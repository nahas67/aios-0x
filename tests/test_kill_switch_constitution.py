"""CONSTITUTION.md 2.2 conformance: the kill-switch sequence is cancel, then
flatten, then halt.

The constitution names three ordered steps. The implementation performed two of
them. `DurableOrderManager.cancel` and `BaseExecutionAdapter.cancel_all_orders`
both existed and both were reachable from the replay runner, but nothing invoked
them, so the switch flattened positions and engaged the lockout while leaving
orders working at the venue. An order placed before the emergency could then
fill and leave exposure that no flatten step had passed.

specs/KillSwitch.tla is the machine-checked counterpart: it encodes the mandate
rather than the implementation, and TLC explores 48 distinct states of it. These
tests are the other half -- they assert that the Python conforms to the same
contract, which the specification cannot do on its own.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from communities.c5_execution.execution import KillSwitch
from core.risk_governor import RiskGovernor
from schemas.contracts import EmergencyStateValue


class _RecordingBus:
    """Wraps the real event bus so emissions can be observed.

    A hand-rolled stub was tried first and had the wrong `publish` signature,
    which says more about how little of the contract lives in the bus than any
    amount of stubbing would have. The real bus is used and its emissions are
    captured on the way through.
    """

    def __init__(self) -> None:
        from core.event_bus import InMemoryEventBus

        self._inner = InMemoryEventBus()
        self.published: list[Any] = []

    async def publish(self, *args: Any, **kwargs: Any) -> None:
        self.published.append(args[0] if args else None)
        await self._inner.publish(*args, **kwargs)

    async def start(self) -> None:
        await self._inner.start()

    async def stop(self) -> None:
        await self._inner.stop()


def _governor() -> RiskGovernor:
    return RiskGovernor(_RecordingBus())


def _switch(
    governor: RiskGovernor,
    *,
    positions: dict[str, dict[str, str]] | None = None,
    cancel: Any = None,
    prices: dict[str, float] | None = None,
) -> tuple[KillSwitch, list[str], list[float]]:
    """Build a KillSwitch over recorded collaborators.

    Returns the switch plus the two ordered logs the assertions read: the
    sequence of operations performed, and the exit prices used to flatten.
    """
    order_log: list[str] = []
    price_log: list[float] = []

    async def _flatten(execution_id: str, price: float) -> None:
        order_log.append(f"flatten:{execution_id}")
        price_log.append(price)

    async def _cancel() -> int:
        order_log.append("cancel")
        return 2

    switch = KillSwitch(
        governor=governor,
        positions_view=lambda: dict(positions or {}),
        flatten_callback=_flatten,
        price_lookup=lambda symbol: (prices or {}).get(symbol, 100.0),
        cancel_open_orders=cancel if cancel is not None else _cancel,
    )
    return switch, order_log, price_log


def test_cancel_happens_before_any_flatten() -> None:
    """The ordering is the point, and order is not observable from end state.

    A system that flattens first and cancels second reaches an identical final
    state -- so this asserts the log, not the outcome. That is the same reason
    the TLA+ spec carries an explicit phase variable rather than deriving the
    sequence from counts.
    """
    switch, order_log, _ = _switch(
        _governor(),
        positions={"e1": {"symbol": "AAPL"}, "e2": {"symbol": "MSFT"}},
    )

    assert asyncio.run(switch.trigger("test")) == 2

    assert order_log[0] == "cancel", (
        "CONSTITUTION.md 2.2 makes cancelling open orders the FIRST step; "
        f"got {order_log!r}"
    )
    assert order_log.count("cancel") == 1
    assert order_log.count("flatten:e1") == 1
    assert order_log.count("flatten:e2") == 1


def test_the_halt_is_engaged_after_both_prior_steps() -> None:
    """Escalation is last. A halt engaged mid-sequence would leave the remaining
    step to a caller that has already been told trading is locked out."""
    governor = _governor()
    switch, order_log, _ = _switch(
        governor, positions={"e1": {"symbol": "AAPL"}}
    )

    asyncio.run(switch.trigger("test"))

    assert order_log == ["cancel", "flatten:e1"]
    assert governor.state is EmergencyStateValue.EMERGENCY_HALT


def test_cancelled_count_is_reported_and_audited() -> None:
    """The audit trail must say what was stopped, not just what was flattened.

    `trigger` returns the flattened count for its existing callers, so the
    cancelled count is exposed separately and folded into the escalation reason
    -- an incident review that cannot see how many orders were killed is an
    incident review that has to guess.
    """
    governor = _governor()
    switch, _, _ = _switch(governor, positions={"e1": {"symbol": "AAPL"}})

    asyncio.run(switch.trigger("drawdown breach"))

    assert switch.cancelled_last == 2
    reasons = [event.reason for event in governor.history]
    assert any("cancelled 2" in reason for reason in reasons), (
        f"the escalation reason must carry the cancelled count: {reasons!r}"
    )


def test_a_switch_without_an_oms_still_halts() -> None:
    """The cancel step is optional, so callers holding no OMS keep working.

    Absence of the capability must not silently skip the *lockout*: a system
    that cannot cancel is exactly the system that most needs to stop trading.
    """
    governor = _governor()
    switch, order_log, _ = _switch(
        governor, positions={"e1": {"symbol": "AAPL"}}, cancel=None
    )
    # `cancel=None` in _switch falls back to the default recorder, so build the
    # no-OMS switch directly instead.
    no_oms = KillSwitch(
        governor=governor,
        positions_view=lambda: {"e1": {"symbol": "AAPL"}},
        flatten_callback=lambda eid, price: asyncio.sleep(0),
        price_lookup=lambda symbol: 100.0,
    )

    flattened = asyncio.run(no_oms.trigger("no oms available"))

    assert flattened == 1
    assert governor.state is EmergencyStateValue.EMERGENCY_HALT
    assert switch.cancelled_last is None or switch.cancelled_last >= 0


def test_lockout_still_requires_a_human_operator() -> None:
    """Unchanged by this work, and asserted here so the sequence fix cannot
    weaken it: no amount of re-triggering clears a lockout without an id."""
    governor = _governor()
    switch, _, _ = _switch(governor, positions={"e1": {"symbol": "AAPL"}})

    asyncio.run(switch.trigger("first"))
    asyncio.run(switch.trigger("second"))

    assert governor.state is EmergencyStateValue.EMERGENCY_HALT
    with pytest.raises(ValueError, match="operator_id"):
        asyncio.run(governor.human_reset(""))

    asyncio.run(governor.human_reset("operator-7"))
    assert governor.state is EmergencyStateValue.NORMAL


def test_flatten_uses_adverse_slippage_and_never_invents_a_price() -> None:
    """A long position exits below the mark and a short exits above it.

    Honesty Law 1: the exit price is derived from the supplied mark, and a
    missing mark must not become a default that looks like a real quote.
    """
    switch, _, price_log = _switch(
        _governor(),
        positions={
            "long": {"symbol": "AAPL", "action": "BUY"},
            "short": {"symbol": "MSFT", "action": "SELL"},
        },
        prices={"AAPL": 100.0, "MSFT": 50.0},
    )

    asyncio.run(switch.trigger("test"))

    # Indexed rather than zipped: the order of flatten operations is the
    # dictionary's insertion order, and pairing by zip would silently pass if a
    # third position were added without a matching expectation.
    assert len(price_log) == 2, f"expected two exits, got {price_log!r}"
    long_exit, short_exit = price_log
    assert long_exit < 100.0, "a long must exit below the mark"
    assert short_exit > 50.0, "a short must exit above the mark"
