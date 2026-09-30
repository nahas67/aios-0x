"""Latency is the only variable (goal G160).

The twin replays one deterministic fixture through several round-trip
targets. These tests pin what makes the comparison meaningful rather than
theatrical: stages sum to the target, slower paths trade worse prices on a
drifting book (staleness, not a penalty term), partial fills stay partial,
and the whole comparison runs under identical conditions with distinct
targets.
"""

from __future__ import annotations

import pytest

from simulation.execution_twin import (
    STAGE_SHARES,
    LatencyBudget,
    TwinConfig,
    compare_latencies,
    make_fixture_ticks,
    run_twin,
)


def _config(**overrides) -> TwinConfig:
    fields: dict[str, object] = {"quantity": 400.0}
    fields.update(overrides)
    return TwinConfig(**fields)  # type: ignore[arg-type]


# ══════════════════════════════════════════════════════════════════════════
# The budget and the fixture
# ══════════════════════════════════════════════════════════════════════════


def test_stage_shares_sum_to_one() -> None:
    """A budget whose parts do not sum to its whole is a different budget
    wearing this one's name."""
    assert sum(STAGE_SHARES.values()) == pytest.approx(1.0)


def test_budget_splits_a_target_into_stages() -> None:
    budget = LatencyBudget.split(100.0)
    assert budget.target_ms == pytest.approx(100.0)
    assert budget.decide_ms + budget.transmit_ms + budget.venue_ms + budget.ack_ms == pytest.approx(
        100.0
    )
    # Acknowledgement comes back after the fill: it costs reporting latency,
    # not price. Action delay excludes it.
    assert budget.action_delay_ms == pytest.approx(80.0)


def test_nonpositive_targets_are_refused() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        LatencyBudget.split(0.0)


def test_fixture_is_deterministic_and_finite() -> None:
    """Closed form, not seeded: reproduces forever without pinning a
    generator version. A comparison run on different books is not a
    comparison."""
    first = make_fixture_ticks(400)
    second = make_fixture_ticks(400)
    assert [(t.t_ms, t.price, t.volume) for t in first] == [
        (t.t_ms, t.price, t.volume) for t in second
    ]
    assert all(t.price > 0 and t.volume > 0 and t.bid_size > 0 for t in first)
    with pytest.raises(ValueError, match="at least one tick"):
        make_fixture_ticks(0)


def test_config_refuses_nonsense() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        TwinConfig(quantity=0.0)
    with pytest.raises(ValueError, match="buy or sell"):
        TwinConfig(quantity=1.0, side="hold")
    with pytest.raises(ValueError, match="max_participation"):
        TwinConfig(quantity=1.0, max_participation=1.5)


# ══════════════════════════════════════════════════════════════════════════
# The comparison: latency costs, measured
# ══════════════════════════════════════════════════════════════════════════


def test_latency_comparison_exists_for_two_targets_under_one_fixture() -> None:
    """The gate: same book, same order, two round-trips. Slower paths trade
    worse on a drifting book — staleness made observable, not a penalty term
    added to taste."""
    ticks = make_fixture_ticks()
    results = compare_latencies(ticks, _config(), [20.0, 200.0])
    fast, slow = results[20.0], results[200.0]
    assert fast.fill_rate == pytest.approx(1.0)
    assert slow.fill_rate == pytest.approx(1.0)
    # The book drifts up; the slower buy executes later against higher prints.
    assert slow.volume_weighted_price > fast.volume_weighted_price


def test_four_targets_compare_under_identical_conditions() -> None:
    ticks = make_fixture_ticks()
    results = compare_latencies(ticks, _config(), [20.0, 50.0, 100.0, 200.0])
    assert set(results) == {20.0, 50.0, 100.0, 200.0}
    prices = [results[t].volume_weighted_price for t in (20.0, 50.0, 100.0, 200.0)]
    assert prices == sorted(prices)


def test_duplicate_targets_are_refused() -> None:
    """Identical targets compared is a comparison of a run with itself:
    keyed results would silently drop one."""
    with pytest.raises(ValueError, match="distinct"):
        compare_latencies(make_fixture_ticks(), _config(), [50.0, 50.0])


def test_partial_fills_stay_partial() -> None:
    """A tape that cannot absorb the child leaves it open: the remainder
    lands in unfilled rather than rounding complete, and the fill rate says
    so honestly."""
    ticks = make_fixture_ticks()
    result = run_twin(ticks, TwinConfig(quantity=1_000_000.0), LatencyBudget.split(20.0))
    assert result.unfilled > 0.0
    assert result.fill_rate < 1.0
    assert result.fill_rate > 0.0


def test_fills_carry_delay_attribution() -> None:
    """Every fill records when it was decided, when it printed, and its
    impact: the per-stage story, not just the average."""
    ticks = make_fixture_ticks()
    result = run_twin(ticks, _config(), LatencyBudget.split(50.0))
    assert len(result.fills) == 4
    for fill in result.fills:
        assert fill.fill_t_ms >= fill.arrival_t_ms
        assert fill.fill_rate == pytest.approx(1.0)
        assert fill.impact_bps >= 0.0
    assert result.total_impact_bps >= 0.0


def test_empty_tape_is_refused() -> None:
    with pytest.raises(ValueError, match="needs ticks"):
        run_twin([], _config(), LatencyBudget.split(20.0))


def test_sell_side_mirrors_buy_side() -> None:
    """Direction is a sign, not a separate implementation: sells execute
    against the bid queue with mirrored impact."""
    ticks = make_fixture_ticks()
    buy = run_twin(ticks, _config(side="buy"), LatencyBudget.split(50.0))
    sell = run_twin(ticks, _config(side="sell"), LatencyBudget.split(50.0))
    assert buy.fill_rate == pytest.approx(1.0)
    assert sell.fill_rate == pytest.approx(1.0)
    assert sell.volume_weighted_price < buy.volume_weighted_price
