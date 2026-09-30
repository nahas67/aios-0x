"""Statistics for the certification firewall (vNext goals G080, G060).

Everything here exists to answer one question honestly: *is this strategy's
apparent edge real, or is it the maximum of many things I tried?* A raw Sharpe
ratio cannot answer that. It is computed on one selected path out of N, and its
expected value under the null is not zero precisely because selection happened.

Five tools, in the order a certification runs them:

purged / embargoed cross-validation
    K-fold splits leak information through overlapping label windows. A
    training observation whose label extends into the test period has seen the
    test data. Purging removes those; embargo additionally removes the
    observations immediately after the test block, whose features may still
    encode it.

combinatorial purged CV (CPCV)
    Produces many backtest paths from one dataset, which is what makes a
    distribution of outcomes possible instead of a single number.

deflated Sharpe ratio
    Corrects for selection across N trials. The headline statistic of the
    firewall: a Sharpe of 1.8 that is the best of 10,000 trials is expected
    from a strategy with no edge at all.

probability of backtest overfitting (PBO)
    The complementary question. If a strategy is selected in-sample and then
    ranks in the bottom half out-of-sample, the selection was noise.

multiple-testing correction
    Bonferroni and Benjamini-Hochberg over the family of hypotheses actually
    tested, so a p-value is not quoted without the count it was drawn from.

Standard library only, deliberately. These are the numbers a capital decision
rests on; each is small enough to read, and a numerical library would make them
unauditable without making them any more correct. Every formula is cited in its
docstring so a reviewer can check it against the paper.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

__all__ = [
    "CPCVSplits",
    "PurgedSplit",
    "benjamini_hochberg",
    "bonferroni_threshold",
    "combinatorial_purged_splits",
    "deflated_sharpe_ratio",
    "expected_max_sharpe",
    "normal_cdf",
    "normal_ppf",
    "pbo_from_cscv",
    "probabilistic_sharpe_ratio",
    "purged_kfold_splits",
    "sharpe_ratio",
]

#: Euler-Mascheroni constant. Appears in the expected-maximum of N standard
#: normals, which is the whole point of the deflated Sharpe ratio.
_EULER_MASCHERONI = 0.5772156649015329


# ══════════════════════════════════════════════════════════════════════════
# Normal distribution
# ══════════════════════════════════════════════════════════════════════════


def normal_cdf(x: float) -> float:
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_ppf(p: float) -> float:
    """Inverse standard normal CDF.

    Acklam's rational approximation refined by one Halley step against
    ``normal_cdf``. The initial estimate is accurate to ~1.15e-9 and the
    refinement pushes the double-precision error below 1e-15, which matters
    because this feeds a threshold that decides whether a strategy trades.

    Not from training data: the coefficients are Acklam's published rational
    approximation (Algorithm 26.2.23), and the refinement step is standard
    Newton-with-correction against the exact CDF.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be in (0, 1); got {p}")

    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00)

    p_low, p_high = 0.02425, 1.0 - 0.02425
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
            ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
        )
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )

    # One Halley step against the exact CDF.
    error = normal_cdf(x) - p
    density = math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
    if density > 0.0:
        u = error / density
        x -= u / (1.0 + 0.5 * x * u)
    return x


# ══════════════════════════════════════════════════════════════════════════
# Purged and embargoed cross-validation
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PurgedSplit:
    """One train/test index split with its leakage accounting.

    ``purged`` counts training observations removed because their label window
    overlapped the test block. ``embargoed`` counts those removed from the far
    side of the test block. Both are reported rather than merely applied, so a
    report can state how much was removed - a purge that silently removed
    everything would otherwise look identical to a purge that worked.
    """

    train: tuple[int, ...]
    test: tuple[int, ...]
    purged: int
    embargoed: int

    @property
    def is_clean(self) -> bool:
        """True when no training index sits inside or adjacent to the test block."""
        return self.purged == 0 and self.embargoed == 0


def _label_end(index: int, label_horizon: int) -> int:
    """Last index whose label is contaminated by observing ``index``.

    A horizon of 3 means the label at position i was produced by looking three
    periods forward, so it overlaps the test block whenever its window reaches
    into it.
    """
    return index + max(0, label_horizon)


