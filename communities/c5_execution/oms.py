"""Community 5: durable OMS — orders as persistent state machines (spec §23).

The prototype kept order state in a process-memory dict, so a restart erased the
fact that orders were live. This module makes order state durable *before*
anything reaches a venue (write-ahead), drives it through the legal state
machine with optimistic versioning, and emits every hop into the transactional
outbox in the same database transaction.

Guarantees:

- "order accepted" is never confused with "trade filled" (§23): acceptance is a
  state transition; the fill is a separate economic record applied exactly once.
- Re-submitting the same ``client_order_id`` returns the existing order instead
  of creating a second one.
- An illegal hop or a stale writer is refused by the store, not by convention.
- Every transition is published as a canonical ``aios.platform.*`` envelope with
  a deterministic idempotency key, so a publisher retry cannot duplicate it.
"""

import logging
from typing import TYPE_CHECKING

from core.financial_kernel import (
    BaseFinancialStore,
    DurableOrder,
    Fill,
    OrderTransition,
    OutboxEvent,
    TimeInForce,
)
from core.platform_events import (
    PlatformEvent,
    PlatformEventType,
    execution_completed,
    order_denied,
    order_requested,
)
from schemas.contracts import OrderSide, OrderStatus, OrderType, generate_uuid

if TYPE_CHECKING:
    from core.safety_plane import SafetyPlane

logger = logging.getLogger(__name__)

PRODUCER = "c5-execution"


class OrderBlocked(PermissionError):
    """A durable safety restriction forbids creating this order.

    Deliberately a ``PermissionError``: this is an authorization refusal, not a
    validation error, and it must not be swallowed by retry logic that treats
    ValueError as "try again".
    """


