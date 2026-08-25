"""Operator chat console (Experience Plane): ask the OS anything.

A natural-language front door for operators:

- QUERIES  ("pnl", "show rejected hypotheses", "model metrics", "gates")
    -> answered from the read-only snapshot builders. Zero authority.
- COMMANDS ("pause trading", "set autonomy supervised", "promote model …")
    -> executed THROUGH the audited ControlPlane with the operator's OWN
       role. The bot never holds authority; RBAC + receipts decide.

Deterministic intent matching first — the console works with zero LLM keys.
An optional gateway can rephrase answers later without ever touching the
authorization path.
"""

import re
from typing import Any

from api.views import SystemSnapshotBuilder
from core.control_plane import ControlPlane


class OperatorChat:
    """Intent router between an operator and the read-only views / control plane."""

    def __init__(self, builder: SystemSnapshotBuilder, control_plane: ControlPlane | None) -> None:
        self.builder = builder
        self.control_plane = control_plane

    # ------------------------------------------------------------- intents

    _QUERY_ROUTES: tuple[tuple[str, str, str], ...] = (
        # (regex, builder method, human label)
        (r"\bp ?/? ?l\b|pnl|profit|loss", "pnl", "P&L analysis"),
        (r"equity|balance|nav", "executive", "executive snapshot"),
        (r"\brisk\b|drawdown", "risk_state", "risk state"),
        (r"\btrades?\b|executions?|fills?", "executions", "recent executions"),
        (r"\bposition", "positions", "open positions"),
        (r"hypothes|knowledge|research graph", "knowledge", "hypothesis knowledge"),
        (r"\bmodels?\b|logreg|baseline", "models_view", "model registry"),
        (r"evaluation|verdicts?", "evaluations_view", "evaluation records"),
        (r"platform events?", "platform_feed", "platform events"),
        (r"\bgates?\b|production|live capital|tax|testnet", "gates_view", "human-held gates"),
        (r"\bhealth\b|chain", "health", "system health"),
        (r"calibration|brier", "research_quality", "prediction calibration"),
    )

    _COMMAND_ROUTES: tuple[tuple[str, str, dict[str, Any]], ...] = (
        (r"^pause\b|^stop trading", "pause_trading", {}),
        (r"^resume\b|^start trading", "resume_trading", {}),
        (r"^set autonomy\s+(manual|assisted|supervised|autonomous)", "set_autonomy", {}),
        (r"^approve live capital", "approve_live_capital", {}),
        (r"^evaluate trial\s+(\S+)", "evaluate_trial", {"name": "{0}"}),
        (r"^promote model\s+(\S+)(?:\s+v(\S+))?", "promote_model",
         {"model_id": "{0}", "version": "{1|v1}"}),
        (r"^promote challenger\s+(\S+)", "promote_challenger",
         {"trial_name": "{0}", "decision": "promote"}),
        (r"^reject challenger\s+(\S+)", "promote_challenger",
         {"trial_name": "{0}", "decision": "reject"}),
    )

    # ------------------------------------------------------------- handling

    async def ask(self, operator_id: str, role: str, message: str) -> dict[str, Any]:
        message = (message or "").strip()
        if not message:
            return self._help()

        lowered = message.lower()

        # ---- commands first (explicit verbs)
        command = self._match_command(lowered)
        if command is not None:
            action, params = command
            if self.control_plane is None:
                return {"kind": "error", "answer": "control plane not wired"}
            try:
                record = await self.control_plane.execute(operator_id, role, action, params)
            except PermissionError as exc:
                return {"kind": "denied", "answer": f"DENIED: {exc}", "action": action}
            except (ValueError, RuntimeError, NotImplementedError) as exc:
                return {"kind": "error", "answer": f"{type(exc).__name__}: {exc}", "action": action}
            inner = record.get("result", record)
            return {
                "kind": "command",
                "action": action,
                "params": params,
                "result": inner,
                "answer": f"{action} OK (audited): {inner}",
            }

        # ---- queries (read-only)
        route = self._match_query(lowered)
        if route is not None:
            label, method = route
            data = getattr(self.builder, method)()
            return {
                "kind": "query",
                "query": label,
                "data": data,
                "answer": f"{label}: see data payload ({self._summarize(data)})",
            }

        return self._help()

    # ------------------------------------------------------------- internals

    def _match_command(self, lowered: str) -> tuple[str, dict[str, Any]] | None:
        for pattern, action, template in self._COMMAND_ROUTES:
            match = re.search(pattern, lowered)
            if match is None:
                continue
            params: dict[str, Any] = {}
            groups = match.groups()
            for key, value in template.items():
                if isinstance(value, str) and value.startswith("{"):
                    spec = value.strip("{}")
                    if "|" in spec:
                        idx, default = spec.split("|")
                        raw = groups[int(idx)] if groups[int(idx)] else default
                    else:
                        raw = groups[int(spec)]
                    params[key] = raw
                else:
                    params[key] = value
            if action == "set_autonomy":
                params = {"mode": groups[0]}
            return action, params
        return None

    def _match_query(self, lowered: str) -> tuple[str, str] | None:
        for pattern, method, label in self._QUERY_ROUTES:
            if re.search(pattern, lowered):
                return label, method
        return None

    @staticmethod
    def _summarize(data: Any) -> str:
        if isinstance(data, list):
            return f"{len(data)} rows"
        if isinstance(data, dict):
            if "gates" in data:
                blocked = [g["gate"] for g in data["gates"] if g["status"] != "APPROVED"]
                return (
                    "production ALLOWED"
                    if not blocked
                    else f"blocked by: {', '.join(blocked)}"
                )
            keys = ", ".join(list(data.keys())[:4])
            return f"{len(data)} fields ({keys}...)"
        return type(data).__name__

    @staticmethod
    def _help() -> dict[str, Any]:
        return {
            "kind": "help",
            "answer": (
                "ASK (read-only): pnl · equity · risk · trades · positions · "
                "hypotheses · models · evaluations · platform events · gates · "
                "health · calibration\n"
                "COMMAND (RBAC-audited): pause/resume trading · set autonomy "
                "<mode> · approve live capital · evaluate trial <name> · promote "
                "model <id> [vX] · promote/reject challenger <name>"
            ),
        }
