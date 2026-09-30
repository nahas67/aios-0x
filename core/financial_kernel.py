"""Deterministic financial state plane: durable financial truth for AIOS-0X V1.

Implements master-spec §23 (persistent order state machines), §26
(reconciliation records), §29–§31 (event envelope, transactional outbox,
durable consumer inbox), §61 (invariants) and §64 (financial schema).

Design rules enforced here, not merely documented:

1. **Atomic mutation + publication** (§30): every financial state change and
   its outbound event are written in ONE database transaction. A crash between
   them is impossible; the transactional outbox is the hand-off.
2. **Exactly-once economic effects** (§31): a fill is identified by its
   ``fill_id`` (or the venue's ``broker_execution_id``). Re-delivery of the
   same fill is a *no-op* that produces no state change and no event.
3. **Legal state machines only** (§23): an order moves only along
   ``ORDER_TRANSITIONS``, guarded by an optimistic ``version`` — a stale writer
   can never overwrite newer state.
4. **Cash is double-entry** (§28): postings carry integer minor units and must
   balance to zero per transaction id.
5. **Positions are reconstructible** (§61): ``rebuild_positions()`` recomputes
   positions from the immutable fill ledger and must match live state.

The store is deliberately an ABC with a local SQLite tier shipped today; the
PostgreSQL tier is an adapter behind the same interface (Doc 16 zero-lock-in).
"""

import hashlib
import json
import logging
import sqlite3
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from core.financial_invariants import InvariantVerificationMixin
from core.migrations import apply_sqlite_migrations, latest_version
from schemas.contracts import (
    OrderSide,
    OrderStatus,
    OrderType,
    generate_uuid,
    is_terminal,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------- errors


class FinancialStoreError(RuntimeError):
    """Base class for deterministic financial-store refusals."""


class InvalidOrderTransition(FinancialStoreError):
    """Attempted an order transition the state machine does not allow."""


class StaleOrderVersion(FinancialStoreError):
    """Optimistic-concurrency failure: another writer advanced the order."""


class UnbalancedPostings(FinancialStoreError):
    """Cash postings do not sum to zero for their transaction."""


class OverFill(FinancialStoreError):
    """Fill quantity exceeds the order's remaining quantity."""


class UnknownOrder(FinancialStoreError):
    """Order id is not present in durable state."""


class InsufficientCash(FinancialStoreError):
    """Reservation exceeds settled cash minus existing reservations."""


# --------------------------------------------------------------------- models


class TimeInForce(StrEnum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    DEAD_LETTER = "DEAD_LETTER"


class ReconciliationSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AnomalyKind(StrEnum):
    """Reconciliation discrepancy taxonomy (master-spec §26).

    Identity first, counts never. A ``broker_execution_id`` that exists both at
    the venue and internally *with matching economics* is a **match**, not a
    discrepancy; only the set-difference and the conflicting mappings below are
    findings. Classifying a correct match as a duplicate would make every
    authoritative broker snapshot look like an incident.
    """

    # ---- orders
    MISSING_ORDER = "MISSING_ORDER"
    """Internal live order absent from a window that should have contained it."""
    UNKNOWN_BROKER_ORDER = "UNKNOWN_BROKER_ORDER"
    """Venue holds an order AIOS never recorded."""
    ORDER_CONFLICT = "ORDER_CONFLICT"
    """One order identity mapped to conflicting economic terms on each side."""

    # ---- executions (identity matching)
    BROKER_ONLY_EXECUTION = "BROKER_ONLY_EXECUTION"
    """Venue execution id with no internal fill: the blotter is missing a fill."""
    INTERNAL_ONLY_EXECUTION = "INTERNAL_ONLY_EXECUTION"
    """Internal fill whose id the venue does not report in a window that should
    have covered it. Never inferred from differing counts."""
    EXECUTION_CONFLICT = "EXECUTION_CONFLICT"
    """Same execution identity carrying conflicting economics (quantity, price,
    symbol, side, or a different owning order)."""
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"
    """The same execution identity appears more than once within ONE source."""

    # ---- balances
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    CASH_MISMATCH = "CASH_MISMATCH"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    STALE_STATUS = "STALE_STATUS"

    # ---- deprecated (read-compatibility for findings persisted by V1-A.1).
    # Never emitted: a correct broker/internal match is a match.
    DUPLICATE_FILL = "DUPLICATE_FILL"
    MISSING_FILL = "MISSING_FILL"


class LockoutScope(StrEnum):
    """How far a reconciliation discrepancy's restriction must reach (§33)."""

    NONE = "NONE"
    STRATEGY = "STRATEGY"
    ACCOUNT = "ACCOUNT"
    BROKER = "BROKER"
    GLOBAL = "GLOBAL"


#: Widest-first ordering; ``max`` over findings yields the required reach.
SCOPE_RANK: dict[LockoutScope, int] = {
    LockoutScope.NONE: 0,
    LockoutScope.STRATEGY: 1,
    LockoutScope.ACCOUNT: 2,
    LockoutScope.BROKER: 3,
    LockoutScope.GLOBAL: 4,
}


#: Restriction reach for each anomaly kind. Only CRITICAL findings restrict.
LOCKOUT_SCOPE_BY_KIND: dict[AnomalyKind, LockoutScope] = {
    AnomalyKind.MISSING_ORDER: LockoutScope.ACCOUNT,
    AnomalyKind.UNKNOWN_BROKER_ORDER: LockoutScope.ACCOUNT,
    AnomalyKind.ORDER_CONFLICT: LockoutScope.ACCOUNT,
    AnomalyKind.BROKER_ONLY_EXECUTION: LockoutScope.ACCOUNT,
    AnomalyKind.INTERNAL_ONLY_EXECUTION: LockoutScope.ACCOUNT,
    AnomalyKind.EXECUTION_CONFLICT: LockoutScope.ACCOUNT,
    AnomalyKind.DUPLICATE_EXECUTION: LockoutScope.ACCOUNT,
    AnomalyKind.QUANTITY_MISMATCH: LockoutScope.ACCOUNT,
    AnomalyKind.CASH_MISMATCH: LockoutScope.ACCOUNT,
    AnomalyKind.POSITION_MISMATCH: LockoutScope.ACCOUNT,
    AnomalyKind.STALE_STATUS: LockoutScope.ACCOUNT,
}


class ReconciliationMode(StrEnum):
    """What the adapter actually asked the venue for (the §26 window contract).

    Reconciliation is only meaningful relative to what was requested:

    - ``FULL_SNAPSHOT``: the venue returned its complete order/execution history
      for the account, so *both* set-differences are meaningful.
    - ``BOUNDED_WINDOW``: the venue returned executions within
      ``[window_start, window_end]``; only internal fills inside that interval
      are expected to be reported, so internal-only is scoped to the interval.
    - ``CURSOR``: an incremental delta from a broker token. The payload proves
      nothing about executions it did not mention, so internal-only findings
      cannot be derived and are not emitted.
    """

    FULL_SNAPSHOT = "FULL_SNAPSHOT"
    BOUNDED_WINDOW = "BOUNDED_WINDOW"
    CURSOR = "CURSOR"


class FindingStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


#: Legal order-state transitions (§23). Terminal states have no successors.
ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING_NEW: frozenset(
        {
            OrderStatus.ACCEPTED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        }
    ),
    OrderStatus.ACCEPTED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED}
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
}


def is_transition_allowed(current: OrderStatus, target: OrderStatus) -> bool:
    """True when the deterministic order state machine permits the hop.

    A hop to the *same* non-terminal status is permitted: it records an auditable
    event (a quantity amendment, a successive partial fill) without changing
    state, so it can never move money on its own.

    A terminal status is final. ``FILLED -> FILLED`` is rejected even though it
    changes nothing economically, because allowing it would let a completed order
    keep accumulating version hops - and it would make "this order is done"
    unprovable from the order history alone.
    """
    if target == current:
        return not is_terminal(current)
    return target in ORDER_TRANSITIONS[current]


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _parse_dt_opt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


class OutboxEvent(BaseModel):
    """Durable outbound event envelope (master-spec §29).

    Written in the same transaction as the state change it describes; a
    publisher drains it afterwards and the payload hash makes the published
    bytes verifiable against what was committed.
    """

    event_id: str = Field(default_factory=generate_uuid)
    event_type: str = Field(..., min_length=1)
    schema_version: str = "1"
    occurred_at: datetime = Field(default_factory=_utc_now)
    published_at: datetime | None = None
    producer: str = Field(..., min_length=1)
    actor: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    trace_id: str | None = None
    idempotency_key: str = Field(..., min_length=1)
    policy_version: str | None = None
    model_version: str | None = None
    strategy_version: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""
    attempts: int = Field(default=0, ge=0)
    status: OutboxStatus = OutboxStatus.PENDING
    last_error: str | None = None
    available_at: datetime | None = None
    claimed_by: str | None = None

    @model_validator(mode="after")
    def _derive_payload_hash(self) -> "OutboxEvent":
        expected = _payload_hash(self.payload)
        if not self.payload_hash:
            self.payload_hash = expected
        elif self.payload_hash != expected:
            raise ValueError("payload_hash does not match payload contents")
        return self