def outbox_event_from_platform(
    event: PlatformEvent,
    idempotency_key: str,
    *,
    producer: str = PRODUCER,
    actor: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> OutboxEvent:
    """Wrap a canonical platform event in the §29 outbox envelope."""
    return OutboxEvent(
        event_type=str(event.event_type),
        producer=producer,
        actor=actor or event.actor_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        payload=event.model_dump(mode="json"),
    )


class DurableOrderManager:
    """Owns durable order state for one account; the write-ahead OMS of record."""

    def __init__(
        self,
        store: BaseFinancialStore,
        *,
        account_id: str = "default",
        portfolio_id: str = "default",
        actor: str = PRODUCER,
        safety: "SafetyPlane | None" = None,
        broker: str | None = None,
    ) -> None:
        self.store = store
        self.account_id = account_id
        self.portfolio_id = portfolio_id
        self.actor = actor
        # The durable safety plane (spec §33). When present it is the last word:
        # a restricted scope cannot even *record* an order intent, so no later
        # bug in an execution path can leak one to a venue.
        self._safety = safety
        self.broker = broker

    def blocked_reasons(self, strategy_id: str) -> list[str]:
        """Active durable restrictions for this order's account/venue/strategy."""
        if self._safety is None:
            return []
        decision = self._safety.is_blocked(
            account_id=self.account_id, broker=self.broker, strategy_id=strategy_id
        )
        return list(decision.reasons) if decision.blocked else []

    def _assert_authorized(self, strategy_id: str) -> None:
        reasons = self.blocked_reasons(strategy_id)
        if reasons:
            raise OrderBlocked(
                f"order refused for account={self.account_id} strategy={strategy_id}: "
                + "; ".join(reasons)
            )

    # ------------------------------------------------------------------ writes

    def prepare_order(
        self,
        *,
        client_order_id: str,
        strategy_id: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        plan_id: str | None = None,
    ) -> DurableOrder:
        """Persist a PENDING_NEW order before any venue call (write-ahead)."""
        self._assert_authorized(strategy_id)
        order = DurableOrder(
            internal_order_id=generate_uuid(),
            client_order_id=client_order_id,
            strategy_id=strategy_id,
            portfolio_id=self.portfolio_id,
            account_id=self.account_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            status=OrderStatus.PENDING_NEW,
        )
        event = outbox_event_from_platform(
            order_requested(
                plan_id or client_order_id, strategy_id, str(side), symbol
            ),
            f"order:{client_order_id}:requested",
            producer=self.actor,
        )
        stored = self.store.submit_order(order, (event,))
        if stored.internal_order_id != order.internal_order_id:
            logger.info(
                "durable OMS: client_order_id %s already persisted; reusing order",
                client_order_id,
            )
        return stored

    def accept(
        self,
        order_id: str,
        *,
        broker_order_id: str | None = None,
        expected_version: int | None = None,
    ) -> DurableOrder:
        """Venue acknowledged the order (NOT a fill)."""
        events: tuple[OutboxEvent, ...] = ()
        if broker_order_id is not None:
            events = (
                OutboxEvent(
                    event_type=PlatformEventType.ORDER_ACCEPTED_BY_VENUE,
                    producer=self.actor,
                    idempotency_key=f"order:{order_id}:broker_ack",
                    payload={
                        "order_id": order_id,
                        "broker_order_id": broker_order_id,
                    },
                ),
            )
        return self.store.transition_order(
            order_id,
            OrderStatus.ACCEPTED,
            self.actor,
            reason="venue acknowledged order",
            expected_version=expected_version,
            events=events,
            # The venue's identifier is persisted with the acknowledgement: it is
            # the join key reconciliation needs after a restart (§23, §26).
            broker_order_id=broker_order_id,
        )

    def reject(
        self,
        order_id: str,
        reason: str,
        *,
        expected_version: int | None = None,
    ) -> DurableOrder:
        order = self.store.order(order_id)
        if order is None:
            raise ValueError(f"unknown order {order_id!r}")
        event = outbox_event_from_platform(
            order_denied(order.strategy_id, reason, source=self.actor),
            f"order:{order_id}:rejected",
            producer=self.actor,
        )
        return self.store.transition_order(
            order_id,
            OrderStatus.REJECTED,
            self.actor,
            reason=reason,
            expected_version=expected_version,
            events=(event,),
        )

    def cancel(self, order_id: str, reason: str = "operator cancel") -> DurableOrder:
        return self.store.transition_order(
            order_id, OrderStatus.CANCELLED, self.actor, reason=reason
        )

    def expire(self, order_id: str, reason: str = "time in force elapsed") -> DurableOrder:
        return self.store.transition_order(
            order_id, OrderStatus.EXPIRED, self.actor, reason=reason
        )

    def apply_fill(self, fill: Fill) -> bool:
        """Apply a venue fill exactly once; False when already applied."""
        order = self.store.order(fill.order_id)
        if order is None:
            raise ValueError(f"fill references unknown order {fill.order_id!r}")
        event = outbox_event_from_platform(
            execution_completed(
                fill.fill_id,
                fill.symbol,
                fill.price,
                fill.quantity,
                "venue",
            ),
            f"fill:{fill.fill_id}",
            producer=self.actor,
            correlation_id=fill.order_id,
        )
        return self.store.apply_fill(fill, (event,))

    # ------------------------------------------------------------------ reads

    def order(self, order_id: str) -> DurableOrder | None:
        return self.store.order(order_id)

    def recover_open_orders(self) -> list[DurableOrder]:
        """Live orders after a restart — durable state, not process memory."""
        open_orders = self.store.open_orders(self.account_id)
        logger.info("durable OMS recovery: %d open order(s) rehydrated", len(open_orders))
        return open_orders

    def transitions_for(self, order_id: str) -> list[OrderTransition]:
        return self.store.transitions(order_id)

    def stats(self) -> dict[str, int]:
        open_orders = self.store.open_orders(self.account_id)
        return {
            "open_orders": len(open_orders),
            "fills": len([f for f in self.store.fills() if f.account_id == self.account_id]),
            "outbox_backlog": self.store.outbox_backlog(),
        }
