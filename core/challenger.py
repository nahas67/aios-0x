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
from kernel.promotion import PromotionController, RollbackController
from research.evaluation import EvaluationRecord, EvaluationVerdict, evaluate_trial

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
    evaluation: EvaluationRecord | None = None

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
    """Owns trials; persists evaluations into the hash-chained audit log.

    Promotion is fail-closed on TWO gates: a human must act (PROMOTE action)
    AND a PASS EvaluationRecord must exist. Neither alone suffices.
    """

    def __init__(
        self,
        store: BaseMemoryStore,
        promotions: PromotionController | None = None,
        rollbacks: RollbackController | None = None,
    ) -> None:
        self.store = store
        self.trials: dict[str, ChallengerTrial] = {}
        self._promotions = promotions
        self._rollbacks = rollbacks

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

        # Formal EvaluationRecord (§14): verdict with honesty gates, stored on
        # the trial and in the audit trail. This record is what promotion
        # requires — the raw recommendation alone is no longer sufficient.
        metric_value_map = {
            "pnl": (trial.champion.pnl, trial.challenger.pnl),
            "directional_accuracy_pct": (
                trial.champion.directional_accuracy_pct,
                trial.challenger.directional_accuracy_pct,
            ),
            "max_drawdown_pct": (
                -trial.champion.max_drawdown_pct,
                -trial.challenger.max_drawdown_pct,
            ),
        }
        champ_v, chall_v = metric_value_map.get(
            trial.metric, (trial.champion.pnl, trial.challenger.pnl)
        )
        trial.evaluation = evaluate_trial(
            champion_trades=trial.champion.trades,
            challenger_trades=trial.challenger.trades,
            metric=trial.metric,
            champion_value=champ_v,
            challenger_value=chall_v,
            trial_name=name,
        )

        recommendation = trial.recommend()
        recommendation["verdict"] = trial.evaluation.verdict.value
        self.store.append_event(
            "EVALUATION_RECORD",
            trial.evaluation.evaluation_id,
            trial.evaluation.model_dump(mode="json"),
        )
        self.store.append_event(
            "CHALLENGER_EVALUATION",
            name,
            {
                "champion": vars(trial.champion),
                "challenger": vars(trial.challenger),
                "recommendation": recommendation,
                "evaluation": trial.evaluation.model_dump(mode="json"),
            },
        )
        return recommendation

    def promote(self, name: str, operator_id: str) -> dict[str, Any]:
        """HUMAN-GATED + EVIDENCE-GATED promotion.

        Requires: (1) EVALUATED state, (2) an EvaluationRecord with verdict
        PASS. A human CANNOT override a FAIL/INCONCLUSIVE verdict — that is
        the §21 rule "no self-promotion" applied to operators too.
        """
        trial = self._get(name)
        if trial.state != TrialState.EVALUATED:
            raise PermissionError(
                f"trial {name} is {trial.state.value}; promotion requires EVALUATED evidence"
            )
        if trial.evaluation is None:
            raise PermissionError(
                f"trial {name} has no EvaluationRecord; promotion denied (fail closed)"
            )
        if trial.evaluation.verdict is not EvaluationVerdict.PASS:
            raise PermissionError(
                f"trial {name} verdict is {trial.evaluation.verdict.value}; "
                "promotion requires PASS — humans cannot overrule evidence"
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

        # Kernel promotion controller: receipt + rollback target registration.
        rollback_version = ""
        if self._promotions is not None and self._rollbacks is not None:
            self._promotions.propose("trial", name, "challenger", evaluation_ref=trial.evaluation.evaluation_id)
            self._promotions.mark_evaluated("trial", name, "challenger")
            self._rollbacks.register_target("trial", name, "challenger", "baseline")
            self._promotions.promote("trial", name, "challenger", operator_id, rollback_target_version="baseline")
            rollback_version = "baseline"

        trial.state = TrialState.PROMOTED
        trial.promoted_by = operator_id
        self.store.append_event(
            "CHALLENGER_DECISION",
            name,
            {
                "state": "PROMOTED",
                "by": operator_id,
                "evaluation_id": trial.evaluation.evaluation_id,
                "rollback_target": rollback_version,
            },
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
