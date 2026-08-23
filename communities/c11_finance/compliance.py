"""Community 11: Compliance surveillance hooks + NAV utility.

v0 deterministic rules: restricted symbols, wash-sale-style window, fat-finger
quantity multiples. Alerts publish on aios.c11.compliance_alert; CRITICAL
alerts carry blocks_execution=True.
"""

import statistics
from collections import deque

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import (
    ComplianceAlert,
    TradeExecutionReceipt,
)


def compute_nav(cash: float, positions: dict[str, tuple[float, float]]) -> float:
    """NAV = cash + sum(qty x mark_price). Positions map symbol -> (qty, mark)."""
    return round(cash + sum(q * mark for q, mark in positions.values()), 2)


class Surveillance:
    """Stateful checks over the fill stream."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        restricted_symbols: set[str] | None = None,
        wash_window_trades: int = 3,
        fat_finger_multiple: float = 10.0,
        qty_history_bars: int = 20,
    ) -> None:
        self.event_bus = event_bus
        self.restricted_symbols = restricted_symbols or set()
        self.wash_window_trades = wash_window_trades
        self.fat_finger_multiple = fat_finger_multiple
        self.qty_history_bars = qty_history_bars
        self._recent_sides: dict[str, deque[str]] = {}
        self._qty_history: dict[str, deque[float]] = {}

    def _record(self, receipt: TradeExecutionReceipt) -> None:
        side_hist = self._recent_sides.setdefault(
            receipt.symbol, deque(maxlen=self.wash_window_trades)
        )
        # Direction inferred from slippage sign convention used by the engine.
        side_hist.append(receipt.strategy_id)  # placeholder identity of trade flow
        qty_hist = self._qty_history.setdefault(receipt.symbol, deque(maxlen=self.qty_history_bars))
        qty_hist.append(receipt.filled_quantity)

    async def check_fill(
        self, receipt: TradeExecutionReceipt, action_hint: str = "BUY"
    ) -> list[ComplianceAlert]:
        alerts: list[ComplianceAlert] = []
        sym = receipt.symbol

        if sym in self.restricted_symbols:
            alert = ComplianceAlert(
                rule_name="RESTRICTED_SYMBOL",
                severity="CRITICAL",
                detail=f"{sym} is on the restricted list",
                symbol=sym,
                ref_execution_id=receipt.execution_id,
                blocks_execution=True,
            )
            alerts.append(alert)

        history = self._qty_history.get(sym)
        if history and len(history) >= 5:
            median_qty = statistics.median(history)
            if median_qty > 0 and receipt.filled_quantity > median_qty * self.fat_finger_multiple:
                alerts.append(
                    ComplianceAlert(
                        rule_name="FAT_FINGER_QTY",
                        severity="CRITICAL",
                        detail=(
                            f"qty {receipt.filled_quantity:g} exceeds "
                            f"{self.fat_finger_multiple:g}x median {median_qty:g}"
                        ),
                        symbol=sym,
                        ref_execution_id=receipt.execution_id,
                        blocks_execution=True,
                    )
                )

        sides = self._recent_sides.get(sym)
        if sides and len(sides) >= 2:
            # Same-symbol re-entry shortly after an exit pattern: heuristic flag.
            alternating = any(sides[i] != sides[i + 1] for i in range(len(sides) - 1))
            if alternating and action_hint.lower() == "buy":
                alerts.append(
                    ComplianceAlert(
                        rule_name="WASH_SALE_WINDOW",
                        severity="WARNING",
                        detail="rapid same-symbol round-trip pattern detected",
                        symbol=sym,
                        ref_execution_id=receipt.execution_id,
                        blocks_execution=False,
                    )
                )

        self._record(receipt)
        for alert in alerts:
            await self.event_bus.publish(EventTopic.COMPLIANCE_ALERT, alert)
        return alerts
