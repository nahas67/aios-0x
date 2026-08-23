"""Data-quality machinery: symbol health registry + anomaly detection (Directive 9).

Quality states: LIVE | FRESH | AGING | STALE | EXPIRED | UNKNOWN | CORRUPTED.
Anomalies publish DataAnomalyAlert payloads; alerts with freezes_symbol=True
must pause strategy generation for that symbol until clean data re-arrives.
"""

from collections import deque
from typing import Literal

from schemas.contracts import (
    DataAnomalyAlert,
    EvidencePack,
    MarketDataPayload,
)

QualityState = Literal["LIVE", "FRESH", "AGING", "STALE", "EXPIRED", "UNKNOWN", "CORRUPTED"]

_FREEZING_STATES = frozenset({"STALE", "EXPIRED", "CORRUPTED"})

_GAP_PCT_THRESHOLD = 15.0  # Doc 02: >15% one-bar jump without news is anomalous
_VOLUME_SPIKE_MULTIPLE = 8.0


class SymbolHealthRegistry:
    """Tracks quality state per symbol; freezing states gate strategy generation."""

    def __init__(self) -> None:
        self._states: dict[str, QualityState] = {}

    def set_state(self, symbol: str, state: QualityState) -> bool:
        """Update state; returns True when this call changed freeze status."""
        previous = self._states.get(symbol)
        self._states[symbol] = state
        was_frozen = previous in _FREEZING_STATES
        now_frozen = state in _FREEZING_STATES
        return was_frozen != now_frozen

    def apply_alert(self, alert: DataAnomalyAlert) -> None:
        if alert.freezes_symbol:
            state: QualityState = "CORRUPTED" if alert.anomaly_type == "OHLC_INVALID" else "STALE"
            self.set_state(alert.symbol, state)

    def apply_payload(self, payload: MarketDataPayload) -> None:
        """Clean arrivals restore health based on provenance quality."""
        state: QualityState = "UNKNOWN"
        if payload.provenance is not None:
            state = payload.provenance.quality_state
        if payload.is_simulated:
            state = "FRESH"
        self._states[payload.symbol] = state

    def is_frozen(self, symbol: str) -> bool:
        return self._states.get(symbol, "UNKNOWN") in _FREEZING_STATES

    def state_of(self, symbol: str) -> QualityState:
        return self._states.get(symbol, "UNKNOWN")


class AnomalyDetector:
    """Stateful detector over the DATA_ACQUIRED stream.

    Checks per Doc 02/Directive 9:
    - OHLC validity (high/low consistency)
    - one-bar price gaps beyond threshold
    - volume spikes vs rolling median
    Emits alerts for violations; caller publishes them on DATA_ANOMALY.
    """

    def __init__(
        self,
        gap_pct_threshold: float = _GAP_PCT_THRESHOLD,
        volume_spike_multiple: float = _VOLUME_SPIKE_MULTIPLE,
        history_bars: int = 20,
    ) -> None:
        self.gap_pct_threshold = gap_pct_threshold
        self.volume_spike_multiple = volume_spike_multiple
        self.history_bars = history_bars
        self._last_close: dict[str, float] = {}
        self._volume_history: dict[str, deque[float]] = {}

    def ingest(self, payload: MarketDataPayload) -> list[DataAnomalyAlert]:
        """Validate one arrival; returns alerts to publish (possibly empty)."""
        alerts: list[DataAnomalyAlert] = []
        price = payload.price_data
        symbol = payload.symbol
        simulated = payload.is_simulated

        # OHLC validity
        if not (
            price.high >= price.low
            and price.high >= max(price.open, price.close)
            and price.low <= min(price.open, price.close)
        ):
            alerts.append(
                DataAnomalyAlert(
                    symbol=symbol,
                    anomaly_type="OHLC_INVALID",
                    severity="CRITICAL",
                    detail="Inconsistent OHLC relationships in incoming bar",
                    observed_value=price.high,
                    reference_value=price.low,
                    freezes_symbol=True,
                    is_simulated=simulated,
                )
            )
            return alerts  # corrupt bar: no further checks make sense

        # Price gap vs previous close
        last = self._last_close.get(symbol)
        if last is not None and last > 0:
            gap_pct = abs(price.open - last) / last * 100.0
            if gap_pct > self.gap_pct_threshold:
                alerts.append(
                    DataAnomalyAlert(
                        symbol=symbol,
                        anomaly_type="PRICE_GAP",
                        severity="CRITICAL",
                        detail=f"Bar-open gap {gap_pct:.2f}% exceeds {self.gap_pct_threshold:.1f}% threshold",
                        observed_value=round(gap_pct, 4),
                        reference_value=last,
                        freezes_symbol=True,
                        is_simulated=simulated,
                    )
                )

        # Volume spike vs rolling median
        history = self._volume_history.setdefault(symbol, deque(maxlen=self.history_bars))
        if len(history) >= 5:
            ordered = sorted(history)
            mid = len(ordered) // 2
            median_volume = (
                ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
            )
            if median_volume > 0 and price.volume > median_volume * self.volume_spike_multiple:
                alerts.append(
                    DataAnomalyAlert(
                        symbol=symbol,
                        anomaly_type="VOLUME_SPIKE",
                        severity="WARNING",
                        detail=(
                            f"Volume {price.volume:g} exceeds {self.volume_spike_multiple:g}x "
                            f"rolling median ({median_volume:g})"
                        ),
                        observed_value=price.volume,
                        reference_value=median_volume,
                        freezes_symbol=False,
                        is_simulated=simulated,
                    )
                )

        # Bookkeeping AFTER checks so each bar compares against its true predecessor
        history.append(price.volume)
        self._last_close[symbol] = price.close
        return alerts


def evidence_quality_ok(pack: EvidencePack) -> bool:
    """Cheap sanity check used before grounding verification on an EvidencePack."""
    return pack.high >= pack.low and pack.close > 0 and pack.volume >= 0
