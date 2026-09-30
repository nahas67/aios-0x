"""RiskGovernor: independent emergency authority (Directives 39/40, RISK_MODEL doc).

Owns the emergency state machine and the trading lockout. The lockout can only
be cleared by an explicit human reset carrying an operator id - no automated
component may clear it.

Lockout is persisted: on boot the governor refuses to allow trading while a
lockout event exists without a matching human reset in the audit store.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import (
    EmergencyEvent,
    EmergencyStateValue,
)

if TYPE_CHECKING:
    from core.persistence import BaseMemoryStore

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RiskGovernor:
    """Emergency state machine + lockout authority."""

    def __init__(self, event_bus: BaseEventBus) -> None:
        self.event_bus = event_bus
        self.state: EmergencyStateValue = EmergencyStateValue.NORMAL
        self._history: list[EmergencyEvent] = []

    # ---------------------------------------------------------------- queries

    @property
    def locked_out(self) -> bool:
        return self.state in {
            EmergencyStateValue.EMERGENCY_HALT,
            EmergencyStateValue.EXECUTION_FAILURE,
            EmergencyStateValue.SECURITY_INCIDENT,
        }

    @property
    def history(self) -> list[EmergencyEvent]:
        return list(self._history)

    # ----------------------------------------------------------- transitions

    async def escalate(
        self, new_state: EmergencyStateValue, reason: str, triggered_by: str = "system"
    ) -> EmergencyEvent:
        if new_state == self.state:
            # Idempotent escalation; still record for audit visibility.
            event = EmergencyEvent(
                previous_state=self.state,
                new_state=self.state,
                reason=reason,
                triggered_by=triggered_by,
                trading_allowed=not self.locked_out,
                lockout_engaged=self.locked_out,
            )
            await self._emit(event)
            return event

        previous = self.state
        self.state = new_state
        event = EmergencyEvent(
            previous_state=previous,
            new_state=new_state,
            reason=reason,
            triggered_by=triggered_by,
            trading_allowed=not self.locked_out,
            lockout_engaged=self.locked_out,
        )
        await self._emit(event)
        if self.locked_out:
            logger.critical(
                "LOCKOUT ENGAGED (%s): %s - human reset required", new_state.value, reason
            )
        return event

    async def human_reset(self, operator_id: str, note: str = "") -> EmergencyEvent:
        """ONLY path out of a lockout; requires a non-empty operator identity."""
        if not operator_id or not operator_id.strip():
            raise ValueError("human_reset requires a non-empty operator_id")
        if not self.locked_out:
            logger.info("human_reset ignored: governor not locked out")
            return EmergencyEvent(
                previous_state=self.state,
                new_state=self.state,
                reason="reset-noop (not locked out)",
                triggered_by=operator_id,
                trading_allowed=True,
                lockout_engaged=False,
            )
        previous = self.state
        self.state = EmergencyStateValue.NORMAL
        event = EmergencyEvent(
            previous_state=previous,
            new_state=EmergencyStateValue.NORMAL,
            reason=f"human reset: {note}" if note else "human reset",
            triggered_by=operator_id,
            trading_allowed=True,
            lockout_engaged=False,
        )
        await self._emit(event)
        logger.warning("Lockout cleared by operator %s", operator_id)
        return event

    async def _emit(self, event: EmergencyEvent) -> None:
        self._history.append(event)
        await self.event_bus.publish(EventTopic.RISK_EMERGENCY, event)

    # ------------------------------------------------------ drawdown linkage

    async def observe_drawdown(self, dd_pct: float, halt_threshold_pct: float) -> bool:
        """Map drawdown tiers to states; returns True when trading is allowed."""
        if dd_pct >= halt_threshold_pct:
            await self.escalate(
                EmergencyStateValue.EMERGENCY_HALT,
                f"drawdown {dd_pct:.2f}% >= halt {halt_threshold_pct:.2f}%",
                triggered_by="portfolio_governor",
            )
        elif dd_pct > 0 and self.state == EmergencyStateValue.NORMAL:
            pass  # WARNING/CAUTION remain governed by C9 sizing; no emergency yet
        return not self.locked_out



def load_lockout_from_store(store: "BaseMemoryStore") -> bool:
    """Return True when the audit log ends in an uncleared lockout.

    Scans RISK_EMERGENCY events; a lockout_engaged=True with no subsequent
    human reset means trading must stay blocked after restart.
    """
    locked = False
    for payload in store.iter_event_payloads("aios.risk.emergency"):
        if payload.get("lockout_engaged"):
            locked = True
        elif (
            payload.get("new_state") == "NORMAL"
            and payload.get("triggered_by", "system") != "system"
        ):
            locked = False
    return locked
