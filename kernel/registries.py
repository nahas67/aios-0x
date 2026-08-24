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

from kernel.promotion import PromotionController
from kernel.provenance import NodeType, ProvenanceGraph
from kernel.state_machine import StateMachineDefinition, StateMachineEngine


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

    def reference(self) -> dict[str, str]:
        """The reference a strategy/experiment pins to."""
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "content_hash": self.content_hash,
        }


class DatasetRegistry:
    """Versioned datasets. A dataset reference identifies the EXACT data used."""

    def __init__(self, state_machine: StateMachineEngine, provenance: ProvenanceGraph) -> None:
        self._sm = state_machine
        self._provenance = provenance
        self._versions: dict[str, DatasetVersion] = {}

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
    ) -> DatasetVersion:
        key = f"{dataset_id}:{version}"
        if key in self._versions:
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
        )
        self._versions[key] = dv
        self._sm.register_definition(StateMachineDefinition(
            object_type=key, initial_state="DRAFT",
            transitions={"DRAFT": {"VALIDATED"}, "VALIDATED": {"ACTIVE", "DEPRECATED"},
                         "ACTIVE": {"DEPRECATED"}, "DEPRECATED": set()},
            terminal_states={"DEPRECATED"},
        ))
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
        self._sm.transition(key, key, "VALIDATED", actor_id, "dataset validated")
        self._versions[key].status = DatasetStatus.VALIDATED

    def activate(self, dataset_id: str, version: str, actor_id: str) -> None:
        key = f"{dataset_id}:{version}"
        self._sm.transition(key, key, "ACTIVE", actor_id, "dataset activated")
        self._versions[key].status = DatasetStatus.ACTIVE

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

    def compute_reproducibility_hash(self) -> str:
        """The hash that proves this experiment is reproducible."""
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
    """Reproducible experiments. Every run pins ALL versions + seed + config."""

    def __init__(
        self,
        state_machine: StateMachineEngine,
        provenance: ProvenanceGraph,
    ) -> None:
        self._sm = state_machine
        self._provenance = provenance
        self._runs: dict[str, ExperimentRun] = {}

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
    ) -> ExperimentRun:
        if experiment_id in self._runs:
            raise ValueError(f"experiment already exists: {experiment_id!r}")
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
        )
        run.reproducibility_hash = run.compute_reproducibility_hash()
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
        return run

    def start(self, experiment_id: str, actor_id: str) -> None:
        self._transition(experiment_id, "RUNNING", actor_id)
        self._runs[experiment_id].status = ExperimentStatus.RUNNING
        self._runs[experiment_id].started_at = _now()

    def complete(self, experiment_id: str, actor_id: str, result: dict[str, Any]) -> None:
        self._transition(experiment_id, "COMPLETED", actor_id)
        run = self._runs[experiment_id]
        run.status = ExperimentStatus.COMPLETED
        run.completed_at = _now()
        run.result = result

    def fail(self, experiment_id: str, actor_id: str, error: str) -> None:
        self._transition(experiment_id, "FAILED", actor_id)
        self._runs[experiment_id].status = ExperimentStatus.FAILED
        self._runs[experiment_id].result = {"error": error}

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
