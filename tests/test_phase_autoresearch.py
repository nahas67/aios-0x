"""AutoResearch tests: the UPDATE-HYPOTHESIS-SPACE step of the core loop.

Proves that settled knowledge deterministically widens the hypothesis space:
inversion theses for chronically-rejected symbols, continuation theses for
repeat winners — durable, lineage-linked, kernel-tracked, challenger-staged,
and idempotent across sessions. Nothing auto-promotes.
"""

import asyncio
from pathlib import Path

import pytest

from core.research_store import SqliteResearchStore
from research.auto_research import AutoResearchEngine, as_candidate, outcome_evidence_summary
from research.engine import HypothesisEngine
from schemas.contracts import (
    CandidateHypothesis,
    VerificationReport,
)
from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner


def _candidate(symbol: str) -> CandidateHypothesis:
    return CandidateHypothesis(
        symbol=symbol,
        thesis=f"test thesis {symbol}",
        supporting_arguments=["s"],
        counter_arguments=["c"],
        timeframe="1d",
        expected_risk_reward_ratio=2.0,
    )


def _report(hypothesis_id: str, verified: bool = True) -> VerificationReport:
    return VerificationReport(
        hypothesis_id=hypothesis_id,
        confidence_score=85.0 if verified else 40.0,
        verified_claims=["x"] if verified else [],
        flagged_hallucinations=[],
        verification_notes="unit",
    )


def _seed(engine: HypothesisEngine, symbol: str, outcomes: list[bool]) -> None:
    """Settle `len(outcomes)` hypotheses on one symbol with given directions."""
    from schemas.contracts import CandidateHypothesis as CH

    for i, correct in enumerate(outcomes):
        c = CH(
            symbol=symbol,
            thesis=f"{symbol} thesis #{i}",
            supporting_arguments=["s"],
            counter_arguments=["c"],
            timeframe="1d",
            expected_risk_reward_ratio=2.0,
        )
        engine.register_from_candidate(c)
        engine.apply_verification(_report(c.hypothesis_id))
        engine.apply_outcome(
            c.hypothesis_id, direction_correct=correct, realized_pnl=50.0 if correct else -30.0
        )


# ------------------------------------------------------------------ synthesis


def test_inversion_proposed_for_chronically_rejected_symbol(tmp_path: Path) -> None:
    store = SqliteResearchStore(tmp_path / "r.db")
    engine = HypothesisEngine(store)
    _seed(engine, "DOGE/USD", [False, False, False])

    proposals = AutoResearchEngine(store).synthesize()
    assert len(proposals) == 1
    p = proposals[0]
    assert p.symbol == "DOGE/USD"
    assert "mean-reversion" in p.statement or "Mean" in p.statement
    assert p.status.value == "UNTESTED"
    assert len(p.parent_hypotheses) == 3, "lineage must link the rejected hypotheses"
    assert p.applicable_regime.startswith("auto_research:")


def test_continuation_proposed_for_repeat_supported_symbol(tmp_path: Path) -> None:
    store = SqliteResearchStore(tmp_path / "r.db")
    engine = HypothesisEngine(store)
    _seed(engine, "SPY", [True, True])

    proposals = AutoResearchEngine(store).synthesize()
    assert len(proposals) == 1
    assert "continuation" in proposals[0].statement.lower()
    assert len(proposals[0].parent_hypotheses) == 2


def test_no_proposal_for_mixed_or_thin_evidence(tmp_path: Path) -> None:
    store = SqliteResearchStore(tmp_path / "r.db")
    engine = HypothesisEngine(store)
    _seed(engine, "MIXED", [True, False])   # mixed: no rule fires
    _seed(engine, "THIN", [False])          # single outcome: below threshold

    assert AutoResearchEngine(store).synthesize() == []


def test_synthesis_is_idempotent_across_sessions(tmp_path: Path) -> None:
    db = tmp_path / "r.db"

    def fresh() -> tuple[HypothesisEngine, list]:
        store = SqliteResearchStore(db)
        engine = HypothesisEngine(store)
        return engine, AutoResearchEngine(store).synthesize()

    engine_a, first = fresh()
    _seed(engine_a, "AAA", [False, False])
    (proposal,) = AutoResearchEngine(SqliteResearchStore(db)).synthesize()
    AutoResearchEngine(SqliteResearchStore(db)).register(proposal)

    # a brand-new session must NOT re-propose the same signature
    _, second = fresh()
    assert second == []
    assert proposal.hypothesis_id in {
        h.hypothesis_id for h in SqliteResearchStore(db).list_hypotheses()
    }


def test_outcome_summary_helper(tmp_path: Path) -> None:
    store = SqliteResearchStore(tmp_path / "r.db")
    engine = HypothesisEngine(store)
    c = _candidate("SUM")
    engine.register_from_candidate(c)
    engine.apply_verification(_report(c.hypothesis_id))
    engine.apply_outcome(c.hypothesis_id, False, -25.5)

    summary = outcome_evidence_summary(store, c.hypothesis_id)
    assert summary["outcomes"] == 1
    assert summary["realized_pnl_total"] == pytest.approx(-25.5)


# ---------------------------------------------------------------- runner wiring


def test_runner_autoresearch_closes_the_loop(tmp_path: Path) -> None:
    from core.config import Settings

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=120)
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "run.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
        settings=Settings(model_provider="none"),
    )
    asyncio.run(runner.run())

    # proposals exist as UNTESTED durable knowledge with auto rationale
    autos = [
        h
        for h in runner.research_store.list_hypotheses(limit=5000)
        if h.rationale.startswith("auto_research:")
    ]
    # this dataset's outcomes may support, reject, or both; at least one rule fired
    assert autos, "auto-research must propose from settled outcomes"
    for h in autos:
        assert h.status.value == "UNTESTED"
        assert all(len(pid) > 0 for pid in h.parent_hypotheses)
        # kernel-tracked through the bridge
        state = runner.kernel_bridge.kernel.state_machine.get_state("hypothesis", h.hypothesis_id)
        assert state == "UNTESTED"
        # challenger staged for human-gated evaluation
        trial_name = f"auto:{h.hypothesis_id[:8]}"
        assert trial_name in runner.build_challenge_registry().trials


def test_runner_flag_off_disables_autoresearch(tmp_path: Path) -> None:
    from core.config import Settings

    write_dataset(tmp_path / "golden", symbols=["SPY"], total_bars=90)
    runner = ReplayRunner(
        csv_path_by_symbol={"SPY": tmp_path / "golden" / "SPY_1d.csv"},
        store_path=tmp_path / "off.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
        settings=Settings(model_provider="none", auto_research=False),
    )
    asyncio.run(runner.run())
    autos = [
        h
        for h in runner.research_store.list_hypotheses(limit=5000)
        if h.rationale.startswith("auto_research:")
    ]
    assert autos == []


def test_as_candidate_preserves_identity(tmp_path: Path) -> None:
    store = SqliteResearchStore(tmp_path / "r.db")
    engine = HypothesisEngine(store)
    _seed(engine, "K", [True, True])
    (p,) = AutoResearchEngine(store).synthesize()
    candidate = as_candidate(p)
    assert candidate.hypothesis_id == p.hypothesis_id
    assert candidate.symbol == p.symbol
