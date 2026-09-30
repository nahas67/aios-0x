"""V1-A.2 — the safety plane actually stops capital changes (§33, §61).

The spec's completion standard is a chain, not a component:

    broker/external execution state
      -> normalized reconciliation snapshot
      -> deterministic comparison
      -> persistent findings
      -> safety lockout if required

...and the lockout must *bite*. A restriction that is recorded but not consulted
is theatre, so these tests drive the whole chain from a broker mismatch down to a
refused order, over the real composition path (``OrderManager`` -> adapter).

Also pinned here: a restriction stops **new orders** but never blocks the
application of a fill that already happened. Refusing a fill would make the book
disagree with the venue — the exact failure reconciliation exists to detect.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from communities.c5_execution.adapters import BaseExecutionAdapter
from communities.c5_execution.broker_reconciliation import (
    BrokerProvenance,
    BrokerReconciliationAdapter,
    RawBrokerPayload,
)
from communities.c5_execution.execution import OrderManager
from communities.c5_execution.oms import DurableOrderManager, OrderBlocked
from communities.c5_execution.reconciliation import ReconciliationEngine
from core.event_bus import InMemoryEventBus
from core.financial_kernel import (
    Fill,
    LockoutScope,
    ReconciliationMode,
    SafetyLockout,
    SqliteFinancialStore,
)
from core.persistence import SqliteMemoryStore
from core.safety_plane import SafetyAuthorizationError, SafetyPlane
from schemas.contracts import (
    OrderSide,
    OrderStatus,
    PortfolioAllocationPlan,
    StrategySpecification,
    TradeExecutionReceipt,
)

ACCOUNT = "acct-lockout"


# ------------------------------------------------------------------- fixtures


def _plan(symbol: str = "BTC/USD", strategy_id: str = "momentum-1") -> PortfolioAllocationPlan:
    spec = StrategySpecification(
        hypothesis_id="h1",
        strategy_id=strategy_id,
        symbol=symbol,
        action="BUY",
        entry_price=100.0,
        stop_loss_price=97.0,
        take_profit_price=106.0,
        position_size_pct=5.0,
    )
    return PortfolioAllocationPlan(
        strategy=spec,
        approved=True,
        final_position_size_pct=5.0,
        portfolio_status="HEALTHY",
        drawdown_pct=0.0,
    )


class RecordingAdapter(BaseExecutionAdapter):
    """Venue double that records submissions, so \"never reached the venue\" is provable."""

    def __init__(self, venue: str = "paper") -> None:
        self.venue = venue or "paper"
        self.submissions: list[tuple[str, float]] = []

    async def submit(
        self, plan: PortfolioAllocationPlan, quantity: float, **kwargs: Any
    ) -> TradeExecutionReceipt | None:
        self.submissions.append((plan.strategy.symbol, quantity))
        return TradeExecutionReceipt(
            execution_id=f"exec-{len(self.submissions)}",
            symbol=plan.strategy.symbol,
            side=plan.strategy.action,
            filled_quantity=quantity,
            fill_price=plan.strategy.entry_price,
            slippage=0.0,
            fees=0.0,
            strategy_id=plan.strategy.strategy_id,
        )

    def positions_snapshot(self) -> dict[str, float]:
        return {}


class Harness:
    def __init__(self, tmp_path: Path, *, venue: str = "paper") -> None:
        self.store = SqliteFinancialStore(tmp_path / "financial.db")
        self.audit = SqliteMemoryStore(tmp_path / "audit.db")
        self.safety = SafetyPlane(
            self.store, audit=self.audit, account_id=ACCOUNT, broker=venue
        )
        self.adapter = RecordingAdapter(venue)
        self.bus = InMemoryEventBus()
        self.oms = DurableOrderManager(
            self.store,
            account_id=ACCOUNT,
            safety=self.safety,
            broker=self.adapter.venue,
        )
        self.manager = OrderManager(
            event_bus=self.bus,
            adapter=self.adapter,
            quantity_provider=lambda plan: 1.0,
            durable=self.oms,
            safety=self.safety,
        )

    def engage(self, scope: LockoutScope, subject: str, reason: str = "test") -> SafetyLockout:
        return self.safety.engage(scope=scope, subject=subject, reason=reason)

    def close(self) -> None:
        self.store.close()
        self.audit.close()


@pytest.fixture
def harness(tmp_path: Path):
    built = Harness(tmp_path)
    asyncio.run(built.bus.start())
    try:
        yield built
    finally:
        asyncio.run(built.bus.stop())
        built.close()


# ------------------------------------------------------- the gate itself


def test_account_lockout_refuses_the_order_before_the_venue(harness: Harness) -> None:
    harness.engage(LockoutScope.ACCOUNT, ACCOUNT, "CRITICAL cash mismatch")

    receipt = asyncio.run(harness.manager.on_plan(_plan(), locked_out=False))

    assert receipt is None
    assert harness.adapter.submissions == [], "a restricted account reached the venue"
    assert harness.store.orders() == [], "a restricted account even wrote an order"
    assert harness.store.fills() == []


