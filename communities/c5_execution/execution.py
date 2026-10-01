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
from typing import TYPE_CHECKING, Any

from communities.c5_execution.adapters import BaseExecutionAdapter
from communities.c5_execution.oms import DurableOrderManager
from core.event_bus import BaseEventBus, EventTopic
from core.financial_kernel import DurableOrder, Fill
from core.trace import new_trace_id
from schemas.contracts import (
    EmergencyStateValue,
    OrderRequest,
    OrderStatus,
    PortfolioAllocationPlan,
    TradeExecutionReceipt,
)

if TYPE_CHECKING:
    from core.risk_governor import RiskGovernor
    from core.safety_plane import LockoutDecision, SafetyPlane

logger = logging.getLogger(__name__)


class OrderManager:
    """Owns order state for one adapter; idempotent by client_order_id.

    When a :class:`DurableOrderManager` is injected the order is written
    **before** it reaches a venue (write-ahead OMS, spec §23) and the resulting
    execution is applied to durable state exactly once. The in-memory mirror is
    kept for the read-only API and the control plane, but it is no longer the
    only record of what is live.
    """

    def __init__(
        self,
        event_bus: BaseEventBus,
        adapter: BaseExecutionAdapter,
        quantity_provider: Callable[[PortfolioAllocationPlan], float],
        durable: DurableOrderManager | None = None,
        # Quoted because SafetyPlane is a TYPE_CHECKING-only import. On Python
        # <=3.13 an unquoted annotation here is evaluated at definition time and
        # raises NameError, so the module cannot be imported at all. Python 3.14
        # made annotations lazy by default (PEP 649), which hid the bug in the
        # local venv while the Docker image and CI both run 3.12. pyproject
        # declares requires-python >=3.11, so 3.12 is in scope.
        safety: "SafetyPlane | None" = None,
    ) -> None:
        self.event_bus = event_bus
        self.adapter = adapter
        self._quantity_provider = quantity_provider
        self._durable = durable
        self._safety = safety
        self.orders: dict[str, OrderRequest] = {}

    # Quoted for the same reason as `safety` above: LockoutDecision is imported
    # under TYPE_CHECKING only, and an unquoted return annotation raises
    # NameError on Python <=3.13.
    def safety_decision(self, plan: PortfolioAllocationPlan) -> "LockoutDecision | None":
        """Durable safety-plane verdict for this plan's account/venue/strategy.

        The in-memory ``RiskGovernor`` lockout is a *separate* control that lives
        only in this process. The safety plane reads restrictions from the
        financial store, so a CRITICAL reconciliation discrepancy survives a
        restart and still blocks the order. Consulted immediately before the
        venue call, which is the last moment at which blocking is free.
        """
        if self._safety is None:
            return None
        return self._safety.is_blocked(
            broker=getattr(self.adapter, "venue", None),
            strategy_id=plan.strategy.strategy_id,
        )

    def _safety_block_reason(self, plan: PortfolioAllocationPlan) -> str | None:
        decision = self.safety_decision(plan)
        if decision is None or not decision.blocked:
            return None
        return "; ".join(decision.reasons) or "safety lockout engaged"

    def _client_order_id(self, plan: PortfolioAllocationPlan) -> str:
        return f"{plan.strategy.symbol}:{plan.strategy.strategy_id}"

    def orders_by_status(self, *statuses: OrderStatus) -> list[OrderRequest]:
        return [o for o in self.orders.values() if o.status in statuses]

    @property
    def has_open_orders(self) -> bool:
        open_states = {OrderStatus.PENDING_NEW, OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED}
        return any(o.status in open_states for o in self.orders.values())

    async def on_plan(
        self,
        plan: PortfolioAllocationPlan,
        locked_out: bool,
        *,
        envelope: Any | None = None,
        instrument_id: str | None = None,
        mic: str | None = None,
        strategy_version: str | None = None,
        timings: Any = (),
        survivorship: Any | None = None,
        trace_id: str | None = None,
    ) -> TradeExecutionReceipt | None:
        """Execute an approved plan through the lifecycle (idempotent).

        The firewall context (envelope plus the identity fields the verdict
        needs) travels with the plan from here to the venue: the OMS demands
        the verdict before persisting, and the adapter re-checks the envelope
        scope before contacting the venue. Omit it and a firewall-bound
        deployment refuses at both boundaries; a deployment without a
        firewall behaves exactly as before.
        """
        if not plan.approved:
            logger.info("order manager ignoring unapproved plan %s", plan.plan_id)
            return None
        if locked_out:
            logger.warning(
                "REJECTED order for %s: execution lockout engaged",
                plan.strategy.symbol,
            )
            return None
        block_reason = self._safety_block_reason(plan)
        if block_reason is not None:
            logger.warning(
                "REJECTED order for %s: durable safety lockout (%s)",
                plan.strategy.symbol,
                block_reason,
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

        # The firewall prices notional off a reference price, which for a
        # market order is the plan's entry price rather than a limit that
        # does not exist. Passing limit_price (None on markets) would make
        # every market order unevaluable.
        # Observability is not authorization: a missing trace id mints one
        # with a logged warning rather than refusing the order. Blocking
        # orders over missing telemetry would confuse safety with telemetry,
        # and a telemetry outage would become a trading halt.
        if trace_id is None:
            trace_id = new_trace_id()
            logger.warning("no trace id supplied for plan %s; minted %s", plan.plan_id, trace_id)
        durable_order = self._write_ahead(
            order,
            envelope=envelope,
            instrument_id=instrument_id,
            mic=mic,
            price=plan.strategy.entry_price,
            strategy_version=strategy_version,
            timings=timings,
            survivorship=survivorship,
            trace_id=trace_id,
        )

        # Re-check as late as possible: a lockout engaged while this order was
        # being prepared must still stop it before the venue sees it. A suppressed
        # order is *not* left ACCEPTED - it is durably rejected with the reason.
        late_block = self._safety_block_reason(plan)
        if late_block is not None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"safety lockout: {late_block}"
            self._durable_reject(durable_order, order.reject_reason)
            logger.warning(
                "REJECTED order for %s at submit boundary: %s",
                plan.strategy.symbol,
                late_block,
            )
            return None

        try:
            receipt = await self.adapter.submit(
                plan, quantity, envelope=envelope, trace_id=trace_id
            )
        except Exception as exc:
            # A venue exception must still leave durable state consistent: an
            # order that never reached the venue can never stay "accepted".
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"adapter error: {exc}"
            self._durable_reject(durable_order, order.reject_reason)
            raise
        if receipt is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "venue rejected (funds/limits)"
            order.updated_at = order.created_at
            self._durable_reject(durable_order, "venue rejected (funds/limits)")
            return None

        order.status = OrderStatus.FILLED
        order.filled_quantity = receipt.filled_quantity
        order.avg_fill_price = receipt.fill_price
        order.updated_at = order.created_at
        self._durable_fill(durable_order, order, receipt)

        filled_view = order.model_copy()
        await self.event_bus.publish(EventTopic.ORDER_FILLED, filled_view)
        # TRADE_EXECUTED is emitted by the paper engine itself - single source.
        return receipt

    # ------------------------------------------------------- durable write path

    def _write_ahead(
        self,
        order: OrderRequest,
        *,
        envelope: Any | None = None,
        instrument_id: str | None = None,
        mic: str | None = None,
        price: float | None = None,
        strategy_version: str | None = None,
        timings: Any = (),
        survivorship: Any | None = None,
        trace_id: str | None = None,
    ) -> DurableOrder | None:
        """Persist the order before the venue sees it ("write-ahead OMS").

        The durable idempotency key is scoped to the plan, not just the
        strategy: an idempotency key identifies ONE order attempt forever, so a
        genuine retry after a rejection (a new plan) must be a new attempt,
        while a re-delivered plan stays a no-op.
        """
        if self._durable is None:
            return None
        key = order.client_order_id
        if order.plan_id:
            key = f"{key}#{order.plan_id}"
        written = self._durable.prepare_order(
            client_order_id=key,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
            limit_price=order.limit_price,
            plan_id=order.plan_id,
            envelope=envelope,
            instrument_id=instrument_id,
            mic=mic,
            price=price if price is not None else order.limit_price,
            strategy_version=strategy_version,
            timings=timings,
            survivorship=survivorship,
            trace_id=trace_id,
        )
        if written.status is not OrderStatus.PENDING_NEW:
            # Same attempt already exists in durable state: never re-drive it.
            logger.info(
                "durable OMS: attempt %s already in state %s; not resubmitting",
                key,
                written.status,
            )
            return None
        return self._durable.accept(written.internal_order_id)

    def _durable_fill(
        self,
        durable_order: DurableOrder | None,
        order: OrderRequest,
        receipt: TradeExecutionReceipt,
    ) -> None:
        if self._durable is None or durable_order is None:
            return
        # The venue is authoritative for execution facts, including sizing: the
        # durable order carries the plan estimate until the venue reports what it
        # actually did. The amendment is recorded, never silent.
        if receipt.filled_quantity > durable_order.quantity + 1e-9:
            durable_order = self._durable.store.amend_order_quantity(
                durable_order.internal_order_id,
                receipt.filled_quantity,
                actor=self._durable.actor,
                reason="venue sizing supersedes plan estimate",
            )
        self._durable.apply_fill(
            Fill(
                # The venue's execution id is the fill identity: re-delivering the
                # same callback can never double-count the position.
                fill_id=receipt.execution_id,
                order_id=durable_order.internal_order_id,
                broker_execution_id=receipt.execution_id,
                symbol=order.symbol,
                side=order.side,
                quantity=receipt.filled_quantity,
                price=receipt.fill_price,
                fee=receipt.fees,
                executed_at=receipt.executed_at,
            )
        )

    def _durable_reject(self, durable_order: DurableOrder | None, reason: str) -> None:
        if self._durable is None or durable_order is None:
            return
        self._durable.reject(durable_order.internal_order_id, reason)


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
