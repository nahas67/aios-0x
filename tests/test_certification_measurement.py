"""A certification must be measured, not promised (goal G080).

The firewall originally took booleans: ``capacity_modelled=True``. That is a
promise, and a promise is exactly what a process under deadline makes. This
suite pins the replacement: the cost, capacity, stress, and execution checks are
derived from numbers a backtest produces, so a caller that will not run one
cannot certify.

The property under test throughout is that **the evidence must be internally
consistent with itself**. Costs applied means the net and gross series differ,
not that somebody said so. A capacity claim is a measured ceiling that covers
the size the mandate needs, not a number typed into a form.
"""

from __future__ import annotations

import random

import pytest

from core.backtest import (
    CostModel,
    ExecutionModel,
    RegimeSlice,
    StressScenario,
    apply_stress,
    capacity_ceiling,
    run_backtest,
    worst_case_sharpe,
)
from kernel.bootstrap import create_kernel
from kernel.strategy_registry import (
    CertificationEvidence,
    StrategyRegistry,
    ValidationStatus,
)

SIZES = [1e4, 1e5, 5e5, 1e6, 5e6, 1e7, 5e7]


@pytest.fixture()
def registry() -> StrategyRegistry:
    return StrategyRegistry(create_kernel().provenance)


def _register(registry: StrategyRegistry) -> None:
    registry.register(
        strategy_id="momentum-1",
        version="v1",
        hypothesis_id="hyp-1",
        family="momentum",
        dataset_ref={"dataset_id": "btc_daily", "version": "v1.0"},
    )


def _regimes() -> dict[str, RegimeSlice]:
    """A measured decomposition: two regimes, both with enough observations
    and both profitable net of costs. What a real ``regime_sharpes`` call
    returns for a strategy that works in more than one state of the world."""
    return {
        "trending_up": RegimeSlice("trending_up", 1.4, 300),
        "range_bound": RegimeSlice("range_bound", 0.3, 200),
    }


# ══════════════════════════════════════════════════════════════════════════
# The cost model
# ══════════════════════════════════════════════════════════════════════════


def test_a_costless_model_is_detected_as_degenerate() -> None:
    """Zero everywhere is not a cost model; it is a wish."""
    assert CostModel(
        commission_bps=0.0, half_spread_bps=0.0, impact_coefficient_bps=0.0
    ).is_degenerate() is True
    assert CostModel().is_degenerate() is False


def test_impact_follows_the_square_root_law() -> None:
    """Doubling size costs ~41% more impact, not 100%.

    The square root is the empirical result; a linear impact assumption is how
    a capacity estimate ends up three times too large.
    """
    costs = CostModel(commission_bps=0.0, half_spread_bps=0.0, impact_coefficient_bps=10.0)
    once = costs.impact_bps(0.01)
    twice = costs.impact_bps(0.04)
    assert twice / once == pytest.approx(2.0, rel=1e-9), "4x participation is 2x impact"
    assert twice == pytest.approx(2.0 * once, rel=1e-9)


def test_zero_participation_costs_nothing() -> None:
    assert CostModel().impact_bps(0.0) == 0.0


def test_a_frictionless_execution_model_is_detected() -> None:
    assert ExecutionModel().is_frictionless() is True
    assert ExecutionModel(latency_bars=1).is_frictionless() is False
    assert ExecutionModel(partial_fill_ratio=0.9).is_frictionless() is False
    assert ExecutionModel(rejected_rate=0.01).is_frictionless() is False


# ══════════════════════════════════════════════════════════════════════════
# The backtest
# ══════════════════════════════════════════════════════════════════════════


