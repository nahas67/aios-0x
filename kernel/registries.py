"""Data Architecture Registries: dataset, feature, model, experiment.

Every experiment must be reproducible. This module makes that enforceable:
a strategy references a dataset VERSION, a feature VERSION, a model VERSION —
not ambiguous names. The experiment registry pins all versions + seed + config
so any historical result can be reproduced exactly.
"""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.experiment_sink import PostgresExperimentSink, SqliteExperimentSink
from kernel.promotion import PromotionController
from kernel.provenance import NodeType, ProvenanceGraph
from kernel.state_machine import StateMachineDefinition, StateMachineEngine

#: Either durable tier. The registry writes snapshots and reads them back;
#: both tiers hold the same events or the parity suite has found a defect.
ExperimentSink = SqliteExperimentSink | PostgresExperimentSink


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


# ================================================================ dataset


class DatasetStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class DatasetVersion(BaseModel):
    dataset_id: str
    version: str
    source: str
    schema_hash: str
    content_hash: str
    time_start: str
    time_end: str
    row_count: int
    normalization_version: str = "v1"
    status: DatasetStatus = DatasetStatus.DRAFT
    created_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # ── vNext G030: point-in-time semantics. Optional so existing registrations
    # keep working; a version that intends to back research must set them.
    as_of_semantics: str = Field(
        default="event_time",
        description="Which clock the version is cut on: event_time, available_at, or as_known",
    )
    bitemporal: bool = Field(
        default=False,
        description="True when the version stores both valid time and transaction time",
    )
    immutable_hash: str | None = Field(
        default=None,
        description="Content digest of the frozen dataset; set once, never mutated",
    )

    def reference(self) -> dict[str, str]:
        """The reference a strategy/experiment pins to."""
        ref: dict[str, str] = {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "content_hash": self.content_hash,
        }
        if self.immutable_hash is not None:
            ref["immutable_hash"] = self.immutable_hash
        return ref

    def is_pit_qualified(self) -> bool:
        """Whether this version may back point-in-time research.

        A version qualifies when it names its cut clock, records both times,
        and froze its content. Anything less is a snapshot with an opinion
        about time, not a point-in-time dataset.
        """
        return (
            self.as_of_semantics in {"event_time", "available_at", "as_known"}
            and self.bitemporal
            and self.immutable_hash is not None
        )


def _dataset_lifecycle(object_type: str) -> StateMachineDefinition:
    """The lifecycle every dataset version follows. Factored so registration
    and resume construct the identical machine: a resume that rebuilt a
    different machine would restore states the live path could never reach."""
    return StateMachineDefinition(
        object_type=object_type, initial_state="DRAFT",
        transitions={"DRAFT": {"VALIDATED"}, "VALIDATED": {"ACTIVE", "DEPRECATED"},
                     "ACTIVE": {"DEPRECATED"}, "DEPRECATED": set()},
        terminal_states={"DEPRECATED"},
    )


