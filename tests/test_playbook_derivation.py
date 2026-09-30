"""The position size is derived from the backtest, not from a person (goal G120).

Until this work, ``publish_playbook`` took an ``action`` parameter: whoever
called it stated the position size, and the certification only proved the
*strategy* had been measured, not that the *size* had. That is the last place
in the decision path where a number reached the market without a measurement
behind it, and a parameter is the wrong shape for it — a caller under deadline
reaches for the parameter the way every previous caller did.

So there is no longer a parameter. The size is ``required_notional / book`` —
the mandate's own size — and what the measurements contribute is *permission*:
every check below must hold, and the first one that does not names itself in
the refusal. There is deliberately no fallback size, because a fallback is a
human judgment wearing arithmetic's clothes.

Three decisions in this suite deserve stating because they are the ones a
reviewer would question:

**The bounds stay caller-supplied.** Deriving thresholds from the same backtest
that justifies them is selection bias: the data cannot both choose the
threshold and vouch for it, which is the overfitting the PBO check exists to
catch. What the measurements do instead is gate — the regime must have been
measured profitable — and the bounds are then recorded under the content hash
alongside the basis that justifies trading them.

**``CERTIFIED_WITH_LIMITS`` is refused.** Limits mean a sub-metric was weak,
and a weak sub-metric is exactly what a position size must not be built on.
The middle verdict state exists so the firewall does not have to lie, not so
the fast tier can trade through a qualification nobody resolved.

**The evidence is retained on the artifact, not re-supplied.** A verdict
without its measurements is a conclusion without premises, and re-supplying
the evidence at publish time would let whoever publishes choose which numbers
justify the size. ``record_verdict`` requires the evidence and checks it
describes the certified trial; ``publish_playbook`` reads it off the artifact.
"""

from __future__ import annotations

import pytest

from core.backtest import RegimeSlice, regime_sharpes
from kernel.bootstrap import create_kernel, publish_playbook
from kernel.playbook import (
    Bound,
    DerivationRefused,
    PlaybookAction,
    PlaybookActionKind,
    Regime,
    build_measured_playbook,
    build_playbook,
    derive_action,
)
from kernel.strategy_registry import (
    CertificationEvidence,
    CertificationVerdict,
    StrategyRegistry,
    ValidationError,
)


@pytest.fixture()
def registry() -> StrategyRegistry:
    return StrategyRegistry(create_kernel().provenance)


def _evidence(**overrides: object) -> CertificationEvidence:
    """Measurements a real backtest and real detectors would produce."""
    fields: dict[str, object] = {
        "look_ahead_clean": True,
        "panel_clean": True,
        "survivorship_clean": True,
        "gross_sharpe": 2.1,
        "net_sharpe": 1.6,
        "n_trades": 180,
        "cost_bps": 6.0,
        "participation": 0.03,
        "capacity_ceiling_usd": 5_000_000.0,
        "required_notional_usd": 100_000.0,
        "stress_scenarios_run": 3,
        "worst_stress_sharpe": 0.4,
        "worst_stress_scenario": "crash",
        "execution_latency_bars": 2,
        "execution_partial_fill_ratio": 0.95,
        "execution_rejected_rate": 0.001,
    }
    fields.update(overrides)
    return CertificationEvidence(**fields)  # type: ignore[arg-type]


def _regimes() -> dict[str, RegimeSlice]:
    return {
        "trending_up": RegimeSlice("trending_up", 1.4, 300),
        "range_bound": RegimeSlice("range_bound", 0.3, 200),
    }


def _certified_verdict(
    registry: StrategyRegistry,
    *,
    observed: float = 2.1,
    evidence: CertificationEvidence | None = None,
    regimes: dict[str, RegimeSlice] | None = None,
) -> CertificationVerdict:
    """A verdict built from measurements, through the real firewall."""
    measured = evidence if evidence is not None else _evidence()
    return registry.build_verdict(
        "momentum-1",
        "v1",
        observed,
        140,
        n_observations=500,
        pbo=0.10,
        evidence=measured,
        regime_performance=regimes if regimes is not None else _regimes(),
    )


def _register(registry: StrategyRegistry) -> None:
    registry.register(
        strategy_id="momentum-1",
        version="v1",
        hypothesis_id="hyp-1",
        family="momentum",
        dataset_ref={"dataset_id": "btc_daily", "version": "v1.0"},
    )


