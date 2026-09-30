"""Phase D/E bridge tests: research knowledge + platform events API surface.

The planes exist; this proves the command center can SEE them: durable
hypothesis knowledge over /api/v1/knowledge, per-hypothesis evidence
drill-downs, and the typed aios.platform.* stream over /api/v1/platform-events.
"""

import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner


@pytest.fixture()
def ran_runner(tmp_path: Path) -> ReplayRunner:
    from core.config import Settings
    settings = Settings(model_provider="none", autonomy_mode="AUTONOMOUS")
    write_dataset(tmp_path / "golden", symbols=["BTC/USD", "ETH/USD"], total_bars=120)
    runner = ReplayRunner(
        csv_path_by_symbol={
            "BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv",
            "ETH/USD": tmp_path / "golden" / "ETH_USD_1d.csv",
        },
        store_path=tmp_path / "surface.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
        settings=settings,
    )
    asyncio.run(runner.run())
    return runner


def test_knowledge_view_exposes_durable_state(ran_runner: ReplayRunner) -> None:
    builder = ran_runner.build_snapshot_builder()
    view = builder.knowledge()
    assert view["available"] is True
    assert view["hypotheses"] > 0
    assert view["evidence"] > 0
    assert view["statuses"].get("REJECTED", 0) + view["statuses"].get("SUPPORTED", 0) >= 1

    recent = view["recent"]
    assert recent
    sample = recent[0]
    for field in ("hypothesis_id", "statement", "status", "evidence_total", "supports"):
        assert field in sample


def test_hypothesis_detail_returns_evidence_graph(ran_runner: ReplayRunner) -> None:
    builder = ran_runner.build_snapshot_builder()
    view = builder.knowledge()
    settled = next(
        h
        for h in view["recent"]
        if h["status"] in {"SUPPORTED", "REJECTED"}
    )
    detail = builder.hypothesis_detail(settled["hypothesis_id"])
    assert detail["statement"]
    assert detail["status"] in {"SUPPORTED", "REJECTED"}
    relationships = {e["relationship"] for e in detail["evidence"]}
    assert "outcome" in relationships
    for ev in detail["evidence"]:
        assert len(ev["content_hash"]) == 64  # sha256 hex


def test_platform_feed_newest_first_and_typed(ran_runner: ReplayRunner) -> None:
    builder = ran_runner.build_snapshot_builder()
    feed = builder.platform_feed(limit=200)
    assert feed
    kinds = {row["kind"] for row in feed}
    assert "aios.platform.experiment_completed" in kinds
    stamps = [str(row.get("occurred_at", "")) for row in feed]
    assert stamps == sorted(stamps, reverse=True), "feed must be newest-first"


def test_http_endpoints_serve_research_surface(ran_runner: ReplayRunner) -> None:
    from api.server import CommandCenterServer

    server = CommandCenterServer(
        ran_runner.build_snapshot_builder(), ran_runner.build_control_plane(), port=0
    )
    server.start()
    try:
        base = f"http://127.0.0.1:{server.port}"

        with urllib.request.urlopen(f"{base}/api/v1/knowledge", timeout=5) as resp:
            body = json.loads(resp.read())
        assert body["available"] is True and body["recent"]

        hypothesis_id = body["recent"][0]["hypothesis_id"]
        with urllib.request.urlopen(
            f"{base}/api/v1/knowledge/{hypothesis_id}", timeout=5
        ) as resp:
            detail = json.loads(resp.read())
        assert detail["hypothesis_id"] == hypothesis_id

        with urllib.request.urlopen(
            f"{base}/api/v1/platform-events?limit=50", timeout=5
        ) as resp:
            feed = json.loads(resp.read())
        assert feed["events"], "platform feed must not be empty"

        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f"{base}/api/v1/knowledge/does-not-exist", timeout=5)
        assert excinfo.value.code == 404
    finally:
        server.stop()
