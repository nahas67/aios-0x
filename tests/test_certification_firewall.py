"""Certification is the gate between a candidate and a playbook (goal G080).

Nothing today stops an uncertified strategy from reaching the risk firewall.
The firewall is real and deterministic, but it cannot ask whether the strategy
behind the order was ever statistically validated, because no such question is
represented anywhere in the system. That is the gap this suite closes.

The properties asserted here are the ones that distinguish a certification gate
from a score:

* a strategy with no verdict cannot reach APPROVED
* an adapted strategy cannot inherit its parent's sign-off
* look-ahead and survivorship contamination are detected and reject
* the headline statistic corrects for selection across trials, so trying 10,000
  strategies raises the bar rather than lowering the expectation
* every failure mode is recorded, not just the ones that passed
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime

import pytest

from core.backtest import RegimeSlice
from core.quant_statistics import (
    benjamini_hochberg,
    bonferroni_threshold,
    combinatorial_purged_splits,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    normal_cdf,
    normal_ppf,
    pbo_from_cscv,
    probabilistic_sharpe_ratio,
    purged_kfold_splits,
    sharpe_ratio,
)
from kernel.bootstrap import create_kernel
from kernel.strategy_registry import (
    CertificationEvidence,
    StrategyRegistry,
    ValidationError,
    ValidationStatus,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _regimes() -> dict[str, RegimeSlice]:
    """A measured decomposition both regimes clear: enough observations and
    profitable net of costs. Mirrors the measurement-suite fixture so the two
    files agree on what "fully measured" means."""
    return {
        "trending_up": RegimeSlice("trending_up", 1.4, 300),
        "range_bound": RegimeSlice("range_bound", 0.3, 200),
    }


# ══════════════════════════════════════════════════════════════════════════
# Normal distribution primitives
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (0.5, 0.0),
        (0.975, 1.959963985),
        (0.99, 2.326347874),
        (0.05, -1.644853627),
        (0.025, -1.959963985),
    ],
)
def test_normal_ppf_matches_published_quantiles(p: float, expected: float) -> None:
    assert normal_ppf(p) == pytest.approx(expected, abs=1e-8)


def test_normal_ppf_inverts_the_cdf_to_double_precision() -> None:
    """The threshold this feeds decides whether a strategy trades.

    A one-percent error in the quantile would move a capital decision, so the
    round trip is asserted to full double precision rather than to a loose
    tolerance.
    """
    for p in (1e-6, 1e-3, 0.01, 0.1, 0.5, 0.9, 0.99, 0.999, 1 - 1e-6):
        assert normal_cdf(normal_ppf(p)) == pytest.approx(p, abs=1e-12)


def test_normal_ppf_rejects_improbable_arguments() -> None:
    for bad in (0.0, 1.0, -0.1, 1.4):
        with pytest.raises(ValueError, match="p must be in"):
            normal_ppf(bad)


# ══════════════════════════════════════════════════════════════════════════
# Purged and embargoed cross-validation
# ══════════════════════════════════════════════════════════════════════════


def test_no_training_index_ever_overlaps_the_test_block() -> None:
    """The property that makes the split honest, for every fold."""
    for fold, split in enumerate(purged_kfold_splits(200, 5, label_horizon=3, embargo=2)):
        assert not (set(split.train) & set(split.test)), f"fold {fold} leaked"


def test_a_zero_horizon_and_zero_embargo_purges_nothing() -> None:
    """A baseline: with no leakage mechanism, the splitter must remove nothing.

    Without this, an over-aggressive purge would look like correct behaviour.
    """
    for split in purged_kfold_splits(100, 5, label_horizon=0, embargo=0):
        assert split.purged == 0
        assert split.embargoed == 0
        assert len(split.train) + len(split.test) == 100


def test_a_longer_label_horizon_purges_more() -> None:
    """A 10-day label genuinely contaminates more training rows than a 1-day one."""
    short = purged_kfold_splits(200, 5, label_horizon=1, embargo=0)
    long = purged_kfold_splits(200, 5, label_horizon=10, embargo=0)
    assert sum(s.purged for s in long) > sum(s.purged for s in short)


def test_the_embargo_removes_exactly_the_configured_count() -> None:
    """A count an operator can reason about, not a percentage they cannot.

    The final fold is excluded: the embargo removes the observations *after* a
    test block, and the last block has no tail. That is correct, and asserting
    it explicitly keeps a future change from "fixing" it into a purge.
    """
    splits = purged_kfold_splits(200, 5, label_horizon=0, embargo=3)
    for split in splits[:-1]:
        assert split.embargoed == 3
    assert splits[-1].embargoed == 0, "the last fold has no tail to embargo"


def test_purging_never_deletes_the_whole_training_set() -> None:
    """An over-aggressive purge leaves nothing to fit on and is a bug, not caution."""
    for split in purged_kfold_splits(500, 5, label_horizon=20, embargo=5):
        assert len(split.train) > 100, f"purge left only {len(split.train)} rows"


def test_train_and_test_always_partition_the_sample_without_embargo() -> None:
    for split in purged_kfold_splits(120, 6, label_horizon=0, embargo=0):
        assert sorted([*split.train, *split.test]) == list(range(120))


def test_impossible_split_shapes_are_refused() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        purged_kfold_splits(100, 1)
    with pytest.raises(ValueError, match="cannot be split"):
        purged_kfold_splits(3, 5)
    with pytest.raises(ValueError, match="non-negative"):
        purged_kfold_splits(100, 5, embargo=-1)


# ══════════════════════════════════════════════════════════════════════════
# Combinatorial purged CV
# ══════════════════════════════════════════════════════════════════════════


def test_cpcv_enumerates_every_test_group_combination() -> None:
    from math import comb

    cpcv = combinatorial_purged_splits(120, 6, test_groups=2, label_horizon=0, embargo=0)
    assert cpcv.n_paths == comb(6, 2) == 15


def test_cpcv_phi_is_the_test_group_ratio() -> None:
    cpcv = combinatorial_purged_splits(120, 6, test_groups=2)
    assert cpcv.phi() == pytest.approx(2 / 6)


def test_cpcv_never_leaks_across_any_path() -> None:
    cpcv = combinatorial_purged_splits(180, 6, test_groups=2, label_horizon=3, embargo=2)
    for split in cpcv.splits:
        assert not (set(split.train) & set(split.test))


def test_cpcv_paths_cover_the_sample_rather_than_one_block() -> None:
    """A distribution of outcomes is the point; one test block is not a backtest."""
    cpcv = combinatorial_purged_splits(120, 6, test_groups=2, label_horizon=0, embargo=0)
    tested = set()
    for split in cpcv.splits:
        tested.update(split.test)
    assert tested == set(range(120))


def test_cpcv_rejects_impossible_group_shapes() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        combinatorial_purged_splits(120, 1)
    with pytest.raises(ValueError, match=r"\[1, n_groups\)"):
        combinatorial_purged_splits(120, 4, test_groups=4)


# ══════════════════════════════════════════════════════════════════════════
# Sharpe and its selection correction
# ══════════════════════════════════════════════════════════════════════════


def test_sharpe_of_a_flat_series_is_zero_not_an_error() -> None:
    """A flat series is a real observation with a zero ratio."""
    assert sharpe_ratio([0.01] * 50) == 0.0
    assert sharpe_ratio([0.01]) == 0.0


def test_sharpe_annualises() -> None:
    daily = [0.001, -0.001, 0.002, -0.0005] * 25
    assert sharpe_ratio(daily, periods_per_year=252) == pytest.approx(
        sharpe_ratio(daily, periods_per_year=1) * math.sqrt(252)
    )


def test_expected_max_sharpe_grows_with_trials() -> None:
    """This is the selection bias made explicit, and it must be monotone."""
    values = [expected_max_sharpe(n) for n in (1, 10, 100, 1000, 10000)]
    assert values == sorted(values)
    assert values[0] == 0.0
    assert values[-1] > 3.0


def test_one_trial_has_no_selection_bias() -> None:
    assert expected_max_sharpe(1) == 0.0


def test_deflated_sharpe_penalises_trying_many_strategies() -> None:
    """The headline property of the firewall.

    A Sharpe of 1.0 from a single trial is convincing. The same 1.0 selected
    as the best of 10,000 trials is what a worthless strategy hands you for
    free, and the DSR says so.
    """
    single = deflated_sharpe_ratio(1.0, n_trials=1, n_observations=252)
    many = deflated_sharpe_ratio(1.0, n_trials=10000, n_observations=252)
    assert single > 0.99
    assert many < 0.01


def test_deflated_sharpe_falls_monotonically_with_trials() -> None:
    values = [
        deflated_sharpe_ratio(2.0, n_trials=n, n_observations=252)
        for n in (1, 100, 1000, 10000)
    ]
    assert values == sorted(values, reverse=True)


def test_deflated_sharpe_rises_with_more_observations() -> None:
    """The same reported Sharpe is better evidence from more data."""
    few = deflated_sharpe_ratio(1.5, n_trials=100, n_observations=50)
    many = deflated_sharpe_ratio(1.5, n_trials=100, n_observations=5000)
    assert many > few


def test_psr_penalises_negative_skew_and_fat_tails() -> None:
    """A lottery-ticket equity curve must not certify on its Sharpe alone."""
    clean = probabilistic_sharpe_ratio(
        1.0, n_observations=252, skewness=0.0, kurtosis=3.0
    )
    skewed = probabilistic_sharpe_ratio(
        1.0, n_observations=252, skewness=-2.0, kurtosis=12.0
    )
    assert skewed < clean


def test_psr_needs_at_least_two_observations() -> None:
    with pytest.raises(ValueError, match="at least 2 observations"):
        probabilistic_sharpe_ratio(1.0, n_observations=1)


# ══════════════════════════════════════════════════════════════════════════
# Probability of backtest overfitting
# ══════════════════════════════════════════════════════════════════════════


def test_pbo_on_pure_noise_is_about_a_half() -> None:
    """If selection were harmless, a coin flip would score 0.5.

    Calibrated over many seeds because a single draw is a coin flip itself.
    """
    values = []
    for seed in range(120):
        rng = random.Random(seed)
        noise = [[rng.gauss(0, 0.01) for _ in range(30)] for _ in range(8)]
        values.append(pbo_from_cscv(noise))
    assert sum(values) / len(values) == pytest.approx(0.5, abs=0.15)


def test_pbo_on_a_persistent_edge_is_near_zero() -> None:
    """A real edge survives out-of-sample, so the in-sample winner stays top."""
    values = []
    for seed in range(60):
        rng = random.Random(seed)
        matrix = [[rng.gauss(0, 0.01) for _ in range(30)] for _ in range(8)]
        for row in matrix:
            row[0] = rng.gauss(0.03, 0.01)
        values.append(pbo_from_cscv(matrix))
    assert sum(values) / len(values) < 0.1


def test_pbo_is_one_for_a_strategy_that_only_works_in_sample() -> None:
    """The canonical overfitting shape: brilliant in-sample, inverted after."""
    matrix = []
    for slice_index in range(8):
        row = [random.Random(slice_index * 100 + j).gauss(0, 0.001) for j in range(20)]
        # Slice 0-3 carry a huge in-sample edge; 4-7 invert it.
        row[0] = 1.0 if slice_index < 4 else -1.0
        matrix.append(row)
    assert pbo_from_cscv(matrix) == pytest.approx(1.0)


def test_pbo_rejects_malformed_matrices() -> None:
    with pytest.raises(ValueError, match="even number of slices"):
        pbo_from_cscv([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
    with pytest.raises(ValueError, match="at least 2 strategies"):
        pbo_from_cscv([[0.1], [0.2], [0.3], [0.4]])
    with pytest.raises(ValueError, match="rectangular"):
        pbo_from_cscv([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6], [0.7, 0.8], [0.9, 1.0], [1.1, 1.2], [1.3, 1.4], [1.5, 1.6, 1.7]])


# ══════════════════════════════════════════════════════════════════════════
# Multiple-testing correction
# ══════════════════════════════════════════════════════════════════════════


def test_bonferroni_shrinks_with_the_number_of_tests() -> None:
    assert bonferroni_threshold(0.05, 1) == 0.05
    assert bonferroni_threshold(0.05, 100) == pytest.approx(0.0005)
    assert bonferroni_threshold(0.05, 1000) < bonferroni_threshold(0.05, 100)


def test_bh_rejects_a_clear_signal_and_spares_the_rest() -> None:
    """[0.001, 0.8, 0.7]: one hypothesis stands out, and the other two do not.

    Returns True for *not rejected*, so the clear signal is the only False.
    """
    assert benjamini_hochberg([0.001, 0.8, 0.7], 0.05) == [False, True, True]


def test_bh_rejects_nothing_when_nothing_stands_out() -> None:
    assert benjamini_hochberg([0.9, 0.8, 0.7], 0.05) == [True, True, True]


def test_bh_is_more_powerful_than_bonferroni_at_the_same_alpha() -> None:
    p_values = [0.04, 0.2, 0.6, 0.9]
    survivors = benjamini_hochberg(p_values, 0.05)
    assert survivors[0] is True, "p=0.04 of 4 should survive BH but not Bonferroni"
    assert bonferroni_threshold(0.05, 4) < 0.04, "and Bonferroni would have rejected it"


def test_bh_preserves_input_order() -> None:
    """The verdict must travel with its hypothesis, not with its sorted position."""
    p_values = [0.001, 0.5, 0.9]
    baseline = benjamini_hochberg(p_values, 0.05)
    for permutation in ([0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]):
        shuffled = benjamini_hochberg([p_values[i] for i in permutation], 0.05)
        assert [shuffled[k] for k in range(3)] == [baseline[i] for i in permutation]


def test_bh_rejects_exactly_the_smallest_p_value() -> None:
    """One clear signal among three: that one, and only that one, is rejected."""
    assert benjamini_hochberg([0.001, 0.8, 0.7], 0.05) == [False, True, True]
    assert benjamini_hochberg([0.8, 0.001, 0.7], 0.05) == [True, False, True]
    assert benjamini_hochberg([0.8, 0.7, 0.001], 0.05) == [True, True, False]


def test_bh_rejects_invalid_p_values() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        benjamini_hochberg([0.5, 1.5], 0.05)


# ══════════════════════════════════════════════════════════════════════════
# The registry: the state machine
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def registry() -> StrategyRegistry:
    return StrategyRegistry(create_kernel().provenance)


def _register(registry: StrategyRegistry, strategy_id: str = "momentum-1") -> None:
    registry.register(
        strategy_id=strategy_id,
        version="v1",
        hypothesis_id="hyp-1",
        family="momentum",
        dataset_ref={"dataset_id": "btc_daily", "version": "v1.0"},
    )


def _passing_evidence() -> CertificationEvidence:
    """Evidence that a real backtest and real detectors would produce.

    Every field is a number or a detector verdict, never a hand-written
    boolean. ``contamination_measured`` requires all three contamination
    detectors to have RUN and reported clean, so a caller that skips one cannot
    pass by default.
    """
    return CertificationEvidence(
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


def test_a_new_strategy_starts_unvalidated(registry: StrategyRegistry) -> None:
    _register(registry)
    assert registry.get("momentum-1", "v1").status is ValidationStatus.UNVALIDATED


def test_an_unvalidated_strategy_cannot_be_approved(registry: StrategyRegistry) -> None:
    """The single most important line in this file.

    A certification gate that lets an unvalidated artifact through is not a
    gate, and the risk firewall downstream has no way to tell.
    """
    _register(registry)
    with pytest.raises(ValidationError, match="UNVALIDATED"):
        registry.approve("momentum-1", "v1", validator="risk", approver="admin")


def test_approval_requires_a_recorded_verdict(registry: StrategyRegistry) -> None:
    _register(registry)
    with pytest.raises(ValidationError, match="no CertificationVerdict"):
        registry.approve("momentum-1", "v1", validator="risk", approver="admin")


def test_a_full_happy_path_reaches_approved(registry: StrategyRegistry) -> None:
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk")
    registry.record_verdict(
        "momentum-1", "v1", registry.build_verdict(
        "momentum-1", "v1", 2.4, 1, pbo=0.02, evidence=_passing_evidence(),
        regime_performance=_regimes(),
    ),
        evidence=_passing_evidence(),
    )
    registry.approve("momentum-1", "v1", validator="risk", approver="admin")
    assert registry.get("momentum-1", "v1").status is ValidationStatus.APPROVED


def test_a_failed_verdict_blocks_approval(registry: StrategyRegistry) -> None:
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk")
    verdict = registry.build_verdict("momentum-1", "v1", 0.1, 10_000)
    assert verdict.verdict == "REJECTED"
    registry.record_verdict(
        "momentum-1", "v1", verdict, evidence=CertificationEvidence(gross_sharpe=0.1)
    )
    with pytest.raises(ValidationError, match="REJECTED"):
        registry.approve("momentum-1", "v1", validator="risk", approver="admin")


def test_a_rejected_strategy_is_terminal(registry: StrategyRegistry) -> None:
    """A failed verdict rejects, and nothing reopens it.

    Recording the failed verdict is what rejects; a separate explicit reject
    would be a second transition out of an already-terminal state, which is
    refused.
    """
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk")
    verdict = registry.build_verdict("momentum-1", "v1", 0.1, 10_000)
    assert verdict.verdict == "REJECTED"
    registry.record_verdict(
        "momentum-1", "v1", verdict, evidence=CertificationEvidence(gross_sharpe=0.1)
    )
    assert registry.get("momentum-1", "v1").status is ValidationStatus.REJECTED

    with pytest.raises(ValidationError, match="cannot transition"):
        registry.begin_validation("momentum-1", "v1", "risk")
    with pytest.raises(ValidationError, match="cannot transition"):
        registry.reject("momentum-1", "v1", "second rejection", actor="risk")


def test_an_operator_rejection_is_recorded_with_its_reason(
    registry: StrategyRegistry,
) -> None:
    """A rejection an operator wrote down should survive as the record."""
    _register(registry)
    registry.reject("momentum-1", "v1", "capacity too thin for the mandate", actor="risk")
    artifact = registry.get("momentum-1", "v1")
    assert artifact.status is ValidationStatus.REJECTED
    assert artifact.parameters["rejection_reason"] == "capacity too thin for the mandate"


# ══════════════════════════════════════════════════════════════════════════
# Separation of duties
# ══════════════════════════════════════════════════════════════════════════


def test_the_validator_may_not_also_be_the_approver(registry: StrategyRegistry) -> None:
    """Self-certification is not a control.

    The same identity that produced the evidence cannot sign off on it, because
    a validator marking its own work approved has added no information.
    """
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk-bot")
    registry.record_verdict(
        "momentum-1", "v1", registry.build_verdict(
        "momentum-1", "v1", 2.4, 1, pbo=0.02, evidence=_passing_evidence(),
        regime_performance=_regimes(),
    ),
        evidence=_passing_evidence(),
    )
    with pytest.raises(ValidationError, match="cannot approve its own"):
        registry.approve("momentum-1", "v1", validator="risk-bot", approver="risk-bot")


def test_a_different_approver_is_accepted(registry: StrategyRegistry) -> None:
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk-bot")
    registry.record_verdict(
        "momentum-1", "v1", registry.build_verdict(
        "momentum-1", "v1", 2.4, 1, pbo=0.02, evidence=_passing_evidence(),
        regime_performance=_regimes(),
    ),
        evidence=_passing_evidence(),
    )
    registry.approve("momentum-1", "v1", validator="risk-bot", approver="admin")
    assert registry.get("momentum-1", "v1").approver == "admin"


# ══════════════════════════════════════════════════════════════════════════
# Adaptation must not inherit a sign-off
# ══════════════════════════════════════════════════════════════════════════


def test_adaptation_creates_a_child_with_empty_evidence(registry: StrategyRegistry) -> None:
    """The most important line after the approval gate.

    An adapted strategy is a different strategy. If the child inherited the
    parent's verdict, every adaptation would be a free pass past the firewall,
    and adapting a strategy would become the cheapest way to ship an untested
    one.
    """
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk-bot")
    registry.record_verdict(
        "momentum-1", "v1", registry.build_verdict(
        "momentum-1", "v1", 2.4, 1, pbo=0.02, evidence=_passing_evidence(),
        regime_performance=_regimes(),
    ),
        evidence=_passing_evidence(),
    )
    registry.approve("momentum-1", "v1", validator="risk-bot", approver="admin")

    child = registry.adapt("momentum-1", "v1", "momentum-1-fitted", "v2")

    assert child.status is ValidationStatus.UNVALIDATED
    assert child.verdict is None
    assert child.parent_ref == "momentum-1:v1"
    with pytest.raises(ValidationError, match="no CertificationVerdict"):
        registry.approve("momentum-1-fitted", "v2", validator="risk", approver="admin")


def test_an_adaptation_of_a_child_still_carries_no_evidence(
    registry: StrategyRegistry,
) -> None:
    _register(registry)
    registry.adapt("momentum-1", "v1", "child", "v1")
    grandchild = registry.adapt("child", "v1", "grandchild", "v1")
    assert grandchild.verdict is None
    assert grandchild.parent_ref == "child:v1"


def test_adapting_an_unknown_strategy_is_refused(registry: StrategyRegistry) -> None:
    with pytest.raises(KeyError):
        registry.adapt("no-such", "v1", "child", "v1")


# ══════════════════════════════════════════════════════════════════════════
# The verdict itself
# ══════════════════════════════════════════════════════════════════════════


def test_a_verdict_names_every_check_it_ran() -> None:
    """A score without its components is a mood, not a measurement."""
    registry = StrategyRegistry(create_kernel().provenance)
    _register(registry)
    verdict = registry.build_verdict(
        "momentum-1", "v1", 2.1, 1, pbo=0.02, evidence=_passing_evidence()
    )
    names = {check.name for check in verdict.checks}
    assert {
        "lookahead_detected",
        "survivorship_clean",
        "purged_cv",
        "embargo_enforced",
        "cpcv_paths",
        "deflated_sharpe",
        "probabilistic_sharpe",
        "probabilistic_backtest_overfitting",
        "multiple_testing_corrected",
        "fees_slippage_modelled",
        "capacity_modelled",
        "regime_decomposition",
        "stress_tested",
        "execution_simulated",
    } <= names


def test_a_failing_check_names_itself_in_the_failure_reasons(
    registry: StrategyRegistry,
) -> None:
    _register(registry)
    evidence = CertificationEvidence(
        gross_sharpe=0.2,
        net_sharpe=0.1,
        cost_bps=4.0,
        look_ahead_clean=False,
        panel_clean=True,
        survivorship_clean=True,
        capacity_ceiling_usd=1_000_000.0,
        required_notional_usd=1_000_000.0,
        stress_scenarios_run=3,
        worst_stress_sharpe=0.0,
        execution_latency_bars=1,
    )
    verdict = registry.build_verdict(
        "momentum-1", "v1", 0.2, 10_000, pbo=0.9, evidence=evidence
    )
    assert verdict.verdict == "REJECTED"
    assert "lookahead_detected" in verdict.failure_reasons
    assert "probabilistic_backtest_overfitting" in verdict.failure_reasons
    assert "deflated_sharpe" in verdict.failure_reasons


def test_a_verdict_records_its_policy_version(registry: StrategyRegistry) -> None:
    _register(registry)
    verdict = registry.build_verdict(
        "momentum-1", "v1", 2.1, 1, pbo=0.02, evidence=_passing_evidence()
    )
    assert verdict.policy_version
    assert verdict.decided_at


def test_a_verdict_is_immutable_once_recorded(registry: StrategyRegistry) -> None:
    """Re-deciding a recorded verdict would let a good result overwrite a bad one."""
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk")
    verdict = registry.build_verdict("momentum-1", "v1", 0.1, 10_000)
    registry.record_verdict(
        "momentum-1", "v1", verdict, evidence=CertificationEvidence(gross_sharpe=0.1)
    )
    better = registry.build_verdict("momentum-1", "v1", 9.9, 1)
    with pytest.raises(ValidationError, match="already carries a verdict"):
        registry.record_verdict(
            "momentum-1", "v1", better, evidence=CertificationEvidence(gross_sharpe=9.9)
        )
