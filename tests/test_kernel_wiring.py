"""Phase A completion tests: the ReplayRunner runs ON the AIOS kernel.

Proves the kernel is no longer shelfware:
- dataset/feature registered as versioned hashed objects
- hypotheses and strategies tracked through formal lifecycles
- every execution authorized by the authority gateway with receipts
- postmortem outcomes update hypothesis status (negative knowledge preserved)
- experiment reproducibility hash stable across identical runs
- provenance graph resolves dataset -> ... -> postmortem chains
"""

import asyncio
from pathlib import Path

import pytest

from schemas.contracts import (
    CandidateHypothesis,
    PortfolioAllocationPlan,
    PortfolioStatus,
    StrategySpecification,
    VerificationReport,
)
from simulation.generate_golden_data import write_dataset
from simulation.kernel_bridge import KernelBridge
from simulation.replay_runner import ReplayRunner


@pytest.fixture()
def small_dataset(tmp_path: Path) -> dict[str, Path]:
    write_dataset(tmp_path / "golden", symbols=["BTC/USD", "ETH/USD"], total_bars=120)
    by_symbol = {
        "BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv",
        "ETH/USD": tmp_path / "golden" / "ETH_USD_1d.csv",
    }
    return {s: p for s, p in by_symbol.items() if p.exists()}


def _run(dataset: dict[str, Path], store_path: Path) -> tuple[ReplayRunner, object]:
    runner = ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=store_path,
        initial_balance=100000.0,
        slippage_pct=0.05,
    )
    summary = asyncio.run(runner.run())
    return runner, summary


def _hypothesis(symbol: str = "BTC/USD") -> CandidateHypothesis:
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
        verified_claims=["claim-1"] if verified else [],
        flagged_hallucinations=[] if verified else ["fabricated number"],
        verification_notes="unit-test report",
    )


def _plan(strategy: StrategySpecification, approved: bool = True) -> PortfolioAllocationPlan:
    return PortfolioAllocationPlan(
        strategy=strategy,
        approved=approved,
        final_position_size_pct=5.0,
        portfolio_status=PortfolioStatus.HEALTHY if approved else PortfolioStatus.CAUTION,
        drawdown_pct=0.0,
    )


# --------------------------------------------------------------------- boot


def test_kernel_boot_registers_community_actors() -> None:
    bridge = KernelBridge()
    actors = {a.actor_id for a in bridge.kernel.identity.list_all()}
    for expected in ("c1-data-fabric", "c2-research", "c3-verification", "c4-strategy",
                     "c5-execution", "c9-governor", "system"):
        assert expected in actors
    stats = bridge.stats()
    assert stats["capabilities_declared"] >= 8


def test_dataset_and_feature_registered_with_content_hash(small_dataset) -> None:
    async def _flow() -> None:
        bridge = KernelBridge()
        ref = await bridge.register_replay_dataset(small_dataset)
        assert ref["dataset_id"] == "replay"
        dv = bridge.kernel.datasets.get("replay", ref["version"])
        assert dv.content_hash
        expected_rows = sum(
            sum(1 for _ in open(path, encoding="utf-8")) - 1
            for path in small_dataset.values()
        )
        assert dv.row_count == expected_rows
        # dataset lifecycle reached ACTIVE through the state machine engine
        # (DatasetRegistry keys each version as its own machine type)
        key = f"replay:{ref['version']}"
        assert bridge.kernel.state_machine.get_state(key, key) == "ACTIVE"
        fv = bridge.kernel.features.get("ohlcv_passthrough", "v1")
        assert fv.validation_status == "VALIDATED"
        assert fv.dataset_ref["content_hash"] == dv.content_hash

    asyncio.run(_flow())


# ------------------------------------------------------------- full-loop wiring