# ══════════════════════════════════════════════════════════════════════════
# regime_sharpes: the measurement itself
# ══════════════════════════════════════════════════════════════════════════


def test_returns_are_split_by_label_with_counts() -> None:
    """Each slice reports its own Sharpe and how many observations support it."""
    returns = [0.02, 0.0] * 50 + [-0.01, 0.005] * 50
    labels = ["trending_up"] * 100 + ["range_bound"] * 100
    slices = regime_sharpes(returns, labels)
    assert set(slices) == {"trending_up", "range_bound"}
    assert slices["trending_up"].n_observations == 100
    assert slices["range_bound"].n_observations == 100
    assert slices["trending_up"].net_sharpe > 0
    assert slices["range_bound"].net_sharpe < 0


def test_a_misaligned_join_is_refused_not_truncated() -> None:
    """A label series that does not align is a join error.

    Silently dropping the tail would leave a decomposition describing a
    different sample than the backtest, and the difference would be invisible
    in every number downstream.
    """
    with pytest.raises(ValueError, match="misaligned|returns but.*labels"):
        regime_sharpes([0.01] * 10, ["up"] * 9)


def test_a_thin_slice_reports_zero_rather_than_raising() -> None:
    """One observation has no measurable edge, which is a finding, not an error.

    Refusing it here would conflate "unmeasurable" with "computation failed".
    The certification floor on observation counts is what refuses a playbook
    for a thin regime — that decision belongs to policy, not arithmetic.
    """
    slices = regime_sharpes([0.05], ["crisis"])
    assert slices["crisis"].net_sharpe == 0.0
    assert slices["crisis"].n_observations == 1


def test_empty_inputs_yield_an_empty_decomposition() -> None:
    """No labels is not an error; it is the input a strategy with no regimes
    would produce, and the firewall treats it as unmeasured downstream."""
    assert regime_sharpes([], []) == {}


def test_an_unknown_label_is_a_regime_not_an_error() -> None:
    """The measurement does not validate the taxonomy.

    A label the engine has never seen is still a slice of the sample, and
    rejecting it here would mean the measurement layer owns the regime
    vocabulary — which belongs to the playbook layer that interprets it.
    """
    slices = regime_sharpes([0.01, 0.02], ["something_new", "something_new"])
    assert slices["something_new"].n_observations == 2


# ══════════════════════════════════════════════════════════════════════════
# build_verdict: regime checks are measured, not asserted
# ══════════════════════════════════════════════════════════════════════════


def test_each_regime_gets_its_own_named_check(registry: StrategyRegistry) -> None:
    """The per-regime numbers live in the verdict, under their own names.

    Recorded inside the hashed verdict rather than beside it, so the playbook's
    ``verdict_hash`` covers the regime performance it gates on. A measurement
    stored next to the verdict could be swapped without invalidating anything;
    a measurement inside the verdict cannot.
    """
    _register(registry)
    verdict = _certified_verdict(registry)
    by_name = {c.name: c for c in verdict.checks}
    assert by_name["regime_sharpe:trending_up"].value == pytest.approx(1.4)
    assert by_name["regime_sharpe:range_bound"].value == pytest.approx(0.3)
    assert by_name["regime_sharpe:trending_up"].passed is True
    assert verdict.verdict == "CERTIFIED"


def test_a_missing_decomposition_fails_as_unmeasured(registry: StrategyRegistry) -> None:
    """The boolean this replaces: ``regime_decomposition=True`` believed."""
    _register(registry)
    verdict = registry.build_verdict(
        "momentum-1", "v1", 2.1, 140, n_observations=500, pbo=0.10, evidence=_evidence()
    )
    check = next(c for c in verdict.checks if c.name == "regime_decomposition")
    assert check.passed is False
    assert "never measured" in check.detail
    assert verdict.verdict == "CERTIFIED_WITH_LIMITS"


def test_an_empty_decomposition_measures_nothing(registry: StrategyRegistry) -> None:
    """An empty dict is not a decomposition; it is the absence of one with
    better formatting. Accepted as input, failed as a check."""
    _register(registry)
    verdict = registry.build_verdict(
        "momentum-1", "v1", 2.1, 140, n_observations=500, pbo=0.10,
        evidence=_evidence(), regime_performance={},
    )
    check = next(c for c in verdict.checks if c.name == "regime_decomposition")
    assert check.passed is False
    assert verdict.verdict == "CERTIFIED_WITH_LIMITS"


