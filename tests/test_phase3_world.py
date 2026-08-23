"""Phase 3 Data Fabric & World Intelligence tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from communities.c1_data.ccxt_fetcher import CcxtDataFetcher, _build_exchange
from communities.c10_world.macro_calendar import FileMacroCalendar
from communities.c10_world.regime_engine import RegimeEngine
from communities.c10_world.world_engines import ExpectationEngine, ScenarioEngine
from core.data_quality import AnomalyDetector, SymbolHealthRegistry
from core.event_bus import InMemoryEventBus
from schemas.contracts import (
    DataAnomalyAlert,
    MarketDataPayload,
    NewsSentiment,
    PriceData,
    RegimeState,
    ScenarioSet,
    ScheduledEvent,
)


def _payload(
    symbol: str = "BTC/USD",
    open_: float = 100.0,
    high: float = 102.0,
    low: float = 98.0,
    close: float = 101.0,
    volume: float = 1000.0,
) -> MarketDataPayload:
    return MarketDataPayload(
        symbol=symbol,
        timeframe="1d",
        price_data=PriceData(open=open_, high=high, low=low, close=close, volume=volume),
        news_sentiment=[NewsSentiment(title="t", sentiment_score=0.5, source="x")],
        is_simulated=True,
    )


# ---------------------------------------------------------------- data quality


def test_anomaly_detector_ohlc_invalid_detected_and_freezes() -> None:
    """PriceData schema only enforces positivity, so high<low reaches the detector,
    which must catch it as CRITICAL and freeze the symbol."""
    detector = AnomalyDetector()
    bad = MarketDataPayload(
        symbol="BTC/USD",
        timeframe="1d",
        price_data=PriceData(open=100.0, high=90.0, low=95.0, close=101.0, volume=10.0),
        is_simulated=True,
    )
    alerts = detector.ingest(bad)
    assert len(alerts) == 1
    assert alerts[0].anomaly_type == "OHLC_INVALID"
    assert alerts[0].freezes_symbol is True
    assert alerts[0].severity == "CRITICAL"


def test_health_registry_freeze_lifecycle() -> None:
    health = SymbolHealthRegistry()
    assert health.is_frozen("X/USD") is False

    alert = DataAnomalyAlert(
        symbol="X/USD",
        anomaly_type="PRICE_GAP",
        severity="CRITICAL",
        detail="gap",
        freezes_symbol=True,
        is_simulated=True,
    )
    health.apply_alert(alert)
    assert health.is_frozen("X/USD") is True

    clean = _payload(symbol="X/USD")
    health.apply_payload(clean)
    assert health.is_frozen("X/USD") is False


def test_gap_detection_emits_critical_alert() -> None:
    detector = AnomalyDetector()
    detector.ingest(_payload())
    gapped = _payload(open_=130.0, high=133.0, low=128.0, close=131.0)
    alerts = detector.ingest(gapped)
    gap_alerts = [a for a in alerts if a.anomaly_type == "PRICE_GAP"]
    assert len(gap_alerts) == 1
    assert gap_alerts[0].freezes_symbol is True
    assert gap_alerts[0].severity == "CRITICAL"


def test_volume_spike_warning_does_not_freeze() -> None:
    detector = AnomalyDetector()
    for _ in range(6):
        detector.ingest(_payload())
    spiked = _payload(volume=50000.0)
    alerts = detector.ingest(spiked)
    spikes = [a for a in alerts if a.anomaly_type == "VOLUME_SPIKE"]
    assert len(spikes) == 1
    assert spikes[0].freezes_symbol is False


# ------------------------------------------------------------------- ccxt fetch


class _FakeExchange:
    """Test double standing in for a ccxt exchange client."""

    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def fetch_ohlcv(self, symbol: str, timeframe: str, since, limit: int):
        return self._rows[-limit:]


def test_ccxt_fetcher_with_injected_fake_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        [1700000000000, 100.0, 101.0, 99.0, 100.5, 12.0],
        [1700000060000, 100.5, 103.0, 100.0, 102.0, 15.0],
    ]
    monkeypatch.setattr(
        "communities.c1_data.ccxt_fetcher._build_exchange",
        lambda eid, opts: _FakeExchange(rows),
    )
    fetcher = CcxtDataFetcher(exchange_id="binance")
    data = asyncio.run(fetcher.fetch_price_data("BTC/USD", "1m"))
    assert data["close"] == pytest.approx(102.0)

    provenance = fetcher.provenance()
    assert provenance.source_type == "MARKET"
    assert provenance.quality_state == "LIVE"
    assert provenance.source_id == "ccxt:binance"


def test_ccxt_build_exchange_unknown_id() -> None:
    with pytest.raises(ValueError, match="unknown ccxt exchange"):
        _build_exchange("not_an_exchange", {})


@pytest.mark.skipif(
    __import__("os").environ.get("AIOS_LIVE_TESTS", "") != "1",
    reason="network test; set AIOS_LIVE_TESTS=1 to run live public-endpoint check",
)
def test_ccxt_live_public_endpoint() -> None:
    fetcher = CcxtDataFetcher(exchange_id="binance")
    data = asyncio.run(fetcher.fetch_price_data("BTC/USDT", "1m"))
    assert data["close"] > 0


# ------------------------------------------------------------- world engines


def _calendar_file(tmp_path: Path, with_actual: bool) -> Path:
    now = datetime.now(UTC)
    t0 = (now - timedelta(days=1)).isoformat()
    actual = f"{3.1 if with_actual else ''}"
    content = (
        "event_id,title,event_time,consensus,prior,actual,unit,affected_symbols,is_simulated\n"
        f"evt-001,CPI YoY,{t0},3.0,3.2,{actual},%,SPY;QQQ;BTC/USD,true\n"
    )
    path = tmp_path / "calendar.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_macro_calendar_loads_and_replays_once(tmp_path: Path) -> None:
    cal = FileMacroCalendar(_calendar_file(tmp_path, with_actual=True))
    events = cal.all_events()
    assert len(events) == 1
    assert events[0].affected_symbols == ["SPY", "QQQ", "BTC/USD"]
    assert events[0].is_simulated is True

    past = datetime.now(UTC) + timedelta(days=1)
    due1 = cal.due_events(past)
    due2 = cal.due_events(past)
    assert len(due1) == 1
    assert due2 == []  # each event returns exactly once


def test_expectation_engine_interpretations() -> None:
    bus = InMemoryEventBus()
    engine = ExpectationEngine(bus)

    base = dict(
        event_id="e1", title="CPI", event_time=datetime.now(UTC), unit="%", affected_symbols=[]
    )

    # Hot inflation is WORSE than expected (higher_is_better=False)
    hotter_cpi = ScheduledEvent(
        **base, consensus=3.0, actual=3.4, higher_is_better=False, is_simulated=True
    )
    snap1 = engine.process(hotter_cpi)
    assert snap1 is not None
    assert snap1.interpretation == "WORSE_THAN_EXPECTED"

    cooler_cpi = ScheduledEvent(
        **base, consensus=3.0, actual=2.5, higher_is_better=False, is_simulated=True
    )
    snap2 = engine.process(cooler_cpi)
    assert snap2 is not None and snap2.interpretation == "BETTER_THAN_EXPECTED"

    # GDP convention: higher print is genuinely better
    gdp_base = dict(base, title="GDP")
    hot_gdp = ScheduledEvent(
        **gdp_base, consensus=2.0, actual=2.8, higher_is_better=True, is_simulated=True
    )
    snap3 = engine.process(hot_gdp)
    assert snap3 is not None and snap3.interpretation == "BETTER_THAN_EXPECTED"

    inline = ScheduledEvent(**base, consensus=3.0, actual=3.001, is_simulated=True)
    snap4 = engine.process(inline)
    assert snap4 is not None and snap4.interpretation == "AS_EXPECTED"

    unreleased = ScheduledEvent(**base, consensus=3.0, is_simulated=True)
    assert engine.process(unreleased) is None  # no invention of actuals


def test_scenario_cards_sum_to_one(tmp_path: Path) -> None:
    bus = InMemoryEventBus()

    async def _run() -> ScenarioSet:
        engine = ScenarioEngine(bus)
        event = ScheduledEvent(
            event_id="e9",
            title="FOMC",
            event_time=datetime.now(UTC),
            consensus=5.25,
            is_simulated=True,
        )
        return await engine.on_event(event)

    scenario_set = asyncio.run(_run())
    names = {card.name for card in scenario_set.cards}
    assert {"BASE", "BULL", "BEAR"} <= names
    total = sum(c.probability for c in scenario_set.cards)
    assert abs(total - 1.0) <= 0.01


# ---------------------------------------------------------------- regime engine


def _series_payloads(symbol: str, closes: list[float]) -> list[MarketDataPayload]:
    out = []
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    for i, c in enumerate(closes):
        out.append(
            MarketDataPayload(
                symbol=symbol,
                timeframe="1d",
                timestamp=ts + timedelta(days=i),
                price_data=PriceData(open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1000.0),
                is_simulated=True,
            )
        )
    return out


def test_regime_engine_labels_trend_and_vol() -> None:
    bus = InMemoryEventBus()

    async def _run() -> RegimeState | None:
        engine = RegimeEngine(bus, window_bars=20)
        rising = [100 + i * 2 for i in range(15)]
        for payload in _series_payloads("T/USD", rising):
            await engine.on_data_acquired(payload)
        return engine.current("T/USD")

    state = asyncio.run(_run())
    assert state is not None
    assert state.trend.value == "UP"
    assert state.vol_regime in {"LOW", "NORMAL", "HIGH"}


# ------------------------------------------------------------------ reactions


def test_strategy_agent_freezes_on_anomaly_and_unfreezes_on_clean() -> None:
    from communities.c4_strategy.strategy_agent import StrategyAgent
    from core.risk_firewall import RiskConfig, RiskFirewall
    from schemas.contracts import (
        CandidateHypothesis,
        VerificationReport,
    )

    async def _run() -> tuple[object, object]:
        bus = InMemoryEventBus()
        await bus.start()
        agent = StrategyAgent(bus, RiskFirewall(RiskConfig()))
        await agent.on_data_acquired(_payload())

        alert = DataAnomalyAlert(
            symbol="BTC/USD",
            anomaly_type="PRICE_GAP",
            severity="CRITICAL",
            detail="test freeze",
            freezes_symbol=True,
            is_simulated=True,
        )
        await agent.on_data_anomaly(alert)

        hyp = CandidateHypothesis(
            symbol="BTC/USD",
            thesis="t",
            supporting_arguments=["a"],
            counter_arguments=["b"],
            timeframe="1d",
            expected_risk_reward_ratio=2.0,
        )
        report = VerificationReport(
            hypothesis_id=hyp.hypothesis_id,
            confidence_score=90.0,
            verified_claims=["a"],
            flagged_hallucinations=[],
            verification_notes="ok",
        )
        frozen_result = await agent.generate_strategy(report, hyp)

        clean = MarketDataPayload(
            symbol="BTC/USD",
            timeframe="1d",
            price_data=PriceData(open=101.0, high=103.0, low=99.0, close=102.0, volume=1200.0),
            is_simulated=True,
            provenance=None,
        )
        await agent.on_data_acquired(clean)
        unfrozen_result = await agent.generate_strategy(report, hyp)
        await bus.stop()
        return frozen_result, unfrozen_result

    frozen, unfrozen = asyncio.run(_run())
    assert frozen == []  # NO TRADE while frozen
    assert unfrozen != []  # clean arrival restores


def test_runner_calendar_integration_publishes_scenarios_and_expectations(
    tmp_path: Path,
) -> None:
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=40)
    dataset = {"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"}

    cal = tmp_path / "calendar.csv"
    cal.write_text(
        "event_id,title,event_time,consensus,prior,actual,unit,affected_symbols,is_simulated,higher_is_better\n"
        f"evt-hot,CPI YoY,{datetime(2024, 1, 15, tzinfo=UTC).isoformat()},3.0,3.2,3.8,%,SPY,true,false\n",
        encoding="utf-8",
    )

    runner = ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=tmp_path / "world.db",
        macro_calendar_path=cal,
    )
    asyncio.run(runner.run())

    rows = runner.store._conn.execute(
        "SELECT kind, COUNT(*) AS n FROM event_log WHERE kind IN "
        "('aios.c10.scenarios_published','aios.c10.expectation_updated',"
        "'aios.c1.data_anomaly','aios.c10.regime_changed') "
        "GROUP BY kind"
    ).fetchall()
    kinds = {r["kind"]: r["n"] for r in rows}
    assert kinds.get("aios.c10.scenarios_published", 0) >= 1
    assert kinds.get("aios.c10.expectation_updated", 0) >= 1
    # chain still valid after world events joined the log
    ok, _bad = runner.store.verify_chain()
    assert ok is True
