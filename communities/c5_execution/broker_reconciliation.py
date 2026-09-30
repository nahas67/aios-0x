"""Normalized broker reconciliation adapters (§25, §26).

Every production broker exposes a different reconciliation surface:

======================  =====================================================
Broker shape            What it can answer
======================  =====================================================
``FULL_SNAPSHOT``       complete order + execution history for the account
``BOUNDED_WINDOW``      executions within an explicit ``[start, end]``
``CURSOR``              an incremental delta from a broker token
======================  =====================================================

The engine's window contract (see ``communities.c5_execution.reconciliation``)
expresses exactly that, and this module is the *adapter side* of it: an
:class:`BrokerReconciliationAdapter` declaration says what a venue can produce,
and :func:`normalize_snapshot` turns a broker-specific raw payload into a
:class:`BrokerSnapshot` **without discarding broker state**.

Two rules make that trustworthy:

1. **Provenance is mandatory.** A normalized snapshot always records which broker
   and account it came from, when it was queried, which window or cursor was
   requested, and which adapter version produced it. A snapshot without
   provenance cannot be reconciled honestly, so :class:`BrokerProvenance` refuses
   to be constructed without a broker and a query time.
2. **Raw identifiers are preserved.** Each normalized view keeps the broker's own
   ids and any extra fields in ``raw``. Normalising must not mean amputating.

Adapters are registered by name so a venue can be swapped without touching the
engine, and an unknown adapter fails closed rather than silently producing an
empty (and therefore "clean") snapshot.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from communities.c5_execution.reconciliation import (
    BrokerExecutionView,
    BrokerOrderView,
    BrokerSnapshot,
    ReconciliationWindow,
)
from core.financial_kernel import ReconciliationMode
from schemas.contracts import OrderSide, OrderStatus

logger = logging.getLogger(__name__)


class AdapterError(RuntimeError):
    """A broker adapter could not produce a trustworthy snapshot."""


class UnknownAdapter(AdapterError):
    """No adapter is registered under that name; the engine must not guess."""


@dataclass(frozen=True)
class BrokerProvenance:
    """Where a normalized snapshot came from, and under what request."""

    broker: str
    account_id: str
    queried_at: datetime
    mode: ReconciliationMode
    adapter_version: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    cursor_token: str | None = None
    request_id: str | None = None
    #: Which facets the venue's answer actually contains. Declaring these is not
    #: bookkeeping: the engine refuses to derive an "absent" finding from a facet
    #: the venue never reported, so an adapter that honestly declares partial
    #: coverage produces no false CRITICAL discrepancy (and no false lockout).
    covers_orders: bool = True
    covers_executions: bool = True
    covers_positions: bool = True

    def __post_init__(self) -> None:
        if not self.broker.strip():
            raise AdapterError("provenance requires a broker name")
        if not self.adapter_version.strip():
            raise AdapterError("provenance requires an adapter version")
        if self.mode is ReconciliationMode.BOUNDED_WINDOW:
            if self.window_start is None or self.window_end is None:
                raise AdapterError("BOUNDED_WINDOW provenance requires both window bounds")
        if self.mode is ReconciliationMode.CURSOR and not self.cursor_token:
            raise AdapterError("CURSOR provenance requires a cursor token")

    def to_window(self) -> ReconciliationWindow:
        return ReconciliationWindow(
            mode=self.mode,
            account_id=self.account_id,
            broker=self.broker,
            adapter_version=self.adapter_version,
            window_start=self.window_start,
            window_end=self.window_end,
            cursor_token=self.cursor_token,
            queried_at=self.queried_at,
            covers_orders=self.covers_orders,
            covers_executions=self.covers_executions,
            covers_positions=self.covers_positions,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "account_id": self.account_id,
            "queried_at": self.queried_at.isoformat(),
            "mode": str(self.mode),
            "adapter_version": self.adapter_version,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "cursor_token": self.cursor_token,
            "request_id": self.request_id,
            "covers": [
                name
                for name, flag in (
                    ("orders", self.covers_orders),
                    ("executions", self.covers_executions),
                    ("positions", self.covers_positions),
                )
                if flag
            ],
        }


@dataclass
class RawBrokerPayload:
    """An un-normalized broker response, plus the contract it answers.

    ``orders``/``executions`` are deliberately untyped dicts: each adapter knows
    its own venue's field names, and normalisation is the adapter's job.
    """

    provenance: BrokerProvenance
    orders: list[dict[str, Any]] = field(default_factory=list)
    executions: list[dict[str, Any]] = field(default_factory=list)
    positions: dict[str, float] = field(default_factory=dict)
    cash_minor: int | None = None


class BrokerReconciliationAdapter(ABC):
    """One venue's reconciliation surface."""

    #: Registry name (also used in run provenance).
    name: str = ""
    #: Adapter implementation version, recorded on every run.
    version: str = "1.0"
    #: The strongest claim this venue's API can support.
    mode: ReconciliationMode = ReconciliationMode.FULL_SNAPSHOT

    @abstractmethod
    def fetch(self, account_id: str, **kwargs: Any) -> RawBrokerPayload:
        """Query the venue and return its raw response with provenance."""

    # ------------------------------------------------------------ normalising

    def normalize(self, payload: RawBrokerPayload) -> BrokerSnapshot:
        """Turn a raw payload into a typed snapshot (venue-specific mappings)."""
        return normalize_snapshot(payload)

    def snapshot(self, account_id: str, **kwargs: Any) -> BrokerSnapshot:
        """Fetch and normalize in one step; the engine's entry point."""
        payload = self.fetch(account_id, **kwargs)
        return self.normalize(payload)