def test_a_thin_regime_fails_without_rejecting_the_strategy(
    registry: StrategyRegistry,
) -> None:
    """Twenty observations cannot support a playbook, but they do not impeach
    the strategy either. Operational, not statistical: it constrains *where*
    the strategy may trade, the way a low ceiling constrains *how much*."""
    _register(registry)
    verdict = _certified_verdict(
        registry,
        regimes={"trending_up": RegimeSlice("trending_up", 2.2, 20)},
    )
    check = next(c for c in verdict.checks if c.name == "regime_sharpe:trending_up")
    assert check.passed is False
    assert "too thin" in check.detail
    assert verdict.verdict == "CERTIFIED_WITH_LIMITS"
    assert "regime_sharpe:trending_up" in verdict.failure_reasons


def test_a_losing_regime_fails_without_rejecting_the_strategy(
    registry: StrategyRegistry,
) -> None:
    _register(registry)
    verdict = _certified_verdict(
        registry,
        regimes={
            "trending_up": RegimeSlice("trending_up", 1.4, 300),
            "crisis": RegimeSlice("crisis", -0.8, 120),
        },
    )
    check = next(c for c in verdict.checks if c.name == "regime_sharpe:crisis")
    assert check.passed is False
    assert "loses money" in check.detail
    assert verdict.verdict == "CERTIFIED_WITH_LIMITS"


def test_regime_failures_are_operational_not_integrity(registry: StrategyRegistry) -> None:
    """The classification matters: integrity or statistical failures reject,
    operational ones limit. A regime that lost money says where not to trade,
    not that the measurement was dishonest."""
    _register(registry)
    verdict = _certified_verdict(
        registry, regimes={"crisis": RegimeSlice("crisis", -0.5, 100)}
    )
    assert verdict.verdict == "CERTIFIED_WITH_LIMITS"


# ══════════════════════════════════════════════════════════════════════════
# record_verdict: the evidence is retained and bound
# ══════════════════════════════════════════════════════════════════════════


def test_recording_without_evidence_is_refused(registry: StrategyRegistry) -> None:
    """A verdict without retained measurements is a conclusion without premises.

    The playbook derivation sizes positions from the capacity ceiling, and it
    must read that ceiling off the artifact. An optional evidence parameter
    would let the first caller in a hurry skip it, and every playbook after
    that would be sized from numbers nobody retained.
    """
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk")
    verdict = _certified_verdict(registry)
    with pytest.raises(TypeError):
        registry.record_verdict("momentum-1", "v1", verdict)  # type: ignore[call-arg]


def test_mismatched_evidence_is_refused(registry: StrategyRegistry) -> None:
    """The binding that keeps a strong verdict from being recorded alongside
    weak measurements.

    The verdict's observed Sharpe and the evidence's gross Sharpe are the same
    trial's number reported in two places. A mismatch means the measurements
    describe a different backtest than the one that was certified — which is
    exactly how a team ships the good verdict with the convenient numbers.
    """
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk")
    verdict = _certified_verdict(registry, observed=2.1)
    other = _evidence(gross_sharpe=3.9, net_sharpe=3.5)
    with pytest.raises(ValidationError, match="does not match"):
        registry.record_verdict("momentum-1", "v1", verdict, evidence=other)


def test_matching_evidence_is_retained_on_the_artifact(
    registry: StrategyRegistry,
) -> None:
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk")
    evidence = _evidence()
    registry.record_verdict("momentum-1", "v1", _certified_verdict(registry), evidence=evidence)
    artifact = registry.get("momentum-1", "v1")
    assert artifact.evidence is not None
    assert artifact.evidence.capacity_ceiling_usd == pytest.approx(5_000_000.0)
    assert artifact.evidence.required_notional_usd == pytest.approx(100_000.0)


def test_a_rejected_verdict_keeps_its_measurements_too(
    registry: StrategyRegistry,
) -> None:
    """Failures are preserved, not discarded.

    A rejected strategy's measurements are the most expensive thing the
    research programme produced for it. Dropping them at record time would
    make the rejection unreviewable — nobody could later ask *how badly* it
    failed or *where*.
    """
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk")
    verdict = registry.build_verdict("momentum-1", "v1", 0.1, 10_000)
    evidence = CertificationEvidence(gross_sharpe=0.1, net_sharpe=-0.2)
    registry.record_verdict("momentum-1", "v1", verdict, evidence=evidence)
    assert registry.get("momentum-1", "v1").evidence is not None