def test_global_lockout_refuses_every_strategy(harness: Harness) -> None:
    harness.engage(LockoutScope.GLOBAL, "*", "kill switch")
    for strategy_id in ("momentum-1", "meanrev-2", "carry-3"):
        assert (
            asyncio.run(harness.manager.on_plan(_plan(strategy_id=strategy_id), locked_out=False))
            is None
        )
    assert harness.adapter.submissions == []


def test_strategy_scoped_lockout_blocks_only_that_strategy(harness: Harness) -> None:
    harness.engage(LockoutScope.STRATEGY, "momentum-1", "strategy degraded in live")

    blocked = asyncio.run(harness.manager.on_plan(_plan(strategy_id="momentum-1"), locked_out=False))
    allowed = asyncio.run(harness.manager.on_plan(_plan(strategy_id="carry-3"), locked_out=False))

    assert blocked is None
    assert allowed is not None
    assert harness.adapter.submissions == [("BTC/USD", 1.0)]


def test_broker_scoped_lockout_does_not_block_a_different_venue(harness: Harness) -> None:
    harness.engage(LockoutScope.BROKER, "ccxt:binance:LIVE", "venue disconnected")

    # This manager talks to "paper", so it is unaffected.
    assert asyncio.run(harness.manager.on_plan(_plan(), locked_out=False)) is not None
    assert harness.adapter.submissions == [("BTC/USD", 1.0)]


def test_lockout_on_another_account_does_not_block(harness: Harness) -> None:
    harness.engage(LockoutScope.ACCOUNT, "some-other-account", "their problem")
    assert asyncio.run(harness.manager.on_plan(_plan(), locked_out=False)) is not None


def test_write_ahead_oms_refuses_a_restricted_account(harness: Harness) -> None:
    """Defence in depth: even a caller that skips OrderManager cannot write intent."""
    harness.engage(LockoutScope.ACCOUNT, ACCOUNT, "restricted")
    with pytest.raises(OrderBlocked) as caught:
        harness.oms.prepare_order(
            client_order_id="direct-1",
            strategy_id="momentum-1",
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
        )
    assert "restricted" in str(caught.value)
    assert harness.store.orders() == []


def test_release_restores_trading(harness: Harness) -> None:
    lockout = harness.engage(LockoutScope.ACCOUNT, ACCOUNT, "restricted")
    assert asyncio.run(harness.manager.on_plan(_plan(), locked_out=False)) is None

    harness.safety.release(
        lockout.lockout_id, operator_id="risk-1", role="RISK_ADMIN", note="verified with venue"
    )
    assert asyncio.run(harness.manager.on_plan(_plan(), locked_out=False)) is not None


def test_a_restriction_cannot_be_lifted_by_an_agent_identity(harness: Harness) -> None:
    lockout = harness.engage(LockoutScope.ACCOUNT, ACCOUNT, "restricted")
    for role in ("VIEWER", "OPERATOR", "AGENT", "SERVICE"):
        with pytest.raises(SafetyAuthorizationError):
            harness.safety.release(
                lockout.lockout_id, operator_id="agent-x", role=role, note="let me trade"
            )
    assert len(harness.store.active_lockouts()) == 1


def test_lockout_survives_a_restart_and_still_blocks(harness: Harness) -> None:
    """The gate reads durable state, so a new process inherits the restriction."""
    harness.engage(LockoutScope.ACCOUNT, ACCOUNT, "restricted")

    reopened = SqliteFinancialStore(harness.store.db_path)
    try:
        fresh_plane = SafetyPlane(
            reopened, account_id=ACCOUNT, broker="paper"
        )
        decision = fresh_plane.is_blocked()
        assert decision.blocked is True
        assert ACCOUNT in decision.reasons[0]
        fresh_oms = DurableOrderManager(reopened, account_id=ACCOUNT, safety=fresh_plane)
        with pytest.raises(OrderBlocked):
            fresh_oms.prepare_order(
                client_order_id="after-restart",
                strategy_id="momentum-1",
                symbol="BTC/USD",
                side=OrderSide.BUY,
                quantity=1.0,
            )
    finally:
        reopened.close()


# ---------------------------------------------------- fills must NOT be blocked


def test_pending_fill_still_applies_while_the_account_is_restricted(
    harness: Harness,
) -> None:
    """A fill that already happened must be booked, restriction or not.

    Suppressing it would leave internal positions disagreeing with the venue,
    which is precisely the discrepancy reconciliation exists to detect.
    """
    order = harness.oms.prepare_order(
        client_order_id="pre-lockout",
        strategy_id="momentum-1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=2.0,
    )
    harness.oms.accept(order.internal_order_id, broker_order_id="b-1")

    harness.engage(LockoutScope.ACCOUNT, ACCOUNT, "mismatch found mid-flight")

    applied = harness.oms.apply_fill(
        Fill(
            fill_id="fill-mid-flight",
            order_id=order.internal_order_id,
            broker_execution_id="exec-mid-flight",
            account_id=ACCOUNT,
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=100.0,
        )
    )
    assert applied is True
    position = harness.store.positions(ACCOUNT)[0]
    assert position.quantity == pytest.approx(1.0)


