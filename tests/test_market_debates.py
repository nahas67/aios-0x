"""Market candles (A5), debates (A1) and backtest (B4) HTTP surface.

- A5 ``GET /api/v1/market/candles`` wraps a ``BaseDataFetcher`` (tested with
  the network-free ``SimulatedDataFetcher``); indicators come from
  ``core/indicators.py`` pure functions over the real series.
- A1 ``GET /api/v1/debates`` surfaces recorded debate sessions, else honest
  absence (debates only live in memory during replay).
- B4 ``POST /api/v1/research/backtest`` wraps ``WindowSlicer`` + ``_sharpe`` /
  ``_max_dd_pct`` over a caller-supplied closes array (no network).
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from api.server import CommandCenterServer
from api.views import SystemSnapshotBuilder
from communities.c1_data.data_agent import SimulatedDataFetcher
from communities.c10_world.regime_engine import RegimeEngine
from core.event_bus import InMemoryEventBus
from core.indicators import bollinger, ema, macd, rsi
from core.persistence import SqliteMemoryStore
from schemas.contracts import MarketDataPayload, PriceData


def _get(port: int, path: str) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                headers={"Authorization": "Bearer test-token"},
            ),
            timeout=10,
        ) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return exc.code, {}


def _post(port: int, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer test-token",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return exc.code, {}


def _feed(engine: RegimeEngine, symbol: str, bars: int, base: float = 100.0) -> None:
    async def _go() -> None:
        for i in range(bars):
            px = base + i * 0.5
            await engine.on_data_acquired(
                MarketDataPayload(
                    symbol=symbol,
                    timeframe="1h",
                    price_data=PriceData(
                        open=px, high=px + 1.0, low=px - 1.0, close=px, volume=10.0
                    ),
                    is_simulated=True,
                )
            )

    asyncio.run(_go())


def _builder(tmp_path: Path, **kwargs: Any) -> SystemSnapshotBuilder:
    store = SqliteMemoryStore(tmp_path / "audit.db")
    return SystemSnapshotBuilder(store=store, **kwargs)


@pytest.fixture(scope="module")
def market_port(tmp_path_factory: pytest.TempPathFactory) -> Any:
    workdir = tmp_path_factory.mktemp("market")
    store = SqliteMemoryStore(workdir / "audit.db")
    builder = SystemSnapshotBuilder(store=store, market_fetcher=SimulatedDataFetcher())
    server = CommandCenterServer(builder, None, port=0, auth_token="test-token")
    server.start()
    time.sleep(0.3)
    yield server.port
    server.stop()
    store.close()


@pytest.fixture(scope="module")
def empty_port(tmp_path_factory: pytest.TempPathFactory) -> Any:
    workdir = tmp_path_factory.mktemp("empty")
    store = SqliteMemoryStore(workdir / "audit.db")
    builder = SystemSnapshotBuilder(store=store)
    server = CommandCenterServer(builder, None, port=0)
    server.start()
    time.sleep(0.3)
    yield server.port
    server.stop()
    store.close()


# ------------------------------------------------------------- indicators


def test_ema_insufficient_data_is_none() -> None:
    assert ema([1.0, 2.0], 20) is None
    assert ema([], 5) is None


def test_ema_flat_series_converges_to_level() -> None:
    assert ema([10.0] * 30, 20) == pytest.approx(10.0)


def test_ema_rising_series_lags_last_close() -> None:
    closes = [float(100 + i) for i in range(30)]
    value = ema(closes, 20)
    assert value is not None
    assert value < closes[-1]
    assert value > closes[0]


def test_rsi_insufficient_data_is_none() -> None:
    assert rsi([100.0] * 10, 14) is None


def test_rsi_all_gains_is_100() -> None:
    assert rsi([float(100 + i) for i in range(20)], 14) == pytest.approx(100.0)


def test_rsi_bounds() -> None:
    closes = [100.0, 102.0, 101.0, 103.0, 99.0, 100.5, 98.0, 101.0] * 3
    value = rsi(closes, 14)
    assert value is not None
    assert 0.0 <= value <= 100.0


def test_macd_insufficient_data_is_none() -> None:
    assert macd([100.0] * 10) is None


def test_macd_flat_series_near_zero() -> None:
    result = macd([10.0] * 60)
    assert result is not None
    assert result["macd"] == pytest.approx(0.0, abs=1e-6)
    assert set(result) == {"macd", "signal", "histogram"}


def test_bollinger_insufficient_data_is_none() -> None:
    assert bollinger([1.0, 2.0], 20) is None


def test_bollinger_bands_ordering() -> None:
    closes = [float(100 + (i % 5)) for i in range(30)]
    bands = bollinger(closes, 20)
    assert bands is not None
    assert bands["lower"] <= bands["middle"] <= bands["upper"]
    assert bands["upper"] > bands["lower"]


# ------------------------------------------------------------------ A5


def test_candles_from_simulated_fetcher(tmp_path: Path) -> None:
    builder = _builder(tmp_path, market_fetcher=SimulatedDataFetcher())
    payload = builder.market_candles("BTC/USD", "1h")
    assert payload["available"] is True
    assert payload["symbol"] == "BTC/USD"
    assert payload["tf"] == "1h"
    candle = payload["candles"][0]
    assert set(candle) >= {"time", "open", "high", "low", "close", "volume"}
    assert candle["high"] >= candle["low"]
    assert set(payload["indicators"]) >= {"ema20", "ema50", "rsi14", "macd", "bollinger"}


def test_candles_indicators_from_real_history(tmp_path: Path) -> None:
    engine = RegimeEngine(event_bus=InMemoryEventBus(), window_bars=60)
    _feed(engine, "ETH/USD", 60)
    builder = _builder(
        tmp_path, market_fetcher=SimulatedDataFetcher(), regime_engine=engine
    )
    payload = builder.market_candles("ETH/USD", "1h")
    assert payload["available"] is True
    assert payload["indicators"]["ema20"] is not None
    assert payload["indicators"]["rsi14"] is not None
    assert 0.0 <= payload["indicators"]["rsi14"] <= 100.0
    assert payload["indicators"]["bollinger"] is not None


def test_candles_missing_params_raise(tmp_path: Path) -> None:
    builder = _builder(tmp_path, market_fetcher=SimulatedDataFetcher())
    with pytest.raises(ValueError, match="symbol and tf"):
        builder.market_candles("", "1h")
    with pytest.raises(ValueError, match="symbol and tf"):
        builder.market_candles("BTC/USD", "")


def test_candles_without_fetcher_is_honest_absence(tmp_path: Path) -> None:
    payload = _builder(tmp_path).market_candles("BTC/USD", "1h")
    assert payload["available"] is False
    assert "reason" in payload


def test_candles_fetcher_failure_is_honest_absence(tmp_path: Path) -> None:
    class _Boom(SimulatedDataFetcher):
        async def fetch_price_data(self, symbol: str, timeframe: str) -> dict[str, Any]:
            raise RuntimeError("venue down")

    payload = _builder(tmp_path, market_fetcher=_Boom()).market_candles("BTC/USD", "1h")
    assert payload["available"] is False
    assert "reason" in payload


def test_candles_routed(market_port: int) -> None:
    status, payload = _get(market_port, "/api/v1/market/candles?symbol=BTC/USD&tf=1h")
    assert status == 200, payload
    assert payload["available"] is True
    assert payload["candles"][0]["close"] > 0


def test_candles_missing_params_is_400(market_port: int) -> None:
    status, payload = _get(market_port, "/api/v1/market/candles?symbol=BTC/USD")
    assert status == 400
    assert "error" in payload


def test_candles_unwired_is_honest_absence(empty_port: int) -> None:
    status, payload = _get(empty_port, "/api/v1/market/candles?symbol=BTC/USD&tf=1h")
    assert status == 200
    assert payload["available"] is False


# ------------------------------------------------------------------ A1


def test_debates_empty_is_honest_absence(tmp_path: Path) -> None:
    payload = _builder(tmp_path).debates_view()
    assert payload["available"] is False
    assert "no debates recorded" in payload["reason"]


def test_debates_shape(tmp_path: Path) -> None:
    builder = _builder(
        tmp_path,
        debate_sessions=[
            {
                "id": "d-1",
                "symbol": "BTC/USD",
                "side": "LONG",
                "status": "COMPLETE",
                "consensusScorePct": 72.5,
                "turns": [
                    {
                        "agentId": "BULL",
                        "stance": "BULL",
                        "thesis": "momentum positive",
                        "confidencePct": 80.0,
                    }
                ],
            }
        ],
    )
    payload = builder.debates_view()
    assert payload["available"] is True
    session = payload["debates"][0]
    assert session["id"] == "d-1"
    assert session["turns"][0]["agentId"] == "BULL"


def test_debates_transcript_turns_normalised(tmp_path: Path) -> None:
    builder = _builder(
        tmp_path,
        debate_sessions=[
            {
                "id": "t-1",
                "symbol": "ETH/USD",
                "turns": [{"role": "BEAR", "content": "overbought on the hourly"}],
            }
        ],
    )
    payload = builder.debates_view()
    turn = payload["debates"][0]["turns"][0]
    assert turn["agentId"] == "BEAR"
    assert turn["thesis"] == "overbought on the hourly"


def test_debates_routed_empty(empty_port: int) -> None:
    status, payload = _get(empty_port, "/api/v1/debates")
    assert status == 200
    assert payload["available"] is False


# ------------------------------------------------------------------ B4


def test_backtest_pure_computation(tmp_path: Path) -> None:
    builder = _builder(tmp_path)
    closes = [float(100 + i * 0.3 + (i % 7)) for i in range(300)]
    payload = builder.research_backtest(closes, train_bars=90, test_bars=30)
    assert isinstance(payload["sharpe"], float)
    assert payload["max_dd_pct"] >= 0.0
    assert len(payload["windows"]) > 0
    window = payload["windows"][0]
    assert set(window) >= {"window_index", "test_sharpe", "test_max_dd_pct"}


def test_backtest_rejects_bad_input(tmp_path: Path) -> None:
    builder = _builder(tmp_path)
    with pytest.raises(ValueError, match="at least"):
        builder.research_backtest([1.0, 2.0])
    with pytest.raises(ValueError, match="5000"):
        builder.research_backtest([1.0] * 5001)
    with pytest.raises(ValueError, match="number"):
        builder.research_backtest([1.0, "x", 3.0])  # type: ignore[list-item]


def test_backtest_routed(market_port: int) -> None:
    closes = [float(100 + i * 0.2) for i in range(200)]
    status, payload = _post(
        market_port,
        "/api/v1/research/backtest",
        {"closes": closes, "train_bars": 90, "test_bars": 30},
    )
    assert status == 200, payload
    assert "sharpe" in payload
    assert "max_dd_pct" in payload
    assert len(payload["windows"]) > 0


def test_backtest_routed_bad_input_is_400(market_port: int) -> None:
    status, payload = _post(market_port, "/api/v1/research/backtest", {"closes": [1.0]})
    assert status == 400
    assert "error" in payload


# ------------------------------------------------- serve wiring (plan §6)


def _serve_runner(tmp_path: Path) -> Any:
    """Minimal serve-composition runner: golden CSV + file store, no network."""
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=40)
    return ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "serve.db",
    )


def test_serve_builder_wires_market_fetcher(tmp_path: Path) -> None:
    builder = _serve_runner(tmp_path).build_snapshot_builder()
    assert builder.market_fetcher is not None
    payload = builder.market_candles("BTC/USD", "1h")
    assert payload["available"] is True
    assert payload["candles"][0]["close"] > 0


def test_serve_debates_honest_absence_without_llm(tmp_path: Path) -> None:
    builder = _serve_runner(tmp_path).build_snapshot_builder()
    payload = builder.debates_view()
    assert payload["available"] is False
    assert "MODEL_PROVIDER=none" in payload["reason"]


def test_serve_builder_surfaces_recorded_transcripts(tmp_path: Path) -> None:
    runner = _serve_runner(tmp_path)
    runner.store.append_event(
        "TRANSCRIPT",
        None,
        {
            "json": json.dumps(
                {
                    "transcript_id": "t-serve-1",
                    "symbol": "BTC/USD",
                    "timeframe": "1d",
                    "turns": [{"role": "BULL", "content": "momentum positive"}],
                }
            )
        },
    )
    payload = runner.build_snapshot_builder().debates_view()
    assert payload["available"] is True
    assert payload["debates"][0]["turns"][0]["agentId"] == "BULL"


def test_serve_control_plane_receives_reconciliation_engine(tmp_path: Path) -> None:
    runner = _serve_runner(tmp_path)
    plane = runner.build_control_plane()
    assert plane.reconciliation_engine is runner.reconciliation
