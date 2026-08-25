"""Evaluation Plane (original architecture §14): formal verdicts, never vibes.

Every consequential artifact — a challenger trial, a trained model — passes
through a structured evaluation producing an EvaluationRecord:

    PASS | FAIL | INCONCLUSIVE

"Looks good" is not a verdict. Honesty gates are structural:

- Trials with too few trades on either side are INCONCLUSIVE regardless of
  margin (small samples lie).
- Models evaluated on fewer than MIN_WF_PREDICTIONS walk-forward predictions
  are INCONCLUSIVE.
- A FAIL or INCONCLUSIVE record makes promotion IMPOSSIBLE — even for a
  human operator (enforced in the challenger registry / promotion flow).
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvaluationVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


MIN_TRIAL_TRADES = 5
MIN_WF_PREDICTIONS = 30
MIN_WF_ACCURACY_PCT = 55.0
MAX_WF_BRIER = 0.5
MIN_CHALLENGER_MARGIN = 1e-9


class EvaluationRecord(BaseModel):
    """Immutable evidence-backed verdict for one subject."""

    evaluation_id: str = Field(default_factory=lambda: _entropy_id())
    subject_type: str  # "trial" | "model"
    subject_ref: str
    evaluator: str  # "challenger_compare_v1" | "walk_forward_v1" | ...
    verdict: EvaluationVerdict
    dimensions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    summary: str = ""


def _entropy_id() -> str:
    import hashlib
    import time

    return hashlib.sha256(f"{time.time_ns()}".encode()).hexdigest()[:16]


def evaluate_trial(
    champion_trades: int,
    challenger_trades: int,
    metric: str,
    champion_value: float,
    challenger_value: float,
    trial_name: str,
) -> EvaluationRecord:
    """Champion-vs-challenger verdict with minimum-sample honesty gates."""
    dimensions: dict[str, dict[str, Any]] = {
        "sample_size": {
            "passed": champion_trades >= MIN_TRIAL_TRADES
            and challenger_trades >= MIN_TRIAL_TRADES,
            "champion_trades": champion_trades,
            "challenger_trades": challenger_trades,
            "required": MIN_TRIAL_TRADES,
        },
        "metric_superiority": {
            "passed": challenger_value > champion_value + MIN_CHALLENGER_MARGIN,
            "metric": metric,
            "champion": round(champion_value, 4),
            "challenger": round(challenger_value, 4),
            "margin": round(challenger_value - champion_value, 4),
        },
    }
    sample_ok = dimensions["sample_size"]["passed"]
    better = dimensions["metric_superiority"]["passed"]

    if not sample_ok:
        verdict = EvaluationVerdict.INCONCLUSIVE
        summary = (
            f"INCONCLUSIVE: insufficient trades "
            f"(champion={champion_trades}, challenger={challenger_trades}, "
            f"need >= {MIN_TRIAL_TRADES} each)"
        )
    elif better:
        verdict = EvaluationVerdict.PASS
        summary = f"PASS: challenger better on {metric}"
    else:
        verdict = EvaluationVerdict.FAIL
        summary = f"FAIL: challenger not better on {metric}"

    return EvaluationRecord(
        subject_type="trial",
        subject_ref=trial_name,
        evaluator="challenger_compare_v1",
        verdict=verdict,
        dimensions=dimensions,
        evidence_refs=[f"trial:{trial_name}"],
        summary=summary,
    )


def evaluate_model_walk_forward(
    model_ref: str, metrics: dict[str, Any]
) -> EvaluationRecord:
    """Model verdict from walk-forward metrics only. Small n => INCONCLUSIVE."""
    accuracy = float(metrics.get("wf_accuracy_pct", 0.0))
    brier = float(metrics.get("wf_brier", 1.0))
    n = int(float(metrics.get("wf_n_predictions", 0.0)))

    dimensions: dict[str, dict[str, Any]] = {
        "sample_size": {"passed": n >= MIN_WF_PREDICTIONS, "n_predictions": n,
                         "required": MIN_WF_PREDICTIONS},
        "accuracy": {"passed": accuracy >= MIN_WF_ACCURACY_PCT, "value": accuracy,
                      "required_pct": MIN_WF_ACCURACY_PCT},
        "calibration": {"passed": 0.0 < brier <= MAX_WF_BRIER, "brier": brier,
                         "max": MAX_WF_BRIER},
    }
    if not dimensions["sample_size"]["passed"]:
        verdict = EvaluationVerdict.INCONCLUSIVE
        summary = f"INCONCLUSIVE: only {n} walk-forward predictions (< {MIN_WF_PREDICTIONS})"
    elif all(d["passed"] for d in dimensions.values()):
        verdict = EvaluationVerdict.PASS
        summary = f"PASS: wf accuracy {accuracy}% with brier {brier} over {n} predictions"
    else:
        verdict = EvaluationVerdict.FAIL
        failed = [name for name, d in dimensions.items() if not d["passed"]]
        summary = f"FAIL: {', '.join(failed)}"

    return EvaluationRecord(
        subject_type="model",
        subject_ref=model_ref,
        evaluator="walk_forward_v1",
        verdict=verdict,
        dimensions=dimensions,
        evidence_refs=[f"MODEL_TRAINED:{model_ref}"],
        summary=summary,
    )
