"""Phase C Research Plane tests: durable hypotheses + hash-addressable evidence.

Proves knowledge survives the process: a hypothesis registered in one store
instance is queryable, with its full evidence graph and terminal status, from
a completely fresh instance (restart simulation) — on SQLite locally and
PostgreSQL when AIOS_TEST_PG_DSN is set.
"""

import asyncio
import os
from pathlib import Path

import pytest

from core.research_store import (
    PostgresResearchStore,
    SqliteResearchStore,
    build_research_store,
    select_research_store_class,
)
from kernel.bootstrap import create_kernel
from research.engine import HypothesisEngine, wire_kernel_to_engine
from schemas.contracts import (
    CandidateHypothesis,
    EvidencePackage,
    HypothesisStatus,
    VerificationReport,
)
from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner

PG_DSN = os.environ.get("AIOS_TEST_PG_DSN", "")


def _candidate(symbol: str = "BTC/USD") -> CandidateHypothesis:
    return CandidateHypothesis(
        symbol=symbol,
        thesis="Momentum persists; price trends up over the horizon.",
        supporting_arguments=["trend filter positive"],
        counter_arguments=["regime may flip"],
        timeframe="1d",
        expected_risk_reward_ratio=2.0,
    )


def _report(hypothesis_id: str, verified: bool = True) -> VerificationReport:
    return VerificationReport(
        hypothesis_id=hypothesis_id,
        confidence_score=85.0 if verified else 40.0,
        verified_claims=["trend filter positive"] if verified else [],
        flagged_hallucinations=[] if verified else ["fabricated number"],
        verification_notes="unit-test report",
    )


# ------------------------------------------------------------------ evidence


def test_evidence_is_hash_addressable_and_deduped(tmp_path: Path) -> None:
    store = SqliteResearchStore(tmp_path / "r.db")
    e1 = EvidencePackage(
        source="c3_verification", claims=["a"], payload={"report_id": "rep-1"}
    )
    e2 = EvidencePackage(
        source="c3_verification", claims=["a"], payload={"report_id": "rep-1"}
    )  # identical content, different auto id
    id1 = store.save_evidence(e1)
    id2 = store.save_evidence(e2)
    assert id1 == id2, "identical payloads must dedupe to one canonical row"

    e3 = EvidencePackage(
        source="c3_verification", claims=["different"], payload={"report_id": "rep-2"}
    )
    assert store.save_evidence(e3) != id1

    counts = store.counts()
    assert counts["evidence"] == 2


# ------------------------------------------------------- lifecycle persistence


def test_hypothesis_lifecycle_survives_restart(tmp_path: Path) -> None:
    """Register -> verify -> settle in session 1; read it all back in session 2."""
    db = tmp_path / "research.db"

    # ---- session 1
    engine_a = HypothesisEngine(SqliteResearchStore(db))
    candidate = _candidate()
    engine_a.register_from_candidate(candidate)
    engine_a.apply_verification(_report(candidate.hypothesis_id))
    h_mid = engine_a.get(candidate.hypothesis_id)
    assert h_mid.status is HypothesisStatus.TESTING
    status = engine_a.apply_outcome(
        candidate.hypothesis_id,
        direction_correct=False,
        realized_pnl=-64.5,
        execution_id="exec-1",
    )
    assert status is HypothesisStatus.REJECTED

    # ---- session 2 (fresh instances = simulated process restart)
    engine_b = HypothesisEngine(SqliteResearchStore(db))
    h_after = engine_b.get(candidate.hypothesis_id)
    assert h_after.statement.startswith("Momentum persists")
    assert h_after.status is HypothesisStatus.REJECTED
    assert len(h_after.evidence_ids) >= 2

    pairs = engine_b.store.evidence_for_hypothesis(candidate.hypothesis_id)
    relationships = {rel for _, rel in pairs}
    assert {"supports", "outcome"} <= relationships
    outcome_ev = next(ev for ev, rel in pairs if rel == "outcome")
    assert any("realized_pnl=-64.50" in c for c in outcome_ev.claims)
    assert outcome_ev.content_hash(), "evidence must be hash-addressable"


def test_unverified_verification_records_contradicting_evidence(tmp_path: Path) -> None:
    engine = HypothesisEngine(SqliteResearchStore(tmp_path / "r.db"))
    candidate = _candidate("ETH/USD")
    engine.register_from_candidate(candidate)
    engine.apply_verification(_report(candidate.hypothesis_id, verified=False))

    h = engine.get(candidate.hypothesis_id)
    assert h.status is HypothesisStatus.UNTESTED  # never entered TESTING
    pairs = engine.store.evidence_for_hypothesis(candidate.hypothesis_id)
    assert any(rel == "contradicts" for _, rel in pairs)


def test_duplicate_registration_is_idempotent(tmp_path: Path) -> None:
    engine = HypothesisEngine(SqliteResearchStore(tmp_path / "r.db"))
    candidate = _candidate()
    first = engine.register_from_candidate(candidate)
    second = engine.register_from_candidate(candidate)
    assert first.hypothesis_id == second.hypothesis_id
    assert engine.store.counts()["hypotheses"] == 1


