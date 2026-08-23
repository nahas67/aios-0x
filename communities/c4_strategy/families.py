"""Community 4: Strategy families - independent candidate generators.

Each family encodes a distinct, deterministic edge hypothesis:
- MomentumFamily: continuation of directional pressure with sentiment agreement.
- MeanReversionFamily: fade statistically extreme one-bar moves (Bollinger-style z-score).

Families return raw candidates (action + geometry); selection/ranking is the
OpportunityEngine's job, gating is C9's job. NO TRADE remains a valid output
of every family.
"""

import math
from collections import deque
from dataclasses import dataclass

from schemas.contracts import MarketDataPayload


@dataclass(frozen=True)
class FamilyCandidate:
    """Raw proposal before contract validation."""

    family: str
    action: str  # BUY | SELL only (HOLD = no candidate)
    entry_price: float
    stop_distance_pct: float
    risk_reward_ratio: float

    def stop_price(self) -> float:
        if self.action == "BUY":
            return round(self.entry_price * (1 - self.stop_distance_pct / 100.0), 4)
        return round(self.entry_price * (1 + self.stop_distance_pct / 100.0), 4)

    def take_profit_price(self) -> float:
        target = self.stop_distance_pct * self.risk_reward_ratio
        if self.action == "BUY":
            return round(self.entry_price * (1 + target / 100.0), 4)
        return round(self.entry_price * (1 - target / 100.0), 4)


class StrategyFamily:
    """Base class for candidate-generating families."""

    name: str = "base"

    def evaluate(
        self,
        symbol: str,
        payload: MarketDataPayload,
        close_history: deque[float],
        sentiment_avg: float,
    ) -> FamilyCandidate | None:
        raise NotImplementedError


class MomentumFamily(StrategyFamily):
    """Directional continuation when momentum and sentiment agree.

    Geometry mirrors the pre-Phase-4 baseline: stop = half the realized bar
    range (clamped), target = stop x hypothesis R:R (passed via rr).
    """

    name = "momentum"

    def __init__(
        self,
        max_stop_distance_pct: float,
        min_stop_distance_pct: float = 0.5,
        stop_fraction_of_range: float = 0.5,
    ) -> None:
        self.max_stop_distance_pct = max_stop_distance_pct * 0.8
        self.min_stop_distance_pct = min_stop_distance_pct
        self.stop_fraction_of_range = stop_fraction_of_range

    def evaluate(
        self,
        symbol: str,
        payload: MarketDataPayload,
        close_history: deque[float],
        sentiment_avg: float,
    ) -> FamilyCandidate | None:
        price = payload.price_data
        momentum_pct = (price.close - price.open) / price.open * 100.0

        if momentum_pct > 0 and sentiment_avg >= 0:
            action = "BUY"
        elif momentum_pct < 0 and sentiment_avg <= 0:
            action = "SELL"
        else:
            return None

        bar_range_pct = (price.high - price.low) / price.open * 100.0
        stop_distance = min(
            max(bar_range_pct * self.stop_fraction_of_range, self.min_stop_distance_pct),
            self.max_stop_distance_pct,
        )
        return FamilyCandidate(
            family=self.name,
            action=action,
            entry_price=price.close,
            stop_distance_pct=round(stop_distance, 4),
            risk_reward_ratio=2.0,
        )


class MeanReversionFamily(StrategyFamily):
    """Fade extreme moves: |return| > k x rolling stdev against the move.

    Requires at least ``min_history`` closes. Direction opposes the outlier;
    sentiment disagreement strengthens (but is not required for) the signal.
    """

    name = "mean_reversion"

    def __init__(
        self,
        zscore_threshold: float = 2.0,
        min_history: int = 10,
        base_stop_pct: float = 1.5,
        rr: float = 1.6,
    ) -> None:
        self.zscore_threshold = zscore_threshold
        self.min_history = min_history
        self.base_stop_pct = base_stop_pct
        self.rr = rr

    def _rolling_stats(self, history: deque[float]) -> tuple[float, float] | None:
        values = list(history)[: len(history) - 1]  # stats exclude the current bar
        if len(values) < self.min_history:
            return None
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        std = math.sqrt(variance)
        if std <= 0:
            return None
        return mean, std

    def evaluate(
        self,
        symbol: str,
        payload: MarketDataPayload,
        close_history: deque[float],
        sentiment_avg: float,
    ) -> FamilyCandidate | None:
        stats = self._rolling_stats(close_history)
        if stats is None:
            return None
        mean, std = stats
        last = close_history[-1]
        prev_mean = list(close_history)[-2] if len(close_history) >= 2 else last
        ret_pct = (last - prev_mean) / prev_mean * 100.0
        z = (last - mean) / std

        vol_stop = max(self.base_stop_pct, abs(ret_pct) * 0.75)

        # Oversold bounce: sharp down-move stretched below mean
        if z < -self.zscore_threshold and ret_pct < 0:
            return FamilyCandidate(
                family=self.name,
                action="BUY",
                entry_price=payload.price_data.close,
                stop_distance_pct=round(vol_stop, 4),
                risk_reward_ratio=self.rr,
            )
        # Overbought fade: sharp up-move stretched above mean AND sentiment not supportive
        if z > self.zscore_threshold and ret_pct > 0 and sentiment_avg <= 0:
            return FamilyCandidate(
                family=self.name,
                action="SELL",
                entry_price=payload.price_data.close,
                stop_distance_pct=round(vol_stop, 4),
                risk_reward_ratio=self.rr,
            )
        return None


DEFAULT_FAMILIES: tuple[StrategyFamily, ...] = (
    MomentumFamily(max_stop_distance_pct=6.25),
    MeanReversionFamily(),
)