def test_full_run_lifecycle_through_kernel(small_dataset, tmp_path) -> None:
    runner, summary = _run(small_dataset, tmp_path / "k.db")
    bridge = runner.kernel_bridge
    assert summary.trades_closed >= 1

    # Experiment pinned + completed with a reproducibility hash
    assert summary.experiment_reproducibility_hash != ""
    exp = bridge.kernel.experiments.get(str(bridge.experiment_id))
    assert exp.reproducibility_hash == summary.experiment_reproducibility_hash
    state = bridge.kernel.state_machine.get_state("experiment", bridge.experiment_id)
    assert state == "COMPLETED"
    assert exp.dataset_version == bridge.dataset_version

    # Hypotheses became first-class kernel objects (not just transient payloads)
    stats = bridge.stats()
    assert stats["tracked_hypotheses"] > 0
    assert stats["tracked_strategies"] > 0

    # At least one strategy walked IDEA -> ... -> EVALUATED via the gateway
    evaluated = [
        sid
        for sid in bridge.tracked_strategy_ids()
        if bridge.kernel.state_machine.get_state("strategy", sid) == "EVALUATED"
    ]
    assert evaluated, "no strategy reached EVALUATED"

    # Every kernel receipt — gateway decisions AND state-machine co-receipts —
    # is mirrored 1:1 into the hash-chained audit log by the receipt sink.
    stats = bridge.stats()
    assert stats["receipts"] >= stats["authorizations"] > 0
    mirrored = runner.store.iter_event_payloads("DECISION_RECEIPT")
    assert len(mirrored) == stats["receipts"]
    assert any(r["decision"] == "ALLOW" for r in mirrored)


def test_execution_receipts_authorize_every_fill(small_dataset, tmp_path) -> None:
    runner, summary = _run(small_dataset, tmp_path / "k.db")
    bridge = runner.kernel_bridge
    fills = list(runner._receipts.values())
    assert len(fills) == summary.trades_closed
    for receipt in fills:
        state = bridge.kernel.state_machine.get_state("strategy", receipt.strategy_id)
        assert state == "EVALUATED"
        receipts_for = bridge.kernel.receipts.by_object("strategy", receipt.strategy_id)
        actions = [r.requested_action for r in receipts_for]
        assert "transition:BACKTESTED" in actions
        assert "transition:EVALUATED" in actions
        assert all(r.decision == "ALLOW" for r in receipts_for)


# ------------------------------------------------------- hypothesis knowledge


def test_hypothesis_lifecycle_supported_and_rejected_paths() -> None:
    """SUPPORTED on correct direction; REJECTED preserved as negative knowledge."""

    async def _flow() -> None:
        bridge = KernelBridge()

        h_good = _hypothesis()
        await bridge.on_hypothesis(h_good)
        assert bridge.kernel.state_machine.get_state("hypothesis", h_good.hypothesis_id) == "UNTESTED"
        await bridge.on_verification(_report(h_good.hypothesis_id))
        assert bridge.kernel.state_machine.get_state("hypothesis", h_good.hypothesis_id) == "TESTING"
        await bridge.on_hypothesis_outcome(h_good.hypothesis_id, direction_correct=True, pnl=150.0)
        assert bridge.kernel.state_machine.get_state("hypothesis", h_good.hypothesis_id) == "SUPPORTED"

        h_bad = _hypothesis("ETH/USD")
        await bridge.on_hypothesis(h_bad)
        await bridge.on_verification(_report(h_bad.hypothesis_id))
        await bridge.on_hypothesis_outcome(h_bad.hypothesis_id, direction_correct=False, pnl=-80.0)
        assert bridge.kernel.state_machine.get_state("hypothesis", h_bad.hypothesis_id) == "REJECTED"

        # Unverified hypotheses never enter TESTING
        h_unverified = _hypothesis("SOL/USD")
        await bridge.on_hypothesis(h_unverified)
        await bridge.on_verification(_report(h_unverified.hypothesis_id, verified=False))
        assert bridge.kernel.state_machine.get_state("hypothesis", h_unverified.hypothesis_id) == "UNTESTED"

    asyncio.run(_flow())


def test_postmortem_settlement_updates_hypothesis(small_dataset, tmp_path) -> None:
    """Whatever the market said, every settled trade's hypothesis got a verdict."""
    runner, _summary = _run(small_dataset, tmp_path / "k.db")
    sm = runner.kernel_bridge.kernel.state_machine
    verdicts = {
        sm.get_state("hypothesis", hid)
        for hid in runner.kernel_bridge.tracked_hypothesis_ids()
    }
    assert verdicts & {"SUPPORTED", "REJECTED"}, "no hypothesis reached a postmortem verdict"


# ---------------------------------------------------------------- authority