class DatasetRegistry:
    """Versioned datasets. A dataset reference identifies the EXACT data used.

    With a ``sink``, every lifecycle transition is written through to durable
    storage before the in-memory commit — the same sink-first discipline as
    the experiment ledger, for the same reason: a durable event the memory
    lacks heals on resume, while a memory state the sink lacks is gone
    permanently. Legality is pre-checked so an illegal transition leaves no
    phantom event in a log that cannot un-write.
    """

    def __init__(
        self,
        state_machine: StateMachineEngine,
        provenance: ProvenanceGraph,
        sink: Any = None,
    ) -> None:
        self._sm = state_machine
        self._provenance = provenance
        self._versions: dict[str, DatasetVersion] = {}
        self._sink = sink

    @classmethod
    def resume(
        cls,
        state_machine: StateMachineEngine,
        provenance: ProvenanceGraph,
        sink: Any,
    ) -> "DatasetRegistry":
        """Rebuild a registry from its durable log after a restart.

        Re-registers each version's lifecycle definition (identical shape to
        the live path), restores state-machine objects at their stored status
        without replaying transitions, and replays provenance nodes — all in
        first-seen order.
        """
        registry = cls(state_machine, provenance, sink)
        for key, payload in sink.read_snapshots().items():
            version = DatasetVersion.model_validate_json(payload)
            registry._versions[key] = version
            state_machine.register_definition(_dataset_lifecycle(key))
            state_machine.restore_object(key, key, version.status.value)
            provenance.add_node(
                key, NodeType.DATASET_VERSION, label=f"{version.dataset_id}@{version.version}",
                content_hash=version.content_hash, source=version.source,
            )
        return registry

    @property
    def sink(self) -> Any | None:
        """The durable sink, if one is attached."""
        return self._sink

    def _record(self, event_type: str, key: str, version: DatasetVersion) -> None:
        if self._sink is None:
            return
        self._sink.append(key, event_type, version.model_dump_json(), _now())

    def register(
        self,
        dataset_id: str,
        version: str,
        source: str,
        schema_hash: str,
        content_hash: str,
        time_start: str,
        time_end: str,
        row_count: int,
        actor_id: str,
        metadata: dict[str, Any] | None = None,
        as_of_semantics: str = "event_time",
        bitemporal: bool = False,
        immutable_hash: str | None = None,
    ) -> DatasetVersion:
        key = f"{dataset_id}:{version}"
        # Both registries checked before anything is written: the sink cannot
        # un-write, so a collision must fail before the REGISTERED event.
        if key in self._versions or self._sm.has_object(key, key):
            raise ValueError(f"dataset version already exists: {key!r}")
        dv = DatasetVersion(
            dataset_id=dataset_id,
            version=version,
            source=source,
            schema_hash=schema_hash,
            content_hash=content_hash,
            time_start=time_start,
            time_end=time_end,
            row_count=row_count,
            metadata=metadata or {},
            as_of_semantics=as_of_semantics,
            bitemporal=bitemporal,
            immutable_hash=immutable_hash,
        )
        self._record("REGISTERED", key, dv)
        self._versions[key] = dv
        self._sm.register_definition(_dataset_lifecycle(key))
        self._sm.create_object(key, key, actor_id)
        self._provenance.add_node(
            key, NodeType.DATASET_VERSION, label=f"{dataset_id}@{version}",
            content_hash=content_hash, source=source,
        )
        return dv

    def get(self, dataset_id: str, version: str) -> DatasetVersion:
        key = f"{dataset_id}:{version}"
        dv = self._versions.get(key)
        if dv is None:
            raise KeyError(f"dataset version not found: {key!r}")
        return dv

    def validate(self, dataset_id: str, version: str, actor_id: str) -> None:
        key = f"{dataset_id}:{version}"
        self._sm.check_transition(key, key, "VALIDATED")
        staged = self._versions[key].model_copy(update={"status": DatasetStatus.VALIDATED})
        self._record("VALIDATED", key, staged)
        self._sm.transition(key, key, "VALIDATED", actor_id, "dataset validated")
        self._versions[key] = staged

    def activate(self, dataset_id: str, version: str, actor_id: str) -> None:
        key = f"{dataset_id}:{version}"
        self._sm.check_transition(key, key, "ACTIVE")
        staged = self._versions[key].model_copy(update={"status": DatasetStatus.ACTIVE})
        self._record("ACTIVATED", key, staged)
        self._sm.transition(key, key, "ACTIVE", actor_id, "dataset activated")
        self._versions[key] = staged

    def compute_hash(self, data: Any) -> str:
        return _hash(data)


# ================================================================ feature


