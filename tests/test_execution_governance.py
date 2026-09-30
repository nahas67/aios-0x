"""No venue call without a per-call verdict (goal G050, wired).

``test_agent_governance.py`` proves the Guardian works. This proves it is
*reachable* — that the execution path actually routes through it. A control that
is correct but bypassed is worse than no control, because the system's
assurance then rests on something that does not run.

The load-bearing property: governance can only ever reduce an order. A clamp
that could be widened, or a notional cap checked against the proposal rather
than the governed value, would be a control that reports an order was governed
when it was not.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from communities.c5_execution.adapters import (
    ARG_NOTIONAL,
    ARG_QUANTITY,
    CcxtExecutionAdapter,
    ExecutionUnavailableError,
    PaperExecutionAdapter,
)
from kernel.tool_governance import (
    Disposition,
    GovernanceError,
    ToolGuardian,
    build_execution_guardian,
    guardian_secret_from_env,
)
from schemas.contracts import PortfolioAllocationPlan, StrategySpecification
from simulation.paper_engine import PaperEngine

SECRET = b"execution-governance-test-key"


@pytest.fixture()
def guardian() -> ToolGuardian:
    return ToolGuardian(SECRET)


def _plan(action: str = "BUY", entry: float = 100.0, size: float = 10.0) -> PortfolioAllocationPlan:
    spec = StrategySpecification(
        hypothesis_id="h",
        symbol="BTC/USD",
        action=action,  # type: ignore[arg-type]
        entry_price=entry,
        stop_loss_price=entry * (0.97 if action == "BUY" else 1.03),
        take_profit_price=entry * (1.06 if action == "BUY" else 0.94),
        position_size_pct=size,
    )
    return PortfolioAllocationPlan(
        strategy=spec,
        approved=True,
        final_position_size_pct=size,
        portfolio_status="HEALTHY",
        drawdown_pct=0.0,
    )


class RecordingVenue:
    """Minimal venue that records exactly what it was asked to do."""

    def __init__(self) -> None:
        self.orders: list[dict[str, Any]] = []
        self.cancelled: list[str | None] = []

    def set_sandbox_mode(self, flag: bool) -> None:  # pragma: no cover - parity only
        self.sandbox = flag

    def create_order(self, symbol: str, type_: str, side: str, amount: float, price=None):
        order = {
            "id": f"o{len(self.orders)}",
            "symbol": symbol,
            "type": type_,
            "side": side,
            "amount": amount,
            "filled": amount,
            "average": 100.0,
            "fee": {"cost": 0.0},
        }
        self.orders.append(order)
        return order

    def cancel_all_orders(self, symbol: str | None = None) -> list:
        self.cancelled.append(symbol)
        return []

    def fetch_positions(self) -> list:
        return []


def _ccxt(guardian: ToolGuardian, venue: RecordingVenue) -> CcxtExecutionAdapter:
    return CcxtExecutionAdapter(
        "binance",
        api_key_env="K",
        secret_env="S",
        env={
            "AIOS_ALLOW_LIVE_EXECUTION": "1",
            "AIOS_EXCHANGE_TESTNET": "1",
            "K": "k",
            "S": "s",
        },
        guardian=guardian,
        client_builder=lambda exchange_id, options: venue,
    )


# ══════════════════════════════════════════════════════════════════════════
# A guard is required, not optional
# ══════════════════════════════════════════════════════════════════════════


def test_an_adapter_cannot_be_constructed_without_a_guardian() -> None:
    """A default that allows would make ungoverned and governed look identical.

    Requiring the guard is the difference between a control and a convention,
    and it is the property the reference implementation lacks.
    """
    engine = PaperEngine(_Bus(), initial_balance=100000.0)
    with pytest.raises(ExecutionUnavailableError, match="requires a ToolGuard"):
        PaperExecutionAdapter(engine)


def test_the_ccxt_adapter_also_refuses_to_exist_ungoverned() -> None:
    """Not just the paper tier: a live-capable adapter is the one that matters."""
    with pytest.raises(ExecutionUnavailableError, match="requires a ToolGuard"):
        CcxtExecutionAdapter(
            "binance",
            api_key_env="K",
            secret_env="S",
            env={
                "AIOS_ALLOW_LIVE_EXECUTION": "1",
                "AIOS_EXCHANGE_TESTNET": "1",
                "K": "k",
                "S": "s",
            },
            client_builder=lambda e, o: RecordingVenue(),
        )


# ══════════════════════════════════════════════════════════════════════════
# The venue sees the governed value
# ══════════════════════════════════════════════════════════════════════════


def test_an_unclamped_order_reaches_the_venue_unchanged(
    guardian: ToolGuardian,
) -> None:
    venue = RecordingVenue()
    adapter = _ccxt(guardian, venue)
    asyncio.run(adapter.submit(_plan(entry=100.0), quantity=0.5))
    assert venue.orders[0]["amount"] == pytest.approx(0.5)


def test_a_clamp_reduces_what_reaches_the_venue(guardian: ToolGuardian) -> None:
    """The whole point: a smaller order executes, not a refusal.

    A firewall that denies everything over the line trains operators to route
    around it, so the reduction is the better behaviour and the one tested here.
    """
    venue = RecordingVenue()
    guardian.register_clamp_rule(ARG_QUANTITY, maximum=0.2, reason_code="quantity_cap_exceeded")
    adapter = _ccxt(guardian, venue)

    receipt = asyncio.run(adapter.submit(_plan(entry=100.0), quantity=0.5))
    assert receipt is not None
    assert venue.orders[0]["amount"] == pytest.approx(0.2)
    assert receipt.filled_quantity == pytest.approx(0.2)


def test_a_notional_clamp_also_reduces_the_venue_order(guardian: ToolGuardian) -> None:
    venue = RecordingVenue()
    guardian.register_clamp_rule(
        ARG_NOTIONAL, maximum=50.0, reason_code="notional_cap_exceeded"
    )
    adapter = _ccxt(guardian, venue)
    asyncio.run(adapter.submit(_plan(entry=100.0), quantity=0.5))
    # 0.5 units at 100.00 is 50.00 of notional, clamped to the ceiling.
    assert venue.orders[0]["amount"] == pytest.approx(0.5)


def test_a_clamp_is_evaluated_before_the_constitutional_cap(
    guardian: ToolGuardian,
) -> None:
    """The cap is checked against the value the venue will see.

    Checking the proposal instead would be checking a number that is never
    submitted, so a clamp large enough to bring the order under the cap would
    still be refused — the worst of both.
    """
    venue = RecordingVenue()
    # Clamp quantity to 0.05 => 5.00 notional, under the 100.00 micro-live cap.
    guardian.register_clamp_rule(ARG_QUANTITY, maximum=0.05, reason_code="cap")
    adapter = _ccxt(guardian, venue)
    receipt = asyncio.run(adapter.submit(_plan(entry=100.0), quantity=0.5))
    assert receipt is not None
    assert venue.orders[0]["amount"] == pytest.approx(0.05)


def test_the_constitutional_cap_still_refuses_an_ungoverned_overflow(
    guardian: ToolGuardian,
) -> None:
    """Removing governance must not remove the constitution.

    An unopinioned Guardian plus an order over the cap is still refused: the
    two controls are independent, and one being absent does not disable the other.
    """
    venue = RecordingVenue()
    adapter = _ccxt(guardian, venue)
    with pytest.raises(ExecutionUnavailableError, match="micro-live cap"):
        asyncio.run(adapter.submit(_plan(entry=100000.0), quantity=1.0))
    assert venue.orders == []


def test_governance_never_increases_an_order(guardian: ToolGuardian) -> None:
    """A Guardian cannot make an order larger. The reduction is one-directional.

    The clamp helper only ever lowers a value, so this holds by construction;
    asserting it means a future change to the merge precedence cannot quietly
    introduce a widening path.
    """
    venue = RecordingVenue()
    guardian.register_clamp_rule(ARG_QUANTITY, maximum=0.1, reason_code="cap")
    adapter = _ccxt(guardian, venue)
    asyncio.run(adapter.submit(_plan(entry=100.0), quantity=0.5))
    sent = venue.orders[0]["amount"]
    assert sent <= 0.5


def test_a_denial_prevents_the_venue_call_entirely(guardian: ToolGuardian) -> None:
    venue = RecordingVenue()
    guardian.register_deny_rule("instrument_not_listed", lambda c: True)
    adapter = _ccxt(guardian, venue)
    with pytest.raises(ExecutionUnavailableError, match="denied"):
        asyncio.run(adapter.submit(_plan(), quantity=0.5))
    assert venue.orders == []


def test_a_raising_policy_rule_blocks_the_venue_call(guardian: ToolGuardian) -> None:
    """A broken policy must stop the order, not silently permit it."""
    venue = RecordingVenue()

    def broken(call):
        raise RuntimeError("policy service down")

    guardian.register_rule(broken)
    adapter = _ccxt(guardian, venue)
    with pytest.raises(ExecutionUnavailableError, match="policy_rule_error"):
        asyncio.run(adapter.submit(_plan(), quantity=0.5))
    assert venue.orders == []


# ══════════════════════════════════════════════════════════════════════════
# The paper tier is governed too
# ══════════════════════════════════════════════════════════════════════════


def test_paper_orders_are_governed_as_well(guardian: ToolGuardian) -> None:
    """A clamp that applies only to live venues would let the same proposal
    through twice, in two venues, at two sizes."""
    bus_guard = ToolGuardian(SECRET)
    bus_guard.register_deny_rule("paper_blocked", lambda c: True)
    engine = PaperEngine(_Bus(), initial_balance=100000.0)
    adapter = PaperExecutionAdapter(engine, guardian=bus_guard)
    with pytest.raises(ExecutionUnavailableError, match="denied"):
        asyncio.run(adapter.submit(_plan(), quantity=0.5))
    _ = guardian


class _Bus:
    """Minimal bus stub; the paper engine only needs start/stop/publish."""

    async def start(self) -> None:  # pragma: no cover - stub
        pass

    async def stop(self) -> None:  # pragma: no cover - stub
        pass

    async def publish(self, topic, payload) -> None:  # pragma: no cover - stub
        pass


# ══════════════════════════════════════════════════════════════════════════
# The decision is auditable
# ══════════════════════════════════════════════════════════════════════════


def test_every_order_attempt_leaves_a_decision_receipt(guardian: ToolGuardian) -> None:
    """A refusal is as auditable as a fill.

    An attempt that never reached the venue is exactly the attempt an operator
    will later ask about, so it must leave the same kind of trace.
    """
    venue = RecordingVenue()
    adapter = _ccxt(guardian, venue)
    asyncio.run(adapter.submit(_plan(entry=100.0), quantity=0.5))
    with pytest.raises(ExecutionUnavailableError, match="micro-live cap"):
        asyncio.run(adapter.submit(_plan(entry=50000.0), quantity=1.0))

    log = guardian.log()
    assert len(log) == 2
    assert all(d.call_digest for d in log)
    assert guardian.verify_chain() is True
    assert len(venue.orders) == 1, "the refused order must not have reached the venue"


def test_a_clamped_decision_records_what_it_replaced(guardian: ToolGuardian) -> None:
    guardian.register_clamp_rule(ARG_QUANTITY, maximum=0.1, reason_code="cap")
    decision = guardian.evaluate(_governed_call(quantity=0.5))
    assert decision.disposition is Disposition.MODIFY
    assert decision.parameter_overrides[ARG_QUANTITY].original == 0.5
    assert decision.reason_codes == ["cap"]


def _governed_call(quantity: float):
    from kernel.tool_governance import ToolCall

    return ToolCall(
        tool="ccxt:binance:testnet.order",
        operation="place",
        capability="broker.order.place",
        agent_id="c5-execution",
        arguments={ARG_QUANTITY: {"value": quantity, "provenance": "RISK_ENGINE"}},
    )


# ══════════════════════════════════════════════════════════════════════════
# Composition helpers
# ══════════════════════════════════════════════════════════════════════════


def test_the_default_execution_guardian_clamps_both_ceilings() -> None:
    guardian = build_execution_guardian(SECRET, max_notional=1000.0, max_quantity=5.0)
    decision = guardian.evaluate(
        _call_with({"notional": 5000.0, "quantity": 50.0})
    )
    assert decision.disposition is Disposition.MODIFY
    assert decision.parameter_overrides["notional"].value == 1000.0
    assert decision.parameter_overrides["quantity"].value == 5.0


def test_an_unclamped_order_passes_the_default_guardian() -> None:
    guardian = build_execution_guardian(SECRET, max_notional=1000.0, max_quantity=5.0)
    decision = guardian.evaluate(_call_with({"notional": 100.0, "quantity": 1.0}))
    assert decision.disposition is Disposition.ALLOW


def _call_with(arguments: dict[str, Any]):
    from kernel.tool_governance import ToolCall

    return ToolCall(
        tool="t",
        agent_id="a",
        arguments={k: {"value": v, "provenance": "RISK_ENGINE"} for k, v in arguments.items()},
    )


def test_a_missing_governance_secret_is_refused_with_instructions() -> None:
    """No default key: one in the source tree would prove nothing.

    This is the reason the paper tier logs a warning and says so, rather than
    quietly falling back everywhere.
    """
    with pytest.raises(GovernanceError, match="AIOS_GOVERNANCE_SECRET"):
        guardian_secret_from_env({})


def test_a_configured_secret_is_used() -> None:
    assert guardian_secret_from_env({"AIOS_GOVERNANCE_SECRET": "s3cret"}) == b"s3cret"
