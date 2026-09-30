"""PostgreSQL tier of the deterministic financial state plane.

Same *semantics* as :class:`core.financial_kernel.SqliteFinancialStore`, built on
PostgreSQL-native concurrency rather than a process-wide mutex:

=========================  ===================================================
Concern                    Mechanism
=========================  ===================================================
order version hops         ``SELECT ... FOR UPDATE`` on the order row inside the
                           same transaction that writes the new version
fill uniqueness            UNIQUE(fill_id) and the partial unique index on
                           ``(account_id, broker_execution_id)``; ``ON CONFLICT
                           DO NOTHING`` turns a replay into "already applied"
cash reservations          ``FOR UPDATE`` over the account's reservation rows
                           before reading settled-and-reserved totals, so two
                           processes cannot both spend the same available cash
outbox claiming            ``FOR UPDATE SKIP LOCKED`` over claimable rows, so
                           competing workers take disjoint batches
consumer inbox             PRIMARY KEY (consumer_name, event_id)
reconciliation/lockouts    partial unique index on ``(scope, subject)`` WHERE
                           ``active``; one incident cannot double-engage
durable DDL                versioned migrations, never implicit CREATE TABLE
=========================  ===================================================

The production tier does **not** migrate itself: ``auto_migrate`` defaults to
``False`` and an out-of-date schema raises
:class:`core.migrations.SchemaNotMigrated`. Run ``python -m aios db migrate``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from core.financial_invariants import InvariantVerificationMixin
from core.financial_kernel import (
    BaseFinancialStore,
    CashPosting,
    CashReservation,
    DurableOrder,
    Fill,
    FinancialStoreError,
    FindingStatus,
    InsufficientCash,
    InvalidOrderTransition,
    InvariantReport,
    LockoutScope,
    OrderTransition,
    OutboxEvent,
    OutboxStatus,
    OverFill,
    PositionRecord,
    ReconciliationFinding,
    ReconciliationMode,
    ReconciliationRun,
    ReconciliationSeverity,
    SafetyLockout,
    StaleOrderVersion,
    TimeInForce,
    UnbalancedPostings,
    UnknownOrder,
    _canonical,
    _utc_now,
    apply_fill_to_position,
    is_transition_allowed,
)
from core.migrations import (
    SchemaNotMigrated,
    apply_postgres_migrations,
    latest_version,
    schema_status,
)
from schemas.contracts import OrderSide, OrderStatus, OrderType, generate_uuid, is_terminal

logger = logging.getLogger(__name__)

#: Statement timeout for financial transactions. A blocked statement must fail
#: the transaction (and be retried) rather than hold locks indefinitely.
DEFAULT_STATEMENT_TIMEOUT_MS = 15_000
DEFAULT_LOCK_TIMEOUT_MS = 10_000


def _require_psycopg() -> Any:
    """Import psycopg lazily so the SQLite tier needs no optional dependency."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise FinancialStoreError(
            "PostgreSQL support requires the optional dependency: "
            "pip install 'aios[postgres]'"
        ) from exc
    return psycopg


