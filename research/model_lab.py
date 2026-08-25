"""Model Lab: stdlib-only model lifecycle (original architecture §12).

Definition → Training → Artifact(hash) → Evaluation(walk-forward) → Version.

The first real model: a tiny logistic regression predicting next-bar direction
from OHLCV-derived features. Pure Python, deterministic, no dependencies —
small enough to audit line by line, honest enough to walk forward:

    for each bar t >= train_min:
        fit on bars [0, t)          # everything STRICTLY before t
        predict direction of bar t  # the label closes[t] vs closes[t-1]

No future information ever touches a prediction. The trained artifact is
hash-addressable; evaluation metrics come from the walk-forward loop only —
never in-sample fit statistics.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field

_FEATURE_RETURNS = (1, 2, 3, 5)
_FEATURE_VOL_WINDOWS = (5, 10)
_MIN_TRAIN_BARS = 60


@dataclass
class LogRegModel:
    """Batch-GD logistic regression with L2 + internal feature standardization.

    Features are raw returns/vol ratios (~1e-3 scale); without standardization
    gradients vanish and the model outputs a constant 0.5. fit() stores
    per-feature mean/std; predict_proba applies THE SAME stats — both are part
    of the hash-addressable artifact.
    """

    weights: list[float] = field(default_factory=list)
    bias: float = 0.0
    mean: list[float] = field(default_factory=list)
    std: list[float] = field(default_factory=list)
    lr: float = 0.1
    epochs: int = 300
    l2: float = 1e-3

    @staticmethod
    def _sigmoid(z: float) -> float:
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def _standardize(self, row: list[float]) -> list[float]:
        return [
            (x - m) / s if s > 1e-12 else 0.0
            for x, m, s in zip(row, self.mean, self.std, strict=True)
        ]

    def fit(self, X: list[list[float]], y: list[int]) -> None:
        n_features = len(X[0])
        n = len(X)
        self.mean = [sum(col) / n for col in zip(*X, strict=True)]
        self.std = [
            math.sqrt(sum((row[j] - self.mean[j]) ** 2 for row in X) / n)
            for j in range(n_features)
        ]
        Z = [self._standardize(row) for row in X]
        self.weights = [0.0] * n_features
        self.bias = 0.0
        for _ in range(self.epochs):
            grad_w = [0.0] * n_features
            grad_b = 0.0
            for row, label in zip(Z, y, strict=True):
                pred = self._sigmoid(
                    self.bias + sum(w * x for w, x in zip(self.weights, row, strict=True))
                )
                err = pred - label
                grad_b += err
                for j, x in enumerate(row):
                    grad_w[j] += err * x
            self.bias -= self.lr * grad_b / n
            for j in range(n_features):
                self.weights[j] -= self.lr * (grad_w[j] / n + self.l2 * self.weights[j])

    def predict_proba(self, row: list[float]) -> float:
        z_row = self._standardize(row)
        return self._sigmoid(
            self.bias + sum(w * x for w, x in zip(self.weights, z_row, strict=True))
        )

    def artifact_hash(self) -> str:
        canonical = json.dumps(
            {"w": self.weights, "b": self.bias, "m": self.mean, "s": self.std},
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


def _feature_row(window: list[float]) -> list[float]:
    """Feature vector for the MOST RECENT bar of `window` (causal formulas)."""
    last = window[-1]
    feats: list[float] = []
    for k in _FEATURE_RETURNS:
        base = window[-1 - k]
        feats.append((last - base) / base if base else 0.0)
    for w in _FEATURE_VOL_WINDOWS:
        rets = [
            (window[j] - window[j - 1]) / window[j - 1]
            for j in range(len(window) - w, len(window))
            if window[j - 1]
        ]
        mean = sum(rets) / len(rets) if rets else 0.0
        var = sum((r - mean) ** 2 for r in rets) / len(rets) if rets else 0.0
        feats.append(math.sqrt(var))
    sma_fast = sum(window[-5:]) / 5
    sma_slow = sum(window[-10:]) / min(10, len(window))
    feats.append(last / sma_fast - 1.0 if sma_fast else 0.0)
    feats.append(last / sma_slow - 1.0 if sma_slow else 0.0)
    return feats


def min_bars_required() -> int:
    """Bars needed before one trainable feature row exists."""
    return max(*_FEATURE_RETURNS, *_FEATURE_VOL_WINDOWS)


def build_features(closes: list[float]) -> tuple[list[list[float]], list[int], list[int]]:
    """Feature rows + labels + the bar index each row predicts.

    Row i uses ONLY closes up to and including index i (window ends at i);
    its label is the direction of close[i+1] vs close[i]. Alignment is
    strict: the label bar never contributes to its own features.
    """
    max_lookback = max(*_FEATURE_RETURNS, *_FEATURE_VOL_WINDOWS)
    X: list[list[float]] = []
    y: list[int] = []
    predict_at: list[int] = []
    for i in range(max_lookback - 1, len(closes) - 1):
        X.append(_feature_row(closes[: i + 1]))
        y.append(1 if closes[i + 1] > closes[i] else 0)
        predict_at.append(i + 1)
    return X, y, predict_at


def features_for_latest(closes: list[float]) -> list[float] | None:
    """Inference row for the most recent bar; None when history too short.

    This is the row a LIVE decision would use at bar t to bet on bar t+1 —
    identical formulas to training rows, no label required.
    """
    max_lookback = max(*_FEATURE_RETURNS, *_FEATURE_VOL_WINDOWS)
    if len(closes) < max_lookback:
        return None
    return _feature_row(closes)


def walk_forward_evaluate(closes: list[float], train_min: int = _MIN_TRAIN_BARS) -> dict[str, float]:
    """Expanding-window honesty check: fit on past, predict next bar."""
    X, y, _ = build_features(closes)
    n_predictions = max(0, len(y) - train_min)
    if n_predictions <= 0:
        return {"n_predictions": 0.0, "accuracy_pct": 0.0, "brier": 0.0}

    correct = 0
    brier_total = 0.0
    for t in range(train_min, len(y)):
        model = LogRegModel(epochs=120)
        model.fit(X[:t], y[:t])
        proba = model.predict_proba(X[t])
        predicted_up = proba >= 0.5
        if predicted_up == (y[t] == 1):
            correct += 1
        brier_total += (proba - y[t]) ** 2

    return {
        "n_predictions": float(n_predictions),
        "accuracy_pct": round(correct / n_predictions * 100.0, 2),
        "brier": round(brier_total / n_predictions, 4),
    }


def train_pooled(series_by_symbol: dict[str, list[float]]) -> dict[str, object]:
    """Train one pooled model across all symbols; evaluate walk-forward per symbol.

    Returns the registry payload: artifact hash + honest metrics.
    """
    X_all: list[list[float]] = []
    y_all: list[int] = []
    per_symbol_eval: dict[str, dict[str, float]] = {}
    for symbol, closes in sorted(series_by_symbol.items()):
        if len(closes) > _MIN_TRAIN_BARS + 2:
            per_symbol_eval[symbol] = walk_forward_evaluate(closes)
        X_sym, y_sym, _ = build_features(closes)
        X_all.extend(X_sym)
        y_all.extend(y_sym)

    if not X_all:
        return {"trained": False}
    final = LogRegModel()
    final.fit(X_all, y_all)
    total_preds = sum(m["n_predictions"] for m in per_symbol_eval.values())
    accuracy = (
        sum(m["accuracy_pct"] * m["n_predictions"] for m in per_symbol_eval.values())
        / total_preds
        if total_preds
        else 0.0
    )
    brier = (
        sum(m["brier"] * m["n_predictions"] for m in per_symbol_eval.values()) / total_preds
        if total_preds
        else 0.0
    )
    return {
        "trained": True,
        "artifact_hash": final.artifact_hash(),
        "metrics": {
            "wf_accuracy_pct": round(accuracy, 2),
            "wf_brier": round(brier, 4),
            "wf_n_predictions": float(total_preds),
            "samples_fit": float(len(X_all)),
            "symbols": float(len(per_symbol_eval)),
        },
        "per_symbol": per_symbol_eval,
    }