def _trending_series(
    n: int = 1500, drift: float = 0.0018, sigma: float = 0.012, seed: int = 11
) -> tuple[list[int], list[float], list[float]]:
    """A frequent-rebalancing long/flat signal on a drifting series.

    Two properties the capacity tests depend on, and neither is free:

    * **Enough bars.** 300 bars leave a sampling error of about 0.0006 on a
      0.0008 drift, so the "edge" is noise and every test measures nothing. 1,500
      bars puts the drift several standard errors from zero.
    * **Enough turnover.** A signal that never changes position pays cost once
      and impact never accumulates, so capacity would never bind. Flipping in
      and out of the market every few bars pays on most bars.

    Volume is deliberately thin, so a plausible notional becomes a material
    participation rate and the square-root law has something to act on.
    """
    rng = random.Random(seed)
    prices: list[float] = [100.0]
    volumes: list[float] = []
    for _ in range(n - 1):
        prices.append(max(1.0, prices[-1] * (1.0 + rng.gauss(drift, sigma))))
        volumes.append(120_000.0)
    signals = [1 if (i % 10) < 7 else 0 for i in range(n)]
    return signals, prices, volumes


def test_a_costless_run_produces_identical_gross_and_net() -> None:
    """The measurable signature of a backtest with no costs attached."""
    signals, prices, volumes = _trending_series()
    result = run_backtest(
        signals,
        prices,
        volumes=volumes,
        notional=100_000.0,
        costs=CostModel(commission_bps=0.0, half_spread_bps=0.0, impact_coefficient_bps=0.0),
    )
    assert result.gross_sharpe == result.net_sharpe
    assert result.costs_applied is False
    assert result.cost_drag == 0.0


def test_a_real_cost_model_moves_the_net_series() -> None:
    signals, prices, volumes = _trending_series()
    result = run_backtest(signals, prices, volumes=volumes, notional=100_000.0)
    assert result.costs_applied is True
    assert result.cost_drag > 0.0
    assert result.net_sharpe < result.gross_sharpe


def test_impact_erodes_returns_as_size_grows() -> None:
    """The reason capacity exists: the same edge is worth less at scale."""
    signals, prices, volumes = _trending_series()
    small = run_backtest(signals, prices, volumes=volumes, notional=10_000.0)
    large = run_backtest(signals, prices, volumes=volumes, notional=10_000_000.0)
    assert large.participation > small.participation
    assert large.net_sharpe < small.net_sharpe


def test_participation_never_exceeds_one_in_a_real_run() -> None:
    """A participation rate above 1 means the model is not being used correctly."""
    signals, prices, volumes = _trending_series()
    result = run_backtest(
        signals, prices, volumes=volumes, notional=1.0, costs=CostModel()
    )
    assert 0.0 <= result.participation <= 1.0


def test_a_series_too_short_returns_an_empty_result() -> None:
    result = run_backtest([1], [100.0], volumes=[1.0])
    assert result.gross_returns == []
    assert result.net_sharpe == 0.0
    assert result.costs_applied is False


# ══════════════════════════════════════════════════════════════════════════
# Capacity, measured
# ══════════════════════════════════════════════════════════════════════════


def test_capacity_ceiling_falls_as_the_bar_rises() -> None:
    """The claim that shrinks when it should is the whole point.

    Capacity is measured, so a stricter performance requirement must admit a
    smaller size. An asserted capacity number cannot behave this way, which is
    exactly why this test exists.
    """
    signals, prices, volumes = _trending_series()
    ceilings = [
        capacity_ceiling(
            signals, prices, volumes=volumes, target_notionals=SIZES, min_net_sharpe=bar
        )
        for bar in (0.5, 1.0, 1.5, 2.0, 2.25)
    ]
    assert all(c > 0.0 for c in ceilings)
    assert ceilings == sorted(ceilings, reverse=True), ceilings
    assert ceilings[0] > ceilings[-1], "a stricter bar must admit a smaller size"


def test_net_sharpe_erodes_monotonically_with_size() -> None:
    """The mechanism behind capacity: the same edge is worth less at scale."""
    signals, prices, volumes = _trending_series()
    sharpes = [
        run_backtest(signals, prices, volumes=volumes, notional=notional).net_sharpe
        for notional in SIZES
    ]
    assert sharpes == sorted(sharpes, reverse=True), sharpes
    assert sharpes[0] > sharpes[-1]


