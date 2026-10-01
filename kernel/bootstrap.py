"""Kernel Bootstrap: creates and wires all kernel components as a single unit.

This is the composition root for the kernel. The ReplayRunner calls
``create_kernel()`` at boot and every subsequent operation goes through
the returned ``AIOSKernel`` instance — never around it.
"""

import logging
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from kernel.authority import AuthorityGateway
from kernel.capability import CapabilityRouter
from kernel.competence import competence_resolver
from kernel.identity import ActorType, IdentityRegistry, Role
from kernel.playbook import CertificationOracle, PlaybookRouter
from kernel.promotion import PromotionController, RollbackController
from kernel.provenance import NodeType, ProvenanceGraph
from kernel.receipts import ReceiptStore
from kernel.registries import (
    DatasetRegistry,
    ExperimentRegistry,
    FeatureRegistry,
    ModelRegistry,
)
from kernel.state_machine import StateMachineDefinition, StateMachineEngine
from kernel.strategy_registry import CertificationVerdict, StrategyArtifact, StrategyRegistry

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# Certification, connected
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RegistryCertificationOracle:
    """Answers the playbook router's question from the strategy registry.

    Exists as a separate type rather than adding a method to
    ``StrategyRegistry`` because the router's question is narrower than the
    registry's responsibility: the router needs "may this be traded right now",
    and giving the router a reference to the whole registry would let it reach
    ``approve``, ``reject``, or ``record_verdict`` — the certification authority
    would then be reachable from the fast tier's own collaborator. The narrower
    surface is the control.

    Delegates to :meth:`StrategyArtifact.is_playable`, which requires both an
    ``APPROVED`` status and a certified verdict. Two conditions rather than one
    because each is individually reachable by a bug: a verdict with no approval
    means nobody signed off, and an approval with no verdict means nobody
    measured.
    """

    registry: StrategyRegistry

    def verdict_for(self, strategy_id: str, strategy_version: str) -> CertificationVerdict | None:
        try:
            artifact = self.registry.get(strategy_id, strategy_version)
        except KeyError:
            return None
        return artifact.verdict

    def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
        try:
            artifact = self.registry.get(strategy_id, strategy_version)
        except KeyError:
            # An unknown strategy is not a certified one. Returning False rather
            # than raising keeps a typo in a playbook binding from taking the
            # fast tier down, while still refusing to trade it.
            return False
        return artifact.is_playable()


def build_playbook_router(registry: StrategyRegistry) -> PlaybookRouter:
    """A router whose certification AND competence both come from the real registry.

    The alternative -- letting a caller pass any ``CertificationOracle`` -- would
    allow a permissive stub into production, and a stub that always says yes is
    indistinguishable from a working one until it matters. This constructor takes
    the registry specifically so the production path has no seam.

    Competence is derived rather than accepted as an argument, for the same reason.
    A caller-supplied declaration would let a permissive one into production, and a
    permissive competence declaration is indistinguishable from a correct one until a
    strategy trades somewhere it should not.

    The resolver is LAZY. Reading the registry here and passing a finished
    `StrategyCompetence` would describe the registry as it is at this instant --
    which, at boot, is empty -- and every strategy would then be permanently
    incompetent. Competence is therefore read when a playbook is offered, by which
    point the strategy has been certified and the verdict carrying its per-regime
    measurements exists. See `kernel.competence.competence_resolver`.
    """
    return PlaybookRouter(
        RegistryCertificationOracle(registry),
        competence=competence_resolver(registry),
    )


def publish_playbook(
    router: PlaybookRouter,
    artifact: StrategyArtifact,
    *,
    playbook_id: str,
    version: str,
    title: str,
    regime: Any,
    bounds: Any,
    book_size_usd: float,
    evidence: tuple[str, ...] = (),
) -> Any:
    """Derive and register a playbook from a certified strategy artifact.

    Requires the artifact itself rather than identifiers, so the verdict — and
    the measurements behind it — are read off the artifact rather than
    re-looked-up or re-supplied by a caller that might hold different ones.
    The action is derived from the retained evidence, not accepted: there is
    no parameter for it, so no caller can publish a hand-sized position
    through this path.

    An artifact with no retained evidence is refused even when its verdict is
    certified. The verdict says the measurements passed; without the
    measurements themselves there is nothing to derive a size from, and
    accepting a size from elsewhere would be the human-supplied position this
    path exists to eliminate.
    """
    from kernel.playbook import build_measured_playbook

    if artifact.verdict is None:
        raise ValueError(
            f"{artifact.ref} carries no CertificationVerdict, so there is nothing to "
            "bind a playbook to. Certify the strategy first."
        )
    if artifact.evidence is None:
        raise ValueError(
            f"{artifact.ref} carries a verdict but no retained measurements. A "
            "position cannot be derived from a conclusion without its premises; "
            "record the verdict with its evidence."
        )
    playbook = build_measured_playbook(
        playbook_id=playbook_id,
        version=version,
        title=title,
        regime=regime,
        bounds=bounds,
        strategy_id=artifact.strategy_id,
        strategy_version=artifact.version,
        verdict=artifact.verdict,
        evidence=artifact.evidence,
        book_size_usd=book_size_usd,
        sources=evidence,
    )
    return router.register(playbook)

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
    datasets: DatasetRegistry | None = None
    features: FeatureRegistry | None = None
    models: ModelRegistry | None = None
    experiments: ExperimentRegistry | None = None
    #: The certification firewall. Present on the kernel rather than constructed
    #: ad hoc so that a playbook can only be published against a verdict this
    #: kernel holds — a router wired to a throwaway registry would certify
    #: against nothing.
    strategies: StrategyRegistry | None = None
    #: The fast tier's policy selector. Reads certification live from
    #: ``strategies``; see :class:`RegistryCertificationOracle`.
    playbook_router: PlaybookRouter | None = None
    certification: CertificationOracle | None = None
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


