"""Phase 4 tests: opportunity ranking, mean reversion, portfolio governor, research tools."""

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from communities.c4_strategy.families import MeanReversionFamily
from communities.c4_strategy.opportunity import alpha_decay_multiplier, rank, score_candidate
from communities.c9_portfolio.portfolio import PortfolioGovernor
from core.event_bus import InMemoryEventBus
from core.persistence import SqliteMemoryStore
from research.integrity import RunnerConfigFacts, lint_dataset, lint_runner_config
from research.walkforward import calibration_report
from schemas.contracts import (
    MarketDataPayload,
    NewsSentiment,
    PortfolioAllocationPlan,
    PortfolioStatus,
    PriceData,
    StrategySpecification,
)


def _payload(close: float, prev_close: float | None = None) -> MarketDataPayload:
    open_ = prev_close if prev_close is not None else close * 0.995
    return MarketDataPayload(
        symbol="BTC/USD",
        timeframe="1d",
        price_data=PriceData(
            open=open_,
            high=max(open_, close) * 1.005,
            low=min(open_, close) * 0.995,
            close=close,
            volume=1000.0,
        ),
        news_sentiment=[NewsSentiment(title="t", sentiment_score=0.0, source="x")],
        is_simulated=True,
    )


# ------------------------------------------------------------------ opportunity


def test_alpha_decay_halves_at_half_life() -> None:
    assert alpha_decay_multiplier("1d", 0) == pytest.approx(1.0)
    assert alpha_decay_multiplier("1d", 5) == pytest.approx(0.5)
    assert alpha_decay_multiplier("1d", 10) == pytest.approx(0.25)


def test_score_ranks_higher_edge_first() -> None:
    def _spec(rr_distance: float) -> StrategySpecification:
        return StrategySpecification(
            hypothesis_id="h",
            symbol="BTC/USD",
            action="BUY",
            entry_price=100.0,
            stop_loss_price=100.0 - rr_distance,
            take_profit_price=100.0 + rr_distance * 2,
            position_size_pct=1.0,
        )

    strong = score_candidate(_spec(2.0), "momentum", confidence_pct=85)
    weak = score_candidate(_spec(2.0), "momentum", confidence_pct=55)
    ranked = rank([weak, strong])
    assert ranked[0].strategy_id == strong.strategy_id
    # breakeven p for RR=2 is 1/3; confidence 85% -> positive edge; 55% -> ~+0.22
    assert strong.edge_proxy > weak.edge_proxy > 0


# ------------------------------------------------------------- mean reversion


def test_mean_reversion_fires_on_extreme_drop() -> None:
    from collections import deque

    family = MeanReversionFamily(min_history=10, zscore_threshold=2.0)
    # Mild oscillation gives nonzero stdev; agent appends the crash close last.
    base = [100.0 + (0.4 if i % 2 else -0.4) for i in range(12)]
    history: deque[float] = deque(base, maxlen=30)
    history.append(90.0)  # current bar: -10% crash
    payload = _payload(close=90.0, prev_close=100.0)
    candidate = family.evaluate("BTC/USD", payload, history, sentiment_avg=0.0)
    assert candidate is not None
    assert candidate.action == "BUY"
    assert candidate.family == "mean_reversion"


def test_mean_reversion_silent_in_calm_regime() -> None:
    from collections import deque

    family = MeanReversionFamily(min_history=10)
    history: deque[float] = deque([100.0 + i * 0.1 for i in range(12)], maxlen=30)
    payload = _payload(close=101.0, prev_close=100.9)
    assert family.evaluate("BTC/USD", payload, history, sentiment_avg=0.5) is None


# ------------------------------------------------------------------- governor


def _governor(equity: float, exposures: dict[str, float], bus: InMemoryEventBus):
    return PortfolioGovernor(
        event_bus=bus,
        initial_equity=100000.0,
        equity_provider=lambda: equity,
        exposure_by_class_provider=lambda: exposures,
    )


def _spec(size: float = 5.0, symbol: str = "AAPL") -> StrategySpecification:
    return StrategySpecification(
        hypothesis_id="h",
        symbol=symbol,
        action="BUY",
        entry_price=100.0,
        stop_loss_price=97.0,
        take_profit_price=106.0,
        position_size_pct=size,
    )


def test_governor_approves_healthy() -> None:
    governor = _governor(100000.0, {}, InMemoryEventBus())
    plan = governor.evaluate(_spec())
    assert plan.approved is True
    assert plan.portfolio_status == PortfolioStatus.HEALTHY
    assert plan.final_position_size_pct == 5.0


def test_governor_drawdown_tiers_scale_and_halt() -> None:
    warn = _governor(98500.0, {}, InMemoryEventBus())  # 1.5% dd
    plan_warn = warn.evaluate(_spec())
    assert plan_warn.portfolio_status == PortfolioStatus.WARNING
    assert plan_warn.final_position_size_pct == pytest.approx(3.75)

    halt = _governor(97000.0, {}, InMemoryEventBus())  # 3.0% dd
    plan_halt = halt.evaluate(_spec())
    assert plan_halt.approved is False
    assert plan_halt.portfolio_status == PortfolioStatus.CRITICAL_HALT
    assert plan_halt.final_position_size_pct == 0.0


def test_governor_class_cap_scales_down() -> None:
    # EQUITY already at 33%; adding 5% would breach 35% cap
    governor = _governor(100000.0, {"EQUITY": 33000.0}, InMemoryEventBus())
    plan = governor.evaluate(_spec(size=5.0))
    assert plan.approved is True
    assert plan.final_position_size_pct <= 2.0 + 1e-6
    assert any("cap" in r.lower() for r in plan.reasons)