class DurableOrder(BaseModel):
    """Canonical OMS order record; never held only in process memory."""

    internal_order_id: str = Field(default_factory=generate_uuid)
    client_order_id: str = Field(..., min_length=1, description="Idempotency key")
    broker_order_id: str | None = None
    strategy_id: str = Field(..., min_length=1)
    portfolio_id: str = "default"
    account_id: str = "default"
    symbol: str = Field(..., min_length=1)
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: float = Field(..., gt=0.0)
    limit_price: float | None = Field(default=None, gt=0.0)
    stop_price: float | None = Field(default=None, gt=0.0)
    time_in_force: TimeInForce = TimeInForce.DAY
    filled_quantity: float = Field(default=0.0, ge=0.0)
    avg_fill_price: float | None = Field(default=None, gt=0.0)
    status: OrderStatus = OrderStatus.PENDING_NEW
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    reject_reason: str | None = None

    @property
    def remaining_quantity(self) -> float:
        return round(self.quantity - self.filled_quantity, 12)

    @model_validator(mode="after")
    def _validate(self) -> "DurableOrder":
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT orders require limit_price")
        if self.filled_quantity > self.quantity + 1e-9:
            raise ValueError("filled_quantity exceeds quantity")
        return self


class OrderTransition(BaseModel):
    """Append-only history of one order state change."""

    transition_id: str = Field(default_factory=generate_uuid)
    order_id: str = Field(..., min_length=1)
    from_status: OrderStatus | None
    to_status: OrderStatus
    version: int = Field(..., ge=1)
    reason: str | None = None
    actor: str = Field(..., min_length=1)
    occurred_at: datetime = Field(default_factory=_utc_now)


class Fill(BaseModel):
    """One execution event from a venue (the only economic truth)."""

    fill_id: str = Field(default_factory=generate_uuid)
    order_id: str = Field(..., min_length=1)
    broker_execution_id: str | None = None
    account_id: str = "default"
    strategy_id: str | None = None
    symbol: str = Field(..., min_length=1)
    side: OrderSide
    quantity: float = Field(..., gt=0.0)
    price: float = Field(..., gt=0.0)
    fee: float = Field(default=0.0, ge=0.0)
    currency: str = "USD"
    executed_at: datetime = Field(default_factory=_utc_now)


class CashPosting(BaseModel):
    """Double-entry cash movement in integer minor units."""

    posting_id: str = Field(default_factory=generate_uuid)
    transaction_id: str = Field(..., min_length=1)
    account_id: str = "default"
    currency: str = "USD"
    amount_minor: int
    description: str = ""
    source_ref: str | None = None
    occurred_at: datetime = Field(default_factory=_utc_now)


class CashReservation(BaseModel):
    """Cash set aside for live orders so buying power is explicit (§27)."""

    reservation_id: str = Field(default_factory=generate_uuid)
    account_id: str = "default"
    currency: str = "USD"
    amount_minor: int = Field(..., gt=0)
    reason: str = ""
    order_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    released_at: datetime | None = None


class PositionRecord(BaseModel):
    """Canonical position row (long or short; signed quantity)."""

    account_id: str = "default"
    symbol: str = Field(..., min_length=1)
    quantity: float = 0.0
    avg_cost: float = 0.0
    currency: str = "USD"
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    last_fill_id: str | None = None
    updated_at: datetime = Field(default_factory=_utc_now)


class ReconciliationFinding(BaseModel):
    """One discrepancy between broker state and internal truth (§26)."""

    finding_id: str = Field(default_factory=generate_uuid)
    run_id: str = Field(..., min_length=1)
    kind: AnomalyKind
    severity: ReconciliationSeverity
    subject: str = Field(..., min_length=1)
    detail: str = ""
    internal_value: str | None = None
    broker_value: str | None = None
    scope: LockoutScope = LockoutScope.NONE
    broker: str | None = None
    account_id: str | None = None
    strategy_id: str | None = None
    execution_id: str | None = None
    status: FindingStatus = FindingStatus.OPEN
    resolution_note: str | None = None
    resolved_by: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    resolved_at: datetime | None = None


class ReconciliationRun(BaseModel):
    """One reconciliation pass over an account (always persisted).

    Carries the window contract it was requested under, so a finding can always
    be explained by *what the venue was asked for* (master-spec §26).
    """

    run_id: str = Field(default_factory=generate_uuid)
    account_id: str = "default"
    mode: ReconciliationMode = ReconciliationMode.FULL_SNAPSHOT
    broker: str | None = None
    adapter_version: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    cursor_token: str | None = None
    queried_at: datetime | None = None
    started_at: datetime = Field(default_factory=_utc_now)
    finished_at: datetime | None = None
    checked_orders: int = 0
    checked_fills: int = 0
    checked_positions: int = 0
    matched_executions: int = 0
    broker_only_executions: int = 0
    internal_only_executions: int = 0
    finding_count: int = 0
    lockout_scope: LockoutScope = LockoutScope.NONE
    ok: bool = True


class SafetyLockout(BaseModel):
    """A safety-plane restriction on an account, broker, strategy or the system.

    Engaged deterministically by a CRITICAL reconciliation finding; released only
    through an authenticated human authority (§33, §76).
    """

    lockout_id: str = Field(default_factory=generate_uuid)
    scope: LockoutScope
    subject: str = Field(..., min_length=1, description="account id, broker, strategy id or '*'")
    reason: str = Field(..., min_length=1)
    finding_id: str | None = None
    run_id: str | None = None
    engaged_by: str = Field(..., min_length=1)
    engaged_at: datetime = Field(default_factory=_utc_now)
    released_by: str | None = None
    released_at: datetime | None = None
    release_note: str | None = None
    active: bool = True


