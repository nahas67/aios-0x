"""Position sizing from distributions and covariance (goal G130).

Expected returns are distributions, not points: each symbol carries a mean
and a dispersion, and the covariance matrix says how they move together. Two
independent optimizers read the same inputs and each produces weights:

*inverse-volatility* (closed form, correlation-blind) and *hierarchical risk
parity* (correlation-clustered recursive bisection, López de Prado 2016 —
single-linkage on correlation distance, implemented here in stdlib because
the method needs sorting and bisection, not a solver).

The pair exists for disagreement, not for consensus. When the two methods
differ beyond tolerance, the output is a finding naming the divergence, not
an average: averaging two methods that disagree manufactures a portfolio
neither method endorses, and the average of a right answer and a wrong one
is a wrong answer with better manners. Agreement within tolerance returns
either set (they coincide) with the measured divergence recorded.

The output is a ``PortfolioProposal``: weights, methods, agreement metrics,
expected portfolio statistics. It is explicitly not an order — no venue, no
order id, no submit path — and the type carries that absence so no caller can
reach for what is not there. Turning a proposal into an order is the
firewall's job, downstream, with an envelope.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "CovarianceMatrix",
    "ExpectedReturns",
    "OptimizationDisagreement",
    "PortfolioBrain",
    "PortfolioProposal",
    "hierarchical_risk_parity_weights",
    "inverse_volatility_weights",
]

#: Maximum weight divergence the two optimizers may show before the output
#: becomes a finding instead of a proposal. Stated, not tuned: five points of
#: weight on one name is a different portfolio, not a rounding difference.
MAX_WEIGHT_DIVERGENCE = 0.05


class OptimizationDisagreement(ValueError):
    """The two optimizers disagreed beyond tolerance.

    Raised rather than returned, because a disagreement is not a result with
    a flag on it — any caller that could catch and ignore the flag would have
    an average wearing a warning label. The exception carries the per-symbol
    divergences so the review starts from numbers, not from surprise.
    """


class ExpectedReturns(BaseModel):
    """Mean and dispersion per symbol. Dispersion is required, not optional:
    a point estimate without uncertainty is a wish, and sizing from wishes is
    how books discover covariance in production."""

    model_config = {"frozen": True}

    means: dict[str, float]
    sds: dict[str, float] = Field(description="Per-symbol dispersion; every symbol in means needs one")

    @model_validator(mode="after")
    def _complete_and_positive(self) -> ExpectedReturns:
        missing = [symbol for symbol in self.means if symbol not in self.sds]
        if missing:
            raise ValueError(
                f"symbols without dispersion: {missing}. Size from a mean "
                "without uncertainty and the covariance is decoration."
            )
        non_positive = [symbol for symbol, sd in self.sds.items() if sd <= 0.0]
        if non_positive:
            raise ValueError(
                f"non-positive dispersion for {non_positive}: a zero-volatility "
                "asset has infinite precision, which sizes to the whole book. "
                "Refused rather than normalized."
            )
        for symbol, sd in self.sds.items():
            if not math.isfinite(sd) or not math.isfinite(self.means.get(symbol, 0.0)):
                raise ValueError(f"non-finite input for {symbol!r}")
        return self

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.means))


class CovarianceMatrix(BaseModel):
    """Pairwise covariances, keyed both directions or neither.

    Validated for symmetry and positive diagonal at construction. Full
    positive-definiteness is not checked — an O(n³) decomposition on every
    construction would tax the path that needs this object most — and the
    omission is stated here rather than hidden: HRP tolerates indefinite
    input by clustering on correlation distance, and the disagreement gate
    catches what the validation does not.
    """

    model_config = {"frozen": True}

    symbols: tuple[str, ...]
    entries: dict[str, float] = Field(
        description="Keyed 'a|b' with a,b in symbols; both directions or neither"
    )

    @model_validator(mode="after")
    def _symmetric_positive_diagonal(self) -> CovarianceMatrix:
        names = set(self.symbols)
        for key, value in self.entries.items():
            try:
                first, second = key.split("|")
            except ValueError:
                raise ValueError(f"covariance key {key!r} must be 'a|b'") from None
            if first not in names or second not in names:
                raise ValueError(f"covariance key {key!r} names unknown symbols")
            mirror = f"{second}|{first}"
            if self.entries.get(mirror) != value:
                raise ValueError(
                    f"covariance {key!r} is asymmetric: {value} vs "
                    f"{self.entries.get(mirror)}. An asymmetric covariance "
                    "is not a covariance."
                )
        for symbol in self.symbols:
            diagonal = self.entries.get(f"{symbol}|{symbol}")
            if diagonal is None:
                raise ValueError(f"missing variance for {symbol!r}")
            if diagonal <= 0.0:
                raise ValueError(f"non-positive variance for {symbol!r}: {diagonal}")
        return self

    def get(self, first: str, second: str) -> float:
        return self.entries[f"{first}|{second}"]

    def correlation(self, first: str, second: str) -> float:
        """Pearson correlation, clamped to [-1, 1] against float drift."""
        if first == second:
            return 1.0
        denominator = math.sqrt(self.get(first, first) * self.get(second, second))
        if denominator <= 0.0:
            return 0.0
        return max(-1.0, min(1.0, self.get(first, second) / denominator))


class PortfolioProposal(BaseModel):
    """Sized weights that are explicitly not an order.

    No venue, no order id, no side, no submit path: the fields an order needs
    are absent so no caller can reach for them. The expected statistics ride
    along so the proposal can be judged without re-running the optimizers,
    and the agreement metrics say how much the two methods concurred.
    """

    model_config = {"frozen": True}

    weights: dict[str, float]
    methods: tuple[str, ...] = ("inverse_volatility", "hierarchical_risk_parity")
    max_weight_divergence: float = Field(ge=0.0)
    expected_return: float
    expected_volatility: float
    rationale: str = Field(..., min_length=1)


def _normalize(weights: dict[str, float], cap: float) -> dict[str, float]:
    """Scale to sum 1.0 within a per-name cap. A cap that cannot fit is
    refused rather than breached: silently exceeding a concentration limit to
    make the arithmetic work is the optimizer overriding risk."""
    total = sum(weights.values())
    if total <= 0.0:
        raise OptimizationDisagreement("all weights zero: nothing to normalize")
    scaled = {name: weight / total for name, weight in weights.items()}
    over = {name: weight for name, weight in scaled.items() if weight > cap}
    if over:
        raise OptimizationDisagreement(
            f"per-name cap {cap:.2f} cannot fit: "
            + ", ".join(f"{name}={weight:.3f}" for name, weight in sorted(over.items()))
        )
    return scaled


def inverse_volatility_weights(
    expected: ExpectedReturns, *, cap: float = 1.0
) -> dict[str, float]:
    """Closed form, correlation-blind: weight ∝ 1/σ. The baseline the
    correlation-aware method must beat to justify its complexity."""
    raw = {symbol: 1.0 / expected.sds[symbol] for symbol in expected.symbols}
    return _normalize(raw, cap)


def _correlation_distance(covariance: CovarianceMatrix, first: str, second: str) -> float:
    return math.sqrt(max(0.0, 0.5 * (1.0 - covariance.correlation(first, second))))


def hierarchical_risk_parity_weights(
    expected: ExpectedReturns,
    covariance: CovarianceMatrix,
    *,
    cap: float = 1.0,
) -> dict[str, float]:
    """HRP by single-linkage clustering on correlation distance with
    recursive bisection on cluster variance (López de Prado 2016).

    Single linkage over quasi-diagonalization: the dendrogram order comes
    from nearest-neighbour chaining, and bisection splits variance inversely
    between adjacent clusters. Deterministic given inputs — ties break by
    sorted symbol order, so the same matrix always yields the same tree.
    """
    symbols = sorted(set(expected.symbols) & set(covariance.symbols))
    if len(symbols) < 2:
        raise OptimizationDisagreement("HRP needs at least two covered symbols")
    variances = {symbol: covariance.get(symbol, symbol) for symbol in symbols}
    # Single-linkage chaining: repeatedly attach the closest unplaced symbol
    # to the placed set. Sorted iteration keeps ties deterministic.
    ordered = [symbols[0]]
    remaining = set(symbols[1:])
    while remaining:
        best, best_distance = "", math.inf
        for candidate in sorted(remaining):
            nearest = min(_correlation_distance(covariance, candidate, placed) for placed in ordered)
            if nearest < best_distance:
                best, best_distance = candidate, nearest
        ordered.append(best)
        remaining.discard(best)

    def cluster_variance(members: list[str]) -> float:
        weights = {symbol: 1.0 / variances[symbol] for symbol in members}
        total = sum(weights.values())
        weights = {symbol: weight / total for symbol, weight in weights.items()}
        return sum(
            weights[a] * weights[b] * covariance.get(a, b) for a in members for b in members
        )

    def bisect(members: list[str], weight: float, out: dict[str, float]) -> None:
        if len(members) == 1:
            out[members[0]] = out.get(members[0], 0.0) + weight
            return
        mid = len(members) // 2
        left, right = members[:mid], members[mid:]
        var_left, var_right = cluster_variance(left), cluster_variance(right)
        total = var_left + var_right
        if total <= 0.0:
            bisect(left, weight / 2.0, out)
            bisect(right, weight / 2.0, out)
            return
        # Inverse-variance split: the calmer cluster takes the larger share.
        bisect(left, weight * (1.0 - var_left / total), out)
        bisect(right, weight * (1.0 - var_right / total), out)

    raw: dict[str, float] = {}
    bisect(ordered, 1.0, raw)
    return _normalize(raw, cap)


@dataclass(frozen=True)
class PortfolioBrain:
    """Two optimizers, one proposal or one finding. Stateless and pure.

    Long-only: every weight is non-negative by construction of both methods,
    and the cap is enforced after normalization rather than before, so a cap
    that cannot fit fails loudly instead of silently rescaling someone's risk
    limit away.
    """

    max_weight: float = 0.6
    divergence_tolerance: float = MAX_WEIGHT_DIVERGENCE

    def propose(
        self, expected: ExpectedReturns, covariance: CovarianceMatrix
    ) -> PortfolioProposal:
        """Run both optimizers; agree within tolerance or raise the finding.

        On agreement either set would do — they coincide — so the proposal
        carries the inverse-volatility weights with the measured divergence
        recorded. Recording the divergence even on agreement is what lets a
        reviewer see consensus rather than take it on faith.
        """
        first = inverse_volatility_weights(expected, cap=self.max_weight)
        second = hierarchical_risk_parity_weights(expected, covariance, cap=self.max_weight)
        names = set(first) | set(second)
        divergence = max(abs(first.get(n, 0.0) - second.get(n, 0.0)) for n in names)
        if divergence > self.divergence_tolerance:
            detail = ", ".join(
                f"{n}: iv={first.get(n, 0.0):.3f} hrp={second.get(n, 0.0):.3f}"
                for n in sorted(names)
                if abs(first.get(n, 0.0) - second.get(n, 0.0)) > self.divergence_tolerance / 2.0
            )
            raise OptimizationDisagreement(
                f"optimizers diverge (max {divergence:.3f} > tolerance "
                f"{self.divergence_tolerance:.3f}): {detail}. No average is "
                "offered: the average of two disagreeing portfolios is a "
                "portfolio neither method endorses."
            )
        symbols = expected.symbols
        mean = sum(first[s] * expected.means[s] for s in symbols)
        variance = sum(
            first[a] * first[b] * covariance.get(a, b) for a in symbols for b in symbols
        )
        return PortfolioProposal(
            weights=first,
            max_weight_divergence=round(divergence, 6),
            expected_return=mean,
            expected_volatility=math.sqrt(max(0.0, variance)),
            rationale=(
                f"inverse-volatility and HRP agree within {divergence:.4f}; "
                f"{len(symbols)} names, long-only, capped at {self.max_weight:.0%}"
            ),
        )