def test_governor_kelly_requires_calibration_samples() -> None:
    bus = InMemoryEventBus()
    no_data = PortfolioGovernor(
        event_bus=bus,
        initial_equity=100000.0,
        equity_provider=lambda: 100000.0,
        exposure_by_class_provider=lambda: {},
        win_rate_provider=lambda s: (0.7, 5),  # too few samples -> ignored
    )
    plan = no_data.evaluate(_spec())
    assert plan.kelly_fraction_used is None

    calibrated = PortfolioGovernor(
        event_bus=bus,
        initial_equity=100000.0,
        equity_provider=lambda: 100000.0,
        exposure_by_class_provider=lambda: {},
        win_rate_provider=lambda s: (0.70, 50),
    )
    plan2 = calibrated.evaluate(_spec())
    assert plan2.kelly_fraction_used is not None and plan2.kelly_fraction_used > 0


async def _collect_plan(bus: InMemoryEventBus) -> list[PortfolioAllocationPlan]:
    plans: list[PortfolioAllocationPlan] = []

    async def sink(plan: PortfolioAllocationPlan) -> None:
        plans.append(plan)

    await bus.subscribe(
        __import__("core.event_bus", fromlist=["EventTopic"]).EventTopic.PORTFOLIO_ALLOCATED, sink
    )
    return plans


def test_paper_engine_executes_approved_plan_only() -> None:
    from simulation.paper_engine import PaperEngine

    async def _run():
        bus = InMemoryEventBus()
        await bus.start()
        engine = PaperEngine(bus, initial_balance=100000.0)
        governor = _governor(100000.0, {"EQUITY": 34000.0}, bus)
        await bus.subscribe(
            __import__("core.event_bus", fromlist=["EventTopic"]).EventTopic.PORTFOLIO_ALLOCATED,
            engine.on_plan,
        )

        spec = _spec(size=5.0)
        await governor.on_strategy_generated(spec)  # publishes scaled plan
        await bus.wait_until_idle()

        executed_qty = list(engine.open_positions.values())
        await bus.stop()
        return executed_qty

    positions = asyncio.run(_run())
    assert len(positions) == 1
    assert positions[0].receipt.filled_quantity > 0


# ------------------------------------------------------------------ integrity


def test_integrity_linters_pass_on_clean_config() -> None:
    rows = [
        {
            "timestamp": f"2024-01-{i:02d}T00:00:00+00:00",
            "open": "1",
            "high": "2",
            "low": "0.5",
            "close": "1.5",
        }
        for i in range(1, 6)
    ]
    report = lint_dataset(rows, symbol_count=7)
    assert report.passed is True

    config_report = lint_runner_config(
        RunnerConfigFacts(
            slippage_pct=0.05,
            taker_fee_pct=0.1,
            position_cap_per_symbol=1,
            uses_bracket_exits=True,
            no_same_bar_exit=True,
            as_of_fetcher=True,
        )
    )
    assert config_report.passed is True

    bad = lint_runner_config(
        RunnerConfigFacts(
            slippage_pct=0.0,
            taker_fee_pct=0.0,
            position_cap_per_symbol=1,
            uses_bracket_exits=False,
            no_same_bar_exit=False,
            as_of_fetcher=False,
        )
    )
    assert bad.passed is False
    assert len([c for c in bad.checks if not c.passed]) >= 4


# ----------------------------------------------------------------- e2e via runner


def test_runner_routes_through_governor(tmp_path: Path) -> None:
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=40)
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "gov.db",
    )
    summary = asyncio.run(runner.run())

    rows = runner.store._conn.execute(
        "SELECT kind, COUNT(*) AS n FROM event_log WHERE kind IN "
        "('aios.c4.strategy_generated','aios.c9.portfolio_allocated','aios.c4.opportunity_ranked') "
        "GROUP BY kind"
    ).fetchall()
    kinds = {r["kind"]: r["n"] for r in rows}
    assert kinds.get("aios.c4.strategy_generated", 0) >= summary.trades_closed
    assert kinds.get("aios.c9.portfolio_allocated", 0) >= summary.trades_closed
    ok, _bad = runner.store.verify_chain()
    assert ok is True


def test_calibration_report_buckets_and_brier(tmp_path: Path) -> None:
    store = SqliteMemoryStore(Path(tempfile.mkdtemp()) / "cal.db")
    from schemas.contracts import PredictionRecord

    for i in range(25):
        confident_correct = i % 4 != 0  # 80% of high-confidence correct
        rec = PredictionRecord(
            hypothesis_id=f"h{i}",
            strategy_id=f"s{i}",
            symbol="BTC/USD",
            direction="BUY",
            entry_reference_price=100.0,
            target_price=106.0,
            stop_price=97.0,
            horizon_timeframe="1d",
            confidence_score=90.0 if confident_correct else 60.0,
            expected_risk_reward_ratio=2.0,
            decision_bar_timestamp=datetime.now(UTC),
        )
        scored = rec.score(
            exit_price=106.0,
            exit_reason="TARGET_HIT",
            realized_pnl=10.0,
            direction_correct=confident_correct,
        )
        store.save_prediction(scored)

    report = calibration_report(store._conn)
    assert report.total_scored == 25
    assert report.reliable is True
    assert 0.0 <= report.brier_score <= 1.0
    assert len(report.buckets) >= 1
