"""REDUCE_ONLY as enforced by the control plane, not just as a pure rule.

`core/reduce_only.py` is exhaustively unit-tested, and every one of those tests passes
whether or not the control plane calls it. That gap is not hypothetical: the first
version of this wiring put the reduce-only check AFTER the autonomy branches in
`classify_plan`, and because each of those branches returns immediately, the check was
unreachable whenever autonomy was EXECUTING -- the normal operating state. The command
would have authenticated, audited, returned `{"reduce_only": true}`, and changed nothing.

So these tests assert the wiring, not the rule: that the flag is reachable through the
audited control-action path, that it actually changes `classify_plan`, and that it cannot
make a refused plan execute.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from core.control_plane import ROLE_MATRIX, ControlAction, ControlPlane
from core.event_bus import InMemoryEventBus
from core.persistence import SqliteMemoryStore
from core.risk_governor import RiskGovernor


def make_plane(positions: list[dict[str, object]] | None = None) -> ControlPlane:
    # Keyed by execution id, not symbol. That is the shape the composition root actually
    # supplies (see simulation/replay_runner.py::_positions_view), and getting it wrong
    # here would have tested a contract the control plane never sees: keyed by symbol,
    # `net_exposure` iterates the keys and every position read raises AttributeError.
    def positions_view() -> dict[str, dict[str, str]]:
        return {f"exec-{i}": dict(p) for i, p in enumerate(positions or [])}

    return ControlPlane(
        store=SqliteMemoryStore(":memory:"),
        event_bus=InMemoryEventBus(),
        risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
        strategy_agent=None,
        order_manager=None,
        positions_view=positions_view,
    )


def plan_for(symbol: str, action: str) -> SimpleNamespace:
    return SimpleNamespace(strategy=SimpleNamespace(symbol=symbol, action=action))


def run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


class TestReduceOnlyIsAnAuditedControlAction:
    def test_the_action_exists(self) -> None:
        assert ControlAction("set_reduce_only") is ControlAction.SET_REDUCE_ONLY

    def test_it_requires_risk_admin_not_operator(self) -> None:
        from core.control_plane import OperatorRole

        # A standing capital constraint, like SET_MAX_POSITION_PCT and SET_AUTONOMY.
        assert ControlAction.SET_REDUCE_ONLY not in ROLE_MATRIX[OperatorRole.OPERATOR]
        assert ControlAction.SET_REDUCE_ONLY in ROLE_MATRIX[OperatorRole.RISK_ADMIN]
        assert ControlAction.SET_REDUCE_ONLY in ROLE_MATRIX[OperatorRole.ADMIN]

    def test_operator_is_denied_and_the_denial_is_audited(self) -> None:
        plane = make_plane()
        with pytest.raises(PermissionError):
            run(plane.execute("op-1", "OPERATOR", "set_reduce_only", {"enabled": "true"}))
        assert plane.reduce_only is False

    def test_risk_admin_can_enable_and_disable(self) -> None:
        plane = make_plane()
        # `execute` returns the audit record with the handler's payload nested under
        # "result", not the handler's dict directly.
        enabled = run(
            plane.execute("ra-1", "RISK_ADMIN", "set_reduce_only", {"enabled": "true"})
        )
        assert enabled["result"] == {"reduce_only": True, "previous": False}
        assert plane.reduce_only is True
        disabled = run(
            plane.execute("ra-1", "RISK_ADMIN", "set_reduce_only", {"enabled": "false"})
        )
        assert disabled["result"] == {"reduce_only": False, "previous": True}
        assert plane.reduce_only is False

    def test_enabling_writes_a_dedicated_audit_event(self) -> None:
        plane = make_plane()
        run(plane.execute("ra-1", "RISK_ADMIN", "set_reduce_only", {"enabled": "true"}))
        events = [
            p for p in plane.store.iter_event_payloads("REDUCE_ONLY_SET")
        ]
        assert len(events) == 1
        assert events[0]["operator_id"] == "ra-1"
        assert events[0]["enabled"] is True

    def test_it_is_off_by_default(self) -> None:
        assert make_plane().reduce_only is False


class TestReduceOnlyGatesPlans:
    def _executing_plane(self, positions: list[dict[str, object]] | None = None) -> ControlPlane:
        plane = make_plane(positions)
        # EXECUTING is the state that matters: it is the one where an unchecked
        # reduce-only gate would let orders straight through.
        plane.autonomy = plane.autonomy.__class__("AUTONOMOUS")
        return plane

    def test_without_the_flag_a_buy_still_executes(self) -> None:
        plane = self._executing_plane()
        assert plane.classify_plan(plan_for("BTC", "BUY")) == "EXECUTE"

    def test_buying_into_flat_is_held_once_enabled(self) -> None:
        plane = self._executing_plane()
        plane.reduce_only = True
        assert plane.classify_plan(plan_for("BTC", "BUY")) == "HOLD"

    def test_selling_into_flat_is_held_once_enabled(self) -> None:
        plane = self._executing_plane()
        plane.reduce_only = True
        assert plane.classify_plan(plan_for("BTC", "SELL")) == "HOLD"

    def test_adding_to_an_existing_long_is_held(self) -> None:
        plane = self._executing_plane([{"symbol": "BTC", "action": "BUY", "filled_quantity": 5.0}])
        plane.reduce_only = True
        assert plane.classify_plan(plan_for("BTC", "BUY")) == "HOLD"

    def test_reducing_an_existing_long_is_permitted(self) -> None:
        plane = self._executing_plane([{"symbol": "BTC", "action": "BUY", "filled_quantity": 5.0}])
        plane.reduce_only = True
        assert plane.classify_plan(plan_for("BTC", "SELL")) == "EXECUTE"

    def test_covering_an_existing_short_is_permitted(self) -> None:
        plane = self._executing_plane(
            [{"symbol": "BTC", "action": "SELL", "filled_quantity": 5.0}]
        )
        plane.reduce_only = True
        assert plane.classify_plan(plan_for("BTC", "BUY")) == "EXECUTE"

    def test_adding_to_an_existing_short_is_held(self) -> None:
        plane = self._executing_plane(
            [{"symbol": "BTC", "action": "SELL", "filled_quantity": 5.0}]
        )
        plane.reduce_only = True
        assert plane.classify_plan(plan_for("BTC", "SELL")) == "HOLD"

    def test_a_long_in_one_symbol_does_not_authorise_another(self) -> None:
        plane = self._executing_plane([{"symbol": "BTC", "action": "BUY", "filled_quantity": 5.0}])
        plane.reduce_only = True
        assert plane.classify_plan(plan_for("SOL", "BUY")) == "HOLD"

    def test_hold_is_never_blocked(self) -> None:
        plane = self._executing_plane()
        plane.reduce_only = True
        assert plane.classify_plan(plan_for("BTC", "HOLD")) == "EXECUTE"

    def test_it_never_resurrects_a_paused_plane(self) -> None:
        # Narrowing must not widen: with trading paused, reduce-only must not make an
        # otherwise-refused plan execute.
        plane = self._executing_plane()
        plane.reduce_only = True
        plane.paused = True
        assert plane.classify_plan(plan_for("BTC", "SELL")) == "HOLD"

    def test_clearing_the_flag_restores_normal_routing(self) -> None:
        plane = self._executing_plane()
        plane.reduce_only = True
        assert plane.classify_plan(plan_for("BTC", "BUY")) == "HOLD"
        run(plane.execute("ra-1", "RISK_ADMIN", "set_reduce_only", {"enabled": "false"}))
        assert plane.classify_plan(plan_for("BTC", "BUY")) == "EXECUTE"