# ------------------------------------------------------------ kernel restore


def test_restore_into_fresh_kernel_state_machine(tmp_path: Path) -> None:
    db = tmp_path / "r.db"
    engine_a = HypothesisEngine(SqliteResearchStore(db))
    in_flight = []
    for sym in ("BTC/USD", "ETH/USD"):
        c = _candidate(sym)
        engine_a.register_from_candidate(c)
        engine_a.apply_verification(_report(c.hypothesis_id))  # -> TESTING
        in_flight.append((c.hypothesis_id, "TESTING"))
    # settled one stays terminal and must NOT be restored
    settled = _candidate("SOL/USD")
    engine_a.register_from_candidate(settled)
    engine_a.apply_verification(_report(settled.hypothesis_id))
    engine_a.apply_outcome(settled.hypothesis_id, True, 10.0)

    kernel = create_kernel()
    restored = wire_kernel_to_engine(kernel, engine_a)
    assert restored == 2
    for hid, expected in in_flight:
        assert kernel.state_machine.get_state("hypothesis", hid) == expected
    with pytest.raises(KeyError):
        kernel.state_machine.get_state("hypothesis", settled.hypothesis_id)


def test_knowledge_summary_counts_statuses(tmp_path: Path) -> None:
    engine = HypothesisEngine(SqliteResearchStore(tmp_path / "r.db"))
    for i, correct in enumerate([True, False, False]):
        c = _candidate(f"S{i}")
        engine.register_from_candidate(c)
        engine.apply_verification(_report(c.hypothesis_id))
        engine.apply_outcome(c.hypothesis_id, correct, 10.0 if correct else -5.0)
    summary = engine.knowledge_summary()
    assert summary["statuses"]["SUPPORTED"] == 1
    assert summary["statuses"]["REJECTED"] == 2


# ------------------------------------------------------------- runner wiring


def test_runner_persists_research_knowledge(tmp_path: Path) -> None:
    write_dataset(tmp_path / "golden", symbols=["BTC/USD", "ETH/USD"], total_bars=120)

    def _run(store_name: str) -> tuple[ReplayRunner, object]:
        runner = ReplayRunner(
            csv_path_by_symbol={
                "BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv",
                "ETH/USD": tmp_path / "golden" / "ETH_USD_1d.csv",
            },
            store_path=tmp_path / store_name,
            initial_balance=100000.0,
            slippage_pct=0.05,
        )
        summary = asyncio.run(runner.run())
        return runner, summary

    runner, summary = _run("run.db")  # research rows land alongside in .research.db
    assert summary.trades_closed >= 1
    stats = runner.kernel_bridge.stats()
    research = stats["research"]
    assert research["hypotheses"] > 0
    assert research["evidence"] > 0
    statuses = research["statuses"]
    assert statuses.get("REJECTED", 0) + statuses.get("SUPPORTED", 0) >= 1

    # Cross-session: brand-new engine over the same files reads everything back
    engine_b = HypothesisEngine(build_research_store(tmp_path / "run.db"))
    rejected = engine_b.store.list_hypotheses(status=HypothesisStatus.REJECTED)
    supported = engine_b.store.list_hypotheses(status=HypothesisStatus.SUPPORTED)
    assert rejected or supported
    some = (rejected + supported)[0]
    pairs = engine_b.store.evidence_for_hypothesis(some.hypothesis_id)
    assert any(rel == "supports" for _, rel in pairs)


# ------------------------------------------------------------------ factory


def test_research_store_selection_matches_memory_store_rules() -> None:
    assert select_research_store_class(None) is SqliteResearchStore
    assert select_research_store_class("postgresql://u:p@h/db") is PostgresResearchStore
    store = build_research_store(Path("x.db"), database_url=None)
    assert isinstance(store, SqliteResearchStore)
    store.close()


# --------------------------------------------------------- PostgreSQL parity


@pytest.mark.skipif(
    not PG_DSN, reason="set AIOS_TEST_PG_DSN to run live PostgreSQL parity"
)
class TestPostgresParity:
    def test_full_lifecycle_and_restart(self) -> None:
        import uuid

        marker = uuid.uuid4().hex[:8]
        store = PostgresResearchStore(PG_DSN)
        engine = HypothesisEngine(store)

        c = CandidateHypothesis(
            symbol=f"PARITY_{marker}",
            thesis=f"parity check {marker}",
            supporting_arguments=["s1"],
            counter_arguments=["c1"],
            timeframe="1d",
            expected_risk_reward_ratio=2.0,
        )
        engine.register_from_candidate(c)
        engine.apply_verification(_report(c.hypothesis_id))
        engine.apply_outcome(c.hypothesis_id, True, 42.0, execution_id=f"exec-{marker}")

        fresh = HypothesisEngine(PostgresResearchStore(PG_DSN))
        h = fresh.get(c.hypothesis_id)
        assert h.status is HypothesisStatus.SUPPORTED
        pairs = fresh.store.evidence_for_hypothesis(c.hypothesis_id)
        assert {rel for _, rel in pairs} == {"supports", "outcome"}
        assert all(isinstance(ev.content_hash(), str) for ev, _ in pairs)