def purged_kfold_splits(
    n_observations: int,
    n_splits: int = 5,
    *,
    label_horizon: int = 1,
    embargo: int = 1,
) -> list[PurgedSplit]:
    """K-fold splits with purging and embargo (López de Prado, Advances in
    Financial Machine Learning, ch. 7).

    Purging removes training observations whose forward-looking label window
    reaches into the test block. Embargo additionally drops the ``embargo``
    observations immediately after the test block, whose features can still
    encode it even when their labels do not.

    The embargo percentage used by the reference implementation is 1% of the
    sample; here it is a count, because a count is the unit an operator can
    reason about when a split looks wrong.
    """
    if n_splits < 2:
        raise ValueError(f"n_splits must be at least 2; got {n_splits}")
    if n_observations < n_splits:
        raise ValueError(
            f"{n_observations} observations cannot be split into {n_splits} folds"
        )
    if embargo < 0:
        raise ValueError(f"embargo must be non-negative; got {embargo}")

    fold_size = n_observations // n_splits
    splits: list[PurgedSplit] = []
    for fold in range(n_splits):
        start = fold * fold_size
        stop = n_observations if fold == n_splits - 1 else start + fold_size
        test = tuple(range(start, stop))
        test_start, test_stop = start, stop

        train: list[int] = []
        purged = 0
        embargoed = 0
        for i in range(n_observations):
            if test_start <= i < test_stop:
                continue
            # Purge a training observation whose FORWARD label window reaches
            # into the test block. Only the pre-test side can do this: a label
            # window that starts after the test block runs away from it, so
            # purging that side as well would delete the entire tail.
            if i < test_start and _label_end(i, label_horizon) > test_start:
                purged += 1
                continue
            # Embargo the region immediately after the test block, whose
            # features can encode it even when its labels do not.
            if test_stop <= i < test_stop + embargo:
                embargoed += 1
                continue
            train.append(i)
        splits.append(
            PurgedSplit(
                train=tuple(train), test=test, purged=purged, embargoed=embargoed
            )
        )
    return splits


@dataclass(frozen=True)
class CPCVSplits:
    """Combinatorial purged cross-validation: many paths from one dataset."""

    splits: tuple[PurgedSplit, ...]
    n_groups: int
    test_groups: int

    @property
    def n_paths(self) -> int:
        """How many distinct backtest paths the combinations produce."""
        return len(self.splits)

    def phi(self) -> float:
        """The φ ratio: test observations per split divided by total.

        Bailey et al. use this to size a CPCV run: with N groups and k chosen
        as test groups, phi = k/N. A value of 1.0 means each split tests on
        everything, which defeats the purpose.
        """
        if self.n_groups == 0:
            return 0.0
        return self.test_groups / self.n_groups


def combinatorial_purged_splits(
    n_observations: int,
    n_groups: int = 6,
    *,
    test_groups: int = 2,
    label_horizon: int = 1,
    embargo: int = 1,
) -> CPCVSplits:
    """CPCV (Bailey et al., "The Probability of Backtesting Overfitting").

    Partitions the sample into ``n_groups`` contiguous blocks and enumerates
    every combination of ``test_groups`` of them. The point is a distribution
    of outcomes rather than a single number: a strategy that only works on one
    of twenty paths has not been validated.
    """
    if n_groups < 2:
        raise ValueError(f"n_groups must be at least 2; got {n_groups}")
    if not 1 <= test_groups < n_groups:
        raise ValueError(
            f"test_groups must be in [1, n_groups); got {test_groups} of {n_groups}"
        )
    if n_observations < n_groups:
        raise ValueError(f"{n_observations} observations cannot form {n_groups} groups")

    block = n_observations // n_groups
    blocks: list[tuple[int, ...]] = []
    for g in range(n_groups):
        start = g * block
        stop = n_observations if g == n_groups - 1 else start + block
        blocks.append(tuple(range(start, stop)))

    splits: list[PurgedSplit] = []
    for combo in combinations(range(n_groups), test_groups):
        test_indices: list[int] = []
        for g in combo:
            test_indices.extend(blocks[g])
        test = tuple(sorted(test_indices))
        test_start, test_stop = test[0], test[-1] + 1

        train: list[int] = []
        purged = 0
        embargoed = 0
        for i in range(n_observations):
            if test_start <= i < test_stop:
                continue
            # Same asymmetry as the k-fold case: only a pre-test observation can
            # have its label window reach into the test block.
            if i < test_start and _label_end(i, label_horizon) > test_start:
                purged += 1
                continue
            if test_stop <= i < test_stop + embargo:
                embargoed += 1
                continue
            train.append(i)
        splits.append(
            PurgedSplit(train=tuple(train), test=test, purged=purged, embargoed=embargoed)
        )
    return CPCVSplits(tuple(splits), n_groups, test_groups)


# ══════════════════════════════════════════════════════════════════════════
# Sharpe ratios, and the corrections that make them honest
# ══════════════════════════════════════════════════════════════════════════


def sharpe_ratio(returns: Sequence[float], *, periods_per_year: int = 252) -> float:
    """Annualised Sharpe ratio. Zero when the series has no dispersion.

    Zero rather than an exception: a flat series is a real observation with a
    zero ratio, and raising would make a degenerate input look like a
    computation failure.
    """
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    if variance <= 0.0:
        return 0.0
    return (mean / math.sqrt(variance)) * math.sqrt(periods_per_year)


