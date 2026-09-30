"""Read-only command-center views over live system state.

Pure functions returning JSON-able dicts - the contract any UI (web, TUI,
export) consumes. No framework, no I/O; the HTTP server is a thin shell.
"""

import hashlib
import json
import os
from collections import defaultdict
from typing import Any

from communities.c11_finance.audit_graph import decision_provenance
from core.persistence import BaseMemoryStore
from research.walkforward import calibration_report


def _env_enabled(value: object) -> bool:
    """Interpret an opt-in environment flag without treating ``0`` as true."""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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
        settings: Any = None,
        control_plane: Any = None,
        order_manager: Any = None,
        regime_engine: Any = None,
        equity_curve: Any = None,
        benchmark_curve: Any = None,
        research_engine: Any = None,
        kernel_bridge: Any = None,
        ca_workflow: Any = None,
        financial_store: Any = None,
        ibor: Any = None,
        safety_plane: Any = None,
        reconciliation_engine: Any = None,
        event_bus: Any = None,
        consumer_lag_provider: Any = None,
    ) -> None:
        self.store = store
        self.ledger = ledger
        self.governor = governor
        self.risk_governor = risk_governor
        self.paper = paper_engine
        self.lot_book = lot_book
        self.settings = settings
        self.control_plane = control_plane
        self.order_manager = order_manager
        self.regime_engine = regime_engine
        self.equity_curve = equity_curve if equity_curve is not None else []
        self._benchmark_curve = benchmark_curve if benchmark_curve is not None else []
        self.research_engine = research_engine
        self.kernel_bridge = kernel_bridge
        self.ca_workflow = ca_workflow
        self.financial_store = financial_store
        self.ibor = ibor
        self.safety_plane = safety_plane
        self.reconciliation_engine = reconciliation_engine
        # Durable event backbone (JetStream) and a lag probe for its durable
        # consumers. Both are optional: the publishing process owns the consumer
        # names, so a serving process that cannot see them must say "unknown"
        # rather than report a reassuring zero.
        self.event_bus = event_bus
        self.consumer_lag_provider = consumer_lag_provider

    # ------------------------------------------------- durable financial kernel

    def _financial_unavailable(self, what: str) -> dict[str, Any]:
        """Honest absence: the durable kernel is not wired in this process (§75).

        Never fabricates an empty-but-plausible book, because "nothing is known"
        and "we hold nothing" are very different statements to an operator.
        """
        return {
            "available": False,
            "reason": f"durable financial kernel not wired: {what} unavailable",
        }

    def ibor_view(self) -> dict[str, Any]:
        """Canonical Investment Book of Record snapshot (§27)."""
        if self.ibor is None:
            return self._financial_unavailable("IBOR")
        try:
            snapshot = self.ibor.snapshot()
        except Exception as exc:  # noqa: BLE001 - report, never invent
            return {"available": False, "reason": f"IBOR snapshot failed: {exc}"}
        return {"available": True, **snapshot.model_dump(mode="json")}

    def financial_positions(self) -> dict[str, Any]:
        if self.financial_store is None:
            return self._financial_unavailable("positions")
        try:
            positions = self.financial_store.positions()
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": str(exc)}
        return {
            "available": True,
            "positions": [
                {
                    "account_id": p.account_id,
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_cost": p.avg_cost,
                    "realized_pnl": p.realized_pnl,
                    "fees_paid": p.fees_paid,
                    "updated_at": p.updated_at.isoformat(),
                }
                for p in positions
            ],
        }

    def financial_cash(self) -> dict[str, Any]:
        """Cash by account/currency: settled, reserved and therefore available."""
        if self.financial_store is None:
            return self._financial_unavailable("cash")
        try:
            postings = self.financial_store.cash_postings()
            reservations = self.financial_store.reservations()
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": str(exc)}
        # Balances are derived from the posting ledger, not from a mutable
        # "balance" column: the ledger is the authority (double-entry, §28).
        pairs = sorted({(p.account_id, p.currency) for p in postings})
        rows = [
            {
                "account_id": account_id,
                "currency": currency,
                "settled_minor": self.financial_store.cash_balance_minor(
                    account_id, currency
                ),
                "reserved_minor": self.financial_store.reserved_cash_minor(
                    account_id, currency
                ),
                "available_minor": self.financial_store.cash_balance_minor(
                    account_id, currency
                )
                - self.financial_store.reserved_cash_minor(account_id, currency),
            }
            for account_id, currency in pairs
        ]
        return {
            "available": True,
            "cash": rows,
            "reservations": [
                {
                    "reservation_id": r.reservation_id,
                    "account_id": r.account_id,
                    "currency": r.currency,
                    "amount_minor": r.amount_minor,
                    "reason": r.reason,
                    "order_id": r.order_id,
                    "active": r.released_at is None,
                    "created_at": r.created_at.isoformat(),
                }
                for r in reservations
            ],
        }

    def financial_orders(self, limit: int = 100) -> dict[str, Any]:
        if self.financial_store is None:
            return self._financial_unavailable("orders")
        try:
            orders = self.financial_store.orders()
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": str(exc)}
        return {
            "available": True,
            "orders": [
                {
                    "internal_order_id": o.internal_order_id,
                    "client_order_id": o.client_order_id,
                    "broker_order_id": o.broker_order_id,
                    "strategy_id": o.strategy_id,
                    "symbol": o.symbol,
                    "side": str(o.side),
                    "quantity": o.quantity,
                    "filled_quantity": o.filled_quantity,
                    "status": str(o.status),
                    "version": o.version,
                    "created_at": o.created_at.isoformat(),
                }
                for o in orders[-limit:]
            ],
        }

    def financial_order_detail(self, order_id: str) -> dict[str, Any]:
        """One order with its immutable transition history and fills."""
        if self.financial_store is None:
            return self._financial_unavailable("order")
        order = self.financial_store.order(order_id)
        if order is None:
            raise KeyError(order_id)
        transitions = self.financial_store.transitions(order_id)
        fills = self.financial_store.fills(order_id)
        return {
            "available": True,
            "order": {
                "internal_order_id": order.internal_order_id,
                "client_order_id": order.client_order_id,
                "broker_order_id": order.broker_order_id,
                "strategy_id": order.strategy_id,
                "symbol": order.symbol,
                "side": str(order.side),
                "quantity": order.quantity,
                "filled_quantity": order.filled_quantity,
                "status": str(order.status),
                "version": order.version,
            },
            "transitions": [
                {
                    "from_status": str(t.from_status),
                    "to_status": str(t.to_status),
                    "actor": t.actor,
                    "reason": t.reason,
                    "occurred_at": t.occurred_at.isoformat(),
                }
                for t in transitions
            ],
            "fills": [
                {
                    "fill_id": f.fill_id,
                    "broker_execution_id": f.broker_execution_id,
                    "quantity": f.quantity,
                    "price": f.price,
                    "fee": f.fee,
                    "currency": f.currency,
                    "executed_at": f.executed_at.isoformat(),
                }
                for f in fills
            ],
        }

    def financial_fills(self, limit: int = 100) -> dict[str, Any]:
        if self.financial_store is None:
            return self._financial_unavailable("fills")
        try:
            fills = self.financial_store.fills()
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": str(exc)}
        return {
            "available": True,
            "fills": [
                {
                    "fill_id": f.fill_id,
                    "order_id": f.order_id,
                    "broker_execution_id": f.broker_execution_id,
                    "account_id": f.account_id,
                    "symbol": f.symbol,
                    "side": str(f.side),
                    "quantity": f.quantity,
                    "price": f.price,
                    "fee": f.fee,
                    "strategy_id": f.strategy_id,
                    "executed_at": f.executed_at.isoformat(),
                }
                for f in fills[-limit:]
            ],
        }

    def financial_invariants(self) -> dict[str, Any]:
        """Run the invariant suite live; a failure is reported, never hidden."""
        if self.financial_store is None:
            return self._financial_unavailable("invariants")
        try:
            report = self.financial_store.verify_invariants()
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": f"invariant verification failed: {exc}"}
        return {
            "available": True,
            "ok": report.ok,
            "checked": len(report.checks),
            "failures": [
                {"name": c.name, "detail": c.detail} for c in report.failures()
            ],
        }

    def financial_health(self) -> dict[str, Any]:
        """Store identity, schema state, outbox backlog and dead letters."""
        if self.financial_store is None:
            return self._financial_unavailable("health")
        try:
            health = self.financial_store.health()
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": str(exc)}
        payload: dict[str, Any] = {"available": True, **health}
        if self.safety_plane is not None:
            payload["safety"] = self.safety_plane.state()
        return payload

    def event_backbone_view(self) -> dict[str, Any]:
        """Durable event backbone health and consumer lag (§29).

        Absence is reported as absence. A process that owns no JetStream
        connection, or that cannot see the publishing consumer's durable name,
        returns ``wired: False`` / ``consumer_lag: None`` — an operator deciding
        whether the platform is keeping up must not be shown a fabricated zero.
        """
        if self.event_bus is None:
            return {
                "wired": False,
                "reason": "no durable event backbone is wired into this process",
                "consumer_lag": None,
            }
        health: dict[str, Any] = {}
        health_fn = getattr(self.event_bus, "health", None)
        if callable(health_fn):
            try:
                health = dict(health_fn())
            except Exception as exc:  # noqa: BLE001 - report, never invent
                return {
                    "wired": True,
                    "reachable": False,
                    "error": str(exc),
                    "consumer_lag": None,
                }
        lag: int | None = None
        if self.consumer_lag_provider is not None:
            try:
                lag = self.consumer_lag_provider()
            except Exception:  # noqa: BLE001 - unknown lag stays unknown
                lag = None
        return {"wired": True, **health, "consumer_lag": lag}

    def financial_outbox(self, limit: int = 50) -> dict[str, Any]:
        """Event delivery state: backlog, dead letters, recent publications."""
        if self.financial_store is None:
            return self._financial_unavailable("outbox")
        try:
            backlog = self.financial_store.outbox_backlog()
            dead = self.financial_store.dead_letters()
            pending = self.financial_store.outbox_pending(limit=limit)
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": str(exc)}
        return {
            "available": True,
            "backlog": backlog,
            "dead_letter_count": len(dead),
            "dead_letters": [
                {
                    "event_id": e.event_id,
                    "event_type": str(e.event_type),
                    "attempts": e.attempts,
                    "last_error": e.last_error,
                }
                for e in dead
            ],
            "pending": [
                {
                    "event_id": e.event_id,
                    "event_type": str(e.event_type),
                    "status": str(e.status),
                    "attempts": e.attempts,
                    "claimed_by": e.claimed_by,
                }
                for e in pending
            ],
            "event_backbone": self.event_backbone_view(),
        }

    def financial_reconciliation(self, limit: int = 20) -> dict[str, Any]:
        """Broker truth vs internal truth, with findings and resolution state."""
        if self.financial_store is None:
            return self._financial_unavailable("reconciliation")
        try:
            from core.financial_kernel import FindingStatus

            runs = self.financial_store.reconciliation_runs(limit=limit)
            open_findings = self.financial_store.findings(FindingStatus.OPEN)
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": str(exc)}
        latest = runs[0] if runs else None
        return {
            "available": True,
            "last_run": (
                {
                    "run_id": latest.run_id,
                    "mode": str(latest.mode),
                    "broker": latest.broker,
                    "adapter_version": latest.adapter_version,
                    "window_start": (
                        latest.window_start.isoformat() if latest.window_start else None
                    ),
                    "window_end": (
                        latest.window_end.isoformat() if latest.window_end else None
                    ),
                    "cursor_token": latest.cursor_token,
                    "queried_at": (
                        latest.queried_at.isoformat() if latest.queried_at else None
                    ),
                    "started_at": latest.started_at.isoformat(),
                    "finished_at": (
                        latest.finished_at.isoformat() if latest.finished_at else None
                    ),
                    "matched_executions": latest.matched_executions,
                    "broker_only_executions": latest.broker_only_executions,
                    "internal_only_executions": latest.internal_only_executions,
                    "finding_count": latest.finding_count,
                    "ok": bool(latest.ok),
                    "lockout_scope": str(latest.lockout_scope),
                }
                if latest is not None
                else None
            ),
            "runs": [
                {
                    "run_id": r.run_id,
                    "mode": str(r.mode),
                    "started_at": r.started_at.isoformat(),
                    "matched_executions": r.matched_executions,
                    "finding_count": r.finding_count,
                    "ok": bool(r.ok),
                    "lockout_scope": str(r.lockout_scope),
                }
                for r in runs
            ],
            "open_findings": [
                {
                    "finding_id": f.finding_id,
                    "run_id": f.run_id,
                    "kind": str(f.kind),
                    "severity": str(f.severity),
                    "subject": f.subject,
                    "detail": f.detail,
                    "internal_value": f.internal_value,
                    "broker_value": f.broker_value,
                    "status": str(f.status),
                    "scope": str(f.scope),
                    "created_at": f.created_at.isoformat(),
                }
                for f in open_findings
            ],
            "lockouts": (
                self.safety_plane.state() if self.safety_plane is not None else None
            ),
        }

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
        receipts: dict[str, dict[str, Any]] = {}
        for payload in self.store.iter_event_payloads("aios.c5.order_executed"):
            receipts[payload.get("execution_id", "")] = {
                "symbol": payload.get("symbol"),
                "fill_price": payload.get("fill_price"),
                "strategy_id": payload.get("strategy_id"),
            }
        strategies: dict[str, dict[str, Any]] = {}
        for payload in self.store.iter_event_payloads("aios.c4.strategy_generated"):
            strategies[payload.get("strategy_id", "")] = {
                "action": payload.get("action"),
                "confidence": None,
            }
        verifications: dict[str, float] = {}
        for payload in self.store.iter_event_payloads("aios.c3.verification_completed"):
            verifications[payload.get("hypothesis_id", "")] = float(
                payload.get("confidence_score") or 0
            )
        observations: dict[str, dict[str, Any]] = {}
        for payload in self.store.iter_event_payloads("aios.c6.observation_completed"):
            observations[payload.get("execution_id", "")] = {
                "exit_reason": payload.get("exit_reason"),
                "direction_correct": payload.get("direction_correct"),
            }
        hypotheses_by_strategy: dict[str, str] = {}
        for payload in self.store.iter_event_payloads("aios.c4.strategy_generated"):
            hypotheses_by_strategy[payload.get("strategy_id", "")] = payload.get(
                "hypothesis_id", ""
            )

        out: list[dict[str, Any]] = []
        for execution_id, pnl in reversed(rows):
            meta = receipts.get(execution_id, {})
            sid = meta.get("strategy_id", "")
            hyp_id = hypotheses_by_strategy.get(sid, "")
            obs = observations.get(execution_id, {})
            out.append(
                {
                    "execution_id": execution_id,
                    "symbol": meta.get("symbol"),
                    "fill_price": meta.get("fill_price"),
                    "realized_pnl": pnl,
                    "action": (strategies.get(sid) or {}).get("action"),
                    "confidence_pct": verifications.get(hyp_id),
                    "exit_reason": obs.get("exit_reason"),
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
        tax_events = self.store.iter_event_payloads("TAX_COMPUTATION")
        latest_tax = tax_events[-1] if tax_events else None
        review_items = [p for p in reversed(self.store.iter_event_payloads("REVIEW_ITEM"))][:5]
        return {
            "trial_balance_total": sum(balances.values()) if balances is not None else None,
            "balanced": (sum(balances.values()) == 0) if balances is not None else None,
            "accounts_minor": balances,
            "open_lot_qty": {
                s: self.lot_book.open_qty(s) for s in sorted(getattr(self.lot_book, "_lots", {}))
            }
            if self.lot_book
            else {},
            "tax": {
                "rule_citation": (latest_tax or {}).get("rule_citation"),
                "jurisdiction": (latest_tax or {}).get("jurisdiction"),
                "taxable_gain_minor": (latest_tax or {}).get("taxable_gain_minor"),
                "tax_due_minor": (latest_tax or {}).get("tax_due_minor"),
                "requires_signoff": (latest_tax or {}).get("requires_professional_signoff", True),
                "ca_state": (review_items[0] or {}).get("state") if review_items else None,
            },
            "ca_review_queue": [
                {"subject_ref": r.get("subject_ref"), "state": r.get("state")} for r in review_items
            ],
        }

    # -------------------------------------------------------------- research

    def research_quality(self) -> dict[str, Any]:
        from core.persistence import SqliteMemoryStore

        assert isinstance(self.store, SqliteMemoryStore), "calibration needs SQLite store"
        report = calibration_report(self.store._conn)  # noqa: SLF001 - same package family
        # mode="json" converts datetimes to ISO strings — raw datetime objects
        # crash the HTTP JSON encoder (pre-existing 500 on /api/v1/research).
        return report.model_dump(mode="json")

    # -------------------------------------------------------------- settings

    def settings_view(self) -> dict[str, Any]:
        """Effective configuration for the Settings Center. Secrets masked."""
        s = self.settings

        def configured(value: Any) -> bool:
            return bool(value)

        live_requested = _env_enabled(os.environ.get("AIOS_ALLOW_LIVE_EXECUTION"))
        execution_environment = (
            "SHADOW"
            if bool(getattr(self.paper, "shadow_mode", False))
            else "PAPER"
        )
        approval_recorded = bool(
            self.control_plane is not None
            and getattr(self.control_plane, "live_capital_approved_by", None)
        )
        view: dict[str, Any] = {
            "system": {
                "model_provider": getattr(s, "model_provider", "none"),
                "research_mode": getattr(s, "research_mode", "deterministic"),
                "llm_configured": bool(
                    getattr(s, "openai_api_key", None) or getattr(s, "anthropic_api_key", None)
                ),
                "shadow_mode": getattr(
                    getattr(self.paper, "shadow_mode", False), "__bool__", lambda: False
                )(),
            },
            "ai": {
                "research_model_cheap": getattr(s, "research_model_cheap", None),
                "research_model_reasoning": getattr(s, "research_model_reasoning", None),
                "verification_model": getattr(s, "verification_model", None),
                "llm_temperature": getattr(s, "llm_temperature", None),
            },
            "data": {
                "finnhub": configured(getattr(s, "finnhub_api_key", None)),
                "gnews": configured(getattr(s, "gnews_api_key", None)),
                "newsdata": configured(getattr(s, "newsdata_api_key", None)),
                "marketstack": configured(getattr(s, "marketstack_api_key", None)),
                "fred": configured(getattr(s, "fred_api_key", None)),
            },
            "risk": {
                "max_class_exposure_pct": getattr(self.governor, "max_class_exposure_pct", None)
                if self.governor
                else None,
                "halt_dd_pct": getattr(self.governor, "halt_dd_pct", None)
                if self.governor
                else None,
                "warning_dd_pct": getattr(self.governor, "warning_dd_pct", None)
                if self.governor
                else None,
                "caution_dd_pct": getattr(self.governor, "caution_dd_pct", None)
                if self.governor
                else None,
            },
            "execution_rails": {
                "environment": execution_environment,
                "paper_capability": self.paper is not None,
                "testnet_capability": False,
                "live_adapter_available": False,
                "live_execution_allowed_env": live_requested,
                "live_routing_enabled": False,
                "live_capital_approval_recorded": approval_recorded,
                "constitution_live_routing": False,
                "micro_live_cap_usd": 100.0,
                "constitution_pinned": True,
            },
            "autonomy": (self.control_plane.autonomy.value if self.control_plane else None),
            "pending_approvals": len(getattr(self.control_plane, "pending_approvals", {}) or {}),
        }
        return view

    def approvals_view(self) -> list[dict[str, Any]]:
        pending = getattr(self.control_plane, "pending_approvals", {}) or {}
        out = []
        for plan_id, dump in pending.items():
            strategy = dump.get("strategy", {})
            out.append(
                {
                    "plan_id": plan_id,
                    "symbol": strategy.get("symbol"),
                    "action": strategy.get("action"),
                    "entry_price": strategy.get("entry_price"),
                    "position_size_pct": dump.get("final_position_size_pct"),
                    "status": "PENDING_APPROVAL",
                }
            )
        return out

    # ------------------------------------------------- workspace: portfolio

    def portfolio(self) -> dict[str, Any]:
        cash = getattr(self.paper, "cash_balance", None) if self.paper else None
        positions = self.positions()
        exposure_by_class: dict[str, float] = {}
        notional_open = 0.0
        for p in positions:
            notional_open += float(p.get("mark_value") or 0.0)
            cls = p.get("asset_class") or "OTHER"
            exposure_by_class[cls] = exposure_by_class.get(cls, 0.0) + float(
                p.get("mark_value") or 0.0
            )
        nav = round((cash or 0.0) + notional_open, 2)
        total = nav or 1.0
        allocation = {k: round(v / total * 100.0, 2) for k, v in exposure_by_class.items()}
        return {
            "nav": nav,
            "cash": cash,
            "open_notional": round(notional_open, 2),
            "exposure_pct": round(notional_open / total * 100.0, 2),
            "allocation_pct": allocation,
            "closed_trades": len(self.store.pnl_series()),
            "realized_pnl": round(sum(p for _, p in self.store.pnl_series()), 2),
        }

    def positions(self) -> list[dict[str, Any]]:
        engine = self.paper
        if engine is None:
            return []
        out: list[dict[str, Any]] = []
        class_map = getattr(getattr(self.control_plane, "governor", None), "_classes", {})
        for eid, pos in engine.open_positions.items():
            r = pos.receipt
            mark = r.fill_price
            try:
                if self.order_manager is not None and hasattr(self.order_manager, "adapter"):
                    pass
            except Exception:  # noqa: BLE001
                pass
            # mark via last close when a regime/price source is reachable
            if self.regime_engine is not None:
                closes = getattr(self.regime_engine, "_closes", {}).get(r.symbol)
                if closes:
                    mark = float(list(closes)[-1])
            direction = 1 if pos.action == "BUY" else -1
            unrealized = round(direction * (mark - r.fill_price) * r.filled_quantity, 2)
            out.append(
                {
                    "execution_id": eid,
                    "symbol": r.symbol,
                    "action": pos.action,
                    "qty": r.filled_quantity,
                    "entry": r.fill_price,
                    "mark": mark,
                    "unrealized": unrealized,
                    "stop": pos.stop_loss_price,
                    "target": pos.take_profit_price,
                    "mark_value": round(mark * r.filled_quantity, 2),
                    "asset_class": class_map.get(r.symbol, "OTHER"),
                }
            )
        return out

    def orders(self, limit: int = 50) -> list[dict[str, Any]]:
        if self.order_manager is None:
            return []
        out = []
        for order in list(self.order_manager.orders.values())[-limit:]:
            out.append(
                {
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                    "side": order.side.value if hasattr(order.side, "value") else order.side,
                    "status": order.status.value
                    if hasattr(order.status, "value")
                    else order.status,
                    "quantity": order.quantity,
                    "avg_fill_price": order.avg_fill_price,
                    "reject_reason": order.reject_reason,
                    "created_at": order.created_at.isoformat(),
                }
            )
        return list(reversed(out))

    # ------------------------------------------------ workspace: intelligence

    def agents(self) -> list[dict[str, Any]]:
        from core.agents import registered_agents
        from core.reputation import compute_reputations

        roster = registered_agents(self.store)
        reps = compute_reputations(self.store).get("families", {})
        out = []
        for agent_id, info in sorted(roster.items()):
            out.append(
                {
                    "agent_id": agent_id,
                    "community": info.get("community"),
                    "role": info.get("role"),
                    "version": info.get("version"),
                    "publishes": info.get("publishes", []),
                    "reputation": reps.get(agent_id),
                }
            )
        return out

    def opportunities(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.store.iter_event_payloads("aios.c4.opportunity_ranked")[-limit:]
        out = []
        for p in reversed(rows):
            out.append(
                {
                    "strategy_id": p.get("strategy_id"),
                    "symbol": p.get("symbol"),
                    "family": p.get("family"),
                    "edge_proxy": p.get("edge_proxy"),
                    "expected_rr": p.get("expected_rr"),
                    "alpha_decay": p.get("alpha_decay_multiplier"),
                    "composite_rank": p.get("composite_rank"),
                }
            )
        return out

    def events(self, limit: int = 30) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        sources = {
            "aios.c10.expectation_updated": "MACRO",
            "aios.c10.scenarios_published": "SCENARIO",
            "aios.c10.regime_changed": "REGIME",
            "aios.c11.compliance_alert": "COMPLIANCE",
            "aios.risk.emergency": "EMERGENCY",
            "aios.c1.data_anomaly": "DATA",
        }
        for kind, label in sources.items():
            for p in self.store.iter_event_payloads(kind)[-limit:]:
                merged.append(
                    {
                        "kind": kind,
                        "label": label,
                        "ts": p.get("created_at") or p.get("assessed_at"),
                        "title": p.get("title")
                        or p.get("detail")
                        or p.get("reason")
                        or p.get("anomaly_type")
                        or kind,
                        "symbol": p.get("symbol"),
                        "severity": p.get("severity")
                        or ("CRITICAL" if p.get("lockout_engaged") else "INFO"),
                        "payload": p,
                    }
                )
        merged.sort(key=lambda x: x.get("ts") or "", reverse=True)
        return merged[:limit]

    def regimes(self) -> list[dict[str, Any]]:
        engine = self.regime_engine
        if engine is None:
            return []
        out = []
        current = getattr(engine, "_current", {})
        for symbol, state in sorted(current.items()):
            out.append(
                {
                    "symbol": symbol,
                    "trend": state.trend.value if hasattr(state.trend, "value") else state.trend,
                    "vol_regime": (
                        state.vol_regime.value
                        if hasattr(state.vol_regime, "value")
                        else state.vol_regime
                    ),
                    "realized_vol_pct": state.realized_vol_pct,
                    "window_bars": state.window_bars,
                }
            )
        return out

    def audit(self, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        q = (query or "").lower()
        out: list[dict[str, Any]] = []
        for row in reversed(self._audit_rows()):
            kind = row["kind"]
            payload_text = row["payload_json"].lower()
            if q and q not in kind.lower() and q not in payload_text:
                continue
            out.append(
                {
                    "seq": row["seq"],
                    "ts": row["ts"],
                    "kind": kind,
                    "ref_id": row["ref_id"],
                    "payload": json.loads(row["payload_json"]),
                }
            )
            if len(out) >= limit:
                break
        return out

    def _audit_rows(self) -> list[Any]:
        from core.persistence import SqliteMemoryStore

        assert isinstance(self.store, SqliteMemoryStore)
        with self.store._lock:  # noqa: SLF001 - same-package read
            rows = self.store._conn.execute(
                "SELECT seq, ts, kind, ref_id, payload_json FROM event_log "
                "ORDER BY seq DESC LIMIT 500"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------- research plane (Phase C/D)

    def knowledge(self) -> dict[str, Any]:
        """Durable hypothesis knowledge: status counts + recent hypotheses."""
        engine = self.research_engine
        if engine is None:
            return {"available": False}
        summary = engine.knowledge_summary()
        recent = []
        for h in engine.store.list_hypotheses(limit=60):
            relationships: dict[str, int] = defaultdict(int)
            try:
                pairs = engine.store.evidence_for_hypothesis(h.hypothesis_id)
            except Exception:  # noqa: BLE001 - view must not crash the API
                pairs = []
            for _, rel in pairs:
                relationships[rel] += 1
            recent.append(
                {
                    "hypothesis_id": h.hypothesis_id,
                    "statement": h.statement[:160],
                    "symbol": h.symbol,
                    "status": h.status.value,
                    "confidence": h.confidence,
                    "evidence_total": len(pairs),
                    "supports": relationships.get("supports", 0),
                    "contradicts": relationships.get("contradicts", 0),
                    "outcomes": relationships.get("outcome", 0),
                    "last_updated": h.last_updated.isoformat(),
                }
            )
        return {"available": True, **summary, "recent": recent}

    def hypothesis_detail(self, hypothesis_id: str) -> dict[str, Any]:
        """Full hypothesis record with its evidence graph."""
        engine = self.research_engine
        if engine is None:
            raise KeyError("research plane unavailable")
        h = engine.get(hypothesis_id)
        evidence = []
        for ev, relationship in engine.store.evidence_for_hypothesis(hypothesis_id):
            evidence.append(
                {
                    "evidence_id": ev.evidence_id,
                    "source": ev.source,
                    "relationship": relationship,
                    "confidence": ev.confidence,
                    "claims": ev.claims,
                    "counter_claims": ev.counter_claims,
                    "content_hash": ev.content_hash(),
                    "retrieval_time": ev.retrieval_time.isoformat(),
                }
            )
        return {
            "hypothesis_id": h.hypothesis_id,
            "statement": h.statement,
            "rationale": h.rationale,
            "expected_outcome": h.expected_outcome,
            "assumptions": h.assumptions,
            "symbol": h.symbol,
            "timeframe": h.timeframe,
            "expected_risk_reward_ratio": h.expected_risk_reward_ratio,
            "status": h.status.value,
            "confidence": h.confidence,
            "parent_hypotheses": h.parent_hypotheses,
            "dataset_ref": h.dataset_ref,
            "first_seen": h.first_seen.isoformat(),
            "last_updated": h.last_updated.isoformat(),
            "evidence": evidence,
        }

    def platform_feed(self, limit: int = 100) -> list[dict[str, Any]]:
        """Recent typed platform events across all kinds, newest first."""
        from core.platform_events import PlatformEventType

        rows: list[dict[str, Any]] = []
        for event_type in PlatformEventType:
            for payload in self.store.iter_event_payloads(event_type.value):
                payload["kind"] = event_type.value
                rows.append(payload)
        rows.sort(key=lambda p: str(p.get("occurred_at", "")), reverse=True)
        return rows[:limit]

    def models_view(self) -> dict[str, Any]:
        """Model registry contents (§12 lifecycle states + evaluation metrics)."""
        bridge = self.kernel_bridge
        if bridge is None or getattr(bridge, "kernel", None) is None:
            return {"available": False, "models": []}
        registry = bridge.kernel.models
        versions = registry.list_versions() if hasattr(registry, "list_versions") else []
        trained_events = self.store.iter_event_payloads("MODEL_TRAINED")
        by_ref = {e.get("artifact_hash"): e for e in trained_events}
        for mv in versions:
            extra = by_ref.get(mv.get("artifact_hash"))
            if extra:
                mv["walk_forward"] = extra.get("metrics", {})
                mv["per_symbol"] = extra.get("per_symbol_walk_forward", {})
        return {"available": True, "models": versions}

    def evaluations_view(self, limit: int = 50) -> list[dict[str, Any]]:
        """Recent formal EvaluationRecords (§14): PASS/FAIL/INCONCLUSIVE."""
        rows = self.store.iter_event_payloads("EVALUATION_RECORD")
        return list(reversed(rows))[:limit]

    def audit_verify(self) -> dict[str, Any]:
        """Walk the hash chain and report integrity with real counts.

        Replaces any client-side "N blocks intact" theatre: every number here
        is recomputed from the ``event_log`` table on each call.
        """
        from core.persistence import SqliteMemoryStore

        if not isinstance(self.store, SqliteMemoryStore):
            ok, bad_seq = self.store.verify_chain()
            try:
                blocks = int(self.store.counts().get("event_log", 0))
            except Exception:  # noqa: BLE001 - view must not crash the API
                blocks = 0
            return {
                "valid": ok,
                "blocks_checked": blocks,
                "head_hash": "",
                "breaks": [{"seq": bad_seq, "reason": "chain break"}]
                if bad_seq is not None
                else [],
            }
        with self.store._lock:  # noqa: SLF001 - same-package read
            rows = self.store._conn.execute(
                "SELECT seq, ts, kind, ref_id, payload_json, prev_hash, hash "
                "FROM event_log ORDER BY seq ASC"
            ).fetchall()
        expected_prev = "0" * 64
        head_hash = "0" * 64
        breaks: list[dict[str, Any]] = []
        for row in rows:
            recomputed = hashlib.sha256(
                f"{row['ts']}|{row['kind']}|{row['ref_id']}|"
                f"{row['payload_json']}|{row['prev_hash']}".encode()
            ).hexdigest()
            reasons: list[str] = []
            if row["prev_hash"] != expected_prev:
                reasons.append("prev_hash mismatch")
            if row["hash"] != recomputed:
                reasons.append("hash mismatch")
            if reasons:
                breaks.append({"seq": int(row["seq"]), "reason": "; ".join(reasons)})
            # Continue from the stored hash so one break does not cascade
            # into false positives on every later block.
            expected_prev = row["hash"]
            head_hash = row["hash"]
        return {
            "valid": not breaks,
            "blocks_checked": len(rows),
            "head_hash": head_hash,
            "breaks": breaks,
        }

    def models_registry_view(self) -> dict[str, Any]:
        """Model governance list reshaped from ``ModelRegistry.list_versions()``.

        Matches the ``/models`` honest-absence convention: no registry means
        ``{available: False, models: []}``, never a fabricated roster.
        """
        bridge = self.kernel_bridge
        if bridge is None or getattr(bridge, "kernel", None) is None:
            return {"available": False, "models": []}
        registry = getattr(bridge.kernel, "models", None)
        if registry is None or not hasattr(registry, "list_versions"):
            return {"available": False, "models": []}
        try:
            versions = registry.list_versions()
        except Exception as exc:  # noqa: BLE001 - report, never invent
            return {"available": False, "models": [], "reason": str(exc)}
        models: list[dict[str, Any]] = []
        for mv in versions:
            model_id = str(mv.get("model_id", ""))
            version = str(mv.get("version", ""))
            models.append(
                {
                    "id": f"{model_id}@{version}" if model_id else version,
                    "name": model_id,
                    "version": version,
                    "status": mv.get("status"),
                    "model_type": mv.get("model_type"),
                    "artifact_hash": mv.get("artifact_hash", ""),
                    "evaluation_metrics": mv.get("evaluation_metrics", {}),
                    "feature_ref": mv.get("feature_ref", {}),
                    "created_at": mv.get("created_at"),
                }
            )
        return {"available": True, "models": models}

    def instruments_view(self) -> dict[str, Any]:
        """Tradeable symbols from live sources — regimes, positions, orders.

        No hardcoded symbol list: when no source is wired the honest answer
        is an empty list, matching the ``/regimes`` convention.
        """
        class_map: dict[str, str] = {}
        governor = self.governor or getattr(self.control_plane, "governor", None)
        raw_classes = getattr(governor, "_classes", None)
        if isinstance(raw_classes, dict):
            class_map = {str(k): str(v) for k, v in raw_classes.items()}
        symbols: dict[str, dict[str, Any]] = {}

        def _add(symbol: object) -> None:
            if not isinstance(symbol, str) or not symbol or symbol in symbols:
                return
            symbols[symbol] = {
                "symbol": symbol,
                "name": symbol,
                "category": class_map.get(symbol, "UNKNOWN"),
            }

        for row in self.regimes():
            _add(row.get("symbol"))
        for position in self.positions():
            _add(position.get("symbol"))
        for order in self.orders():
            _add(order.get("symbol"))
        return {"instruments": sorted(symbols.values(), key=lambda r: str(r["symbol"]))}

    # ------------------------------------------------------------- human gates

    def gates_view(self) -> dict[str, Any]:
        """Constitution §5 human-held production gates, live status.

        The user controls these; this view makes visible WHAT blocks WHAT.
        """
        import os

        ca_approved = False
        if self.ca_workflow is not None:
            try:
                items = self.ca_workflow.items
                # ``state`` is optional on a workflow item, so the value is read
                # through a guarded chain: a missing state is not an approval.
                ca_approved = any(
                    getattr(getattr(i, "state", None), "value", None) == "APPROVED_BY_CA"
                    for i in items
                )
            except Exception:  # noqa: BLE001 - view must not crash
                ca_approved = False
        execution_environment = (
            "SHADOW" if bool(getattr(self.paper, "shadow_mode", False)) else "PAPER"
        )
        capital_by = (
            self.control_plane.live_capital_approved_by
            if self.control_plane is not None
            else None
        )
        autonomy = (
            self.control_plane.autonomy.value if self.control_plane is not None else "—"
        )
        audit_valid, _ = self.store.verify_chain()
        risk_healthy = bool(self.risk_governor is not None and not self.risk_governor.locked_out)

        def gate(gid: str, title: str, approved: bool | None, ready: bool, unblock: str) -> dict[str, Any]:
            status = "APPROVED" if approved else ("READY" if ready else "BLOCKED")
            return {
                "gate": gid,
                "title": title,
                "status": status,
                "how_to_unblock": "" if approved or ready else unblock,
            }

        def recorded_gate(gid: str, title: str, recorded_by: str | None, detail: str) -> dict[str, Any]:
            return {
                "gate": gid,
                "title": title,
                "status": "RECORDED" if recorded_by else "BLOCKED",
                "how_to_unblock": detail if not recorded_by else "Recorded for audit only; does not enable live routing.",
            }

        gates = [
            gate(
                "execution_environment",
                f"Execution environment: {execution_environment}",
                None,
                execution_environment in {"PAPER", "SHADOW"},
                "Configure the composition root for paper or shadow mode.",
            ),
            gate(
                "paper_capability",
                "Paper/shadow execution capability",
                None,
                self.paper is not None,
                "Wire the paper execution engine before running simulation.",
            ),
            gate(
                "testnet_capability",
                "Broker testnet adapter capability",
                None,
                False,
                "The current composition root is paper-only; testnet adapter wiring is not verified.",
            ),
            gate(
                "testnet_validation",
                "Broker testnet validation",
                None,
                False,
                "Complete authenticated sandbox order, cancel, fill, reconnect, and reconciliation tests.",
            ),
            gate(
                "live_adapter",
                "Live execution adapter",
                None,
                False,
                "Live routing is unavailable in this release and is constitutionally disabled.",
            ),
            gate(
                "risk_health",
                "Risk subsystem healthy",
                risk_healthy,
                False,
                "Restore the risk governor and clear any lockout through reviewed human action.",
            ),
            gate(
                "audit_integrity",
                "Audit chain integrity",
                audit_valid,
                False,
                "Stop and investigate the first invalid audit sequence.",
            ),
            gate(
                "broker_testnet",
                "Broker testnet credentials",
                None,
                False,
                "Credentials alone are insufficient; testnet adapter wiring and validation are still required.",
            ),
            gate(
                "market_data_licensed",
                "Licensed market data",
                None,
                _env_enabled(os.environ.get("MARKETSTACK_API_KEY"))
                or _env_enabled(os.environ.get("FINNHUB_API_KEY")),
                "Configure and validate a licensed provider; synthetic replay remains non-production data.",
            ),
            gate(
                "tax_signoff",
                "Tax professional sign-off",
                ca_approved,
                False,
                "A licensed professional must move the filing review to APPROVED_BY_CA.",
            ),
            recorded_gate(
                "human_live_approval",
                "Human live-capital approval record",
                capital_by,
                "An ADMIN may record the approval through the audited control plane.",
            ),
            recorded_gate(
                "live_capital",
                "Live capital approval (record only)",
                capital_by,
                "An ADMIN may record the approval through the audited control plane; it cannot enable routing.",
            ),
            gate(
                "constitutional_live_routing",
                "Constitutional live-routing authorization",
                False,
                False,
                "Requires a ratified constitutional amendment and a separate reviewed production composition root.",
            ),
        ]
        return {
            "execution_environment": execution_environment,
            "autonomy": autonomy,
            "live_capital_approved_by": capital_by,
            "live_routing_enabled": False,
            "gates": gates,
            "production_allowed": False,
        }

    # ------------------------------------------------- analytics (Phase: charts)

    def equity(self) -> dict[str, Any]:
        """Equity curve + derived drawdown series + benchmark for the performance chart."""
        curve = list(self.equity_curve or [])
        peak = curve[0] if curve else 0.0
        dd: list[float] = []
        for value in curve:
            peak = max(peak, value)
            dd.append(round((peak - value) / peak * 100.0, 3) if peak else 0.0)
        bench = list(getattr(self, "_benchmark_curve", []) or [])
        return {
            "equity": curve,
            "drawdown_pct": dd,
            "benchmark": bench,
            "start": curve[0] if curve else None,
            "end": curve[-1] if curve else None,
            "points": len(curve),
        }

    def graduation(self) -> dict[str, Any]:
        """Paper graduation criteria (Thales pattern): is this strategy ready for live?"""
        curve = list(self.equity_curve or [])
        pnl_data = self.pnl()
        totals = pnl_data["totals"]
        trades = totals["trades"]
        win_rate = totals["win_rate_pct"]

        peak = curve[0] if curve else 1.0
        max_dd = 0.0
        for v in curve:
            peak = max(peak, v)
            if peak > 0:
                max_dd = max(max_dd, (peak - v) / peak * 100.0)

        returns = (
            [(b - a) / a for a, b in zip(curve, curve[1:], strict=False)] if len(curve) >= 2 else []
        )
        n = len(returns)
        sharpe = 0.0
        if n > 1 and returns:
            mean_r = sum(returns) / n
            std_r = (sum((r - mean_r) ** 2 for r in returns) / (n - 1)) ** 0.5
            if std_r > 0:
                sharpe = round(mean_r / std_r * (n**0.5), 2)

        criteria = [
            {
                "name": "Sharpe ratio",
                "current": sharpe,
                "threshold": 1.5,
                "op": ">=",
                "pass": sharpe >= 1.5,
            },
            {
                "name": "Trade count",
                "current": trades,
                "threshold": 50,
                "op": ">=",
                "pass": trades >= 50,
            },
            {
                "name": "Win rate",
                "current": win_rate,
                "threshold": 45.0,
                "op": ">=",
                "pass": win_rate >= 45.0,
            },
            {
                "name": "Max drawdown",
                "current": round(max_dd, 2),
                "threshold": 20.0,
                "op": "<=",
                "pass": max_dd <= 20.0,
            },
        ]
        all_pass = all(c["pass"] for c in criteria)
        return {
            "ready_for_live": False,
            "paper_criteria_pass": all_pass,
            "criteria": criteria,
            "note": "Paper metrics are informational only; live routing is constitutionally disabled in this release.",
        }

    def _family_join(self) -> dict[str, dict[str, Any]]:
        """execution_id -> {family, symbol} joined from strategy events."""
        fam_by_strategy: dict[str, str] = {}
        sym_by_strategy: dict[str, str] = {}
        for p in self.store.iter_event_payloads("aios.c4.strategy_generated"):
            sid = p.get("strategy_id")
            if sid:
                fam_by_strategy[sid] = p.get("family", "unknown")
                sym_by_strategy[sid] = p.get("symbol", "?")
        exec_map: dict[str, dict[str, Any]] = {}
        for p in self.store.iter_event_payloads("aios.c5.order_executed"):
            eid = p.get("execution_id")
            sid = p.get("strategy_id")
            if eid and sid:
                exec_map[eid] = {
                    "family": fam_by_strategy.get(sid, "unknown"),
                    "symbol": sym_by_strategy.get(sid, "?"),
                }
        return exec_map

    def pnl(self) -> dict[str, Any]:
        """Realized P&L broken down by strategy family and symbol + fee totals."""
        exec_map = self._family_join()
        by_family: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"trades": 0, "wins": 0, "pnl": 0.0}
        )
        by_symbol: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"trades": 0, "wins": 0, "pnl": 0.0}
        )
        total = {"trades": 0, "wins": 0, "pnl": 0.0}
        for execution_id, pnl in self.store.pnl_series():
            meta = exec_map.get(execution_id, {"family": "unknown", "symbol": "?"})
            win = pnl > 0
            for bucket, key in ((by_family, meta["family"]), (by_symbol, meta["symbol"])):
                b = bucket[key]
                b["trades"] += 1
                b["wins"] += int(win)
                b["pnl"] = round(b["pnl"] + pnl, 2)
            total["trades"] += 1
            total["wins"] += int(win)
            total["pnl"] = round(total["pnl"] + pnl, 2)

        fees_minor = (self.ledger.balances() if self.ledger else {}).get("EXPENSE:FEES", 0)
        return {
            "totals": {
                **total,
                "win_rate_pct": round(total["wins"] / total["trades"] * 100, 2)
                if total["trades"]
                else 0.0,
                "fees": round(fees_minor / 100.0, 2),
            },
            "by_family": dict(by_family),
            "by_symbol": dict(by_symbol),
        }

    def strategies(self) -> list[dict[str, Any]]:
        """Per-family performance stats for the Strategy Center."""
        breakdown = self.pnl()
        out = []
        for family, stats in sorted(breakdown["by_family"].items()):
            out.append(
                {
                    "family": family,
                    "trades": stats["trades"],
                    "wins": stats["wins"],
                    "losses": stats["trades"] - stats["wins"],
                    "win_rate_pct": round(stats["wins"] / stats["trades"] * 100, 2)
                    if stats["trades"]
                    else 0.0,
                    "pnl": stats["pnl"],
                    "active": True,
                }
            )
        return out

    def alerts(self) -> list[dict[str, Any]]:
        """Aggregated alert center: critical/warning across all guard rails."""
        alerts: list[dict[str, Any]] = []
        for p in self.store.iter_event_payloads("aios.risk.emergency")[-20:]:
            alerts.append(
                {
                    "severity": "CRITICAL" if p.get("lockout_engaged") else "WARNING",
                    "category": "RISK",
                    "message": p.get("reason", "risk event"),
                    "ts": p.get("created_at"),
                }
            )
        for p in self.store.iter_event_payloads("aios.c11.compliance_alert")[-20:]:
            alerts.append(
                {
                    "severity": p.get("severity", "WARNING"),
                    "category": "COMPLIANCE",
                    "message": p.get("detail", "compliance alert"),
                    "symbol": p.get("symbol"),
                    "ts": p.get("created_at"),
                }
            )
        for p in self.store.iter_event_payloads("aios.c1.data_anomaly")[-20:]:
            alerts.append(
                {
                    "severity": p.get("severity", "WARNING"),
                    "category": "DATA",
                    "message": p.get("detail", "data anomaly"),
                    "symbol": p.get("symbol"),
                    "ts": p.get("created_at"),
                }
            )
        for p in self.store.iter_event_payloads("aios.c5.reconciliation_failed")[-5:]:
            alerts.append(
                {
                    "severity": "CRITICAL",
                    "category": "EXECUTION",
                    "message": "reconciliation failed",
                    "ts": p.get("created_at"),
                }
            )
        severity_rank = {"CRITICAL": 0, "WARNING": 1, "IMPORTANT": 2, "INFO": 3}
        alerts.sort(key=lambda a: severity_rank.get(a["severity"], 9))
        return alerts

    def memory_center(self) -> dict[str, Any]:
        counts = self.store.counts()
        lessons = self.store.iter_event_payloads("aios.c6.observation_completed")[-50:]
        sample = []
        for obs in reversed(lessons):
            for lesson in obs.get("lessons_learned", [])[:1]:
                sample.append(
                    {
                        "execution_id": obs.get("execution_id"),
                        "lesson": lesson,
                        "exit_reason": obs.get("exit_reason"),
                    }
                )
        return {
            "counts": counts,
            "lesson_samples": sample[:10],
            "vector_collections": ["postmortem_lessons"],
            "note": "Raw log is immutable; summaries always reference evidence ids.",
        }

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
    lines.append(f'aios_emergency_state{{state="{state}"}} 1')
    return "\n".join(lines) + "\n"
