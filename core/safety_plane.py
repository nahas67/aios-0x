"""Community-independent safety plane: deterministic execution restrictions (§33).

The safety plane is *not* an agent, cannot be reached by an agent, and does not
depend on the runtime being healthy. It owns one question answered from durable
state:

    may capital-changing work proceed for (account, broker, strategy)?

Two properties make it trustworthy:

1. **Engagement is deterministic.** A CRITICAL reconciliation finding maps to a
   scope through :data:`core.financial_kernel.LOCKOUT_SCOPE_BY_KIND`; nothing
   consults a model, a heuristic or an operator preference to decide that a
   mismatch should restrict trading.
2. **Release is human and role-gated.** Releasing re-uses the ONE authoritative
   RBAC matrix (``core.control_plane.ROLE_MATRIX``) and requires the
   ``RESET_LOCKOUT`` capability — held by RISK_ADMIN and ADMIN, never by an
   agent identity. A non-empty ``operator_id`` string proves nothing; the
   *role* is resolved server-side before this call and must be sufficient.

Every engagement and release is written to the audit log, and the restriction
itself lives in the financial store (``safety_lockouts``), so a process restart
cannot forget a restriction.
"""

from __future__ import annotations

import logging
from typing import Any

from core.control_plane import ROLE_MATRIX, ControlAction, OperatorRole
from core.financial_kernel import (
    BaseFinancialStore,
    LockoutScope,
    SafetyLockout,
)

logger = logging.getLogger(__name__)

#: The producer name recorded on deterministic (non-human) engagement.
DETERMINISTIC_ACTOR = "c5-reconciliation"

#: Subject used for a system-wide restriction.
GLOBAL_SUBJECT = "*"


class SafetyAuthorizationError(PermissionError):
    """A caller tried to release a restriction without the required authority."""


class LockoutDecision:
    """Answer to "may this work proceed?", with the reasons when it may not."""

    def __init__(self, blocked: bool, reasons: list[str], lockouts: list[SafetyLockout]) -> None:
        self.blocked = blocked
        self.reasons = reasons
        self.lockouts = lockouts

    def __bool__(self) -> bool:
        """Truthy when work is permitted (``if decision:`` reads naturally)."""
        return not self.blocked

    def as_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "reasons": list(self.reasons),
            "lockouts": [
                {
                    "lockout_id": lockout.lockout_id,
                    "scope": str(lockout.scope),
                    "subject": lockout.subject,
                    "reason": lockout.reason,
                    "engaged_at": lockout.engaged_at.isoformat(),
                }
                for lockout in self.lockouts
            ],
        }