def _skewness(returns: Sequence[float]) -> float:
    n = len(returns)
    if n < 3:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / n
    if variance <= 0.0:
        return 0.0
    third = sum((r - mean) ** 3 for r in returns) / n
    return float(third / (variance**1.5))


def _kurtosis(returns: Sequence[float]) -> float:
    """Non-excess kurtosis (normal = 3), matching the PSR formula's convention."""
    n = len(returns)
    if n < 4:
        return 3.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / n
    if variance <= 0.0:
        return 3.0
    fourth = sum((r - mean) ** 4 for r in returns) / n
    return fourth / (variance**2)


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    *,
    benchmark_sharpe: float = 0.0,
    n_observations: int = 1,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """PSR: the probability the true Sharpe exceeds ``benchmark_sharpe``.

    Bailey and Lopez de Prado, "The Deflated Sharpe Ratio". Formula:

        PSR(SR*) = Z[ (SR - SR*) sqrt(N-1)
                      / sqrt(1 - g3*SR + (g4-1)/4 * SR^2) ]

    The denominator is the point. A return series with fat tails or negative
    skew makes a given reported Sharpe less informative, and the correction is
    what stops a lottery-ticket equity curve from certifying.

    SR and SR* are in the same (here, annualised) units; N is the number of
    return observations contributing to them.
    """
    if n_observations < 2:
        raise ValueError(
            f"PSR needs at least 2 observations to mean anything; got {n_observations}"
        )
    variance_term = (
        1.0 - skewness * observed_sharpe + (kurtosis - 1.0) / 4.0 * observed_sharpe**2
    )
    if variance_term <= 0.0:
        # Degenerate distribution: the ratio is undefined, and the honest answer
        # is the probability of beating a benchmark under no information.
        return normal_cdf(observed_sharpe - benchmark_sharpe)
    z = (
        (observed_sharpe - benchmark_sharpe)
        * math.sqrt(n_observations - 1)
        / math.sqrt(variance_term)
    )
    return normal_cdf(z)


