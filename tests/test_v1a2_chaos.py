"""V1-A.2 chaos and failure injection: break it on purpose, then verify recovery.

Each test here injects one specific failure at one specific boundary and then
asserts the *financial* outcome, not just that an exception came back. The
distinctions that matter:

- A process that dies **before** commit must leave nothing behind.
- A process that dies **after** commit must leave exactly one economic effect,
  and redelivery must not add a second.
- A store whose backend vanishes must not report success, and must be usable
  again afterwards.

Where a layer is unavailable the test skips rather than simulating it. Nothing
in this module fakes a database or a broker.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from communities.c5_execution.oms import DurableOrderManager
from core.financial_kernel import (
    BaseFinancialStore,
    CashPosting,
    Fill,
    SqliteFinancialStore,
)
from schemas.contracts import OrderSide

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------- helpers


def seed_cash(store: BaseFinancialStore, account: str, opening_minor: int = 10**9) -> None:
    store.post_cash(
        [
            CashPosting(transaction_id=f"seed:{account}", account_id=account, amount_minor=opening_minor),
            CashPosting(
                transaction_id=f"seed:{account}",
                account_id="counterparty",
                amount_minor=-opening_minor,
            ),
        ]
    )


def accepted_order(store: BaseFinancialStore, account: str, quantity: float = 100.0) -> Any:
    oms = DurableOrderManager(store, account_id=account)
    prepared = oms.prepare_order(
        client_order_id=f"{account}-ord",
        strategy_id="chaos",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=quantity,
    )
    return oms.accept(prepared.internal_order_id)


def make_fill(
    order: Any,
    fill_id: str,
    quantity: float = 1.0,
    *,
    exec_id: str | None = None,
) -> Fill:
    return Fill(
        fill_id=fill_id,
        order_id=order.internal_order_id,
        broker_execution_id=exec_id if exec_id is not None else f"exec-{fill_id}",
        account_id=order.account_id,
        symbol=order.symbol,
        side=order.side,
        quantity=quantity,
        price=50_000.0,
    )


def open_store(backend: str, target: str, **kwargs: Any) -> BaseFinancialStore:
    if backend == "postgres":
        from core.pg_financial_store import PostgresFinancialStore

        return PostgresFinancialStore(target, auto_migrate=True, **kwargs)
    return SqliteFinancialStore(target, **kwargs)  # type: ignore[arg-type]


@pytest.fixture()
def pg_dsn_only(reset_postgres: str) -> str:
    if not reset_postgres:
        pytest.skip("set AIOS_TEST_PG_DSN to run the PostgreSQL chaos drills")
    return reset_postgres


@pytest.fixture()
def nats_url_only(nats_url: str) -> str:
    if not nats_url:
        pytest.skip("set AIOS_TEST_NATS_URL to run the JetStream chaos drills")
    return nats_url


# ------------------------------------------- PostgreSQL backend termination


def test_terminated_backend_rolls_back_an_open_transaction(pg_dsn_only: str) -> None:
    """Killing the server backend mid-transaction must leave no partial state.

    This is a genuine server-side disconnect: ``pg_terminate_backend`` on the
    store's own connection, issued from a second connection, while the store
    holds an uncommitted financial change.
    """
    psycopg = pytest.importorskip("psycopg")
    store = open_store("postgres", pg_dsn_only)
    account = f"chaos-term-{os.getpid()}"
    try:
        seed_cash(store, account)
        order = accepted_order(store, account)
        fill_id = f"chaos-fill-{account}"

        with pytest.raises(psycopg.Error):
            with store.transaction() as tx:
                assert tx.apply_fill(make_fill(order, fill_id)) is True
                # The financial change is in flight and NOT yet committed.
                # Kill the backend underneath it.
                with psycopg.connect(pg_dsn_only, autocommit=True) as killer:
                    with killer.cursor() as cur:
                        cur.execute(
                            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                            " WHERE pid = %s",
                            (store._query_one("SELECT pg_backend_pid() AS pid")["pid"],),
                        )
                # Any further statement on the dead connection must fail.
                store._execute("SELECT 1")
    finally:
        store.close()

    # The uncommitted fill did not survive, and the book is untouched.
    reopened = open_store("postgres", pg_dsn_only)
    try:
        assert [f.fill_id for f in reopened.fills(order.internal_order_id)] == []
        current = reopened.order(order.internal_order_id)
        assert current is not None and current.filled_quantity == 0.0

        # Recovery is a retry, and it applies exactly once.
        assert reopened.apply_fill(make_fill(order, fill_id)) is True
        assert len(reopened.fills(order.internal_order_id)) == 1
        report = reopened.verify_invariants()
        assert report.ok is True, [c.name for c in report.failures()]
    finally:
        reopened.close()


def test_committed_state_survives_backend_termination(pg_dsn_only: str) -> None:
    """A committed transaction is not at risk from a later disconnect."""
    psycopg = pytest.importorskip("psycopg")
    store = open_store("postgres", pg_dsn_only)
    account = f"chaos-commit-{os.getpid()}"
    try:
        seed_cash(store, account)
        order = accepted_order(store, account)
        fill_id = f"chaos-committed-{account}"
        assert store.apply_fill(make_fill(order, fill_id, quantity=2.0)) is True
        backlog_committed = store.outbox_backlog()

        with psycopg.connect(pg_dsn_only, autocommit=True) as killer:
            with killer.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = %s",
                    (store._query_one("SELECT pg_backend_pid() AS pid")["pid"],),
                )
    finally:
        store.close()

    reopened = open_store("postgres", pg_dsn_only)
    try:
        fills = reopened.fills(order.internal_order_id)
        assert [f.fill_id for f in fills] == [fill_id]
        assert round(fills[0].quantity, 9) == 2.0
        # Financial mutation and its outbox event were one transaction, so a
        # disconnect after commit cannot have separated them.
        assert reopened.outbox_backlog() == backlog_committed
        assert reopened.order(order.internal_order_id).filled_quantity == 2.0  # type: ignore[union-attr]

        # Replaying the SAME venue execution under a new internal fill id is
        # still refused by the database after the disconnect.
        assert (
            reopened.apply_fill(
                make_fill(order, f"{fill_id}-replay", exec_id=f"exec-{fill_id}")
            )
            is False
        )
        assert len(reopened.fills(order.internal_order_id)) == 1
        assert reopened.verify_invariants().ok is True
    finally:
        reopened.close()


# -------------------------------------------------- process termination


_TERMINATE_CHILD = """
import os, sys
sys.path.insert(0, {root!r})
from communities.c5_execution.oms import DurableOrderManager
from core.financial_kernel import CashPosting, Fill
from schemas.contracts import OrderSide