def create_kernel(
    receipt_sink: Callable[[str, str | None, dict[str, Any]], None] | None = None,
) -> AIOSKernel:
    """Create and wire a fully configured AIOS kernel.

    ``receipt_sink`` (optional) receives every decision receipt for durable
    mirroring — typically the hash-chained audit log's append_event.
    """
    identity = IdentityRegistry()
    capabilities = CapabilityRouter()
    receipts = ReceiptStore(receipt_sink)
    sm = StateMachineEngine(receipts)
    authority = AuthorityGateway(identity, capabilities, receipts, sm)
    provenance = ProvenanceGraph()
    promotions = PromotionController(receipts)
    rollbacks = RollbackController()
    datasets = DatasetRegistry(sm, provenance)
    features = FeatureRegistry(provenance)
    models = ModelRegistry(provenance, promotions)
    experiments = ExperimentRegistry(sm, provenance)
    strategies = StrategyRegistry(provenance=provenance)
    certification: CertificationOracle = RegistryCertificationOracle(strategies)
    # Competence resolved from the same registry the oracle certifies
    # against, so a playbook can only activate in a regime its strategy was
    # measured good enough to trade. Resolved lazily rather than read here:
    # the registry is empty at construction, so a snapshot taken now would
    # refuse every strategy forever.
    _competence = competence_resolver(strategies)
    playbook_router = PlaybookRouter(certification, competence=_competence)

    # Register standard lifecycles
    for lifecycle in (STRATEGY_LIFECYCLE, HYPOTHESIS_LIFECYCLE, EXPERIMENT_LIFECYCLE):
        sm.register_definition(lifecycle)

    # Register default actors
    identity.register("system", ActorType.SERVICE, "AIOS System", roles={Role.ADMIN})

    # Declare capabilities that role mappings reference
    capability_names = (
        "AIOS.transition.strategy",
        "AIOS.transition.hypothesis",
        "AIOS.transition.experiment",
        "AIOS.research",
        "AIOS.backtest",
        "AIOS.execute",
        "AIOS.evaluate",
        "AIOS.promote.strategy",
        "AIOS.register.dataset",
        "AIOS.register.feature",
        "AIOS.experiment",
    )
    for cap_name in capability_names:
        capabilities.declare(cap_name, ABC, f"Capability: {cap_name}")

    # Grant system roles access to all capabilities (composition root only)
    for capability_name in capability_names:
        authority.grant_role_capability(Role.ADMIN, capability_name)
        authority.grant_role_capability(Role.RISK_ADMIN, capability_name)

    authority.grant_role_capability(Role.AGENT_RESEARCH, "AIOS.research")
    authority.grant_role_capability(Role.AGENT_STRATEGY, "AIOS.backtest")
    authority.grant_role_capability(Role.AGENT_STRATEGY, "AIOS.transition.strategy")
    authority.grant_role_capability(Role.AGENT_CRITIC, "AIOS.evaluate")
    authority.grant_role_capability(Role.AGENT_CRITIC, "AIOS.transition.hypothesis")
    authority.grant_role_capability(Role.SERVICE_EXECUTION, "AIOS.execute")
    authority.grant_role_capability(Role.SERVICE_DATA, "AIOS.register.dataset")
    authority.grant_role_capability(Role.SERVICE_DATA, "AIOS.register.feature")

    return AIOSKernel(
        identity=identity,
        capabilities=capabilities,
        receipts=receipts,
        state_machine=sm,
        authority=authority,
        provenance=provenance,
        promotions=promotions,
        rollbacks=rollbacks,
        datasets=datasets,
        features=features,
        models=models,
        experiments=experiments,
        strategies=strategies,
        playbook_router=playbook_router,
        certification=certification,
    )
