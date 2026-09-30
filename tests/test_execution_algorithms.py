"""Property tests for the G150 execution schedulers (TWAP/VWAP/POV).

Every test is deterministic (fixed fixtures, no clocks, no randomness) and
carries a docstring naming the defect it prevents, per repo rule. Repetition
assertions prove the schedulers are pure: same inputs, same schedule.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from communities.c5_execution.algorithms import (
    DEGRADATION_EMPTY_PROFILE,
    ExecutionSchedule,
    InfeasibleScheduleError,
    InvalidScheduleInputError,
    ScheduleError,
    pov_schedule,
    twap_schedule,
    vwap_schedule,
)

# ─────────────────────────────────────────────────────────────────────────────
# TWAP
# ─────────────────────────────────────────────────────────────────────────────


def test_twap_children_sum_exactly_to_total() -> None:
    """Prevents dust creation/loss: children must add up to the total exactly."""
    for total, bars in ((100, 3), (101, 4), (7, 7), (1, 5), (1000, 9)):
        schedule = twap_schedule(total, bars)
        assert schedule.allocated == total
        assert sum(schedule.children) == total


def test_twap_even_split_differs_by_at_most_one_lot() -> None:
    """Prevents lopsided slicing: an even split must stay within one lot."""
    schedule = twap_schedule(100, 3, lot_size=10)
    assert sorted(schedule.children) == [30, 30, 40]
    assert max(schedule.children) - min(schedule.children) <= 10


def test_twap_lot_multiples_round_down_only() -> None:
    """Prevents rounding up past entitlement: every child is a whole lot."""
    schedule = twap_schedule(100, 3, lot_size=10)
    assert all(child % 10 == 0 for child in schedule.children)
    assert schedule.allocated == 100


def test_twap_remainder_bars_are_named() -> None:
    """Prevents silent remainder handling: leftover lots land on named bars."""
    schedule = twap_schedule(100, 3, lot_size=10)
    assert schedule.remainder_bars == (0,)
    assert schedule.children[0] == 40
    even = twap_schedule(90, 3, lot_size=10)
    assert even.remainder_bars == ()
    assert list(even.children) == [30, 30, 30]


def test_twap_rejects_sub_lot_total() -> None:
    """Prevents silent dust loss: a non-whole-lot total is refused, not floored."""
    with pytest.raises(InvalidScheduleInputError):
        twap_schedule(95, 3, lot_size=10)


def test_twap_monotone_in_total() -> None:
    """Prevents regressive slicing: a larger total never shrinks any child.

    Invariant (TWAP): for fixed bars/lots, raising the total by whole lots
    never decreases any per-bar child.
    """
    previous = twap_schedule(90, 4).children
    for total in range(91, 112):
        current = twap_schedule(total, 4).children
        assert all(new >= old for new, old in zip(current, previous, strict=True))
        previous = current


def test_twap_determinism_by_repetition() -> None:
    """Prevents hidden nondeterminism (clocks/randomness): repeats are identical."""
    first = twap_schedule(1000, 7, lot_size=5)
    for _ in range(5):
        assert twap_schedule(1000, 7, lot_size=5) == first


def test_twap_respects_authorized_max_quantity() -> None:
    """Prevents cap breach: no child exceeds the authorized maximum."""
    schedule = twap_schedule(100, 4, max_quantity=30)
    assert all(child <= 30 for child in schedule.children)
    assert schedule.allocated == 100


def test_twap_refuses_total_beyond_cap_capacity() -> None:
    """Prevents cap breach by overflow: an unfillable total is refused, not clipped."""
    with pytest.raises(InfeasibleScheduleError):
        twap_schedule(100, 2, max_quantity=40)


def test_twap_single_bar_holds_whole_total() -> None:
    """Prevents degenerate-window loss: one bar receives the entire total."""
    schedule = twap_schedule(50, 1)
    assert list(schedule.children) == [50]


def test_twap_rejects_bad_inputs() -> None:
    """Prevents garbage-in schedules: non-positive totals and empty grids fail."""
    for total, bars in ((0, 3), (-10, 3), (100, 0), (100, -2)):
        with pytest.raises(InvalidScheduleInputError):
            twap_schedule(total, bars)


# ─────────────────────────────────────────────────────────────────────────────
# VWAP
# ─────────────────────────────────────────────────────────────────────────────


def test_vwap_children_sum_exactly_to_total() -> None:
    """Prevents dust creation/loss under proportional splits."""
    schedule = vwap_schedule(101, [70, 20, 10])
    assert schedule.allocated == 101
    assert len(schedule.children) == 3


def test_vwap_tracks_profile_within_one_lot() -> None:
    """Prevents mislabeled equal-splits: each child stays near its exact share."""
    volumes = [70, 20, 10]
    total = 101
    schedule = vwap_schedule(total, volumes)
    weight_sum = sum(volumes)
    for child, volume in zip(schedule.children, volumes, strict=True):
        quota = total * volume / weight_sum
        assert abs(child - quota) <= 1
    # And it must actually differentiate: nothing like TWAP's flat [34, 34, 33].
    assert schedule.children[0] > schedule.children[1] > schedule.children[2]


def test_vwap_preserves_strict_volume_order() -> None:
    """Prevents order inversion: a higher-volume bar never receives less.

    Invariant (VWAP, uncapped): vol_i > vol_j implies child_i >= child_j.
    """
    schedule = vwap_schedule(97, [50, 30, 15, 5])
    children = schedule.children
    assert children[0] >= children[1] >= children[2] >= children[3]


def test_vwap_zero_weight_bar_receives_zero() -> None:
    """Prevents invented flow: bars with no expected volume receive nothing."""
    schedule = vwap_schedule(100, [80, 20, 0])
    assert schedule.children[2] == 0
    assert schedule.allocated == 100


def test_vwap_all_zero_profile_degrades_to_twap_with_named_reason() -> None:
    """Prevents divide-by-zero: an empty profile falls back to TWAP, named."""
    schedule = vwap_schedule(90, [0, 0, 0])
    assert schedule.degraded is True
    assert schedule.degradation_reason == DEGRADATION_EMPTY_PROFILE
    assert list(schedule.children) == [30, 30, 30]
    assert schedule.allocated == 90


def test_vwap_empty_list_degrades_to_single_bar_twap() -> None:
    """Prevents divide-by-zero on a missing profile: one bar holds the total."""
    schedule = vwap_schedule(50, [])
    assert schedule.degraded is True
    assert schedule.degradation_reason == DEGRADATION_EMPTY_PROFILE
    assert list(schedule.children) == [50]


def test_vwap_degraded_schedule_is_not_confused_with_planned() -> None:
    """Prevents silent fallback: a healthy profile is never marked degraded."""
    schedule = vwap_schedule(90, [30, 30, 30])
    assert schedule.degraded is False
    assert schedule.degradation_reason == ""


def test_vwap_quota_adherence_across_totals() -> None:
    """Prevents profile drift at some sizes: every child tracks its share.

    Invariant (VWAP, uncapped): at *every* total, each child stays within one
    lot of its exact proportional quota for that total. Cross-total per-child
    monotonicity is deliberately NOT claimed here: largest-remainder methods
    exhibit the Alabama paradox (volumes [50, 30, 20, 10] give bar 3 a share
    of 10 at total 104 but 9 at total 105), and quota adherence — tracking the
    profile, the point of VWAP — is the property kept instead.
    """
    volumes = [50, 30, 20, 10]
    weight_sum = sum(volumes)
    for total in range(95, 115):
        schedule = vwap_schedule(total, volumes)
        assert schedule.allocated == total
        for child, volume in zip(schedule.children, volumes, strict=True):
            assert abs(child - total * volume / weight_sum) <= 1
    # The paradox case itself still tracks within quota.
    paradox = vwap_schedule(105, volumes)
    assert list(paradox.children) == [48, 29, 19, 9]


def test_vwap_determinism_by_repetition() -> None:
    """Prevents hidden nondeterminism (tie-breaks/clocks): repeats are identical."""
    first = vwap_schedule(1000, [55, 25, 15, 5], lot_size=5)
    for _ in range(5):
        assert vwap_schedule(1000, [55, 25, 15, 5], lot_size=5) == first


def test_vwap_concentrated_profile_breach_is_refused() -> None:
    """Prevents cap breach by concentration: refused, never reshaped past the max."""
    with pytest.raises(InfeasibleScheduleError):
        vwap_schedule(102, [100, 1, 1], max_quantity=60)


def test_vwap_max_notional_cap_limits_every_child() -> None:
    """Prevents notional overflow: price-derived ceilings bind every child."""
    schedule = vwap_schedule(
        100, [10, 10, 10, 10], max_notional=300.0, reference_price=10.0
    )
    assert all(child * 10.0 <= 300.0 for child in schedule.children)
    assert schedule.allocated == 100


def test_vwap_rejects_negative_volumes() -> None:
    """Prevents nonsense profiles: negative bar volumes are refused."""
    with pytest.raises(InvalidScheduleInputError):
        vwap_schedule(100, [80, -20, 40])


# ─────────────────────────────────────────────────────────────────────────────
# POV
# ─────────────────────────────────────────────────────────────────────────────


def test_pov_children_sum_exactly_to_total() -> None:
    """Prevents dust creation/loss under rate-capped fills."""
    schedule = pov_schedule(100, [400, 200, 600], max_participation=0.25)
    assert schedule.allocated == 100


def test_pov_never_exceeds_participation() -> None:
    """Prevents rate breach: no child exceeds its bar's participation limit."""
    volumes = [400, 200, 600, 100]
    rate = 0.25
    schedule = pov_schedule(150, volumes, max_participation=rate)
    for child, volume in zip(schedule.children, volumes, strict=True):
        assert child <= rate * volume + 1e-6