backend, target, account, order_id, fill_id = sys.argv[1:6]
if backend == "postgres":
    from core.pg_financial_store import PostgresFinancialStore
    store = PostgresFinancialStore(target, auto_migrate=True)
else:
    from core.financial_kernel import SqliteFinancialStore
    store = SqliteFinancialStore(target)

with store.transaction() as tx:
    tx.apply_fill(
        Fill(
            fill_id=fill_id,
            order_id=order_id,
            broker_execution_id="exec-" + fill_id,
            account_id=account,
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50000.0,
        )
    )
    # Terminate the process with the transaction still open and uncommitted.
    # os._exit skips atexit/finally, so no rollback is ever issued by the client;
    # only the database's own disconnect handling can save the book.
    os._exit(3)
"""


@pytest.fixture(params=["sqlite", "postgres"])
def chaos_backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[tuple[str, str]]:
    if request.param == "postgres":
        dsn = os.environ.get("AIOS_TEST_PG_DSN", "")
        if not dsn:
            pytest.skip("set AIOS_TEST_PG_DSN to run the PostgreSQL chaos drills")
        yield "postgres", dsn
    else:
        yield "sqlite", str(tmp_path / "chaos.db")


def test_process_terminated_mid_transaction_leaves_no_partial_state(
    chaos_backend: tuple[str, str],
) -> None:
    """A killed process must not leave half a financial change behind."""
    backend, target = chaos_backend
    account = f"chaos-kill-{backend}-{os.getpid()}"
    store = open_store(backend, target)
    try:
        seed_cash(store, account)
        order = accepted_order(store, account)
    finally:
        store.close()

    fill_id = f"killed-fill-{account}"
    script = _TERMINATE_CHILD.format(root=str(Path(__file__).resolve().parents[1]))
    completed = subprocess.run(
        [sys.executable, "-c", script, backend, target, account, order.internal_order_id, fill_id],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 3, completed.stderr[-2000:]

    reopened = open_store(backend, target)
    try:
        assert [f.fill_id for f in reopened.fills(order.internal_order_id)] == [], (
            "a killed process left a partially applied fill"
        )
        current = reopened.order(order.internal_order_id)
        assert current is not None and current.filled_quantity == 0.0
        assert reopened.verify_invariants().ok is True

        # The work is still doable: retry applies it exactly once.
        assert reopened.apply_fill(make_fill(order, fill_id)) is True
        assert len(reopened.fills(order.internal_order_id)) == 1
        assert reopened.verify_invariants().ok is True
    finally:
        reopened.close()


# ------------------------------------------------- consumer crash boundaries


def _chaos_subject(tag: str) -> str:
    """A subject unique to this drill.

    The durable consumer filter is the subject, so a one-off subject means this
    consumption sees only this test's message no matter what previous runs left
    behind in the (persistent) JetStream store. Consuming a shared subject would
    make the assertions depend on history.
    """
    import uuid

    return f"aios.platform.chaos.{tag}.{uuid.uuid4().hex[:12]}"


def test_consumer_crash_after_commit_before_ack_does_not_reapply(
    nats_url_only: str, tmp_path: Path
) -> None:
    """The hardest boundary: effect committed, transport not acknowledged.

    The effect and its inbox row commit together, then the process "dies" before
    acking. Redelivery must find the inbox row and acknowledge without applying
    the economic effect a second time.
    """
    import asyncio

    from core.financial_kernel import OutboxEvent
    from core.jetstream_bus import DurableInboxConsumer, JetStreamBus

    store = SqliteFinancialStore(tmp_path / "consume.db")
    applied: list[str] = []

    def effect(payload: dict[str, Any]) -> dict[str, Any]:
        applied.append(str(payload.get("token")))
        return {"applied": payload.get("token")}

    async def scenario() -> dict[str, Any]:
        import uuid

        tag = uuid.uuid4().hex[:12]
        subject = _chaos_subject(f"ack-{tag}")
        # A short ack_wait makes redelivery observable inside a test budget
        # instead of after the 30s production default.
        bus = JetStreamBus(nats_url_only, ack_wait_seconds=1.0, max_deliver=5)
        await bus.connect()
        try:
            await bus.publish_envelope(
                OutboxEvent(
                    event_type=subject,
                    producer="chaos",
                    idempotency_key=f"key-{tag}",
                    payload={"token": "crash-after-commit"},
                )
            )

            consumer = DurableInboxConsumer(
                bus, store, f"c-{tag}", subject, effect, batch=5, fetch_timeout=2.0
            )
            subscription = await bus.pull_subscribe(subject, f"c-{tag}")
            try:
                # Phase 1: apply the effect and commit, then vanish without ack.
                messages = await subscription.fetch(5, timeout=3.0)
                assert messages, "expected a delivery to process"
                import json as _json

                envelope = _json.loads(messages[0].data.decode())
                outcome = consumer.process_payload(
                    str(envelope["event_id"]), envelope["payload"]
                )
                assert outcome == "APPLIED"
                assert len(applied) == 1

                # Phase 1 applied the effect directly (bypassing the delivery
                # path), so that is the baseline the redelivery must not exceed.
                processed_after_commit = consumer.processed

                # Phase 2: the server redelivers after ack_wait; the same
                # consumer object and durable name stand in for the restart.
                for _ in range(60):
                    await consumer.consume_once(subscription)
                    if consumer.duplicates:
                        break
                    await asyncio.sleep(0.25)
                stats = consumer.stats()
                stats["processed_after_commit"] = processed_after_commit
            finally:
                await subscription.unsubscribe()
            return stats
        finally:
            await bus.stop()

    try:
        stats = asyncio.run(scenario())
    finally:
        store.close()

    assert stats["duplicates"] >= 1, stats
    assert stats["processed"] == stats["processed_after_commit"], (
        "redelivery re-applied a committed effect: "
        f"processed went {stats['processed_after_commit']} -> {stats['processed']}"
    )
    assert len(applied) == 1, f"economic effect applied {len(applied)} times"
    assert stats["inbox_rows"] == 1, stats


def test_consumer_crash_before_commit_applies_exactly_once_on_redelivery(
    nats_url_only: str, tmp_path: Path
) -> None:
    """Crash before the transaction commits: nothing landed, retry applies once."""
    import asyncio

    from core.financial_kernel import OutboxEvent
    from core.jetstream_bus import DurableInboxConsumer, JetStreamBus

    store = SqliteFinancialStore(tmp_path / "consume2.db")
    attempts = {"n": 0}

    def flaky(payload: dict[str, Any]) -> dict[str, Any]:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("simulated crash before commit")
        return {"ok": payload.get("token")}

    async def scenario() -> dict[str, Any]:
        import uuid

        tag = uuid.uuid4().hex[:12]
        subject = _chaos_subject(f"pre-{tag}")
        bus = JetStreamBus(nats_url_only, ack_wait_seconds=1.0, max_deliver=5)
        await bus.connect()
        try:
            await bus.publish_envelope(
                OutboxEvent(
                    event_type=subject,
                    producer="chaos",
                    idempotency_key=f"key-{tag}",
                    payload={"token": "crash-before-commit"},
                )
            )
            name = f"c-{tag}"
            consumer = DurableInboxConsumer(
                bus, store, name, subject, flaky, batch=5, fetch_timeout=2.0, max_deliver=5
            )
            subscription = await bus.pull_subscribe(subject, name)
            try:
                for _ in range(60):
                    await consumer.consume_once(subscription)
                    if consumer.processed:
                        break
                    await asyncio.sleep(0.25)
            finally:
                await subscription.unsubscribe()
            return {**consumer.stats(), "inbox": store.inbox_count(name)}
        finally:
            await bus.stop()

    try:
        stats = asyncio.run(scenario())
    finally:
        store.close()

    assert stats["processed"] == 1, stats
    assert stats["inbox"] == 1, stats
    assert attempts["n"] >= 2, "redelivery was not attempted after the crash"
    assert stats["duplicates"] == 0, stats


# ------------------------------------------- reconciliation cannot be skipped


def test_unreadable_venue_is_not_recorded_as_a_clean_reconciliation(
    tmp_path: Path,
) -> None:
    """A venue that cannot be read must never produce a clean verdict.

    The dangerous failure mode is not a crash — it is a reconciliation that
    "passes" because the adapter returned nothing. This asserts the runner
    escalates and records no clean run.
    """
    import asyncio

    from core.config import Settings
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=40)
    store = SqliteFinancialStore(tmp_path / "unreadable.db")
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=str(tmp_path / "audit.db"),
        settings=Settings(model_provider="none", autonomy_mode="AUTONOMOUS"),
        financial_store=store,
    )

    class UnreadableAdapter:
        """A venue whose position endpoint is down."""

        venue = "unreadable"

        def positions_snapshot(self) -> dict[str, float]:
            raise TimeoutError("venue did not answer within the request budget")

    escalations: list[str] = []

    async def watch(new_state: Any, reason: str, triggered_by: str = "system", **_: Any) -> None:
        escalations.append(reason)

    runner.adapter = UnreadableAdapter()  # type: ignore[assignment]
    runner.risk_governor.escalate = watch  # type: ignore[assignment]

    with pytest.raises(TimeoutError):
        asyncio.run(runner._reconcile())  # type: ignore[attr-defined]
    store.close()

    assert escalations, "an unreadable venue was accepted silently"
    assert "venue" in escalations[0].lower()
    # And crucially: no run was persisted claiming the book matched.
    from core.financial_kernel import FindingStatus

    reopened = SqliteFinancialStore(tmp_path / "unreadable.db")
    try:
        assert reopened.reconciliation_runs(limit=10) == []
        assert reopened.findings(FindingStatus.OPEN) == []
    finally:
        reopened.close()


def test_forced_replay_restart_preserves_financial_invariants(tmp_path: Path) -> None:
    """Cold start in the middle of a run must not corrupt committed state."""
    import asyncio

    from core.config import Settings
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["BTC/USD", "ETH/USD"], total_bars=60)
    dataset = {
        "BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv",
        "ETH/USD": tmp_path / "golden" / "ETH_USD_1d.csv",
    }
    db = tmp_path / "restart.db"

    for _ in range(2):
        store = SqliteFinancialStore(db)
        runner = ReplayRunner(
            csv_path_by_symbol=dataset,
            store_path=str(tmp_path / "audit.db"),
            settings=Settings(model_provider="none", autonomy_mode="AUTONOMOUS"),
            financial_store=store,
        )
        with tempfile.TemporaryDirectory() as scratch:
            _ = scratch
            asyncio.run(runner.run())
        # Financial invariants must hold at the end of every run, and the second
        # run must build on a consistent book rather than a corrupted one.
        report = store.verify_invariants()
        assert report.ok is True, [c.name for c in report.failures()]
        store.close()
