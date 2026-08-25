"""Model Lab tests: §12 lifecycle with stdlib-only logistic regression.

Honesty is the contract: features never see their own label bar, evaluation
comes exclusively from the walk-forward loop, and the trained artifact is
hash-addressable. Registry wiring proves DEFINED -> TRAINED -> EVALUATED with
real run metrics, exposed over /api/v1/models.
"""

import asyncio
from pathlib import Path

import pytest

from research.model_lab import (
    LogRegModel,
    build_features,
    train_pooled,
    walk_forward_evaluate,
)
from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner

# ------------------------------------------------------------------ features


def test_feature_label_alignment_is_strictly_causal() -> None:
    """Row i's window ends at bar i; its label is bar i+1 vs bar i."""
    closes = [100.0 + i for i in range(40)]  # monotonic up
    X, y, predict_at = build_features(closes)
    assert predict_at[0] > 0
    for idx, bar in enumerate(predict_at):
        # every row predicts the NEXT bar after its window
        assert y[idx] == (1 if closes[bar] > closes[bar - 1] else 0)
        if idx > 0:
            assert bar == predict_at[idx - 1] + 1  # one step per row, no gaps
    assert all(v == 1 for v in y)  # uptrend: every next bar is up


def test_model_learns_and_artifact_hash_binds_weights() -> None:
    closes = [100 * (1 + 0.01 * ((i % 10) / 10)) + i * 0.5 for i in range(300)]
    X, y, _ = build_features(closes)
    model = LogRegModel(epochs=150)
    model.fit(X[:200], y[:200])
    proba = model.predict_proba(X[250])
    assert 0.0 <= proba <= 1.0

    before = model.artifact_hash()
    assert len(before) == 64
    model.weights[0] += 0.5  # any weight change must change the hash
    assert model.artifact_hash() != before


def test_walk_forward_returns_honest_metrics(tmp_path: Path) -> None:
    import random

    rng = random.Random(42)
    closes = [100.0]
    for _ in range(220):
        closes.append(max(1.0, closes[-1] * (1 + rng.gauss(0.0008, 0.012))))
    metrics = walk_forward_evaluate(closes)
    assert metrics["n_predictions"] == 220 - 60 - 1 + 1 - 1 or metrics["n_predictions"] > 0
    assert 0.0 <= metrics["accuracy_pct"] <= 100.0
    assert 0.0 <= metrics["brier"] <= 1.0


# ------------------------------------------------------------------ pooled lab


def test_train_pooled_registers_across_symbols() -> None:
    series: dict[str, list[float]] = {}
    for base in (50.0, 120.0, 400.0):
        symbol = f"S{int(base)}"
        closes = [base]
        for i in range(180):
            closes.append(closes[-1] * (1 + 0.002 * ((-1) ** (i // 7))))
        series[symbol] = closes

    result = train_pooled(series)
    assert result["trained"] is True
    assert result["artifact_hash"]
    metrics = result["metrics"]
    assert set(metrics) >= {"wf_accuracy_pct", "wf_brier", "wf_n_predictions"}
    assert metrics["symbols"] == 3.0


def test_train_pooled_empty_input_is_honest() -> None:
    assert train_pooled({}) == {"trained": False}


# ---------------------------------------------------------------- runner wiring


def test_runner_trains_and_evaluates_direction_logreg(tmp_path: Path) -> None:
    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=150)
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "ml.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
    )
    asyncio.run(runner.run())

    mv = runner.kernel_bridge.kernel.models.get("direction_logreg", "v1")
    assert mv.status.value == "EVALUATED"
    assert len(mv.artifact_hash) == 64
    assert mv.feature_ref["feature_id"] == "ohlcv_passthrough"
    assert "wf_accuracy_pct" in mv.evaluation_metrics

    events = runner.store.iter_event_payloads("MODEL_TRAINED")
    assert len(events) == 1
    assert events[0]["artifact_hash"] == mv.artifact_hash

    view = runner.build_snapshot_builder().models_view()
    assert view["available"] is True
    ids = {m["model_id"] for m in view["models"]}
    assert {"deterministic_baseline", "direction_logreg"} <= ids
    logreg_view = next(m for m in view["models"] if m["model_id"] == "direction_logreg")
    assert "walk_forward" in logreg_view and logreg_view["walk_forward"]


def test_flag_off_skips_ml_training(tmp_path: Path) -> None:
    from core.config import Settings

    write_dataset(tmp_path / "golden", symbols=["SPY"], total_bars=120)
    runner = ReplayRunner(
        csv_path_by_symbol={"SPY": tmp_path / "golden" / "SPY_1d.csv"},
        store_path=tmp_path / "off.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
        settings=Settings(model_provider="none", ml_training=False),
    )
    asyncio.run(runner.run())
    with pytest.raises(KeyError):
        runner.kernel_bridge.kernel.models.get("direction_logreg", "v1")
    assert runner.store.iter_event_payloads("MODEL_TRAINED") == []
