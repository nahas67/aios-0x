"""Human control plane with RBAC (Directives 47/80).

Every action requires an operator identity and a role; every execution is
appended to the audit store as a CONTROL_ACTION event. Role matrix:

    VIEWER      - read-only (no actions)
    OPERATOR    - pause/resume trading, cancel orders, freeze/unfreeze symbols
    RISK_ADMIN  - OPERATOR + set limits, trigger kill switch, reset lockout
    ADMIN       - RISK_ADMIN + approve live capital

Actions delegate to components injected by the composition root; the plane
never reaches into community internals beyond that wiring.
"""

import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from core.event_bus import BaseEventBus
from core.persistence import BaseMemoryStore
from core.risk_governor import RiskGovernor
from schemas.contracts import (
    DataAnomalyAlert,
    EmergencyStateValue,
    OrderStatus,
    is_terminal,
)

logger = logging.getLogger(__name__)


class OperatorRole(StrEnum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    RISK_ADMIN = "RISK_ADMIN"
    ADMIN = "ADMIN"


class ControlAction(StrEnum):
    PAUSE_TRADING = "pause_trading"
    RESUME_TRADING = "resume_trading"
    CANCEL_OPEN_ORDERS = "cancel_open_orders"
    FREEZE_SYMBOL = "freeze_symbol"
    UNFREEZE_SYMBOL = "unfreeze_symbol"
    SET_MAX_POSITION_PCT = "set_max_position_pct"
    SET_HALT_DRAWDOWN_PCT = "set_halt_drawdown_pct"
    TRIGGER_KILL_SWITCH = "trigger_kill_switch"
    RESET_LOCKOUT = "reset_lockout"
    APPROVE_LIVE_CAPITAL = "approve_live_capital"
    PROMOTE_CHALLENGER = "promote_challenger"


def _build_matrix() -> dict[OperatorRole, frozenset[ControlAction]]:
    operator = frozenset(
        {
            ControlAction.PAUSE_TRADING,
            ControlAction.RESUME_TRADING,
            ControlAction.CANCEL_OPEN_ORDERS,
            ControlAction.FREEZE_SYMBOL,
            ControlAction.UNFREEZE_SYMBOL,
        }
    )
    risk_admin = operator | {
        ControlAction.SET_MAX_POSITION_PCT,
        ControlAction.SET_HALT_DRAWDOWN_PCT,
        ControlAction.TRIGGER_KILL_SWITCH,
        ControlAction.RESET_LOCKOUT,
        ControlAction.PROMOTE_CHALLENGER,
    }
    admin = risk_admin | {ControlAction.APPROVE_LIVE_CAPITAL}
    return {
        OperatorRole.VIEWER: frozenset(),
        OperatorRole.OPERATOR: operator,
        OperatorRole.RISK_ADMIN: frozenset(risk_admin),
        OperatorRole.ADMIN: frozenset(admin),
    }


ROLE_MATRIX = _build_matrix()

Handler = Callable[..., Awaitable[dict[str, Any]]]


class ControlPlane:
    """Audited operator console over live system components."""

    def __init__(
        self,
        store: BaseMemoryStore,
        event_bus: BaseEventBus,
        risk_governor: RiskGovernor,
        strategy_agent: Any,
        order_manager: Any,
        governor: Any = None,
        paper_engine: Any = None,
        challenge_registry: Any = None,
        price_lookup: Callable[[str], float] | None = None,
        flatten_callback: Callable[[str, float], Awaitable[None]] | None = None,
        positions_view: Callable[[], dict[str, dict[str, str]]] | None = None,
    ) -> None:
        self.store = store
        self.event_bus = event_bus
        self.risk_governor = risk_governor
        self.strategy_agent = strategy_agent
        self.order_manager = order_manager
        self.governor = governor
        self.paper_engine = paper_engine
        self.challenge_registry = challenge_registry
        self._price_lookup = price_lookup or (lambda symbol: 0.0)
        self._flatten = flatten_callback
        self._positions_view = positions_view or (lambda: {})
        self.paused = False
        self.live_capital_approved_by: str | None = None

    # ------------------------------------------------------------------ authz

    def authorize(self, role: OperatorRole, action: ControlAction) -> bool:
        return action in ROLE_MATRIX.get(role, frozenset())

    async def execute(
        self,
        operator_id: str,
        role: str,
        action: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Authorize + perform one control action; returns an audited record."""
        params = params or {}
        if not operator_id.strip():
            raise ValueError("operator_id required")

        def _deny(reason: str, parsed_role: str = "UNKNOWN") -> PermissionError:
            self.store.append_event(
                "CONTROL_ACTION",
                None,
                {
                    "operator_id": operator_id,
                    "role": parsed_role,
                    "action": action,
                    "authorized": False,
                    "reason": reason,
                    "params": params,
                },
            )
            return PermissionError(reason)

        try:
            role_enum = OperatorRole(role.upper())
        except ValueError as exc:
            raise _deny(f"unknown role: {role!r}") from exc
        try:
            action_enum = ControlAction(action.lower())
        except ValueError as exc:
            raise _deny(f"unknown action: {action!r}", role_enum.value) from exc

        if not self.authorize(role_enum, action_enum):
            record = {
                "operator_id": operator_id,
                "role": role_enum.value,
                "action": action_enum.value,
                "authorized": False,
                "params": params,
            }
            self.store.append_event("CONTROL_ACTION", None, record)
            raise PermissionError(f"role {role_enum.value} may not perform {action_enum.value}")

        handler_name = f"_do_{action_enum.value}"
        handler: Handler | None = getattr(self, handler_name, None)
        if handler is None:
            raise NotImplementedError(action_enum.value)

        result = await handler(operator_id, **params)
        result_record = {
            "operator_id": operator_id,
            "role": role_enum.value,
            "action": action_enum.value,
            "authorized": True,
            "params": params,
            "result": result,
        }
        self.store.append_event("CONTROL_ACTION", None, result_record)
        logger.info(
            "CONTROL %s by %s (%s): %s",
            action_enum.value,
            operator_id,
            role_enum.value,
            result,
        )
        return result_record

    # -------------------------------------------------------------- handlers
    # Signature convention: async (operator_id: str, **typed params).

    async def _do_pause_trading(self, operator_id: str) -> dict[str, Any]:
        self.paused = True
        return {"paused": True}

    async def _do_resume_trading(self, operator_id: str) -> dict[str, Any]:
        self.paused = False
        return {"paused": False}

    async def _do_cancel_open_orders(self, operator_id: str) -> dict[str, Any]:
        cancelled: list[str] = []
        for client_id, order in list(self.order_manager.orders.items()):
            if not is_terminal(order.status):
                order.status = OrderStatus.CANCELLED
                order.updated_at = order.created_at
                cancelled.append(client_id)
        return {"cancelled": cancelled}

    async def _do_freeze_symbol(self, operator_id: str, symbol: str = "") -> dict[str, Any]:
        if not symbol:
            raise ValueError("symbol required")
        alert = DataAnomalyAlert(
            symbol=symbol,
            anomaly_type="STALE_DATA",
            severity="CRITICAL",
            detail=f"manual freeze by {operator_id}",
            freezes_symbol=True,
            is_simulated=False,
        )
        await self.strategy_agent.on_data_anomaly(alert)
        return {"frozen": symbol}

    async def _do_unfreeze_symbol(self, operator_id: str, symbol: str = "") -> dict[str, Any]:
        if not symbol:
            raise ValueError("symbol required")
        self.strategy_agent._frozen_symbols.discard(symbol)  # noqa: SLF001 - control plane
        return {"unfrozen": symbol}

    async def _do_set_max_position_pct(self, operator_id: str, pct: float = 0.0) -> dict[str, Any]:
        self._require_governor()
        if not 0 < pct <= 100:
            raise ValueError("pct must be in (0, 100]")
        self.governor.max_class_exposure_pct = float(pct)
        return {"max_class_exposure_pct": float(pct)}

    async def _do_set_halt_drawdown_pct(self, operator_id: str, pct: float = 0.0) -> dict[str, Any]:
        self._require_governor()
        if not 0 < pct <= 100:
            raise ValueError("pct must be in (0, 100]")
        self.governor.halt_dd_pct = float(pct)
        return {"halt_dd_pct": float(pct)}

    async def _do_trigger_kill_switch(self, operator_id: str) -> dict[str, Any]:
        if self.paper_engine is None or self._flatten is None:
            raise RuntimeError("kill-switch targets not wired")
        positions = self._positions_view()
        slip = 0.25 / 100.0
        for execution_id, view in list(positions.items()):
            base = self._price_lookup(view["symbol"])
            adverse = base * ((1 - slip) if view.get("action", "BUY") == "BUY" else (1 + slip))
            await self._flatten(execution_id, round(adverse, 4))
        await self.risk_governor.escalate(
            EmergencyStateValue.EMERGENCY_HALT,
            f"manual kill switch by {operator_id}",
            triggered_by=operator_id,
        )
        return {"flattened": len(positions), "state": self.risk_governor.state.value}

    async def _do_reset_lockout(self, operator_id: str, note: str = "") -> dict[str, Any]:
        event = await self.risk_governor.human_reset(operator_id, note)
        return {"new_state": event.new_state.value}

    async def _do_approve_live_capital(self, operator_id: str, note: str = "") -> dict[str, Any]:
        self.live_capital_approved_by = operator_id
        self.store.append_event(
            "LIVE_CAPITAL_APPROVAL", None, {"operator_id": operator_id, "note": note}
        )
        return {"live_capital_approved_by": operator_id}

    async def _do_promote_challenger(
        self, operator_id: str, trial_name: str = "", decision: str = "promote"
    ) -> dict[str, Any]:
        if self.challenge_registry is None:
            raise RuntimeError("challenge registry not wired")
        if not trial_name:
            raise ValueError("trial_name required")
        if decision == "promote":
            promoted: dict[str, Any] = self.challenge_registry.promote(trial_name, operator_id)
            return promoted
        rejected: dict[str, Any] = self.challenge_registry.reject(trial_name, operator_id)
        return rejected

    def _require_governor(self) -> None:
        if self.governor is None:
            raise RuntimeError("portfolio governor not wired into control plane")
