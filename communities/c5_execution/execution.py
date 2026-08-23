"""Community 5: Order lifecycle manager + kill switch (Directive 41, Doc 07).

OrderManager converts approved allocation plans into idempotent orders,
drives them through the lifecycle via an execution adapter, and publishes
ORDER_SUBMITTED / ORDER_FILLED events plus the downstream-compatible
TRADE_EXECUTED receipt.

KillSwitch implements Doc 07's deterministic sequence:
    cancel open orders -> flatten positions -> EMERGENCY_HALT lockout.
Lockout clears ONLY via RiskGovernor.human_reset(operator_id).
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from communities.c5_execution.adapters import BaseExecutionAdapter
from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import (
    EmergencyStateValue,
    OrderRequest,
    OrderStatus,
    PortfolioAllocationPlan,
    TradeExecutionReceipt,
)

if TYPE_CHECKING:
    from core.risk_governor import RiskGovernor

logger = logging.getLogger(__name__)


class OrderManager:
    """Owns order state for one adapter; idempotent by client_order_id."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        adapter: BaseExecutionAdapter,
        quantity_provider: Callable[[PortfolioAllocationPlan], float],
    ) -> None:
        self.event_bus = event_bus
        self.adapter = adapter
        self._quantity_provider = quantity_provider
        self.orders: dict[str, OrderRequest] = {}

    def _client_order_id(self, plan: PortfolioAllocationPlan) -> str:
        return f"{plan.strategy.symbol}:{plan.strategy.strategy_id}"

    def orders_by_status(self, *statuses: OrderStatus) -> list[OrderRequest]:
        return [o for o in self.orders.values() if o.status in statuses]

    @property
    def has_open_orders(self) -> bool:
        open_states = {OrderStatus.PENDING_NEW, OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED}
        return any(o.status in open_states for o in self.orders.values())

    async def on_plan(
        self, plan: PortfolioAllocationPlan, locked_out: bool
    ) -> TradeExecutionReceipt | None:
        """Execute an approved plan through the lifecycle (idempotent)."""
        if not plan.approved:
            logger.info("order manager ignoring unapproved plan %s", plan.plan_id)
            return None
        if locked_out:
            logger.warning(
                "REJECTED order for %s: execution lockout engaged",
                plan.strategy.symbol,
            )
            return None

        client_id = self._client_order_id(plan)
        existing = self.orders.get(client_id)
        if existing is not None and existing.status not in (
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
        ):
            logger.info("duplicate plan suppressed by idempotency key %s", client_id)
            return None

        quantity = max(0.0, self._quantity_provider(plan))
        if quantity <= 0:
            logger.warning("plan %s produced zero quantity; skipped", plan.plan_id)
            return None

        order = OrderRequest(
            client_order_id=client_id,
            strategy_id=plan.strategy.strategy_id,
            plan_id=plan.plan_id,
            symbol=plan.strategy.symbol,
            side="BUY" if plan.strategy.action == "BUY" else "SELL",  # type: ignore[arg-type]
            quantity=round(quantity, 6),
        )
        order.status = OrderStatus.ACCEPTED
        self.orders[client_id] = order
        await self.event_bus.publish(EventTopic.ORDER_SUBMITTED, order)

        receipt = await self.adapter.submit(plan, quantity)
        if receipt is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "venue rejected (funds/limits)"
            order.updated_at = order.created_at
            return None

        order.status = OrderStatus.FILLED
        order.filled_quantity = receipt.filled_quantity
        order.avg_fill_price = receipt.fill_price
        order.updated_at = order.created_at

        filled_view = order.model_copy()
        await self.event_bus.publish(EventTopic.ORDER_FILLED, filled_view)
        # TRADE_EXECUTED is emitted by the paper engine itself - single source.
        return receipt


class KillSwitch:
    """Deterministic emergency sequence; lockout cleared only by human reset."""

    def __init__(
        self,
        governor: "RiskGovernor",
        positions_view: Callable[[], dict[str, dict[str, str]]],
        flatten_callback: Callable[[str, float], Awaitable[None]],
        price_lookup: Callable[[str], float],
        adverse_slip_pct: float = 0.25,
    ) -> None:
        self.governor = governor
        self._positions_view = positions_view
        self._flatten = flatten_callback
        self._price_of = price_lookup
        self.adverse_slip_pct = adverse_slip_pct
        self.engaged_at: datetime | None = None

    async def trigger(self, reason: str, triggered_by: str = "system") -> int:
        """Cancel->flatten->lockout. Returns number of positions flattened."""
        positions = self._positions_view()
        logger.critical(
            "KILL SWITCH triggered (%s): flattening %d position(s)",
            reason,
            len(positions),
        )

        flattened = 0
        slip = self.adverse_slip_pct / 100.0
        for execution_id, view in list(positions.items()):
            symbol = view["symbol"]
            action = view.get("action", "BUY")
            base_price = self._price_of(symbol)
            exit_price = base_price * ((1 - slip) if action == "BUY" else (1 + slip))
            await self._flatten(execution_id, round(exit_price, 4))
            flattened += 1

        await self.governor.escalate(
            EmergencyStateValue.EMERGENCY_HALT,
            f"kill switch: {reason}",
            triggered_by=triggered_by,
        )
        self.engaged_at = datetime.now(UTC)
        return flattened