def test_gross_sharpe_is_independent_of_size() -> None:
    """Only the costs change with size. A gross figure that varied would mean
    the size was silently changing the strategy, not just its frictions."""
    signals, prices, volumes = _trending_series()
    gross = [
        run_backtest(signals, prices, volumes=volumes, notional=notional).gross_sharpe
        for notional in SIZES
    ]
    assert len(set(gross)) == 1, gross


def test_capacity_is_zero_when_nothing_clears_the_bar() -> None:
    signals, prices, volumes = _trending_series()
    assert (
        capacity_ceiling(
            signals,
            prices,
            volumes=volumes,
            target_notionals=SIZES,
            min_net_sharpe=1_000.0,
        )
        == 0.0
    )


def test_capacity_ignores_non_positive_sizes() -> None:
    signals, prices, volumes = _trending_series()
    ceiling = capacity_ceiling(
        signals,
        prices,
        volumes=volumes,
        target_notionals=[0.0, -5.0, 10_000.0],
        min_net_sharpe=0.0,
    )
    assert ceiling == 10_000.0


def test_capacity_without_volumes_ignores_impact() -> None:
    """Omitted volume disables impact, which is a measurable deficiency.

    The fixed round trip still applies, so the result is costed but not
    capacity-limited, and a certification relying on it should be treated as
    measuring less than one that used volumes.
    """
    signals, prices, volumes = _trending_series()
    with_volumes = capacity_ceiling(
        signals, prices, volumes=volumes, target_notionals=SIZES, min_net_sharpe=2.2
    )
    without = capacity_ceiling(
        signals, prices, volumes=None, target_notionals=SIZES, min_net_sharpe=2.2
    )
    assert without >= with_volumes, "no volume means no impact ceiling"


# ══════════════════════════════════════════════════════════════════════════
# Stress, measured
# ══════════════════════════════════════════════════════════════════════════


def test_stress_applies_the_shock_to_the_series() -> None:
    prices = [100.0] * 10
    stressed = apply_stress(prices, StressScenario("crash", shock=-0.5, at_fraction=0.5))
    assert stressed[:5] == prices[:5], "the pre-shock region is untouched"
    assert stressed[5] == pytest.approx(50.0)


def test_stress_never_produces_a_non_positive_price() -> None:
    stressed = apply_stress([1.0] * 6, StressScenario("wipeout", shock=-0.99, at_fraction=0.0))
    assert all(p > 0.0 for p in stressed)


def test_worst_case_sharpe_names_the_scenario_that_hurt() -> None:
    """A stress result has to name its culprit, or it is not actionable."""
    signals, prices, volumes = _trending_series()
    sharpe, name = worst_case_sharpe(
        signals,
        prices,
        volumes=volumes,
        notional=100_000.0,
        scenarios=[StressScenario("mild", shock=-0.01), StressScenario("severe", shock=-0.40)],
    )
    assert name in {"mild", "severe"}
    assert sharpe <= 1_000.0


def test_a_harsher_scenario_cannot_improve_the_worst_case() -> None:
    """Monotonicity: breaking the tape harder cannot help."""
    signals, prices, volumes = _trending_series()
    mild, _ = worst_case_sharpe(
        signals, prices, volumes=volumes, notional=100_000.0,
        scenarios=[StressScenario("mild", shock=-0.05)],
    )
    severe, _ = worst_case_sharpe(
        signals, prices, volumes=volumes, notional=100_000.0,
        scenarios=[StressScenario("severe", shock=-0.50, volatility_multiplier=3.0)],
    )
    assert severe <= mild


def test_no_scenarios_is_reported_rather_than_guessed() -> None:
    signals, prices, volumes = _trending_series()
    sharpe, name = worst_case_sharpe(
        signals, prices, volumes=volumes, notional=100_000.0, scenarios=[]
    )
    assert (sharpe, name) == (0.0, "none")


# ══════════════════════════════════════════════════════════════════════════
# The evidence is derived, not asserted
# ══════════════════════════════════════════════════════════════════════════


def test_evidence_with_no_cost_is_detected_as_uncosted() -> None:
    """The claim checked against the numbers, not against the caller."""
    evidence = CertificationEvidence(gross_sharpe=2.0, net_sharpe=2.0)
    assert evidence.costs_applied is False
    assert "identical" in evidence.cost_detail


