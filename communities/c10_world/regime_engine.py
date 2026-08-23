"""Community 10: regime engine v0 - deterministic trend/volatility labeling.

Labels per symbol over a rolling window:
- trend: EMA(8) slope vs threshold
- vol_regime: realized stdev of bar returns vs fixed bands

Regime flips publish REGIME_CHANGED; StrategyAgent scales sizing by vol regime.
"""

import math
from collections import deque
from datetime import datetime

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import MarketDataPayload, RegimeState, TrendLabel, VolRegime


class RegimeEngine:
    """Maintains rolling history and publishes regime transitions."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        window_bars: int = 20,
        ema_span: int = 8,
        trend_slope_threshold_pct: float = 0.05,
        high_vol_pct: float = 1.5,
        low_vol_pct: float = 0.4,
    ) -> None:
        self.event_bus = event_bus
        self.window_bars = window_bars
        self.ema_alpha = 2.0 / (ema_span + 1)
        self.trend_slope_threshold_pct = trend_slope_threshold_pct
        self.high_vol_pct = high_vol_pct
        self.low_vol_pct = low_vol_pct
        self._closes: dict[str, deque[float]] = {}
        self._ema: dict[str, float | None] = {}
        self._current: dict[str, RegimeState] = {}

    def _assess(self, symbol: str, ts: datetime, is_simulated: bool) -> RegimeState:
        closes = self._closes[symbol]
        returns_pct = [
            (b - a) / a * 100.0 for a, b in zip(list(closes), list(closes)[1:], strict=False)
        ]
        realized_vol = statistics_stdev(returns_pct) if len(returns_pct) >= 2 else 0.0

        last = closes[-1]
        prev_ema = self._ema.get(symbol)
        ema = last if prev_ema is None else prev_ema + self.ema_alpha * (last - prev_ema)
        self._ema[symbol] = ema
        slope_pct = (last - ema) / ema * 100.0 if ema else 0.0

        if slope_pct > self.trend_slope_threshold_pct:
            trend = TrendLabel.UP
        elif slope_pct < -self.trend_slope_threshold_pct:
            trend = TrendLabel.DOWN
        else:
            trend = TrendLabel.FLAT

        if realized_vol >= self.high_vol_pct:
            vol_regime = VolRegime.HIGH
        elif realized_vol <= self.low_vol_pct:
            vol_regime = VolRegime.LOW
        else:
            vol_regime = VolRegime.NORMAL

        return RegimeState(
            symbol=symbol,
            trend=trend,
            vol_regime=vol_regime,
            realized_vol_pct=round(realized_vol, 4),
            ema_slope_pct=round(slope_pct, 4),
            assessed_at=ts,
            window_bars=len(closes),
            is_simulated=is_simulated,
        )

    async def on_data_acquired(self, payload: MarketDataPayload) -> RegimeState | None:
        closes = self._closes.setdefault(payload.symbol, deque(maxlen=self.window_bars))
        closes.append(payload.price_data.close)
        if len(closes) < 5:
            return None  # not enough evidence yet - honest no-label state

        state = self._assess(payload.symbol, payload.timestamp, payload.is_simulated)
        previous = self._current.get(payload.symbol)
        changed = previous is None or (
            previous.trend != state.trend or previous.vol_regime != state.vol_regime
        )
        if changed and previous is not None:
            await self.event_bus.publish(EventTopic.REGIME_CHANGED, state)
        self._current[payload.symbol] = state
        return state

    def current(self, symbol: str) -> RegimeState | None:
        return self._current.get(symbol)


def statistics_stdev(values: list[float]) -> float:
    """Population-free sample stdev without external deps."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)