def _dt(value: Any) -> datetime:
    """Coerce a PostgreSQL timestamp (or ISO string) to an aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value))


def _dt_opt(value: Any) -> datetime | None:
    return None if value is None else _dt(value)


class PgFinancialTransaction:
    """Typed handle for one atomic PostgreSQL financial change."""

    def __init__(self, store: PostgresFinancialStore) -> None:
        self._store = store

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


class PostgresFinancialStore(InvariantVerificationMixin, BaseFinancialStore):
    """Server-grade financial state plane (master-spec §56)."""

    DEFAULT_DUST_RATIO = 1e-3

    def __init__(
        self,
        dsn: str,
        *,
        max_outbox_attempts: int = 5,
        dust_ratio: float = DEFAULT_DUST_RATIO,
        auto_migrate: bool = False,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
        lock_timeout_ms: int = DEFAULT_LOCK_TIMEOUT_MS,
    ) -> None:
        psycopg = _require_psycopg()
        self.dsn = dsn
        self.max_outbox_attempts = max_outbox_attempts
        self.dust_ratio = dust_ratio
        # Autocommit is *on* deliberately. Under ``autocommit=False`` every bare
        # read (there are dozens of readers below) opens an implicit transaction
        # and leaves it open until someone commits; the next
        # ``Connection.transaction()`` would then nest as a SAVEPOINT and the
        # mutation would never become durable. With autocommit on, reads are
        # standalone statements and every atomic change is wrapped explicitly in
        # ``Connection.transaction()`` (real BEGIN/COMMIT), which is also what
        # makes the ``FOR UPDATE`` / ``SKIP LOCKED`` guarantees below hold.
        self._conn = psycopg.connect(dsn, autocommit=True)
        with self._conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {int(statement_timeout_ms)}")
            cur.execute(f"SET lock_timeout = {int(lock_timeout_ms)}")
            cur.execute("SET idle_in_transaction_session_timeout = 60000")
        self._tx: PgFinancialTransaction | None = None
        self._applied_migrations: list[int] = []
        self._ensure_schema(auto_migrate=auto_migrate)

    # ------------------------------------------------------------------ schema

    def _ensure_schema(self, *, auto_migrate: bool) -> None:
        status = schema_status(self._conn, dialect="postgres")
        if status.get("up_to_date"):
            return
        current = status.get("current", 0)
        if not auto_migrate:
            raise SchemaNotMigrated(
                f"financial schema at version {current}, code requires "
                f"{latest_version()}; run `python -m aios db migrate --dsn <dsn>` "
                "(or pass auto_migrate=True in a disposable test environment)"
            )
        self._applied_migrations = apply_postgres_migrations(self._conn)

    def schema_version(self) -> int:
        row = self._query_one("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations")
        return int(row["v"]) if row is not None else 0

    # ---------------------------------------------------------- transactions

    @contextmanager
    def transaction(self) -> Iterator[PgFinancialTransaction]:
        """One atomic financial change; nested calls join the open transaction."""
        if self._tx is not None:
            yield self._tx
            return
        tx = PgFinancialTransaction(self)
        with self._conn.transaction():
            self._tx = tx
            try:
                yield tx
            finally:
                self._tx = None

    def _require_tx(self) -> None:
        if self._tx is None:
            raise FinancialStoreError(
                "financial mutations must run inside store.transaction()"
            )

    # ----------------------------------------------------------- raw plumbing

    def _query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            columns = [d.name for d in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]

    def _query_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.rowcount)

    def _invariant_rows(self, sql: str) -> list[dict[str, Any]]:
        return self._query(sql)

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
        with self.transaction() as tx:
            return tx.amend_order_quantity(order_id, quantity, actor, reason)

    def reserve_cash(self, reservation: CashReservation) -> CashReservation:
        with self.transaction() as tx:
            return tx.reserve_cash(reservation)

    def release_cash(self, reservation_id: str) -> CashReservation:
        with self.transaction() as tx:
            return tx.release_cash(reservation_id)

    def _lock_order(self, order_id: str) -> dict[str, Any] | None:
        """Take a row lock on one order; the lock is held to commit.

        Every writer that can advance an order's version goes through here, which
        is what makes the version hop serialisable across processes. The
        ``UNIQUE(order_id, version)`` constraint on ``order_transitions`` is the
        second line of defence: even a buggy caller cannot record two hops at the
        same version.
        """
        return self._query_one(
            "SELECT * FROM orders WHERE internal_order_id = %s FOR UPDATE", (order_id,)
        )

    def _submit_order(
        self, order: DurableOrder, events: Sequence[OutboxEvent]
    ) -> DurableOrder:
        self._require_tx()
        existing = self._order_by_client_id(order.client_order_id)
        if existing is not None:
            logger.info(
                "duplicate order suppressed by idempotency key %s", order.client_order_id
            )
            return existing
        if order.status is not OrderStatus.PENDING_NEW or order.filled_quantity != 0.0:
            raise FinancialStoreError("new orders must be PENDING_NEW with no fills")
        created = order.model_copy(update={"version": 1})
        inserted = self._query(
            "INSERT INTO orders (internal_order_id, client_order_id, broker_order_id,"
            " strategy_id, portfolio_id, account_id, symbol, side, order_type, quantity,"
            " limit_price, stop_price, time_in_force, filled_quantity, avg_fill_price,"
            " status, version, created_at, updated_at, reject_reason)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
            " %s, %s, %s, %s)"
            " ON CONFLICT (client_order_id) DO NOTHING RETURNING *",
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
                created.created_at,
                created.updated_at,
                created.reject_reason,
            ),
        )
        if not inserted:
            # Lost the race on client_order_id: return the winner's row.
            winner = self._order_by_client_id(order.client_order_id)
            if winner is None:  # pragma: no cover - the conflict implies a row
                raise FinancialStoreError("order conflict without a winner")
            return winner
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
        row = self._lock_order(order_id)
        if row is None:
            raise UnknownOrder(f"unknown order {order_id!r}")
        current = self._row_to_order(row)
        assert current is not None
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
        changed = self._execute(
            "UPDATE orders SET status = %s, version = %s, updated_at = %s,"
            " reject_reason = %s, broker_order_id = %s"
            " WHERE internal_order_id = %s AND version = %s",
            (
                str(updated.status),
                updated.version,
                updated.updated_at,
                updated.reject_reason,
                updated.broker_order_id,
                updated.internal_order_id,
                current.version,
            ),
        )
        if changed != 1:
            # The FOR UPDATE lock should make this impossible; if it ever fires,
            # the version guard did its job and the caller must retry.
            raise StaleOrderVersion(
                f"order {current.internal_order_id} changed under its row lock"
            )
        return updated

    def _amend_order_quantity(
        self, order_id: str, quantity: float, actor: str, reason: str
    ) -> DurableOrder:
        self._require_tx()
        row = self._lock_order(order_id)
        if row is None:
            raise UnknownOrder(f"unknown order {order_id!r}")
        current = self._row_to_order(row)
        assert current is not None
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
        self._execute(
            "UPDATE orders SET quantity = %s, version = %s, updated_at = %s"
            " WHERE internal_order_id = %s",
            (
                updated.quantity,
                updated.version,
                updated.updated_at,
                order_id,
            ),
        )
        self._insert_transition(
            OrderTransition(
                order_id=order_id,
                from_status=current.status,
                to_status=current.status,
                version=updated.version,
                reason=(
                    f"quantity amendment {current.quantity:g} -> {updated.quantity:g}: "
                    f"{reason}"
                ),
                actor=actor,
            )
        )
        return updated

    # -------------------------------------------------------------- fill write

    def _apply_fill(self, fill: Fill, events: Sequence[OutboxEvent]) -> bool:
        self._require_tx()
        if self._fill_exists(fill):
            logger.info("duplicate fill %s ignored (exactly-once)", fill.fill_id)
            return False
        row = self._lock_order(fill.order_id)
        if row is None:
            raise UnknownOrder(f"fill references unknown order {fill.order_id!r}")
        order = self._row_to_order(row)
        assert order is not None
        if fill.side is not order.side:
            raise FinancialStoreError(
                f"fill side {fill.side} does not match order side {order.side}"
            )
        if fill.quantity > order.remaining_quantity + 1e-9:
            raise OverFill(
                f"fill {fill.quantity} exceeds remaining {order.remaining_quantity} "
                f"on order {order.internal_order_id}"
            )

        inserted = self._query(
            "INSERT INTO fills (fill_id, order_id, broker_execution_id, account_id,"
            " strategy_id, symbol, side, quantity, price, fee, currency, executed_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT DO NOTHING RETURNING fill_id",
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
                fill.executed_at,
            ),
        )
        if not inserted:
            # Concurrent replay of the same economic event lost the race.
            logger.info("fill %s lost the uniqueness race; treating as applied", fill.fill_id)
            return False

        filled = round(order.filled_quantity + fill.quantity, 12)
        notional = (
            order.filled_quantity * (order.avg_fill_price or 0.0)
        ) + (fill.quantity * fill.price)
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
        self._execute(
            "UPDATE orders SET filled_quantity = %s, avg_fill_price = %s, status = %s,"
            " version = %s, updated_at = %s WHERE internal_order_id = %s",
            (
                filled,
                avg,
                str(target),
                order.version + 1,
                _utc_now(),
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
        if self._query_one("SELECT 1 AS x FROM fills WHERE fill_id = %s", (fill.fill_id,)):
            return True
        if fill.broker_execution_id is not None:
            return (
                self._query_one(
                    "SELECT 1 AS x FROM fills WHERE account_id = %s"
                    " AND broker_execution_id = %s",
                    (fill.account_id, fill.broker_execution_id),
                )
                is not None
            )
        return False

    def _apply_position_fill(self, fill: Fill) -> None:
        row = self._query_one(
            "SELECT * FROM positions WHERE account_id = %s AND symbol = %s FOR UPDATE",
            (fill.account_id, fill.symbol),
        )
        position = (
            self._row_to_position(row)
            if row is not None
            else PositionRecord(account_id=fill.account_id, symbol=fill.symbol)
        )
        updated = apply_fill_to_position(position, fill)
        self._execute(
            "INSERT INTO positions (account_id, symbol, quantity, avg_cost, currency,"
            " realized_pnl, fees_paid, last_fill_id, updated_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (account_id, symbol) DO UPDATE SET"
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
                updated.updated_at,
            ),
        )

    def _insert_transition(self, transition: OrderTransition) -> None:
        self._execute(
            "INSERT INTO order_transitions (transition_id, order_id, from_status,"
            " to_status, version, reason, actor, occurred_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                transition.transition_id,
                transition.order_id,
                None if transition.from_status is None else str(transition.from_status),
                str(transition.to_status),
                transition.version,
                transition.reason,
                transition.actor,
                transition.occurred_at,
            ),
        )

    # -------------------------------------------------------------- cash writes

    def _post_cash(self, postings: Sequence[CashPosting]) -> int:
        self._require_tx()
        inserted = 0
        for posting in postings:
            inserted += self._execute(
                "INSERT INTO cash_postings (posting_id, transaction_id, account_id,"
                " currency, amount_minor, description, source_ref, occurred_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    posting.posting_id,
                    posting.transaction_id,
                    posting.account_id,
                    posting.currency,
                    posting.amount_minor,
                    posting.description,
                    posting.source_ref,
                    posting.occurred_at,
                ),
            )
        for transaction_id in {p.transaction_id for p in postings}:
            row = self._query_one(
                "SELECT COALESCE(SUM(amount_minor), 0) AS total FROM cash_postings"
                " WHERE transaction_id = %s",
                (transaction_id,),
            )
            total = int(row["total"]) if row is not None else 0
            if total != 0:
                raise UnbalancedPostings(
                    f"cash transaction {transaction_id} does not balance: {total} minor units"
                )
        return inserted

    def _lock_reservations(self, account_id: str, currency: str) -> None:
        """Serialise cash reservation writers for one account/currency.

        Locking ``cash_postings`` rows would lock nothing when the account has no
        postings yet, so the account's reservation rows (and, when empty, the
        ``orders`` of the account) carry the lock. PostgreSQL has no
        ``LOCK ON empty SET``, so we take an advisory transaction lock keyed by
        account+currency: the classic way to serialise a balance check that spans
        two tables.
        """
        self._execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{account_id}:{currency}",)
        )

    def _reserve_cash(self, reservation: CashReservation) -> CashReservation:
        self._require_tx()
        self._lock_reservations(reservation.account_id, reservation.currency)
        settled = self._cash_balance_minor(reservation.account_id, reservation.currency)
        reserved = self._reserved_cash_minor(reservation.account_id, reservation.currency)
        if reservation.amount_minor > settled - reserved:
            raise InsufficientCash(
                f"reserve {reservation.amount_minor} exceeds available "
                f"{settled - reserved} minor units for {reservation.account_id}"
            )
        self._execute(
            "INSERT INTO cash_reservations (reservation_id, account_id, currency,"
            " amount_minor, reason, order_id, created_at, released_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)",
            (
                reservation.reservation_id,
                reservation.account_id,
                reservation.currency,
                reservation.amount_minor,
                reservation.reason,
                reservation.order_id,
                reservation.created_at,
            ),
        )
        return reservation

    def _release_cash(self, reservation_id: str) -> CashReservation:
        self._require_tx()
        row = self._query_one(
            "SELECT * FROM cash_reservations WHERE reservation_id = %s FOR UPDATE",
            (reservation_id,),
        )
        if row is None:
            raise FinancialStoreError(f"unknown reservation {reservation_id!r}")
        released_at = _utc_now()
        self._execute(
            "UPDATE cash_reservations SET released_at = %s"
            " WHERE reservation_id = %s AND released_at IS NULL",
            (released_at, reservation_id),
        )
        return CashReservation(
            reservation_id=str(row["reservation_id"]),
            account_id=str(row["account_id"]),
            currency=str(row["currency"]),
            amount_minor=int(row["amount_minor"]),
            reason=str(row["reason"]),
            order_id=row["order_id"],
            created_at=_dt(row["created_at"]),
            released_at=released_at,
        )

    # ------------------------------------------------------------ outbox writes

    def _enqueue(self, events: Sequence[OutboxEvent]) -> None:
        self._require_tx()
        for event in events:
            self._execute(
                "INSERT INTO event_outbox (event_id, event_type, schema_version,"
                " occurred_at, published_at, producer, actor, correlation_id,"
                " causation_id, trace_id, idempotency_key, policy_version,"
                " model_version, strategy_version, payload_json, payload_hash,"
                " attempts, status, last_error, available_at, claimed_by)"
                " VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                " %s, %s, %s, %s, NULL, NULL, NULL) ON CONFLICT DO NOTHING",
                (
                    event.event_id,
                    event.event_type,
                    event.schema_version,
                    event.occurred_at,
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
        """Claim a disjoint batch of pending events for one worker.

        ``FOR UPDATE SKIP LOCKED`` lets N workers drain the same outbox in
        parallel without stepping on each other: each claims a different set, and
        a worker that dies mid-publish leaves its rows claimable for a retry.
        """
        now = _utc_now()
        rows: list[dict[str, Any]] = []
        with self._conn.transaction():
            rows = self._query(
                "WITH claimable AS ("
                "  SELECT event_id FROM event_outbox"
                "  WHERE status = %s AND (available_at IS NULL OR available_at <= %s)"
                "  ORDER BY occurred_at ASC, event_id ASC"
                "  FOR UPDATE SKIP LOCKED LIMIT %s"
                ") UPDATE event_outbox o SET status = %s, claimed_by = %s,"
                " attempts = o.attempts + 1 FROM claimable c"
                " WHERE o.event_id = c.event_id RETURNING o.*",
                (
                    str(OutboxStatus.PENDING),
                    now,
                    limit,
                    str(OutboxStatus.PUBLISHING),
                    worker,
                ),
            )
        return [self._row_to_event({**row, "attempts": int(row["attempts"])}) for row in rows]

    def mark_published(self, event_id: str) -> None:
        self._execute(
            "UPDATE event_outbox SET status = %s, published_at = %s, last_error = NULL"
            " WHERE event_id = %s",
            (str(OutboxStatus.PUBLISHED), _utc_now(), event_id),
        )

    def mark_failed(self, event_id: str, error: str, retry_delay_seconds: int = 5) -> None:
        row = self._query_one(
            "SELECT attempts FROM event_outbox WHERE event_id = %s", (event_id,)
        )
        attempts = int(row["attempts"]) if row is not None else 0
        dead = attempts >= self.max_outbox_attempts
        available = _utc_now() + timedelta(seconds=retry_delay_seconds * max(1, attempts))
        self._execute(
            "UPDATE event_outbox SET status = %s, last_error = %s, available_at = %s,"
            " claimed_by = NULL WHERE event_id = %s",
            (
                str(OutboxStatus.DEAD_LETTER if dead else OutboxStatus.PENDING),
                error,
                available,
                event_id,
            ),
        )

    def outbox_backlog(self) -> int:
        row = self._query_one(
            "SELECT COUNT(*) AS n FROM event_outbox WHERE status IN (%s, %s)",
            (str(OutboxStatus.PENDING), str(OutboxStatus.PUBLISHING)),
        )
        return int(row["n"]) if row is not None else 0

    def recover_claims_after_restart(self) -> int:
        """Return orphaned outbox claims to PENDING (see the ABC contract)."""
        recovered = self._execute(
            "UPDATE event_outbox SET status = %s, claimed_by = NULL"
            " WHERE status = %s AND published_at IS NULL",
            (str(OutboxStatus.PENDING), str(OutboxStatus.PUBLISHING)),
        )
        if recovered:
            logger.warning(
                "recovered %d orphaned outbox claim(s) from a previous process",
                recovered,
            )
        return recovered

    def dead_letters(self) -> list[OutboxEvent]:
        rows = self._query(
            "SELECT * FROM event_outbox WHERE status = %s ORDER BY occurred_at ASC",
            (str(OutboxStatus.DEAD_LETTER),),
        )
        return [self._row_to_event(row) for row in rows]

    def outbox_pending(self, limit: int = 100) -> list[OutboxEvent]:
        rows = self._query(
            "SELECT * FROM event_outbox WHERE status = %s ORDER BY occurred_at ASC LIMIT %s",
            (str(OutboxStatus.PENDING), limit),
        )
        return [self._row_to_event(row) for row in rows]

    def published_events(self, limit: int = 100) -> list[OutboxEvent]:
        rows = self._query(
            "SELECT * FROM event_outbox WHERE status = %s"
            " ORDER BY published_at DESC LIMIT %s",
            (str(OutboxStatus.PUBLISHED), limit),
        )
        return [self._row_to_event(row) for row in rows]

    # ------------------------------------------------------ consumer inbox

    def _record_applied(self, consumer: str, event_id: str, result_hash: str) -> bool:
        inserted = self._execute(
            "INSERT INTO consumer_inbox (consumer_name, event_id, result_hash,"
            " processed_at) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (consumer, event_id, result_hash, _utc_now()),
        )
        return inserted == 1

    def record_applied(self, consumer: str, event_id: str, result_hash: str) -> bool:
        with self.transaction() as tx:
            return tx.record_applied(consumer, event_id, result_hash)

    def was_applied(self, consumer: str, event_id: str) -> str | None:
        row = self._query_one(
            "SELECT result_hash FROM consumer_inbox"
            " WHERE consumer_name = %s AND event_id = %s",
            (consumer, event_id),
        )
        return None if row is None else str(row["result_hash"])

    def inbox_count(self, consumer: str | None = None) -> int:
        if consumer is None:
            row = self._query_one("SELECT COUNT(*) AS n FROM consumer_inbox")
        else:
            row = self._query_one(
                "SELECT COUNT(*) AS n FROM consumer_inbox WHERE consumer_name = %s",
                (consumer,),
            )
        return int(row["n"]) if row is not None else 0

    # ------------------------------------------------------------------ reads

    def _order_by_client_id(self, client_order_id: str) -> DurableOrder | None:
        return self._row_to_order(
            self._query_one(
                "SELECT * FROM orders WHERE client_order_id = %s", (client_order_id,)
            )
        )

    def order(self, order_id: str) -> DurableOrder | None:
        return self._row_to_order(
            self._query_one(
                "SELECT * FROM orders WHERE internal_order_id = %s", (order_id,)
            )
        )

    def order_by_client_id(self, client_order_id: str) -> DurableOrder | None:
        return self._order_by_client_id(client_order_id)

    def orders(self, account_id: str | None = None) -> list[DurableOrder]:
        if account_id is None:
            rows = self._query("SELECT * FROM orders ORDER BY created_at ASC")
        else:
            rows = self._query(
                "SELECT * FROM orders WHERE account_id = %s ORDER BY created_at ASC",
                (account_id,),
            )
        return [o for o in (self._row_to_order(r) for r in rows) if o is not None]

    def open_orders(self, account_id: str | None = None) -> list[DurableOrder]:
        statuses = [str(s) for s in self._open_states()]
        sql = (
            "SELECT * FROM orders WHERE status = ANY(%s)"
            + (" AND account_id = %s" if account_id is not None else "")
            + " ORDER BY created_at ASC"
        )
        params: list[Any] = [statuses]
        if account_id is not None:
            params.append(account_id)
        rows = self._query(sql, params)
        return [o for o in (self._row_to_order(r) for r in rows) if o is not None]

    @staticmethod
    def _open_states() -> tuple[OrderStatus, ...]:
        return (
            OrderStatus.PENDING_NEW,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        )

    def transitions(self, order_id: str) -> list[OrderTransition]:
        rows = self._query(
            "SELECT * FROM order_transitions WHERE order_id = %s ORDER BY version ASC",
            (order_id,),
        )
        return [
            OrderTransition(
                transition_id=str(r["transition_id"]),
                order_id=str(r["order_id"]),
                from_status=None
                if r["from_status"] is None
                else OrderStatus(str(r["from_status"])),
                to_status=OrderStatus(str(r["to_status"])),
                version=int(r["version"]),
                reason=r["reason"],
                actor=str(r["actor"]),
                occurred_at=_dt(r["occurred_at"]),
            )
            for r in rows
        ]

    def fills(self, order_id: str | None = None) -> list[Fill]:
        if order_id is None:
            rows = self._query("SELECT * FROM fills ORDER BY executed_at ASC, fill_id ASC")
        else:
            rows = self._query(
                "SELECT * FROM fills WHERE order_id = %s ORDER BY executed_at ASC, fill_id ASC",
                (order_id,),
            )
        return [
            Fill(
                fill_id=str(r["fill_id"]),
                order_id=str(r["order_id"]),
                broker_execution_id=r["broker_execution_id"],
                account_id=str(r["account_id"]),
                strategy_id=r["strategy_id"],
                symbol=str(r["symbol"]),
                side=OrderSide(str(r["side"])),
                quantity=float(r["quantity"]),
                price=float(r["price"]),
                fee=float(r["fee"]),
                currency=str(r["currency"]),
                executed_at=_dt(r["executed_at"]),
            )
            for r in rows
        ]

    def positions(self, account_id: str | None = None) -> list[PositionRecord]:
        if account_id is None:
            rows = self._query("SELECT * FROM positions ORDER BY symbol ASC")
        else:
            rows = self._query(
                "SELECT * FROM positions WHERE account_id = %s ORDER BY symbol ASC",
                (account_id,),
            )
        return [self._row_to_position(r) for r in rows]

    def cash_postings(self, transaction_id: str | None = None) -> list[CashPosting]:
        if transaction_id is None:
            rows = self._query(
                "SELECT * FROM cash_postings ORDER BY occurred_at ASC, posting_id ASC"
            )
        else:
            rows = self._query(
                "SELECT * FROM cash_postings WHERE transaction_id = %s"
                " ORDER BY occurred_at ASC, posting_id ASC",
                (transaction_id,),
            )
        return [
            CashPosting(
                posting_id=str(r["posting_id"]),
                transaction_id=str(r["transaction_id"]),
                account_id=str(r["account_id"]),
                currency=str(r["currency"]),
                amount_minor=int(r["amount_minor"]),
                description=str(r["description"]),
                source_ref=r["source_ref"],
                occurred_at=_dt(r["occurred_at"]),
            )
            for r in rows
        ]

    def cash_balance_minor(self, account_id: str, currency: str) -> int:
        return self._cash_balance_minor(account_id, currency)

    def _cash_balance_minor(self, account_id: str, currency: str) -> int:
        row = self._query_one(
            "SELECT COALESCE(SUM(amount_minor), 0) AS total FROM cash_postings"
            " WHERE account_id = %s AND currency = %s",
            (account_id, currency),
        )
        return int(row["total"]) if row is not None else 0

    def reservations(self, account_id: str | None = None) -> list[CashReservation]:
        if account_id is None:
            rows = self._query("SELECT * FROM cash_reservations ORDER BY created_at ASC")
        else:
            rows = self._query(
                "SELECT * FROM cash_reservations WHERE account_id = %s"
                " ORDER BY created_at ASC",
                (account_id,),
            )
        return [
            CashReservation(
                reservation_id=str(r["reservation_id"]),
                account_id=str(r["account_id"]),
                currency=str(r["currency"]),
                amount_minor=int(r["amount_minor"]),
                reason=str(r["reason"]),
                order_id=r["order_id"],
                created_at=_dt(r["created_at"]),
                released_at=_dt_opt(r["released_at"]),
            )
            for r in rows
        ]

    def reserved_cash_minor(self, account_id: str, currency: str) -> int:
        return self._reserved_cash_minor(account_id, currency)

    def _reserved_cash_minor(self, account_id: str, currency: str) -> int:
        row = self._query_one(
            "SELECT COALESCE(SUM(amount_minor), 0) AS total FROM cash_reservations"
            " WHERE account_id = %s AND currency = %s AND released_at IS NULL",
            (account_id, currency),
        )
        return int(row["total"]) if row is not None else 0

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

    # --------------------------------------------------------- reconciliation

    def record_reconciliation(
        self, run: ReconciliationRun, findings: Sequence[ReconciliationFinding]
    ) -> ReconciliationRun:
        with self.transaction():
            critical = [
                f for f in findings if f.severity is ReconciliationSeverity.CRITICAL
            ]
            scope = LockoutScope.NONE
            for finding in critical:
                if _scope_rank(finding.scope) > _scope_rank(scope):
                    scope = finding.scope
            stored = run.model_copy(
                update={
                    "finished_at": run.finished_at or _utc_now(),
                    "finding_count": len(findings),
                    "lockout_scope": scope,
                    "ok": not critical,
                }
            )
            self._execute(
                "INSERT INTO reconciliation_runs (run_id, account_id, started_at,"
                " finished_at, checked_orders, checked_fills, checked_positions,"
                " finding_count, ok, mode, broker, adapter_version, window_start,"
                " window_end, cursor_token, queried_at, lockout_scope,"
                " matched_executions, broker_only_executions, internal_only_executions)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                " %s, %s, %s, %s, %s) ON CONFLICT (run_id) DO NOTHING",
                (
                    stored.run_id,
                    stored.account_id,
                    stored.started_at,
                    stored.finished_at,
                    stored.checked_orders,
                    stored.checked_fills,
                    stored.checked_positions,
                    stored.finding_count,
                    stored.ok,
                    str(stored.mode),
                    stored.broker,
                    stored.adapter_version,
                    stored.window_start,
                    stored.window_end,
                    stored.cursor_token,
                    stored.queried_at,
                    str(stored.lockout_scope),
                    stored.matched_executions,
                    stored.broker_only_executions,
                    stored.internal_only_executions,
                ),
            )
            for finding in findings:
                self._execute(
                    "INSERT INTO reconciliation_findings (finding_id, run_id, kind,"
                    " severity, subject, detail, internal_value, broker_value, status,"
                    " resolution_note, resolved_by, created_at, resolved_at, broker,"
                    " account_id, strategy_id, execution_id, scope)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s, NULL,"
                    " %s, %s, %s, %s, %s) ON CONFLICT (finding_id) DO NOTHING",
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
                        finding.created_at,
                        finding.broker,
                        finding.account_id,
                        finding.strategy_id,
                        finding.execution_id,
                        str(finding.scope),
                    ),
                )
        return stored

    def findings(self, status: FindingStatus | None = None) -> list[ReconciliationFinding]:
        if status is None:
            rows = self._query(
                "SELECT * FROM reconciliation_findings ORDER BY created_at ASC"
            )
        else:
            rows = self._query(
                "SELECT * FROM reconciliation_findings WHERE status = %s"
                " ORDER BY created_at ASC",
                (str(status),),
            )
        return [self._row_to_finding(r) for r in rows]

    def findings_by_id(self, finding_id: str) -> ReconciliationFinding:
        row = self._query_one(
            "SELECT * FROM reconciliation_findings WHERE finding_id = %s", (finding_id,)
        )
        if row is None:
            raise FinancialStoreError(f"unknown finding {finding_id!r}")
        return self._row_to_finding(row)

    def findings_for_run(self, run_id: str) -> list[ReconciliationFinding]:
        rows = self._query(
            "SELECT * FROM reconciliation_findings WHERE run_id = %s"
            " ORDER BY created_at ASC",
            (run_id,),
        )
        return [self._row_to_finding(r) for r in rows]

    def reconciliation_runs(
        self, account_id: str | None = None, limit: int = 50
    ) -> list[ReconciliationRun]:
        if account_id is None:
            rows = self._query(
                "SELECT * FROM reconciliation_runs ORDER BY started_at DESC LIMIT %s",
                (limit,),
            )
        else:
            rows = self._query(
                "SELECT * FROM reconciliation_runs WHERE account_id = %s"
                " ORDER BY started_at DESC LIMIT %s",
                (account_id, limit),
            )
        return [self._row_to_run(r) for r in rows]

    def resolve_finding(
        self, finding_id: str, operator_id: str, note: str
    ) -> ReconciliationFinding:
        if not operator_id.strip():
            raise FinancialStoreError("human identity required to resolve a discrepancy")
        changed = self._execute(
            "UPDATE reconciliation_findings SET status = %s, resolution_note = %s,"
            " resolved_by = %s, resolved_at = %s WHERE finding_id = %s",
            (
                str(FindingStatus.RESOLVED),
                note,
                operator_id,
                _utc_now(),
                finding_id,
            ),
        )
        if changed != 1:
            raise FinancialStoreError(f"unknown finding {finding_id!r}")
        return self.findings_by_id(finding_id)

    # ------------------------------------------------------- safety lockouts

    def engage_lockout(self, lockout: SafetyLockout) -> SafetyLockout:
        if lockout.scope is LockoutScope.NONE:
            raise FinancialStoreError("refusing to engage a lockout with scope NONE")
        with self.transaction():
            self._execute(
                "INSERT INTO safety_lockouts (lockout_id, scope, subject, reason,"
                " finding_id, run_id, engaged_by, engaged_at, released_by, released_at,"
                " release_note, active) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL,"
                " NULL, NULL, TRUE) ON CONFLICT DO NOTHING",
                (
                    lockout.lockout_id,
                    str(lockout.scope),
                    lockout.subject,
                    lockout.reason,
                    lockout.finding_id,
                    lockout.run_id,
                    lockout.engaged_by,
                    lockout.engaged_at,
                ),
            )
        existing = self.active_lockouts(lockout.scope, lockout.subject)
        if not existing:  # pragma: no cover - the insert above must land
            raise FinancialStoreError("lockout insert did not persist")
        return existing[0]

    def active_lockouts(
        self,
        scope: LockoutScope | None = None,
        subject: str | None = None,
    ) -> list[SafetyLockout]:
        sql = "SELECT * FROM safety_lockouts WHERE active = TRUE"
        params: list[Any] = []
        if scope is not None:
            sql += " AND scope = %s"
            params.append(str(scope))
        if subject is not None:
            sql += " AND subject = %s"
            params.append(subject)
        sql += " ORDER BY engaged_at ASC"
        return [self._row_to_lockout(r) for r in self._query(sql, params)]

    def release_lockout(
        self, lockout_id: str, released_by: str, note: str
    ) -> SafetyLockout:
        if not released_by.strip():
            raise FinancialStoreError("human identity required to release a lockout")
        self._execute(
            "UPDATE safety_lockouts SET active = FALSE, released_by = %s,"
            " released_at = %s, release_note = %s"
            " WHERE lockout_id = %s AND active = TRUE",
            (released_by, _utc_now(), note, lockout_id),
        )
        row = self._query_one(
            "SELECT * FROM safety_lockouts WHERE lockout_id = %s", (lockout_id,)
        )
        if row is None:
            raise FinancialStoreError(f"unknown lockout {lockout_id!r}")
        return self._row_to_lockout(row)

    # ------------------------------------------------------------ invariants

    def verify_invariants(self) -> InvariantReport:
        report: InvariantReport = InvariantVerificationMixin.verify_invariants(self)
        return report

    # ------------------------------------------------------------ row mappers

    @staticmethod
    def _row_to_order(row: dict[str, Any] | None) -> DurableOrder | None:
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
            limit_price=None if row["limit_price"] is None else float(row["limit_price"]),
            stop_price=None if row["stop_price"] is None else float(row["stop_price"]),
            time_in_force=TimeInForce(str(row["time_in_force"])),
            filled_quantity=float(row["filled_quantity"]),
            avg_fill_price=(
                None if row["avg_fill_price"] is None else float(row["avg_fill_price"])
            ),
            status=OrderStatus(str(row["status"])),
            version=int(row["version"]),
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
            reject_reason=row["reject_reason"],
        )

    @staticmethod
    def _row_to_position(row: dict[str, Any]) -> PositionRecord:
        return PositionRecord(
            account_id=str(row["account_id"]),
            symbol=str(row["symbol"]),
            quantity=float(row["quantity"]),
            avg_cost=float(row["avg_cost"]),
            currency=str(row["currency"]),
            realized_pnl=float(row["realized_pnl"]),
            fees_paid=float(row["fees_paid"]),
            last_fill_id=row["last_fill_id"],
            updated_at=_dt(row["updated_at"]),
        )

    @staticmethod
    def _row_to_event(row: dict[str, Any]) -> OutboxEvent:
        import json

        return OutboxEvent(
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"]),
            schema_version=str(row["schema_version"]),
            occurred_at=_dt(row["occurred_at"]),
            published_at=_dt_opt(row["published_at"]),
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
            available_at=_dt_opt(row["available_at"]),
            claimed_by=row["claimed_by"],
        )

    @staticmethod
    def _row_to_finding(row: dict[str, Any]) -> ReconciliationFinding:
        from core.financial_kernel import AnomalyKind

        return ReconciliationFinding(
            finding_id=str(row["finding_id"]),
            run_id=str(row["run_id"]),
            kind=AnomalyKind(str(row["kind"])),
            severity=ReconciliationSeverity(str(row["severity"])),
            subject=str(row["subject"]),
            detail=str(row["detail"]),
            internal_value=row["internal_value"],
            broker_value=row["broker_value"],
            status=FindingStatus(str(row["status"])),
            resolution_note=row["resolution_note"],
            resolved_by=row["resolved_by"],
            created_at=_dt(row["created_at"]),
            resolved_at=_dt_opt(row["resolved_at"]),
            broker=row["broker"],
            account_id=row["account_id"],
            strategy_id=row["strategy_id"],
            execution_id=row["execution_id"],
            scope=LockoutScope(str(row["scope"] or LockoutScope.NONE)),
        )

    @staticmethod
    def _row_to_run(row: dict[str, Any]) -> ReconciliationRun:
        return ReconciliationRun(
            run_id=str(row["run_id"]),
            account_id=str(row["account_id"]),
            mode=ReconciliationMode(str(row["mode"] or ReconciliationMode.FULL_SNAPSHOT)),
            broker=row["broker"],
            adapter_version=row["adapter_version"],
            window_start=_dt_opt(row["window_start"]),
            window_end=_dt_opt(row["window_end"]),
            cursor_token=row["cursor_token"],
            queried_at=_dt_opt(row["queried_at"]),
            started_at=_dt(row["started_at"]),
            finished_at=_dt_opt(row["finished_at"]),
            checked_orders=int(row["checked_orders"]),
            checked_fills=int(row["checked_fills"]),
            checked_positions=int(row["checked_positions"]),
            matched_executions=int(row["matched_executions"]),
            broker_only_executions=int(row["broker_only_executions"]),
            internal_only_executions=int(row["internal_only_executions"]),
            finding_count=int(row["finding_count"]),
            lockout_scope=LockoutScope(str(row["lockout_scope"] or LockoutScope.NONE)),
            ok=bool(row["ok"]),
        )

    @staticmethod
    def _row_to_lockout(row: dict[str, Any]) -> SafetyLockout:
        return SafetyLockout(
            lockout_id=str(row["lockout_id"]),
            scope=LockoutScope(str(row["scope"])),
            subject=str(row["subject"]),
            reason=str(row["reason"]),
            finding_id=row["finding_id"],
            run_id=row["run_id"],
            engaged_by=str(row["engaged_by"]),
            engaged_at=_dt(row["engaged_at"]),
            released_by=row["released_by"],
            released_at=_dt_opt(row["released_at"]),
            release_note=row["release_note"],
            active=bool(row["active"]),
        )

    # ---------------------------------------------------------------- health

    def health(self) -> dict[str, Any]:
        """Operator-facing store health; never fabricates a reading."""
        try:
            status = schema_status(self._conn, dialect="postgres")
            return {
                "backend": "postgres",
                "reachable": True,
                "schema": status,
                "outbox_backlog": self.outbox_backlog(),
                "dead_letters": len(self.dead_letters()),
                "open_findings": len(self.findings(FindingStatus.OPEN)),
                "active_lockouts": len(self.active_lockouts()),
            }
        except Exception as exc:  # noqa: BLE001 - report the failure honestly
            return {"backend": "postgres", "reachable": False, "error": str(exc)}

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001 - closing must be best-effort
            logger.exception("error closing postgres financial store")


def _scope_rank(scope: LockoutScope) -> int:
    from core.financial_kernel import SCOPE_RANK

    return SCOPE_RANK[scope]


def build_postgres_financial_store(
    dsn: str, *, auto_migrate: bool = False
) -> PostgresFinancialStore:
    """Build the server-grade financial store (or raise if unavailable)."""
    return PostgresFinancialStore(dsn, auto_migrate=auto_migrate)


__all__ = [
    "PgFinancialTransaction",
    "PostgresFinancialStore",
    "build_postgres_financial_store",
    "generate_uuid",
]
