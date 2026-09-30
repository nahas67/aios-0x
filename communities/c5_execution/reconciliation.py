"""Community 5: reconciliation — broker truth vs internal financial truth (§26).

The broker is externally authoritative for what it executed; AIOS is
authoritative for intended business logic. This engine compares the two and
classifies every divergence into the §26 taxonomy.

**Identity, not counting.** A ``broker_execution_id`` that exists at the venue and
internally *with matching economics* is a **match**. V1-A.1 classified that as
``DUPLICATE_FILL``, which made every correct authoritative broker snapshot look
like an incident. The comparison is now pure set algebra over execution
identities:

    broker_ids ∩ internal_ids   -> matched (a match with conflicting economics
                                   becomes EXECUTION_CONFLICT instead)
    broker_ids - internal_ids   -> BROKER_ONLY_EXECUTION   (missing internally)
    internal_ids - broker_ids   -> INTERNAL_ONLY_EXECUTION (missing at the venue,
                                   within the window that should have covered it)

Counts are never used as a proxy for presence: ``len(broker) > len(internal)``
tells you nothing when the two sets hold completely different identities.

**The window contract.** A comparison is only meaningful relative to what was
requested (see :class:`ReconciliationWindow`): a full snapshot supports both
set-differences, a bounded time window scopes internal-only to the interval, and
a cursor-based delta supports neither claim about absence. Adapters must state
which one they performed, and the contract is persisted with the run.

**Duplicates** mean one of three things, never "a match": the same execution
identity appearing more than once within one source, one identity mapped to
conflicting economic data, or an impossible repeated economic application.

Findings are typed, never free text: each names its kind, severity, scope,
subject, and both sides of the mismatch, so the safety plane can act
mechanically. Resolution is human-only, role-gated by the RBAC matrix, and
always attributed.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from core.control_plane import ROLE_MATRIX, ControlAction, OperatorRole
from core.financial_kernel import (
    LOCKOUT_SCOPE_BY_KIND,
    AnomalyKind,
    BaseFinancialStore,
    DurableOrder,
    Fill,
    FindingStatus,
    LockoutScope,
    ReconciliationFinding,
    ReconciliationMode,
    ReconciliationRun,
    ReconciliationSeverity,
)
from core.platform_events import (
    PlatformEvent,
    reconciliation_completed,
    reconciliation_finding_opened,
)
from schemas.contracts import OrderSide, OrderStatus

logger = logging.getLogger(__name__)

PRODUCER = "c5-execution"

#: Comparison tolerances. Execution economics must agree to better than these;
#: they exist to absorb binary-float representation, not sloppy bookkeeping.
QUANTITY_TOL = 1e-8
PRICE_TOL = 1e-6
FEE_TOL = 1e-6
CASH_TOL_MINOR = 0

#: Severity per anomaly kind. The scale is preserved for adapters that later add
#: informational drift; every kind today is capital-relevant and restricts.
SEVERITY_BY_KIND: dict[AnomalyKind, ReconciliationSeverity] = {
    AnomalyKind.MISSING_ORDER: ReconciliationSeverity.CRITICAL,
    AnomalyKind.UNKNOWN_BROKER_ORDER: ReconciliationSeverity.CRITICAL,
    AnomalyKind.ORDER_CONFLICT: ReconciliationSeverity.CRITICAL,
    AnomalyKind.BROKER_ONLY_EXECUTION: ReconciliationSeverity.CRITICAL,
    AnomalyKind.INTERNAL_ONLY_EXECUTION: ReconciliationSeverity.CRITICAL,
    AnomalyKind.EXECUTION_CONFLICT: ReconciliationSeverity.CRITICAL,
    AnomalyKind.DUPLICATE_EXECUTION: ReconciliationSeverity.CRITICAL,
    AnomalyKind.QUANTITY_MISMATCH: ReconciliationSeverity.CRITICAL,
    AnomalyKind.CASH_MISMATCH: ReconciliationSeverity.CRITICAL,
    AnomalyKind.POSITION_MISMATCH: ReconciliationSeverity.CRITICAL,
    AnomalyKind.STALE_STATUS: ReconciliationSeverity.CRITICAL,
}

#: Which side a duplicate was observed on (recorded in the finding detail).
BROKER_SOURCE = "broker"
INTERNAL_SOURCE = "internal"


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= max(tol, tol * max(abs(a), abs(b)))


class ReconciliationWindow:
    """What the adapter asked the venue for, and how the venue answered.

    The §26 window contract has two independent dimensions, and conflating them
    is how a reconciliation engine invents incidents:

    *How far* the answer reaches — the ``mode``: a full snapshot, a bounded time
    window, or an incremental delta. This scopes the *set-difference* claims.

    *Which facets* the answer actually contains — ``covers_orders``,
    ``covers_executions``, ``covers_positions``. Plenty of real venues answer
    positions and not executions; a paper/self-venue may answer only positions.
    If the venue never reported executions, its silence is not evidence of a
    missing execution, and the engine must not manufacture a CRITICAL finding
    (and therefore an account lockout) out of a question nobody asked.

    Both dimensions are declared by the adapter and persisted with the run, so a
    finding can always be explained by what the venue was actually asked.
    """

    def __init__(
        self,
        mode: ReconciliationMode = ReconciliationMode.FULL_SNAPSHOT,
        *,
        account_id: str = "default",
        broker: str | None = None,
        adapter_version: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        cursor_token: str | None = None,
        queried_at: datetime | None = None,
        covers_orders: bool = True,
        covers_executions: bool = True,
        covers_positions: bool = True,
    ) -> None:
        self.mode = mode
        self.account_id = account_id
        self.broker = broker
        self.adapter_version = adapter_version
        self.window_start = window_start
        self.window_end = window_end
        self.cursor_token = cursor_token
        self.queried_at = queried_at
        self.covers_orders = bool(covers_orders)
        self.covers_executions = bool(covers_executions)
        self.covers_positions = bool(covers_positions)
        if mode is ReconciliationMode.BOUNDED_WINDOW:
            if window_start is None or window_end is None:
                raise ValueError("BOUNDED_WINDOW requires window_start and window_end")
            if window_end < window_start:
                raise ValueError("window_end must not precede window_start")

    @property
    def may_assert_broker_only(self) -> bool:
        """Whether an execution absent internally is provably missing.

        True whenever the venue reported executions at all: the venue executed
        something it has no internal counterpart for, and that is a real gap in
        our book regardless of the window's other dimensions.
        """
        return self.covers_executions

    @property
    def may_assert_internal_only(self) -> bool:
        """Whether an execution absent at the venue is provably missing.

        False for ``CURSOR`` (a delta proves nothing about what it did not
        mention) and false when the venue did not report executions at all.
        """
        return self.covers_executions and self.mode in (
            ReconciliationMode.FULL_SNAPSHOT,
            ReconciliationMode.BOUNDED_WINDOW,
        )

    def covers(self, executed_at: datetime) -> bool:
        """Whether this window claims to include an event at ``executed_at``."""
        if self.mode is ReconciliationMode.FULL_SNAPSHOT:
            return True
        if self.mode is ReconciliationMode.BOUNDED_WINDOW:
            assert self.window_start is not None and self.window_end is not None
            return self.window_start <= executed_at <= self.window_end
        return False

    @property
    def facets(self) -> tuple[str, ...]:
        """The facets this response actually contains (for provenance/UI)."""
        return tuple(
            name
            for name, flag in (
                ("orders", self.covers_orders),
                ("executions", self.covers_executions),
                ("positions", self.covers_positions),
            )
            if flag
        )

    def describe(self) -> str:
        base: str
        if self.mode is ReconciliationMode.BOUNDED_WINDOW:
            base = (
                f"{self.mode} [{self.window_start.isoformat()} .. "
                f"{self.window_end.isoformat()}]"
                if self.window_start and self.window_end
                else str(self.mode)
            )
        elif self.mode is ReconciliationMode.CURSOR:
            base = f"{self.mode} cursor={self.cursor_token or 'unknown'}"
        else:
            base = str(self.mode)
        if len(self.facets) == 3:
            return base
        return f"{base} facets={','.join(self.facets) or 'none'}"


class BrokerOrderView:
    """What the venue believes about one order (typed, not a dict).

    ``raw`` preserves broker-specific fields the common model has no slot for;
    useful broker state is never discarded just to fit a simplified shape.
    """

    def __init__(
        self,
        broker_order_id: str,
        client_order_id: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        filled_quantity: float,
        status: OrderStatus,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.broker_order_id = broker_order_id
        self.client_order_id = client_order_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.filled_quantity = filled_quantity
        self.status = status
        self.raw = dict(raw or {})


class BrokerExecutionView:
    """One execution as reported by the venue.

    ``fee`` is ``None`` when the venue does not report it for this execution —
    an unknown fee is not a fee of zero, and must not create a conflict.
    """

    def __init__(
        self,
        broker_execution_id: str,
        client_order_id: str,
        quantity: float,
        price: float,
        *,
        symbol: str | None = None,
        side: OrderSide | None = None,
        executed_at: datetime | None = None,
        fee: float | None = None,
        currency: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.broker_execution_id = broker_execution_id
        self.client_order_id = client_order_id
        self.quantity = quantity
        self.price = price
        self.symbol = symbol
        self.side = side
        self.executed_at = executed_at
        self.fee = fee
        self.currency = currency
        self.raw = dict(raw or {})


class BrokerSnapshot:
    """The venue's view of an account, plus the contract under which it was read.

    Orders, positions and cash are snapshot-shaped at every real broker; the
    window scopes *executions*. That asymmetry is stated here rather than hidden.
    """

    def __init__(
        self,
        window: ReconciliationWindow | None = None,
        orders: Sequence[BrokerOrderView] = (),
        executions: Sequence[BrokerExecutionView] = (),
        positions: dict[str, float] | None = None,
        cash_minor: int | None = None,
        account_id: str = "default",
    ) -> None:
        self.window = window or ReconciliationWindow(account_id=account_id)
        if window is None:
            self.window.account_id = account_id
        self.orders = list(orders)
        self.executions = list(executions)
        self.positions = dict(positions or {})
        self.cash_minor = cash_minor

    @property
    def account_id(self) -> str:
        return self.window.account_id


class ExecutionMatch:
    """Outcome of matching one execution identity across both sources."""

    def __init__(
        self,
        matched: list[str],
        broker_only: list[str],
        internal_only: list[str],
    ) -> None:
        self.matched = matched
        self.broker_only = broker_only
        self.internal_only = internal_only

    @property
    def matched_count(self) -> int:
        return len(self.matched)


class ReconciliationResult:
    """Outcome of one pass; drives the safety plane via ``lockout_scope``."""

    def __init__(
        self,
        run: ReconciliationRun,
        findings: list[ReconciliationFinding],
        events: list[PlatformEvent],
        matches: ExecutionMatch,
        engaged_lockouts: list[Any] | None = None,
    ) -> None:
        self.run = run
        self.findings = findings
        self.events = events
        self.matches = matches
        self.engaged_lockouts = list(engaged_lockouts or [])

    @property
    def ok(self) -> bool:
        return self.run.ok

    @property
    def requires_lockout(self) -> bool:
        return self.run.lockout_scope is not LockoutScope.NONE

    @property
    def lockout_scope(self) -> LockoutScope:
        return self.run.lockout_scope

    def critical(self) -> list[ReconciliationFinding]:
        return [f for f in self.findings if f.severity is ReconciliationSeverity.CRITICAL]


class ReconciliationEngine:
    """Compares broker state against internal durable financial state.

    ``safety`` is optional so the engine can be used in read-only analysis, but
    when it is wired a CRITICAL finding engages the matching restriction before
    this method returns — reconciliation that does not restrict is theatre.
    """

    def __init__(
        self,
        store: BaseFinancialStore,
        account_id: str = "default",
        safety: Any = None,
    ) -> None:
        self.store = store
        self.account_id = account_id
        self.safety = safety

    # ------------------------------------------------------------------ pass

    def reconcile(self, snapshot: BrokerSnapshot) -> ReconciliationResult:
        window = snapshot.window
        run = ReconciliationRun(
            account_id=window.account_id,
            mode=window.mode,
            broker=window.broker,
            adapter_version=window.adapter_version,
            window_start=window.window_start,
            window_end=window.window_end,
            cursor_token=window.cursor_token,
            queried_at=window.queried_at,
        )
        findings: list[ReconciliationFinding] = []
        internal_orders = {o.client_order_id: o for o in self._internal_orders()}
        internal_fills = [f for f in self.store.fills() if f.account_id == window.account_id]
        order_by_id = {o.internal_order_id: o for o in self.store.orders(window.account_id)}

        self._reconcile_orders(run, window, snapshot, internal_orders, findings)
        matches = self._reconcile_executions(
            run, window, snapshot, internal_fills, order_by_id, findings
        )
        self._reconcile_positions(run, window, snapshot, findings)
        self._reconcile_cash(run, window, snapshot, findings)

        run = run.model_copy(
            update={
                "checked_orders": len(snapshot.orders),
                "checked_fills": len(snapshot.executions),
                "checked_positions": len(snapshot.positions),
                "matched_executions": matches.matched_count,
                "broker_only_executions": len(matches.broker_only),
                "internal_only_executions": len(matches.internal_only),
            }
        )
        stored = self.store.record_reconciliation(run, findings)
        events = [
            reconciliation_completed(
                stored.run_id, stored.account_id, len(findings), stored.ok
            )
        ]
        events.extend(
            reconciliation_finding_opened(f.finding_id, str(f.kind), str(f.severity), f.subject)
            for f in findings
        )

        engaged = self._engage_lockouts(stored, findings)
        logger.info(
            "reconciliation run %s (%s): matched=%d broker_only=%d internal_only=%d "
            "findings=%d lockout_scope=%s",
            stored.run_id,
            window.describe(),
            matches.matched_count,
            len(matches.broker_only),
            len(matches.internal_only),
            len(findings),
            stored.lockout_scope,
        )
        return ReconciliationResult(stored, findings, events, matches, engaged)

    # -------------------------------------------------------------- matching

    def _reconcile_executions(
        self,
        run: ReconciliationRun,
        window: ReconciliationWindow,
        snapshot: BrokerSnapshot,
        internal_fills: list[Fill],
        order_by_id: dict[str, DurableOrder],
        findings: list[ReconciliationFinding],
    ) -> ExecutionMatch:
        internal_by_exec: dict[str, list[Fill]] = {}
        for fill in internal_fills:
            if fill.broker_execution_id:
                internal_by_exec.setdefault(fill.broker_execution_id, []).append(fill)

        # A duplicate is the SAME identity twice within ONE source. On the
        # internal side the unique index should make this impossible; if it ever
        # happens it is a genuine integrity incident (impossible repeated
        # economic application), so it is reported rather than assumed away.
        for exec_id, fills in internal_by_exec.items():
            if len(fills) > 1:
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.DUPLICATE_EXECUTION,
                        f"execution {exec_id} applied economically {len(fills)} times internally",
                        subject=exec_id,
                        internal_value=str(len(fills)),
                        broker_value=None,
                        window=window,
                        execution_id=exec_id,
                        strategy_id=fills[0].strategy_id,
                    )
                )

        broker_counts = Counter(e.broker_execution_id for e in snapshot.executions)
        for exec_id, count in broker_counts.items():
            if count > 1:
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.DUPLICATE_EXECUTION,
                        f"venue returned execution {exec_id} {count} times in one response"
                        f" (source={BROKER_SOURCE})",
                        subject=exec_id,
                        internal_value=None,
                        broker_value=str(count),
                        window=window,
                        execution_id=exec_id,
                    )
                )

        broker_ids = set(broker_counts)
        internal_ids = set(internal_by_exec)
        matched: list[str] = []
        broker_only: list[str] = []
        internal_only: list[str] = []

        for exec_id in sorted(broker_ids):
            internal = internal_by_exec.get(exec_id)
            if internal is None:
                broker_only.append(exec_id)
                continue
            conflicts = self._execution_conflicts(
                snapshot.executions, exec_id, internal[0], order_by_id
            )
            if conflicts:
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.EXECUTION_CONFLICT,
                        f"execution {exec_id} has conflicting economics: "
                        + "; ".join(conflicts),
                        subject=exec_id,
                        internal_value=self._describe_fill(internal[0]),
                        broker_value=self._describe_broker_execution(
                            snapshot.executions, exec_id
                        ),
                        window=window,
                        execution_id=exec_id,
                        strategy_id=internal[0].strategy_id,
                    )
                )
            else:
                matched.append(exec_id)

        if broker_only:
            for exec_id in broker_only:
                view = next(
                    e for e in snapshot.executions if e.broker_execution_id == exec_id
                )
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.BROKER_ONLY_EXECUTION,
                        "venue execution is missing from the internal blotter",
                        subject=exec_id,
                        internal_value=None,
                        broker_value=f"{view.quantity:g}@{view.price:g} "
                        f"client_order_id={view.client_order_id}",
                        window=window,
                        execution_id=exec_id,
                    )
                )

        if window.may_assert_internal_only:
            for exec_id in sorted(internal_ids - broker_ids):
                fill = internal_by_exec[exec_id][0]
                if not window.covers(fill.executed_at):
                    # Outside the requested interval: the venue was never asked
                    # about it, so its absence proves nothing.
                    continue
                internal_only.append(exec_id)
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.INTERNAL_ONLY_EXECUTION,
                        "internal fill is absent from the venue's report for the"
                        f" requested window ({window.describe()})",
                        subject=exec_id,
                        internal_value=self._describe_fill(fill),
                        broker_value=None,
                        window=window,
                        execution_id=exec_id,
                        account_id=fill.account_id,
                        strategy_id=fill.strategy_id,
                    )
                )
        else:
            logger.debug(
                "window %s cannot support internal-only claims; skipping %d candidate(s)",
                window.describe(),
                len(internal_ids - broker_ids),
            )

        return ExecutionMatch(matched, broker_only, internal_only)

    def _reconcile_orders(
        self,
        run: ReconciliationRun,
        window: ReconciliationWindow,
        snapshot: BrokerSnapshot,
        internal_orders: dict[str, DurableOrder],
        findings: list[ReconciliationFinding],
    ) -> None:
        broker_client_ids = {o.client_order_id for o in snapshot.orders}
        broker_counts = Counter(o.client_order_id for o in snapshot.orders)
        for client_id, count in broker_counts.items():
            if count > 1:
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.DUPLICATE_EXECUTION,
                        f"venue returned order {client_id} {count} times in one response"
                        f" (source={BROKER_SOURCE})",
                        subject=client_id,
                        internal_value=None,
                        broker_value=str(count),
                        window=window,
                    )
                )

        for view in snapshot.orders:
            internal = internal_orders.get(view.client_order_id)
            if internal is None:
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.UNKNOWN_BROKER_ORDER,
                        "venue holds an order AIOS never recorded",
                        subject=view.client_order_id,
                        internal_value=None,
                        broker_value=view.broker_order_id,
                        window=window,
                    )
                )
                continue

            conflicts: list[str] = []
            if internal.symbol != view.symbol:
                conflicts.append(f"symbol {internal.symbol} != {view.symbol}")
            if internal.side is not view.side:
                conflicts.append(f"side {internal.side} != {view.side}")
            if not _close(internal.quantity, view.quantity, QUANTITY_TOL):
                conflicts.append(f"quantity {internal.quantity:g} != {view.quantity:g}")
            if conflicts:
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.ORDER_CONFLICT,
                        f"order {view.client_order_id} terms disagree: " + "; ".join(conflicts),
                        subject=view.client_order_id,
                        internal_value=(
                            f"{internal.symbol}/{internal.side}/{internal.quantity:g}"
                        ),
                        broker_value=f"{view.symbol}/{view.side}/{view.quantity:g}",
                        window=window,
                        strategy_id=internal.strategy_id,
                    )
                )

            if not _close(internal.filled_quantity, view.filled_quantity, QUANTITY_TOL):
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.QUANTITY_MISMATCH,
                        "filled quantity differs between venue and internal state",
                        subject=internal.client_order_id,
                        internal_value=f"{internal.filled_quantity}",
                        broker_value=f"{view.filled_quantity}",
                        window=window,
                        strategy_id=internal.strategy_id,
                    )
                )
            elif internal.status is not view.status and view.status is OrderStatus.FILLED:
                findings.append(
                    self._finding(
                        run,
                        AnomalyKind.STALE_STATUS,
                        "venue reports FILLED while internal state is not terminal",
                        subject=internal.client_order_id,
                        internal_value=str(internal.status),
                        broker_value=str(view.status),
                        window=window,
                        strategy_id=internal.strategy_id,
                    )
                )

        if not window.covers_orders:
            # The venue was not asked about orders, so our open orders being
            # absent from its answer is not a discrepancy.
            logger.debug(
                "window %s does not cover orders; skipping MISSING_ORDER claims",
                window.describe(),
            )
            return

        open_client_ids = {o.client_order_id for o in self.store.open_orders(window.account_id)}
        for client_id in sorted(open_client_ids - broker_client_ids):
            internal = internal_orders.get(client_id)
            findings.append(
                self._finding(
                    run,
                    AnomalyKind.MISSING_ORDER,
                    "AIOS holds a live order the venue does not report",
                    subject=client_id,
                    internal_value=internal.internal_order_id if internal else None,
                    broker_value=None,
                    window=window,
                    strategy_id=internal.strategy_id if internal else None,
                )
            )

    def _reconcile_positions(
        self,
        run: ReconciliationRun,
        window: ReconciliationWindow,
        snapshot: BrokerSnapshot,
        findings: list[ReconciliationFinding],
    ) -> None:
        internal_positions = {
            p.symbol: p.quantity for p in self.store.positions(window.account_id)
        }
        # A full snapshot that actually covers positions is authoritative for the
        # whole book; a windowed, cursor or positions-less read only tells us
        # about the symbols it mentioned.
        symbols = set(snapshot.positions)
        if window.covers_positions and window.mode is ReconciliationMode.FULL_SNAPSHOT:
            symbols |= set(internal_positions)
        for symbol in sorted(symbols):
            broker_qty = snapshot.positions.get(symbol)
            internal_qty = internal_positions.get(symbol, 0.0)
            if broker_qty is None and _close(internal_qty, 0.0, QUANTITY_TOL):
                continue
            if broker_qty is not None and _close(internal_qty, broker_qty, QUANTITY_TOL):
                continue
            findings.append(
                self._finding(
                    run,
                    AnomalyKind.POSITION_MISMATCH,
                    "position quantity differs between venue and IBOR",
                    subject=symbol,
                    internal_value=f"{internal_qty}",
                    broker_value=None if broker_qty is None else f"{broker_qty}",
                    window=window,
                )
            )

    def _reconcile_cash(
        self,
        run: ReconciliationRun,
        window: ReconciliationWindow,
        snapshot: BrokerSnapshot,
        findings: list[ReconciliationFinding],
    ) -> None:
        if snapshot.cash_minor is None:
            return
        internal_cash = self.store.cash_balance_minor(window.account_id, "USD")
        if abs(internal_cash - snapshot.cash_minor) > CASH_TOL_MINOR:
            findings.append(
                self._finding(
                    run,
                    AnomalyKind.CASH_MISMATCH,
                    "cash balance differs between venue and internal ledger",
                    subject=window.account_id,
                    internal_value=str(internal_cash),
                    broker_value=str(snapshot.cash_minor),
                    window=window,
                )
            )

    # ------------------------------------------------------------- economics

    @staticmethod
    def _execution_conflicts(
        broker_executions: Sequence[BrokerExecutionView],
        exec_id: str,
        internal: Fill,
        order_by_id: dict[str, DurableOrder],
    ) -> list[str]:
        """Field-level disagreement for one matched execution identity."""
        broker_views = [e for e in broker_executions if e.broker_execution_id == exec_id]
        if not broker_views:
            return [f"execution {exec_id} present internally but absent from payload"]
        broker = broker_views[0]
        conflicts: list[str] = []

        internal_order = order_by_id.get(internal.order_id)
        internal_client_id = internal_order.client_order_id if internal_order else None
        if internal_client_id and broker.client_order_id != internal_client_id:
            conflicts.append(
                f"owner order {internal_client_id} != {broker.client_order_id}"
            )
        if not _close(internal.quantity, broker.quantity, QUANTITY_TOL):
            conflicts.append(f"quantity {internal.quantity:g} != {broker.quantity:g}")
        if not _close(internal.price, broker.price, PRICE_TOL):
            conflicts.append(f"price {internal.price:g} != {broker.price:g}")
        if broker.symbol is not None and broker.symbol != internal.symbol:
            conflicts.append(f"symbol {internal.symbol} != {broker.symbol}")
        if broker.side is not None and broker.side is not internal.side:
            conflicts.append(f"side {internal.side} != {broker.side}")
        if broker.fee is not None and not _close(internal.fee, broker.fee, FEE_TOL):
            conflicts.append(f"fee {internal.fee:g} != {broker.fee:g}")
        return conflicts

    @staticmethod
    def _describe_fill(fill: Fill) -> str:
        return (
            f"{fill.quantity:g}@{fill.price:g} fee={fill.fee:g} "
            f"order={fill.order_id} at={fill.executed_at.isoformat()}"
        )

    @staticmethod
    def _describe_broker_execution(
        broker_executions: Sequence[BrokerExecutionView], exec_id: str
    ) -> str:
        views = [e for e in broker_executions if e.broker_execution_id == exec_id]
        if not views:
            return ""
        v = views[0]
        return f"{v.quantity:g}@{v.price:g} client_order_id={v.client_order_id}"

    # ------------------------------------------------------------- safety

    def _engage_lockouts(
        self, run: ReconciliationRun, findings: Sequence[ReconciliationFinding]
    ) -> list[Any]:
        """Restrict the required scope for CRITICAL findings (§33).

        Findings are grouped by (scope, subject) so one incident produces one
        restriction — the partial unique index makes duplicates a no-op anyway.
        """
        if self.safety is None or run.lockout_scope is LockoutScope.NONE:
            return []
        engaged: list[Any] = []
        seen: set[tuple[LockoutScope, str]] = set()
        for finding in findings:
            if finding.severity is not ReconciliationSeverity.CRITICAL:
                continue
            scope = finding.scope
            if scope is LockoutScope.NONE:
                continue
            subject = self._subject_for(scope, finding, run)
            key = (scope, subject)
            if key in seen:
                continue
            seen.add(key)
            engaged.append(
                self.safety.engage_for_scope(
                    scope,
                    account_id=finding.account_id or run.account_id,
                    broker=run.broker,
                    strategy_id=finding.strategy_id,
                    reason=(
                        f"{finding.kind} on {finding.subject}: {finding.detail}"
                    )[:500],
                    finding_id=finding.finding_id,
                    run_id=run.run_id,
                )
            )
        return engaged

    @staticmethod
    def _subject_for(
        scope: LockoutScope,
        finding: ReconciliationFinding,
        run: ReconciliationRun,
    ) -> str:
        if scope is LockoutScope.ACCOUNT:
            return finding.account_id or run.account_id or "*"
        if scope is LockoutScope.STRATEGY:
            return finding.strategy_id or "*"
        if scope is LockoutScope.BROKER:
            return run.broker or "*"
        return "*"

    # ------------------------------------------------------------------ reads

    def open_findings(self) -> list[ReconciliationFinding]:
        return self.store.findings(FindingStatus.OPEN)

    def resolve(
        self,
        finding_id: str,
        operator_id: str,
        role: str,
        note: str,
    ) -> ReconciliationFinding:
        """Resolve a finding under server-resolved human authority.

        CRITICAL findings need the ``RESET_LOCKOUT`` capability (RISK_ADMIN, ADMIN)
        because clearing a capital-relevant discrepancy is a risk decision; other
        findings need ``RESOLVE_RECONCILIATION_FINDING`` (OPERATOR and above).
        """
        if not operator_id.strip():
            raise PermissionError("authenticated operator identity required")
        try:
            parsed = OperatorRole(str(role).strip().upper())
        except ValueError as exc:
            raise PermissionError(f"unknown role {role!r}") from exc
        finding = self.store.findings_by_id(finding_id)
        required = (
            ControlAction.RESET_LOCKOUT
            if finding.severity is ReconciliationSeverity.CRITICAL
            else ControlAction.RESOLVE_RECONCILIATION_FINDING
        )
        if required not in ROLE_MATRIX.get(parsed, frozenset()):
            raise PermissionError(
                f"role {parsed.value} may not resolve a {finding.severity} finding"
            )
        stored = self.store.resolve_finding(finding_id, operator_id, note)
        logger.info(
            "finding %s (%s) resolved by %s (%s)", finding_id, finding.kind, operator_id, parsed
        )
        return stored

    # -------------------------------------------------------------- internals

    def _internal_orders(self) -> list[DurableOrder]:
        return self.store.orders(self.account_id)

    @staticmethod
    def _finding(
        run: ReconciliationRun,
        kind: AnomalyKind,
        detail: str,
        *,
        subject: str,
        internal_value: str | None,
        broker_value: str | None,
        window: ReconciliationWindow,
        account_id: str | None = None,
        strategy_id: str | None = None,
        execution_id: str | None = None,
    ) -> ReconciliationFinding:
        severity = SEVERITY_BY_KIND[kind]
        scope = (
            LOCKOUT_SCOPE_BY_KIND.get(kind, LockoutScope.ACCOUNT)
            if severity is ReconciliationSeverity.CRITICAL
            else LockoutScope.NONE
        )
        return ReconciliationFinding(
            run_id=run.run_id,
            kind=kind,
            severity=severity,
            subject=subject,
            detail=detail,
            internal_value=internal_value,
            broker_value=broker_value,
            scope=scope,
            broker=window.broker,
            account_id=account_id or window.account_id,
            strategy_id=strategy_id,
            execution_id=execution_id,
        )
