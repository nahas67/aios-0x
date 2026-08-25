"""ML-driven strategy family: the trained direction model proposes candidates.

Closes the §12→§13 loop: `direction_logreg` stops being a registry entry and
starts generating FamilyCandidates as a CHALLENGER against the deterministic
families.

Honesty rules (non-negotiable):
- The family fits ONLY on closes already visible in `close_history` — the
  expanding-window discipline of the walk-forward evaluator, applied live.
- Refits happen every `retrain_interval` evaluations; inference uses the
  shared feature formulas from research.model_lab (one source of truth).
- NO TRADE is the default: candidates appear only when the model is confident
  (|proba - 0.5| >= threshold - 0.5) and geometry respects the R:R firewall.
"""

from collections import deque

from communities.c4_strategy.families import FamilyCandidate, StrategyFamily
from research.model_lab import LogRegModel, build_features, features_for_latest, min_bars_required
from schemas.contracts import MarketDataPayload


class MLDirectionFamily(StrategyFamily):
    """Next-bar direction model as a candidate generator (challenger)."""

    name = "ml_direction"

    def __init__(
        self,
        threshold: float = 0.60,
        retrain_interval: int = 20,
        rr: float = 1.8,
        min_stop_distance_pct: float = 0.6,
        max_stop_distance_pct: float = 5.0,
        epochs: int = 150,
    ) -> None:
        if not 0.5 < threshold < 1.0:
            raise ValueError("threshold must be within (0.5, 1.0)")
        self.threshold = threshold
        self.retrain_interval = max(1, retrain_interval)
        self.rr = rr
        self.min_stop = min_stop_distance_pct
        self.max_stop = max_stop_distance_pct
        self.epochs = epochs
        self._model: LogRegModel | None = None
        self._calls = 0
        self._refits = 0

    # ------------------------------------------------------------------ model

    def _maybe_refit(self, history: list[float]) -> None:
        if self._model is not None and self._calls % self.retrain_interval != 0:
            return
        X, y, _ = build_features(history)
        if len(X) < 10:  # too little signal to fit meaningfully
            return
        model = LogRegModel(epochs=self.epochs)
        model.fit(X, y)
        self._model = model
        self._refits += 1

    def _stop_distance_pct(self, history: list[float]) -> float:
        window = history[-11:]
        rets = [
            abs(window[j] - window[j - 1]) / window[j - 1]
            for j in range(1, len(window))
            if window[j - 1]
        ]
        vol_pct = (sum(rets) / len(rets) * 100.0) if rets else 1.0
        return min(self.max_stop, max(self.min_stop, 2.0 * vol_pct))

    # ------------------------------------------------------------- interface

    def evaluate(
        self,
        symbol: str,
        payload: MarketDataPayload,
        close_history: deque[float],
        sentiment_avg: float,
    ) -> FamilyCandidate | None:
        history = list(close_history)
        self._calls += 1
        if len(history) < min_bars_required() + 20:
            return None  # warm-up: no model opinion until there is real signal
        self._maybe_refit(history)
        if self._model is None:
            return None

        row = features_for_latest(history)
        if row is None:
            return None
        proba_up = self._model.predict_proba(row)

        action: str | None = None
        if proba_up >= self.threshold:
            action = "BUY"
        elif proba_up <= 1.0 - self.threshold:
            action = "SELL"
        if action is None:
            return None

        entry = payload.price_data.close
        return FamilyCandidate(
            family=self.name,
            action=action,
            entry_price=entry,
            stop_distance_pct=round(self._stop_distance_pct(history), 4),
            risk_reward_ratio=self.rr,
        )
