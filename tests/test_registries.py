"""Data Architecture Registry tests: dataset, feature, model, experiment reproducibility."""

import pytest

from kernel.bootstrap import create_kernel
from kernel.provenance import NodeType
from kernel.registries import (
    DatasetRegistry,
    ExperimentRegistry,
    FeatureRegistry,
    ModelRegistry,
)


@pytest.fixture()
def kernel():
    return create_kernel()


@pytest.fixture()
def dataset_registry(kernel):
    return DatasetRegistry(kernel.state_machine, kernel.provenance)


@pytest.fixture()
def feature_registry(kernel):
    return FeatureRegistry(kernel.provenance)


@pytest.fixture()
def model_registry(kernel):
    return ModelRegistry(kernel.provenance, kernel.promotions)


@pytest.fixture()
def experiment_registry(kernel):
    return ExperimentRegistry(kernel.state_machine, kernel.provenance)


# ------------------------------------------------------------------ dataset


def test_dataset_registration_and_versioning(dataset_registry, kernel) -> None:
    dv = dataset_registry.register(
        dataset_id="btc_daily",
        version="v1.0",
        source="ccxt:binance",
        schema_hash="abc123",
        content_hash="def456",
        time_start="2024-01-01",
        time_end="2025-12-31",
        row_count=730,
        actor_id="system",
    )
    assert dv.content_hash == "def456"
    assert dv.status.value == "DRAFT"

    # Duplicate version rejected
    with pytest.raises(ValueError, match="already exists"):
        dataset_registry.register(
            "btc_daily", "v1.0", "src", "h", "h", "2024", "2025", 1, "system"
        )

    # Lifecycle: DRAFT → VALIDATED → ACTIVE
    dataset_registry.validate("btc_daily", "v1.0", "system")
    dataset_registry.activate("btc_daily", "v1.0", "system")
    retrieved = dataset_registry.get("btc_daily", "v1.0")
    assert retrieved.status.value == "ACTIVE"


def test_dataset_hash_consistency(dataset_registry) -> None:
    data = {"symbol": "BTC/USD", "rows": [1, 2, 3]}
    h1 = dataset_registry.compute_hash(data)
    h2 = dataset_registry.compute_hash(data)
    assert h1 == h2
    different = dataset_registry.compute_hash({"symbol": "BTC/USD", "rows": [1, 2]})
    assert h1 != different


# ------------------------------------------------------------------ feature


def test_feature_versioning_and_dataset_link(feature_registry, dataset_registry, kernel) -> None:
    # Register dataset first so provenance edge can link
    dataset_registry.register(
        "btc_daily", "v1.0", "ccxt", "sh", "ch", "2024", "2025", 730, "system"
    )

    fv = feature_registry.register(
        feature_id="rsi_14",
        version="v1",
        definition="Relative Strength Index (14 period)",
        dataset_ref={"dataset_id": "btc_daily", "version": "v1.0"},
        computation_code="def compute(bars): return rsi(bars, 14)",
    )
    assert fv.computation_hash != ""

    # Duplicate rejected
    with pytest.raises(ValueError, match="already exists"):
        feature_registry.register("rsi_14", "v1", "def", {}, "code")

    feature_registry.validate("rsi_14", "v1")
    retrieved = feature_registry.get("rsi_14", "v1")
    assert retrieved.validation_status == "VALIDATED"
    assert retrieved.dataset_ref["dataset_id"] == "btc_daily"


# ------------------------------------------------------------------- model


def test_model_lifecycle_defined_to_promoted(model_registry, feature_registry) -> None:
    feature_registry.register(
        "rsi_14", "v1", "RSI", {"dataset_id": "d", "version": "v1"}, "code"
    )
    mv = model_registry.register(
        model_id="momentum_predictor",
        version="v1.0",
        model_type="linear_regression",
        feature_ref={"feature_id": "rsi_14", "version": "v1"},
    )
    assert mv.status.value == "DEFINED"

    model_registry.mark_trained("momentum_predictor", "v1.0", artifact_hash="artifact-abc")
    assert model_registry.get("momentum_predictor", "v1.0").status.value == "TRAINED"

    model_registry.mark_evaluated(
        "momentum_predictor", "v1.0", metrics={"sharpe": 1.8, "ic": 0.05}
    )
    retrieved = model_registry.get("momentum_predictor", "v1.0")
    assert retrieved.status.value == "EVALUATED"
    assert retrieved.evaluation_metrics["sharpe"] == 1.8


# --------------------------------------------------------------- experiment


def test_experiment_reproducibility_hash(experiment_registry) -> None:
    run1 = experiment_registry.create(
        experiment_id="exp-001",
        hypothesis_id="hyp-btc-momentum",
        strategy_version="momentum_v2",
        dataset_version="btc_daily:v1.0",
        actor_id="system",
        feature_versions=["rsi_14:v1"],
        configuration={"slippage_pct": 0.05, "balance": 100000},
        random_seed=42,
    )
    run2 = experiment_registry.create(
        experiment_id="exp-002",
        hypothesis_id="hyp-btc-momentum",
        strategy_version="momentum_v2",
        dataset_version="btc_daily:v1.0",
        actor_id="system",
        feature_versions=["rsi_14:v1"],
        configuration={"slippage_pct": 0.05, "balance": 100000},
        random_seed=42,
    )
    # Same versions + config + seed = same reproducibility hash
    assert run1.reproducibility_hash == run2.reproducibility_hash

    # Different seed = different hash
    run3 = experiment_registry.create(
        experiment_id="exp-003",
        hypothesis_id="hyp-btc-momentum",
        strategy_version="momentum_v2",
        dataset_version="btc_daily:v1.0",
        actor_id="system",
        random_seed=43,
    )
    assert run1.reproducibility_hash != run3.reproducibility_hash


def test_experiment_lifecycle(experiment_registry) -> None:
    run = experiment_registry.create(
        experiment_id="exp-lc",
        hypothesis_id="h1",
        strategy_version="s1",
        dataset_version="d1",
        actor_id="system",
    )
    assert run.status.value == "CREATED"

    experiment_registry.start("exp-lc", "system")
    assert experiment_registry.get("exp-lc").status.value == "RUNNING"

    experiment_registry.complete("exp-lc", "system", result={"sharpe": 1.7})
    completed = experiment_registry.get("exp-lc")
    assert completed.status.value == "COMPLETED"
    assert completed.result["sharpe"] == 1.7
    assert completed.completed_at != ""

    # Cannot transition from terminal state
    with pytest.raises(Exception):
        experiment_registry.start("exp-lc", "system")


def test_experiment_provenance_link(experiment_registry, kernel) -> None:
    """Hypothesis → experiment edge exists in provenance graph."""
    # Create a hypothesis node first
    kernel.provenance.add_node("hyp-test-1", NodeType.HYPOTHESIS, label="test hypothesis")

    run = experiment_registry.create(
        experiment_id="exp-prov",
        hypothesis_id="hyp-test-1",
        strategy_version="s1",
        dataset_version="d1",
        actor_id="system",
    )

    chain = kernel.provenance.full_chain("exp-prov")
    assert chain["node"]["node_type"] == NodeType.EXPERIMENT
    upstream_ids = [n["node_id"] for n in chain["upstream"]]
    assert "hyp-test-1" in upstream_ids
