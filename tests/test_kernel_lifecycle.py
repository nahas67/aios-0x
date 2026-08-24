"""Kernel lifecycle integration test: full chain from idea to postmortem."""

import asyncio

import pytest

from kernel.bootstrap import AIOSKernel, create_kernel
from kernel.identity import ActorType, Role
from kernel.provenance import NodeType


@pytest.fixture()
def kernel() -> AIOSKernel:
    return create_kernel()


def _register_actors(k: AIOSKernel) -> None:
    k.identity.register(
        "researcher-1", ActorType.HUMAN, "Research Lead", roles={Role.RESEARCHER, Role.OPERATOR}
    )
    k.identity.register(
        "risk-admin", ActorType.HUMAN, "Risk Officer", roles={Role.RISK_ADMIN, Role.OPERATOR}
    )
    k.identity.register(
        "agent-momentum", ActorType.AGENT, "Momentum Agent", roles={Role.AGENT_RESEARCH}
    )
    k.identity.register("viewer", ActorType.HUMAN, "Read Only", roles={Role.VIEWER})
    # Grant researcher the transition capability for this test scenario
    k.authority.grant_role_capability(Role.RESEARCHER, "AIOS.transition.strategy")


def test_full_strategy_lifecycle_through_kernel(kernel: AIOSKernel) -> None:
    """The definitive kernel test: create → research → backtest → evaluate → promote."""
    _register_actors(kernel)

    # --- 1. Capabilities are pre-declared by create_kernel()
    # (AIOS.transition.strategy, AIOS.research, AIOS.backtest, AIOS.evaluate, etc.)

    # --- 2. Grant role-capability mappings
    kernel.authority.grant_role_capability(Role.RESEARCHER, "AIOS.research")
    kernel.authority.grant_role_capability(Role.RESEARCHER, "AIOS.transition.strategy")
    kernel.authority.grant_role_capability(Role.RISK_ADMIN, "AIOS.transition.strategy")
    kernel.authority.grant_role_capability(Role.RISK_ADMIN, "AIOS.evaluate")

    # --- 3. Create a strategy (kernel-tracked + provenance node)
    state = kernel.create_tracked_object(
        "strategy",
        "strat-btc-001",
        "researcher-1",
        label="BTC momentum strategy",
        symbol="BTC/USD",
        family="momentum",
    )
    assert state == "IDEA"
    assert kernel.provenance.node_count() >= 1

    # --- 4. Researcher transitions through lifecycle via authority gateway
    from kernel.authority import AuthorityRequest

    transitions = [
        ("HYPOTHESIS", "hypothesis formed from research"),
        ("DRAFT", "strategy code implemented"),
        ("VALIDATED", "unit + integration tests pass"),
        ("BACKTESTED", "backtest over 730 bars complete"),
        ("EVALUATED", "evaluation passed all gates"),
        ("APPROVED_FOR_PAPER", "risk review approved"),
        ("PAPER", "deployed to paper trading"),
    ]
    for to_state, reason in transitions:
        result = asyncio.run(
            kernel.authority.authorize(
                AuthorityRequest(
                    actor_id="researcher-1",
                    capability="AIOS.transition.strategy",
                    object_type="strategy",
                    object_id="strat-btc-001",
                    action=f"transition:{to_state}",
                    reason=reason,
                    evidence_refs=[f"evidence-{to_state.lower()}"],
                )
            )
        )
        assert result.decision.value == "ALLOW", f"transition to {to_state} denied: {result.detail}"

    assert kernel.state_machine.get_state("strategy", "strat-btc-001") == "PAPER"

    # --- 5. Viewer cannot transition (RBAC enforced)
    kernel.state_machine.create_object("strategy", "strat-eth-001", "researcher-1")
    result = asyncio.run(
        kernel.authority.authorize(
            AuthorityRequest(
                actor_id="viewer",
                capability="AIOS.transition.strategy",
                object_type="strategy",
                object_id="strat-eth-001",
                action="transition:HYPOTHESIS",
                reason="viewer tries",
            )
        )
    )
    assert result.decision.value == "DENY"

    # --- 6. Provenance graph has the strategy node
    node = kernel.provenance.get_node("strat-btc-001")
    assert node.node_type == NodeType.STRATEGY_VERSION
    assert kernel.provenance.node_count() >= 1

    # --- 7. Promotion requires human + EVALUATED
    kernel.promotions.propose("strategy", "strat-btc-001", "v1.0", evaluation_ref="eval-001")
    with pytest.raises(PermissionError, match="EVALUATED"):
        kernel.promotions.promote("strategy", "strat-btc-001", "v1.0", "researcher-1")

    kernel.promotions.mark_evaluated("strategy", "strat-btc-001", "v1.0")
    promoted = kernel.promotions.promote(
        "strategy",
        "strat-btc-001",
        "v1.0",
        "risk-admin",
        rollback_target_version="v0.9",
    )
    assert promoted.state.value == "PROMOTED"

    # --- 8. Receipts exist for every decision
    assert kernel.receipts.count() >= 10  # at least 7 transitions + 1 deny + 1 promote

    # --- 9. Plugin lifecycle
    kernel.register_plugin("ccxt-adapter", "execution")
    kernel.activate_plugin("ccxt-adapter")
    assert kernel.is_plugin_active("ccxt-adapter")
    kernel.deactivate_plugin("ccxt-adapter")
    assert not kernel.is_plugin_active("ccxt-adapter")