def test_evidence_with_a_cost_drag_counts_as_costed() -> None:
    evidence = CertificationEvidence(gross_sharpe=2.0, net_sharpe=1.6, cost_bps=4.0)
    assert evidence.costs_applied is True


def test_evidence_from_a_real_backtest_converts_mechanically() -> None:
    """The conversion is one-way, which is what stops a hand-built pass."""
    signals, prices, volumes = _trending_series()
    result = run_backtest(signals, prices, volumes=volumes, notional=100_000.0)
    evidence = CertificationEvidence.from_backtest(result)
    assert evidence.costs_applied is True
    assert evidence.gross_sharpe == result.gross_sharpe
    assert evidence.net_sharpe == result.net_sharpe
    assert evidence.n_trades == result.n_trades


def test_a_costless_backtest_converts_to_uncosted_evidence() -> None:
    """Running a backtest without costs still fails the cost check.

    This is the case the boolean signature used to wave through.
    """
    signals, prices, volumes = _trending_series()
    result = run_backtest(
        signals,
        prices,
        volumes=volumes,
        notional=100_000.0,
        costs=CostModel(commission_bps=0.0, half_spread_bps=0.0, impact_coefficient_bps=0.0),
    )
    assert CertificationEvidence.from_backtest(result).costs_applied is False


# ══════════════════════════════════════════════════════════════════════════
# The firewall consumes measurements
# ══════════════════════════════════════════════════════════════════════════


def test_a_strategy_with_no_evidence_cannot_certify(registry: StrategyRegistry) -> None:
    """The headline property: no backtest, no certification."""
    _register(registry)
    verdict = registry.build_verdict("momentum-1", "v1", 5.0, 1, pbo=0.01)
    assert verdict.verdict == "REJECTED"
    failed = {check.name for check in verdict.checks if not check.passed}
    assert {"fees_slippage_modelled", "capacity_modelled", "stress_tested", "execution_simulated"} <= failed


def test_a_fully_measured_strategy_certifies(registry: StrategyRegistry) -> None:
    _register(registry)
    evidence = CertificationEvidence(
        look_ahead_clean=True,
        panel_clean=True,
        survivorship_clean=True,
        gross_sharpe=2.4,
        net_sharpe=2.1,
        n_trades=180,
        cost_bps=4.0,
        participation=0.03,
        capacity_ceiling_usd=5_000_000.0,
        required_notional_usd=1_000_000.0,
        stress_scenarios_run=3,
        worst_stress_sharpe=0.4,
        worst_stress_scenario="crash",
        execution_latency_bars=2,
        execution_partial_fill_ratio=0.95,
        execution_rejected_rate=0.001,
    )
    verdict = registry.build_verdict(
        "momentum-1", "v1", 2.1, 1, pbo=0.01, evidence=evidence, regime_performance=_regimes()
    )
    assert verdict.verdict == "CERTIFIED", verdict.failure_reasons


def test_a_capacity_ceiling_below_the_mandate_fails(registry: StrategyRegistry) -> None:
    """A strategy that only works at $10k does not certify a $1m mandate."""
    _register(registry)
    evidence = CertificationEvidence(
        look_ahead_clean=True,
        panel_clean=True,
        survivorship_clean=True,
        gross_sharpe=2.4,
        net_sharpe=2.1,
        cost_bps=4.0,
        participation=0.03,
        capacity_ceiling_usd=10_000.0,
        required_notional_usd=1_000_000.0,
        stress_scenarios_run=3,
        worst_stress_sharpe=0.4,
        execution_latency_bars=2,
        execution_partial_fill_ratio=0.9,
    )
    verdict = registry.build_verdict("momentum-1", "v1", 2.1, 1, pbo=0.01, evidence=evidence)
    check = next(c for c in verdict.checks if c.name == "capacity_modelled")
    assert check.passed is False
    assert "below" in check.detail