class FeatureVersion(BaseModel):
    feature_id: str
    version: str
    definition: str
    dataset_ref: dict[str, str]
    computation_hash: str
    validation_status: str = "PENDING"
    created_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureRegistry:
    """Versioned features. A strategy references a feature VERSION, not a name."""

    def __init__(self, provenance: ProvenanceGraph) -> None:
        self._provenance = provenance
        self._versions: dict[str, FeatureVersion] = {}

    def register(
        self,
        feature_id: str,
        version: str,
        definition: str,
        dataset_ref: dict[str, str],
        computation_code: str,
        metadata: dict[str, Any] | None = None,
    ) -> FeatureVersion:
        key = f"{feature_id}:{version}"
        if key in self._versions:
            raise ValueError(f"feature version already exists: {key!r}")
        fv = FeatureVersion(
            feature_id=feature_id,
            version=version,
            definition=definition,
            dataset_ref=dataset_ref,
            computation_hash=_hash(computation_code),
            metadata=metadata or {},
        )
        self._versions[key] = fv
        self._provenance.add_node(
            key, NodeType.FEATURE_VERSION, label=f"{feature_id}@{version}",
            dataset_ref=json.dumps(dataset_ref),
        )
        # Link to dataset in provenance
        dataset_node = f"{dataset_ref['dataset_id']}:{dataset_ref['version']}"
        try:
            self._provenance.add_edge(dataset_node, key, "feature_computed_from")
        except KeyError:
            pass  # dataset not in provenance yet
        return fv

    def get(self, feature_id: str, version: str) -> FeatureVersion:
        key = f"{feature_id}:{version}"
        fv = self._versions.get(key)
        if fv is None:
            raise KeyError(f"feature version not found: {key!r}")
        return fv

    def validate(self, feature_id: str, version: str) -> None:
        key = f"{feature_id}:{version}"
        fv = self._versions.get(key)
        if fv is None:
            raise KeyError(f"feature version not found: {key!r}")
        fv.validation_status = "VALIDATED"


# ================================================================ model


class ModelStatus(StrEnum):
    DEFINED = "DEFINED"
    TRAINED = "TRAINED"
    EVALUATED = "EVALUATED"
    PROMOTED = "PROMOTED"
    DEPRECATED = "DEPRECATED"


class ModelVersion(BaseModel):
    model_id: str
    version: str
    model_type: str
    feature_ref: dict[str, str]
    artifact_hash: str = ""
    evaluation_metrics: dict[str, float] = Field(default_factory=dict)
    status: ModelStatus = ModelStatus.DEFINED
    created_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelRegistry:
    """Versioned models. Uses kernel PromotionController for promotion."""

    def __init__(
        self,
        provenance: ProvenanceGraph,
        promotions: PromotionController,
    ) -> None:
        self._provenance = provenance
        self._promotions = promotions
        self._versions: dict[str, ModelVersion] = {}

    def register(
        self,
        model_id: str,
        version: str,
        model_type: str,
        feature_ref: dict[str, str],
        metadata: dict[str, Any] | None = None,
    ) -> ModelVersion:
        key = f"{model_id}:{version}"
        if key in self._versions:
            raise ValueError(f"model version already exists: {key!r}")
        mv = ModelVersion(
            model_id=model_id,
            version=version,
            model_type=model_type,
            feature_ref=feature_ref,
            metadata=metadata or {},
        )
        self._versions[key] = mv
        self._provenance.add_node(
            key, NodeType.MODEL_VERSION, label=f"{model_id}@{version}",
        )
        feature_node = f"{feature_ref.get('feature_id', '')}:{feature_ref.get('version', '')}"
        try:
            self._provenance.add_edge(feature_node, key, "model_trained_on")
        except KeyError:
            pass
        return mv

    def mark_trained(self, model_id: str, version: str, artifact_hash: str) -> None:
        key = f"{model_id}:{version}"
        mv = self._versions.get(key)
        if mv is None:
            raise KeyError(f"model version not found: {key!r}")
        mv.status = ModelStatus.TRAINED
        mv.artifact_hash = artifact_hash

    def mark_evaluated(self, model_id: str, version: str, metrics: dict[str, float]) -> None:
        key = f"{model_id}:{version}"
        mv = self._versions.get(key)
        if mv is None:
            raise KeyError(f"model version not found: {key!r}")
        mv.status = ModelStatus.EVALUATED
        mv.evaluation_metrics = metrics

    def get(self, model_id: str, version: str) -> ModelVersion:
        key = f"{model_id}:{version}"
        mv = self._versions.get(key)
        if mv is None:
            raise KeyError(f"model version not found: {key!r}")
        return mv

    def list_versions(self) -> list[dict[str, Any]]:
        """All registered model versions (JSON-safe), registration order."""
        return [mv.model_dump(mode="json") for mv in self._versions.values()]


