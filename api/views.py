"""Read-only command-center views over live system state.

Pure functions returning JSON-able dicts - the contract any UI (web, TUI,
export) consumes. No framework, no I/O; the HTTP server is a thin shell.
"""

from typing import Any

from communities.c11_finance.audit_graph import decision_provenance
from core.persistence import BaseMemoryStore
from research.walkforward import calibration_report


class SystemSnapshotBuilder:
    """Assembles view payloads from stores and live components."""

    def __init__(
        self,
        store: BaseMemoryStore,
        ledger: Any = None,
        governor: Any = None,
        risk_governor: Any = None,
        paper_engine: Any = None,
        lot_book: Any = None,
    ) -> None:
        self.store = store
        self.ledger = ledger
        self.governor = governor
        self.risk_governor = risk_governor
        self.paper = paper_engine
        self.lot_book = lot_book

    # ------------------------------------------------------------- executive

    def executive(self) -> dict[str, Any]:
        counts = self.store.counts()
        pnl_rows = self.store.pnl_series()
        cumulative = round(sum(p for _, p in pnl_rows), 2)
        return {
            "cash_balance": getattr(self.paper, "cash_balance", None),
            "open_positions": len(getattr(self.paper, "open_positions", {}) or {}),
            "cumulative_realized_pnl": cumulative,
            "closed_trades": len(pnl_rows),
            "emergency_state": (
                self.risk_governor.state.value if self.risk_governor else "UNKNOWN"
            ),
            "drawdown_pct": self.governor.current_drawdown_pct() if self.governor else None,
            "chain_valid": self.store.verify_chain()[0],
            "events_logged": counts["event_log"],
            "predictions_scored": counts["predictions"],
            "postmortems": counts["postmortems"],
            "paused": None,
        }

    # ------------------------------------------------------------- decisions

    def executions(self, limit: int = 25) -> list[dict[str, Any]]:
        rows = self.store.pnl_series()[-limit:]
        out: list[dict[str, Any]] = []
        receipts: dict[str, dict[str, Any]] = {}
        for payload in self.store.iter_event_payloads("aios.c5.order_executed"):
            receipts[payload.get("execution_id", "")] = {
                "symbol": payload.get("symbol"),
                "fill_price": payload.get("fill_price"),
                "strategy_id": payload.get("strategy_id"),
            }
        for execution_id, pnl in reversed(rows):
            meta = receipts.get(execution_id, {})
            out.append(
                {
                    "execution_id": execution_id,
                    "symbol": meta.get("symbol"),
                    "fill_price": meta.get("fill_price"),
                    "realized_pnl": pnl,
                }
            )
        return out

    def decision_drilldown(self, execution_id: str) -> dict[str, Any]:
        walk = decision_provenance(self.store, execution_id)
        observation = walk.get("observation") or {}
        strategy = walk.get("strategy") or {}
        hypothesis = walk.get("hypothesis") or {}
        verification = walk.get("verification") or {}
        return {
            "execution_id": execution_id,
            "decision": {
                "action": strategy.get("action"),
                "symbol": strategy.get("symbol"),
                "family": strategy.get("family"),
                "position_size_pct": strategy.get("position_size_pct"),
            },
            "reason": {"thesis": hypothesis.get("thesis")},
            "evidence": {
                "supporting_arguments": hypothesis.get("supporting_arguments", []),
                "counter_arguments": hypothesis.get("counter_arguments", []),
            },
            "verification": {
                "confidence_score": verification.get("confidence_score"),
                "fact_score": verification.get("fact_score"),
                "balance_score": verification.get("balance_score"),
                "math_score": verification.get("math_score"),
                "flagged_hallucinations": verification.get("flagged_hallucinations", []),
            },
            "risk": {
                "stop_loss_price": strategy.get("stop_loss_price"),
                "take_profit_price": strategy.get("take_profit_price"),
            },
            "outcome": {
                "actual_pnl": observation.get("actual_pnl"),
                "exit_reason": observation.get("exit_reason"),
                "direction_correct": observation.get("direction_correct"),
                "lessons_learned": observation.get("lessons_learned", []),
            },
            "chain_complete": walk["chain_complete"],
        }

    # ------------------------------------------------------------------ risk

    def risk_state(self) -> dict[str, Any]:
        history = [
            {
                "new_state": e.new_state.value,
                "reason": e.reason,
                "triggered_by": e.triggered_by,
                "lockout_engaged": e.lockout_engaged,
            }
            for e in (self.risk_governor.history[-10:] if self.risk_governor else [])
        ]
        compliance = [
            p for p in reversed(self.store.iter_event_payloads("aios.c11.compliance_alert"))
        ][:10]
        emergencies = [p for p in reversed(self.store.iter_event_payloads("aios.risk.emergency"))][
            :10
        ]
        return {
            "current_state": self.risk_governor.state.value if self.risk_governor else None,
            "locked_out": self.risk_governor.locked_out if self.risk_governor else None,
            "drawdown_pct": self.governor.current_drawdown_pct() if self.governor else None,
            "halt_dd_pct": getattr(self.governor, "halt_dd_pct", None),
            "max_class_exposure_pct": getattr(self.governor, "max_class_exposure_pct", None),
            "class_exposures_pct": self.governor._class_exposures_public()
            if hasattr(self.governor, "_class_exposures_public")
            else {},
            "recent_transitions": history,
            "compliance_alerts": compliance,
            "emergency_events": emergencies,
        }

    # ------------------------------------------------------------ accounting

    def accounting(self) -> dict[str, Any]:
        balances = self.ledger.balances() if self.ledger else {}
        return {
            "trial_balance_total": sum(balances.values()) if balances is not None else None,
            "balanced": (sum(balances.values()) == 0) if balances is not None else None,
            "accounts_minor": balances,
            "open_lot_qty": {
                s: self.lot_book.open_qty(s) for s in sorted(getattr(self.lot_book, "_lots", {}))
            }
            if self.lot_book
            else {},
        }

    # -------------------------------------------------------------- research

    def research_quality(self) -> dict[str, Any]:
        from core.persistence import SqliteMemoryStore

        assert isinstance(self.store, SqliteMemoryStore), "calibration needs SQLite store"
        report = calibration_report(self.store._conn)  # noqa: SLF001 - same package family
        return report.model_dump()

    # ---------------------------------------------------------------- health

    def health(self) -> dict[str, Any]:
        ok, bad_seq = self.store.verify_chain()
        return {
            "audit_chain_valid": ok,
            "first_bad_seq": bad_seq,
            "counts": self.store.counts(),
            "components": {
                "ledger_wired": self.ledger is not None,
                "governor_wired": self.governor is not None,
                "risk_governor_wired": self.risk_governor is not None,
                "paper_engine_wired": self.paper is not None,
            },
        }


