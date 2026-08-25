"""KernelBridge: wires the ReplayRunner onto the AIOS kernel (Phase A completion).

The kernel existed but the runner bypassed it. This bridge makes the kernel the
operating system of the replay loop:

- Every community actor is a registered kernel identity with least-privilege roles.
- The replay dataset and its features are registered as VERSIONED, HASHED
  kernel objects (DatasetRegistry / FeatureRegistry).
- The whole run is an ExperimentRun pinned to dataset version + seed + config,
  with a reproducibility hash.
- Hypotheses, strategies, executions and postmortems become kernel-tracked
  objects whose lifecycle transitions pass through the AuthorityGateway —
  every ALLOW/DENY produces a decision receipt mirrored into the hash-chained
  audit log.
- The provenance graph links dataset -> hypothesis -> strategy -> experiment
  -> execution -> postmortem so any outcome can answer "WHY did we believe".

Nothing here reasons. The bridge only records and enforces what the
deterministic planes already decided.
"""

import csv
import hashlib
import uuid
from pathlib import Path
from typing import Any

from core.event_bus import BaseEventBus, EventTopic
from core.platform_events import (
    PlatformEvent,
    PlatformEventType,
    dataset_version_created,
    evaluation_completed,
    execution_completed,
    experiment_completed,
    experiment_started,
    hypothesis_created,
    hypothesis_rejected,
    order_authorized,
    order_denied,
    order_requested,
    post_mortem_created,
    risk_decision_made,
)
from kernel.authority import AuthorityRequest, AuthorityResult
from kernel.bootstrap import AIOSKernel, create_kernel
from kernel.identity import ActorType, Role
from kernel.provenance import NodeType
from kernel.receipts import Decision, DecisionReceipt
from schemas.contracts import (
    CandidateHypothesis,
    PortfolioAllocationPlan,
    PostmortemRecord,
    StrategySpecification,
    TradeExecutionReceipt,
    VerificationReport,
)

# Community actors: (actor_id, type, display_name, roles)
_COMMUNITY_ACTORS: tuple[tuple[str, ActorType, str, set[Role]], ...] = (
    ("c1-data-fabric", ActorType.SERVICE, "C1 Data Fabric", {Role.SERVICE_DATA}),
    ("c2-research", ActorType.AGENT, "C2 Research Agent", {Role.AGENT_RESEARCH}),
    ("c3-verification", ActorType.AGENT, "C3 Verification Agent", {Role.AGENT_CRITIC}),
    ("c4-strategy", ActorType.AGENT, "C4 Strategy Agent", {Role.AGENT_STRATEGY}),
    ("c5-execution", ActorType.SERVICE, "C5 Execution Service", {Role.SERVICE_EXECUTION}),
    ("c8-autoresearch", ActorType.AGENT, "C8 AutoResearch Engine", {Role.AGENT_RESEARCH}),
    ("c9-governor", ActorType.SERVICE, "C9 Portfolio Governor", {Role.RISK_ADMIN}),
)

_TIME_COLUMNS = ("timestamp", "datetime", "date", "ts")

