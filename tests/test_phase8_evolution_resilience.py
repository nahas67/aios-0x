"""Phase 8 tests: challenger trials, reputation, disaster drills."""

import asyncio
from pathlib import Path

import pytest

from core.challenger import ChallengeRegistry, TrialState
from core.persistence import SqliteMemoryStore
from core.reputation import compute_reputations
from research.disaster import (
    drill_corrupt_feed_freeze,
    drill_ingestion_outage,
    drill_kill_switch_end_to_end,
    drill_memory_poisoning_and_tamper,
)
from simulation.generate_golden_data import write_dataset


@pytest.fixture()
def small_csv(tmp_path: Path) -> Path:
    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=60)
    return tmp_path / "golden" / "BTC_USD_1d.csv"


# ------------------------------------------------------------------ challenger


def test_challenger_promotion_requires_human_gate(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "trial.db")
    registry = ChallengeRegistry(store)

    trial = registry.propose("mean-reversion-rr-2.0", metric="pnl")
    assert trial.state == TrialState.PROPOSED

    # Promotion before evaluation is refused
    with pytest.raises(PermissionError, match="EVALUATED"):
        registry.promote("mean-reversion-rr-2.0", operator_id="human-1")

    class FakeSummary:
        def __init__(self, pnl: float, acc: float = 55.0):
            self.trades_closed = 10
            self.cumulative_pnl = pnl
            self.directional_accuracy_pct = acc
            self.max_drawdown_pct = 1.0

    async def _evaluate():
        async def run_side(side: str):
            return FakeSummary(200.0 if side == "challenger" else 100.0)

        return await registry.evaluate(
            "mean-reversion-rr-2.0",
            run_configured_runner=run_side,
            families_factory=lambda side: [object()],
        )

    rec = asyncio.run(_evaluate())
    assert rec["recommendation"] == "PROMOTE"
    assert registry.trials["mean-reversion-rr-2.0"].state == TrialState.EVALUATED

    result = registry.promote("mean-revision-typo" if False else "mean-reversion-rr-2.0", "human-1")
    assert result["promoted"] is True
    assert registry.trials["mean-reversion-rr-2.0"].state == TrialState.PROMOTED

    decisions = store.iter_event_payloads("CHALLENGER_DECISION")
    assert decisions and decisions[-1]["by"] == "human-1"


def test_challenger_rejects_on_negative_evidence(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "rej.db")
    registry = ChallengeRegistry(store)
    registry.propose("worse-challenger", metric="pnl")

    class FakeSummary:
        trades_closed = 5
        directional_accuracy_pct = 40.0
        max_drawdown_pct = 2.0

        def __init__(self, pnl: float):
            self.cumulative_pnl = pnl

    async def _run():
        async def run_side(side: str):
            return FakeSummary(-500.0 if side == "challenger" else 100.0)

        await registry.evaluate(
            "worse-challenger",
            run_configured_runner=run_side,
            families_factory=lambda s: [],
        )
        # §21 fail-closed: a FAIL verdict makes promotion impossible even for
        # a human operator — the evidence cannot be overruled.
        with pytest.raises(PermissionError, match="cannot overrule"):
            registry.promote("worse-challenger", "human-2")
        return {"promoted": False}

    result = asyncio.run(_run())
    assert result["promoted"] is False
    assert registry.trials["worse-challenger"].state == TrialState.EVALUATED
    records = store.iter_event_payloads("EVALUATION_RECORD")
    assert any(r["verdict"] == "FAIL" for r in records)


# ------------------------------------------------------------------ reputation


def test_reputation_unknown_below_sample_gate_and_scored_above(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from schemas.contracts import PredictionRecord

    store = SqliteMemoryStore(tmp_path / "rep.db")

    def _add(strategy_id: str, family: str, correct: bool, confidence: float = 80.0) -> None:
        rec = PredictionRecord(
            hypothesis_id=f"h-{strategy_id}",
            strategy_id=strategy_id,
            symbol="BTC/USD",
            direction="BUY",
            entry_reference_price=100.0,
            target_price=106.0,
            stop_price=97.0,
            horizon_timeframe="1d",
            confidence_score=confidence,
            expected_risk_reward_ratio=2.0,
            decision_bar_timestamp=datetime.now(UTC),
        )
        scored = rec.score(
            exit_price=106.0 if correct else 97.0,
            exit_reason="TARGET_HIT" if correct else "STOP_HIT",
            realized_pnl=10.0 if correct else -5.0,
            direction_correct=correct,
        )
        store.save_prediction(scored)

    # Wire strategy->family mapping via the audit log the way the runner does
    store.append_event(
        "aios.c4.strategy_generated",
        None,
        {"strategy_id": "s-low", "hypothesis_id": "h-s-low", "family": "momentum"},
    )
    for i in range(5):  # below gate of 10
        _add("s-low", "momentum", correct=i % 2 == 0)

    report = compute_reputations(store)
    momentum_low = report["families"]["momentum"]
    assert momentum_low["state"] == "INSUFFICIENT_SAMPLES"
    assert momentum_low["reputation"] is None

    store.append_event(
        "aios.c4.strategy_generated",
        None,
        {"strategy_id": "s-ok", "hypothesis_id": "h-s-ok", "family": "mean_reversion"},
    )
    for i in range(12):  # above gate; strong record
        _add("s-ok", "mean_reversion", correct=i % 5 != 0)  # ~80% accuracy

    report2 = compute_reputations(store)
    mr = report2["families"]["mean_reversion"]
    assert mr["state"] == "ACTIVE"
    assert mr["reputation"] is not None and mr["reputation"] > 50
    assert mr["scored_predictions"] == 12


# ------------------------------------------------------------ disaster drills


def test_drill_ingestion_outage(small_csv: Path, tmp_path: Path) -> None:
    result = asyncio.run(drill_ingestion_outage(small_csv, tmp_path / "outage.db"))
    assert result["passed"] is True, result
    assert result["failures_injected"] >= 3
    assert result["data_failure_escalations"] >= 3
    assert result["chain_valid"] is True


def test_drill_corrupt_feed_freeze(small_csv: Path, tmp_path: Path) -> None:
    result = asyncio.run(drill_corrupt_feed_freeze(small_csv, tmp_path / "poison_feed.db"))
    assert result["passed"] is True, result
    assert result["freezing_flag_set"] is True


def test_drill_memory_poisoning_and_tamper(tmp_path: Path) -> None:
    result = asyncio.run(drill_memory_poisoning_and_tamper(tmp_path))
    assert result["passed"] is True, result


def test_drill_kill_switch_end_to_end(small_csv: Path, tmp_path: Path) -> None:
    result = asyncio.run(drill_kill_switch_end_to_end(small_csv, tmp_path / "ks.db"))
    assert result["passed"] is True, result
    assert result["positions_flat_at_end"] is True