def prometheus_metrics(snapshot: dict[str, Any]) -> str:
    """Minimal Prometheus text exposition from an executive snapshot."""
    lines = [
        "# HELP aios_cash_balance Cash balance in major units",
        "# TYPE aios_cash_balance gauge",
        f"aios_cash_balance {snapshot.get('cash_balance') or 0}",
        "# HELP aios_open_positions Count of open positions",
        "# TYPE aios_open_positions gauge",
        f"aios_open_positions {snapshot.get('open_positions') or 0}",
        "# HELP aios_cumulative_pnl Cumulative realized PnL",
        "# TYPE aios_cumulative_pnl gauge",
        f"aios_cumulative_pnl {snapshot.get('cumulative_realized_pnl') or 0}",
        "# HELP aios_drawdown_pct Current drawdown percent",
        "# TYPE aios_drawdown_pct gauge",
        f"aios_drawdown_pct {snapshot.get('drawdown_pct') or 0}",
        "# HELP aios_events_logged Audit events logged",
        "# TYPE aios_events_logged counter",
        f"aios_events_logged {snapshot.get('events_logged') or 0}",
        "# HELP aios_audit_chain_valid 1 when hash chain verifies",
        "# TYPE aios_audit_chain_valid gauge",
        f"aios_audit_chain_valid {1 if snapshot.get('chain_valid') else 0}",
    ]
    state = str(snapshot.get("emergency_state", "UNKNOWN"))
    lines.append('aios_emergency_state{state="%s"} 1' % state)
    return "\n".join(lines) + "\n"