class SafetyPlane:
    """Durable, RBAC-gated execution restrictions."""

    def __init__(
        self,
        store: BaseFinancialStore,
        audit: Any = None,
        *,
        account_id: str = "default",
        broker: str | None = None,
    ) -> None:
        self.store = store
        self.audit = audit
        self.account_id = account_id
        self.broker = broker

    # ------------------------------------------------------------- engagement

    def engage(
        self,
        *,
        scope: LockoutScope,
        subject: str,
        reason: str,
        finding_id: str | None = None,
        run_id: str | None = None,
        engaged_by: str = DETERMINISTIC_ACTOR,
    ) -> SafetyLockout:
        """Restrict a scope. Fail-closed: a store error is never swallowed."""
        if scope is LockoutScope.NONE:
            raise ValueError("scope NONE is not a restriction")
        lockout = SafetyLockout(
            scope=scope,
            subject=subject or GLOBAL_SUBJECT,
            reason=reason,
            finding_id=finding_id,
            run_id=run_id,
            engaged_by=engaged_by,
        )
        stored = self.store.engage_lockout(lockout)
        self._audit(
            "SAFETY_LOCKOUT_ENGAGED",
            {
                "lockout_id": stored.lockout_id,
                "scope": str(stored.scope),
                "subject": stored.subject,
                "reason": stored.reason,
                "finding_id": stored.finding_id,
                "run_id": stored.run_id,
                "engaged_by": stored.engaged_by,
            },
        )
        logger.warning(
            "safety plane: %s lockout on %s (%s)", stored.scope, stored.subject, stored.reason
        )
        return stored

    def engage_for_scope(
        self,
        scope: LockoutScope,
        *,
        account_id: str | None = None,
        broker: str | None = None,
        strategy_id: str | None = None,
        reason: str,
        finding_id: str | None = None,
        run_id: str | None = None,
    ) -> SafetyLockout:
        """Engage using the natural subject for the requested scope.

        A scope whose subject cannot be resolved degrades to GLOBAL rather than
        silently restricting nothing — an unresolvable restriction is exactly the
        case where broadening is the safe direction.
        """
        subject = GLOBAL_SUBJECT
        if scope is LockoutScope.ACCOUNT:
            subject = account_id or self.account_id or GLOBAL_SUBJECT
        elif scope is LockoutScope.BROKER:
            subject = broker or self.broker or GLOBAL_SUBJECT
        elif scope is LockoutScope.STRATEGY:
            subject = strategy_id or GLOBAL_SUBJECT
        if subject == GLOBAL_SUBJECT and scope is not LockoutScope.GLOBAL:
            logger.error(
                "safety plane: no subject for %s scope; broadening to GLOBAL", scope
            )
            scope = LockoutScope.GLOBAL
        return self.engage(
            scope=scope,
            subject=subject,
            reason=reason,
            finding_id=finding_id,
            run_id=run_id,
        )

    # ---------------------------------------------------------------- release

    def release(
        self,
        lockout_id: str,
        *,
        operator_id: str,
        role: str,
        note: str,
    ) -> SafetyLockout:
        """Release one restriction under server-resolved human authority.

        ``role`` must come from the authentication layer (never from a request
        body) and must hold ``RESET_LOCKOUT`` in :data:`ROLE_MATRIX`.
        """
        if not operator_id.strip():
            raise SafetyAuthorizationError("authenticated operator identity required")
        try:
            parsed = OperatorRole(str(role).strip().upper())
        except ValueError as exc:
            raise SafetyAuthorizationError(f"unknown role {role!r}") from exc
        if ControlAction.RESET_LOCKOUT not in ROLE_MATRIX.get(parsed, frozenset()):
            raise SafetyAuthorizationError(
                f"role {parsed.value} may not release a safety lockout"
            )
        released = self.store.release_lockout(lockout_id, operator_id, note)
        self._audit(
            "SAFETY_LOCKOUT_RELEASED",
            {
                "lockout_id": released.lockout_id,
                "scope": str(released.scope),
                "subject": released.subject,
                "operator_id": operator_id,
                "role": parsed.value,
                "note": note,
            },
        )
        logger.warning(
            "safety plane: %s lockout on %s released by %s (%s)",
            released.scope,
            released.subject,
            operator_id,
            parsed.value,
        )
        return released

    # ------------------------------------------------------------------ query

    def is_blocked(
        self,
        *,
        account_id: str | None = None,
        broker: str | None = None,
        strategy_id: str | None = None,
    ) -> LockoutDecision:
        """Whether the requested subject is currently restricted.

        Any store failure blocks: an unreadable safety state must never read as
        "no restriction".
        """
        account = account_id or self.account_id
        venue = broker or self.broker
        try:
            active = self.store.active_lockouts()
        except Exception as exc:  # noqa: BLE001 - fail closed by design
            logger.exception("safety plane: lockout read failed; failing closed")
            return LockoutDecision(True, [f"safety state unreadable: {exc}"], [])

        relevant: list[SafetyLockout] = []
        reasons: list[str] = []
        for lockout in active:
            scope, subject = lockout.scope, lockout.subject
            if scope is LockoutScope.GLOBAL:
                relevant.append(lockout)
            elif scope is LockoutScope.BROKER and venue is not None and subject == venue:
                relevant.append(lockout)
            elif scope is LockoutScope.ACCOUNT and subject == account:
                relevant.append(lockout)
            elif (
                scope is LockoutScope.STRATEGY
                and strategy_id is not None
                and subject == strategy_id
            ):
                relevant.append(lockout)
            else:
                continue
            reasons.append(f"{scope} {subject}: {lockout.reason}")
        return LockoutDecision(bool(relevant), reasons, relevant)

    def state(self) -> dict[str, Any]:
        """Operator-facing summary (never fabricates a healthy reading)."""
        try:
            active = self.store.active_lockouts()
        except Exception as exc:  # noqa: BLE001 - report the failure honestly
            return {
                "known": False,
                "error": str(exc),
                "active_count": None,
                "lockouts": [],
            }
        return {
            "known": True,
            "error": None,
            "active_count": len(active),
            "lockouts": [
                {
                    "lockout_id": lockout.lockout_id,
                    "scope": str(lockout.scope),
                    "subject": lockout.subject,
                    "reason": lockout.reason,
                    "finding_id": lockout.finding_id,
                    "run_id": lockout.run_id,
                    "engaged_by": lockout.engaged_by,
                    "engaged_at": lockout.engaged_at.isoformat(),
                }
                for lockout in active
            ],
        }

    # -------------------------------------------------------------- internals

    def _audit(self, kind: str, payload: dict[str, Any]) -> None:
        if self.audit is None:
            return
        try:
            self.audit.append_event(kind, None, payload)
        except Exception:  # noqa: BLE001 - auditing must not break the restriction
            logger.exception("safety plane: audit append failed for %s", kind)
