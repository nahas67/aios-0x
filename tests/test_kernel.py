"""AIOS Kernel tests: identity, capability, state machine, authority, provenance, promotion."""

import asyncio
from abc import ABC, abstractmethod

import pytest

from kernel.authority import AuthorityGateway, AuthorityRequest
from kernel.capability import CapabilityRouter
from kernel.identity import ActorType, IdentityRegistry, Role
from kernel.promotion import PromotionController, PromotionState, RollbackController
from kernel.provenance import NodeType, ProvenanceGraph
from kernel.receipts import Decision, ReceiptStore
from kernel.state_machine import StateMachineDefinition, StateMachineEngine, TransitionError

# ------------------------------------------------------------------ identity


def test_identity_registration_and_resolution() -> None:
    reg = IdentityRegistry()
    actor = reg.register("human-1", ActorType.HUMAN, "Alice", roles={Role.OPERATOR, Role.VIEWER})
    assert actor.actor_id == "human-1"
    assert actor.has_role(Role.OPERATOR)
    assert not actor.has_role(Role.ADMIN)

    resolved = reg.resolve("human-1")
    assert resolved is actor

    with pytest.raises(KeyError):
        reg.resolve("ghost")
    with pytest.raises(ValueError):
        reg.register("human-1", ActorType.HUMAN)


def test_identity_deactivation() -> None:
    reg = IdentityRegistry()
    reg.register("svc-1", ActorType.SERVICE, roles={Role.SERVICE_DATA})
    reg.deactivate("svc-1")
    with pytest.raises(PermissionError, match="deactivated"):
        reg.resolve("svc-1")


# ------------------------------------------------------- capability router


class BacktestInterface(ABC):
    @abstractmethod
    def run(self) -> dict: ...


class MockBacktest(BacktestInterface):
    def run(self) -> dict:
        return {"result": "ok"}


def test_capability_router_declare_register_resolve() -> None:
    router = CapabilityRouter()
    router.declare("AIOS.backtest", BacktestInterface, "Run a backtest")
    router.register("AIOS.backtest", "vectorbt_v1", MockBacktest, is_default=True)

    impl = router.resolve("AIOS.backtest")
    assert impl is MockBacktest
    assert impl().run() == {"result": "ok"}

    # Explicit implementation selection
    assert router.resolve("AIOS.backtest", "vectorbt_v1") is MockBacktest

    with pytest.raises(ValueError, match="not declared"):
        router.resolve("AIOS.nonexistent")
    with pytest.raises(ValueError, match="not found"):
        router.resolve("AIOS.backtest", "nonexistent_impl")


def test_capability_router_rejects_bad_interface() -> None:
    class NotABC:
        pass

    router = CapabilityRouter()
    with pytest.raises(TypeError, match="ABC"):
        router.declare("AIOS.bad", NotABC)


# --------------------------------------------------------- state machine


def test_state_machine_strategy_lifecycle() -> None:
    store = ReceiptStore()
    engine = StateMachineEngine(store)
    engine.register_definition(
        StateMachineDefinition(
            object_type="strategy",
            initial_state="IDEA",
            transitions={
                "IDEA": {"HYPOTHESIS", "REJECTED"},
                "HYPOTHESIS": {"DRAFT", "REJECTED"},
                "DRAFT": {"VALIDATED", "REJECTED"},
                "VALIDATED": {"BACKTESTED", "REJECTED"},
                "BACKTESTED": {"EVALUATED"},
                "EVALUATED": {"APPROVED_FOR_PAPER", "REJECTED"},
                "APPROVED_FOR_PAPER": {"PAPER"},
                "PAPER": {"LIVE_CANDIDATE", "RETIRED"},
                "LIVE_CANDIDATE": {"LIVE"},
                "LIVE": {"PAUSED", "RETIRED"},
                "PAUSED": {"LIVE", "RETIRED"},
                "REJECTED": set(),
                "RETIRED": set(),
            },
            terminal_states={"RETIRED", "REJECTED"},
        )
    )

    engine.create_object("strategy", "strat-001", "human-1")
    assert engine.get_state("strategy", "strat-001") == "IDEA"

    # Valid chain
    engine.transition("strategy", "strat-001", "HYPOTHESIS", "human-1", "research done")
    engine.transition("strategy", "strat-001", "DRAFT", "human-1", "implemented")
    engine.transition("strategy", "strat-001", "VALIDATED", "human-1", "tests pass")
    assert engine.get_state("strategy", "strat-001") == "VALIDATED"

    # Invalid transition: IDEA -> LIVE is forbidden
    engine.create_object("strategy", "strat-002", "human-1")
    with pytest.raises(TransitionError, match="allowed"):
        engine.transition("strategy", "strat-002", "LIVE", "human-1", "shortcut attempt")

    # Terminal state cannot transition
    engine.transition("strategy", "strat-002", "REJECTED", "human-1", "bad idea")
    with pytest.raises(TransitionError, match="terminal"):
        engine.transition("strategy", "strat-002", "IDEA", "human-1", "resurrect")

    # History is tracked
    history = engine.history("strategy", "strat-001")
    assert len(history) == 3
    assert history[0].from_state == "IDEA"
    assert history[-1].to_state == "VALIDATED"

    # Receipts were generated
    assert store.count() >= 3


# --------------------------------------------------------------- authority


