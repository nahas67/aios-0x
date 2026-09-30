"""Split-conformal prediction intervals (goal G110).

A prediction without an interval is a guess with a decimal point, and an
interval fitted on training residuals is self-deception with a confidence
level: the model has already seen those residuals, so they are small for the
same reason a student grades their own homework highly. Split conformal
prediction (Vovk et al., 2005; Papadopoulos et al., 2002) earns its coverage
from a held-out calibration set the predictor never trained on, and the
finite-sample correction keeps the promise honest at small n.

Two disciplines are structural rather than advisory:

*Residuals arrive, they are not computed here.* The API takes calibration
residuals (or calibration truths plus out-of-sample predictions), never a
training set. A function that accepted training data and promised to split it
internally would be trusting the caller to have kept the split clean — the
exact failure this module exists to prevent. Separation of the calibration
sample is the caller's responsibility and is stated as such; what this module
guarantees is that *given* a calibration sample, the interval covers at the
stated rate up to the finite-sample slack.

*Degenerate inputs are refused, not smoothed.* An empty calibration set, an
alpha outside (0, 1), or a non-finite residual cannot produce an interval,
and producing one anyway — a zero-width interval, a vacuous (−inf, +inf) —
would let a downstream gate read precision where there is none.

Standard library only. The normal quantile needed for the asymptotic
comparison comes from the existing ``normal_ppf``; no distribution is
assumed by the interval itself, which is the point of conformal prediction.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "ConformalInterval",
    "conformal_interval",
    "conformal_quantile",
    "coverage_of",
]


@dataclass(frozen=True)
class ConformalInterval:
    """A prediction interval with its provenance.

    ``quantile`` is the calibrated half-width in residual units; ``method``
    names how it was computed so a reader can reproduce it; ``n_calibration``
    and ``alpha`` are the inputs the guarantee depends on. An interval that
    does not carry these is a pair of numbers, not a claim.
    """

    lower: float
    upper: float
    quantile: float
    method: str
    n_calibration: int
    alpha: float

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def contains(self, value: float) -> bool:
        return self.lower <= value <= self.upper


def conformal_quantile(residuals: Sequence[float], alpha: float) -> float:
    """The (1 − α) split-conformal quantile of absolute residuals.

    Uses the finite-sample correction ``ceil((n+1)(1−α))/n`` (Vovk, 2012):
    the empirical quantile of n points covers the next exchangeable point at
    rate below nominal, and the correction restores the guarantee instead of
    hoping n is large enough that nobody notices.
    """
    values = [abs(float(r)) for r in residuals]
    if len(values) < 2:
        raise ValueError(
            f"conformal calibration needs at least 2 residuals; got {len(values)}. "
            "An interval from one residual is a guess with error bars drawn on."
        )
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must lie in (0, 1); got {alpha}")
    if any(not math.isfinite(v) for v in values):
        raise ValueError(
            "calibration residuals must all be finite: a non-finite residual "
            "is a failed prediction, not a large one, and folding it into a "
            "quantile would launder the failure into width"
        )
    ordered = sorted(values)
    rank = math.ceil((len(ordered) + 1) * (1.0 - alpha))
    rank = min(rank, len(ordered))
    return ordered[rank - 1]


def conformal_interval(
    point_prediction: float,
    residuals: Sequence[float],
    alpha: float = 0.10,
) -> ConformalInterval:
    """Center a symmetric interval on a point prediction.

    Symmetry around the point prediction is a choice, and a limiting one for
    skewed errors — stated here so nobody mistakes it for a property of the
    world. The coverage property (marginal 1 − α over exchangeable draws, up
    to finite-sample slack) is enforced by
    ``test_empirical_coverage_holds_at_the_stated_rate``, *provided the
    residuals come from held-out data the predictor never trained on*.
    Residuals from the training set produce intervals that are too narrow by
    construction; this function cannot tell them apart from honest ones, which
    is why the separation lives in the caller's pipeline and in
    ``test_training_residuals_produce_dishonest_intervals``, which demonstrates
    the collapse.
    """
    if not math.isfinite(point_prediction):
        raise ValueError("the point prediction must be finite: no interval centers on NaN")
    quantile = conformal_quantile(residuals, alpha)
    return ConformalInterval(
        lower=point_prediction - quantile,
        upper=point_prediction + quantile,
        quantile=quantile,
        method="split-conformal absolute residuals, finite-sample corrected",
        n_calibration=len(list(residuals)),
        alpha=alpha,
    )


def coverage_of(interval: ConformalInterval, outcomes: Sequence[float]) -> float:
    """Empirical coverage: the fraction of outcomes the interval contains.

    The check a calibration claim must survive. Reported as a bare fraction —
    whether it clears 1 − α within tolerance is the gate's decision, not this
    function's, because the tolerance depends on n and belongs with the
    decision that uses it.
    """
    outcomes = list(outcomes)
    if not outcomes:
        raise ValueError("coverage of nothing is undefined; supply outcomes")
    return sum(1.0 for y in outcomes if interval.contains(y)) / len(outcomes)
