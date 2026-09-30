"""Cold-start recovery for the financial plane (V1-A.2 completion standard).

A restart must never silently assume that internal state equals broker state.
This module runs the boot sequence in a fixed order and refuses to permit
execution until every step that *can* be completed has been, and every step that
cannot be completed is reported as ``BLOCKED``/``NOT_PERFORMED`` rather than
skipped:

1. establish database connectivity and verify the schema/migrations,
2. return orphaned outbox claims to ``PENDING``,
3. connect the durable event backbone and reattach durable consumers,
4. load unresolved reconciliation findings,
5. query broker state (adapter supplied) and reconcile,
6. rebuild and verify the IBOR against the immutable fill ledger,
7. verify financial invariants,
8. evaluate the safety plane for active restrictions,
9. decide whether execution is permitted, and under which capital mode.

The gate is deliberately conservative: with no broker adapter wired, step 5
cannot be performed, so ``execution_permitted`` is ``False`` and the verdict says
so out loud. ``AUTONOMOUS_LIVE`` is never entered by this code path.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.financial_kernel import BaseFinancialStore, FindingStatus
from core.ibor import InvestmentBookOfRecord

logger = logging.getLogger(__name__)


class StepStatus(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    NOT_PERFORMED = "NOT_PERFORMED"


class CapitalMode(StrEnum):
    """Operating modes (master-spec §34). Ordered from most to least permissive."""

    DISABLED = "DISABLED"
    RESEARCH = "RESEARCH"
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    SUPERVISED_LIVE = "SUPERVISED_LIVE"
    AUTONOMOUS_LIVE = "AUTONOMOUS_LIVE"


#: Modes in which this recovery path may grant execution.
RECOVERY_GRANTABLE_MODES = frozenset(
    {
        CapitalMode.PAPER,
        CapitalMode.SHADOW,
        CapitalMode.SUPERVISED_LIVE,
        CapitalMode.BACKTEST,
        CapitalMode.RESEARCH,
    }
)


@dataclass
class RecoveryStep:
    name: str
    status: StepStatus
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (StepStatus.OK, StepStatus.DEGRADED)

    def as_dict(self) -> dict[str, Any]:
        return {"step": self.name, "status": str(self.status), "detail": self.detail}


@dataclass
class RecoveryReport:
    steps: list[RecoveryStep] = field(default_factory=list)
    capital_mode: CapitalMode = CapitalMode.DISABLED
    execution_permitted: bool = False
    blocking_reasons: list[str] = field(default_factory=list)
    outbox_claims_recovered: int = 0
    unresolved_findings: int = 0
    active_lockouts: int = 0
    ibor_rebuild_ok: bool = False
    invariants_ok: bool = False
    reconciliation_run_id: str | None = None
    reconciliation_ok: bool | None = None

    def step(self, name: str) -> RecoveryStep | None:
        return next((s for s in self.steps if s.name == name), None)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps) and not self.blocking_reasons

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "capital_mode": str(self.capital_mode),
            "execution_permitted": self.execution_permitted,
            "blocking_reasons": list(self.blocking_reasons),
            "steps": [s.as_dict() for s in self.steps],
            "outbox_claims_recovered": self.outbox_claims_recovered,
            "unresolved_findings": self.unresolved_findings,
            "active_lockouts": self.active_lockouts,
            "ibor_rebuild_ok": self.ibor_rebuild_ok,
            "invariants_ok": self.invariants_ok,
            "reconciliation_run_id": self.reconciliation_run_id,
            "reconciliation_ok": self.reconciliation_ok,
        }


class FinancialRecovery:
    """Runs the cold-start sequence against a financial store."""

    def __init__(
        self,
        store: BaseFinancialStore,
        *,
        account_id: str = "default",
        requested_mode: CapitalMode = CapitalMode.PAPER,
        broker_snapshot_provider: Callable[[], Any] | None = None,
        reconciliation_engine: Any = None,
        safety: Any = None,
        bus: Any = None,
        populate_consumers: Callable[[], int] | None = None,
    ) -> None:
        self.store = store
        self.account_id = account_id
        self.requested_mode = requested_mode
        self.broker_snapshot_provider = broker_snapshot_provider
        self.reconciliation_engine = reconciliation_engine
        self.safety = safety
        self.bus = bus
        self.populate_consumers = populate_consumers

    # ------------------------------------------------------------------- run

    def run(self) -> RecoveryReport:
        report = RecoveryReport()
        self._step_connectivity(report)
        self._step_claims(report)
        self._step_backbone(report)
        self._step_findings(report)
        self._step_broker(report)
        self._step_ibor(report)
        self._step_invariants(report)
        self._step_lockouts(report)
        self._decide(report)
        logger.info(
            "cold-start recovery: mode=%s permitted=%s blocked=%s",
            report.capital_mode,
            report.execution_permitted,
            report.blocking_reasons,
        )
        return report

    # ---------------------------------------------------------------- steps

    def _step_connectivity(self, report: RecoveryReport) -> None:
        health = self.store.health()
        if not health.get("reachable"):
            report.steps.append(
                RecoveryStep(
                    "database_connectivity",
                    StepStatus.BLOCKED,
                    f"financial store unreachable: {health.get('error')}",
                )
            )
            report.blocking_reasons.append("financial store unreachable")
            return
        schema = health.get("schema") or {}
        if not schema.get("up_to_date"):
            report.steps.append(
                RecoveryStep(
                    "schema_migrations",
                    StepStatus.BLOCKED,
                    f"schema at {schema.get('current')}, requires {schema.get('required')}",
                )
            )
            report.blocking_reasons.append("financial schema is not migrated")
            return
        report.steps.append(
            RecoveryStep(
                "database_connectivity",
                StepStatus.OK,
                f"{health.get('backend')} reachable, schema v{schema.get('current')}",
            )
        )

    def _step_claims(self, report: RecoveryReport) -> None:
        if report.blocking_reasons:
            report.steps.append(
                RecoveryStep("outbox_claim_recovery", StepStatus.NOT_PERFORMED, "store unusable")
            )
            return
        recovered = self.store.recover_claims_after_restart()
        report.outbox_claims_recovered = recovered
        report.steps.append(
            RecoveryStep(
                "outbox_claim_recovery",
                StepStatus.OK,
                f"{recovered} orphaned claim(s) returned to PENDING",
            )
        )

    def _step_backbone(self, report: RecoveryReport) -> None:
        if self.bus is None:
            report.steps.append(
                RecoveryStep(
                    "event_backbone",
                    StepStatus.DEGRADED,
                    "no durable backbone wired; outbox publication is paused "
                    "(committed state is intact)",
                )
            )
            return
        health = self.bus.health() if hasattr(self.bus, "health") else {"connected": None}
        if not health.get("connected"):
            # Not fatal: the outbox retains everything and publication resumes.
            report.steps.append(
                RecoveryStep(
                    "event_backbone",
                    StepStatus.DEGRADED,
                    f"backbone not connected ({health.get('url')}); publication will resume",
                )
            )
            return
        consumers = self.populate_consumers() if self.populate_consumers else 0
        report.steps.append(
            RecoveryStep(
                "event_backbone",
                StepStatus.OK,
                f"connected to {health.get('stream')}; {consumers} durable consumer(s) reattached",
            )
        )

    def _step_findings(self, report: RecoveryReport) -> None:
        try:
            open_findings = self.store.findings(FindingStatus.OPEN)
        except Exception as exc:  # noqa: BLE001 - surface, never assume clean
            report.steps.append(
                RecoveryStep("unresolved_findings", StepStatus.BLOCKED, f"unreadable: {exc}")
            )
            report.blocking_reasons.append("reconciliation findings unreadable")
            return
        report.unresolved_findings = len(open_findings)
        critical = [f for f in open_findings if str(f.severity) == "CRITICAL"]
        report.steps.append(
            RecoveryStep(
                "unresolved_findings",
                StepStatus.OK,
                f"{len(open_findings)} open finding(s), {len(critical)} critical",
            )
        )
        if critical:
            report.blocking_reasons.append(
                f"{len(critical)} unresolved CRITICAL reconciliation finding(s)"
            )

    def _step_broker(self, report: RecoveryReport) -> None:
        if self.broker_snapshot_provider is None or self.reconciliation_engine is None:
            report.steps.append(
                RecoveryStep(
                    "broker_reconciliation",
                    StepStatus.NOT_PERFORMED,
                    "no broker adapter wired; internal state has NOT been compared with "
                    "the venue, so execution stays blocked",
                )
            )
            report.blocking_reasons.append(
                "broker state was not reconciled at startup (no adapter wired)"
            )
            return
        try:
            snapshot = self.broker_snapshot_provider()
            result = self.reconciliation_engine.reconcile(snapshot)
        except Exception as exc:  # noqa: BLE001 - a failed reconciliation blocks
            report.steps.append(
                RecoveryStep("broker_reconciliation", StepStatus.BLOCKED, f"failed: {exc}")
            )
            report.blocking_reasons.append("startup reconciliation failed")
            return
        report.reconciliation_run_id = result.run.run_id
        report.reconciliation_ok = bool(result.ok)
        if not result.ok:
            report.blocking_reasons.append(
                f"startup reconciliation found {len(result.findings)} discrepancy(ies)"
            )
        report.steps.append(
            RecoveryStep(
                "broker_reconciliation",
                StepStatus.OK if result.ok else StepStatus.BLOCKED,
                f"run {result.run.run_id}: matched={result.run.matched_executions} "
                f"broker_only={result.run.broker_only_executions} "
                f"internal_only={result.run.internal_only_executions} "
                f"findings={len(result.findings)}",
            )
        )

    def _step_ibor(self, report: RecoveryReport) -> None:
        try:
            ibor = InvestmentBookOfRecord(self.store, account_id=self.account_id)
            rebuild = ibor.rebuild()
        except Exception as exc:  # noqa: BLE001 - an unprovable book blocks
            report.steps.append(RecoveryStep("ibor_rebuild", StepStatus.BLOCKED, f"failed: {exc}"))
            report.blocking_reasons.append("IBOR could not be rebuilt")
            return
        report.ibor_rebuild_ok = bool(rebuild.ok)
        if not rebuild.ok:
            report.blocking_reasons.append("IBOR rebuild disagreed with live positions")
        report.steps.append(
            RecoveryStep(
                "ibor_rebuild",
                StepStatus.OK if rebuild.ok else StepStatus.BLOCKED,
                f"checked={rebuild.checked_positions} skipped=0 ok={rebuild.ok}"
                + ("" if rebuild.ok else f" divergences={rebuild.divergences}"),
            )
        )

    def _step_invariants(self, report: RecoveryReport) -> None:
        try:
            invariants = self.store.verify_invariants()
        except Exception as exc:  # noqa: BLE001 - unknown invariants block
            report.steps.append(
                RecoveryStep("financial_invariants", StepStatus.BLOCKED, f"failed: {exc}")
            )
            report.blocking_reasons.append("financial invariants could not be verified")
            return
        report.invariants_ok = bool(invariants.ok)
        if not invariants.ok:
            names = [c.name for c in invariants.failures()]
            report.blocking_reasons.append(f"financial invariants violated: {names}")
        report.steps.append(
            RecoveryStep(
                "financial_invariants",
                StepStatus.OK if invariants.ok else StepStatus.BLOCKED,
                f"{len(invariants.checks)} check(s), failures={[c.name for c in invariants.failures()]}",
            )
        )

    def _step_lockouts(self, report: RecoveryReport) -> None:
        if self.safety is None:
            report.steps.append(
                RecoveryStep(
                    "safety_lockouts",
                    StepStatus.NOT_PERFORMED,
                    "no safety plane wired; existing restrictions were not evaluated",
                )
            )
            report.blocking_reasons.append("safety plane not wired")
            return
        state = self.safety.state()
        if not state.get("known"):
            report.steps.append(
                RecoveryStep(
                    "safety_lockouts", StepStatus.BLOCKED, f"unreadable: {state.get('error')}"
                )
            )
            report.blocking_reasons.append("safety state unreadable")
            return
        report.active_lockouts = int(state.get("active_count") or 0)
        decision = self.safety.is_blocked(account_id=self.account_id)
        if decision.blocked:
            report.blocking_reasons.append(
                "active safety lockout: " + "; ".join(decision.reasons)
            )
        report.steps.append(
            RecoveryStep(
                "safety_lockouts",
                StepStatus.OK if not decision.blocked else StepStatus.BLOCKED,
                f"{report.active_lockouts} active restriction(s)",
            )
        )

    # ---------------------------------------------------------------- verdict

    def _decide(self, report: RecoveryReport) -> None:
        requested = self.requested_mode
        if requested is CapitalMode.AUTONOMOUS_LIVE:
            # Never granted by a boot path, whatever the evidence says.
            report.steps.append(
                RecoveryStep(
                    "capital_mode",
                    StepStatus.BLOCKED,
                    "AUTONOMOUS_LIVE cannot be entered by startup recovery; it requires "
                    "the full evidence gate and an explicit administrative enablement",
                )
            )
            report.blocking_reasons.append("AUTONOMOUS_LIVE requested but not grantable here")
            report.capital_mode = CapitalMode.PAPER
            report.execution_permitted = False
            return

        permitted = not report.blocking_reasons and requested in RECOVERY_GRANTABLE_MODES
        report.capital_mode = requested if permitted else CapitalMode.PAPER
        report.execution_permitted = permitted
        if not permitted and not report.blocking_reasons:
            report.blocking_reasons.append(
                f"requested mode {requested} is not grantable by startup recovery"
            )
        report.steps.append(
            RecoveryStep(
                "capital_mode",
                StepStatus.OK if permitted else StepStatus.BLOCKED,
                f"requested={requested} granted={report.capital_mode} "
                f"permitted={permitted}",
            )
        )


def recover_financial_plane(
    store: BaseFinancialStore,
    *,
    account_id: str = "default",
    requested_mode: CapitalMode = CapitalMode.PAPER,
    **kwargs: Any,
) -> RecoveryReport:
    """Convenience entry point for the boot path and the CLI."""
    return FinancialRecovery(
        store, account_id=account_id, requested_mode=requested_mode, **kwargs
    ).run()


__all__ = [
    "CapitalMode",
    "FinancialRecovery",
    "RECOVERY_GRANTABLE_MODES",
    "RecoveryReport",
    "RecoveryStep",
    "StepStatus",
    "recover_financial_plane",
]
