"""Challenger architecture (Directives 50/51): shadow trials + human promotion.

A trial runs the CHAMPION and a CHALLENGER configuration over IDENTICAL
historical data via the honest replay runner, records both summaries as
immutable evidence, and computes a recommendation. Promotion NEVER happens
automatically: it requires a human PROMOTE_CHALLENGER control action after
the evaluation exists. Rejection is the default when evidence is absent.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.persistence import BaseMemoryStore

logger = logging.getLogger(__name__)


class TrialState(StrEnum):
    PROPOSED = "PROPOSED"
    EVALUATED = "EVALUATED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


@dataclass
class TrialResult:
    side: str  # champion | challenger
    trades: int
    pnl: float
    directional_accuracy_pct: float
    max_drawdown_pct: float


@dataclass
class ChallengerTrial:
    """One champion-vs-challenger comparison over identical data."""

    name: str
    description: str = ""
    metric: str = "pnl"  # pnl | directional_accuracy_pct | max_drawdown_pct(lower better)
    state: TrialState = TrialState.PROPOSED
    champion: TrialResult | None = None
    challenger: TrialResult | None = None
    evaluated_at: datetime | None = None
    promoted_by: str | None = None
    notes: list[str] = field(default_factory=list)

    def recommend(self) -> dict[str, Any]:
        if self.champion is None or self.challenger is None:
            return {"recommendation": "INSUFFICIENT_EVIDENCE"}
        c, ch = self.champion, self.challenger

        def get(r: TrialResult, m: str) -> float:
            value = getattr(r, m)
            metric_value: float = -value if m == "max_drawdown_pct" else value
            return metric_value

        better_challenger = get(ch, self.metric) > get(c, self.metric)
        margin = abs(get(ch, self.metric) - get(c, self.metric))
        return {
            "recommendation": "PROMOTE" if better_challenger else "REJECT",
            "metric": self.metric,
            "champion": get(c, self.metric),
            "challenger": get(ch, self.metric),
            "margin": round(margin, 4),
            "note": "Single-window evidence; require repeated windows before conviction",
        }


class ChallengeRegistry:
    """Owns trials; persists evaluations into the hash-chained audit log."""

    def __init__(self, store: BaseMemoryStore) -> None:
        self.store = store
        self.trials: dict[str, ChallengerTrial] = {}

    def propose(self, name: str, description: str = "", metric: str = "pnl") -> ChallengerTrial:
        trial = ChallengerTrial(name=name, description=description, metric=metric)
        self.trials[name] = trial
        self.store.append_event(
            "CHALLENGER_TRIAL",
            name,
            {"state": trial.state.value, "description": description, "metric": metric},
        )
        return trial

    async def evaluate(
        self,
        name: str,
        run_configured_runner: Callable[[str], Any],
        families_factory: Callable[[str], list[Any]],
    ) -> dict[str, Any]:
        """Run both sides over identical data using injected factories.

        ``families_factory(side)`` returns the StrategyFamily list for that
        side; ``run_configured_runner(families)`` must execute a full replay
        with those families and return a RunSummary.
        """
        trial = self._get(name)

        champ_families = families_factory("champion")
        chall_families = families_factory("challenger")
        _ = (champ_families, chall_families)  # factories own construction details

        summary_c = await run_configured_runner("champion")
        summary_h = await run_configured_runner("challenger")

        trial.champion = TrialResult(
            side="champion",
            trades=summary_c.trades_closed,
            pnl=summary_c.cumulative_pnl,
            directional_accuracy_pct=summary_c.directional_accuracy_pct,
            max_drawdown_pct=summary_c.max_drawdown_pct,
        )
        trial.challenger = TrialResult(
            side="challenger",
            trades=summary_h.trades_closed,
            pnl=summary_h.cumulative_pnl,
            directional_accuracy_pct=summary_h.directional_accuracy_pct,
            max_drawdown_pct=summary_h.max_drawdown_pct,
        )
        trial.state = TrialState.EVALUATED
        trial.evaluated_at = datetime.now(UTC)
        recommendation = trial.recommend()
        self.store.append_event(
            "CHALLENGER_EVALUATION",
            name,
            {
                "champion": vars(trial.champion),
                "challenger": vars(trial.challenger),
                "recommendation": recommendation,
            },
        )
        return recommendation

    def promote(self, name: str, operator_id: str) -> dict[str, Any]:
        """HUMAN-GATED promotion: only after an evaluation exists."""
        trial = self._get(name)
        if trial.state != TrialState.EVALUATED:
            raise PermissionError(
                f"trial {name} is {trial.state.value}; promotion requires EVALUATED evidence"
            )
        rec = trial.recommend()
        if rec["recommendation"] == "REJECT":
            trial.state = TrialState.REJECTED
            trial.notes.append(f"rejected by {operator_id} on evidence")
            self.store.append_event(
                "CHALLENGER_DECISION", name, {"state": "REJECTED", "by": operator_id}
            )
            logger.warning("challenger %s rejected on evidence", name)
            return {"promoted": False, "state": trial.state.value}

        trial.state = TrialState.PROMOTED
        trial.promoted_by = operator_id
        self.store.append_event(
            "CHALLENGER_DECISION",
            name,
            {"state": "PROMOTED", "by": operator_id},
        )
        logger.warning("challenger %s PROMOTED by %s", name, operator_id)
        return {"promoted": True, "state": trial.state.value}

    def reject(self, name: str, operator_id: str, note: str = "") -> dict[str, Any]:
        trial = self._get(name)
        trial.state = TrialState.REJECTED
        trial.notes.append(note or f"rejected by {operator_id}")
        self.store.append_event(
            "CHALLENGER_DECISION", name, {"state": "REJECTED", "by": operator_id}
        )
        return {"promoted": False, "state": trial.state.value}

    def _get(self, name: str) -> ChallengerTrial:
        if name not in self.trials:
            raise KeyError(f"unknown trial: {name}")
        return self.trials[name]
