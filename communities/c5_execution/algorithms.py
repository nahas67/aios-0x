"""Community 5: deterministic execution schedulers — TWAP, VWAP, POV (goal G150).

Where this sits: the schedulers below *propose* child quantities. They place no
orders, call no venue, read no clock, and draw no randomness: the same inputs
produce the same schedule every time. Execution stays on the existing governed
path — each child quantity is submitted through ``BaseExecutionAdapter.govern``
(see ``communities/c5_execution/adapters.py``), which obtains a per-call
Guardian verdict before anything reaches a venue (see
``tests/test_execution_governance.py``). A schedule therefore cannot widen what
governance allows: every child is limited to the authorized maximum up front,
and any schedule that cannot fit inside that maximum is refused rather than
reshaped past it (see ``tests/test_execution_algorithms.py``).

Arithmetic discipline (integer shares, whole lots):

- Quantities are integer shares (or contracts). ``lot_size`` is a positive
  integer; every child is a whole multiple of it.
- Children sum *exactly* to the requested total. Leftover whole lots from the
  apportionment are assigned one per bar to explicitly named bars
  (``remainder_bars``); nothing is rounded to nearest, created, or dropped.
- A total that is not a whole number of lots is refused: sub-lot dust has no
  representable home, and flooring the total would silently lose quantity.
- Per-bar limits are floors (``max_participation * volume``,
  ``max_notional / price``, ``max_quantity``), never ceilings: a child may
  under-fill a limit, never breach one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "DEGRADATION_EMPTY_PROFILE",
    "AlgorithmName",
    "ExecutionSchedule",
    "InfeasibleScheduleError",
    "InvalidScheduleInputError",
    "ScheduleError",
    "pov_schedule",
    "twap_schedule",
    "vwap_schedule",
]

#: Algorithm labels carried on a schedule.
AlgorithmName = Literal["TWAP", "VWAP", "POV"]

#: Named reason recorded when VWAP falls back to an even split.
DEGRADATION_EMPTY_PROFILE = "empty_volume_profile"


class ScheduleError(ValueError):
    """Base class: a schedule could not be built honestly."""


class InvalidScheduleInputError(ScheduleError):
    """Caller error: non-positive totals, empty bar grids, bad lots or caps."""


class InfeasibleScheduleError(ScheduleError):
    """Honest refusal: sum-exactness and the authorized maximum cannot both hold.

    Raised instead of emitting a schedule that breaches a cap or invents
    volume. The caller widens the window, lowers the total, or relaxes the cap
    through governance — the scheduler never relaxes it unilaterally.
    """


class ExecutionSchedule(BaseModel):
    """An immutable per-bar child-quantity schedule (proposed, not executed).

    ``children[i]`` is the quantity for bar ``i``. The model validator enforces
    the load-bearing properties at the type boundary, so even a hand-built
    schedule cannot create or lose quantity (see
    ``tests/test_execution_algorithms.py``).
    """

    model_config = ConfigDict(frozen=True)

    algorithm: AlgorithmName = Field(description="Scheduler that produced this schedule")
    total_quantity: int = Field(gt=0, description="Requested total, in integer shares")
    children: tuple[int, ...] = Field(
        min_length=1, description="Per-bar child quantities, in integer shares"
    )
    lot_size: int = Field(ge=1, description="Every child is a whole multiple of this")
    remainder_bars: tuple[int, ...] = Field(
        default=(),
        description="Named bars that received one extra lot above the floor",
    )
    degraded: bool = Field(default=False, description="True when VWAP fell back to TWAP")
    degradation_reason: str = Field(
        default="", description="Machine-readable reason when degraded is True"
    )
    notes: tuple[str, ...] = Field(default=(), description="Human-readable allocation notes")

    @model_validator(mode="after")
    def _check_schedule_exact(self) -> ExecutionSchedule:
        """Refuse any schedule whose children do not add up to the total."""
        for child in self.children:
            if isinstance(child, bool) or not isinstance(child, int) or child < 0:
                raise ValueError("schedule children must be non-negative integers")
            if child % self.lot_size != 0:
                raise ValueError("schedule children must be whole multiples of lot_size")
        if sum(self.children) != self.total_quantity:
            raise ValueError(
                f"schedule children sum to {sum(self.children)} "
                f"but total_quantity is {self.total_quantity}"
            )
        return self

    @property
    def allocated(self) -> int:
        """Total allocated across bars; always equals ``total_quantity``."""
        return sum(self.children)

    @property
    def num_bars(self) -> int:
        """Number of bars (children) in the schedule."""
        return len(self.children)

    def quantities(self) -> list[int]:
        """Per-bar child quantities as a plain list."""
        return list(self.children)


# ─────────────────────────────────────────────────────────────────────────────
# Shared validation and arithmetic
# ─────────────────────────────────────────────────────────────────────────────


def _validate_lot_inputs(total_quantity: int, lot_size: int) -> int:
    """Check the total/lot pair; return the total expressed in whole lots."""
    if isinstance(total_quantity, bool) or not isinstance(total_quantity, int):
        raise InvalidScheduleInputError(
            f"total_quantity must be an integer number of shares, got {total_quantity!r}"
        )
    if total_quantity <= 0:
        raise InvalidScheduleInputError(
            f"total_quantity must be positive, got {total_quantity}"
        )
    if isinstance(lot_size, bool) or not isinstance(lot_size, int):
        raise InvalidScheduleInputError(f"lot_size must be a positive integer, got {lot_size!r}")
    if lot_size <= 0:
        raise InvalidScheduleInputError(f"lot_size must be a positive integer, got {lot_size}")
    if total_quantity % lot_size != 0:
        raise InvalidScheduleInputError(
            f"total_quantity {total_quantity} is not a whole number of "
            f"lots of {lot_size}; sub-lot dust has no representable home, "
            "so the total is refused rather than floored"
        )
    return total_quantity // lot_size


def _validate_bar_count(num_bars: int) -> int:
    if isinstance(num_bars, bool) or not isinstance(num_bars, int):
        raise InvalidScheduleInputError(f"num_bars must be a positive integer, got {num_bars!r}")
    if num_bars < 1:
        raise InvalidScheduleInputError(f"num_bars must be at least 1, got {num_bars}")
    return num_bars


def _validate_volumes(values: Sequence[int], *, allow_empty: bool, what: str) -> list[int]:
    """Check a per-bar volume profile; return it as a plain list of ints."""
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise InvalidScheduleInputError(f"{what} must be a sequence of bar volumes")
    bars = list(values)
    if not bars and not allow_empty:
        raise InvalidScheduleInputError(f"{what} must contain at least one bar")
    for index, volume in enumerate(bars):
        if isinstance(volume, bool) or not isinstance(volume, int):
            raise InvalidScheduleInputError(
                f"{what}[{index}] must be an integer number of shares, got {volume!r}"
            )
        if volume < 0:
            raise InvalidScheduleInputError(f"{what}[{index}] must be non-negative, got {volume}")
    return bars


def _validate_participation(max_participation: float) -> float:
    if isinstance(max_participation, bool) or not isinstance(max_participation, (int, float)):
        raise InvalidScheduleInputError(
            f"max_participation must be a number in (0, 1], got {max_participation!r}"
        )
    rate = float(max_participation)
    if not 0.0 < rate <= 1.0:
        raise InvalidScheduleInputError(
            f"max_participation must be in (0, 1], got {max_participation!r}"
        )
    return rate


def _effective_cap_lots(
    *,
    max_quantity: int | None,
    max_notional: float | None,
    reference_price: float | None,
    lot_size: int,
) -> int | None:
    """Strongest authorized per-child maximum, expressed in whole lots.

    When both ceilings are given the tighter one wins. A notional ceiling
    without a price is refused: compliance would be unverifiable, and an
    unverifiable ceiling is no ceiling.
    """
    candidates: list[int] = []
    if max_quantity is not None:
        if isinstance(max_quantity, bool) or not isinstance(max_quantity, int):
            raise InvalidScheduleInputError(
                f"max_quantity must be a positive integer, got {max_quantity!r}"
            )
        if max_quantity <= 0:
            raise InvalidScheduleInputError(
                f"max_quantity must be a positive integer, got {max_quantity}"
            )
        candidates.append(max_quantity)
    if max_notional is not None:
        if isinstance(max_notional, bool) or not isinstance(max_notional, (int, float)):
            raise InvalidScheduleInputError(
                f"max_notional must be a positive number, got {max_notional!r}"
            )
        if not float(max_notional) > 0.0:
            raise InvalidScheduleInputError(
                f"max_notional must be a positive number, got {max_notional}"
            )
        if reference_price is None:
            raise InvalidScheduleInputError(
                "max_notional without reference_price is unverifiable; "
                "refusing to assume a price for the authorized maximum"
            )
        if (
            isinstance(reference_price, bool)
            or not isinstance(reference_price, (int, float))
            or not float(reference_price) > 0.0
        ):
            raise InvalidScheduleInputError(
                f"reference_price must be a positive number, got {reference_price!r}"
            )
        # Floor, with a small epsilon so a mathematically exact quotient that
        # lands just below an integer in floating point still converts exactly.
        # The epsilon is far below one share at realistic magnitudes, so the
        # floor can never climb above the true quotient by a whole share.
        cap_qty = int(math.floor(float(max_notional) / float(reference_price) + 1e-9))
        candidates.append(cap_qty)
    if not candidates:
        return None
    # Floor the ceiling itself to whole lots: children are lot multiples, so the
    # largest representable compliant child is the floored value, never above.
    return min(candidates) // lot_size


def _check_total_capacity(
    *, total_lots: int, num_bars: int, cap_lots: int | None, lot_size: int, algorithm: str
) -> None:
    """Refuse up front when the total cannot fit inside the authorized maximum."""
    if cap_lots is not None and total_lots > num_bars * cap_lots:
        raise InfeasibleScheduleError(
            f"{algorithm} schedule refused: total {total_lots * lot_size} across "
            f"{num_bars} bars exceeds capacity {num_bars * cap_lots * lot_size} "
            f"({num_bars} bars x authorized maximum {cap_lots * lot_size}); "
            "widen the window or lower the total rather than breaching the maximum"
        )


def _enforce_cap(
    *, lots: Sequence[int], cap_lots: int | None, lot_size: int, algorithm: str
) -> None:
    """Boundary check: no child leaves this module above the authorized maximum."""
    if cap_lots is None:
        return
    for index, bar_lots in enumerate(lots):
        if bar_lots > cap_lots:
            raise InfeasibleScheduleError(
                f"{algorithm} schedule refused: bar {index} needs {bar_lots * lot_size} "
                f"but the authorized maximum is {cap_lots * lot_size}; "
                "the schedule is refused rather than reshaped past the maximum"
            )


def _hamilton_lots(
    weights: Sequence[int], total_lots: int
) -> tuple[list[int], tuple[int, ...]]:
    """Split ``total_lots`` across bars by weight (largest-remainder method).

    Each bar receives ``floor(total * weight / sum)`` lots, then the leftover
    whole lots go one each to the bars with the largest fractional entitlement
    (ties broken toward the earliest bar). All arithmetic is exact integer
    ``divmod`` — no floating point, no clocks, no randomness — so the result is
    fully deterministic and sums exactly to ``total_lots``. A zero-weight bar
    has zero fractional entitlement and, because the leftover is always smaller
    than the number of bars with a positive fraction, never receives a lot.

    Returns the per-bar lots and the sorted indices of the named remainder bars
    (empty when the total divides evenly).
    """
    denominator = sum(weights)
    lots: list[int] = []
    numerators: list[int] = []
    for weight in weights:
        whole, numerator = divmod(total_lots * weight, denominator)
        lots.append(whole)
        numerators.append(numerator)
    leftover = total_lots - sum(lots)
    priority = sorted(range(len(weights)), key=lambda i: (-numerators[i], i))
    for rank in range(leftover):
        lots[priority[rank]] += 1
    return lots, tuple(sorted(priority[:leftover]))


# ─────────────────────────────────────────────────────────────────────────────
# TWAP
# ─────────────────────────────────────────────────────────────────────────────


def twap_schedule(
    total_quantity: int,
    num_bars: int,
    *,
    lot_size: int = 1,
    max_quantity: int | None = None,
    max_notional: float | None = None,
    reference_price: float | None = None,
) -> ExecutionSchedule:
    """Split ``total_quantity`` evenly across ``num_bars`` bars.

    Extra lots that do not divide evenly go one each to the earliest bars
    (named in ``remainder_bars``), so the largest and smallest child differ by
    at most one lot and raising the total never shrinks any child.
    """
    total_lots = _validate_lot_inputs(total_quantity, lot_size)
    bars = _validate_bar_count(num_bars)
    cap_lots = _effective_cap_lots(
        max_quantity=max_quantity,
        max_notional=max_notional,
        reference_price=reference_price,
        lot_size=lot_size,
    )
    _check_total_capacity(
        total_lots=total_lots,
        num_bars=bars,
        cap_lots=cap_lots,
        lot_size=lot_size,
        algorithm="TWAP",
    )
    lots, remainder_bars = _hamilton_lots([1] * bars, total_lots)
    _enforce_cap(lots=lots, cap_lots=cap_lots, lot_size=lot_size, algorithm="TWAP")
    children = tuple(bar_lots * lot_size for bar_lots in lots)
    if remainder_bars:
        note = (
            f"even split across {bars} bars; "
            f"one extra lot to earliest bars {list(remainder_bars)}"
        )
    else:
        note = f"even split across {bars} bars; total divides evenly, no remainder"
    return ExecutionSchedule(
        algorithm="TWAP",
        total_quantity=total_quantity,
        children=children,
        lot_size=lot_size,
        remainder_bars=remainder_bars,
        notes=(note,),
    )


# ─────────────────────────────────────────────────────────────────────────────
# VWAP
# ─────────────────────────────────────────────────────────────────────────────


def vwap_schedule(
    total_quantity: int,
    volumes: Sequence[int],
    *,
    lot_size: int = 1,
    max_quantity: int | None = None,
    max_notional: float | None = None,
    reference_price: float | None = None,
) -> ExecutionSchedule:
    """Split ``total_quantity`` in proportion to the ``volumes`` profile.

    Each child stays within one lot of its exact proportional share, strict
    volume order is preserved (a higher-volume bar never receives less than a
    lower-volume one), and zero-volume bars receive zero. An empty or all-zero
    profile degrades to a TWAP even split with ``degraded=True`` and the named
    reason :data:`DEGRADATION_EMPTY_PROFILE` instead of dividing by zero. A
    concentrated profile that would breach the authorized maximum is refused.

    Deliberate trade-off (Balinski-Young): no apportionment method keeps every
    child within quota *and* never shrinks a child when the total grows
    (the Alabama paradox — e.g. volumes [50, 30, 20, 10] give bar 3 a share
    of 10 at total 104 but 9 at total 105). VWAP keeps quota adherence
    (tracking the profile is the point of VWAP) and does *not* promise
    cross-total per-child monotonicity; TWAP and POV do promise it.
    """
    total_lots = _validate_lot_inputs(total_quantity, lot_size)
    bars = _validate_volumes(volumes, allow_empty=True, what="volumes")
    cap_lots = _effective_cap_lots(
        max_quantity=max_quantity,
        max_notional=max_notional,
        reference_price=reference_price,
        lot_size=lot_size,
    )
    if not bars or sum(bars) == 0:
        count = len(bars) if bars else 1
        _check_total_capacity(
            total_lots=total_lots,
            num_bars=count,
            cap_lots=cap_lots,
            lot_size=lot_size,
            algorithm="VWAP",
        )
        lots, remainder_bars = _hamilton_lots([1] * count, total_lots)
        _enforce_cap(lots=lots, cap_lots=cap_lots, lot_size=lot_size, algorithm="VWAP")
        return ExecutionSchedule(
            algorithm="VWAP",
            total_quantity=total_quantity,
            children=tuple(bar_lots * lot_size for bar_lots in lots),
            lot_size=lot_size,
            remainder_bars=remainder_bars,
            degraded=True,
            degradation_reason=DEGRADATION_EMPTY_PROFILE,
            notes=(
                "volume profile empty; degraded to TWAP even split "
                f"across {count} bar(s) with reason "
                f"{DEGRADATION_EMPTY_PROFILE!r}",
            ),
        )
    _check_total_capacity(
        total_lots=total_lots,
        num_bars=len(bars),
        cap_lots=cap_lots,
        lot_size=lot_size,
        algorithm="VWAP",
    )
    lots, remainder_bars = _hamilton_lots(bars, total_lots)
    _enforce_cap(lots=lots, cap_lots=cap_lots, lot_size=lot_size, algorithm="VWAP")
    return ExecutionSchedule(
        algorithm="VWAP",
        total_quantity=total_quantity,
        children=tuple(bar_lots * lot_size for bar_lots in lots),
        lot_size=lot_size,
        remainder_bars=remainder_bars,
        notes=(f"proportional to {len(bars)}-bar volume profile",),
    )


# ─────────────────────────────────────────────────────────────────────────────
# POV
# ─────────────────────────────────────────────────────────────────────────────


def _participation_limit_lots(rate: float, volume: int, lot_size: int) -> int:
    """Whole lots tradable in a bar at ``rate`` participation (floored, never up)."""
    raw = rate * float(volume)
    return max(0, int(math.floor(raw / float(lot_size) + 1e-9)))


def pov_schedule(
    total_quantity: int,
    volumes: Sequence[int],
    *,
    max_participation: float,
    lot_size: int = 1,
    max_quantity: int | None = None,
    max_notional: float | None = None,
    reference_price: float | None = None,
) -> ExecutionSchedule:
    """Trade at most ``max_participation`` of each bar's volume, earliest first.

    Each bar receives the smaller of its participation limit and the quantity
    still unfilled, so zero-volume bars pause (receive zero) rather than
    inventing volume, and filling stops the moment the total is placed — later
    bars stay at zero instead of trading past completion. When the profile
    cannot absorb the total within the participation rate (or the authorized
    maximum), the schedule is refused instead of exceeding either limit.
    """
    total_lots = _validate_lot_inputs(total_quantity, lot_size)
    bars = _validate_volumes(volumes, allow_empty=False, what="volumes")
    rate = _validate_participation(max_participation)
    cap_lots = _effective_cap_lots(
        max_quantity=max_quantity,
        max_notional=max_notional,
        reference_price=reference_price,
        lot_size=lot_size,
    )
    limits = [
        min(_participation_limit_lots(rate, volume, lot_size), cap_lots)
        if cap_lots is not None
        else _participation_limit_lots(rate, volume, lot_size)
        for volume in bars
    ]
    capacity = sum(limits) * lot_size
    if sum(limits) < total_lots:
        raise InfeasibleScheduleError(
            f"POV schedule refused: total {total_quantity} exceeds participatable "
            f"capacity {capacity} at participation {rate} across {len(bars)} bars; "
            "pausing instead of exceeding participation or inventing volume"
        )
    lots = [0] * len(bars)
    remaining = total_lots
    for index, limit in enumerate(limits):
        take = limit if limit < remaining else remaining
        lots[index] = take
        remaining -= take
        if remaining == 0:
            break
    if remaining > 0:  # Backstop; the capacity check above already excluded this.
        raise InfeasibleScheduleError(
            f"POV schedule refused: {remaining * lot_size} shares unplaceable "
            "within participation and the authorized maximum"
        )
    _enforce_cap(lots=lots, cap_lots=cap_lots, lot_size=lot_size, algorithm="POV")
    paused = [index for index, volume in enumerate(bars) if volume == 0]
    return ExecutionSchedule(
        algorithm="POV",
        total_quantity=total_quantity,
        children=tuple(bar_lots * lot_size for bar_lots in lots),
        lot_size=lot_size,
        remainder_bars=(),
        notes=(
            f"max participation {rate} of bar volume; "
            f"zero-volume bars pause at {paused}; "
            "unfilled quantity carried forward bar-to-bar in order",
        ),
    )
