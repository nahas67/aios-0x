"""V1-A.2 PostgreSQL financial store: real transactions, real locks, real DB.

The SQLite tier proves the *semantics*; this tier proves the semantics survive
contact with a server that has genuine concurrent writers. Nothing here is
mocked: every test opens real ``psycopg`` connections against a real PostgreSQL
and asserts on what the database did.

Two classes of evidence live here, and they are deliberately different:

1. **Parity** — the same deterministic scenario, replayed on SQLite and on
   PostgreSQL, must produce the same projected book. A store that "works" only in
   one dialect is not a store, and divergence here is a financial bug.
2. **Concurrency protection at the database level** — the application's
   idempotency checks are *reads*, so they are defeated by another transaction's
   uncommitted work. What actually protects the book is the row lock
   (``FOR UPDATE``), the unique index, and ``SKIP LOCKED``. Each of those is
   exercised by holding a real uncommitted transaction on one connection and
   showing that the second connection cannot slip past it.

The suite skips itself unless ``AIOS_TEST_PG_DSN`` is set, so the hermetic
default run stays green on SQLite alone.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from communities.c5_execution.oms import DurableOrderManager
from core.financial_kernel import (
    AnomalyKind,
    CashPosting,
    CashReservation,
    DurableOrder,
    Fill,
    FinancialStoreError,
    FindingStatus,
    InsufficientCash,
    InvalidOrderTransition,
    LockoutScope,
    OutboxEvent,
    OutboxStatus,
    ReconciliationFinding,
    ReconciliationMode,
    ReconciliationRun,
    ReconciliationSeverity,
    SafetyLockout,
    SqliteFinancialStore,
    StaleOrderVersion,
)
from core.migrations import SchemaNotMigrated, latest_version
from schemas.contracts import OrderSide, OrderStatus

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------- plumbing


@pytest.fixture()
def dsn(reset_postgres: str) -> str:
    """The migrated, truncated-once-per-session PostgreSQL DSN."""
    if not reset_postgres:
        pytest.skip("set AIOS_TEST_PG_DSN to run the PostgreSQL financial store")
    return reset_postgres


@pytest.fixture()
def store(dsn: str) -> Iterator[Any]:
    """One store instance (one database connection) for the duration of a test."""
    from core.pg_financial_store import PostgresFinancialStore

    created = PostgresFinancialStore(dsn, auto_migrate=True)
    try:
        yield created
    finally:
        created.close()


@pytest.fixture()
def second_store(dsn: str) -> Iterator[Any]:
    """A genuinely independent connection, used as the competitor.

    ``lock_timeout_ms`` is deliberately short: a contention test that waits ten
    seconds for the default lock timeout is a slow test, and the point is that
    the second writer *fails* rather than that it waits politely.
    """
    from core.pg_financial_store import PostgresFinancialStore

    created = PostgresFinancialStore(dsn, auto_migrate=True, lock_timeout_ms=750)
    try:
        yield created
    finally:
        created.close()


@contextmanager
def raw_connection(dsn: str) -> Iterator[Any]:
    """A bare psycopg connection with autocommit off, for holding locks open."""
    psycopg = pytest.importorskip("psycopg")
    conn = psycopg.connect(dsn, autocommit=False)
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def drain_outbox(target: Any) -> int:
    """Publish everything queued so a test starts from a known-empty outbox.

    The PostgreSQL database is shared across a whole session, so events left by
    an earlier test are older than this test's events and would otherwise be
    claimed first, in place of the rows the assertions are about.
    """
    published = 0
    while True:
        batch = target.claim_outbox("drain", limit=500)
        if not batch:
            break
        for event in batch:
            target.mark_published(event.event_id)
            published += 1
    return published


def seed_cash(target: Any, account: str, opening_minor: int = 1_000_000) -> None:
    target.post_cash(
        [
            CashPosting(transaction_id=f"seed:{account}", account_id=account, amount_minor=opening_minor),
            CashPosting(
                transaction_id=f"seed:{account}",
                account_id="counterparty",
                amount_minor=-opening_minor,
            ),
        ]
    )


def accepted_order(target: Any, account: str, quantity: float = 10.0) -> DurableOrder:
    oms = DurableOrderManager(target, account_id=account)
    prepared = oms.prepare_order(
        client_order_id=f"{account}-ord",
        strategy_id="strat-1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=quantity,
    )
    return oms.accept(prepared.internal_order_id)


def partial_fill(
    order: DurableOrder,
    quantity: float,
    price: float,
    *,
    fill_id: str,
    exec_id: str | None = None,
    fee: float = 0.5,
) -> Fill:
    return Fill(
        fill_id=fill_id,
        order_id=order.internal_order_id,
        broker_execution_id=exec_id if exec_id is not None else f"exec-{fill_id}",
        account_id=order.account_id,
        strategy_id=order.strategy_id,
        symbol=order.symbol,
        side=order.side,
        quantity=quantity,
        price=price,
        fee=fee,
        executed_at=datetime.now(UTC),
    )


def event_for(key: str) -> OutboxEvent:
    return OutboxEvent(
        event_type="aios.platform.order_requested",
        producer="test",
        idempotency_key=key,
        payload={"key": key},
    )


def fingerprint(target: Any, account: str) -> dict[str, Any]:
    """A dialect-independent projection of the book, for parity comparison."""
    positions = {p.symbol: p for p in target.positions(account)}
    position = positions.get("BTC/USD")
    # fills/findings are global on a shared server, so the projection is scoped
    # to this account or unrelated rows from other tests would poison the parity
    # comparison.
    fills = [f for f in target.fills() if f.account_id == account]
    drafts = [
        {
            "kind": str(f.kind),
            "severity": str(f.severity),
            "subject": f.subject,
            "scope": str(f.scope),
            "status": str(f.status),
        }
        for f in target.findings()
        if f.account_id == account
    ]
    return {
        "cash_minor": target.cash_balance_minor(account, "USD"),
        "reserved_minor": target.reserved_cash_minor(account, "USD"),
        "reservations": len(target.reservations(account)),
        "fills": len(fills),
        "fill_quantity": round(sum(f.quantity for f in fills), 9),
        "fill_fee": round(sum(f.fee for f in fills), 9),
        "position_quantity": round(position.quantity, 9) if position else 0.0,
        "position_avg_cost": round(position.avg_cost, 9) if position else 0.0,
        "position_realized_pnl": round(position.realized_pnl, 9) if position else 0.0,
        "orders": sorted(
            (str(o.status), o.version, round(o.filled_quantity, 9))
            for o in target.orders(account)
        ),
        # Sorted hop counts, not a dict: internal ids and account-derived client
        # ids differ between the two runs by construction, and neither is
        # economic. The number of hops per order is.
        "transitions": sorted(
            len(target.transitions(o.internal_order_id)) for o in target.orders(account)
        ),
        "findings": sorted(drafts, key=lambda d: (d["kind"], d["subject"])),
    }


def run_scenario(
    target: Any, account: str, *, tmp_dir: Any = None
) -> tuple[dict[str, Any], Any]:
    """The same deterministic financial flow, executed on any store tier."""
    seed_cash(target, account, opening_minor=50_000)
    order = accepted_order(target, account, quantity=10.0)

    # Two partial fills plus an overfill attempt and an exact replay.
    target.apply_fill(partial_fill(order, 3.0, 100.0, fill_id="f1"))
    target.apply_fill(partial_fill(order, 2.0, 110.0, fill_id="f2"))
    replayed = target.apply_fill(partial_fill(order, 3.0, 100.0, fill_id="f1"))
    try:
        target.apply_fill(partial_fill(order, 99.0, 100.0, fill_id="f-over"))
        overfill = "applied"
    except FinancialStoreError as exc:
        overfill = type(exc).__name__

    reservation = target.reserve_cash(
        CashReservation(account_id=account, currency="USD", amount_minor=1_000, reason="drill")
    )
    try:
        target.reserve_cash(
            CashReservation(account_id=account, currency="USD", amount_minor=10**9, reason="too big")
        )
        reservation_refusal = "granted"
    except InsufficientCash:
        reservation_refusal = "InsufficientCash"
    target.release_cash(reservation.reservation_id)

    # CANCELLED is legal from PARTIALLY_FILLED; FILLED is not legal from the
    # terminal CANCELLED state. The second hop must be refused on both tiers.
    cancelled = target.transition_order(
        order.internal_order_id, OrderStatus.CANCELLED, actor="w", reason="operator cancel"
    )
    terminal_state = str(cancelled.status)
    try:
        target.transition_order(order.internal_order_id, OrderStatus.FILLED, actor="w")
        terminal_refusal = "advanced"
    except InvalidOrderTransition:
        terminal_refusal = "InvalidOrderTransition"

    run = ReconciliationRun(account_id=account)
    target.record_reconciliation(
        run,
        [
            ReconciliationFinding(
                run_id=run.run_id,
                kind=AnomalyKind.BROKER_ONLY_EXECUTION,
                severity=ReconciliationSeverity.CRITICAL,
                subject="exec-ghost",
                detail="venue execution absent internally",
                scope=LockoutScope.ACCOUNT,
                account_id=account,
                execution_id="exec-ghost",
            )
        ],
    )

    result = {
        "replayed_applied": replayed,
        "overfill": overfill,
        "reservation_refusal": reservation_refusal,
        "terminal_state": terminal_state,
        "terminal_refusal": terminal_refusal,
        **fingerprint(target, account),
    }
    return result, order


# --------------------------------------------------------------- migration contract


def test_schema_is_versioned_and_refuses_to_self_create_in_production(
    dsn: str,
) -> None:
    """The store must not implicitly create production tables on startup.

    A fresh database is probed in its own disposable ``CREATE DATABASE`` so the
    assertion is about genuinely absent tables rather than a mocked check. If the
    role lacks CREATEDB the probe skips rather than weakening the claim.
    """
    psycopg = pytest.importorskip("psycopg")
    from core.pg_financial_store import PostgresFinancialStore

    probe = f"aios_schema_probe_{os.getpid()}"
    admin = psycopg.connect(dsn, autocommit=True)
    try:
        try:
            with admin.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{probe}"')
        except psycopg.Error as exc:  # pragma: no cover - privileges differ per deployment
            pytest.skip(f"role cannot CREATE DATABASE for the migration probe: {exc}")

        from psycopg.conninfo import make_conninfo

        probe_dsn = make_conninfo(dsn, dbname=probe)

        # Production startup path: no implicit DDL, an explicit, actionable error.
        with pytest.raises(SchemaNotMigrated) as excinfo:
            PostgresFinancialStore(probe_dsn, auto_migrate=False)
        assert "db migrate" in str(excinfo.value)

        # The disposable/test path may migrate explicitly and then reports a
        # concrete version rather than a bare boolean.
        migrated = PostgresFinancialStore(probe_dsn, auto_migrate=True)
        try:
            assert migrated.schema_version() == latest_version()
            status = migrated.health()
            assert status["reachable"] is True
        finally:
            migrated.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (probe,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{probe}"')
        admin.close()


def test_migrated_schema_is_up_to_date(store: Any) -> None:
    assert store.schema_version() == latest_version()
    assert store.health()["reachable"] is True


# ------------------------------------------------------------------- parity


def test_postgres_preserves_sqlite_semantics(tmp_path: Any, dsn: str) -> None:
    """The same flow on both tiers must project the same book.

    Timestamps, uuids and the two dialects' internal row ordering are excluded;
    everything economic is compared exactly.
    """
    from core.pg_financial_store import PostgresFinancialStore

    pg = PostgresFinancialStore(dsn, auto_migrate=True)
    sqlite = SqliteFinancialStore(tmp_path / "parity.db")
    try:
        drain_outbox(pg)
        pg_account = f"parity-pg-{os.getpid()}"
        sqlite_account = f"parity-sqlite-{os.getpid()}"
        pg_result, _ = run_scenario(pg, pg_account)
        sqlite_result, _ = run_scenario(sqlite, sqlite_account)

        # Account ids appear in nothing compared here, so the projections must be
        # byte-identical once the account-scoped book is normalised.
        assert pg_result == sqlite_result
        assert pg_result["fills"] == 2
        assert pg_result["replayed_applied"] is False
        assert pg_result["overfill"] == "OverFill"
        assert pg_result["reservation_refusal"] == "InsufficientCash"
        assert pg_result["terminal_refusal"] == "InvalidOrderTransition"
        assert pg_result["position_quantity"] == 5.0
    finally:
        sqlite.close()
        pg.close()


# ------------------------------------------------- mutation + outbox are one unit


def test_mutation_and_outbox_commit_as_one_unit(store: Any) -> None:
    """A crash after both writes must leave neither behind."""
    account = f"atomic-{os.getpid()}"
    seed_cash(store, account)
    order = accepted_order(store, account, quantity=5.0)
    fill = partial_fill(order, 1.0, 100.0, fill_id=f"atomic-{os.getpid()}")
    event = event_for(f"atomic-{os.getpid()}")
    before_backlog = store.outbox_backlog()

    with pytest.raises(RuntimeError):
        with store.transaction() as tx:
            assert tx.apply_fill(fill, [event]) is True
            # Both writes are visible inside the transaction...
            raise RuntimeError("process dies mid-transaction")

    # ...and neither survived it.
    assert store.fills(order.internal_order_id) == []
    assert store.order(order.internal_order_id).filled_quantity == 0.0  # type: ignore[union-attr]
    assert store.outbox_backlog() == before_backlog
    assert all(e.event_id != event.event_id for e in store.published_events(500))
    assert all(e.event_id != event.event_id for e in store.outbox_pending(500))

    # The committed path is the counter-proof: same two writes, no crash.
    with store.transaction() as tx:
        assert tx.apply_fill(fill, [event]) is True
    assert len(store.fills(order.internal_order_id)) == 1
    assert store.outbox_backlog() == before_backlog + 1


def test_mutations_require_an_explicit_transaction(store: Any) -> None:
    with pytest.raises(FinancialStoreError):
        store._enqueue([event_for(f"no-tx-{os.getpid()}")])
    with pytest.raises(FinancialStoreError):
        store._submit_order(
            DurableOrder(
                client_order_id=f"no-tx-{os.getpid()}",
                strategy_id="s1",
                symbol="BTC/USD",
                side=OrderSide.BUY,
                quantity=1.0,
            ),
            (),
        )


# ----------------------------------------------- database-enforced uniqueness


def test_broker_execution_identity_is_unique_per_account(store: Any) -> None:
    """The partial unique index is the last line of defence, not the app check."""
    psycopg = pytest.importorskip("psycopg")
    account = f"uniq-{os.getpid()}"
    seed_cash(store, account)
    order = accepted_order(store, account, quantity=10.0)
    exec_id = f"exec-uniq-{os.getpid()}"
    store.apply_fill(partial_fill(order, 1.0, 100.0, fill_id=f"u1-{account}", exec_id=exec_id))

    # Replaying the SAME venue execution under a new internal fill id is refused
    # by the application check (it is the same economic event).
    assert (
        store.apply_fill(
            partial_fill(order, 1.0, 100.0, fill_id=f"u2-{account}", exec_id=exec_id)
        )
        is False
    )

    # Bypassing the application check entirely, the database still refuses a
    # second row for the same (account_id, broker_execution_id).
    with pytest.raises(psycopg.errors.UniqueViolation):
        store._execute(
            "INSERT INTO fills (fill_id, order_id, broker_execution_id, account_id,"
            " strategy_id, symbol, side, quantity, price, fee, currency, executed_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                f"raw-{account}",
                order.internal_order_id,
                exec_id,
                account,
                "s",
                "BTC/USD",
                "BUY",
                1.0,
                100.0,
                0.0,
                "USD",
                datetime.now(UTC),
            ),
        )

    # A different account may legitimately hold the same venue execution id.
    other = f"uniq-other-{os.getpid()}"
    seed_cash(store, other)
    other_order = accepted_order(store, other, quantity=10.0)
    assert (
        store.apply_fill(
            partial_fill(other_order, 1.0, 100.0, fill_id=f"u-other-{other}", exec_id=exec_id)
        )
        is True
    )


def test_consumer_inbox_uniqueness_is_enforced_by_the_primary_key(store: Any) -> None:
    psycopg = pytest.importorskip("psycopg")
    consumer = f"consumer-{os.getpid()}"
    event_id = f"event-{os.getpid()}"

    assert store.record_applied(consumer, event_id, "hash-1") is True
    assert store.record_applied(consumer, event_id, "hash-1") is False
    assert store.was_applied(consumer, event_id) == "hash-1"

    with pytest.raises(psycopg.errors.UniqueViolation):
        store._execute(
            "INSERT INTO consumer_inbox (consumer_name, event_id, result_hash, processed_at)"
            " VALUES (%s, %s, %s, %s)",
            (consumer, event_id, "hash-1", datetime.now(UTC)),
        )


def test_order_transition_version_cannot_repeat(store: Any) -> None:
    """``UNIQUE(order_id, version)`` forbids two hops recorded at one version."""
    psycopg = pytest.importorskip("psycopg")
    account = f"ver-{os.getpid()}"
    seed_cash(store, account)
    order = accepted_order(store, account, quantity=5.0)

    with pytest.raises(psycopg.errors.UniqueViolation):
        store._execute(
            "INSERT INTO order_transitions (transition_id, order_id, from_status,"
            " to_status, version, reason, actor, occurred_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                f"dup-transition-{account}",
                order.internal_order_id,
                "PENDING_NEW",
                "ACCEPTED",
                2,
                "duplicate",
                "test",
                datetime.now(UTC),
            ),
        )


# ---------------------------------------------------- row locks across connections


def test_uncommitted_fill_cannot_be_replayed_by_another_connection(
    store: Any, second_store: Any
) -> None:
    """Real row locks, not the application's read-then-write check.

    The competitor can see neither the uncommitted fill row nor the bumped order
    state, so its idempotency check passes and it walks straight into the
    ``FOR UPDATE`` lock. The database — not the application — is what stops it.
    """
    psycopg = pytest.importorskip("psycopg")
    account = f"lock-{os.getpid()}"
    seed_cash(store, account)
    order = accepted_order(store, account, quantity=10.0)
    exec_id = f"exec-lock-{os.getpid()}"

    with store.transaction() as tx:
        applied = tx.apply_fill(
            partial_fill(order, 1.0, 100.0, fill_id=f"l1-{account}", exec_id=exec_id)
        )
        assert applied is True

        # Competitor is blocked on the order row and gives up at lock_timeout.
        with pytest.raises(psycopg.Error) as excinfo:
            second_store.apply_fill(
                partial_fill(order, 1.0, 100.0, fill_id=f"l2-{account}", exec_id=exec_id)
            )
        assert type(excinfo.value).__name__ in {
            "LockNotAvailable",
            "OperationalError",
            "QueryCanceled",
        }, excinfo.value

        # It applied nothing: no second fill, no second position application.
        assert len(second_store.fills(order.internal_order_id)) == 0

    # After the commit the competitor retries and is refused *cleanly* by the
    # unique broker-execution identity rather than by a lock.
    assert (
        second_store.apply_fill(
            partial_fill(order, 1.0, 100.0, fill_id=f"l3-{account}", exec_id=exec_id)
        )
        is False
    )
    fills = store.fills(order.internal_order_id)
    assert len(fills) == 1
    assert round(fills[0].quantity, 9) == 1.0
    assert store.verify_invariants().ok is True


def test_uncommitted_transition_cannot_be_double_advanced(
    store: Any, second_store: Any
) -> None:
    """The version hop is serialised by the order row lock."""
    psycopg = pytest.importorskip("psycopg")
    account = f"locktrans-{os.getpid()}"
    seed_cash(store, account)
    order = accepted_order(store, account, quantity=5.0)
    assert order.version == 2

    with store.transaction() as tx:
        advanced = tx.transition_order(order.internal_order_id, OrderStatus.CANCELLED, "a")
        assert advanced.version == 3

        with pytest.raises(psycopg.Error):
            second_store.transition_order(
                order.internal_order_id,
                OrderStatus.CANCELLED,
                "b",
                expected_version=2,
            )
        assert second_store.order(order.internal_order_id).version == 2  # type: ignore[union-attr]

    winner = store.order(order.internal_order_id)
    assert winner is not None and winner.status is OrderStatus.CANCELLED
    assert winner.version == 3
    assert len(store.transitions(order.internal_order_id)) == 3

    # A stale writer that slept through the whole thing is still refused.
    with pytest.raises((StaleOrderVersion, InvalidOrderTransition)):
        second_store.transition_order(
            order.internal_order_id, OrderStatus.FILLED, "late", expected_version=2
        )


def test_claim_outbox_skips_rows_locked_by_another_worker(store: Any, dsn: str) -> None:
    """``SKIP LOCKED`` is load-bearing, so it is asserted against a real lock.

    A separate connection holds an uncommitted ``FOR UPDATE`` on the oldest
    pending event. The store's claim must return the *rest* of the batch and
    leave the locked row alone — never block, never steal a claimed row.
    """
    drain_outbox(store)
    account = f"skip-{os.getpid()}"
    for index in range(3):
        DurableOrderManager(store, account_id=account).prepare_order(
            client_order_id=f"{account}-{index}",
            strategy_id="s",
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
        )
    pending = {e.event_id for e in store.outbox_pending(50)}
    assert len(pending) == 3

    with raw_connection(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT event_id FROM event_outbox WHERE status = %s"
            " ORDER BY occurred_at ASC, event_id ASC LIMIT 1 FOR UPDATE",
            (str(OutboxStatus.PENDING),),
        )
        held = cur.fetchone()
        assert held is not None
        locked_id = str(held[0])
        assert locked_id in pending

        claimed = {e.event_id for e in store.claim_outbox("w-contender", limit=10)}
        assert locked_id not in claimed, "claimed a row another worker holds"
        assert claimed == pending - {locked_id}

        # A second pass must not loop forever over the one it cannot have.
        assert store.claim_outbox("w-contender-2", limit=10) == []
        conn.rollback()

    # Once the holder releases, the row is claimable again.
    recovered = {e.event_id for e in store.claim_outbox("w-recovered", limit=10)}
    assert recovered == {locked_id}


# ------------------------------------------------------- cash reservation safety


def test_reservations_cannot_exceed_available_cash_on_postgres(store: Any) -> None:
    account = f"resv-{os.getpid()}"
    seed_cash(store, account, opening_minor=10_000)

    first = store.reserve_cash(
        CashReservation(account_id=account, currency="USD", amount_minor=6_000)
    )
    # Available is settled minus reserved, so the second 6k cannot be granted.
    with pytest.raises(InsufficientCash):
        store.reserve_cash(
            CashReservation(account_id=account, currency="USD", amount_minor=6_000)
        )
    assert store.reserved_cash_minor(account, "USD") == 6_000

    store.release_cash(first.reservation_id)
    assert store.reserved_cash_minor(account, "USD") == 0

    # Releasing twice is not an error and cannot double-credit buying power.
    store.release_cash(first.reservation_id)
    assert store.reserved_cash_minor(account, "USD") == 0

    # The advisory transaction lock made the account the serialisation point, so
    # the invariant holds even though reservations are separate rows.
    assert store.verify_invariants().ok is True


# ----------------------------------------------- reconciliation & lockout state


def test_reconciliation_state_and_findings_round_trip(store: Any) -> None:
    account = f"recon-{os.getpid()}"
    run = ReconciliationRun(
        account_id=account,
        broker="sim-venue",
        adapter_version="1.2.3",
        mode=ReconciliationMode.FULL_SNAPSHOT,
    )
    finding = ReconciliationFinding(
        run_id=run.run_id,
        kind=AnomalyKind.BROKER_ONLY_EXECUTION,
        severity=ReconciliationSeverity.CRITICAL,
        subject=f"exec-{account}",
        detail="venue execution absent internally",
        internal_value=None,
        broker_value="1@100",
        scope=LockoutScope.ACCOUNT,
        broker="sim-venue",
        account_id=account,
        execution_id=f"exec-{account}",
    )

    stored = store.record_reconciliation(run, [finding])
    assert stored.ok is False
    assert stored.finding_count == 1
    assert stored.lockout_scope is LockoutScope.ACCOUNT
    assert stored.mode is ReconciliationMode.FULL_SNAPSHOT

    loaded = [f for f in store.findings(FindingStatus.OPEN) if f.account_id == account]
    assert [f.finding_id for f in loaded] == [finding.finding_id]
    assert loaded[0].broker_value == "1@100"

    runs = store.reconciliation_runs(account_id=account, limit=5)
    assert runs and runs[0].run_id == run.run_id
    assert runs[0].adapter_version == "1.2.3"

    resolved = store.resolve_finding(finding.finding_id, "alice", "confirmed with venue")
    assert resolved.status is FindingStatus.RESOLVED
    assert resolved.resolved_by == "alice"
    assert resolved.resolved_at is not None
    assert all(
        f.finding_id != finding.finding_id for f in store.findings(FindingStatus.OPEN)
    )


def test_active_lockout_is_unique_per_scope_and_subject(store: Any) -> None:
    account = f"lockout-{os.getpid()}"
    first = store.engage_lockout(
        SafetyLockout(
            scope=LockoutScope.ACCOUNT,
            subject=account,
            reason="critical reconciliation finding",
            engaged_by="reconciliation",
        )
    )
    # A second engagement of the same scope+subject is absorbed by the partial
    # unique index and returns the restriction that already exists.
    second = store.engage_lockout(
        SafetyLockout(
            scope=LockoutScope.ACCOUNT,
            subject=account,
            reason="duplicate incident",
            engaged_by="reconciliation",
        )
    )
    assert first.lockout_id == second.lockout_id
    assert len(store.active_lockouts(LockoutScope.ACCOUNT, account)) == 1

    # A human release must name an identity, and cannot be done twice.
    released = store.release_lockout(first.lockout_id, "alice", "venue confirmed")
    assert released.active is False
    assert store.active_lockouts(LockoutScope.ACCOUNT, account) == []

    with pytest.raises(FinancialStoreError):
        store.release_lockout(first.lockout_id, "  ", "no identity")


# -------------------------------------------------- position state and invariants


def test_positions_equal_reconstruction_and_tampering_is_detected(store: Any) -> None:
    account = f"pos-{os.getpid()}"
    seed_cash(store, account)
    order = accepted_order(store, account, quantity=10.0)
    store.apply_fill(partial_fill(order, 4.0, 100.0, fill_id=f"p1-{account}"))
    store.apply_fill(partial_fill(order, 1.0, 120.0, fill_id=f"p2-{account}"))

    live = {(p.symbol, round(p.quantity, 9), round(p.avg_cost, 9)) for p in store.positions(account)}
    rebuilt = {
        (p.symbol, round(p.quantity, 9), round(p.avg_cost, 9))
        for p in store.rebuild_positions(account)
    }
    assert live == rebuilt
    # 4@100 + 1@120 with 1.00 of fees spread over 5 units -> 104.20 average cost.
    assert live == {("BTC/USD", 5.0, 104.2)}

    report = store.verify_invariants()
    assert report.ok is True, [c.name for c in report.failures()]
    names = {c.name for c in report.checks}
    for required in (
        "cash_postings_balance",
        "fills_match_order_state",
        "positions_reconstructible",
        "no_overfilled_orders",
        "reservations_within_settled_cash",
        "outbox_payload_hashes",
        "order_transitions_legal",
        "order_version_matches_history",
        "critical_findings_not_silently_cleared",
        "lockouts_released_by_named_human",
        "schema_up_to_date",
    ):
        assert required in names, f"invariant {required!r} is not verified"

    # Direct database tampering must be caught, not smoothed over.
    store._execute(
        "UPDATE positions SET quantity = quantity + 7 WHERE account_id = %s AND symbol = %s",
        (account, "BTC/USD"),
    )
    tampered = store.verify_invariants()
    assert tampered.ok is False
    assert "positions_reconstructible" in {c.name for c in tampered.failures()}

    # Restore the row so the shared database stays usable for later tests; a
    # detection test must not leave the book inconsistent behind it.
    store._execute(
        "UPDATE positions SET quantity = quantity - 7 WHERE account_id = %s AND symbol = %s",
        (account, "BTC/USD"),
    )
    assert store.verify_invariants().ok is True


def test_outbox_dead_letter_path_is_durable(store: Any) -> None:
    from core.pg_financial_store import PostgresFinancialStore

    limited = PostgresFinancialStore(store.dsn, auto_migrate=True, max_outbox_attempts=2)
    try:
        # Start from a genuinely empty outbox: earlier tests in this session may
        # have left events claimed-but-unpublished, so recover those claims first
        # (exactly what a restarted publisher does) and then drain.
        limited.recover_claims_after_restart()
        drain_outbox(limited)
        assert limited.outbox_backlog() == 0

        account = f"dlq-{os.getpid()}"
        seed_cash(limited, account)
        accepted_order(limited, account, quantity=1.0)
        event = limited.outbox_pending(10)[0]

        for _ in range(2):
            claimed = limited.claim_outbox("w", limit=1)
            assert claimed and claimed[0].event_id == event.event_id
            limited.mark_failed(event.event_id, "broker unreachable", retry_delay_seconds=0)

        # max_outbox_attempts=2 was exhausted: the event is out of the queue but
        # retained as evidence rather than dropped.
        assert limited.outbox_backlog() == 0
        assert limited.claim_outbox("w-emptied", limit=1) == []
        dead = limited.dead_letters()
        assert [e.event_id for e in dead] == [event.event_id]
        assert dead[0].last_error == "broker unreachable"

        # A worker that dies holding a claim leaves the row recoverable, and the
        # dead-letter row is untouched by that recovery.
        other_account = f"dlq2-{os.getpid()}"
        seed_cash(limited, other_account)
        accepted_order(limited, other_account, quantity=1.0)
        assert limited.outbox_backlog() == 1
        assert len(limited.claim_outbox("w-dies", limit=1)) == 1
        assert limited.recover_claims_after_restart() == 1
        assert len(limited.outbox_pending(10)) == 1
        assert [e.event_id for e in limited.dead_letters()] == [event.event_id]
    finally:
        limited.close()
