"""SSE live stream + model registry tests.

Sprint 2 finisher: the command center streams executive + platform state via
Server-Sent Events (stdlib only). Model registry: the deterministic strategy
stack is registered as a feature-pinned model version and evaluated with real
run metrics — no more empty registry.
"""

import asyncio
import http.client
import json
from pathlib import Path

from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner


def _run(tmp_path: Path, bars: int = 120) -> ReplayRunner:
    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=bars)
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "sse.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
    )
    asyncio.run(runner.run())
    return runner


# ------------------------------------------------------------------- model


def test_deterministic_baseline_registered_and_evaluated(tmp_path: Path) -> None:
    runner = _run(tmp_path)
    models = runner.kernel_bridge.kernel.models
    mv = models.get("deterministic_baseline", "v1")
    assert mv.model_type == "rule_stack"
    assert mv.feature_ref["feature_id"] == "ohlcv_passthrough"
    assert mv.status.value == "EVALUATED"
    assert "directional_accuracy_pct" in mv.evaluation_metrics
    assert "cumulative_pnl" in mv.evaluation_metrics

    # provenance: feature -> model edge exists
    provenance = runner.kernel_bridge.kernel.provenance
    upstream = {n.node_id for n in provenance.lineage_backward("deterministic_baseline:v1")}
    assert any("ohlcv_passthrough" in node for node in upstream)


# --------------------------------------------------------------------- SSE


def test_sse_stream_pushes_live_snapshots(tmp_path: Path) -> None:
    from api.server import CommandCenterServer

    runner = _run(tmp_path)
    server = CommandCenterServer(
        runner.build_snapshot_builder(), runner.build_control_plane(), port=0
    )
    server.start()
    conn = None
    try:
        base_port = server.port
        conn = http.client.HTTPConnection("127.0.0.1", base_port, timeout=10)
        conn.request("GET", "/api/v1/stream")
        resp = conn.getresponse()
        assert resp.status == 200
        # The media type is what matters; the charset parameter is optional.
        content_type = resp.getheader("Content-Type") or ""
        assert content_type.split(";")[0].strip() == "text/event-stream"

        received: list[dict] = []
        assert resp.fp is not None
        deadline_chunks = 40
        while len(received) < 2 and deadline_chunks > 0:
            line = resp.fp.readline()
            if not line:
                break
            if line.startswith(b"data: "):
                received.append(json.loads(line[len(b"data: "):].strip()))
                deadline_chunks -= 1
            deadline_chunks -= 1

        assert len(received) >= 2, "expected at least two SSE ticks"
        first, second = received[0], received[1]
        for payload in (first, second):
            assert "executive" in payload and "platform_tail" in payload
        assert first["executive"]["chain_valid"] is True
        # two ticks => time actually advanced between snapshots
        assert second["ts"] > first["ts"]
    finally:
        if conn is not None:
            conn.close()
        server.stop()


def test_sse_platform_tail_carries_events(tmp_path: Path) -> None:
    from api.server import CommandCenterServer

    runner = _run(tmp_path)
    server = CommandCenterServer(runner.build_snapshot_builder(), port=0)
    server.start()
    conn = None
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
        conn.request("GET", "/api/v1/stream")
        resp = conn.getresponse()
        line = b""
        while True:
            line = resp.fp.readline()  # type: ignore[union-attr]
            if line.startswith(b"data: "):
                break
        payload = json.loads(line[len(b"data: "):].strip())
        tail = payload["platform_tail"]
        assert isinstance(tail, list)
        assert any(
            str(e.get("kind", "")).startswith("aios.platform.") for e in tail
        ), "platform tail must carry aios.platform.* events"
    finally:
        if conn is not None:
            conn.close()
        server.stop()


def test_ui_ships_eventsource_consumer(tmp_path: Path) -> None:
    """The SPA must consume the stream, not just poll.

    The app hand-rolls SSE over fetch + ReadableStream instead of native
    EventSource because EventSource cannot send an Authorization bearer
    header, and stream requests must carry operator identity.
    """
    stream = Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "stream.ts"
    text = stream.read_text(encoding="utf-8")
    assert "/api/v1/stream" in text
    assert "ReadableStream" in text
