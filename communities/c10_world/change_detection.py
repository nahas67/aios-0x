"""Real change detection for regime intelligence (goals G100/G110).

The 88-line EMA engine in ``regime_engine.py`` labels every bar but detects
nothing: a slow drift and a sudden break produce the same slope readout, and a
label carries no statement of *when* the evidence became knowable. This module
replaces labelling with detection, in two complementary forms:

online CUSUM (Page, 1954)
    A two-sided cumulative-sum test over standardised residuals. The baseline
    mean and dispersion are frozen from an explicit burn-in window, and no
    alarm may fire inside that window — an alarm before calibration is a
    false-positive flood wearing a detector's clothes. After each alarm the
    cumulative sums reset, which imposes a refractory period by construction.

offline segmentation (Bai-Perron style)
    Dynamic programming over prefix sums minimising ``total SSE + penalty``
    per break, with the per-break penalty defaulting to a BIC-style
    ``variance * log(n)`` cost. Retrospective: every break it reports was
    knowable only at the last bar of the sample, and its ``available_at``
    says so rather than backdating the discovery to the break.

Every output carries provenance. A :class:`ChangePoint` records the estimated
break ``index``, the bar where the evidence became knowable (``detected_at`` /
``available_at``), the ``delay_bars`` between them, and a ``confidence`` in
``[0, 1]``. :meth:`ChangePoint.to_feature_observations` converts a detection
into ``kernel.playbook.FeatureObservation`` values, so a regime condition can
consume detections as features with ``available_at`` rather than as bare
labels — a bare label is the look-ahead G120 was built to refuse.

Deterministic given inputs: no randomness, no wall-clock reads, no iteration
order dependence. Standard library plus pydantic only.

Enforced by tests/test_change_detection.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas.observations import FeatureObservation

__all__ = [
    "CUSUMConfig",
    "ChangePoint",
    "OnlineCUSUM",
    "RegimeFeed",
    "segment_series",
    "stable_bars",
]


# ══════════════════════════════════════════════════════════════════════════
# Outputs: detections with provenance, never bare labels
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ChangePoint:
    """One detected break, with when it became knowable.

    ``index`` is the estimated location of the break; ``detected_at`` is the
    bar whose arrival made the evidence sufficient, and ``available_at`` is
    that bar's timestamp. ``delay_bars`` is always ``detected_at - index``,
    so a consumer can bound staleness without re-deriving it. ``confidence``
    is ``g / (g + h)`` online (0.5 exactly at the threshold, approaching 1 on
    large exceedance) and ``d / (1 + d)`` of the standardised segment contrast
    offline (0.5 at a one-sigma contrast).
    """

    index: int
    detected_at: int
    available_at: datetime
    delay_bars: int
    confidence: float
    direction: Literal["up", "down"]
    before_mean: float
    after_mean: float

    def to_feature_observations(self, name: str) -> tuple[FeatureObservation, ...]:
        """Express this detection as point-in-time features.

        Three numeric features — confidence, delay, and signed direction —
        each stamped with this detection's ``available_at``, so a
        ``RegimeCondition`` bound over them is arithmetic over knowable
        values rather than a lookup of a label computed from the future.
        """
        if not name:
            raise ValueError("a feature prefix must be non-empty; an unnamed feature is un auditable")
        return (
            FeatureObservation(
                name=f"{name}_confidence", value=self.confidence, available_at=self.available_at
            ),
            FeatureObservation(
                name=f"{name}_delay_bars",
                value=float(self.delay_bars),
                available_at=self.available_at,
            ),
            FeatureObservation(
                name=f"{name}_direction",
                value=1.0 if self.direction == "up" else -1.0,
                available_at=self.available_at,
            ),
        )


# ══════════════════════════════════════════════════════════════════════════
# Input validation: garbage in is silent corruption out
# ══════════════════════════════════════════════════════════════════════════


def _check_series(values: Sequence[float], stamps: Sequence[datetime]) -> int:
    """Validate a series, returning its length.

    Refuses empty input, length mismatch, non-finite values (a NaN would
    silently poison every cumulative sum downstream), and timestamps that run
    backwards (a break located against unordered time is mislocated by
    definition).
    """
    n = len(values)
    if n == 0:
        raise ValueError("a series with no observations has no breaks to find")
    if len(stamps) != n:
        raise ValueError(
            f"{n} values but {len(stamps)} timestamps: every value needs its as-of time, "
            "because a detection without one is a bare label"
        )
    for i, value in enumerate(values):
        if not math.isfinite(value):
            raise ValueError(f"value at position {i} is {value!r}: only finite values are detectable")
    for i in range(1, n):
        if stamps[i] < stamps[i - 1]:
            raise ValueError(
                f"timestamps run backwards at position {i}: change locations are meaningless "
                "against unordered time"
            )
    return n


# ══════════════════════════════════════════════════════════════════════════
# Online CUSUM
# ══════════════════════════════════════════════════════════════════════════


class CUSUMConfig(BaseModel):
    """Tuning for the online CUSUM. All fields are standardised units.

    ``burn_in`` bars calibrate the baseline; no alarm may fire inside them.
    ``drift`` (k) is the reference value: sustained shifts smaller than k
    standard deviations are absorbed rather than accumulated. ``threshold``
    (h) is the alarm boundary on the cumulative sum. Defaults k=0.5, h=5.0
    are the textbook pairing for a ~1-sigma shift (Page, 1954; Hawkins and
    Olwell, 1998): a one-sigma sustained shift alarms in about ten bars,
    while a five-sigma run under the null is a rare event.
    """

    model_config = {"frozen": True}

    burn_in: int = Field(default=30, ge=1)
    drift: float = Field(default=0.5, ge=0.0)
    threshold: float = Field(default=5.0, gt=0.0)


class OnlineCUSUM:
    """Two-sided CUSUM over standardised residuals with an explicit burn-in.

    The baseline mean and standard deviation are estimated once from the
    first ``burn_in`` observations and then frozen: a baseline that tracks
    the series would absorb the very break it is meant to catch. Bars before
    the burn-in completes update the baseline accumulators only and can never
    alarm, which is what makes the false-positive flood structurally
    impossible rather than merely unlikely.
    """

    def __init__(self, config: CUSUMConfig) -> None:
        self._config = config
        self._burn: list[float] = []
        self._mean = 0.0
        self._sd = 1.0
        self._gpos = 0.0
        self._gneg = 0.0
        self._last_zero = 0
        self._run_sum = 0.0
        self._run_n = 0
        self._n = 0
        self._last_stamp: datetime | None = None

    @property
    def config(self) -> CUSUMConfig:
        return self._config

    @property
    def n_observations(self) -> int:
        return self._n

    @property
    def baseline(self) -> tuple[float, float] | None:
        """The frozen (mean, sd), or ``None`` while still inside burn-in."""
        if self._n < self._config.burn_in:
            return None
        return (self._mean, self._sd)

    def reset(self) -> None:
        """Return to a fresh state with the same config. Deterministic."""
        self._burn = []
        self._mean = 0.0
        self._sd = 1.0
        self._gpos = 0.0
        self._gneg = 0.0
        self._last_zero = 0
        self._run_sum = 0.0
        self._run_n = 0
        self._n = 0
        self._last_stamp = None

    def update(self, value: float, stamp: datetime) -> ChangePoint | None:
        """Feed one bar; return an alarm, or ``None`` when nothing fired."""
        if not math.isfinite(value):
            raise ValueError(f"value {value!r} is not finite: it would poison the cumulative sums")
        if self._last_stamp is not None and stamp < self._last_stamp:
            raise ValueError("timestamps must be non-decreasing: a break against unordered time is mislocated")
        self._last_stamp = stamp
        index = self._n
        self._n += 1

        if self._n <= self._config.burn_in:
            # Calibration only. Returning None here unconditionally is the
            # burn-in guarantee: no alarm inside the window, by construction
            # rather than by threshold luck.
            self._burn.append(value)
            if self._n == self._config.burn_in:
                self._freeze_baseline()
            return None

        assert self._sd > 0.0  # frozen with a positive floor; see _freeze_baseline
        standardised = (value - self._mean) / self._sd
        self._gpos = max(0.0, self._gpos + standardised - self._config.drift)
        self._gneg = max(0.0, self._gneg - standardised - self._config.drift)

        if self._gpos <= 0.0 and self._gneg <= 0.0:
            # Both sums at rest: the current run of evidence starts after here.
            self._last_zero = index
            self._run_sum = 0.0
            self._run_n = 0
            return None

        self._run_sum += value
        self._run_n += 1

        alarming = max(self._gpos, self._gneg)
        if alarming <= self._config.threshold:
            return None

        up = self._gpos >= self._gneg
        confidence = alarming / (alarming + self._config.threshold)
        point = ChangePoint(
            index=self._last_zero,
            detected_at=index,
            available_at=stamp,
            delay_bars=index - self._last_zero,
            confidence=confidence,
            direction="up" if up else "down",
            before_mean=self._mean,
            after_mean=self._run_sum / self._run_n,
        )
        # Reset imposes the refractory period: the next alarm needs a fresh
        # accumulation rather than inheriting this one's momentum.
        self._gpos = 0.0
        self._gneg = 0.0
        self._last_zero = index
        self._run_sum = 0.0
        self._run_n = 0
        return point

    def run(
        self, values: Sequence[float], stamps: Sequence[datetime]
    ) -> list[ChangePoint]:
        """Feed a whole series from a fresh state; return every alarm in order."""
        _check_series(values, stamps)
        self.reset()
        alarms: list[ChangePoint] = []
        for value, stamp in zip(values, stamps, strict=True):
            alarm = self.update(value, stamp)
            if alarm is not None:
                alarms.append(alarm)
        return alarms

    def _freeze_baseline(self) -> None:
        n = len(self._burn)
        mean = sum(self._burn) / n
        if n < 2:
            variance = 0.0
        else:
            variance = sum((v - mean) ** 2 for v in self._burn) / (n - 1)
        # A flat burn-in has zero dispersion; without a floor every later
        # tick is infinitely many standard deviations away. The floor keeps
        # the arithmetic defined, and the threshold still gates the alarm.
        self._mean = mean
        self._sd = math.sqrt(variance) if variance > 0.0 else 1e-9
        # No evidence accumulates during burn-in, so no run of evidence can
        # have started before it ended. Without this, the break estimate
        # would point at bar 0 — the sums never rested during calibration —
        # and every delay would be overstated by the whole burn-in length.
        self._last_zero = self._n - 1


# ══════════════════════════════════════════════════════════════════════════
# Offline segmentation, Bai-Perron style
# ══════════════════════════════════════════════════════════════════════════


def _segment_sse(prefix: list[float], prefix_sq: list[float], start: int, stop: int) -> float:
    """Sum of squared errors of ``values[start:stop]`` around its own mean, O(1)."""
    length = stop - start
    if length <= 0:
        return math.inf
    total = prefix[stop] - prefix[start]
    total_sq = prefix_sq[stop] - prefix_sq[start]
    sse = total_sq - (total * total) / length
    # Float rounding can push a constant segment infinitesimally negative;
    # an SSE below zero is arithmetic noise, not information.
    return max(0.0, sse)


def segment_series(
    values: Sequence[float],
    stamps: Sequence[datetime],
    *,
    max_breaks: int = 5,
    min_segment_len: int = 10,
    penalty: float | None = None,
) -> list[ChangePoint]:
    """Partition the series into constant-mean segments (Bai and Perron, 1998, 2003).

    Dynamic programming over prefix sums minimises
    ``total SSE + penalty * n_breaks``. The default penalty is the BIC-style
    ``variance * log(n)`` per break: a break must earn its keep against the
    cost of describing it, which is what stops noise from segmenting. Ties
    keep the earlier split and the smaller break count, so the output is
    deterministic given inputs.

    Retrospective honesty: every break reported was located with the full
    sample, so ``detected_at`` is the last bar and ``available_at`` is its
    timestamp. A break dated at its own location would claim knowledge the
    detector did not have when the break happened.

    Returns ``[]`` when the series cannot host a break (shorter than two
    minimum segments) or has no dispersion at all — a flat series has no
    break to find, and raising would dress a degenerate input as a failure.
    """
    n = _check_series(values, stamps)
    if max_breaks < 0:
        raise ValueError(f"max_breaks must be non-negative; got {max_breaks}")
    if min_segment_len < 2:
        raise ValueError(f"min_segment_len must be at least 2; got {min_segment_len}")
    if n < 2 * min_segment_len:
        return []

    prefix = [0.0] * (n + 1)
    prefix_sq = [0.0] * (n + 1)
    for i, value in enumerate(values):
        prefix[i + 1] = prefix[i] + value
        prefix_sq[i + 1] = prefix_sq[i] + value * value

    total_sse = _segment_sse(prefix, prefix_sq, 0, n)
    if total_sse <= 1e-9:
        return []
    if penalty is None:
        penalty = (total_sse / n) * math.log(n)
    if penalty < 0.0:
        raise ValueError(f"penalty must be non-negative; got {penalty}")

    inf = math.inf
    # best[k][i]: cheapest cost for the first i bars with exactly k breaks.
    best: list[list[float]] = [[inf] * (n + 1) for _ in range(max_breaks + 1)]
    prev: list[list[int]] = [[-1] * (n + 1) for _ in range(max_breaks + 1)]
    for i in range(min_segment_len, n + 1):
        best[0][i] = _segment_sse(prefix, prefix_sq, 0, i)
    for k in range(1, max_breaks + 1):
        for i in range((k + 1) * min_segment_len, n + 1):
            # Strict improvement keeps the earliest split on ties: the
            # argmin is then a function of the inputs alone.
            for j in range(k * min_segment_len, i - min_segment_len + 1):
                candidate = best[k - 1][j] + _segment_sse(prefix, prefix_sq, j, i)
                if candidate < best[k][i]:
                    best[k][i] = candidate
                    prev[k][i] = j

    n_breaks = 0
    best_cost = best[0][n]
    for k in range(1, max_breaks + 1):
        if best[k][n] is inf:
            continue
        if best[k][n] + penalty * k < best_cost:
            best_cost = best[k][n] + penalty * k
            n_breaks = k

    breaks: list[int] = []
    k, i = n_breaks, n
    while k > 0:
        j = prev[k][i]
        if j < 0:  # pragma: no cover - unreachable when best[k][n] is finite
            raise RuntimeError("backtracking failed: the argmin table disagrees with the cost table")
        breaks.append(j)
        i = j
        k -= 1
    breaks.sort()

    points: list[ChangePoint] = []
    bounds = [0, *breaks, n]
    for position, break_at in enumerate(breaks):
        left_start, right_stop = bounds[position], bounds[position + 2]
        left_n = break_at - left_start
        right_n = right_stop - break_at
        left_mean = (prefix[break_at] - prefix[left_start]) / left_n
        right_mean = (prefix[right_stop] - prefix[break_at]) / right_n
        left_sse = _segment_sse(prefix, prefix_sq, left_start, break_at)
        right_sse = _segment_sse(prefix, prefix_sq, break_at, right_stop)
        dof = left_n + right_n - 2
        pooled = math.sqrt((left_sse + right_sse) / dof) if dof > 0 else 0.0
        # Noiseless break, maximal evidence: constant segments on either side
        # mean the shift stands alone with nothing to confuse it. Returning 0
        # here (0/0 fallback) would score a perfect step below a noisy one —
        # exactly backwards. Infinite contrast maps to confidence 1 below.
        gap = abs(right_mean - left_mean)
        if pooled > 0.0:
            contrast = gap / pooled
        else:
            contrast = math.inf if gap > 0.0 else 0.0
        points.append(
            ChangePoint(
                index=break_at,
                detected_at=n - 1,
                available_at=stamps[n - 1],
                delay_bars=(n - 1) - break_at,
                confidence=1.0 if math.isinf(contrast) else contrast / (1.0 + contrast),
                direction="up" if right_mean >= left_mean else "down",
                before_mean=left_mean,
                after_mean=right_mean,
            )
        )
    return points


def stable_bars(breaks: Sequence[ChangePoint], current_index: int) -> int:
    """Bars since the most recent break at or before ``current_index``.

    With no prior break the whole history is stable, so this returns
    ``current_index + 1`` rather than a sentinel: a sentinel would force
    every caller to invent the same convention, and callers inventing
    conventions is how "stable" comes to mean three different things.
    """
    if current_index < 0:
        raise ValueError(f"current_index must be non-negative; got {current_index}")
    prior = [point.index for point in breaks if point.index <= current_index]
    if not prior:
        return current_index + 1
    return current_index - max(prior)


class RegimeFeed:
    """Live regime features from a CUSUM detector (goal G120).

    The slow path's answer to "what regime is it": consumes a value stream
    bar by bar and emits point-in-time feature observations whenever the
    detector fires, plus a stability reading on demand. The features carry
    ``available_at`` from the detecting bar, so a ``RegimeCondition`` bound
    over them is arithmetic over knowable values — and the router's own
    contamination check stays the backstop, not the feed's promise.

    One detector per stream: mixing streams in one CUSUM would locate breaks
    in a series that never existed. A feed that needs many streams holds many
    feeds.
    """

    def __init__(self, config: CUSUMConfig, *, name: str) -> None:
        if not name:
            raise ValueError("a feed needs a name; unnamed features are unauditable")
        self._detector = OnlineCUSUM(config)
        self._name = name
        self._breaks: list[ChangePoint] = []
        self._n = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def breaks(self) -> tuple[ChangePoint, ...]:
        return tuple(self._breaks)

    def update(self, value: float, stamp: datetime) -> tuple[FeatureObservation, ...]:
        """Feed one bar; return feature observations, empty when quiet.

        Silence is normal output, not an absence: most bars change nothing,
        and a feed that emitted constantly would be a label stream wearing
        feature clothes.
        """
        alarm = self._detector.update(value, stamp)
        self._n += 1
        if alarm is None:
            return ()
        self._breaks.append(alarm)
        return alarm.to_feature_observations(self._name)

    def stability(self, current_index: int) -> int:
        """Bars since the last detected break. The gate's regime input."""
        return stable_bars(self._breaks, current_index)

    def reset(self) -> None:
        """Return to a fresh detector state. History after a reset starts
        over — documented because a reset that silently kept the baseline
        would be a different detector wearing this one's name."""
        self._detector.reset()
        self._breaks = []
        self._n = 0