_REGISTRY: dict[str, BrokerReconciliationAdapter] = {}


def register_adapter(adapter: BrokerReconciliationAdapter) -> BrokerReconciliationAdapter:
    """Register an adapter instance by name (explicit wiring, no discovery magic)."""
    if not adapter.name:
        raise AdapterError("adapter must declare a non-empty name")
    if adapter.name in _REGISTRY and _REGISTRY[adapter.name] is not adapter:
        raise AdapterError(f"adapter {adapter.name!r} is already registered")
    _REGISTRY[adapter.name] = adapter
    logger.info("registered broker reconciliation adapter %s v%s", adapter.name, adapter.version)
    return adapter


def get_adapter(name: str) -> BrokerReconciliationAdapter:
    """Look up an adapter; unknown names fail closed."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise UnknownAdapter(
            f"no broker reconciliation adapter registered as {name!r}; "
            f"known: {sorted(_REGISTRY)}"
        ) from exc


def registered_adapters() -> dict[str, str]:
    """Name -> version for the operational/UI surface."""
    return {name: adapter.version for name, adapter in sorted(_REGISTRY.items())}


def clear_registry() -> None:
    """Test helper: drop all registrations."""
    _REGISTRY.clear()


# ---------------------------------------------------------------- normalising


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _parse_side(value: Any) -> OrderSide | None:
    if value is None:
        return None
    try:
        return OrderSide(str(value).strip().upper())
    except ValueError:
        return None


def _parse_status(value: Any) -> OrderStatus:
    """Map a venue's status vocabulary onto the canonical one.

    An unrecognised status maps to ``ACCEPTED`` (a live, non-terminal order)
    rather than to a terminal one: assuming an unknown status means "finished"
    would silently drop live exposure from the book.
    """
    if value is None:
        return OrderStatus.ACCEPTED
    text = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "NEW": OrderStatus.ACCEPTED,
        "OPEN": OrderStatus.ACCEPTED,
        "PENDING": OrderStatus.ACCEPTED,
        "PENDING_NEW": OrderStatus.PENDING_NEW,
        "LIVE": OrderStatus.ACCEPTED,
        "PARTIALLYFILLED": OrderStatus.PARTIALLY_FILLED,
        "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
        "PARTIAL": OrderStatus.PARTIALLY_FILLED,
        "FILLED": OrderStatus.FILLED,
        "CLOSED": OrderStatus.FILLED,
        "DONE": OrderStatus.FILLED,
        "COMPLETED": OrderStatus.FILLED,
        "CANCELED": OrderStatus.CANCELLED,
        "CANCELLED": OrderStatus.CANCELLED,
        "REJECTED": OrderStatus.REJECTED,
        "FAILED": OrderStatus.REJECTED,
        "EXPIRED": OrderStatus.EXPIRED,
    }
    return aliases.get(text, OrderStatus.ACCEPTED)


_FIRST_PRESENT = ("broker_order_id", "id", "order_id", "orderId", "orderIdString")
_CLIENT_KEYS = ("client_order_id", "clientOrderId", "client_id", "clientOrderID")
_EXEC_KEYS = ("broker_execution_id", "execution_id", "id", "execId", "trade_id")


def _first(row: dict[str, Any], keys: Iterable[str]) -> Any:
    """First key present with a non-empty value (None when absent)."""
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _require(value: Any, what: str, row: dict[str, Any]) -> Any:
    if value is None:
        raise AdapterError(f"broker row is missing {what}: keys={sorted(row)}")
    return value


def normalize_snapshot(
    payload: RawBrokerPayload,
    *,
    order_mapper: Callable[[dict[str, Any]], BrokerOrderView] | None = None,
    execution_mapper: Callable[[dict[str, Any]], BrokerExecutionView] | None = None,
) -> BrokerSnapshot:
    """Normalize a raw broker payload without discarding broker state.

    Adapters whose venue uses unusual field names supply a mapper; the default
    understands the common shapes and always keeps the original row in ``raw``.
    """
    orders: list[BrokerOrderView] = []
    for row in payload.orders:
        view = (
            order_mapper(row)
            if order_mapper is not None
            else _default_order_view(row)
        )
        orders.append(view)

    executions: list[BrokerExecutionView] = []
    for row in payload.executions:
        execution = (
            execution_mapper(row)
            if execution_mapper is not None
            else _default_execution_view(row)
        )
        executions.append(execution)

    return BrokerSnapshot(
        payload.provenance.to_window(),
        orders=orders,
        executions=executions,
        positions=payload.positions,
        cash_minor=payload.cash_minor,
    )


def _default_order_view(row: dict[str, Any]) -> BrokerOrderView:
    broker_order_id = _require(_first(row, _FIRST_PRESENT), "broker_order_id", row)
    client_order_id = _require(_first(row, _CLIENT_KEYS), "client_order_id", row)
    symbol = _require(row.get("symbol") or row.get("ticker"), "symbol", row)
    quantity = _require(row.get("quantity") or row.get("qty"), "quantity", row)
    filled = row.get("filled_quantity", row.get("filled_qty", row.get("filled", 0.0)))
    side = _parse_side(row.get("side"))
    if side is None:
        raise AdapterError(f"broker order {broker_order_id} has no usable side")
    return BrokerOrderView(
        broker_order_id=str(broker_order_id),
        client_order_id=str(client_order_id),
        symbol=str(symbol),
        side=side,
        quantity=float(quantity),
        filled_quantity=float(filled or 0.0),
        status=_parse_status(row.get("status")),
        raw=row,
    )


def _default_execution_view(row: dict[str, Any]) -> BrokerExecutionView:
    exec_id = _require(_first(row, _EXEC_KEYS), "broker_execution_id", row)
    client_order_id = _require(_first(row, _CLIENT_KEYS), "client_order_id", row)
    quantity = _require(row.get("quantity") or row.get("qty"), "quantity", row)
    price = _require(row.get("price") or row.get("fill_price"), "price", row)
    fee = row.get("fee")
    if fee is None:
        fee = row.get("commission")
    return BrokerExecutionView(
        broker_execution_id=str(exec_id),
        client_order_id=str(client_order_id),
        quantity=float(quantity),
        price=float(price),
        symbol=row.get("symbol") or row.get("ticker"),
        side=_parse_side(row.get("side")),
        executed_at=_parse_dt(
            row.get("executed_at") or row.get("timestamp") or row.get("time")
        ),
        # An unreported fee stays None: unknown is not zero, and inventing one
        # would manufacture an EXECUTION_CONFLICT against the internal ledger.
        fee=None if fee is None else float(fee),
        currency=row.get("currency"),
        raw=row,
    )


def snapshot_from_rows(
    broker: str,
    account_id: str,
    *,
    mode: ReconciliationMode,
    orders: Sequence[dict[str, Any]] = (),
    executions: Sequence[dict[str, Any]] = (),
    positions: dict[str, float] | None = None,
    cash_minor: int | None = None,
    adapter_version: str = "1.0",
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    cursor_token: str | None = None,
    queried_at: datetime | None = None,
    request_id: str | None = None,
    covers_orders: bool = True,
    covers_executions: bool = True,
    covers_positions: bool = True,
) -> BrokerSnapshot:
    """Build a normalized snapshot from raw rows (used by adapters and tests)."""
    provenance = BrokerProvenance(
        broker=broker,
        account_id=account_id,
        queried_at=queried_at or datetime.now(UTC),
        mode=mode,
        adapter_version=adapter_version,
        window_start=window_start,
        window_end=window_end,
        cursor_token=cursor_token,
        request_id=request_id,
        covers_orders=covers_orders,
        covers_executions=covers_executions,
        covers_positions=covers_positions,
    )
    payload = RawBrokerPayload(
        provenance=provenance,
        orders=list(orders),
        executions=list(executions),
        positions=dict(positions or {}),
        cash_minor=cash_minor,
    )
    return normalize_snapshot(payload)


__all__ = [
    "AdapterError",
    "BrokerProvenance",
    "BrokerReconciliationAdapter",
    "RawBrokerPayload",
    "UnknownAdapter",
    "clear_registry",
    "get_adapter",
    "normalize_snapshot",
    "register_adapter",
    "registered_adapters",
    "snapshot_from_rows",
]