_PLATFORM_TOPICS: dict[PlatformEventType, EventTopic] = {
    PlatformEventType.DATASET_VERSION_CREATED: EventTopic.PLATFORM_DATASET_VERSION_CREATED,
    PlatformEventType.EXPERIMENT_STARTED: EventTopic.PLATFORM_EXPERIMENT_STARTED,
    PlatformEventType.EXPERIMENT_COMPLETED: EventTopic.PLATFORM_EXPERIMENT_COMPLETED,
    PlatformEventType.HYPOTHESIS_CREATED: EventTopic.PLATFORM_HYPOTHESIS_CREATED,
    PlatformEventType.HYPOTHESIS_REJECTED: EventTopic.PLATFORM_HYPOTHESIS_REJECTED,
    PlatformEventType.EVALUATION_COMPLETED: EventTopic.PLATFORM_EVALUATION_COMPLETED,
    PlatformEventType.ORDER_REQUESTED: EventTopic.PLATFORM_ORDER_REQUESTED,
    PlatformEventType.ORDER_AUTHORIZED: EventTopic.PLATFORM_ORDER_AUTHORIZED,
    PlatformEventType.ORDER_DENIED: EventTopic.PLATFORM_ORDER_DENIED,
    PlatformEventType.RISK_DECISION_MADE: EventTopic.PLATFORM_RISK_DECISION_MADE,
    PlatformEventType.EXECUTION_COMPLETED: EventTopic.PLATFORM_EXECUTION_COMPLETED,
    PlatformEventType.POST_MORTEM_CREATED: EventTopic.PLATFORM_POST_MORTEM_CREATED,
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_facts(paths: list[Path]) -> dict[str, Any]:
    """Schema hash, row count and time bounds across the replay CSVs."""
    schema_parts: list[str] = []
    row_count = 0
    time_start: str | None = None
    time_end: str | None = None
    for path in paths:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            schema_parts.append(",".join(reader.fieldnames or []))
            time_col = next(
                (c for c in _TIME_COLUMNS if c in (reader.fieldnames or [])), None
            )
            for row in reader:
                row_count += 1
                if time_col is not None:
                    value = row.get(time_col) or ""
                    if value:
                        if time_start is None or value < time_start:
                            time_start = value
                        if time_end is None or value > time_end:
                            time_end = value
    schema_hash = hashlib.sha256(";".join(schema_parts).encode()).hexdigest()
    return {
        "schema_hash": schema_hash,
        "row_count": row_count,
        "time_start": time_start or "",
        "time_end": time_end or "",
    }


class KernelBridge:
    """Adapter between the ReplayRunner event flow and the AIOS kernel.

    ``research_engine`` (Phase C) is optional; when present, hypotheses are
    additionally persisted as durable knowledge with hash-addressable evidence.
    """

    def __init__(
        self,
        kernel: AIOSKernel | None = None,
        audit_log: Any = None,
        research_engine: Any = None,
        event_bus: BaseEventBus | None = None,
    ) -> None:
        # When we own kernel creation, wire the audit log as the receipt sink:
        # EVERY decision receipt (gateway + state-machine co-receipts) is then
        # mirrored into the hash-chained log by the store itself.
        self.kernel = kernel or create_kernel(receipt_sink=audit_log)
        self._audit_log = audit_log
        self.research_engine = research_engine  # HypothesisEngine, optional
        self.event_bus = event_bus  # typed platform events, optional
        for actor_id, actor_type, display_name, roles in _COMMUNITY_ACTORS:
            self.kernel.identity.register(actor_id, actor_type, display_name, roles=roles)
        self._hypotheses: set[str] = set()
        self._strategies: set[str] = set()
        self.dataset_version: str | None = None
        self.experiment_id: str | None = None
        self._authorization_calls = 0

    # ------------------------------------------------------------ internals

    async def _emit(self, event: PlatformEvent) -> None:
        """Publish a typed platform event onto the bus.

        The runner subscribes its hash-chained audit logger to EVERY topic,
        so publishing here makes the event durable automatically — no
        separate persistence path, no double logging.
        """
        if self.event_bus is None:
            return
        topic = _PLATFORM_TOPICS.get(event.event_type)
        if topic is None:
            return
        await self.event_bus.publish(topic, event)

    async def _authorize(
        self,
        actor_id: str,
        capability: str,
        object_type: str,
        object_id: str,
        action: str,
        reason: str,
        evidence_refs: list[str] | None = None,
    ) -> AuthorityResult:
        self._authorization_calls += 1
        result = await self.kernel.authority.authorize(
            AuthorityRequest(
                actor_id=actor_id,
                capability=capability,
                object_type=object_type,
                object_id=object_id,
                action=action,
                reason=reason,
                evidence_refs=evidence_refs or [],
            )
        )
        return result

    async def _transition(
        self,
        object_type: str,
        object_id: str,
        to_state: str,
        actor_id: str,
        capability: str,
        reason: str,
        evidence_refs: list[str] | None = None,
    ) -> AuthorityResult | None:
        """Authorize a lifecycle transition through the gateway, then link provenance.

        Returns None when the object is unknown or already in the target state
        (idempotent hooks); returns the DENY result when authority refuses.
        """
        try:
            from_state = self.kernel.state_machine.get_state(object_type, object_id)
        except KeyError:
            return None
        if from_state == to_state:
            return None
        result = await self._authorize(
            actor_id,
            capability,
            object_type,
            object_id,
            f"transition:{to_state}",
            reason,
            evidence_refs,
        )
        if result.decision is not Decision.ALLOW:
            return result
        node_type = _lifecycle_to_node_type(object_type)
        state_node = f"{object_id}:{to_state}"
        try:
            self.kernel.provenance.add_node(
                state_node, node_type, label=f"{object_id} -> {to_state}"
            )
        except ValueError:
            pass
        source_node = f"{object_id}:{from_state}"
        if not self.kernel.provenance.has_node(source_node):
            source_node = object_id  # initial states hang off the object node itself
        try:
            self.kernel.provenance.add_edge(source_node, state_node, "transitions_to")
        except KeyError:
            pass
        return result

    def _link(self, from_id: str, to_id: str, relationship: str) -> None:
        try:
            self.kernel.provenance.add_edge(from_id, to_id, relationship)
        except KeyError:
            pass

    # ------------------------------------------------------------- data plane

    async def register_replay_dataset(
        self, csv_path_by_symbol: dict[str, str | Path], actor_id: str = "c1-data-fabric"
    ) -> dict[str, str]:
        """Register the replay CSVs as a versioned, hashed dataset + feature."""
        if self.dataset_version is not None:
            return {"dataset_id": "replay", "version": self.dataset_version}
        paths = [Path(p) for p in sorted(csv_path_by_symbol.values(), key=str)]
        content_hash = hashlib.sha256(
            "|".join(_sha256_file(p) for p in paths).encode()
        ).hexdigest()
        facts = _csv_facts(paths)
        version = f"v1-{content_hash[:12]}"

        await self._authorize(
            actor_id, "AIOS.register.dataset", "dataset", "replay",
            "register", f"register replay dataset {version}",
        )
        dv = self.kernel.datasets.register(  # type: ignore[union-attr]
            dataset_id="replay",
            version=version,
            source="replay_csv",
            schema_hash=facts["schema_hash"],
            content_hash=content_hash,
            time_start=facts["time_start"],
            time_end=facts["time_end"],
            row_count=facts["row_count"],
            actor_id="system",
            metadata={"symbols": sorted(csv_path_by_symbol)},
        )
        self.kernel.datasets.validate("replay", version, "system")  # type: ignore[union-attr]
        self.kernel.datasets.activate("replay", version, "system")  # type: ignore[union-attr]
        self.dataset_version = version

        await self._authorize(
            "c1-data-fabric", "AIOS.register.feature", "feature", "ohlcv_passthrough",
            "register", "register replay feature ohlcv_passthrough@v1",
        )
        self.kernel.features.register(  # type: ignore[union-attr]
            feature_id="ohlcv_passthrough",
            version="v1",
            definition="raw OHLCV bars consumed untransformed from the replay dataset",
            dataset_ref=dv.reference(),
            computation_code="identity(ohlcv)",
        )
        self.kernel.features.validate("ohlcv_passthrough", "v1")  # type: ignore[union-attr]
        await self._emit(dataset_version_created("replay", version, content_hash))
        return {"dataset_id": "replay", **dv.reference()}

    # -------------------------------------------------------- experiment plane

    async def start_experiment(
        self, symbols: list[str], configuration: dict[str, Any], random_seed: int = 42
    ) -> str:
        assert self.dataset_version is not None, "register_replay_dataset must run first"
        await self._authorize(
            "system", "AIOS.experiment", "experiment", "pending",
            "create", "start replay experiment",
        )
        self.experiment_id = uuid.uuid4().hex[:12]
        run = self.kernel.experiments.create(  # type: ignore[union-attr]
            experiment_id=self.experiment_id,
            hypothesis_id="REPLAY_BATCH",
            strategy_version="mixed",
            dataset_version=self.dataset_version,
            actor_id="system",
            feature_versions=["ohlcv_passthrough:v1"],
            configuration={"symbols": symbols, **configuration},
            random_seed=random_seed,
            environment="replay",
        )
        self.kernel.experiments.start(self.experiment_id, "system")  # type: ignore[union-attr]
        await self._emit(
            experiment_started(self.experiment_id, self.dataset_version, random_seed)
        )
        return run.reproducibility_hash

    async def complete_experiment(self, result_summary: dict[str, Any]) -> None:
        if self.experiment_id is None:
            return
        self.kernel.experiments.complete(self.experiment_id, "system", result_summary)  # type: ignore[union-attr]
        await self._emit(experiment_completed(self.experiment_id, result_summary))

    # ------------------------------------------------------- research pipeline

    async def on_hypothesis(self, hypothesis: CandidateHypothesis) -> None:
        """Track a C2 hypothesis as a first-class kernel object (UNTESTED)."""
        hid = hypothesis.hypothesis_id
        if hid in self._hypotheses:
            return
        self._hypotheses.add(hid)
        self.kernel.create_tracked_object(
            "hypothesis",
            hid,
            actor_id="c2-research",
            label=hypothesis.thesis[:120],
            symbol=hypothesis.symbol,
            timeframe=hypothesis.timeframe,
        )
        if self.dataset_version is not None:
            self._link(f"replay:{self.dataset_version}", hid, "derived_from")
        if self.research_engine is not None:
            self.research_engine.register_from_candidate(
                hypothesis,
                dataset_ref={"dataset_id": "replay", "version": self.dataset_version},
            )
        await self._emit(hypothesis_created(hid, hypothesis.symbol, hypothesis.thesis))

    async def on_verification(self, report: VerificationReport) -> None:
        """C3 verdict moves a VERIFIED hypothesis UNTESTED -> TESTING.

        Unverified hypotheses stay UNTESTED: they were never promoted to an
        active test, and the lifecycle has no failed-verification state.
        """
        if not report.is_verified:
            return
        if self.research_engine is not None:
            self.research_engine.apply_verification(report)
        await self._transition(
            "hypothesis",
            report.hypothesis_id,
            "TESTING",
            actor_id="c3-verification",
            capability="AIOS.transition.hypothesis",
            reason=f"verified confidence={report.confidence_score:.1f}",
            evidence_refs=[report.report_id],
        )

    async def on_hypothesis_outcome(
        self, hypothesis_id: str, direction_correct: bool, pnl: float
    ) -> None:
        """Post-mortem outcome: SUPPORTED or REJECTED (negative knowledge preserved)."""
        target = "SUPPORTED" if direction_correct else "REJECTED"
        result = await self._transition(
            "hypothesis",
            hypothesis_id,
            target,
            actor_id="system",
            capability="AIOS.transition.hypothesis",
            reason=f"outcome pnl={pnl:+.2f} direction_correct={direction_correct}",
        )
        if target == "REJECTED" and (result is None or result.decision is Decision.ALLOW):
            await self._emit(hypothesis_rejected(hypothesis_id, pnl))

    # -------------------------------------------------------- strategy pipeline

    async def on_strategy(self, strategy: StrategySpecification) -> None:
        """Track a C4 strategy: IDEA -> HYPOTHESIS -> DRAFT (firewall-staged)."""
        sid = strategy.strategy_id
        if sid in self._strategies:
            return
        self._strategies.add(sid)
        self.kernel.create_tracked_object(
            "strategy",
            sid,
            actor_id="c4-strategy",
            label=f"{strategy.action} {strategy.symbol} ({strategy.family})",
            symbol=strategy.symbol,
            family=strategy.family,
            hypothesis_id=strategy.hypothesis_id,
        )
        self._link(strategy.hypothesis_id, sid, "produces")
        await self._transition(
            "strategy", sid, "HYPOTHESIS", "c4-strategy", "AIOS.transition.strategy",
            "linked verified hypothesis", evidence_refs=[strategy.hypothesis_id],
        )
        await self._transition(
            "strategy", sid, "DRAFT", "c4-strategy", "AIOS.transition.strategy",
            "passed deterministic risk firewall staging (R:R >= hard floor)",
        )

    async def on_plan_approved(self, plan: PortfolioAllocationPlan) -> None:
        """C9 allocation validates the strategy for paper execution."""
        await self._transition(
            "strategy", plan.strategy.strategy_id, "VALIDATED", "c9-governor",
            "AIOS.transition.strategy", f"portfolio plan {plan.plan_id[:8]} approved",
        )

    async def authorize_execution(self, plan: PortfolioAllocationPlan) -> AuthorityResult:
        """The ONLY path from an approved plan to order dispatch."""
        await self._emit(
            order_requested(
                plan.plan_id,
                plan.strategy.strategy_id,
                plan.strategy.action,
                plan.strategy.symbol,
            )
        )
        result = await self._authorize(
            "c5-execution",
            "AIOS.execute",
            "strategy",
            plan.strategy.strategy_id,
            "execute_order",
            f"plan {plan.plan_id[:8]} {plan.strategy.action} {plan.strategy.symbol}",
            evidence_refs=[plan.plan_id],
        )
        if result.decision is Decision.ALLOW:
            await self._emit(
                order_authorized(plan.plan_id, plan.strategy.strategy_id, result.receipt.receipt_id)
            )
        else:
            await self._emit(
                risk_decision_made("DENY", plan.strategy.strategy_id, result.detail, result.receipt.receipt_id)
            )
            await self._emit(
                order_denied(
                    plan.strategy.strategy_id, result.detail, [result.receipt.receipt_id]
                )
            )
        return result

    async def on_plan_denied(self, strategy_id: str, reason: str) -> None:
        """Governor rejection: recorded as a DENY receipt; no lifecycle change.

        The deterministic governor already refused; the kernel's job is to make
        that refusal an immutable, queryable decision receipt.
        """
        receipt = DecisionReceipt(
            actor_id="c9-governor",
            actor_type="SERVICE",
            object_type="strategy",
            object_id=strategy_id,
            requested_action="execute_order",
            capability="AIOS.execute",
            input_hash=hashlib.sha256(reason.encode()).hexdigest(),
            decision=Decision.DENY,
            reason=reason,
        )
        self.kernel.receipts.save(receipt)
        self._authorization_calls += 1
        await self._emit(
            order_denied(strategy_id, reason, [receipt.receipt_id], source="c9-governor")
        )
        await self._emit(
            risk_decision_made("DENY", strategy_id, reason, receipt.receipt_id)
        )

    async def on_receipt(self, receipt: TradeExecutionReceipt) -> None:
        """A fill in the replay backtest: strategy -> BACKTESTED + EXECUTION node."""
        await self._transition(
            "strategy", receipt.strategy_id, "BACKTESTED", "system",
            "AIOS.transition.strategy",
            f"filled {receipt.filled_quantity:g} @ {receipt.fill_price:g} ({receipt.venue})",
            evidence_refs=[receipt.execution_id],
        )
        try:
            self.kernel.provenance.add_node(
                receipt.execution_id,
                NodeType.EXECUTION,
                label=f"{receipt.symbol} @ {receipt.fill_price:g}",
                venue=receipt.venue,
                is_simulated=receipt.is_simulated,
            )
        except ValueError:
            return
        self._link(receipt.strategy_id, receipt.execution_id, "produces_execution")
        if self.experiment_id is not None:
            self._link(self.experiment_id, receipt.execution_id, "executed_in")
        await self._emit(
            execution_completed(
                receipt.execution_id,
                receipt.symbol,
                receipt.fill_price,
                receipt.filled_quantity,
                receipt.venue,
            )
        )

    # ---------------------------------------------------------- learning loop

    async def on_settled(
        self,
        receipt: TradeExecutionReceipt,
        exit_reason: str,
        realized_pnl: float,
        direction_correct: bool,
        postmortem: PostmortemRecord | None,
    ) -> None:
        """Close the loop: EVALUATED strategy, hypothesis verdict, postmortem node."""
        await self._transition(
            "strategy", receipt.strategy_id, "EVALUATED", "system",
            "AIOS.transition.strategy",
            f"exit {exit_reason} pnl={realized_pnl:+.2f}",
        )
        hypothesis_id = ""
        node = self.kernel.provenance.get_node(receipt.strategy_id)
        hypothesis_id = str(node.data.get("hypothesis_id", "")) if node else ""
        await self._emit(
            evaluation_completed(receipt.strategy_id, exit_reason, realized_pnl)
        )
        if hypothesis_id:
            await self.on_hypothesis_outcome(hypothesis_id, direction_correct, realized_pnl)
            if self.research_engine is not None:
                self.research_engine.apply_outcome(
                    hypothesis_id,
                    direction_correct=direction_correct,
                    realized_pnl=realized_pnl,
                    postmortem=postmortem,
                    execution_id=receipt.execution_id,
                )
        if postmortem is not None:
            try:
                self.kernel.provenance.add_node(
                    postmortem.postmortem_id,
                    NodeType.POST_MORTEM,
                    label=f"postmortem {postmortem.symbol}",
                    symbol=postmortem.symbol,
                )
            except ValueError:
                return
            self._link(receipt.execution_id, postmortem.postmortem_id, "postmortem_of")
            if hypothesis_id:
                self._link(postmortem.postmortem_id, hypothesis_id, "evaluates")
            await self._emit(
                post_mortem_created(postmortem.postmortem_id, hypothesis_id, postmortem.symbol)
            )

    # ------------------------------------------------------------------ stats

    def tracked_strategy_ids(self) -> set[str]:
        return set(self._strategies)

    def tracked_hypothesis_ids(self) -> set[str]:
        return set(self._hypotheses)

    def stats(self) -> dict[str, Any]:
        """Kernel observability snapshot (read-only)."""
        k = self.kernel
        stats = {
            "actors_registered": len(k.identity.list_all()),
            "capabilities_declared": len(k.capabilities.list_capabilities()),
            "receipts": k.receipts.count(),
            "authorizations": self._authorization_calls,
            "provenance_nodes": k.provenance.node_count(),
            "provenance_edges": k.provenance.edge_count(),
            "tracked_hypotheses": len(self._hypotheses),
            "tracked_strategies": len(self._strategies),
            "dataset_version": self.dataset_version,
            "experiment_id": self.experiment_id,
        }
        if self.research_engine is not None:
            stats["research"] = self.research_engine.knowledge_summary()
        return stats


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
