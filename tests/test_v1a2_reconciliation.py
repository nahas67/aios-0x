"""V1-A.2 reconciliation: identity matching, the window contract, and lockout.

The V1-A.1 engine counted fills and called a correct broker/internal match a
``DUPLICATE_FILL``. These tests pin the corrected semantics: matching is set
algebra over execution identities, economics conflicts are their own anomaly, and
absence is only asserted when the requested window supports it.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from communities.c5_execution.oms import DurableOrderManager
from communities.c5_execution.reconciliation import (
    BrokerExecutionView,
    BrokerOrderView,
    BrokerSnapshot,
    ReconciliationEngine,
    ReconciliationWindow,
)
from core.financial_kernel import (
    AnomalyKind,
    DurableOrder,
    Fill,
    LockoutScope,
    ReconciliationMode,
    ReconciliationSeverity,
    SqliteFinancialStore,
)
from core.safety_plane import SafetyAuthorizationError, SafetyPlane
from schemas.contracts import OrderSide, OrderStatus

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def store(tmp_path: Path) -> SqliteFinancialStore:
    created = SqliteFinancialStore(tmp_path / "financial.db")
    yield created
    created.close()


def _order(store: SqliteFinancialStore, quantity: float = 10.0) -> DurableOrder:
    oms = DurableOrderManager(store)
    order = oms.prepare_order(
        client_order_id="ord-1",
        strategy_id="strat-1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=quantity,
    )
    return oms.accept(order.internal_order_id)


def _fill(
    order: DurableOrder,
    quantity: float,
    price: float,
    *,
    fill_id: str,
    exec_id: str,
    fee: float = 0.0,
    executed_at: datetime = T0,
) -> Fill:
    return Fill(
        fill_id=fill_id,
        order_id=order.internal_order_id,
        broker_execution_id=exec_id,
        symbol=order.symbol,
        side=order.side,
        quantity=quantity,
        price=price,
        fee=fee,
        executed_at=executed_at,
    )


def _broker_order(
    *,
    client_order_id: str = "ord-1",
    symbol: str = "BTC/USD",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 10.0,
    filled_quantity: float = 0.0,
    status: OrderStatus = OrderStatus.ACCEPTED,
) -> BrokerOrderView:
    return BrokerOrderView(
        broker_order_id=f"b-{client_order_id}",
        client_order_id=client_order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        filled_quantity=filled_quantity,
        status=status,
    )


def _execution(
    exec_id: str,
    *,
    client_order_id: str = "ord-1",
    quantity: float = 1.0,
    price: float = 100.0,
    symbol: str | None = "BTC/USD",
    side: OrderSide | None = OrderSide.BUY,
    fee: float | None = None,
    executed_at: datetime | None = T0,
) -> BrokerExecutionView:
    return BrokerExecutionView(
        exec_id,
        client_order_id,
        quantity,
        price,
        symbol=symbol,
        side=side,
        fee=fee,
        executed_at=executed_at,
    )


def _kinds(engine: ReconciliationEngine, snapshot: BrokerSnapshot) -> set[AnomalyKind]:
    return {f.kind for f in engine.reconcile(snapshot).findings}


# --------------------------------------------------------------- matching


def test_known_execution_matches_cleanly(store: SqliteFinancialStore) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1")],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    assert result.ok is True
    assert result.findings == []
    assert result.matches.matched == ["exec-1"]
    assert result.run.matched_executions == 1
    assert result.run.broker_only_executions == 0
    assert result.run.internal_only_executions == 0


def test_broker_only_execution_is_reported(store: SqliteFinancialStore) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=2.0)],
            executions=[_execution("exec-1"), _execution("exec-2", quantity=1.0)],
            positions={"BTC/USD": 2.0},
            cash_minor=0,
        )
    )
    assert AnomalyKind.BROKER_ONLY_EXECUTION in {f.kind for f in result.findings}
    assert result.run.broker_only_executions == 1
    assert result.matches.broker_only == ["exec-2"]


def test_internal_only_execution_is_reported_in_a_full_snapshot(
    store: SqliteFinancialStore,
) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    store.apply_fill(_fill(order, 1.0, 101.0, fill_id="f2", exec_id="exec-2"))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1")],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    assert AnomalyKind.INTERNAL_ONLY_EXECUTION in {f.kind for f in result.findings}
    assert result.matches.internal_only == ["exec-2"]


def test_equal_counts_with_different_ids_are_not_a_match(store: SqliteFinancialStore) -> None:
    """Equal cardinality is not evidence of agreement: the ID sets differ."""
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-internal"))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-broker")],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    kinds = {f.kind for f in result.findings}
    assert AnomalyKind.BROKER_ONLY_EXECUTION in kinds
    assert AnomalyKind.INTERNAL_ONLY_EXECUTION in kinds
    assert result.matches.matched == []


def test_matched_execution_with_different_quantity_conflicts(store: SqliteFinancialStore) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1", quantity=2.0)],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    conflict = next(
        f for f in result.findings if f.kind is AnomalyKind.EXECUTION_CONFLICT
    )
    assert "quantity" in conflict.detail
    assert result.matches.matched == []
    assert result.run.matched_executions == 0


def test_matched_execution_with_different_price_conflicts(store: SqliteFinancialStore) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1", price=101.5)],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    conflict = next(f for f in result.findings if f.kind is AnomalyKind.EXECUTION_CONFLICT)
    assert "price" in conflict.detail


def test_matched_execution_with_wrong_owning_order_conflicts(
    store: SqliteFinancialStore,
) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[
                _broker_order(filled_quantity=1.0),
                _broker_order(
                    client_order_id="ord-other", filled_quantity=1.0, status=OrderStatus.FILLED
                ),
            ],
            executions=[_execution("exec-1", client_order_id="ord-other")],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    conflict = next(f for f in result.findings if f.kind is AnomalyKind.EXECUTION_CONFLICT)
    assert "owner order" in conflict.detail


def test_unknown_fee_is_not_a_conflict(store: SqliteFinancialStore) -> None:
    """An unreported fee is unknown, not zero — it must not manufacture a finding."""
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1", fee=0.5))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1", fee=None)],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    assert result.findings == []


def test_duplicate_execution_within_broker_response(store: SqliteFinancialStore) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1"), _execution("exec-1")],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    duplicates = [f for f in result.findings if f.kind is AnomalyKind.DUPLICATE_EXECUTION]
    assert len(duplicates) == 1
    assert "broker" in duplicates[0].detail


def test_replayed_broker_callback_does_not_double_apply_and_still_matches(
    store: SqliteFinancialStore,
) -> None:
    """At-least-once delivery: the same execution delivered twice is applied once."""
    order = _order(store)
    fill = _fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1")
    assert store.apply_fill(fill) is True
    assert store.apply_fill(fill) is False  # replay: no second economic effect
    assert len(store.fills()) == 1

    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1")],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    assert result.findings == []
    assert result.matches.matched == ["exec-1"]


def test_multiple_partial_fills_on_one_order(store: SqliteFinancialStore) -> None:
    order = _order(store, quantity=10.0)
    for index, (qty, price) in enumerate([(4.0, 100.0), (3.0, 101.0), (3.0, 102.0)], start=1):
        store.apply_fill(
            _fill(
                order,
                qty,
                price,
                fill_id=f"f{index}",
                exec_id=f"exec-{index}",
                executed_at=T0 + timedelta(minutes=index),
            )
        )
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=10.0, status=OrderStatus.FILLED)],
            executions=[
                _execution("exec-1", quantity=4.0, price=100.0),
                _execution("exec-2", quantity=3.0, price=101.0),
                _execution("exec-3", quantity=3.0, price=102.0),
            ],
            positions={"BTC/USD": 10.0},
            cash_minor=0,
        )
    )
    assert result.findings == []
    assert result.matches.matched_count == 3


def test_out_of_order_execution_delivery_is_consistent(store: SqliteFinancialStore) -> None:
    """Fills arriving out of chronological order must still reconcile to one set."""
    order = _order(store, quantity=10.0)
    store.apply_fill(
        _fill(order, 3.0, 102.0, fill_id="f3", exec_id="exec-3", executed_at=T0 + timedelta(minutes=3))
    )
    store.apply_fill(
        _fill(order, 4.0, 100.0, fill_id="f1", exec_id="exec-1", executed_at=T0 + timedelta(minutes=1))
    )
    store.apply_fill(
        _fill(order, 3.0, 101.0, fill_id="f2", exec_id="exec-2", executed_at=T0 + timedelta(minutes=2))
    )
    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=10.0, status=OrderStatus.FILLED)],
            executions=[
                _execution("exec-1", quantity=4.0, price=100.0),
                _execution("exec-3", quantity=3.0, price=102.0),
                _execution("exec-2", quantity=3.0, price=101.0),
            ],
            positions={"BTC/USD": 10.0},
            cash_minor=0,
        )
    )
    assert result.findings == []
    assert sorted(result.matches.matched) == ["exec-1", "exec-2", "exec-3"]


def test_reconciliation_after_restart_sees_the_same_identities(tmp_path: Path) -> None:
    """A restart must not turn durable fills into 'missing' executions."""
    db = tmp_path / "financial.db"
    store = SqliteFinancialStore(db)
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    store.close()

    reopened = SqliteFinancialStore(db)
    try:
        engine = ReconciliationEngine(reopened)
        result = engine.reconcile(
            BrokerSnapshot(
                orders=[_broker_order(filled_quantity=1.0)],
                executions=[_execution("exec-1")],
                positions={"BTC/USD": 1.0},
                cash_minor=0,
            )
        )
        assert result.findings == []
        assert result.matches.matched == ["exec-1"]
    finally:
        reopened.close()


# ------------------------------------------------------------ window contract


def test_bounded_window_ignores_internal_fills_outside_the_interval(
    store: SqliteFinancialStore,
) -> None:
    order = _order(store, quantity=10.0)
    inside = _fill(
        order, 1.0, 100.0, fill_id="f-in", exec_id="exec-in", executed_at=T0
    )
    outside = _fill(
        order, 1.0, 101.0, fill_id="f-out", exec_id="exec-out", executed_at=T0 - timedelta(days=5)
    )
    store.apply_fill(inside)
    store.apply_fill(outside)

    engine = ReconciliationEngine(store)
    window = ReconciliationWindow(
        ReconciliationMode.BOUNDED_WINDOW,
        window_start=T0 - timedelta(hours=1),
        window_end=T0 + timedelta(hours=1),
    )
    result = engine.reconcile(
        BrokerSnapshot(
            window,
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-in")],
            positions={"BTC/USD": 2.0},
            cash_minor=0,
        )
    )
    kinds = {f.kind for f in result.findings}
    assert AnomalyKind.INTERNAL_ONLY_EXECUTION not in kinds
    assert AnomalyKind.POSITION_MISMATCH not in kinds  # windowed: broker-only symbols
    assert result.run.mode is ReconciliationMode.BOUNDED_WINDOW
    assert result.run.window_start == window.window_start


def test_cursor_window_never_asserts_internal_only(store: SqliteFinancialStore) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    engine = ReconciliationEngine(store)
    window = ReconciliationWindow(
        ReconciliationMode.CURSOR, cursor_token="cursor-42", broker="alpaca"
    )
    result = engine.reconcile(
        BrokerSnapshot(
            window,
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-2", quantity=1.0)],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    kinds = {f.kind for f in result.findings}
    assert AnomalyKind.INTERNAL_ONLY_EXECUTION not in kinds
    assert AnomalyKind.BROKER_ONLY_EXECUTION in kinds
    assert result.run.cursor_token == "cursor-42"
    assert result.run.broker == "alpaca"


def test_bounded_window_requires_bounds() -> None:
    with pytest.raises(ValueError):
        ReconciliationWindow(ReconciliationMode.BOUNDED_WINDOW)
    with pytest.raises(ValueError):
        ReconciliationWindow(
            ReconciliationMode.BOUNDED_WINDOW,
            window_start=T0,
            window_end=T0 - timedelta(days=1),
        )


# ------------------------------------------------------------- safety lockout


def test_critical_finding_engages_lockout_through_the_safety_plane(
    store: SqliteFinancialStore,
) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    safety = SafetyPlane(store)
    engine = ReconciliationEngine(store, safety=safety)

    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1")],
            positions={"BTC/USD": 5.0},
            cash_minor=0,
        )
    )
    assert result.requires_lockout is True
    assert result.lockout_scope is LockoutScope.ACCOUNT
    assert result.engaged_lockouts, "a CRITICAL finding must restrict the account"

    decision = safety.is_blocked(account_id="default")
    assert decision.blocked is True
    assert "POSITION_MISMATCH" in decision.reasons[0]
    assert safety.is_blocked(account_id="other-account").blocked is False


def test_clean_reconciliation_engages_nothing(store: SqliteFinancialStore) -> None:
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    safety = SafetyPlane(store)
    engine = ReconciliationEngine(store, safety=safety)
    engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1")],
            positions={"BTC/USD": 1.0},
            cash_minor=0,
        )
    )
    assert safety.is_blocked().blocked is False
    assert safety.state()["active_count"] == 0


def test_lockout_release_requires_a_risk_admin_role(store: SqliteFinancialStore) -> None:
    safety = SafetyPlane(store)
    lockout = safety.engage(
        scope=LockoutScope.ACCOUNT,
        subject="default",
        reason="test restriction",
    )
    with pytest.raises(SafetyAuthorizationError):
        safety.release(lockout.lockout_id, operator_id="", role="ADMIN", note="")
    with pytest.raises(SafetyAuthorizationError):
        safety.release(lockout.lockout_id, operator_id="alice", role="VIEWER", note="")
    with pytest.raises(SafetyAuthorizationError):
        safety.release(lockout.lockout_id, operator_id="alice", role="OPERATOR", note="")
    with pytest.raises(SafetyAuthorizationError):
        safety.release(lockout.lockout_id, operator_id="alice", role="NOT_A_ROLE", note="")

    assert safety.is_blocked(account_id="default").blocked is True
    released = safety.release(
        lockout.lockout_id, operator_id="alice", role="RISK_ADMIN", note="venue export was stale"
    )
    assert released.active is False
    assert released.released_by == "alice"
    assert safety.is_blocked(account_id="default").blocked is False


def test_repeated_engagement_of_the_same_scope_is_idempotent(
    store: SqliteFinancialStore,
) -> None:
    safety = SafetyPlane(store)
    first = safety.engage(scope=LockoutScope.ACCOUNT, subject="default", reason="first")
    second = safety.engage(scope=LockoutScope.ACCOUNT, subject="default", reason="second")
    assert first.lockout_id == second.lockout_id
    assert second.reason == "first"
    assert len(store.active_lockouts()) == 1


def test_lockout_scope_broadens_when_the_subject_is_unknown(
    store: SqliteFinancialStore,
) -> None:
    """An unresolvable restriction must broaden, never silently restrict nothing."""
    safety = SafetyPlane(store, account_id="")
    lockout = safety.engage_for_scope(
        LockoutScope.ACCOUNT, account_id=None, reason="unresolvable subject"
    )
    assert lockout.scope is LockoutScope.GLOBAL
    assert safety.is_blocked(account_id="anything").blocked is True


def test_lockout_survives_restart(tmp_path: Path) -> None:
    db = tmp_path / "financial.db"
    store = SqliteFinancialStore(db)
    SafetyPlane(store).engage(
        scope=LockoutScope.ACCOUNT, subject="default", reason="persisted restriction"
    )
    store.close()

    reopened = SqliteFinancialStore(db)
    try:
        assert SafetyPlane(reopened).is_blocked(account_id="default").blocked is True
    finally:
        reopened.close()


def test_finding_resolution_role_gate(store: SqliteFinancialStore) -> None:
    engine = ReconciliationEngine(store)
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    result = engine.reconcile(
        BrokerSnapshot(
            orders=[_broker_order(filled_quantity=1.0)],
            executions=[_execution("exec-1")],
            positions={"BTC/USD": 9.0},
            cash_minor=0,
        )
    )
    finding = result.findings[0]
    assert finding.severity is ReconciliationSeverity.CRITICAL
    with pytest.raises(PermissionError):
        engine.resolve(finding.finding_id, "alice", "OPERATOR", "looks fine")
    resolved = engine.resolve(finding.finding_id, "alice", "RISK_ADMIN", "verified against export")
    assert resolved.resolved_by == "alice"
    assert store.verify_invariants().ok is True


# ------------------------------------------------- the facet/coverage contract


def test_partial_coverage_never_invents_absence_findings(
    store: SqliteFinancialStore,
) -> None:
    """A venue that reports only positions must not be judged on the rest.

    This is the difference between a reconciliation engine and an incident
    generator. If the venue was never asked about orders or executions, its
    silence is not evidence that our orders and fills do not exist, and
    manufacturing CRITICAL findings from that silence would engage a real
    account lockout for no reason.
    """
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))

    window = ReconciliationWindow(
        mode=ReconciliationMode.FULL_SNAPSHOT,
        broker="paper",
        adapter_version="paper-positions-only-1.0",
        covers_orders=False,
        covers_executions=False,
        covers_positions=True,
    )
    assert window.facets == ("positions",)
    assert window.may_assert_internal_only is False

    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(window, positions={"BTC/USD": 1.0}, cash_minor=None)
    )

    assert result.findings == []
    assert result.ok is True
    # The order really is still live and the fill really is in the ledger — so
    # the absence of a MISSING_ORDER / INTERNAL_ONLY_EXECUTION finding is the
    # coverage declaration doing its job, not an empty book.
    assert [o.client_order_id for o in store.open_orders()] == ["ord-1"]
    assert len(store.fills()) == 1
    assert result.matches.matched == []


def test_partial_coverage_still_reports_what_it_did_cover(
    store: SqliteFinancialStore,
) -> None:
    """Declaring partial coverage must not make the engine blind to real gaps."""
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))

    engine = ReconciliationEngine(store)
    # Positions-only coverage, but the one position it does report disagrees.
    mismatched = engine.reconcile(
        BrokerSnapshot(
            ReconciliationWindow(
                covers_orders=False, covers_executions=False, covers_positions=True
            ),
            positions={"BTC/USD": 99.0},
        )
    )
    assert _ANOMALIES(mismatched) == {AnomalyKind.POSITION_MISMATCH}


def test_positions_less_snapshot_only_judges_symbols_it_mentioned(
    store: SqliteFinancialStore,
) -> None:
    """Without position coverage, an unmentioned symbol is not a divergence."""
    order = _order(store)
    store.apply_fill(_fill(order, 2.0, 100.0, fill_id="f1", exec_id="exec-1"))

    engine = ReconciliationEngine(store)
    result = engine.reconcile(
        BrokerSnapshot(
            ReconciliationWindow(
                mode=ReconciliationMode.FULL_SNAPSHOT,
                covers_orders=False,
                covers_executions=False,
                covers_positions=False,
            ),
            positions={"ETH/USD": 0.0},
        )
    )
    assert result.findings == []


def test_full_coverage_still_asserts_absence(store: SqliteFinancialStore) -> None:
    """The default must remain the strict, fully-covering contract."""
    order = _order(store)
    store.apply_fill(_fill(order, 1.0, 100.0, fill_id="f1", exec_id="exec-1"))
    engine = ReconciliationEngine(store)

    result = engine.reconcile(
        BrokerSnapshot(ReconciliationWindow(), orders=[], executions=[], positions={})
    )
    kinds = _ANOMALIES(result)
    # Default coverage: our order is missing at the venue, our fill is missing
    # at the venue, and our position is missing at the venue.
    assert AnomalyKind.MISSING_ORDER in kinds
    assert AnomalyKind.INTERNAL_ONLY_EXECUTION in kinds
    assert AnomalyKind.POSITION_MISMATCH in kinds


def test_window_describe_reports_partial_coverage() -> None:
    full = ReconciliationWindow()
    assert full.describe() == str(ReconciliationMode.FULL_SNAPSHOT)
    assert full.facets == ("orders", "executions", "positions")

    partial = ReconciliationWindow(covers_executions=False, covers_positions=False)
    assert "orders" in partial.describe()
    assert "executions" not in partial.describe().replace("orders", "")
    assert partial.facets == ("orders",)


def _ANOMALIES(result: object) -> set[AnomalyKind]:
    return {f.kind for f in result.findings}  # type: ignore[attr-defined]