def test_an_adapted_child_carries_no_measurements(registry: StrategyRegistry) -> None:
    """Adaptation resets the numbers along with the sign-off.

    A child that inherited its parent's capacity ceiling would be sized from a
    backtest of a different strategy — the same laundering the verdict
    immutability exists to prevent, one field over.
    """
    _register(registry)
    registry.begin_validation("momentum-1", "v1", "risk")
    evidence = _evidence()
    registry.record_verdict("momentum-1", "v1", _certified_verdict(registry), evidence=evidence)
    child = registry.adapt("momentum-1", "v1", "momentum-1-fitted", "v2")
    assert child.verdict is None
    assert child.evidence is None


# ══════════════════════════════════════════════════════════════════════════
# derive_action: the size is a consequence
# ══════════════════════════════════════════════════════════════════════════


def test_the_derived_size_is_the_mandate_over_the_book(
    registry: StrategyRegistry,
) -> None:
    """No human input anywhere in the number: the mandate needs 100k, the book
    holds 1M, so the weight is 10%. The measurements contribute permission,
    not magnitude."""
    _register(registry)
    verdict = _certified_verdict(registry)
    action, basis = derive_action(
        verdict=verdict,
        evidence=_evidence(),
        regime=Regime.TRENDING_UP,
        book_size_usd=1_000_000.0,
    )
    assert action.kind is PlaybookActionKind.TRADE
    assert action.target_weight == pytest.approx(0.10)
    assert action.max_notional_usd == pytest.approx(100_000.0)
    assert basis.verify(action) is True


def test_the_basis_records_every_input_the_size_depends_on(
    registry: StrategyRegistry,
) -> None:
    """An auditor recomputes the size from the basis alone. If any input were
    missing, the check would be against the derivation's word rather than its
    arithmetic."""
    _register(registry)
    verdict = _certified_verdict(registry)
    _, basis = derive_action(
        verdict=verdict,
        evidence=_evidence(),
        regime=Regime.TRENDING_UP,
        book_size_usd=2_000_000.0,
    )
    assert basis.book_size_usd == pytest.approx(2_000_000.0)
    assert basis.capacity_ceiling_usd == pytest.approx(5_000_000.0)
    assert basis.required_notional_usd == pytest.approx(100_000.0)
    assert basis.target_weight == pytest.approx(0.05)
    assert basis.regime is Regime.TRENDING_UP
    assert basis.regime_net_sharpe == pytest.approx(1.4)
    assert basis.policy_version == verdict.policy_version


def test_a_tampered_action_does_not_verify(registry: StrategyRegistry) -> None:
    """The basis is provenance for the size it derives, not a sticker.

    A weight edited after derivation must fail verification rather than ride
    on the basis's credibility.
    """
    _register(registry)
    verdict = _certified_verdict(registry)
    action, basis = derive_action(
        verdict=verdict,
        evidence=_evidence(),
        regime=Regime.TRENDING_UP,
        book_size_usd=1_000_000.0,
    )
    greedy = PlaybookAction(
        kind=PlaybookActionKind.TRADE,
        target_weight=0.90,
        max_notional_usd=100_000.0,
        reason="edited after derivation",
    )
    assert basis.verify(greedy) is False
    assert basis.verify(action) is True


def test_limits_are_refused_not_traded_through(registry: StrategyRegistry) -> None:
    """CERTIFIED_WITH_LIMITS means a sub-metric was weak, and a weak
    sub-metric is exactly what a position size must not be built on.

    The middle verdict state exists so the firewall does not have to lie, not
    so the fast tier can trade through a qualification nobody resolved.
    """
    _register(registry)
    verdict = _certified_verdict(
        registry, regimes={"crisis": RegimeSlice("crisis", -0.5, 100)}
    )
    assert verdict.verdict == "CERTIFIED_WITH_LIMITS"
    with pytest.raises(DerivationRefused, match="Limits qualify"):
        derive_action(
            verdict=verdict,
            evidence=_evidence(),
            regime=Regime.TRENDING_UP,
            book_size_usd=1_000_000.0,
        )


