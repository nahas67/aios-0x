"""Kernel Bootstrap: creates and wires all kernel components as a single unit.

This is the composition root for the kernel. The ReplayRunner calls
``create_kernel()`` at boot and every subsequent operation goes through
the returned ``AIOSKernel`` instance — never around it.
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Any

from kernel.authority import AuthorityGateway
from kernel.capability import CapabilityRouter
from kernel.identity import ActorType, IdentityRegistry, Role
from kernel.promotion import PromotionController, RollbackController
from kernel.provenance import NodeType, ProvenanceGraph
from kernel.receipts import ReceiptStore
from kernel.state_machine import StateMachineDefinition, StateMachineEngine

# ------------------------------------------------------- lifecycle definitions

STRATEGY_LIFECYCLE = StateMachineDefinition(
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
        "LIVE_CANDIDATE": {"AUTHORIZED_LIVE"},
        "AUTHORIZED_LIVE": {"LIVE"},
        "LIVE": {"PAUSED", "RETIRED"},
        "PAUSED": {"LIVE", "RETIRED"},
        "REJECTED": set(),
        "RETIRED": set(),
    },
    terminal_states={"RETIRED", "REJECTED"},
)

HYPOTHESIS_LIFECYCLE = StateMachineDefinition(
    object_type="hypothesis",
    initial_state="UNTESTED",
    transitions={
        "UNTESTED": {"TESTING"},
        "TESTING": {"SUPPORTED", "PARTIALLY_SUPPORTED", "REJECTED"},
        "SUPPORTED": {"SUPERSEDED", "INVALIDATED"},
        "PARTIALLY_SUPPORTED": {"SUPERSEDED", "INVALIDATED", "SUPPORTED"},
        "REJECTED": {"SUPERSEDED"},
        "SUPERSEDED": set(),
        "INVALIDATED": set(),
    },
    terminal_states={"SUPERSEDED", "INVALIDATED"},
)

EXPERIMENT_LIFECYCLE = StateMachineDefinition(
    object_type="experiment",
    initial_state="CREATED",
    transitions={
        "CREATED": {"RUNNING", "FAILED"},
        "RUNNING": {"COMPLETED", "FAILED"},
        "COMPLETED": set(),
        "FAILED": set(),
    },
    terminal_states={"COMPLETED", "FAILED"},
)


# ------------------------------------------------------- kernel dataclass


@dataclass
class AIOSKernel:
    """The AIOS operating system. Everything registers here; nothing bypasses it."""

    identity: IdentityRegistry
    capabilities: CapabilityRouter
    receipts: ReceiptStore
    state_machine: StateMachineEngine
    authority: AuthorityGateway
    provenance: ProvenanceGraph
    promotions: PromotionController
    rollbacks: RollbackController
    _plugin_state: dict[str, str] = field(default_factory=dict)

    def register_plugin(self, plugin_id: str, plugin_type: str, version: str = "v1") -> None:
        """Plugin lifecycle: register → validate → activate."""
        key = f"plugin:{plugin_id}"
        if key in self._plugin_state:
            raise ValueError(f"plugin already registered: {plugin_id!r}")
        self._plugin_state[key] = "REGISTERED"

    def activate_plugin(self, plugin_id: str) -> None:
        key = f"plugin:{plugin_id}"
        if key not in self._plugin_state:
            raise KeyError(f"plugin not registered: {plugin_id!r}")
        if self._plugin_state[key] == "ACTIVE":
            return
        self._plugin_state[key] = "ACTIVE"

    def deactivate_plugin(self, plugin_id: str) -> None:
        key = f"plugin:{plugin_id}"
        if key not in self._plugin_state:
            raise KeyError(f"plugin not registered: {plugin_id!r}")
        self._plugin_state[key] = "DEACTIVATED"

    def is_plugin_active(self, plugin_id: str) -> bool:
        return self._plugin_state.get(f"plugin:{plugin_id}") == "ACTIVE"

    def create_tracked_object(
        self, object_type: str, object_id: str, actor_id: str, label: str = "", **data: Any
    ) -> str:
        """Create a kernel-tracked object AND add it to the provenance graph."""
        state = self.state_machine.create_object(object_type, object_id, actor_id)
        node_type = _lifecycle_to_node_type(object_type)
        self.provenance.add_node(object_id, node_type, label=label, **data)
        return state

    def transition_tracked(
        self,
        object_type: str,
        object_id: str,
        to_state: str,
        actor_id: str,
        reason: str,
        evidence_refs: list[str] | None = None,
    ) -> None:
        """State transition + provenance edge in one atomic operation."""
        from_state = self.state_machine.get_state(object_type, object_id)
        self.state_machine.transition(
            object_type,
            object_id,
            to_state,
            actor_id,
            reason,
            evidence_refs=evidence_refs,
        )
        # Add provenance edge from previous state node to new state node
        new_node_id = f"{object_id}:{to_state}"
        if new_node_id not in {n.node_id for n in self.provenance._nodes.values()}:
            self.provenance.add_node(
                new_node_id,
                _lifecycle_to_node_type(object_type),
                label=f"{object_id} -> {to_state}",
            )
            self.provenance.add_edge(f"{object_id}:{from_state}", new_node_id, "transitions_to")


def _lifecycle_to_node_type(object_type: str) -> NodeType:
    mapping = {
        "strategy": NodeType.STRATEGY_VERSION,
        "hypothesis": NodeType.HYPOTHESIS,
        "experiment": NodeType.EXPERIMENT,
        "evaluation": NodeType.EVALUATION,
        "execution": NodeType.EXECUTION,
        "dataset": NodeType.DATASET_VERSION,
        "feature": NodeType.FEATURE_VERSION,
        "model": NodeType.MODEL_VERSION,
    }
    return mapping.get(object_type, NodeType.SOURCE)


# ------------------------------------------------------- bootstrap factory


def create_kernel() -> AIOSKernel:
    """Create and wire a fully configured AIOS kernel."""
    identity = IdentityRegistry()
    capabilities = CapabilityRouter()
    receipts = ReceiptStore()
    sm = StateMachineEngine(receipts)
    authority = AuthorityGateway(identity, capabilities, receipts, sm)
    provenance = ProvenanceGraph()
    promotions = PromotionController(receipts)
    rollbacks = RollbackController()

    # Register standard lifecycles
    for lifecycle in (STRATEGY_LIFECYCLE, HYPOTHESIS_LIFECYCLE, EXPERIMENT_LIFECYCLE):
        sm.register_definition(lifecycle)

    # Register default actors
    identity.register("system", ActorType.SERVICE, "AIOS System", roles={Role.ADMIN})

    # Declare capabilities that role mappings reference
    for cap_name in (
        "AIOS.transition.strategy",
        "AIOS.transition.hypothesis",
        "AIOS.transition.experiment",
        "AIOS.research",
        "AIOS.backtest",
        "AIOS.execute",
        "AIOS.evaluate",
        "AIOS.promote.strategy",
    ):
        capabilities.declare(cap_name, ABC, f"Capability: {cap_name}")

    # Grant system role access to all capabilities (composition root only)
    for capability_name in (
        "AIOS.transition.strategy",
        "AIOS.transition.hypothesis",
        "AIOS.transition.experiment",
        "AIOS.research",
        "AIOS.backtest",
        "AIOS.execute",
        "AIOS.promote.strategy",
        "AIOS.evaluate",
    ):
        authority.grant_role_capability(Role.ADMIN, capability_name)
        authority.grant_role_capability(Role.RISK_ADMIN, capability_name)

    authority.grant_role_capability(Role.AGENT_RESEARCH, "AIOS.research")
    authority.grant_role_capability(Role.AGENT_STRATEGY, "AIOS.backtest")
    authority.grant_role_capability(Role.SERVICE_EXECUTION, "AIOS.execute")

    return AIOSKernel(
        identity=identity,
        capabilities=capabilities,
        receipts=receipts,
        state_machine=sm,
        authority=authority,
        provenance=provenance,
        promotions=promotions,
        rollbacks=rollbacks,
    )