def test_pov_zero_volume_bar_pauses() -> None:
    """Prevents invented volume: zero-volume bars pause at zero, fill continues."""
    schedule = pov_schedule(100, [0, 1000, 0, 1000], max_participation=0.1)
    assert schedule.children[0] == 0
    assert schedule.children[2] == 0
    assert schedule.allocated == 100


def test_pov_all_zero_volumes_refused() -> None:
    """Prevents trading against no market: nothing participatable means refusal."""
    with pytest.raises(InfeasibleScheduleError):
        pov_schedule(10, [0, 0], max_participation=0.5)


def test_pov_insufficient_participation_refused() -> None:
    """Prevents rate breach under thin volume: unfillable totals are refused."""
    with pytest.raises(InfeasibleScheduleError):
        pov_schedule(30, [100, 100], max_participation=0.1)


def test_pov_stops_at_completion() -> None:
    """Prevents over-trading past completion: trailing bars stay at zero."""
    schedule = pov_schedule(200, [1000, 1000, 1000], max_participation=0.5)
    assert list(schedule.children) == [200, 0, 0]


def test_pov_lot_floor_never_rounds_up() -> None:
    """Prevents rounding-up breach: sub-lot participation capacity stays unfilled."""
    schedule = pov_schedule(90, [95], max_participation=1.0, lot_size=10)
    assert list(schedule.children) == [90]