def test_a_rejection_is_refused(registry: StrategyRegistry) -> None:
    _register(registry)
    verdict = registry.build_verdict("momentum-1", "v1", 0.1, 10_000)
    with pytest.raises(DerivationRefused, match="refused this strategy"):
        derive_action(
            verdict=verdict,
            evidence=_evidence(),
            regime=Regime.TRENDING_UP,
            book_size_usd=1_000_000.0,
        )


def test_each_unmeasured_check_is_named_in_its_refusal(
    registry: StrategyRegistry,
) -> None:
    """Five separate tests in one body would hide which refusal fires first;
    parametrised cases would hide that the loop checks all five. The point is
    the property: *whichever* check is unmeasured, the refusal names it."""
    _register(registry)
    verdict = _certified_verdict(registry)
    cases = {
        "costs": {"gross_sharpe": 1.6, "net_sharpe": 1.6, "cost_bps": 0.0, "participation": 0.0},
        "capacity": {"capacity_ceiling_usd": 0.0},
        "stress": {"stress_scenarios_run": 0},
        "execution": {
            "execution_latency_bars": 0,
            "execution_partial_fill_ratio": 1.0,
            "execution_rejected_rate": 0.0,
        },
        "contamination": {"look_ahead_clean": None, "panel_clean": None, "survivorship_clean": None},
    }
    for name, overrides in cases.items():
        with pytest.raises(DerivationRefused, match=name):
            derive_action(
                verdict=verdict,
                evidence=_evidence(**overrides),
                regime=Regime.TRENDING_UP,
                book_size_usd=1_000_000.0,
            )


def test_an_unmeasured_regime_is_refused(registry: StrategyRegistry) -> None:
    """A playbook for a state the strategy was never observed in is a policy
    for a state nobody measured. The absence of a check is not a passing check."""
    _register(registry)
    verdict = _certified_verdict(registry)
    with pytest.raises(DerivationRefused, match="no measurement"):
        derive_action(
            verdict=verdict,
            evidence=_evidence(),
            regime=Regime.CRISIS,
            book_size_usd=1_000_000.0,
        )


def test_a_losing_regime_is_refused_with_its_numbers(registry: StrategyRegistry) -> None:
    """The firewall never produces a CERTIFIED verdict carrying a failed
    regime check — a failed regime always limits — so this branch is reached
    only by verdicts built outside the firewall. It exists anyway, because
    ``derive_action`` must not trust its inputs to have arrived through the
    governed path: a caller holding a hand-built CERTIFIED verdict must still
    be refused the losing regime, with the numbers that condemn it."""
    from kernel.strategy_registry import CertificationCheck

    _register(registry)
    verdict = _certified_verdict(registry)
    tampered_checks = [
        c for c in verdict.checks if c.name != "regime_sharpe:range_bound"
    ] + [
        CertificationCheck(
            name="regime_sharpe:range_bound",
            passed=False,
            value=-0.8,
            threshold=0.0,
            detail="120 observation(s) in 'range_bound', net Sharpe -0.8000; loses money net of costs",
        )
    ]
    edited = verdict.model_copy(update={"checks": tampered_checks})
    with pytest.raises(DerivationRefused, match="loses money|range_bound"):
        derive_action(
            verdict=edited,
            evidence=_evidence(),
            regime=Regime.RANGE_BOUND,
            book_size_usd=1_000_000.0,
        )


def test_a_mandate_beyond_the_ceiling_is_refused(registry: StrategyRegistry) -> None:
    """The edge does not scale to the mandate. Sizing past a measured ceiling
    is precisely what the ceiling exists to prevent — and the refusal is the
    playbook engine's first real test, that it can decline to describe a
    strategy that measured well but is too small to be worth trading at scale."""
    _register(registry)
    verdict = _certified_verdict(registry)
    evidence = _evidence(required_notional_usd=9_000_000.0)
    with pytest.raises(DerivationRefused, match="does not scale|beyond|ceiling"):
        derive_action(
            verdict=verdict,
            evidence=evidence,
            regime=Regime.TRENDING_UP,
            book_size_usd=10_000_000.0,
        )