# --------------------------- the whole chain: broker -> finding -> lockout -> stop


class BrokerDouble(BrokerReconciliationAdapter):
    """A venue reporting an execution we never booked, plus one we did."""

    name = "fake-broker"
    version = "1.0.0"
    mode = ReconciliationMode.FULL_SNAPSHOT

    def __init__(self, executions: list[dict[str, object]]) -> None:
        self._executions = executions

    def fetch(self, account_id: str, **kwargs: object) -> RawBrokerPayload:
        return RawBrokerPayload(
            provenance=BrokerProvenance(
                broker=self.name,
                account_id=account_id,
                queried_at=datetime.now(UTC),
                mode=self.mode,
                adapter_version=self.version,
            ),
            executions=list(self._executions),
        )


def test_broker_mismatch_flows_to_a_lockout_that_stops_execution(
    harness: Harness,
) -> None:
    # Internal truth: one order, one fill, fully booked.
    order = harness.oms.prepare_order(
        client_order_id="chain-1",
        strategy_id="momentum-1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=1.0,
    )
    harness.oms.accept(order.internal_order_id, broker_order_id="b-9")
    # A venue echoes back the client order id it was sent, which the write-ahead
    # OMS scoped to the attempt; the broker rows must use that same identity.
    sent_client_order_id = harness.store.order(order.internal_order_id).client_order_id  # type: ignore[union-attr]
    harness.oms.apply_fill(
        Fill(
            fill_id="fill-chain-1",
            order_id=order.internal_order_id,
            broker_execution_id="exec-known",
            account_id=ACCOUNT,
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=100.0,
        )
    )
    # The venue also reports an execution nobody booked, at a different price.
    assert asyncio.run(harness.manager.on_plan(_plan(strategy_id="carry-3"), locked_out=False))

    # Raw venue rows, exactly as an adapter would receive them from a broker API.
    broker = BrokerDouble(
        [
            {
                "broker_execution_id": "exec-known",
                "client_order_id": sent_client_order_id,
                "symbol": "BTC/USD",
                "side": "BUY",
                "quantity": 1.0,
                "price": 100.0,
            },
            {
                "broker_execution_id": "exec-ghost",
                "client_order_id": "never-sent",
                "symbol": "BTC/USD",
                "side": "BUY",
                "quantity": 7.0,
                "price": 99.0,
            },
        ]
    )
    engine = ReconciliationEngine(harness.store, account_id=ACCOUNT, safety=harness.safety)
    result = engine.reconcile(broker.snapshot(ACCOUNT))

    assert result.run.broker_only_executions == 1, result.run
    assert any("exec-ghost" in f.subject for f in result.findings)
    assert result.requires_lockout is True
    assert result.engaged_lockouts, "a CRITICAL mismatch must restrict the account"
    assert len(harness.store.active_lockouts()) == 1

    # ...and now the venue is unreachable for NEW orders, but the book still holds.
    # (The recording adapter books no fills, so the 1.0 from the known execution
    # is the whole position; the point is that the lockout changes nothing.)
    submitted_before = len(harness.adapter.submissions)
    booked_before = harness.store.positions(ACCOUNT)[0].quantity
    assert booked_before == pytest.approx(1.0)
    assert asyncio.run(harness.manager.on_plan(_plan(strategy_id="carry-3"), locked_out=False)) is None
    assert len(harness.adapter.submissions) == submitted_before
    assert harness.store.positions(ACCOUNT)[0].quantity == pytest.approx(booked_before)

    # Only a RISK_ADMIN can clear it, and only then does trading resume.
    lockout = harness.store.active_lockouts()[0]
    harness.safety.release(
        lockout.lockout_id, operator_id="risk-1", role="RISK_ADMIN", note="venue confirmed"
    )
    # A fresh strategy id: "carry-3" already has a live order, so re-submitting it
    # would be suppressed by idempotency rather than proving the gate reopened.
    assert asyncio.run(harness.manager.on_plan(_plan(strategy_id="carry-4"), locked_out=False)) is not None


def test_open_order_survives_the_restriction_intact(harness: Harness) -> None:
    order = harness.oms.prepare_order(
        client_order_id="still-open",
        strategy_id="momentum-1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=5.0,
    )
    harness.oms.accept(order.internal_order_id, broker_order_id="b-open")
    harness.engage(LockoutScope.ACCOUNT, ACCOUNT, "restricted")

    live = harness.oms.recover_open_orders()
    assert [o.client_order_id for o in live] == ["still-open"]
    assert live[0].status is OrderStatus.ACCEPTED
    assert live[0].broker_order_id == "b-open"