# ================================================================ experiment


class ExperimentStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExperimentRun(BaseModel):
    experiment_id: str
    hypothesis_id: str
    strategy_version: str
    dataset_version: str
    feature_versions: list[str] = Field(default_factory=list)
    model_versions: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    random_seed: int = 42
    environment: str = "local"
    status: ExperimentStatus = ExperimentStatus.CREATED
    started_at: str = ""
    completed_at: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    reproducibility_hash: str = ""

    # ── vNext G070: lineage and the reason a run failed.
    #
    # `parent_id` makes the run a node in a derivation tree rather than an
    # isolated record, so "what did we try before this?" is a query rather than
    # a grep. `failure_reason` is the reason the ledger exists at all: a
    # rejected run is the most expensive thing a research programme produces,
    # and without a recorded reason it is indistinguishable from one that was
    # never attempted. That is how "10,000 failed experiments -> 1 lucky
    # result -> a claimed 99% strategy" happens.
    parent_id: str | None = Field(
        default=None, description="Experiment this run was derived from"
    )
    failure_reason: str | None = Field(
        default=None, description="Why this run failed; immutable once set"
    )
    failed_at: str = Field(
        default="", description="When the failure was recorded"
    )
    #: Frozen at completion. The verdict is the expensive artifact; losing it
    #: to a restart means the same failure is paid for twice.
    certification_verdict: str | None = None
    deflated_sharpe: float | None = None

    def compute_reproducibility_hash(self) -> str:
        """The hash that proves this experiment is reproducible.

        Deliberately excludes ``parent_id`` and ``result``: lineage is
        navigational, and a result is an output. Including either would make
        two identical configurations hash differently because of what they
        produced rather than what they were.
        """
        repro_data = {
            "hypothesis_id": self.hypothesis_id,
            "strategy_version": self.strategy_version,
            "dataset_version": self.dataset_version,
            "feature_versions": sorted(self.feature_versions),
            "model_versions": sorted(self.model_versions),
            "configuration": self.configuration,
            "random_seed": self.random_seed,
            "environment": self.environment,
        }
        return _hash(repro_data)