def test_a_position_bigger_than_the_book_is_refused(registry: StrategyRegistry) -> None:
    """Leverage is not modelled anywhere in the certification, so a weight
    above 100% has no measurement behind any part of it."""
    _register(registry)
    verdict = _certified_verdict(registry)
    with pytest.raises(DerivationRefused, match="more than the book|leverage"):
        derive_action(
            verdict=verdict,
            evidence=_evidence(),
            regime=Regime.TRENDING_UP,
            book_size_usd=50_000.0,
        )


def test_a_dust_position_is_declined(registry: StrategyRegistry) -> None:
    """Below the policy floor a position cannot move portfolio-level outcomes
    beyond noise. Publishing a playbook for it manufactures a precision the
    portfolio cannot feel — so the engine declines rather than describes."""
    _register(registry)
    verdict = _certified_verdict(registry)
    with pytest.raises(DerivationRefused, match="policy floor|precision"):
        derive_action(
            verdict=verdict,
            evidence=_evidence(),
            regime=Regime.TRENDING_UP,
            book_size_usd=100_000_000.0,
        )


def test_a_nonexistent_book_is_refused(registry: StrategyRegistry) -> None:
    _register(registry)
    verdict = _certified_verdict(registry)
    with pytest.raises(DerivationRefused, match="must exist"):
        derive_action(
            verdict=verdict,
            evidence=_evidence(),
            regime=Regime.TRENDING_UP,
            book_size_usd=0.0,
        )


def test_deriving_from_something_other_than_a_verdict_is_refused(
    registry: StrategyRegistry,
) -> None:
    """A size derived from anything else is a size nobody certified."""
    _register(registry)
    with pytest.raises(TypeError, match="CertificationVerdict"):
        derive_action(
            verdict="CERTIFIED",
            evidence=_evidence(),
            regime=Regime.TRENDING_UP,
            book_size_usd=1_000_000.0,
        )
    with pytest.raises(TypeError, match="CertificationEvidence"):
        derive_action(
            verdict=_certified_verdict(registry),
            evidence={"net_sharpe": 9.9},
            regime=Regime.TRENDING_UP,
            book_size_usd=1_000_000.0,
        )


# ══════════════════════════════════════════════════════════════════════════
# build_measured_playbook: the governed production path
# ══════════════════════════════════════════════════════════════════════════


def test_a_measured_playbook_carries_its_basis(registry: StrategyRegistry) -> None:
    _register(registry)
    verdict = _certified_verdict(registry)
    playbook = build_measured_playbook(
        playbook_id="pb-momentum",
        version="v1",
        title="trend momentum",
        regime=Regime.TRENDING_UP,
        bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
        strategy_id="momentum-1",
        strategy_version="v1",
        verdict=verdict,
        evidence=_evidence(),
        book_size_usd=1_000_000.0,
        sources=("core/backtest.py",),
    )
    assert playbook.action.target_weight == pytest.approx(0.10)
    assert playbook.sizing_basis is not None
    assert playbook.sizing_basis.verify(playbook.action) is True
    assert playbook.sizing_basis.regime_net_sharpe == pytest.approx(1.4)