class InvariantCheck(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class InvariantReport(BaseModel):
    """Machine-checkable proof that financial invariants hold (§61)."""

    checks: list[InvariantCheck] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def failures(self) -> list[InvariantCheck]:
        return [c for c in self.checks if not c.ok]


# ------------------------------------------------------- deterministic algebra


def apply_fill_to_position(position: PositionRecord, fill: Fill) -> PositionRecord:
    """Deterministic position algebra for one fill.

    Shared by every store tier and by ``rebuild_positions`` so that live state
    and the reconstructed book can never disagree by construction: there is
exactly one implementation of what a fill does to a position.

    Rules:

    - Opening or increasing a position capitalises the fee into the cost basis.
      A long pays the fee (worse entry) and a short receives proceeds less the
      fee (also a worse entry), so the basis adjustment follows the fill side.
    - Reducing or closing realises P&L against the cost basis and charges the
      fee to realised P&L.
    - Flipping side leaves the remainder at the fill price as a fresh position.
    """
    signed = fill.quantity if fill.side is OrderSide.BUY else -fill.quantity
    quantity = position.quantity
    avg_cost = position.avg_cost
    realized = position.realized_pnl
    fees = position.fees_paid + fill.fee

    if quantity == 0.0 or (quantity > 0) == (signed > 0):
        new_quantity = round(quantity + signed, 12)
        basis = (
            abs(quantity) * avg_cost
            + abs(signed) * fill.price
            + (fill.fee if signed > 0 else -fill.fee)
        )
        new_avg = round(basis / abs(new_quantity), 10) if new_quantity != 0.0 else 0.0
    else:
        closing = min(abs(signed), abs(quantity))
        realized += (fill.price - avg_cost) * closing * (1.0 if quantity > 0 else -1.0)
        realized -= fill.fee
        new_quantity = round(quantity + signed, 12)
        if new_quantity == 0.0:
            new_avg = 0.0
        elif (new_quantity > 0) != (quantity > 0):
            new_avg = fill.price
        else:
            new_avg = avg_cost

    return PositionRecord(
        account_id=position.account_id,
        symbol=position.symbol,
        quantity=new_quantity,
        avg_cost=round(new_avg, 10),
        currency=fill.currency,
        realized_pnl=round(realized, 10),
        fees_paid=round(fees, 10),
        last_fill_id=fill.fill_id,
        updated_at=_utc_now(),
    )


# ------------------------------------------------------------------ interface


class BaseFinancialStore(ABC):
    """Deterministic financial state boundary (SQLite tier ships in V1)."""

    @abstractmethod
    def transaction(self) -> Any:
        """Open (or join) one atomic financial-state transaction."""

    @abstractmethod
    def submit_order(
        self, order: DurableOrder, events: Sequence[OutboxEvent] = ()
    ) -> DurableOrder:
        """Persist a new order; idempotent on ``client_order_id``."""

    @abstractmethod
    def transition_order(
        self,
        order_id: str,
        to_status: OrderStatus,
        actor: str,
        reason: str | None = None,
        expected_version: int | None = None,
        events: Sequence[OutboxEvent] = (),
        broker_order_id: str | None = None,
    ) -> DurableOrder:
        """Move an order along its state machine with optimistic versioning.

        ``broker_order_id`` records the venue's identifier for this order. It is
        part of the transition (not a separate write) so the acknowledgement is
        atomic with the status hop and lands in the same outbox transaction. It
        must be durable: reconciliation matches internal orders to broker orders
        by this id, and after a restart there is no other place to learn it.
        """

    @abstractmethod
    def amend_order_quantity(
        self, order_id: str, quantity: float, actor: str, reason: str
    ) -> DurableOrder:
        """Reconcile the order quantity with the venue's authoritative sizing."""

    @abstractmethod
    def apply_fill(self, fill: Fill, events: Sequence[OutboxEvent] = ()) -> bool:
        """Apply a fill exactly once; returns False when already applied."""

    @abstractmethod
    def post_cash(self, postings: Sequence[CashPosting]) -> int:
        """Post balanced cash movements; returns rows newly inserted."""

    @abstractmethod
    def cash_postings(self, transaction_id: str | None = None) -> list[CashPosting]:
        """Cash postings, optionally for one transaction."""

    @abstractmethod
    def reserve_cash(self, reservation: CashReservation) -> CashReservation:
        """Reserve settled cash for a live order (buying power)."""

    @abstractmethod
    def release_cash(self, reservation_id: str) -> CashReservation:
        """Release a cash reservation."""

    @abstractmethod
    def rebuild_positions(self, account_id: str | None = None) -> list[PositionRecord]:
        """Recompute positions from the immutable fill ledger."""

    @abstractmethod
    def findings(
        self, status: FindingStatus | None = None
    ) -> list[ReconciliationFinding]:
        """Persisted reconciliation findings, optionally filtered by status."""

    @abstractmethod
    def findings_by_id(self, finding_id: str) -> ReconciliationFinding:
        """One finding by id; raises for an unknown id rather than returning None.

        Reconciliation resolution needs the finding's severity *before* it can
        decide which role is allowed to clear it, so this is part of the store
        boundary rather than an implementation detail.
        """

    @abstractmethod
    def resolve_finding(
        self, finding_id: str, operator_id: str, note: str
    ) -> ReconciliationFinding:
        """Resolve a discrepancy; human identity is mandatory."""

    @abstractmethod
    def order(self, order_id: str) -> DurableOrder | None: ...

    @abstractmethod
    def order_by_client_id(self, client_order_id: str) -> DurableOrder | None: ...

    @abstractmethod
    def orders(self, account_id: str | None = None) -> list[DurableOrder]: ...

    @abstractmethod
    def open_orders(self, account_id: str | None = None) -> list[DurableOrder]: ...

    @abstractmethod
    def transitions(self, order_id: str) -> list[OrderTransition]: ...

    @abstractmethod
    def fills(self, order_id: str | None = None) -> list[Fill]: ...

    @abstractmethod
    def positions(self, account_id: str | None = None) -> list[PositionRecord]: ...

    @abstractmethod
    def cash_balance_minor(self, account_id: str, currency: str) -> int: ...

    @abstractmethod
    def reserved_cash_minor(self, account_id: str, currency: str) -> int: ...

    @abstractmethod
    def claim_outbox(self, worker: str, limit: int = 100) -> list[OutboxEvent]: ...

    @abstractmethod
    def outbox_backlog(self) -> int: ...

    @abstractmethod
    def dead_letters(self) -> list[OutboxEvent]: ...

    @abstractmethod
    def mark_published(self, event_id: str) -> None: ...

    @abstractmethod
    def mark_failed(self, event_id: str, error: str, retry_delay_seconds: int = 5) -> None: ...

    @abstractmethod
    def was_applied(self, consumer: str, event_id: str) -> str | None: ...

    @abstractmethod
    def record_applied(self, consumer: str, event_id: str, result_hash: str) -> bool: ...

    @abstractmethod
    def record_reconciliation(
        self, run: ReconciliationRun, findings: Sequence[ReconciliationFinding]
    ) -> ReconciliationRun: ...

    @abstractmethod
    def engage_lockout(self, lockout: SafetyLockout) -> SafetyLockout:
        """Idempotently restrict a scope; an existing active lockout is returned."""

    @abstractmethod
    def active_lockouts(
        self,
        scope: LockoutScope | None = None,
        subject: str | None = None,
    ) -> list[SafetyLockout]:
        """Currently active restrictions, optionally narrowed to one subject."""

    @abstractmethod
    def release_lockout(
        self, lockout_id: str, released_by: str, note: str
    ) -> SafetyLockout:
        """Release a restriction; requires an authenticated human authority."""

    @abstractmethod
    def schema_version(self) -> int:
        """Highest migration version applied to this database."""

    @abstractmethod
    def outbox_pending(self, limit: int = 100) -> list[OutboxEvent]:
        """Claimable or claimed events, oldest first."""

    @abstractmethod
    def published_events(self, limit: int = 100) -> list[OutboxEvent]:
        """Most recently published events, newest first."""

    @abstractmethod
    def inbox_count(self, consumer: str | None = None) -> int:
        """Processed-event count for one consumer, or across all consumers."""

    @abstractmethod
    def reservations(self, account_id: str | None = None) -> list[CashReservation]:
        """Every cash reservation, open or released."""

    @abstractmethod
    def reconciliation_runs(
        self, account_id: str | None = None, limit: int = 50
    ) -> list[ReconciliationRun]:
        """Persisted reconciliation passes, newest first."""

    @abstractmethod
    def findings_for_run(self, run_id: str) -> list[ReconciliationFinding]:
        """Findings belonging to one reconciliation pass."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Backend identity, schema state and operational counters."""

    @abstractmethod
    def recover_claims_after_restart(self) -> int:
        """Return orphaned outbox claims to PENDING; returns rows recovered.

        **Precondition:** no publisher is running. On cold start every
        ``PUBLISHING`` row is by definition an orphan from the previous process
        (its worker is gone), so reclaiming them all is exactly right. Calling
        this while a publisher is live would steal its in-flight work; use
        ``claim_outbox`` semantics instead in that case.
        """

    @abstractmethod
    def verify_invariants(self) -> InvariantReport: ...

    @abstractmethod
    def close(self) -> None: ...


_OPEN_ORDER_STATES = (
    OrderStatus.PENDING_NEW,
    OrderStatus.ACCEPTED,
    OrderStatus.PARTIALLY_FILLED,
)



class FinancialTransaction:
    """Typed handle for one atomic financial change (master-spec §30, §31).

    Callers compose multiple operations; the enclosing
    :meth:`SqliteFinancialStore.transaction` context commits them together or
    rolls all of them back. Nothing is visible to other connections until
    commit.
    """

    def __init__(self, store: "SqliteFinancialStore") -> None:
        self._store = store

    # -------------------------------------------------------------- order write

    def submit_order(
        self, order: DurableOrder, events: Sequence[OutboxEvent] = ()
    ) -> DurableOrder:
        return self._store._submit_order(order, events)

    def transition_order(
        self,
        order_id: str,
        to_status: OrderStatus,
        actor: str,
        reason: str | None = None,
        expected_version: int | None = None,
        events: Sequence[OutboxEvent] = (),
        broker_order_id: str | None = None,
    ) -> DurableOrder:
        return self._store._transition_order(
            order_id,
            to_status,
            actor,
            reason,
            expected_version,
            events,
            broker_order_id,
        )

    def apply_fill(self, fill: Fill, events: Sequence[OutboxEvent] = ()) -> bool:
        return self._store._apply_fill(fill, events)

    def post_cash(self, postings: Sequence[CashPosting]) -> int:
        return self._store._post_cash(postings)

    def reserve_cash(self, reservation: CashReservation) -> CashReservation:
        return self._store._reserve_cash(reservation)

    def release_cash(self, reservation_id: str) -> CashReservation:
        return self._store._release_cash(reservation_id)

    def amend_order_quantity(
        self, order_id: str, quantity: float, actor: str, reason: str
    ) -> DurableOrder:
        return self._store._amend_order_quantity(order_id, quantity, actor, reason)

    def enqueue(self, events: Sequence[OutboxEvent]) -> None:
        self._store._enqueue(events)

    def record_applied(self, consumer: str, event_id: str, result_hash: str) -> bool:
        return self._store._record_applied(consumer, event_id, result_hash)


class SqliteFinancialStore(InvariantVerificationMixin, BaseFinancialStore):
    """Local SQLite tier of the deterministic financial state plane."""

    #: A market order is complete when the venue delivers at least this share of
    #: the requested quantity. Real venues fill slightly less than requested when
    #: the account is funds-limited, and carrying the remainder as a live order
    #: would report a phantom open position forever.
    DEFAULT_DUST_RATIO = 1e-3

    def __init__(
        self,
        db_path: str | Path,
        max_outbox_attempts: int = 5,
        dust_ratio: float = DEFAULT_DUST_RATIO,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_outbox_attempts = max_outbox_attempts
        self.dust_ratio = dust_ratio
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 10000")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = FULL")
        # Versioned migrations, never implicit CREATE TABLE. The dev/local tier
        # upgrades itself; the production PostgreSQL tier does not (see
        # PostgresFinancialStore, which refuses to open an unmigrated schema).
        self._applied_migrations = apply_sqlite_migrations(self._conn)
        self._conn.commit()
        self._tx: FinancialTransaction | None = None

    def schema_version(self) -> int:
        """Highest migration version applied to this database."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations"
        ).fetchone()
        return int(row["v"]) if row is not None else 0

    # ---------------------------------------------------------- transactions

    @contextmanager
    def transaction(self) -> Iterator[FinancialTransaction]:
        """One atomic financial change; nested calls join the open transaction."""
        with self._lock:
            if self._tx is not None:
                yield self._tx
                return
            self._conn.execute("BEGIN IMMEDIATE")
            tx = FinancialTransaction(self)
            self._tx = tx
            try:
                yield tx
            except BaseException:
                self._conn.rollback()
                self._tx = None
                raise
            else:
                self._conn.commit()
                self._tx = None

    def _require_tx(self) -> None:
        if self._tx is None:
            raise FinancialStoreError(
                "financial mutations must run inside store.transaction()"
            )

    # ------------------------------------------------------------- order writes

    def submit_order(
        self, order: DurableOrder, events: Sequence[OutboxEvent] = ()
    ) -> DurableOrder:
        with self.transaction() as tx:
            return tx.submit_order(order, events)

    def transition_order(
        self,
        order_id: str,
        to_status: OrderStatus,
        actor: str,
        reason: str | None = None,
        expected_version: int | None = None,
        events: Sequence[OutboxEvent] = (),
        broker_order_id: str | None = None,
    ) -> DurableOrder:
        with self.transaction() as tx:
            return tx.transition_order(
                order_id,
                to_status,
                actor,
                reason,
                expected_version,
                events,
                broker_order_id,
            )

    def apply_fill(self, fill: Fill, events: Sequence[OutboxEvent] = ()) -> bool:
        with self.transaction() as tx:
            return tx.apply_fill(fill, events)

    def post_cash(self, postings: Sequence[CashPosting]) -> int:
        with self.transaction() as tx:
            return tx.post_cash(postings)

    def amend_order_quantity(
        self, order_id: str, quantity: float, actor: str, reason: str
    ) -> DurableOrder:
        """Reconcile the order quantity with the venue's authoritative sizing.

        A venue may fill slightly more than a plan-derived estimate (it sizes
        from live equity). The amendment is recorded as an audit hop so the
        order's history explains why its quantity changed.
        """
        with self.transaction() as tx:
            return tx.amend_order_quantity(order_id, quantity, actor, reason)

    def reserve_cash(self, reservation: CashReservation) -> CashReservation:
        with self.transaction() as tx:
            return tx.reserve_cash(reservation)

    def release_cash(self, reservation_id: str) -> CashReservation:
        with self.transaction() as tx:
            return tx.release_cash(reservation_id)

    def _submit_order(
        self, order: DurableOrder, events: Sequence[OutboxEvent]
    ) -> DurableOrder:
        self._require_tx()
        existing = self._row_to_order(
            self._conn.execute(
                "SELECT * FROM orders WHERE client_order_id = ?", (order.client_order_id,)
            ).fetchone()
        )
        if existing is not None:
            logger.info(
                "duplicate order suppressed by idempotency key %s", order.client_order_id
            )
            return existing
        if order.status is not OrderStatus.PENDING_NEW or order.filled_quantity != 0.0:
            raise FinancialStoreError("new orders must be PENDING_NEW with no fills")
        created = order.model_copy(update={"version": 1})
        self._conn.execute(
            "INSERT INTO orders (internal_order_id, client_order_id, broker_order_id,"
            " strategy_id, portfolio_id, account_id, symbol, side, order_type, quantity,"
            " limit_price, stop_price, time_in_force, filled_quantity, avg_fill_price,"
            " status, version, created_at, updated_at, reject_reason)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                created.internal_order_id,
                created.client_order_id,
                created.broker_order_id,
                created.strategy_id,
                created.portfolio_id,
                created.account_id,
                created.symbol,
                str(created.side),
                str(created.order_type),
                created.quantity,
                created.limit_price,
                created.stop_price,
                str(created.time_in_force),
                created.filled_quantity,
                created.avg_fill_price,
                str(created.status),
                created.version,
                created.created_at.isoformat(),
                created.updated_at.isoformat(),
                created.reject_reason,
            ),
        )
        self._insert_transition(
            OrderTransition(
                order_id=created.internal_order_id,
                from_status=None,
                to_status=OrderStatus.PENDING_NEW,
                version=1,
                reason="order submitted",
                actor="oms",
            )
        )
        self._enqueue(events)
        return created

    def _transition_order(
        self,
        order_id: str,
        to_status: OrderStatus,
        actor: str,
        reason: str | None,
        expected_version: int | None,
        events: Sequence[OutboxEvent],
        broker_order_id: str | None = None,
    ) -> DurableOrder:
        self._require_tx()
        current = self.order(order_id)
        if current is None:
            raise UnknownOrder(f"unknown order {order_id!r}")
        if expected_version is not None and current.version != expected_version:
            raise StaleOrderVersion(
                f"order {order_id} is at version {current.version}, "
                f"caller expected {expected_version}"
            )
        if not is_transition_allowed(current.status, to_status):
            raise InvalidOrderTransition(
                f"{current.status} -> {to_status} is not a legal order transition"
            )
        updated = self._write_order_state(current, to_status, reason, broker_order_id)
        self._insert_transition(
            OrderTransition(
                order_id=order_id,
                from_status=current.status,
                to_status=to_status,
                version=updated.version,
                reason=reason,
                actor=actor,
            )
        )
        self._enqueue(events)
        return updated

    def _amend_order_quantity(
        self, order_id: str, quantity: float, actor: str, reason: str
    ) -> DurableOrder:
        self._require_tx()
        current = self.order(order_id)
        if current is None:
            raise UnknownOrder(f"unknown order {order_id!r}")
        if quantity < current.filled_quantity - 1e-9:
            raise FinancialStoreError(
                f"cannot shrink order {order_id} below its filled quantity"
            )
        if is_terminal(current.status):
            raise FinancialStoreError(f"cannot amend terminal order {order_id}")
        if abs(quantity - current.quantity) < 1e-12:
            return current
        updated = current.model_copy(
            update={
                "quantity": round(quantity, 12),
                "version": current.version + 1,
                "updated_at": _utc_now(),
            }
        )
        self._conn.execute(
            "UPDATE orders SET quantity = ?, version = ?, updated_at = ?"
            " WHERE internal_order_id = ?",
            (
                updated.quantity,
                updated.version,
                updated.updated_at.isoformat(),
                order_id,
            ),
        )
        self._insert_transition(
            OrderTransition(
                order_id=order_id,
                from_status=current.status,
                to_status=current.status,
                version=updated.version,
                reason=f"quantity amendment {current.quantity:g} -> {updated.quantity:g}: {reason}",
                actor=actor,
            )
        )
        return updated

    def _write_order_state(
        self,
        current: DurableOrder,
        to_status: OrderStatus,
        reason: str | None,
        broker_order_id: str | None = None,
    ) -> DurableOrder:
        updated = current.model_copy(
            update={
                "status": to_status,
                "version": current.version + 1,
                "updated_at": _utc_now(),
                "reject_reason": reason
                if to_status is OrderStatus.REJECTED
                else current.reject_reason,
                "broker_order_id": broker_order_id or current.broker_order_id,
            }
        )
        self._conn.execute(
            "UPDATE orders SET status = ?, version = ?, updated_at = ?, reject_reason = ?,"
            " broker_order_id = ? WHERE internal_order_id = ?",
            (
                str(updated.status),
                updated.version,
                updated.updated_at.isoformat(),
                updated.reject_reason,
                updated.broker_order_id,
                updated.internal_order_id,
            ),
        )
        return updated

    # -------------------------------------------------------------- fill write

    def _apply_fill(self, fill: Fill, events: Sequence[OutboxEvent]) -> bool:
        self._require_tx()
        if self._fill_exists(fill):
            logger.info("duplicate fill %s ignored (exactly-once)", fill.fill_id)
            return False
        order = self.order(fill.order_id)
        if order is None:
            raise UnknownOrder(f"fill references unknown order {fill.order_id!r}")
        if fill.side is not order.side:
            raise FinancialStoreError(
                f"fill side {fill.side} does not match order side {order.side}"
            )
        if fill.quantity > order.remaining_quantity + 1e-9:
            raise OverFill(
                f"fill {fill.quantity} exceeds remaining {order.remaining_quantity} "
                f"on order {order.internal_order_id}"
            )

        self._conn.execute(
            "INSERT INTO fills (fill_id, order_id, broker_execution_id, account_id,"
            " strategy_id, symbol, side, quantity, price, fee, currency, executed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fill.fill_id,
                fill.order_id,
                fill.broker_execution_id,
                fill.account_id,
                fill.strategy_id,
                fill.symbol,
                str(fill.side),
                fill.quantity,
                fill.price,
                fill.fee,
                fill.currency,
                fill.executed_at.isoformat(),
            ),
        )

        filled = round(order.filled_quantity + fill.quantity, 12)
        notional = (
            (order.filled_quantity * (order.avg_fill_price or 0.0))
            + (fill.quantity * fill.price)
        )
        avg = round(notional / filled, 10) if filled > 0 else None
        remaining = round(order.quantity - filled, 12)
        dust = (
            order.quantity > 0
            and remaining > 0
            and remaining / order.quantity <= self.dust_ratio
        )
        if remaining <= 0 or dust:
            target = OrderStatus.FILLED
            reason = f"fill {fill.fill_id}"
            if dust:
                reason += f" (venue dust remainder {remaining:g} left unfilled)"
        else:
            target = OrderStatus.PARTIALLY_FILLED
            reason = f"fill {fill.fill_id}"
        self._conn.execute(
            "UPDATE orders SET filled_quantity = ?, avg_fill_price = ?, status = ?,"
            " version = ?, updated_at = ? WHERE internal_order_id = ?",
            (
                filled,
                avg,
                str(target),
                order.version + 1,
                _utc_now().isoformat(),
                order.internal_order_id,
            ),
        )
        self._insert_transition(
            OrderTransition(
                order_id=order.internal_order_id,
                from_status=order.status,
                to_status=target,
                version=order.version + 1,
                reason=reason,
                actor="venue",
            )
        )
        self._apply_position_fill(fill)
        self._enqueue(events)
        return True

    def _fill_exists(self, fill: Fill) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM fills WHERE fill_id = ?", (fill.fill_id,)
        ).fetchone()
        if row is not None:
            return True
        if fill.broker_execution_id is not None:
            row = self._conn.execute(
                "SELECT 1 FROM fills WHERE account_id = ? AND broker_execution_id = ?",
                (fill.account_id, fill.broker_execution_id),
            ).fetchone()
            return row is not None
        return False

    def _apply_position_fill(self, fill: Fill) -> None:
        row = self._conn.execute(
            "SELECT * FROM positions WHERE account_id = ? AND symbol = ?",
            (fill.account_id, fill.symbol),
        ).fetchone()
        position = (
            self._row_to_position(row)
            if row is not None
            else PositionRecord(account_id=fill.account_id, symbol=fill.symbol)
        )
        updated = apply_fill_to_position(position, fill)
        self._conn.execute(
            "INSERT INTO positions (account_id, symbol, quantity, avg_cost, currency,"
            " realized_pnl, fees_paid, last_fill_id, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(account_id, symbol) DO UPDATE SET"
            " quantity = excluded.quantity, avg_cost = excluded.avg_cost,"
            " currency = excluded.currency, realized_pnl = excluded.realized_pnl,"
            " fees_paid = excluded.fees_paid, last_fill_id = excluded.last_fill_id,"
            " updated_at = excluded.updated_at",
            (
                updated.account_id,
                updated.symbol,
                updated.quantity,
                updated.avg_cost,
                updated.currency,
                updated.realized_pnl,
                updated.fees_paid,
                updated.last_fill_id,
                updated.updated_at.isoformat(),
            ),
        )

    def _insert_transition(self, transition: OrderTransition) -> None:
        self._conn.execute(
            "INSERT INTO order_transitions (transition_id, order_id, from_status,"
            " to_status, version, reason, actor, occurred_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                transition.transition_id,
                transition.order_id,
                None if transition.from_status is None else str(transition.from_status),
                str(transition.to_status),
                transition.version,
                transition.reason,
                transition.actor,
                transition.occurred_at.isoformat(),
            ),
        )

    # -------------------------------------------------------------- cash writes

    def _post_cash(self, postings: Sequence[CashPosting]) -> int:
        self._require_tx()
        inserted = 0
        for posting in postings:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO cash_postings (posting_id, transaction_id,"
                " account_id, currency, amount_minor, description, source_ref, occurred_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    posting.posting_id,
                    posting.transaction_id,
                    posting.account_id,
                    posting.currency,
                    posting.amount_minor,
                    posting.description,
                    posting.source_ref,
                    posting.occurred_at.isoformat(),
                ),
            )
            inserted += int(cur.rowcount)
        for transaction_id in {p.transaction_id for p in postings}:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(amount_minor), 0) AS total FROM cash_postings"
                " WHERE transaction_id = ?",
                (transaction_id,),
            ).fetchone()
            total = int(row["total"]) if row is not None else 0
            if total != 0:
                raise UnbalancedPostings(
                    f"cash transaction {transaction_id} does not balance: {total} minor units"
                )
        return inserted

    def _reserve_cash(self, reservation: CashReservation) -> CashReservation:
        self._require_tx()
        settled = self._cash_balance_minor(reservation.account_id, reservation.currency)
        reserved = self._reserved_cash_minor(reservation.account_id, reservation.currency)
        if reservation.amount_minor > settled - reserved:
            raise InsufficientCash(
                f"reserve {reservation.amount_minor} exceeds available "
                f"{settled - reserved} minor units for {reservation.account_id}"
            )
        self._conn.execute(
            "INSERT INTO cash_reservations (reservation_id, account_id, currency,"
            " amount_minor, reason, order_id, created_at, released_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                reservation.reservation_id,
                reservation.account_id,
                reservation.currency,
                reservation.amount_minor,
                reservation.reason,
                reservation.order_id,
                reservation.created_at.isoformat(),
            ),
        )
        return reservation

    def _release_cash(self, reservation_id: str) -> CashReservation:
        self._require_tx()
        row = self._conn.execute(
            "SELECT * FROM cash_reservations WHERE reservation_id = ?", (reservation_id,)
        ).fetchone()
        if row is None:
            raise FinancialStoreError(f"unknown reservation {reservation_id!r}")
        released_at = _utc_now().isoformat()
        self._conn.execute(
            "UPDATE cash_reservations SET released_at = ? WHERE reservation_id = ?"
            " AND released_at IS NULL",
            (released_at, reservation_id),
        )
        return CashReservation(
            reservation_id=str(row["reservation_id"]),
            account_id=str(row["account_id"]),
            currency=str(row["currency"]),
            amount_minor=int(row["amount_minor"]),
            reason=str(row["reason"]),
            order_id=row["order_id"],
            created_at=_parse_dt(str(row["created_at"])),
            released_at=_parse_dt(released_at),
        )

    # ----------------------------------------------------------- outbox writes

    def _enqueue(self, events: Sequence[OutboxEvent]) -> None:
        self._require_tx()
        for event in events:
            self._conn.execute(
                "INSERT OR IGNORE INTO event_outbox (event_id, event_type,"
                " schema_version, occurred_at, published_at, producer, actor,"
                " correlation_id, causation_id, trace_id, idempotency_key,"
                " policy_version, model_version, strategy_version, payload_json,"
                " payload_hash, attempts, status, last_error, available_at, claimed_by)"
                " VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL,"
                " NULL, NULL)",
                (
                    event.event_id,
                    event.event_type,
                    event.schema_version,
                    event.occurred_at.isoformat(),
                    event.producer,
                    event.actor,
                    event.correlation_id,
                    event.causation_id,
                    event.trace_id,
                    event.idempotency_key,
                    event.policy_version,
                    event.model_version,
                    event.strategy_version,
                    _canonical(event.payload),
                    event.payload_hash,
                    event.attempts,
                    str(event.status),
                ),
            )

    def claim_outbox(self, worker: str, limit: int = 100) -> list[OutboxEvent]:
        now = _utc_now()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self._conn.execute(
                    "SELECT * FROM event_outbox WHERE status = ? AND (available_at IS"
                    " NULL OR available_at <= ?) ORDER BY occurred_at ASC, event_id ASC"
                    " LIMIT ?",
                    (str(OutboxStatus.PENDING), now.isoformat(), limit),
                ).fetchall()
                for row in rows:
                    self._conn.execute(
                        "UPDATE event_outbox SET status = ?, claimed_by = ?, attempts = ?"
                        " WHERE event_id = ?",
                        (
                            str(OutboxStatus.PUBLISHING),
                            worker,
                            int(row["attempts"]) + 1,
                            str(row["event_id"]),
                        ),
                    )
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        return [
            self._row_to_event(row).model_copy(
                update={
                    "status": OutboxStatus.PUBLISHING,
                    "claimed_by": worker,
                    "attempts": int(row["attempts"]) + 1,
                }
            )
            for row in rows
        ]

    def mark_published(self, event_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE event_outbox SET status = ?, published_at = ?, last_error = NULL"
                " WHERE event_id = ?",
                (str(OutboxStatus.PUBLISHED), _utc_now().isoformat(), event_id),
            )
            self._conn.commit()

    def mark_failed(self, event_id: str, error: str, retry_delay_seconds: int = 5) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT attempts FROM event_outbox WHERE event_id = ?", (event_id,)
            ).fetchone()
            attempts = int(row["attempts"]) if row is not None else 0
            dead = attempts >= self.max_outbox_attempts
            available = _utc_now() + timedelta(seconds=retry_delay_seconds * max(1, attempts))
            self._conn.execute(
                "UPDATE event_outbox SET status = ?, last_error = ?, available_at = ?,"
                " claimed_by = NULL WHERE event_id = ?",
                (
                    str(OutboxStatus.DEAD_LETTER if dead else OutboxStatus.PENDING),
                    error,
                    available.isoformat(),
                    event_id,
                ),
            )
            self._conn.commit()

    def outbox_backlog(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM event_outbox WHERE status IN (?, ?)",
                (str(OutboxStatus.PENDING), str(OutboxStatus.PUBLISHING)),
            ).fetchone()
            return int(row["n"]) if row is not None else 0

    def dead_letters(self) -> list[OutboxEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM event_outbox WHERE status = ? ORDER BY occurred_at ASC",
                (str(OutboxStatus.DEAD_LETTER),),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def outbox_pending(self, limit: int = 100) -> list[OutboxEvent]:
        """Claimable+claimed events, oldest first (operational visibility)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM event_outbox WHERE status IN (?, ?)"
                " ORDER BY occurred_at ASC LIMIT ?",
                (str(OutboxStatus.PENDING), str(OutboxStatus.PUBLISHING), limit),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def recover_claims_after_restart(self) -> int:
        """Return orphaned outbox claims to PENDING (see the ABC contract)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE event_outbox SET status = ?, claimed_by = NULL"
                " WHERE status = ? AND published_at IS NULL",
                (str(OutboxStatus.PENDING), str(OutboxStatus.PUBLISHING)),
            )
            self._conn.commit()
            recovered = int(cur.rowcount)
        if recovered:
            logger.warning(
                "recovered %d orphaned outbox claim(s) from a previous process",
                recovered,
            )
        return recovered

    def published_events(self, limit: int = 100) -> list[OutboxEvent]:
        """Most recently published events, newest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM event_outbox WHERE status = ?"
                " ORDER BY published_at DESC LIMIT ?",
                (str(OutboxStatus.PUBLISHED), limit),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def inbox_count(self, consumer: str | None = None) -> int:
        """Processed-event count for one consumer, or across all consumers."""
        with self._lock:
            if consumer is None:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM consumer_inbox"
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM consumer_inbox WHERE consumer_name = ?",
                    (consumer,),
                ).fetchone()
        return int(row["n"]) if row is not None else 0

    def reservations(self, account_id: str | None = None) -> list[CashReservation]:
        """Every cash reservation, open or released (audit + UI)."""
        sql = "SELECT * FROM cash_reservations"
        params: tuple[Any, ...] = ()
        if account_id is not None:
            sql += " WHERE account_id = ?"
            params = (account_id,)
        sql += " ORDER BY created_at ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            CashReservation(
                reservation_id=str(r["reservation_id"]),
                account_id=str(r["account_id"]),
                currency=str(r["currency"]),
                amount_minor=int(r["amount_minor"]),
                reason=str(r["reason"]),
                order_id=r["order_id"],
                created_at=_parse_dt(str(r["created_at"])),
                released_at=_parse_dt_opt(
                    None if r["released_at"] is None else str(r["released_at"])
                ),
            )
            for r in rows
        ]

    def health(self) -> dict[str, Any]:
        """Operator-facing store health; never fabricates a reading."""
        try:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM event_outbox"
            ).fetchone()
            return {
                "backend": "sqlite",
                "reachable": True,
                "schema": {
                    "dialect": "sqlite",
                    "current": self.schema_version(),
                    "required": latest_version(),
                    "up_to_date": self.schema_version() >= latest_version(),
                },
                "outbox_backlog": self.outbox_backlog(),
                "dead_letters": len(self.dead_letters()),
                "outbox_total": int(row["n"]) if row is not None else 0,
                "open_findings": len(self.findings(FindingStatus.OPEN)),
                "active_lockouts": len(self.active_lockouts()),
            }
        except Exception as exc:  # noqa: BLE001 - report the failure honestly
            return {"backend": "sqlite", "reachable": False, "error": str(exc)}

    # ------------------------------------------------------------- inbox write

    def _record_applied(self, consumer: str, event_id: str, result_hash: str) -> bool:
        self._require_tx()
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO consumer_inbox (consumer_name, event_id, result_hash,"
            " processed_at) VALUES (?, ?, ?, ?)",
            (consumer, event_id, result_hash, _utc_now().isoformat()),
        )
        return bool(cur.rowcount)

    def was_applied(self, consumer: str, event_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT result_hash FROM consumer_inbox WHERE consumer_name = ? AND"
                " event_id = ?",
                (consumer, event_id),
            ).fetchone()
        return None if row is None else str(row["result_hash"])

    def record_applied(self, consumer: str, event_id: str, result_hash: str) -> bool:
        with self.transaction() as tx:
            return tx.record_applied(consumer, event_id, result_hash)

    # ------------------------------------------------------------------ reads

    def order(self, order_id: str) -> DurableOrder | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM orders WHERE internal_order_id = ?", (order_id,)
            ).fetchone()
        return self._row_to_order(row)

    def order_by_client_id(self, client_order_id: str) -> DurableOrder | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
            ).fetchone()
        return self._row_to_order(row)

    def orders(self, account_id: str | None = None) -> list[DurableOrder]:
        sql = "SELECT * FROM orders"
        params: list[Any] = []
        if account_id is not None:
            sql += " WHERE account_id = ?"
            params.append(account_id)
        sql += " ORDER BY created_at ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [o for o in (self._row_to_order(r) for r in rows) if o is not None]

    def open_orders(self, account_id: str | None = None) -> list[DurableOrder]:
        placeholders = ", ".join("?" for _ in _OPEN_ORDER_STATES)
        params: list[Any] = [str(s) for s in _OPEN_ORDER_STATES]
        sql = f"SELECT * FROM orders WHERE status IN ({placeholders})"
        if account_id is not None:
            sql += " AND account_id = ?"
            params.append(account_id)
        sql += " ORDER BY created_at ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [o for o in (self._row_to_order(r) for r in rows) if o is not None]

    def transitions(self, order_id: str) -> list[OrderTransition]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM order_transitions WHERE order_id = ? ORDER BY version ASC",
                (order_id,),
            ).fetchall()
        return [
            OrderTransition(
                transition_id=str(r["transition_id"]),
                order_id=str(r["order_id"]),
                from_status=None if r["from_status"] is None else OrderStatus(str(r["from_status"])),
                to_status=OrderStatus(str(r["to_status"])),
                version=int(r["version"]),
                reason=r["reason"],
                actor=str(r["actor"]),
                occurred_at=_parse_dt(str(r["occurred_at"])),
            )
            for r in rows
        ]

    def fills(self, order_id: str | None = None) -> list[Fill]:
        sql = "SELECT * FROM fills"
        params: tuple[Any, ...] = ()
        if order_id is not None:
            sql += " WHERE order_id = ?"
            params = (order_id,)
        sql += " ORDER BY executed_at ASC, fill_id ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_fill(r) for r in rows]

    def positions(self, account_id: str | None = None) -> list[PositionRecord]:
        sql = "SELECT * FROM positions"
        params: tuple[Any, ...] = ()
        if account_id is not None:
            sql += " WHERE account_id = ?"
            params = (account_id,)
        sql += " ORDER BY symbol ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_position(r) for r in rows]

    def cash_postings(self, transaction_id: str | None = None) -> list[CashPosting]:
        sql = "SELECT * FROM cash_postings"
        params: tuple[Any, ...] = ()
        if transaction_id is not None:
            sql += " WHERE transaction_id = ?"
            params = (transaction_id,)
        sql += " ORDER BY occurred_at ASC, posting_id ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            CashPosting(
                posting_id=str(r["posting_id"]),
                transaction_id=str(r["transaction_id"]),
                account_id=str(r["account_id"]),
                currency=str(r["currency"]),
                amount_minor=int(r["amount_minor"]),
                description=str(r["description"]),
                source_ref=r["source_ref"],
                occurred_at=_parse_dt(str(r["occurred_at"])),
            )
            for r in rows
        ]

    def cash_balance_minor(self, account_id: str, currency: str) -> int:
        with self._lock:
            return self._cash_balance_minor(account_id, currency)

    def _cash_balance_minor(self, account_id: str, currency: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_minor), 0) AS total FROM cash_postings"
            " WHERE account_id = ? AND currency = ?",
            (account_id, currency),
        ).fetchone()
        return int(row["total"]) if row is not None else 0

    def reserved_cash_minor(self, account_id: str, currency: str) -> int:
        with self._lock:
            return self._reserved_cash_minor(account_id, currency)

    def _reserved_cash_minor(self, account_id: str, currency: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_minor), 0) AS total FROM cash_reservations"
            " WHERE account_id = ? AND currency = ? AND released_at IS NULL",
            (account_id, currency),
        ).fetchone()
        return int(row["total"]) if row is not None else 0

    # --------------------------------------------------------- reconciliation

    def record_reconciliation(
        self, run: ReconciliationRun, findings: Sequence[ReconciliationFinding]
    ) -> ReconciliationRun:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                critical = [
                    f for f in findings if f.severity is ReconciliationSeverity.CRITICAL
                ]
                scope = LockoutScope.NONE
                for finding in critical:
                    if SCOPE_RANK[finding.scope] > SCOPE_RANK[scope]:
                        scope = finding.scope
                stored = run.model_copy(
                    update={
                        "finished_at": run.finished_at or _utc_now(),
                        "finding_count": len(findings),
                        "lockout_scope": scope,
                        "ok": not critical,
                    }
                )
                self._conn.execute(
                    "INSERT OR REPLACE INTO reconciliation_runs (run_id, account_id,"
                    " started_at, finished_at, checked_orders, checked_fills,"
                    " checked_positions, finding_count, ok, mode, broker,"
                    " adapter_version, window_start, window_end, cursor_token,"
                    " queried_at, lockout_scope, matched_executions,"
                    " broker_only_executions, internal_only_executions)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        stored.run_id,
                        stored.account_id,
                        stored.started_at.isoformat(),
                        stored.finished_at.isoformat() if stored.finished_at else None,
                        stored.checked_orders,
                        stored.checked_fills,
                        stored.checked_positions,
                        stored.finding_count,
                        int(stored.ok),
                        str(stored.mode),
                        stored.broker,
                        stored.adapter_version,
                        stored.window_start.isoformat() if stored.window_start else None,
                        stored.window_end.isoformat() if stored.window_end else None,
                        stored.cursor_token,
                        stored.queried_at.isoformat() if stored.queried_at else None,
                        str(stored.lockout_scope),
                        stored.matched_executions,
                        stored.broker_only_executions,
                        stored.internal_only_executions,
                    ),
                )
                for finding in findings:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO reconciliation_findings (finding_id,"
                        " run_id, kind, severity, subject, detail, internal_value,"
                        " broker_value, status, resolution_note, resolved_by, created_at,"
                        " resolved_at, broker, account_id, strategy_id, execution_id, scope)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, ?, ?, ?, ?, ?)",
                        (
                            finding.finding_id,
                            finding.run_id,
                            str(finding.kind),
                            str(finding.severity),
                            finding.subject,
                            finding.detail,
                            finding.internal_value,
                            finding.broker_value,
                            str(finding.status),
                            finding.created_at.isoformat(),
                            finding.broker,
                            finding.account_id,
                            finding.strategy_id,
                            finding.execution_id,
                            str(finding.scope),
                        ),
                    )
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        return stored

    def findings(self, status: FindingStatus | None = None) -> list[ReconciliationFinding]:
        sql = "SELECT * FROM reconciliation_findings"
        params: tuple[Any, ...] = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (str(status),)
        sql += " ORDER BY created_at ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_finding(r) for r in rows]

    @staticmethod
    def _row_to_finding(r: sqlite3.Row) -> ReconciliationFinding:
        return ReconciliationFinding(
            finding_id=str(r["finding_id"]),
            run_id=str(r["run_id"]),
            kind=AnomalyKind(str(r["kind"])),
            severity=ReconciliationSeverity(str(r["severity"])),
            subject=str(r["subject"]),
            detail=str(r["detail"]),
            internal_value=r["internal_value"],
            broker_value=r["broker_value"],
            status=FindingStatus(str(r["status"])),
            resolution_note=r["resolution_note"],
            resolved_by=r["resolved_by"],
            created_at=_parse_dt(str(r["created_at"])),
            resolved_at=_parse_dt_opt(
                None if r["resolved_at"] is None else str(r["resolved_at"])
            ),
            broker=r["broker"],
            account_id=r["account_id"],
            strategy_id=r["strategy_id"],
            execution_id=r["execution_id"],
            scope=LockoutScope(str(r["scope"] or LockoutScope.NONE)),
        )

    def reconciliation_runs(
        self, account_id: str | None = None, limit: int = 50
    ) -> list[ReconciliationRun]:
        """Persisted reconciliation passes, newest first."""
        sql = "SELECT * FROM reconciliation_runs"
        params: tuple[Any, ...] = ()
        if account_id is not None:
            sql += " WHERE account_id = ?"
            params = (account_id,)
        sql += " ORDER BY started_at DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(sql, (*params, limit)).fetchall()
        return [self._row_to_run(r) for r in rows]

    def findings_for_run(self, run_id: str) -> list[ReconciliationFinding]:
        """Findings belonging to one reconciliation pass."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reconciliation_findings WHERE run_id = ?"
                " ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
        return [self._row_to_finding(r) for r in rows]

    @staticmethod
    def _row_to_run(r: sqlite3.Row) -> ReconciliationRun:
        return ReconciliationRun(
            run_id=str(r["run_id"]),
            account_id=str(r["account_id"]),
            mode=ReconciliationMode(str(r["mode"] or ReconciliationMode.FULL_SNAPSHOT)),
            broker=r["broker"],
            adapter_version=r["adapter_version"],
            window_start=_parse_dt_opt(
                None if r["window_start"] is None else str(r["window_start"])
            ),
            window_end=_parse_dt_opt(
                None if r["window_end"] is None else str(r["window_end"])
            ),
            cursor_token=r["cursor_token"],
            queried_at=_parse_dt_opt(
                None if r["queried_at"] is None else str(r["queried_at"])
            ),
            started_at=_parse_dt(str(r["started_at"])),
            finished_at=_parse_dt_opt(
                None if r["finished_at"] is None else str(r["finished_at"])
            ),
            checked_orders=int(r["checked_orders"]),
            checked_fills=int(r["checked_fills"]),
            checked_positions=int(r["checked_positions"]),
            matched_executions=int(r["matched_executions"]),
            broker_only_executions=int(r["broker_only_executions"]),
            internal_only_executions=int(r["internal_only_executions"]),
            finding_count=int(r["finding_count"]),
            lockout_scope=LockoutScope(str(r["lockout_scope"] or LockoutScope.NONE)),
            ok=bool(r["ok"]),
        )

    # ------------------------------------------------------- safety lockouts

    def engage_lockout(self, lockout: SafetyLockout) -> SafetyLockout:
        """Idempotently restrict a scope.

        The partial unique index on ``(scope, subject) WHERE active`` is the
        authority: two concurrent engines cannot double-engage, and a recurrence
        of the same condition returns the original lockout with its original
        engaged_at (the restriction never silently extends).
        """
        if lockout.scope is LockoutScope.NONE:
            raise FinancialStoreError("refusing to engage a lockout with scope NONE")
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO safety_lockouts (lockout_id, scope, subject,"
                    " reason, finding_id, run_id, engaged_by, engaged_at, released_by,"
                    " released_at, release_note, active)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 1)",
                    (
                        lockout.lockout_id,
                        str(lockout.scope),
                        lockout.subject,
                        lockout.reason,
                        lockout.finding_id,
                        lockout.run_id,
                        lockout.engaged_by,
                        lockout.engaged_at.isoformat(),
                    ),
                )
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        existing = self.active_lockouts(lockout.scope, lockout.subject)
        if not existing:  # pragma: no cover - the insert above must land
            raise FinancialStoreError("lockout insert did not persist")
        return existing[0]

    def active_lockouts(
        self,
        scope: LockoutScope | None = None,
        subject: str | None = None,
    ) -> list[SafetyLockout]:
        sql = "SELECT * FROM safety_lockouts WHERE active = 1"
        params: list[Any] = []
        if scope is not None:
            sql += " AND scope = ?"
            params.append(str(scope))
        if subject is not None:
            sql += " AND subject = ?"
            params.append(subject)
        sql += " ORDER BY engaged_at ASC"
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [
            SafetyLockout(
                lockout_id=str(r["lockout_id"]),
                scope=LockoutScope(str(r["scope"])),
                subject=str(r["subject"]),
                reason=str(r["reason"]),
                finding_id=r["finding_id"],
                run_id=r["run_id"],
                engaged_by=str(r["engaged_by"]),
                engaged_at=_parse_dt(str(r["engaged_at"])),
                released_by=r["released_by"],
                released_at=_parse_dt_opt(
                    None if r["released_at"] is None else str(r["released_at"])
                ),
                release_note=r["release_note"],
                active=bool(r["active"]),
            )
            for r in rows
        ]

    def release_lockout(
        self, lockout_id: str, released_by: str, note: str
    ) -> SafetyLockout:
        """Release one restriction; a human identity is mandatory.

        Authorisation (which role may release) is enforced by the safety plane
        against the RBAC matrix *before* this call; the store refuses only the
        absence of an identity, so no code path can release anonymously.
        """
        if not released_by.strip():
            raise FinancialStoreError("human identity required to release a lockout")
        with self._lock:
            self._conn.execute(
                "UPDATE safety_lockouts SET active = 0, released_by = ?,"
                " released_at = ?, release_note = ? WHERE lockout_id = ? AND active = 1",
                (released_by, _utc_now().isoformat(), note, lockout_id),
            )
            self._conn.commit()
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM safety_lockouts WHERE lockout_id = ?", (lockout_id,)
            ).fetchone()
        if row is None:
            raise FinancialStoreError(f"unknown lockout {lockout_id!r}")
        return SafetyLockout(
            lockout_id=str(row["lockout_id"]),
            scope=LockoutScope(str(row["scope"])),
            subject=str(row["subject"]),
            reason=str(row["reason"]),
            finding_id=row["finding_id"],
            run_id=row["run_id"],
            engaged_by=str(row["engaged_by"]),
            engaged_at=_parse_dt(str(row["engaged_at"])),
            released_by=row["released_by"],
            released_at=_parse_dt_opt(
                None if row["released_at"] is None else str(row["released_at"])
            ),
            release_note=row["release_note"],
            active=bool(row["active"]),
        )

    def resolve_finding(
        self, finding_id: str, operator_id: str, note: str
    ) -> ReconciliationFinding:
        if not operator_id.strip():
            raise FinancialStoreError("human identity required to resolve a discrepancy")
        with self._lock:
            self._conn.execute(
                "UPDATE reconciliation_findings SET status = ?, resolution_note = ?,"
                " resolved_by = ?, resolved_at = ? WHERE finding_id = ?",
                (
                    str(FindingStatus.RESOLVED),
                    note,
                    operator_id,
                    _utc_now().isoformat(),
                    finding_id,
                ),
            )
            self._conn.commit()
        return self.findings_by_id(finding_id)

    def findings_by_id(self, finding_id: str) -> ReconciliationFinding:
        """Fetch one persisted finding by id (raises if unknown)."""
        found = [f for f in self.findings() if f.finding_id == finding_id]
        if not found:
            raise FinancialStoreError(f"unknown finding {finding_id!r}")
        return found[0]

    # ------------------------------------------------------ IBOR reconstruction

    def rebuild_positions(self, account_id: str | None = None) -> list[PositionRecord]:
        """Recompute positions from the immutable fill ledger (§61)."""
        rebuilt: dict[tuple[str, str], PositionRecord] = {}
        for fill in self.fills():
            key = (fill.account_id, fill.symbol)
            current = rebuilt.get(
                key, PositionRecord(account_id=fill.account_id, symbol=fill.symbol)
            )
            rebuilt[key] = apply_fill_to_position(current, fill)
        values = sorted(rebuilt.values(), key=lambda p: p.symbol)
        if account_id is None:
            return values
        return [p for p in values if p.account_id == account_id]

    # ------------------------------------------------------------ invariants

    def _invariant_rows(self, sql: str) -> list[dict[str, Any]]:
        """Parameter-free row reader used by the shared invariant checks (§61).

        The checks themselves live in :mod:`core.financial_invariants` so the
        SQLite and PostgreSQL tiers prove identical properties instead of two
        drifting copies.
        """
        with self._lock:
            return [dict(row) for row in self._conn.execute(sql).fetchall()]

    # -------------------------------------------------------------- row mappers

    @staticmethod
    def _row_to_order(row: sqlite3.Row | None) -> DurableOrder | None:
        if row is None:
            return None
        return DurableOrder(
            internal_order_id=str(row["internal_order_id"]),
            client_order_id=str(row["client_order_id"]),
            broker_order_id=row["broker_order_id"],
            strategy_id=str(row["strategy_id"]),
            portfolio_id=str(row["portfolio_id"]),
            account_id=str(row["account_id"]),
            symbol=str(row["symbol"]),
            side=OrderSide(str(row["side"])),
            order_type=OrderType(str(row["order_type"])),
            quantity=float(row["quantity"]),
            limit_price=row["limit_price"],
            stop_price=row["stop_price"],
            time_in_force=TimeInForce(str(row["time_in_force"])),
            filled_quantity=float(row["filled_quantity"]),
            avg_fill_price=row["avg_fill_price"],
            status=OrderStatus(str(row["status"])),
            version=int(row["version"]),
            created_at=_parse_dt(str(row["created_at"])),
            updated_at=_parse_dt(str(row["updated_at"])),
            reject_reason=row["reject_reason"],
        )

    @staticmethod
    def _row_to_fill(row: sqlite3.Row) -> Fill:
        return Fill(
            fill_id=str(row["fill_id"]),
            order_id=str(row["order_id"]),
            broker_execution_id=row["broker_execution_id"],
            account_id=str(row["account_id"]),
            strategy_id=row["strategy_id"],
            symbol=str(row["symbol"]),
            side=OrderSide(str(row["side"])),
            quantity=float(row["quantity"]),
            price=float(row["price"]),
            fee=float(row["fee"]),
            currency=str(row["currency"]),
            executed_at=_parse_dt(str(row["executed_at"])),
        )

    @staticmethod
    def _row_to_position(row: sqlite3.Row) -> PositionRecord:
        return PositionRecord(
            account_id=str(row["account_id"]),
            symbol=str(row["symbol"]),
            quantity=float(row["quantity"]),
            avg_cost=float(row["avg_cost"]),
            currency=str(row["currency"]),
            realized_pnl=float(row["realized_pnl"]),
            fees_paid=float(row["fees_paid"]),
            last_fill_id=row["last_fill_id"],
            updated_at=_parse_dt(str(row["updated_at"])),
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> OutboxEvent:
        return OutboxEvent(
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"]),
            schema_version=str(row["schema_version"]),
            occurred_at=_parse_dt(str(row["occurred_at"])),
            published_at=_parse_dt_opt(
                None if row["published_at"] is None else str(row["published_at"])
            ),
            producer=str(row["producer"]),
            actor=row["actor"],
            correlation_id=row["correlation_id"],
            causation_id=row["causation_id"],
            trace_id=row["trace_id"],
            idempotency_key=str(row["idempotency_key"]),
            policy_version=row["policy_version"],
            model_version=row["model_version"],
            strategy_version=row["strategy_version"],
            payload=json.loads(str(row["payload_json"])),
            payload_hash=str(row["payload_hash"]),
            attempts=int(row["attempts"]),
            status=OutboxStatus(str(row["status"])),
            last_error=row["last_error"],
            available_at=_parse_dt_opt(
                None if row["available_at"] is None else str(row["available_at"])
            ),
            claimed_by=row["claimed_by"],
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def record_outbox_failure(
    store: BaseFinancialStore,
    event_id: str,
    exc: BaseException,
    retry_delay_seconds: int = 5,
) -> None:
    """Record a failed publication: the event is retried, never dropped.

    A sink failure leaves the row in the outbox with a backoff, so a broker
    outage only *delays* publication. Committed financial state is untouched
    either way. This is the single place that decides what a failure looks like,
    shared by the synchronous publisher and the event-loop-native one.
    """
    logger.warning(
        "outbox publish failed for %s: %s", event_id, exc or type(exc).__name__
    )
    store.mark_failed(
        event_id,
        f"{type(exc).__name__}: {exc}".strip(),
        retry_delay_seconds=retry_delay_seconds,
    )


def publish_outbox_event(
    store: BaseFinancialStore,
    event: OutboxEvent,
    sink: Callable[[OutboxEvent], None],
    retry_delay_seconds: int = 5,
) -> bool:
    """Attempt one synchronous publication; True on success."""
    try:
        sink(event)
    except Exception as exc:  # noqa: BLE001 - a sink failure must not lose the event
        record_outbox_failure(store, event.event_id, exc, retry_delay_seconds)
        return False
    store.mark_published(event.event_id)
    return True


class OutboxPublisher:
    """Drains the transactional outbox into a downstream sink (§30).

    Publication is at-least-once (a crash between sink delivery and
    ``mark_published`` re-delivers); correctness comes from the deterministic
    ``idempotency_key`` on every envelope, which the sink must honour.

    This façade is *synchronous*, so an async sink must marshal onto its loop
    from a different thread — hence
    :class:`core.jetstream_bus.AsyncOutboxPublisher` for event-loop callers.
    """

    def __init__(
        self,
        store: BaseFinancialStore,
        sink: Callable[[OutboxEvent], None],
        worker: str = "outbox-publisher",
        *,
        retry_delay_seconds: int = 5,
    ) -> None:
        self.store = store
        self._sink = sink
        self.worker = worker
        self.retry_delay_seconds = retry_delay_seconds

    def drain(self, limit: int = 100) -> tuple[int, int]:
        """Publish pending events; returns (published, failed).

        A sink failure marks the event failed rather than dropping it: the row
        stays in the outbox with a backoff, so a broker outage only delays
        publication. The committed financial state is untouched either way.
        """
        published = 0
        failed = 0
        for event in self.store.claim_outbox(self.worker, limit=limit):
            if publish_outbox_event(
                self.store, event, self._sink, self.retry_delay_seconds
            ):
                published += 1
            else:
                failed += 1
        return published, failed


def build_financial_store(
    db_path: str | Path, *, max_outbox_attempts: int = 5
) -> BaseFinancialStore:
    """Build the local deterministic financial store (SQLite tier)."""
    return SqliteFinancialStore(db_path, max_outbox_attempts=max_outbox_attempts)