class ExperimentRegistry:
    """Reproducible experiments. Every run pins ALL versions + seed + config.

    With a ``sink``, every transition is also written through to durable
    storage — and the durable write happens *before* the in-memory commit.
    Either order has a crash window, but the two failures are not symmetric:
    a durable event the memory lacks heals on resume (the sink is the
    authority and resume rebuilds from it), while a memory state the sink
    lacks is gone permanently. The sink is the record; the memory is a cache
    of it.

    Transitions replace the stored run object rather than mutating it in
    place, so the snapshot the sink holds and the object the registry holds
    are the same state by construction rather than by careful ordering.
    Whoever holds a run across a transition must re-read it via :meth:`get`.
    """

    def __init__(
        self,
        state_machine: StateMachineEngine,
        provenance: ProvenanceGraph,
        sink: ExperimentSink | None = None,
    ) -> None:
        self._sm = state_machine
        self._provenance = provenance
        self._runs: dict[str, ExperimentRun] = {}
        self._sink = sink

    @classmethod
    def resume(
        cls,
        state_machine: StateMachineEngine,
        provenance: ProvenanceGraph,
        sink: ExperimentSink,
    ) -> "ExperimentRegistry":
        """Rebuild a registry from its durable log after a restart.

        Restores run snapshots, state-machine objects (at their stored status,
        via ``restore_object`` — no transitions are replayed, so no receipts
        are re-emitted), and the provenance nodes and edges. Creation order is
        first-seen order, so a child's parent link always resolves: a parent
        is necessarily recorded before any experiment derived from it.
        """
        registry = cls(state_machine, provenance, sink)
        for experiment_id, payload in sink.read_snapshots().items():
            run = ExperimentRun.model_validate_json(payload)
            registry._runs[experiment_id] = run
            state_machine.restore_object("experiment", experiment_id, run.status.value)
            provenance.add_node(
                experiment_id, NodeType.EXPERIMENT,
                label=f"experiment:{experiment_id}",
                reproducibility_hash=run.reproducibility_hash,
            )
            try:
                provenance.add_edge(run.hypothesis_id, experiment_id, "tested_by")
            except KeyError:
                pass
            if run.parent_id is not None:
                provenance.add_edge(run.parent_id, experiment_id, "derived_from")
        return registry

    @property
    def sink(self) -> ExperimentSink | None:
        """The durable sink, if one is attached."""
        return self._sink

    def _record(self, event_type: str, run: ExperimentRun) -> None:
        """Write one transition event carrying the run's full snapshot."""
        if self._sink is None:
            return
        self._sink.append(
            run.experiment_id, event_type, run.model_dump_json(), _now()
        )

    def create(
        self,
        experiment_id: str,
        hypothesis_id: str,
        strategy_version: str,
        dataset_version: str,
        actor_id: str,
        feature_versions: list[str] | None = None,
        model_versions: list[str] | None = None,
        configuration: dict[str, Any] | None = None,
        random_seed: int = 42,
        environment: str = "local",
        parent_id: str | None = None,
    ) -> ExperimentRun:
        # Both registries checked before anything is written: two registries
        # can share one state machine, and a collision there must fail before
        # the sink write, not after it — the sink cannot un-write.
        if experiment_id in self._runs or self._sm.has_object("experiment", experiment_id):
            raise ValueError(f"experiment already exists: {experiment_id!r}")
        # Self-parent first: it is the more specific diagnosis, and a naive
        # ordering would report "parent not found" for an experiment that has
        # not been created yet, sending the caller looking in the wrong place.
        if parent_id == experiment_id:
            raise ValueError("an experiment cannot be its own parent")
        # A dangling parent reference would make the derivation tree unqueryable
        # in exactly the way that matters: "what did we try before this?".
        if parent_id is not None and parent_id not in self._runs:
            raise KeyError(f"parent experiment not found: {parent_id!r}")
        run = ExperimentRun(
            experiment_id=experiment_id,
            hypothesis_id=hypothesis_id,
            strategy_version=strategy_version,
            dataset_version=dataset_version,
            feature_versions=feature_versions or [],
            model_versions=model_versions or [],
            configuration=configuration or {},
            random_seed=random_seed,
            environment=environment,
            parent_id=parent_id,
        )
        run.reproducibility_hash = run.compute_reproducibility_hash()
        self._record("CREATED", run)
        self._runs[experiment_id] = run
        self._sm.create_object("experiment", experiment_id, actor_id)
        self._provenance.add_node(
            experiment_id, NodeType.EXPERIMENT,
            label=f"experiment:{experiment_id}",
            reproducibility_hash=run.reproducibility_hash,
        )
        # Link hypothesis → experiment in provenance
        try:
            self._provenance.add_edge(hypothesis_id, experiment_id, "tested_by")
        except KeyError:
            pass
        if parent_id is not None:
            self._provenance.add_edge(parent_id, experiment_id, "derived_from")
        return run

    def start(self, experiment_id: str, actor_id: str) -> None:
        # Legality first: the sink write below cannot be un-written, so an
        # illegal transition must fail before it, not after. check_transition
        # raises exactly what transition() would.
        self._sm.check_transition("experiment", experiment_id, "RUNNING")
        staged = self._runs[experiment_id].model_copy(
            update={"status": ExperimentStatus.RUNNING, "started_at": _now()}
        )
        self._record("STARTED", staged)
        self._transition(experiment_id, "RUNNING", actor_id)
        self._runs[experiment_id] = staged

    def complete(self, experiment_id: str, actor_id: str, result: dict[str, Any]) -> None:
        self._sm.check_transition("experiment", experiment_id, "COMPLETED")
        staged = self._runs[experiment_id].model_copy(
            update={
                "status": ExperimentStatus.COMPLETED,
                "completed_at": _now(),
                "result": result,
            }
        )
        self._record("COMPLETED", staged)
        self._transition(experiment_id, "COMPLETED", actor_id)
        self._runs[experiment_id] = staged

    def fail(self, experiment_id: str, actor_id: str, error: str) -> None:
        """Record a failure and WHY.

        The reason is the point. A failure with no recorded cause is
        indistinguishable from a run that was never attempted, so the count of
        things tried cannot be audited — and an unauditable count of trials is
        exactly what makes a "99% win rate" claim unfalsifiable.
        """
        if not error or not error.strip():
            raise ValueError(
                "a failed experiment requires a failure_reason. An unexplained failure "
                "cannot be distinguished from a run that never happened."
            )
        self._sm.check_transition("experiment", experiment_id, "FAILED")
        staged = self._runs[experiment_id].model_copy(
            update={
                "status": ExperimentStatus.FAILED,
                "result": {"error": error},
                "failure_reason": error,
                "failed_at": _now(),
            }
        )
        self._record("FAILED", staged)
        self._transition(experiment_id, "FAILED", actor_id)
        self._runs[experiment_id] = staged

    def attach_verdict(
        self,
        experiment_id: str,
        *,
        verdict: str,
        deflated_sharpe: float | None = None,
    ) -> None:
        """Freeze a certification verdict onto a completed run.

        The verdict is the most expensive artifact a research programme
        produces. With a sink it survives a restart in the durable log;
        without one it survives only as long as the process, and the same
        failure gets paid for twice.
        """
        run = self.get(experiment_id)
        if run.status is not ExperimentStatus.COMPLETED:
            raise ValueError(
                f"cannot attach a verdict to an experiment in {run.status}; "
                "only a completed run has a result to certify"
            )
        staged = run.model_copy(
            update={"certification_verdict": verdict, "deflated_sharpe": deflated_sharpe}
        )
        self._record("VERDICT_ATTACHED", staged)
        self._runs[experiment_id] = staged

    def lineage(self, experiment_id: str) -> list[ExperimentRun]:
        """Root-first derivation chain from the root experiment down to this one."""
        chain: list[ExperimentRun] = []
        seen: set[str] = set()
        current: str | None = experiment_id
        while current is not None and current not in seen:
            seen.add(current)
            run = self._runs.get(current)
            if run is None:
                break
            chain.append(run)
            current = run.parent_id
        chain.reverse()
        return chain

    def children(self, experiment_id: str) -> list[ExperimentRun]:
        """Direct descendants, in creation order."""
        return [r for r in self._runs.values() if r.parent_id == experiment_id]

    def failures(self) -> list[ExperimentRun]:
        """Every failed run, with its reason.

        The query the ledger exists to answer. "What have we tried and why did
        it not work?" is the question that keeps a research programme from
        re-running the same dead idea every quarter.
        """
        return [r for r in self._runs.values() if r.status is ExperimentStatus.FAILED]

    def attempt_count(self) -> dict[str, int]:
        """Trials per hypothesis — the denominator of every claimed win rate.

        Reported so a headline metric can be read against the number of things
        that were tried to find it. A Sharpe quoted without this count is an
        anecdote with a decimal point.
        """
        counts: dict[str, int] = {}
        for run in self._runs.values():
            counts[run.hypothesis_id] = counts.get(run.hypothesis_id, 0) + 1
        return counts

    def is_reproducible(self, experiment_id: str, other: "ExperimentRun") -> bool:
        """Two experiments are reproducible if their hashes match."""
        run = self._runs.get(experiment_id)
        if run is None:
            raise KeyError(f"experiment not found: {experiment_id!r}")
        return run.reproducibility_hash == other.compute_reproducibility_hash()

    def get(self, experiment_id: str) -> ExperimentRun:
        run = self._runs.get(experiment_id)
        if run is None:
            raise KeyError(f"experiment not found: {experiment_id!r}")
        return run

    def _transition(self, experiment_id: str, to_state: str, actor_id: str) -> None:
        self._sm.transition(
            "experiment", experiment_id, to_state, actor_id,
            f"experiment {to_state.lower()}",
        )
