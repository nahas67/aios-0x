"""V1-A financial kernel: durable state, exactly-once effects, reconstruction.

These tests encode the master-spec §61 invariants and §59 failure modes as
executable proofs: duplicate delivery, reordering, crash-in-the-middle, restart,
broker divergence and stale writers.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from communities.c5_execution.oms import DurableOrderManager
from communities.c5_execution.reconciliation import (
    BrokerExecutionView,
    BrokerOrderView,
    BrokerSnapshot,
    ReconciliationEngine,
)
from core.financial_kernel import (
    AnomalyKind,
    CashPosting,
    CashReservation,
    DurableOrder,
    Fill,
    FinancialStoreError,
    InsufficientCash,
    InvalidOrderTransition,
    OutboxEvent,
    OutboxStatus,
    OverFill,
    ReconciliationSeverity,
    SqliteFinancialStore,
    StaleOrderVersion,
    TimeInForce,
    UnbalancedPostings,
)
from core.ibor import InvestmentBookOfRecord
from schemas.contracts import OrderSide, OrderStatus, OrderType


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[SqliteFinancialStore]:
    created = SqliteFinancialStore(tmp_path / "financial.db")
    yield created
    created.close()


def _prepared(store: SqliteFinancialStore, quantity: float = 1.0) -> DurableOrder:
    oms = DurableOrderManager(store)
    order = oms.prepare_order(
        client_order_id="ord-1",
        strategy_id="strat-1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=quantity,
    )
    return oms.accept(order.internal_order_id)


def _fill(order: DurableOrder, quantity: float, price: float, fill_id: str = "f1") -> Fill:
    return Fill(
        fill_id=fill_id,
        order_id=order.internal_order_id,
        broker_execution_id=f"exec-{fill_id}",
        symbol=order.symbol,
        side=order.side,
        quantity=quantity,
        price=price,
        fee=0.5,
        executed_at=datetime.now(UTC),
    )


# --------------------------------------------------------------- atomicity (30)


def test_state_change_and_event_commit_together(store: SqliteFinancialStore) -> None:
    order = DurableOrder(
        client_order_id="atomic-1",
        strategy_id="s1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=1.0,
    )
    event = OutboxEvent(
        event_type="aios.platform.order_requested",
        producer="test",
        idempotency_key="atomic-1:requested",
        payload={"order": "atomic-1"},
    )
    with pytest.raises(RuntimeError):
        with store.transaction() as tx:
            tx.submit_order(order, (event,))
            raise RuntimeError("crash before commit")

    assert store.order_by_client_id("atomic-1") is None
    assert store.outbox_backlog() == 0

    with store.transaction() as tx:
        tx.submit_order(order, (event,))
    assert store.order_by_client_id("atomic-1") is not None
    assert store.outbox_backlog() == 1


def test_mutations_require_a_transaction(store: SqliteFinancialStore) -> None:
    with pytest.raises(FinancialStoreError):
        store._submit_order(
            DurableOrder(
                client_order_id="no-tx",
                strategy_id="s1",
                symbol="BTC/USD",
                side=OrderSide.BUY,
                quantity=1.0,
            ),
            (),
        )


# ------------------------------------------------------- outbox retry (29, 31)


def test_outbox_claim_publish_retry_and_dead_letter(tmp_path: Path) -> None:
    store = SqliteFinancialStore(tmp_path / "outbox.db", max_outbox_attempts=2)
    try:
        event = OutboxEvent(
            event_type="aios.platform.order_requested",
            producer="test",
            idempotency_key="k1",
            payload={"n": 1},
        )
        order = DurableOrder(
            client_order_id="c-outbox",
            strategy_id="s1",
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
        )
        store.submit_order(order, (event,))

        claimed = store.claim_outbox("worker-1")
        assert [e.event_id for e in claimed] == [event.event_id]
        assert claimed[0].status is OutboxStatus.PUBLISHING
        assert claimed[0].attempts == 1

        # A second worker cannot steal an in-flight event.
        assert store.claim_outbox("worker-2") == []

        store.mark_failed(event.event_id, "provider 503", retry_delay_seconds=0)
        assert store.outbox_backlog() == 1
        reclaimed = store.claim_outbox("worker-2")
        assert reclaimed[0].attempts == 2

        store.mark_failed(event.event_id, "provider 503", retry_delay_seconds=0)
        assert store.outbox_backlog() == 0
        dead = store.dead_letters()
        assert [d.event_id for d in dead] == [event.event_id]
        assert dead[0].status is OutboxStatus.DEAD_LETTER
        assert dead[0].last_error == "provider 503"
    finally:
        store.close()


def test_outbox_payload_hash_is_verifiable(store: SqliteFinancialStore) -> None:
    event = OutboxEvent(
        event_type="aios.platform.execution_completed",
        producer="test",
        idempotency_key="hash-1",
        payload={"fill": "f1", "quantity": 2.5},
    )
    assert event.payload_hash
    with pytest.raises(ValueError):
        OutboxEvent(
            event_type="aios.platform.execution_completed",
            producer="test",
            idempotency_key="hash-2",
            payload={"fill": "f1"},
            payload_hash="0" * 64,
        )


# ------------------------------------------------------- inbox idempotency (31)


def test_consumer_inbox_applies_effect_exactly_once(store: SqliteFinancialStore) -> None:
    event_id = "evt-1"
    applied: list[int] = []

    def handle() -> None:
        with store.transaction() as tx:
            if not tx.record_applied("ibor", event_id, "result-hash"):
                return
            # Double entry: the contra leg lives on a different account, so the
            # transaction balances globally while cash in `default` rises.
            tx.post_cash(
                (
                    CashPosting(
                        transaction_id="t1",
                        account_id="default",
                        amount_minor=1000,
                        description="asset credit",
                    ),
                    CashPosting(
                        transaction_id="t1",
                        account_id="external:clearing",
                        amount_minor=-1000,
                        description="equity/clearing leg",
                    ),
                )
            )
            applied.append(1)

    handle()
    handle()  # at-least-once transport: duplicate delivery
    handle()

    assert applied == [1]
    assert store.was_applied("ibor", event_id) == "result-hash"
    assert store.cash_balance_minor("default", "USD") == 1000
    assert store.cash_balance_minor("external:clearing", "USD") == -1000


# --------------------------------------------------- order state machine (23)


def test_order_lifecycle_and_transitions(store: SqliteFinancialStore) -> None:
    oms = DurableOrderManager(store)
    order = oms.prepare_order(
        client_order_id="ord-life",
        strategy_id="s1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=2.0,
        order_type=OrderType.MARKET,
    )
    assert order.status is OrderStatus.PENDING_NEW
    assert order.version == 1

    accepted = oms.accept(order.internal_order_id, broker_order_id="broker-9")
    assert accepted.status is OrderStatus.ACCEPTED
    assert accepted.version == 2

    assert oms.apply_fill(_fill(order, 1.0, 100.0, "p1")) is True
    partial = store.order(order.internal_order_id)
    assert partial is not None
    assert partial.status is OrderStatus.PARTIALLY_FILLED
    assert partial.filled_quantity == 1.0

    assert oms.apply_fill(_fill(order, 1.0, 110.0, "p2")) is True
    filled = store.order(order.internal_order_id)
    assert filled is not None
    assert filled.status is OrderStatus.FILLED
    assert filled.filled_quantity == 2.0
    assert filled.avg_fill_price == pytest.approx(105.0, abs=1e-6)

    hops = [t.to_status for t in store.transitions(order.internal_order_id)]
    assert hops == [
        OrderStatus.PENDING_NEW,
        OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
    ]
    assert store.verify_invariants().ok


def test_order_submission_is_idempotent_by_client_order_id(store: SqliteFinancialStore) -> None:
    oms = DurableOrderManager(store)
    first = oms.prepare_order(
        client_order_id="dup-ord",
        strategy_id="s1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=1.0,
    )
    second = oms.prepare_order(
        client_order_id="dup-ord",
        strategy_id="s1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=1.0,
    )
    assert first.internal_order_id == second.internal_order_id
    assert len(store.orders()) == 1
    assert len(store.transitions(first.internal_order_id)) == 1


def test_illegal_transition_is_refused(store: SqliteFinancialStore) -> None:
    oms = DurableOrderManager(store)
    order = oms.prepare_order(
        client_order_id="illegal",
        strategy_id="s1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=1.0,
    )
    with pytest.raises(InvalidOrderTransition):
        store.transition_order(order.internal_order_id, OrderStatus.FILLED, "test")
    assert store.order(order.internal_order_id).status is OrderStatus.PENDING_NEW  # type: ignore[union-attr]


def test_stale_version_cannot_overwrite_newer_state(store: SqliteFinancialStore) -> None:
    order = _prepared(store)
    with pytest.raises(StaleOrderVersion):
        store.transition_order(
            order.internal_order_id,
            OrderStatus.CANCELLED,
            "slow-worker",
            expected_version=1,
        )
    assert store.order(order.internal_order_id).status is OrderStatus.ACCEPTED  # type: ignore[union-attr]


def test_expired_and_cancelled_orders_are_terminal(store: SqliteFinancialStore) -> None:
    oms = DurableOrderManager(store)
    order = oms.prepare_order(
        client_order_id="exp-1",
        strategy_id="s1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=1.0,
        order_type=OrderType.LIMIT,
        limit_price=10.0,
        time_in_force=TimeInForce.DAY,
    )
    expired = oms.expire(order.internal_order_id)
    assert expired.status is OrderStatus.EXPIRED
    with pytest.raises(InvalidOrderTransition):
        oms.cancel(order.internal_order_id)


# --------------------------------------------------- exactly-once fills (31, 61)


def test_duplicate_fill_is_not_applied_twice(store: SqliteFinancialStore) -> None:
    order = _prepared(store)
    fill = _fill(order, 1.0, 100.0)
    assert store.apply_fill(fill) is True
    assert store.apply_fill(fill) is False

    positions = store.positions()
    assert len(positions) == 1
    assert positions[0].quantity == 1.0
    assert len(store.fills()) == 1
    assert store.order(order.internal_order_id).filled_quantity == 1.0  # type: ignore[union-attr]
    assert store.verify_invariants().ok


def test_duplicate_fill_detected_by_broker_execution_id(store: SqliteFinancialStore) -> None:
    order = _prepared(store)
    first = _fill(order, 0.4, 100.0, "b1")
    replay = first.model_copy(update={"fill_id": "different-local-id"})
    assert store.apply_fill(first) is True
    assert store.apply_fill(replay) is False
    assert store.positions()[0].quantity == 0.4


def test_overfill_is_refused_without_side_effects(store: SqliteFinancialStore) -> None:
    order = _prepared(store, quantity=1.0)
    with pytest.raises(OverFill):
        store.apply_fill(_fill(order, 2.0, 100.0))
    assert store.fills() == []
    assert store.positions() == []
    assert store.verify_invariants().ok


def test_fill_side_must_match_order(store: SqliteFinancialStore) -> None:
    order = _prepared(store)
    wrong = _fill(order, 1.0, 100.0).model_copy(update={"side": OrderSide.SELL})
    with pytest.raises(FinancialStoreError):
        store.apply_fill(wrong)


# ------------------------------------------------------------ cash ledger (28)


def test_unbalanced_cash_postings_are_refused(store: SqliteFinancialStore) -> None:
    with pytest.raises(UnbalancedPostings):
        store.post_cash(
            (
                CashPosting(transaction_id="tx-1", amount_minor=-500, description="debit"),
                CashPosting(transaction_id="tx-1", amount_minor=400, description="credit"),
            )
        )
    assert store.cash_balance_minor("default", "USD") == 0


def test_reservations_gate_buying_power(store: SqliteFinancialStore) -> None:
    store.post_cash(
        (
            CashPosting(
                transaction_id="fund",
                account_id="default",
                amount_minor=10000,
                description="cash in",
            ),
            CashPosting(
                transaction_id="fund",
                account_id="external:wire",
                amount_minor=-10000,
                description="funding source",
            ),
        )
    )
    store.reserve_cash(CashReservation(amount_minor=4000, reason="order 1"))
    assert store.cash_balance_minor("default", "USD") == 10000
    assert store.reserved_cash_minor("default", "USD") == 4000

    with pytest.raises(InsufficientCash):
        store.reserve_cash(CashReservation(amount_minor=7000, reason="order 2"))

    reservation = store.reserve_cash(CashReservation(amount_minor=5000, reason="order 3"))
    store.release_cash(reservation.reservation_id)
    assert store.reserved_cash_minor("default", "USD") == 4000


# --------------------------------------------------------- IBOR + restart (§27)


def test_book_snapshot_is_honest_about_missing_marks(store: SqliteFinancialStore) -> None:
    order = _prepared(store)
    store.apply_fill(_fill(order, 1.0, 100.0))
    store.post_cash(
        (
            CashPosting(
                transaction_id="dep",
                account_id="default",
                amount_minor=100000,
                description="cash in",
            ),
            CashPosting(
                transaction_id="dep",
                account_id="external:wire",
                amount_minor=-100000,
                description="funding source",
            ),
        )
    )

    blind = InvestmentBookOfRecord(store, mark_provider=None)
    snapshot = blind.snapshot()
    assert snapshot.marks_complete is False
    assert snapshot.nav is None
    assert snapshot.positions[0].market_value is None
    assert snapshot.cash[0].settled_minor == 100000

    marked = InvestmentBookOfRecord(store, mark_provider=lambda symbol: 120.0)
    live = marked.snapshot()
    assert live.marks_complete is True
    assert live.position_for("BTC/USD").market_value == pytest.approx(120.0)  # type: ignore[union-attr]
    assert live.nav == pytest.approx(1000.0 + 120.0, abs=1e-6)
    assert live.unrealized_pnl == pytest.approx(19.5, abs=1e-6)
    assert live.open_orders == []


def test_book_survives_restart_and_rebuilds_from_fills(tmp_path: Path) -> None:
    first = SqliteFinancialStore(tmp_path / "restart.db")
    oms = DurableOrderManager(first)
    order = oms.prepare_order(
        client_order_id="restart-1",
        strategy_id="s1",
        symbol="ETH/USD",
        side=OrderSide.BUY,
        quantity=2.0,
    )
    oms.accept(order.internal_order_id)
    first.apply_fill(_fill(order, 1.0, 50.0, "r1"))
    first.close()

    # Process death happened here: the open order and its fill must survive.
    second = SqliteFinancialStore(tmp_path / "restart.db")
    try:
        recovered = DurableOrderManager(second).recover_open_orders()
        assert [o.client_order_id for o in recovered] == ["restart-1"]
        assert recovered[0].status is OrderStatus.PARTIALLY_FILLED
        assert second.positions()[0].quantity == 1.0

        book = InvestmentBookOfRecord(second, mark_provider=lambda _s: 60.0)
        assert book.rebuild().ok is True
        snapshot = book.snapshot()
        assert snapshot.position_for("ETH/USD").quantity == 1.0  # type: ignore[union-attr]
        assert second.verify_invariants().ok
    finally:
        second.close()


def test_invariants_detect_tampered_positions(store: SqliteFinancialStore) -> None:
    order = _prepared(store)
    store.apply_fill(_fill(order, 1.0, 100.0))
    assert store.verify_invariants().ok

    # Simulate corruption of live state that the fill ledger contradicts.
    store._conn.execute("UPDATE positions SET quantity = 99.0")
    store._conn.commit()
    report = store.verify_invariants()
    assert report.ok is False
    assert "positions_reconstructible" in {c.name for c in report.failures()}


# ------------------------------------------------------- reconciliation (§26)


def test_reconciliation_flags_unknown_order_and_cash_mismatch(store: SqliteFinancialStore) -> None:
    order = _prepared(store)
    store.apply_fill(_fill(order, 1.0, 100.0))
    engine = ReconciliationEngine(store)

    snapshot = BrokerSnapshot(
        orders=[
            BrokerOrderView(
                broker_order_id="b-1",
                client_order_id="ord-1",
                symbol="BTC/USD",
                side=OrderSide.BUY,
                quantity=1.0,
                filled_quantity=1.0,
                status=OrderStatus.FILLED,
            ),
            BrokerOrderView(
                broker_order_id="b-ghost",
                client_order_id="ghost-order",
                symbol="BTC/USD",
                side=OrderSide.BUY,
                quantity=1.0,
                filled_quantity=0.0,
                status=OrderStatus.ACCEPTED,
            ),
        ],
        executions=[
            BrokerExecutionView(
                "exec-f1", "ord-1", 1.0, 100.0, symbol="BTC/USD", side=OrderSide.BUY, fee=0.5
            )
        ],
        positions={"BTC/USD": 2.0},
        cash_minor=1234,
    )
    result = engine.reconcile(snapshot)
    kinds = {f.kind for f in result.findings}
    assert AnomalyKind.UNKNOWN_BROKER_ORDER in kinds
    assert AnomalyKind.POSITION_MISMATCH in kinds
    assert AnomalyKind.CASH_MISMATCH in kinds
    assert result.requires_lockout is True
    assert result.run.ok is False
    assert len(store.findings()) == len(result.findings)


def test_matching_execution_identity_is_a_match_not_a_discrepancy(
    store: SqliteFinancialStore,
) -> None:
    """A broker execution that exists internally WITH matching economics is a
    successful match. V1-A.1 reported this as DUPLICATE_FILL, which turned every
    correct authoritative snapshot into an incident."""
    order = _prepared(store)
    store.apply_fill(_fill(order, 1.0, 100.0))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[
                BrokerOrderView(
                    broker_order_id="b-1",
                    client_order_id="ord-1",
                    symbol="BTC/USD",
                    side=OrderSide.BUY,
                    quantity=1.0,
                    filled_quantity=1.0,
                    status=OrderStatus.FILLED,
                )
            ],
            executions=[
                BrokerExecutionView(
                    "exec-f1",
                    "ord-1",
                    1.0,
                    100.0,
                    symbol="BTC/USD",
                    side=OrderSide.BUY,
                    fee=0.5,
                )
            ],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    assert result.matches.matched == ["exec-f1"]
    assert result.matches.broker_only == []
    assert result.matches.internal_only == []
    assert result.findings == []
    assert result.ok is True
    assert result.requires_lockout is False
    assert AnomalyKind.DUPLICATE_FILL not in {f.kind for f in result.findings}


def test_clean_reconciliation_and_human_resolution(store: SqliteFinancialStore) -> None:
    order = _prepared(store)
    store.apply_fill(_fill(order, 1.0, 100.0))
    engine = ReconciliationEngine(store)
    clean = engine.reconcile(
        BrokerSnapshot(
            orders=[
                BrokerOrderView(
                    broker_order_id="b-1",
                    client_order_id="ord-1",
                    symbol="BTC/USD",
                    side=OrderSide.BUY,
                    quantity=1.0,
                    filled_quantity=1.0,
                    status=OrderStatus.FILLED,
                )
            ],
            executions=[
                BrokerExecutionView(
                    "exec-f1",
                    "ord-1",
                    1.0,
                    100.0,
                    symbol="BTC/USD",
                    side=OrderSide.BUY,
                    fee=0.5,
                )
            ],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    assert clean.ok is True
    assert clean.findings == []

    dirty = engine.reconcile(
        BrokerSnapshot(
            orders=[
                BrokerOrderView(
                    broker_order_id="b-1",
                    client_order_id="ord-1",
                    symbol="BTC/USD",
                    side=OrderSide.BUY,
                    quantity=1.0,
                    filled_quantity=1.0,
                    status=OrderStatus.FILLED,
                )
            ],
            executions=[
                BrokerExecutionView(
                    "exec-f1",
                    "ord-1",
                    1.0,
                    100.0,
                    symbol="BTC/USD",
                    side=OrderSide.BUY,
                    fee=0.5,
                )
            ],
            positions={"BTC/USD": 5.0},
            cash_minor=0,
        )
    )
    finding = dirty.critical()[0]
    assert engine.open_findings()
    with pytest.raises(PermissionError):
        engine.resolve(finding.finding_id, "", "RISK_ADMIN", "no identity")
    with pytest.raises(PermissionError):
        engine.resolve(finding.finding_id, "operator:viewer", "VIEWER", "not my call")

    resolved = engine.resolve(
        finding.finding_id, "operator:principal", "RISK_ADMIN", "broker export lagged"
    )
    assert resolved.resolved_by == "operator:principal"
    assert engine.open_findings() == []
    assert any(
        e.severity is ReconciliationSeverity.CRITICAL for e in dirty.findings
    )


class _FlakySink:
    def __init__(self, fail_first: bool = False) -> None:
        self.seen: list[str] = []
        self.fail_first = fail_first

    def __call__(self, event: OutboxEvent) -> None:
        if self.fail_first:
            self.fail_first = False
            raise RuntimeError("sink unavailable")
        self.seen.append(event.event_id)


def test_outbox_publisher_retries_without_losing_events(store: SqliteFinancialStore) -> None:
    from core.financial_kernel import OutboxPublisher

    order = DurableOrder(
        client_order_id="pub-1",
        strategy_id="s1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=1.0,
    )
    event = OutboxEvent(
        event_type="aios.platform.order_requested",
        producer="test",
        idempotency_key="pub-1:requested",
        payload={"order": "pub-1"},
    )
    store.submit_order(order, (event,))

    sink = _FlakySink(fail_first=True)
    publisher = OutboxPublisher(store, sink)
    published, failed = publisher.drain()
    assert (published, failed) == (0, 1)
    assert store.outbox_backlog() == 1  # the event survived the sink failure
    assert store.dead_letters() == []

    # Retry after the backoff window: the sink sees it exactly once.
    store.mark_failed(event.event_id, "retry now", retry_delay_seconds=0)
    published, failed = publisher.drain()
    assert (published, failed) == (1, 0)
    assert sink.seen == [event.event_id]
    assert store.outbox_backlog() == 0
    assert publisher.drain() == (0, 0)


# --------------------------------------------- composition-root integration


def test_replay_runner_persists_durable_financial_state(tmp_path: Path) -> None:
    """The live order path writes durable state and the book survives restart."""
    import asyncio

    from core.config import Settings
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    base = tmp_path
    dataset_dir = base / "golden"
    write_dataset(dataset_dir, symbols=["BTC/USD"], total_bars=90)
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": dataset_dir / "BTC_USD_1d.csv"},
        store_path=base / "run.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
        settings=Settings(model_provider="none", autonomy_mode="AUTONOMOUS"),
    )
    summary = asyncio.run(runner.run())

    assert summary.trades_closed >= 1
    assert summary.durable_orders >= summary.trades_closed  # entries + exits
    assert summary.durable_fills >= 1
    assert summary.durable_fills <= summary.durable_orders
    assert summary.durable_open_orders == 0, [
        (o.client_order_id, str(o.status), o.quantity, o.filled_quantity)
        for o in runner.financial_store.open_orders()
    ]
    assert summary.financial_invariants_ok is True
    assert summary.ibor_rebuild_ok is True

    store = runner.financial_store
    assert len(store.fills()) == len(
        [o for o in store.orders() if o.filled_quantity > 0]
    )
    # Every entry was closed by the horizon-end force close, so the book is flat
    # and realized P&L is exactly the sum of the closed trades.
    assert all(abs(p.quantity) < 1e-9 for p in store.positions())
    assert pytest.approx(sum(p.realized_pnl for p in store.positions()), abs=1.0) == (
        summary.cumulative_pnl
    )

    # Restart proof: a fresh process reading the same file sees the same book.
    reopened = SqliteFinancialStore(base / "run.db.financial.db")
    try:
        assert len(reopened.fills()) == summary.durable_fills
        assert reopened.verify_invariants().ok is True
        book = InvestmentBookOfRecord(reopened, mark_provider=lambda _s: 100.0)
        assert book.rebuild().ok is True

        # A duplicated venue callback cannot change the book.
        live_fills = reopened.fills()
        if live_fills:
            assert reopened.apply_fill(live_fills[0]) is False
            assert len(reopened.fills()) == len(live_fills)
            assert reopened.verify_invariants().ok is True
    finally:
        reopened.close()


class _FailingPublisherSink:
    def __call__(self, event: OutboxEvent) -> None:
        raise RuntimeError("downstream unavailable")


def test_replay_runner_outbox_is_durable_for_the_publisher(store: SqliteFinancialStore) -> None:
    """Every durable financial mutation left exactly one outbox envelope."""
    from core.financial_kernel import OutboxPublisher

    order = _prepared(store)
    DurableOrderManager(store).apply_fill(_fill(order, 1.0, 100.0))
    assert store.outbox_backlog() == 2  # order requested + execution completed

    publisher = OutboxPublisher(store, _FailingPublisherSink())
    assert publisher.drain() == (0, 2)
    assert store.outbox_backlog() == 2  # nothing is lost when the sink is down


def test_out_of_order_fill_delivery_keeps_book_correct(store: SqliteFinancialStore) -> None:
    """Reordered venue callbacks still produce one correct final book."""
    order = _prepared(store, quantity=3.0)
    fills = [_fill(order, 1.0, 100.0, "o1"), _fill(order, 1.0, 101.0, "o2"), _fill(order, 1.0, 102.0, "o3")]
    delivered = [fills[2], fills[0], fills[2], fills[1], fills[0]]
    for fill in delivered:
        store.apply_fill(fill)

    position = store.positions()[0]
    assert position.quantity == 3.0
    final = store.order(order.internal_order_id)
    assert final is not None and final.status is OrderStatus.FILLED
    assert store.verify_invariants().ok
    assert InvestmentBookOfRecord(store).rebuild().ok is True
    assert len(store.fills()) == 3
