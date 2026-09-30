"""Typed factor definitions and deterministic factor computation (goal G060).

A factor is the smallest unit of the quant factory that can be wrong: a named
transformation of prices with a declared warmup and declared inputs. Two
disciplines keep factors honest, and both are enforced here rather than
documented:

*Warmup is a refusal, not a smaller window.* A factor cannot emit inside its
own warmup, and a gap bar poisons every window containing it — no
interpolation, because an interpolated bar is a fabricated observation wearing
a real timestamp. ``None`` marks every position the factor cannot justify,
and the positions it can justify carry ``available_at`` from the bar they
were known at.

*Definitions are immutable.* Re-registering an id+version with different
content is refused; a changed factor is a new version. A backtest pinned to
``momentum:v3`` must compute what v3 computed, or the pin is decoration.

Effective warmup is the max of the declared warmup and the intrinsic need
(momentum over n needs n+1 bars). The declared value may only raise the bar,
never lower it: a definition that claimed a shorter warmup than its own
arithmetic requires would be certifying its own inadequacy.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "FactorDefinition",
    "FactorRegistry",
    "FactorValue",
    "compute_factor",
    "effective_warmup",
]

#: Transforms this fabric computes. Window-local statistics with closed-form
#: arithmetic; anything model-shaped belongs in the model registry, not here.
SUPPORTED_FACTORS: tuple[str, ...] = ("momentum", "zscore", "realized_vol")


class FactorDefinition(BaseModel):
    """What a factor is, frozen at registration."""

    model_config = {"frozen": True}

    factor_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    family: str = Field(..., min_length=1, description="momentum | mean_reversion | volatility")
    description: str = Field(..., min_length=1)
    inputs: tuple[str, ...] = Field(
        default=("close",), description="Named series this factor reads; PIT requirements"
    )
    warmup_bars: int = Field(default=1, ge=1)
    lookback: int = Field(default=20, ge=1, description="Intrinsic window n")
    formula_ref: str = Field(..., min_length=1, description="The arithmetic, in words")
    code_hash: str = Field(default="", description="Digest of the implementation pinned")

    @property
    def ref(self) -> str:
        return f"{self.factor_id}:{self.version}"


class FactorValue(BaseModel):
    """One computed factor value, stamped with when it became knowable."""

    model_config = {"frozen": True}

    factor_id: str
    version: str
    index: int = Field(ge=0)
    available_at: datetime
    value: float

    def content_key(self) -> str:
        payload = f"{self.factor_id}:{self.version}:{self.index}:{self.value!r}"
        return hashlib.sha256(payload.encode()).hexdigest()


def effective_warmup(definition: FactorDefinition) -> int:
    """Bars required before the first emission.

    The intrinsic need (lookback + 1: n bars of context plus the bar being
    scored) is a floor the declaration cannot go under. A definition may
    demand more — extra burn-in for a noisier estimator — never less.
    """
    return max(definition.warmup_bars, definition.lookback + 1)


def _window(values: Sequence[float | None], stop: int, length: int) -> list[float] | None:
    """The ``length`` closes ending at ``stop`` (exclusive), or ``None`` when
    any is missing or the history is short. A gap poisons the whole window:
    windows are never interpolated, because interpolation fabricates the very
    prices the factor claims to summarise."""
    if stop < length:
        return None
    segment = list(values[stop - length : stop])
    if any(v is None for v in segment):
        return None
    return [float(v) for v in segment if v is not None]


def compute_factor(
    definition: FactorDefinition,
    closes: Sequence[float | None],
    stamps: Sequence[datetime],
) -> list[FactorValue | None]:
    """Compute the factor over a close series with parallel timestamps.

    Returns one entry per bar: a value past warmup over complete windows,
    ``None`` everywhere else. Deterministic given inputs — same series, same
    values, bit-for-bit for the integer-safe paths.
    """
    prices = list(closes)
    times = list(stamps)
    if len(prices) != len(times):
        raise ValueError(
            f"{len(prices)} closes but {len(times)} timestamps: a factor over a "
            "misaligned join locates values in the wrong time"
        )
    if definition.family not in {"momentum", "mean_reversion", "volatility"}:
        raise ValueError(
            f"family {definition.family!r} is not served by this fabric; "
            "known: momentum, mean_reversion, volatility"
        )
    needed = effective_warmup(definition)
    out: list[FactorValue | None] = []
    for i in range(len(prices)):
        if i + 1 < needed:
            out.append(None)
            continue
        window = _window(prices, i + 1, definition.lookback + 1)
        if window is None:
            out.append(None)
            continue
        value: float | None
        if definition.family == "momentum":
            base = window[0]
            if base == 0.0:
                out.append(None)
                continue
            value = window[-1] / base - 1.0
        elif definition.family == "mean_reversion":
            context = window[:-1]
            mean = sum(context) / len(context)
            variance = sum((v - mean) ** 2 for v in context) / (len(context) - 1)
            if variance <= 0.0:
                # No dispersion, no deviation: a z-score against a flat
                # context is undefined, and emitting 0.0 would dress "cannot
                # measure" as "perfectly average".
                out.append(None)
                continue
            value = (window[-1] - mean) / math.sqrt(variance)
        else:
            # strict=False: the pairing is intentionally offset by one
            # (consecutive returns), so the lengths differ by design.
            returns = [
                later / earlier - 1.0
                for earlier, later in zip(window, window[1:], strict=False)
                if earlier != 0.0
            ]
            if len(returns) != definition.lookback:
                out.append(None)
                continue
            mean = sum(returns) / len(returns)
            variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
            value = math.sqrt(max(0.0, variance))
        out.append(
            FactorValue(
                factor_id=definition.factor_id,
                version=definition.version,
                index=i,
                available_at=times[i],
                value=value,
            )
        )
    return out


class FactorRegistry:
    """Typed factor definitions. Computation lives in :func:`compute_factor`;
    this registry owns identity, immutability, and lookup — never arithmetic."""

    def __init__(self) -> None:
        self._definitions: dict[str, FactorDefinition] = {}

    def register(self, definition: FactorDefinition) -> FactorDefinition:
        """Store a definition. Same id+version with different content is
        refused: a changed factor is a new version, because a backtest pinned
        to an id must compute what that id computed."""
        existing = self._definitions.get(definition.ref)
        if existing is not None:
            if existing == definition:
                return existing
            raise ValueError(
                f"factor {definition.ref} already registered with different content. "
                "Register a new version: redefining a pinned factor rewrites history."
            )
        self._definitions[definition.ref] = definition
        return definition

    def get(self, factor_id: str, version: str) -> FactorDefinition:
        key = f"{factor_id}:{version}"
        definition = self._definitions.get(key)
        if definition is None:
            raise KeyError(f"factor not found: {key!r}")
        return definition

    def registered(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def compute(
        self,
        factor_id: str,
        version: str,
        closes: Sequence[float | None],
        stamps: Sequence[datetime],
    ) -> list[FactorValue | None]:
        """Compute a registered factor. Unknown ids fail here, not deep in
        the arithmetic with a confusing error."""
        return compute_factor(self.get(factor_id, version), closes, stamps)

    def as_dict(self) -> dict[str, Any]:
        return {
            ref: definition.model_dump(mode="json") for ref, definition in self._definitions.items()
        }
