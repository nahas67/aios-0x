"""Feature fabric: offline batch and online serving from one transform (G090).

The registry (``kernel.registries.FeatureRegistry``) versions feature
definitions, but versioning alone cannot catch the failure this module exists
to prevent: offline research computing one number while online serving quietly
computes another. When those two disagree, every backtest is a fiction about a
system that never traded.

So the split is structural. :class:`OfflineStore` recomputes features over
historical bars; :class:`OnlineStore` serves them incrementally bar by bar.
Both call :func:`transform_step` — the single implementation of each feature
transform — with the same arguments, so parity holds by construction rather
than by maintaining two implementations and hoping they agree.
:func:`check_offline_online_parity` then states the agreement as a checked
claim that records its own tolerance, because a parity claim without its
epsilon cannot be re-checked (see tests/test_feature_parity.py).

Two further disciplines. First, warmup is a named refusal
(:class:`WarmupRefusal`), never a silent NaN: an online store that has not
seen enough bars raises instead of serving a number it cannot justify, and the
offline store marks those positions ``None``. Second, online features carry
``available_at`` from the bar they were computed from (goal G030): a feature
that cannot say when it became knowable cannot back point-in-time research.

Standard library plus pydantic only. No I/O, no clock reads, no randomness:
``compute`` on the same inputs returns the same floats bit-for-bit.
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "EXACT_PARITY_TOLERANCE",
    "FLOAT_PARITY_TOLERANCE",
    "Bar",
    "CodeHashMismatch",
    "FeatureConfig",
    "FeatureTick",
    "OfflineResult",
    "OfflineStore",
    "OnlineSnapshot",
    "OnlineStore",
    "ParityReport",
    "WarmupRefusal",
    "check_offline_online_parity",
    "code_hash_for",
    "transform_step",
    "warmup_bars",
]

#: Tolerance for transforms whose arithmetic is exact on the fixture
#: (comparisons and addition/subtraction of integral values): the two paths
#: must agree bit-for-bit, so any nonzero difference is a defect.
EXACT_PARITY_TOLERANCE: float = 0.0

#: Tolerance for transforms that divide or multiply in floating point
#: (means, exponential smoothing). Both paths execute the same operations in
#: the same order, so in practice the difference is zero; the epsilon exists
#: so the claim stays checkable if an operation ever reorders.
FLOAT_PARITY_TOLERANCE: float = 1e-12

#: Bumped whenever the arithmetic in :func:`transform_step` changes. Old
#: recomputation hashes then refuse instead of silently reproducing numbers
#: the current code would not produce.
TRANSFORM_LOGIC_VERSION: str = "feature-logic.v1"

#: Every transform this fabric serves. Window-local statistics plus one
#: stateful smoother; anything fancier belongs in a registered research
#: module, not in the serving path.
SUPPORTED_FEATURES: tuple[str, ...] = (
    "sma",
    "momentum",
    "rolling_sum",
    "rolling_max",
    "rolling_min",
    "ema",
)


class WarmupRefusal(ValueError):
    """The online store has not seen enough bars to emit this feature.

    Raised instead of serving NaN. A NaN in a serving path becomes a row in a
    dataset, and a row in a dataset becomes a backtest input; the refusal
    stops that chain at the source by naming what is missing.
    """

    def __init__(self, feature: str, period: int, needed: int, seen: int) -> None:
        self.feature: str = feature
        self.period: int = period
        self.needed: int = needed
        self.seen: int = seen
        super().__init__(
            f"feature {feature!r} (period {period}) needs {needed} bars, "
            f"only {seen} seen: warmup refusal, not a value"
        )


class CodeHashMismatch(ValueError):
    """A recomputation was pinned to code this store would not run."""

    def __init__(self, expected: str, got: str) -> None:
        self.expected: str = expected
        self.got: str = got
        super().__init__(
            f"recomputation pinned to code {got!r} but this store runs "
            f"{expected!r}: refusing to reproduce numbers the pinned code "
            "may not have produced"
        )


class FeatureVersionLike(Protocol):
    """The only shape of ``FeatureRegistry`` this module depends on.

    Duck-typed on purpose: the fabric reads the registered computation hash
    for audit linkage and nothing else, so a sibling lane may evolve the
    registry freely without breaking this module.
    """

    computation_hash: str


class FeatureConfig(BaseModel):
    """Which transform to run and over what window."""

    feature: str = Field(description="One of SUPPORTED_FEATURES")
    period: int = Field(gt=0, description="Lookback length in bars")

    @field_validator("feature")
    @classmethod
    def _known_feature(cls, value: str) -> str:
        if value not in SUPPORTED_FEATURES:
            raise ValueError(
                f"unknown feature {value!r}; supported: {list(SUPPORTED_FEATURES)}"
            )
        return value


class Bar(BaseModel):
    """One historical bar as the fabric sees it.

    ``available_at`` is required, not optional: it is the point-in-time join
    key (goal G030), and a bar that cannot say when it became knowable cannot
    back research. The fabric carries it onto every emitted feature tick.
    """

    close: float = Field(description="Closing price of the bar")
    available_at: datetime = Field(description="When this bar became knowable")
    event_time: datetime | None = Field(
        default=None, description="When the bar's interval closed, if known"
    )
    sequence: int = Field(default=0, ge=0)

    @field_validator("close")
    @classmethod
    def _finite_close(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"bar close must be finite; got {value!r}")
        return value


class FeatureTick(BaseModel):
    """One served feature value, pinned to the bar that produced it."""

    feature_id: str
    version: str
    index: int = Field(ge=0, description="Position of the source bar in the stream")
    available_at: datetime = Field(description="Carried from the source bar")
    value: float

    @field_validator("value")
    @classmethod
    def _finite_value(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("a served feature must be finite; NaN is refused, not served")
        return value


class OfflineResult(BaseModel):
    """A full batch recomputation, with its own reproducibility receipt.

    ``values`` is parallel to ``available_at``: positions inside the warmup
    window hold ``None`` (explicit absence), never NaN. ``code_hash`` pins the
    transform logic that produced the values; ``registry_computation_hash``
    links back to the ``FeatureRegistry`` entry when the caller passed one.
    """

    feature_id: str
    version: str
    config: FeatureConfig
    code_hash: str
    values: list[float | None]
    available_at: list[datetime]
    registry_computation_hash: str | None = Field(default=None)

    @field_validator("values")
    @classmethod
    def _no_silent_nan(cls, rows: list[float | None]) -> list[float | None]:
        for entry in rows:
            if entry is not None and (
                entry != entry or entry in (float("inf"), float("-inf"))
            ):
                raise ValueError("offline results hold floats or None; NaN is refused")
        return rows

    def emitted(self) -> list[tuple[int, float]]:
        """(index, value) pairs past the warmup window, in order."""
        return [(i, v) for i, v in enumerate(self.values) if v is not None]


class OnlineSnapshot(BaseModel):
    """Restartable serving state: everything needed to resume identically."""

    feature_id: str
    version: str
    config: FeatureConfig
    closes: list[float] = Field(description="Trailing window, oldest first")
    available_at: list[datetime] = Field(description="Knowable times, parallel to closes")
    ema_state: float | None = Field(default=None)
    n_seen: int = Field(ge=0)


class ParityReport(BaseModel):
    """The offline/online agreement as a checkable claim.

    ``tolerance`` is part of the claim: without the epsilon the numbers were
    compared under, ``passed`` cannot be re-checked and the report is prose.
    """

    feature_id: str
    version: str
    feature: str
    period: int
    code_hash: str
    n_bars: int
    n_compared: int
    max_abs_diff: float = Field(ge=0.0)
    tolerance: float = Field(ge=0.0)
    passed: bool
    offline_emitted: int
    online_emitted: int


def warmup_bars(feature: str, period: int) -> int:
    """Bars required before the first emission. Momentum compares against the
    bar ``period`` steps back, so it needs one more bar than the rest."""
    if feature not in SUPPORTED_FEATURES:
        raise ValueError(f"unknown feature {feature!r}")
    if period <= 0:
        raise ValueError(f"period must be positive; got {period}")
    if feature == "momentum":
        return period + 1
    return period


def code_hash_for(config: FeatureConfig) -> str:
    """Canonical identity of the transform logic for a config.

    Pinned into every result and checked on recomputation: reproducing numbers
    under a hash the current logic did not earn would be a forged receipt.
    """
    canonical = f"{TRANSFORM_LOGIC_VERSION}:{config.feature}:{config.period}"
    return hashlib.sha256(canonical.encode()).hexdigest()


def transform_step(
    *,
    feature: str,
    window: tuple[float, ...],
    period: int,
    n_seen: int,
    ema_state: float | None,
) -> tuple[float | None, float | None]:
    """One shared feature-transform implementation; both stores call this.

    Args:
        feature: transform name from ``SUPPORTED_FEATURES``.
        window: trailing closes, oldest first (at most ``period + 1`` kept;
            only the tail is ever read).
        period: lookback length in bars.
        n_seen: total bars observed including the current one; warmup is
            decided on this, never on the truncated window length.
        ema_state: running EMA from the previous bar (``None`` before seeding).

    Returns:
        ``(value, new_ema_state)`` where ``value`` is ``None`` inside the
        warmup window. ``None`` is the only absence this function produces;
        it never returns NaN.
    """
    if feature not in SUPPORTED_FEATURES:
        raise ValueError(f"unknown feature {feature!r}")
    if period <= 0:
        raise ValueError(f"period must be positive; got {period}")
    if n_seen <= 0:
        raise ValueError(f"n_seen must be positive; got {n_seen}")
    needed = warmup_bars(feature, period)
    if n_seen < needed:
        return None, ema_state
    tail: tuple[float, ...] = window[-period:] if period > 0 else ()
    if feature == "sma":
        return sum(tail) / period, ema_state
    if feature == "rolling_sum":
        return sum(tail), ema_state
    if feature == "rolling_max":
        return max(tail), ema_state
    if feature == "rolling_min":
        return min(tail), ema_state
    if feature == "momentum":
        return window[-1] - window[-(period + 1)], ema_state
    # feature == "ema": Wilder-style exponential smoother seeded with the SMA
    # of the first period, matching the seeding the research path documents.
    # The recurrence runs through this same step on both paths, so the
    # smoothing history is identical bar-for-bar rather than approximately so.
    if n_seen == period:
        seed = sum(tail) / period
        return seed, seed
    if ema_state is None:  # pragma: no cover - unreachable via the stores
        raise ValueError("ema past warmup requires the running state")
    multiplier = 2.0 / (period + 1)
    updated = ema_state + (window[-1] - ema_state) * multiplier
    return updated, updated


class OfflineStore:
    """Batch feature computation over historical bars.

    Deterministic and total: full recomputation from (data, code-hash,
    config) via :meth:`recompute`, which refuses a hash the current logic
    did not earn instead of reproducing numbers under it.
    """

    def __init__(self, *, feature_id: str, version: str, config: FeatureConfig) -> None:
        if not feature_id:
            raise ValueError("feature_id must be non-empty")
        if not version:
            raise ValueError("version must be non-empty")
        self._feature_id = feature_id
        self._version = version
        self._config = config

    @property
    def code_hash(self) -> str:
        return code_hash_for(self._config)

    def compute(
        self,
        bars: Sequence[Bar],
        *,
        feature_version: FeatureVersionLike | None = None,
    ) -> OfflineResult:
        """Compute the feature over every bar; warmup positions hold ``None``.

        ``feature_version`` is accepted only for audit linkage — its
        ``computation_hash`` is recorded, never executed. The arithmetic is
        always :func:`transform_step`.
        """
        values: list[float | None] = []
        stamps: list[datetime] = []
        history: list[float] = []
        ema_state: float | None = None
        period = self._config.period
        for bar in bars:
            history.append(bar.close)
            stamps.append(bar.available_at)
            window = tuple(history[-(period + 1):])
            value, ema_state = transform_step(
                feature=self._config.feature,
                window=window,
                period=period,
                n_seen=len(history),
                ema_state=ema_state,
            )
            values.append(value)
        return OfflineResult(
            feature_id=self._feature_id,
            version=self._version,
            config=self._config,
            code_hash=self.code_hash,
            values=values,
            available_at=stamps,
            registry_computation_hash=(
                feature_version.computation_hash if feature_version is not None else None
            ),
        )

    def recompute(self, bars: Sequence[Bar], *, code_hash: str) -> OfflineResult:
        """Reproduce a result bit-for-bit from (data, code-hash, config).

        The hash check comes first: recomputing under a foreign hash and
        returning numbers anyway would certify a lineage that never ran.
        """
        if code_hash != self.code_hash:
            raise CodeHashMismatch(expected=self.code_hash, got=code_hash)
        return self.compute(bars)


class OnlineStore:
    """Incremental feature serving with the same arithmetic as the batch path.

    Each :meth:`update` feeds one bar through :func:`transform_step` with the
    running state, so the served sequence equals the offline column past
    warmup by construction. Inside warmup it raises :class:`WarmupRefusal`.
    State survives a restart via :meth:`snapshot` / :meth:`restore`.
    """

    def __init__(self, *, feature_id: str, version: str, config: FeatureConfig) -> None:
        if not feature_id:
            raise ValueError("feature_id must be non-empty")
        if not version:
            raise ValueError("version must be non-empty")
        self._feature_id = feature_id
        self._version = version
        self._config = config
        keep = config.period + 1
        self._closes: deque[float] = deque(maxlen=keep)
        self._stamps: deque[datetime] = deque(maxlen=keep)
        self._ema_state: float | None = None
        self._n_seen: int = 0
        self._last_available_at: datetime | None = None

    @property
    def n_seen(self) -> int:
        return self._n_seen

    @property
    def code_hash(self) -> str:
        return code_hash_for(self._config)

    def update(self, bar: Bar) -> FeatureTick:
        """Serve the feature for one bar, carrying its ``available_at``.

        Raises:
            WarmupRefusal: fewer than the required bars seen so far.
            ValueError: the bar's ``available_at`` moves backwards, which
                would serve a sequence whose knowable times are unordered.
        """
        if (
            self._last_available_at is not None
            and bar.available_at < self._last_available_at
        ):
            raise ValueError(
                f"bar available_at {bar.available_at.isoformat()} precedes "
                f"previously served {self._last_available_at.isoformat()}: "
                "serving out of knowable order would break point-in-time joins"
            )
        self._closes.append(bar.close)
        self._stamps.append(bar.available_at)
        self._last_available_at = bar.available_at
        self._n_seen += 1
        needed = warmup_bars(self._config.feature, self._config.period)
        value, self._ema_state = transform_step(
            feature=self._config.feature,
            window=tuple(self._closes),
            period=self._config.period,
            n_seen=self._n_seen,
            ema_state=self._ema_state,
        )
        if value is None:
            raise WarmupRefusal(
                self._config.feature, self._config.period, needed, self._n_seen
            )
        return FeatureTick(
            feature_id=self._feature_id,
            version=self._version,
            index=self._n_seen - 1,
            available_at=bar.available_at,
            value=value,
        )

    def snapshot(self) -> OnlineSnapshot:
        """Capture restartable serving state (JSON-serializable)."""
        return OnlineSnapshot(
            feature_id=self._feature_id,
            version=self._version,
            config=self._config,
            closes=list(self._closes),
            available_at=list(self._stamps),
            ema_state=self._ema_state,
            n_seen=self._n_seen,
        )

    @classmethod
    def restore(cls, snapshot: OnlineSnapshot) -> OnlineStore:
        """Resume serving from a snapshot with identical subsequent outputs."""
        store = cls(
            feature_id=snapshot.feature_id,
            version=snapshot.version,
            config=snapshot.config,
        )
        store._closes.extend(snapshot.closes)
        store._stamps.extend(snapshot.available_at)
        store._ema_state = snapshot.ema_state
        store._n_seen = snapshot.n_seen
        store._last_available_at = (
            snapshot.available_at[-1] if snapshot.available_at else None
        )
        return store


def check_offline_online_parity(
    bars: Sequence[Bar],
    *,
    feature_id: str,
    version: str,
    config: FeatureConfig,
    tolerance: float,
) -> ParityReport:
    """Compare batch and serving paths over one shared fixture.

    Streams every bar through a fresh :class:`OnlineStore`, aligns served
    ticks with the :class:`OfflineStore` column by index, and reports the
    maximum absolute difference alongside the ``tolerance`` the comparison ran
    under. The tolerance is recorded in the report because a parity claim
    without its epsilon cannot be re-checked.
    """
    if tolerance < 0.0:
        raise ValueError(f"tolerance must be non-negative; got {tolerance}")
    offline = OfflineStore(
        feature_id=feature_id, version=version, config=config
    ).compute(bars)
    online = OnlineStore(feature_id=feature_id, version=version, config=config)
    ticks: list[FeatureTick] = []
    for bar in bars:
        try:
            ticks.append(online.update(bar))
        except WarmupRefusal:
            continue
    emitted = offline.emitted()
    if len(ticks) != len(emitted):
        return ParityReport(
            feature_id=feature_id,
            version=version,
            feature=config.feature,
            period=config.period,
            code_hash=offline.code_hash,
            n_bars=len(bars),
            n_compared=min(len(ticks), len(emitted)),
            max_abs_diff=float("inf"),
            tolerance=tolerance,
            passed=False,
            offline_emitted=len(emitted),
            online_emitted=len(ticks),
        )
    worst = 0.0
    for tick, (index, expected) in zip(ticks, emitted, strict=True):
        if tick.index != index or tick.available_at != offline.available_at[index]:
            return ParityReport(
                feature_id=feature_id,
                version=version,
                feature=config.feature,
                period=config.period,
                code_hash=offline.code_hash,
                n_bars=len(bars),
                n_compared=0,
                max_abs_diff=float("inf"),
                tolerance=tolerance,
                passed=False,
                offline_emitted=len(emitted),
                online_emitted=len(ticks),
            )
        worst = max(worst, abs(tick.value - expected))
    return ParityReport(
        feature_id=feature_id,
        version=version,
        feature=config.feature,
        period=config.period,
        code_hash=offline.code_hash,
        n_bars=len(bars),
        n_compared=len(ticks),
        max_abs_diff=worst,
        tolerance=tolerance,
        passed=worst <= tolerance,
        offline_emitted=len(emitted),
        online_emitted=len(ticks),
    )