@pytest.fixture()
def authority_setup():
    identity = IdentityRegistry()
    capabilities = CapabilityRouter()
    receipts = ReceiptStore()
    sm = StateMachineEngine(receipts)
    gateway = AuthorityGateway(identity, capabilities, receipts, sm)

    identity.register("admin-1", ActorType.HUMAN, roles={Role.ADMIN})
    identity.register("viewer-1", ActorType.HUMAN, roles={Role.VIEWER})

    class StrategyTransitionCap(ABC):
        pass

    capabilities.declare("AIOS.transition.strategy", StrategyTransitionCap, "Strategy transitions")
    gateway.grant_role_capability(Role.ADMIN, "AIOS.transition.strategy")
    gateway.grant_role_capability(Role.RISK_ADMIN, "AIOS.transition.strategy")

    sm.register_definition(
        StateMachineDefinition(
            object_type="strategy",
            initial_state="IDEA",
            transitions={
                "IDEA": {"HYPOTHESIS", "REJECTED"},
                "HYPOTHESIS": {"DRAFT", "REJECTED"},
                "REJECTED": set(),
            },
            terminal_states={"REJECTED"},
        )
    )
    sm.create_object("strategy", "s-1", "admin-1")
    sm.create_object("strategy", "s-2", "admin-1")

    return gateway, identity, receipts, sm


def test_authority_gateway_allow_and_deny(authority_setup) -> None:
    gateway, identity, receipts, sm = authority_setup

    async def _run():
        # ADMIN can transition
        result = await gateway.authorize(
            AuthorityRequest(
                actor_id="admin-1",
                capability="AIOS.transition.strategy",
                object_type="strategy",
                object_id="s-1",
                action="transition:HYPOTHESIS",
                reason="research complete",
            )
        )
        assert result.decision == Decision.ALLOW
        assert sm.get_state("strategy", "s-1") == "HYPOTHESIS"

        # VIEWER cannot transition (role doesn't grant capability)
        result2 = await gateway.authorize(
            AuthorityRequest(
                actor_id="viewer-1",
                capability="AIOS.transition.strategy",
                object_type="strategy",
                object_id="s-2",
                action="transition:HYPOTHESIS",
                reason="viewer tries",
            )
        )
        assert result2.decision == Decision.DENY
        assert sm.get_state("strategy", "s-2") == "IDEA"

        # Unregistered actor is denied
        result3 = await gateway.authorize(
            AuthorityRequest(
                actor_id="ghost",
                capability="AIOS.transition.strategy",
                object_type="strategy",
                object_id="s-1",
                action="transition:DRAFT",
                reason="ghost tries",
            )
        )
        assert result3.decision == Decision.DENY

    asyncio.run(_run())


def test_authority_gateway_receipts_generated(authority_setup) -> None:
    gateway, identity, receipts, sm = authority_setup

    async def _run():
        await gateway.authorize(
            AuthorityRequest(
                actor_id="admin-1",
                capability="AIOS.transition.strategy",
                object_type="strategy",
                object_id="s-1",
                action="transition:HYPOTHESIS",
                reason="test receipt generation",
            )
        )

    asyncio.run(_run())
    assert receipts.count() >= 1
    recent = receipts.recent(1)[0]
    assert recent.decision in (Decision.ALLOW, Decision.DENY)
    assert recent.actor_id == "admin-1"
    assert len(recent.input_hash) == 64  # sha256 hex


# --------------------------------------------------------------- provenance


def test_provenance_graph_lineage() -> None:
    graph = ProvenanceGraph()
    graph.add_node("src-1", NodeType.SOURCE, "Finnhub news feed")
    graph.add_node("evid-1", NodeType.EVIDENCE, "BTC breakout evidence")
    graph.add_node("hyp-1", NodeType.HYPOTHESIS, "BTC will break resistance")
    graph.add_node("exp-1", NodeType.EXPERIMENT, "Backtest run #1")
    graph.add_node("exec-1", NodeType.EXECUTION, "BTC/USD BUY")

    graph.add_edge("src-1", "evid-1", "produces")
    graph.add_edge("evid-1", "hyp-1", "supports")
    graph.add_edge("hyp-1", "exp-1", "tested_by")
    graph.add_edge("exp-1", "exec-1", "produces")

    assert graph.node_count() == 5
    assert graph.edge_count() == 4

    upstream = graph.lineage_backward("exec-1")
    assert len(upstream) == 4  # exp, hyp, evid, src

    downstream = graph.lineage_backward("src-1")  # src has no parents
    assert len(downstream) == 0

    forward = graph.lineage_forward("src-1")
    assert len(forward) == 4

    full = graph.full_chain("exec-1")
    assert full["node"]["node_id"] == "exec-1"
    assert len(full["upstream"]) == 4


# ------------------------------------------------------- promotion/rollback


def test_promotion_requires_evaluated_state() -> None:
    store = ReceiptStore()
    controller = PromotionController(store)
    record = controller.propose("strategy", "strat-1", "v1.0", evaluation_ref="eval-001")
    assert record.state == PromotionState.CANDIDATE

    with pytest.raises(PermissionError, match="EVALUATED"):
        controller.promote("strategy", "strat-1", "v1.0", "human-1")

    controller.mark_evaluated("strategy", "strat-1", "v1.0")
    promoted = controller.promote(
        "strategy", "strat-1", "v1.0", "human-1", rollback_target_version="v0.9"
    )
    assert promoted.state == PromotionState.PROMOTED
    assert promoted.rollback_target == "v0.9"


def test_rollback_controller() -> None:
    rb = RollbackController()
    rb.register_target("strategy", "strat-1", "v2.0", "v1.0")
    target = rb.execute_rollback("strategy", "strat-1", "human-1")
    assert target.rollback_version == "v1.0"
    assert target.rolled_back_by == "human-1"

    with pytest.raises(KeyError):
        rb.get_rollback("strategy", "nonexistent")