def test_a_frictionless_execution_model_fails(registry: StrategyRegistry) -> None:
    """Perfect fills describe a venue that does not exist."""
    _register(registry)
    evidence = CertificationEvidence(
        look_ahead_clean=True,
        panel_clean=True,
        survivorship_clean=True,
        gross_sharpe=2.4,
        net_sharpe=2.1,
        cost_bps=4.0,
        capacity_ceiling_usd=5_000_000.0,
        required_notional_usd=1_000_000.0,
        stress_scenarios_run=3,
        worst_stress_sharpe=0.4,
        # Execution left at its frictionless defaults.
    )
    verdict = registry.build_verdict("momentum-1", "v1", 2.1, 1, pbo=0.01, evidence=evidence)
    check = next(c for c in verdict.checks if c.name == "execution_simulated")
    assert check.passed is False
    assert "frictionless" in check.detail


def test_operational_failures_yield_limits_not_rejection(
    registry: StrategyRegistry,
) -> None:
    """Refusing for a missing capacity model teaches teams to stop reporting it."""
    _register(registry)
    evidence = CertificationEvidence(
        look_ahead_clean=True,
        panel_clean=True,
        survivorship_clean=True,
        gross_sharpe=2.4,
        net_sharpe=2.1,
        cost_bps=4.0,
        execution_latency_bars=1,
    )
    verdict = registry.build_verdict("momentum-1", "v1", 2.1, 1, pbo=0.01, evidence=evidence)
    assert verdict.verdict == "CERTIFIED_WITH_LIMITS"
    assert "capacity_modelled" in verdict.failure_reasons


def test_the_verdict_records_the_measured_numbers(registry: StrategyRegistry) -> None:
    """A report has to be checkable, so the numbers go in the verdict."""
    _register(registry)
    evidence = CertificationEvidence(
        look_ahead_clean=True,
        panel_clean=True,
        survivorship_clean=True,
        gross_sharpe=2.4,
        net_sharpe=2.1,
        cost_bps=4.0,
        capacity_ceiling_usd=5_000_000.0,
        required_notional_usd=1_000_000.0,
        stress_scenarios_run=3,
        worst_stress_sharpe=0.4,
        execution_latency_bars=2,
    )
    verdict = registry.build_verdict("momentum-1", "v1", 2.1, 1, pbo=0.01, evidence=evidence)
    capacity = next(c for c in verdict.checks if c.name == "capacity_modelled")
    stress = next(c for c in verdict.checks if c.name == "stress_tested")
    assert capacity.value == pytest.approx(5_000_000.0)
    assert stress.value == pytest.approx(0.4)


def test_evidence_is_immutable_once_built() -> None:
    """Otherwise a mediocre result can be quietly improved after the fact."""
    evidence = CertificationEvidence(net_sharpe=1.0)
    with pytest.raises(ValueError):
        evidence.net_sharpe = 5.0


def test_a_certified_artifact_is_playable(registry: StrategyRegistry) -> None:
    """The end of the chain: an approved, certified artifact the fast tier may select."""
    _register(registry)
    evidence = CertificationEvidence(
        look_ahead_clean=True,
        panel_clean=True,
        survivorship_clean=True,
        gross_sharpe=2.4,
        net_sharpe=2.1,
        cost_bps=4.0,
        capacity_ceiling_usd=5_000_000.0,
        required_notional_usd=1_000_000.0,
        stress_scenarios_run=3,
        worst_stress_sharpe=0.4,
        execution_latency_bars=2,
    )
    registry.begin_validation("momentum-1", "v1", "risk-bot")
    registry.record_verdict(
        "momentum-1", "v1", registry.build_verdict(
            "momentum-1", "v1", 2.4, 1, pbo=0.01, evidence=evidence, regime_performance=_regimes()
        ),
        evidence=evidence,
    )
    registry.approve("momentum-1", "v1", validator="risk-bot", approver="admin")
    assert registry.get("momentum-1", "v1").status is ValidationStatus.APPROVED
    assert [a.ref for a in registry.playable()] == ["momentum-1:v1"]


def test_an_uncertified_artifact_is_never_playable(registry: StrategyRegistry) -> None:
    _register(registry)
    assert registry.playable() == []