def test_the_basis_is_part_of_the_playbooks_identity(registry: StrategyRegistry) -> None:
    """The same action with different measurements behind it is a different
    claim about the world, so it hashes differently. Otherwise two playbooks
    could share an identity while justifying their size from different numbers."""
    _register(registry)
    verdict = _certified_verdict(registry)
    kwargs: dict[str, object] = {
        "playbook_id": "pb",
        "version": "v1",
        "title": "t",
        "regime": Regime.TRENDING_UP,
        "bounds": (Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
        "strategy_id": "momentum-1",
        "strategy_version": "v1",
        "verdict": verdict,
    }
    first = build_measured_playbook(evidence=_evidence(), book_size_usd=1_000_000.0, **kwargs)  # type: ignore[arg-type]
    second = build_measured_playbook(evidence=_evidence(), book_size_usd=2_000_000.0, **kwargs)  # type: ignore[arg-type]
    assert first.action.target_weight == pytest.approx(0.10)
    assert second.action.target_weight == pytest.approx(0.05)
    assert first.content_hash != second.content_hash


def test_a_basis_that_does_not_match_its_action_is_refused(
    registry: StrategyRegistry,
) -> None:
    """Provenance for a size nobody computed is worse than no provenance: it
    borrows the credibility of a derivation for a number that was written by
    hand."""
    _register(registry)
    verdict = _certified_verdict(registry)
    action, basis = derive_action(
        verdict=verdict,
        evidence=_evidence(),
        regime=Regime.TRENDING_UP,
        book_size_usd=1_000_000.0,
    )
    edited = PlaybookAction(
        kind=action.kind,
        target_weight=0.50,
        max_notional_usd=action.max_notional_usd,
        reason="edited",
    )
    with pytest.raises(DerivationRefused, match="does not match"):
        build_playbook(
            playbook_id="pb",
            version="v1",
            title="t",
            regime=Regime.TRENDING_UP,
            bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
            action=edited,
            strategy_id="momentum-1",
            strategy_version="v1",
            verdict=verdict,
            sizing_basis=basis,
        )


def test_a_hand_built_playbook_carries_no_basis(registry: StrategyRegistry) -> None:
    """The low-level constructor stays available for ABSTAIN and risk-off
    policies that express no position — and its products are visibly
    underived. The absence is the signal: a size with no basis is a claim."""
    _register(registry)
    verdict = _certified_verdict(registry)
    playbook = build_playbook(
        playbook_id="pb-risk-off",
        version="v1",
        title="risk off",
        regime=Regime.CRISIS,
        bounds=(Bound(feature="drawdown", minimum=0.15, maximum=1.0),),
        action=PlaybookAction(kind=PlaybookActionKind.ABSTAIN, reason="drawdown limit"),
        strategy_id="momentum-1",
        strategy_version="v1",
        verdict=verdict,
    )
    assert playbook.sizing_basis is None


# ══════════════════════════════════════════════════════════════════════════
# publish_playbook: the composition root reads, never accepts
# ══════════════════════════════════════════════════════════════════════════


def test_publish_reads_the_retained_measurements() -> None:
    """End to end through the real kernel: register, certify with measurements,
    record, approve, publish against a book — and the selected action is the
    derived size, with the basis on the playbook."""
    from kernel.playbook import PlaybookActionKind as Kind

    kernel = create_kernel()
    assert kernel.strategies is not None
    assert kernel.playbook_router is not None
    registry = kernel.strategies
    registry.register(
        strategy_id="momentum-1",
        version="v1",
        hypothesis_id="hyp-1",
        family="momentum",
        dataset_ref={},
    )
    registry.begin_validation("momentum-1", "v1", "validator-1")
    evidence = _evidence()
    verdict = registry.build_verdict(
        "momentum-1", "v1", 2.1, 140, n_observations=500, pbo=0.10,
        evidence=evidence, regime_performance=_regimes(),
    )
    assert verdict.verdict == "CERTIFIED"
    registry.record_verdict("momentum-1", "v1", verdict, evidence=evidence)
    registry.approve("momentum-1", "v1", validator="validator-1", approver="risk-1")

    playbook = publish_playbook(
        kernel.playbook_router,
        registry.get("momentum-1", "v1"),
        playbook_id="pb",
        version="v1",
        title="t",
        regime=Regime.TRENDING_UP,
        bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
        book_size_usd=1_000_000.0,
    )
    assert playbook.action.kind is Kind.TRADE
    assert playbook.action.target_weight == pytest.approx(0.10)
    assert playbook.sizing_basis is not None


def test_publish_refuses_an_artifact_with_no_retained_measurements() -> None:
    """A verdict with no measurements behind it cannot be sized from.

    Reachable only by constructing the artifact directly — ``record_verdict``
    requires evidence — which is exactly the case this guards: ``publish``
    takes the object, not a registry lookup, so it must not trust the object
    to have arrived through the governed path.
    """
    from kernel.strategy_registry import StrategyArtifact

    kernel = create_kernel()
    assert kernel.playbook_router is not None
    feeder = StrategyRegistry(create_kernel().provenance)
    _register(feeder)
    verdict = _certified_verdict(registry=feeder)
    bare = StrategyArtifact(
        strategy_id="momentum-1",
        version="v1",
        hypothesis_id="hyp-1",
        family="momentum",
        dataset_ref={},
        verdict=verdict,
    )
    with pytest.raises(ValueError, match="no retained measurements"):
        publish_playbook(
            kernel.playbook_router,
            bare,
            playbook_id="pb",
            version="v1",
            title="t",
            regime=Regime.TRENDING_UP,
            bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
            book_size_usd=1_000_000.0,
        )