def test_authority_denies_ungranted_capability_fail_closed() -> None:
    """A strategy agent requesting execution gets DENY + a persisted receipt."""

    async def _flow() -> None:
        bridge = KernelBridge()
        result = await bridge._authorize(
            "c4-strategy", "AIOS.execute", "strategy", "unknown-strategy",
            "execute_order", "bypass attempt",
        )
        from kernel.receipts import Decision

        assert result.decision is Decision.DENY
        assert "do not grant capability" in result.detail
        saved = bridge.kernel.receipts.by_object("strategy", "unknown-strategy")
        assert saved[-1].decision is Decision.DENY

    asyncio.run(_flow())


def test_governor_denial_recorded_as_deny_receipt() -> None:
    from kernel.receipts import Decision

    async def _flow() -> None:
        bridge = KernelBridge()
        await bridge.on_plan_denied("strat-123", "exposure cap exceeded")
        receipts = bridge.kernel.receipts.by_object("strategy", "strat-123")
        assert receipts and receipts[-1].decision is Decision.DENY
        assert receipts[-1].actor_id == "c9-governor"

    asyncio.run(_flow())


# --------------------------------------------------------------- provenance


def test_provenance_chain_dataset_to_postmortem(small_dataset, tmp_path) -> None:
    from kernel.provenance import NodeType

    runner, _summary = _run(small_dataset, tmp_path / "k.db")
    provenance = runner.kernel_bridge.kernel.provenance

    nodes = list(provenance._nodes.values())  # noqa: SLF001 - test introspection
    executions = [n for n in nodes if n.node_type is NodeType.EXECUTION]
    assert executions, "no execution nodes recorded"
    upstream_types = {
        n.node_type for n in provenance.lineage_backward(executions[0].node_id)
    }
    assert NodeType.STRATEGY_VERSION in upstream_types
    assert NodeType.HYPOTHESIS in upstream_types
    assert NodeType.DATASET_VERSION in upstream_types

    postmortems = [n for n in nodes if n.node_type is NodeType.POST_MORTEM]
    assert postmortems, "no postmortem nodes recorded"
    chain = provenance.full_chain(postmortems[0].node_id)
    assert chain["node"]["node_type"] == "POST_MORTEM"
    assert any(n["node_type"] == "EXECUTION" for n in chain["upstream"])


# ---------------------------------------------------------- reproducibility


def test_identical_conditions_identical_experiment_hash(tmp_path) -> None:
    write_dataset(tmp_path / "golden_a", symbols=["SPY"], total_bars=90)
    write_dataset(tmp_path / "golden_b", symbols=["SPY"], total_bars=90)
    dataset_a = {"SPY": tmp_path / "golden_a" / "SPY_1d.csv"}
    dataset_b = {"SPY": tmp_path / "golden_b" / "SPY_1d.csv"}

    _, summary_a = _run(dataset_a, tmp_path / "a.db")
    _, summary_b = _run(dataset_b, tmp_path / "b.db")

    assert summary_a.experiment_reproducibility_hash != ""
    assert (
        summary_a.experiment_reproducibility_hash
        == summary_b.experiment_reproducibility_hash
    ), "identical conditions must produce identical reproducibility hashes"


# ------------------------------------------------------------------- plans


def test_strategy_tracking_is_idempotent() -> None:
    """Duplicate events (bus redelivery) must not create duplicate objects."""

    async def _flow() -> None:
        bridge = KernelBridge()
        strategy = StrategySpecification(
            hypothesis_id="hyp-x",
            symbol="BTC/USD",
            action="BUY",
            entry_price=100.0,
            stop_loss_price=95.0,
            take_profit_price=115.0,
            position_size_pct=5.0,
            family="momentum",
        )
        await bridge.on_strategy(strategy)
        await bridge.on_strategy(strategy)  # duplicate delivery
        await bridge.on_plan_approved(_plan(strategy))
        state = bridge.kernel.state_machine.get_state("strategy", strategy.strategy_id)
        assert state == "VALIDATED"
        history = bridge.kernel.state_machine.history("strategy", strategy.strategy_id)
        assert [t.to_state for t in history] == ["HYPOTHESIS", "DRAFT", "VALIDATED"]

    asyncio.run(_flow())