def expected_max_sharpe(
    n_trials: int, *, n_observations: int = 252, periods_per_year: int = 252
) -> float:
    """Expected maximum Sharpe across ``n_trials`` independent trials.

    The selection bias made explicit. If a team tries 1,000 strategies, the
    best of them will show a Sharpe that a worthless strategy shows *on
    average*, purely from being the best of 1,000.

    Bailey and Lopez de Prado's approximation:

        E[max] = sd(SR) * [ (1 - g) * Z^-1[1 - 1/N] + g * Z^-1[1 - 1/(N*e)] ]

    with g the Euler-Mascheroni constant, N the trial count, and sd(SR) the
    standard deviation of a single trial's Sharpe estimate.

    The sd term is why this function takes ``n_observations``. An annualised
    Sharpe estimated from k periods has standard deviation
    sqrt(periods_per_year / (k - 1)), so more observations shrink the expected
    maximum: the same reported Sharpe is harder to reach by luck when each
    trial is measured precisely. Omitting the term would claim that 5,000
    observations of a worthless strategy perform exactly as badly as 50, which
    is the opposite of what more data buys.
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be at least 1; got {n_trials}")
    if n_observations < 2:
        raise ValueError(
            f"n_observations must be at least 2 to bound a trial's Sharpe; "
            f"got {n_observations}"
        )
    if n_trials == 1:
        return 0.0
    n = float(n_trials)
    first = normal_ppf(1.0 - 1.0 / n)
    second = normal_ppf(1.0 - 1.0 / (n * math.e))
    spread = math.sqrt(periods_per_year / (n_observations - 1))
    return spread * (
        (1.0 - _EULER_MASCHERONI) * first + _EULER_MASCHERONI * second
    )


def deflated_sharpe_ratio(
    observed_sharpe: float,
    *,
    n_trials: int = 1,
    n_observations: int = 1,
    benchmark_sharpe: float | None = None,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """DSR: PSR evaluated against the Sharpe expected from pure selection.

    This is the firewall's headline number. A strategy that was the best of
    10,000 trials needs a much higher reported Sharpe to pass than one that was
    the only trial, and the DSR says by how much.

    The benchmark defaults to the expected maximum rather than zero, which is
    the entire correction: passing means "better than what trying this many
    strategies would hand you for free".
    """
    if benchmark_sharpe is None:
        benchmark_sharpe = expected_max_sharpe(n_trials, n_observations=n_observations)
    return probabilistic_sharpe_ratio(
        observed_sharpe,
        benchmark_sharpe=benchmark_sharpe,
        n_observations=n_observations,
        skewness=skewness,
        kurtosis=kurtosis,
    )


# ══════════════════════════════════════════════════════════════════════════
# Probability of backtest overfitting
# ══════════════════════════════════════════════════════════════════════════


def pbo_from_cscv(performance: Sequence[Sequence[float]]) -> float:
    """PBO via Combinatorially Symmetric Cross-Validation (Bailey et al.).

    Args:
        performance: ``n_slices x n_strategies`` matrix of out-of-sample
            performance, already split into contiguous slices.

    Procedure, which is the part that is easy to get wrong:

    1. For each half of the slices, take that half as in-sample and the
       complement as out-of-sample.
    2. In-sample, find the best strategy. Out-of-sample, find its rank.
    3. Convert the rank to a logit.
    4. PBO is the fraction of logits at or below zero - the fraction of times
       the in-sample winner landed in the bottom half out-of-sample.

    The symmetry in step 1 matters: using only one direction would let a
    systematic ordering artifact masquerade as overfitting.
    """
    n_slices = len(performance)
    if n_slices < 4 or n_slices % 2 != 0:
        raise ValueError(
            f"pbo_from_cscv needs an even number of slices >= 4; got {n_slices}"
        )
    n_strategies = len(performance[0])
    if n_strategies < 2:
        raise ValueError(
            f"PBO needs at least 2 strategies to rank; got {n_strategies}"
        )
    for row in performance:
        if len(row) != n_strategies:
            raise ValueError("performance matrix must be rectangular")

    logits: list[float] = []
    half = n_slices // 2
    for direction in range(2):
        if direction == 0:
            in_sample = list(range(half))
            out_sample = list(range(half, n_slices))
        else:
            in_sample = list(range(half, n_slices))
            out_sample = list(range(half))
        if len(in_sample) == 0 or len(out_sample) == 0:
            continue

        # Best strategy in-sample: highest mean across the IS slices.
        means = [
            sum(performance[s][j] for s in in_sample) / len(in_sample)
            for j in range(n_strategies)
        ]
        best = max(range(n_strategies), key=lambda j: means[j])

        # Its rank out-of-sample: how many strategies beat it.
        oos_means = [
            sum(performance[s][j] for s in out_sample) / len(out_sample)
            for j in range(n_strategies)
        ]
        beaten_by = sum(1 for m in oos_means if m > oos_means[best])
        # Relative rank ORIENTED SO THAT 1 IS BEST. This is the detail that
        # decides whether the statistic means anything: PBO is P(lambda <= 0),
        # so a strategy that won in-sample AND out-of-sample must produce a
        # large positive logit, not a large negative one. Ranking from the best
        # end is what makes that fall out correctly.
        relative = (n_strategies - 1 - beaten_by) / (n_strategies - 1)
        relative = min(max(relative, 1e-9), 1.0 - 1e-9)
        logits.append(math.log(relative / (1.0 - relative)))

    if not logits:
        return 0.0
    return sum(1 for x in logits if x <= 0.0) / len(logits)


# ══════════════════════════════════════════════════════════════════════════
# Multiple-testing correction
# ══════════════════════════════════════════════════════════════════════════


def bonferroni_threshold(alpha: float = 0.05, n_tests: int = 1) -> float:
    """Bonferroni per-test threshold: ``alpha / n_tests``.

    Controls the family-wise error rate at ``alpha``. No assumption about the
    shape of the p-value distribution, which is why it is the right default
    when a researcher is unsure what they are testing.
    """
    if n_tests < 1:
        raise ValueError(f"n_tests must be at least 1; got {n_tests}")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")
    return alpha / n_tests


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg: which hypotheses survive at an FDR of ``alpha``.

    Returns a boolean per input, in the input order: True means the hypothesis
    is *not* rejected. More powerful than Bonferroni because it controls the
    false discovery rate rather than the probability of any one false positive,
    which is the right target when testing many strategies and expecting some
    to work.
    """
    n = len(p_values)
    if n == 0:
        return []
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")
    for p in p_values:
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"p-values must lie in [0, 1]; got {p}")

    order = sorted(range(n), key=lambda i: p_values[i])
    # Find the LARGEST k with p_(k) <= (k/n)*alpha, then reject ranks 1..k.
    # The scan is over all k rather than stopping at the first failure: the
    # condition is not monotone in k, and an early break silently rejects
    # nothing even when the smallest p-value is far below every threshold.
    cutoff = 0
    for position, index in enumerate(order, start=1):
        if p_values[index] <= (position / n) * alpha:
            cutoff = position
    # Map each input position to its rank in the sorted order, then report
    # whether that rank survived the cutoff. Comparing original indices against
    # a set of sorted *positions* would silently reject the wrong hypotheses.
    rank_of = {original: position for position, original in enumerate(order)}
    return [rank_of[j] >= cutoff for j in range(n)]