def test_pov_monotone_in_total() -> None:
    """Prevents regressive fills: a larger total never shrinks any child.

    Invariant (POV): for fixed volumes/rate, raising the total never decreases
    any per-bar child (earliest-fill order absorbs the increase in place).
    """
    volumes = [0, 400, 200, 600]
    previous = pov_schedule(1, volumes, max_participation=0.25).children
    for total in range(2, 300, 7):
        current = pov_schedule(total, volumes, max_participation=0.25).children
        assert all(new >= old for new, old in zip(current, previous, strict=True))
        previous = current


def test_pov_determinism_by_repetition() -> None:
    """Prevents hidden nondeterminism: repeats are identical."""
    first = pov_schedule(250, [300, 700, 500, 900], max_participation=0.3)
    for _ in range(5):
        assert pov_schedule(250, [300, 700, 500, 900], max_participation=0.3) == first


def test_pov_rejects_bad_participation_rates() -> None:
    """Prevents meaningless rates: 0, negative, and above-100% rates fail."""
    for rate in (0.0, -0.1, 1.5):
        with pytest.raises(InvalidScheduleInputError):
            pov_schedule(100, [1000, 1000], max_participation=rate)


def test_pov_rejects_empty_bar_grid() -> None:
    """Prevents scheduling into no bars: an empty grid is refused."""
    with pytest.raises(InvalidScheduleInputError):
        pov_schedule(100, [], max_participation=0.5)


# ─────────────────────────────────────────────────────────────────────────────
# Shared boundaries
# ─────────────────────────────────────────────────────────────────────────────


def test_max_notional_without_price_is_refused() -> None:
    """Prevents assumed prices: an unverifiable notional ceiling fails closed."""
    with pytest.raises(InvalidScheduleInputError):
        twap_schedule(100, 4, max_notional=500.0)
    with pytest.raises(InvalidScheduleInputError):
        vwap_schedule(100, [25, 25, 25, 25], max_notional=500.0)
    with pytest.raises(InvalidScheduleInputError):
        pov_schedule(100, [1000, 1000], max_participation=0.5, max_notional=500.0)


def test_tighter_of_two_ceilings_wins() -> None:
    """Prevents ceiling shopping: quantity and notional caps both bind."""
    notional_binds = twap_schedule(
        80, 4, max_quantity=1000, max_notional=200.0, reference_price=10.0
    )
    assert list(notional_binds.children) == [20, 20, 20, 20]
    quantity_binds = twap_schedule(
        60, 4, max_quantity=15, max_notional=100000.0, reference_price=10.0
    )
    assert list(quantity_binds.children) == [15, 15, 15, 15]


def test_schedule_errors_are_value_errors() -> None:
    """Prevents exception-escape: schedule failures stay catchable as ValueError."""
    assert issubclass(InvalidScheduleInputError, ScheduleError)
    assert issubclass(InfeasibleScheduleError, ScheduleError)
    assert issubclass(ScheduleError, ValueError)


def test_hand_built_schedule_cannot_create_or_lose_dust() -> None:
    """Prevents off-schedule construction: the model itself enforces exact sums."""
    with pytest.raises(ValidationError):
        ExecutionSchedule(
            algorithm="TWAP",
            total_quantity=100,
            children=(50, 40),
            lot_size=1,
        )
    with pytest.raises(ValidationError):
        ExecutionSchedule(
            algorithm="VWAP",
            total_quantity=100,
            children=(50, 50, 1),
            lot_size=1,
        )


def test_schedules_are_immutable() -> None:
    """Prevents post-hoc tampering: schedules cannot be mutated after build."""
    schedule = twap_schedule(100, 4)
    with pytest.raises(ValidationError):
        schedule.children = (100, 0, 0, 0)  # type: ignore[assignment]
