"""Tests for deriving a strategy's domain of competence from its certification verdict.

WHAT IS UNDER TEST, and why it is a derivation rather than a declaration.

The Layer 9 gate (`PlaybookRouter._check_competence`) has been correct since
`6b80af2` and was wired nowhere in production, so it enforced nothing outside tests.
The blocker was recorded as "a decision about which strategies are competent where".
That was wrong: certification already makes the decision, by adding one
`REGIME_CHECK_PREFIX + regime` check per regime in the supplied decomposition, and
passing it only when that regime is neither too thin to support a playbook nor
losing money net of costs.

So competence is read off the verdict. That is the whole reason to prefer it over
hand-declaring, and one test here exists purely to keep it honest:
`test_competence_is_derived_from_the_verdict_and_not_from_the_playbook`. If
competence were derived from playbooks, two strategies activating in the same
regime would be indistinguishable, and that test would fail.

THE FIXTURES ARE REAL CERTIFICATION OUTPUT, not hand-assembled checks.

Every verdict below comes from `StrategyRegistry.build_verdict` given a regime
decomposition. A hand-built `CertificationCheck` list would encode my belief about
the check naming, and the test would then only confirm that the derivation agrees
with my belief -- circular in the same way the derivation is careful not to be. The
probes that established the naming are in the session log, not in the assertions
here, so nothing in this file depends on them staying true: if certification renames
the check, the tests below fail rather than quietly passing against my memory.

One scope limit, stated rather than hidden. The derivation and the resolver are tested against verdicts the real
certification path produced. Two things
are NOT tested against real certification output, and the docstrings on those tests
say so where it matters:

  * `build_playbook` refuses a REJECTED verdict, so no playbook can be constructed
    from a real verdict until the real path certifies one -- which needs data that
    survives deflated-Sharpe, PSR and CSCV. Manufacturing that is designing a
    backtest to get past the firewall, so `_certified_verdict` stands in for the
    verdict the firewall would have issued, and only for tests whose subject is the
    router rather than the derivation.

  * `build_playbook_router` and `create_kernel` are asserted to hand the router a
    RESOLVER over the registry, not a snapshot of it, and the resolver is asked for
    a strategy certified after the kernel was built. That is the defect-58 regression
    test. A router with `competence=None` returns immediately from
    `_check_competence`, so reverting the wiring fails these tests; a resolver
    replaced by a snapshot fails them too, which a boot-time snapshot alone would
    not have.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kernel.competence import competence_from_verdict, competence_resolver
from kernel.playbook import (
    CompetenceNotDeclared,
    DomainOfCompetence,
    PlaybookRouter,
    Regime,
    StrategyIncompetent,
)
from kernel.strategy_registry import (
    REGIME_CHECK_PREFIX,
    CertificationCheck,
    CertificationEvidence,
    CertificationVerdict,
    RegimeSlice,
    StrategyRegistry,
)

# ══════════════════════════════════════════════════════════════════════════
# Fixtures: real certification output, and one hand-built verdict per edge case
# ══════════════════════════════════════════════════════════════════════════


def _evidence() -> CertificationEvidence:
    """Evidence consistent with the verdicts built from it.

    `record_verdict` refuses evidence whose Sharpe disagrees with the verdict, so
    the same object is passed to `build_verdict` and `record_verdict` and the two
    cannot drift apart. Numbers are chosen to be unremarkable rather than
    flattering: nothing in the derivation depends on them being good, only on the
    registry accepting that the measurements describe the trial that was certified.
    """
    return CertificationEvidence(
        gross_sharpe=2.0,
        net_sharpe=1.8,
        n_trades=500,
        cost_bps=4.0,
        participation=0.05,
        capacity_ceiling_usd=250_000.0,
        required_notional_usd=50_000.0,
        stress_scenarios_run=3,
        worst_stress_sharpe=0.4,
        worst_stress_scenario="crash_2008",
        execution_latency_bars=1.0,
        execution_partial_fill_ratio=0.01,
        execution_rejected_rate=0.0,
        look_ahead_clean=True,
        look_ahead_detail="no future bars in any feature",
        panel_clean=True,
        panel_detail="formation dates strictly precede test dates",
        survivorship_clean=True,
        survivorship_detail="point-in-time membership",
    )


def _handmade_verdict(
    checks: list[CertificationCheck],
    *,
    strategy_id: str = "momentum-1",
    strategy_version: str = "v1",
) -> CertificationVerdict:
    """A verdict with a check list supplied directly.

    Used only for the cases the real path cannot easily produce: a verdict with no
    regime decomposition at all, and a check naming a regime this build does not
    know. Those are absences and forward-compatibility cases, and manufacturing
    them any other way would mean corrupting the certification to test a reader of
    its output.
    """
    return CertificationVerdict(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        verdict="REJECTED",
        checks=checks,
        failure_reasons=("supplied for test",),
        observed_sharpe=1.0,
        deflated_sharpe=1.0,
        n_trials=200,
        policy_version="v1",
        validator_id="test-derivation",
        decided_at=datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    )


def _regime_check(regime: str, *, passed: bool) -> CertificationCheck:
    return CertificationCheck(
        name=f"{REGIME_CHECK_PREFIX}{regime}",
        passed=passed,
        value=1.5 if passed else -0.5,
        threshold=0.0,
    )


def _registry_with_decomposition() -> StrategyRegistry:
    """A real registry holding one strategy measured across three regimes.

    trending_up is profitable and well populated, so its check passes. crisis
    loses money. range_bound is profitable in principle but has three observations,
    below the minimum that would support a playbook. high_volatility is absent
    entirely, so nothing at all was measured there. Those four cases are the whole
    state space the derivation has to distinguish, and they come out of the
    certification's own policy rather than out of assertions here.
    """
    registry = StrategyRegistry()
    registry.register(
        strategy_id="momentum-1",
        version="v1",
        hypothesis_id="hyp-1",
        family="trend",
        dataset_ref={"ref": "ds-1"},
    )
    registry.begin_validation("momentum-1", "v1", validator_id="test-derivation")
    evidence = _evidence()
    verdict = registry.build_verdict(
        "momentum-1",
        "v1",
        observed_sharpe=2.0,
        n_trials=300,
        regime_performance={
            "trending_up": RegimeSlice(
                regime="trending_up", net_sharpe=2.5, n_observations=200
            ),
            "crisis": RegimeSlice(regime="crisis", net_sharpe=-0.5, n_observations=200),
            "range_bound": RegimeSlice(
                regime="range_bound", net_sharpe=0.02, n_observations=3
            ),
        },
        evidence=evidence,
    )
    registry.record_verdict("momentum-1", "v1", verdict, evidence=evidence)
    return registry


def _domain_of(registry: StrategyRegistry, ref: tuple[str, str]) -> DomainOfCompetence:
    """The competence the resolver hands back for one strategy, or a hard failure.

    Asserting rather than returning `None` is deliberate: a fixture that silently
    resolved to nothing would make every assertion below vacuous, since
    `is_competent` on a missing domain is a different question than the one being
    asked.
    """
    domain = competence_resolver(registry)(*ref)
    assert domain is not None, f"no competence resolved for {ref}"
    return domain


# ══════════════════════════════════════════════════════════════════════════
# Reading competence off a verdict
# ══════════════════════════════════════════════════════════════════════════


def test_a_measured_profitable_regime_confers_competence() -> None:
    assert _domain_of(_registry_with_decomposition(), ("momentum-1", "v1")).is_competent(
        Regime.TRENDING_UP
    )


def test_a_measured_losing_regime_is_incompetent_and_says_it_was_measured() -> None:
    """Recorded unsafe, not merely unclaimed.

    The distinction is the point of carrying `invalid` separately from `unaddressed`:
    "we measured it and it loses money" is a stronger and more actionable statement
    than "we never said", and a refusal that conflated them would send an operator
    looking for missing data that exists and says the strategy is bad.
    """
    domain = _domain_of(_registry_with_decomposition(), ("momentum-1", "v1"))
    assert not domain.is_competent(Regime.CRISIS)
    assert Regime.CRISIS in domain.invalid
    assert Regime.CRISIS not in domain.unaddressed()


def test_a_too_thin_regime_is_incompetent_and_says_it_was_measured() -> None:
    """Thin and losing are different failures and both are recorded.

    range_bound has a positive Sharpe and three observations. The certification
    refuses it for thinness, and the derivation must land on the same refusal --
    deriving competence from the Sharpe alone would read a three-observation
    reading as competence, which is exactly the sample-size mistake certification
    exists to prevent.
    """
    domain = _domain_of(_registry_with_decomposition(), ("momentum-1", "v1"))
    assert not domain.is_competent(Regime.RANGE_BOUND)
    assert Regime.RANGE_BOUND in domain.invalid


def test_a_never_measured_regime_is_unaddressed_rather_than_invalid() -> None:
    """Silence is not permission, and it is not a condemnation either.

    high_volatility was never decomposed, so the verdict says nothing about it.
    It must land in `unaddressed`, which is incompetent by the same opt-in rule
    the router applies, while staying out of `invalid`, which is reserved for
    measurements that came back negative.
    """
    domain = _domain_of(_registry_with_decomposition(), ("momentum-1", "v1"))
    assert not domain.is_competent(Regime.HIGH_VOLATILITY)
    assert Regime.HIGH_VOLATILITY in domain.unaddressed()
    assert Regime.HIGH_VOLATILITY not in domain.invalid


def test_competence_is_derived_from_the_verdict_and_not_from_the_playbook() -> None:
    """The anti-circularity property, as a test.

    Two strategies, both measured, with verdicts that disagree about the same
    regime: one passed the trending_up check and failed crisis, the other the
    reverse. If competence were read from the playbooks -- each playbook asserting
    the regimes it activates in -- both strategies would carry the same competence,
    because the playbooks are interchangeable here. Reading it off the verdicts
    separates them, and that separation is the property the derivation exists to
    provide: a playbook cannot widen its own permissions by existing.
    """
    trend_only = competence_from_verdict(
        _handmade_verdict(
            [_regime_check("trending_up", passed=True), _regime_check("crisis", passed=False)]
        )
    )
    crisis_only = competence_from_verdict(
        _handmade_verdict(
            [_regime_check("trending_up", passed=False), _regime_check("crisis", passed=True)]
        )
    )

    assert trend_only.is_competent(Regime.TRENDING_UP)
    assert not trend_only.is_competent(Regime.CRISIS)
    assert crisis_only.is_competent(Regime.CRISIS)
    assert not crisis_only.is_competent(Regime.TRENDING_UP)


def test_competence_is_keyed_by_strategy_version() -> None:
    """Two versions of one strategy get separate competences.

    Keyed on the pair, not the id, because a verdict is revocable and a new version
    is the mechanism for amending one. Sharing a competence across versions would
    let a v2 measurement retroactively authorise a v1 playbook.
    """
    registry = _registry_with_decomposition()
    evidence = _evidence()
    registry.register(
        strategy_id="momentum-1",
        version="v2",
        hypothesis_id="hyp-2",
        family="trend",
        dataset_ref={"ref": "ds-1"},
    )
    registry.begin_validation("momentum-1", "v2", validator_id="test-derivation")
    verdict = registry.build_verdict(
        "momentum-1",
        "v2",
        observed_sharpe=2.0,
        n_trials=300,
        regime_performance={
            "crisis": RegimeSlice(regime="crisis", net_sharpe=1.1, n_observations=200),
        },
        evidence=evidence,
    )
    registry.record_verdict("momentum-1", "v2", verdict, evidence=evidence)

    resolve = competence_resolver(registry)

    v1 = resolve("momentum-1", "v1")
    v2 = resolve("momentum-1", "v2")
    assert v1 is not None and v2 is not None, (
        "each version must resolve to its own domain; a resolver answering for only "
        "one of them would let a v1 measurement authorise a v2 playbook"
    )
    assert v1.is_competent(Regime.TRENDING_UP)
    assert not v1.is_competent(Regime.CRISIS)
    assert v2.is_competent(Regime.CRISIS)
    assert not v2.is_competent(Regime.TRENDING_UP)


# ══════════════════════════════════════════════════════════════════════════
# Refusing to derive what the measurements do not support
# ══════════════════════════════════════════════════════════════════════════


def test_a_verdict_with_no_regime_decomposition_refuses_to_yield_competence() -> None:
    """Raised, not returned empty.

    An empty declaration reads two ways -- "competent nowhere" and "never declared"
    -- and only the first is what the data says. Returning it would push the
    ambiguity onto every caller, and the likeliest response to a strategy that cannot
    trade anywhere would be to hand-write a competence declaration, which is the
    circular version of this whole arrangement.

    The message is matched deliberately. `DomainOfCompetence` rejects an empty valid
    set with a `ValidationError`, which is a `ValueError` subclass -- so a bare
    `pytest.raises(ValueError)` is satisfied whether this function raises or merely
    returns something the model then rejects. That made the first version of this
    test pass under a mutation that deleted the raise entirely, which is how it was
    found. Matching on the derivation's own words distinguishes the two.
    """
    verdict = _handmade_verdict(
        [
            CertificationCheck(name="deflated_sharpe", passed=True, value=1.8, threshold=0.95),
            CertificationCheck(name="stress_tested", passed=True, value=0.4, threshold=0.0),
        ]
    )
    with pytest.raises(ValueError, match="per-regime"):
        competence_from_verdict(verdict)


def test_a_passing_check_that_is_not_per_regime_confers_no_competence() -> None:
    """A verdict that passed everything except the regime gate yields nothing.

    Certification's other checks -- Sharpe, stress, execution, look-ahead -- say the
    strategy is sound in aggregate. They say nothing about where. A derivation that
    treated any passing check as competence would hand out a universal declaration
    from a strategy nobody decomposed, which is the unaddressed() case in reverse.

    Matched on the message for the reason given above: without it this test is
    satisfied by the model's own empty-declaration rejection, and so cannot tell the
    two failures apart.
    """
    verdict = _handmade_verdict(
        [
            CertificationCheck(name="deflated_sharpe", passed=True, value=1.8, threshold=0.95),
            CertificationCheck(name="execution_simulated", passed=True, value=1.0, threshold=1.0),
            CertificationCheck(name="purged_cv", passed=True, value=1.0, threshold=1.0),
        ]
    )
    with pytest.raises(ValueError, match="per-regime"):
        competence_from_verdict(verdict)


def test_a_check_naming_a_regime_this_build_does_not_know_confers_nothing() -> None:
    """A forward-compatible verdict fails closed.

    A verdict written by a newer registry may carry regimes this build has never
    heard of. The check passes, and reading it as competence would require inventing
    a `Regime` member to hold it. Skipping it means such a strategy trades nowhere
    on this build, which is correct: an unknown regime cannot be justified by a
    member of an enum that does not contain it, and guessing would be the definition
    of a hallucinated permission.
    """
    verdict = _handmade_verdict([_regime_check("martian_meltdown", passed=True)])
    with pytest.raises(ValueError):
        competence_from_verdict(verdict)

    mixed = competence_from_verdict(
        _handmade_verdict(
            [
                _regime_check("trending_up", passed=True),
                _regime_check("martian_meltdown", passed=True),
            ]
        )
    )
    assert mixed.is_competent(Regime.TRENDING_UP)
    assert set(mixed.valid) == {Regime.TRENDING_UP}


# ══════════════════════════════════════════════════════════════════════════
# Building the registry-wide competence
# ══════════════════════════════════════════════════════════════════════════


def test_an_undecomposed_strategy_resolves_to_no_competence() -> None:
    """Certified without being decomposed is the same as never measured.

    The fixture is a real verdict built WITHOUT a regime decomposition, not a
    strategy left uncertified. Those are different cases and conflating them
    produced a false pass on the first run of this test: an uncertified strategy is
    refused by the oracle before competence is consulted, so recording it here would
    point an operator at the wrong layer.
    """
    registry = _registry_with_decomposition()
    evidence = _evidence()
    registry.register(
        strategy_id="undecomposed-1",
        version="v1",
        hypothesis_id="hyp-9",
        family="unknown",
        dataset_ref={"ref": "ds-9"},
    )
    registry.begin_validation("undecomposed-1", "v1", validator_id="test-derivation")
    verdict = registry.build_verdict(
        "undecomposed-1", "v1", observed_sharpe=2.0, n_trials=300, evidence=evidence
    )
    registry.record_verdict("undecomposed-1", "v1", verdict, evidence=evidence)

    resolve = competence_resolver(registry)

    assert resolve("undecomposed-1", "v1") is None
    # And the strategy that WAS decomposed is unaffected by its neighbour.
    assert resolve("momentum-1", "v1") is not None


def test_a_strategy_that_was_never_certified_resolves_to_no_competence() -> None:
    """Uncertified, unknown, and undecomposed all resolve to None -- on purpose.

    Three different reasons for having no competence, one answer, because from the
    router's side they are the same fact: nothing has been shown, so nothing is
    granted. Distinguishing them would mean the resolver returning a reason code
    that `_check_competence` then has to translate back into prose, and the prose
    already exists.
    """
    registry = _registry_with_decomposition()
    registry.register(
        strategy_id="uncertified-1",
        version="v1",
        hypothesis_id="hyp-10",
        family="unknown",
        dataset_ref={"ref": "ds-10"},
    )
    resolve = competence_resolver(registry)

    assert resolve("uncertified-1", "v1") is None, "registered but never certified"
    assert resolve("momentum-1", "v9") is None, "known strategy, unknown version"
    assert resolve("no-such-strategy", "v1") is None, "not in the registry at all"


def test_an_undecomposed_strategy_is_refused_at_admission_with_a_reason() -> None:
    """The None becomes a refusal that explains itself, not a silent skip.

    This is what replaced the skip list. An eager builder had to accumulate the
    strategies it could not cover and log them, because nothing downstream would
    otherwise mention them. Resolving at admission puts the refusal at the point of
    use, where it already reads: undeclared, opt-in, and named.
    """
    registry = _registry_with_decomposition()
    resolve = competence_resolver(registry)
    router = PlaybookRouter(_ApprovingOracle(), competence=resolve)

    with pytest.raises(CompetenceNotDeclared) as caught:
        router.register(
            _playbook(regime=Regime.TRENDING_UP, strategy_id="undecomposed-1")
        )
    message = str(caught.value)
    assert "undecomposed-1" in message
    assert "no domain of competence" in message


def test_an_empty_registry_resolves_to_nothing_without_raising() -> None:
    """The degenerate case stated, so it cannot be mistaken for a bug later.

    Resolution must not raise on absence. A resolver that raised would turn "this
    strategy is not certified yet" into a crash on the admission path, which is the
    ordinary state of a registry during the hours before anything is approved.
    """
    resolve = competence_resolver(StrategyRegistry())
    assert resolve("anything", "v1") is None


# ══════════════════════════════════════════════════════════════════════════
# The production wiring -- the gap this closes
# ══════════════════════════════════════════════════════════════════════════


def test_the_production_router_is_built_with_a_resolver_over_the_registry() -> None:
    """The disclosed gap, pinned.

    Both production construction sites built `PlaybookRouter(oracle)` with no
    competence, so the Layer 9 gate enforced nothing outside tests. This asserts
    `build_playbook_router` hands the router a resolver bound to the registry's own
    verdicts. A router with `competence=None` returns immediately from
    `_check_competence`, so this fails if the wiring is reverted, and the failure is a
    refusal where a trade was expected rather than a slow drift.
    """
    from kernel.bootstrap import build_playbook_router

    registry = _registry_with_decomposition()
    router = build_playbook_router(registry)

    wired = router._competence  # noqa: SLF001 -- the wiring is the subject
    assert wired is not None, "the production router enforces no competence"
    assert callable(wired), "the router must resolve, not hold a boot-time snapshot"

    domain = wired("momentum-1", "v1")
    assert domain is not None
    assert domain.is_competent(Regime.TRENDING_UP)
    assert not domain.is_competent(Regime.CRISIS)


def test_a_router_given_derived_competence_refuses_a_playbook_it_did_not_measure() -> None:
    """The gate firing on derived data, not merely installed.

    The competence here is derived from a REAL verdict produced by the real
    certification path. The playbook's own verdict is hand-made and marked
    CERTIFIED, because `build_playbook` refuses a REJECTED verdict and the real path
    cannot be made to certify here without fabricating a backtest that survives
    deflated-Sharpe, PSR and CSCV -- that is, without designing data to get past the
    firewall this repository exists to keep. So the split is deliberate and stated:
    the derivation is tested against real certification output, and the router's
    enforcement of that derivation is tested with a well-formed verdict standing in
    for one the firewall would have issued. Neither half is asserted by the other.

    The oracle is local for the same reason. The production oracle is exercised by
    the wiring test above; what matters here is that a router handed derived
    competence refuses a playbook in a regime the measurements rejected, which is a
    claim about `_check_competence` and not about where the oracle came from.
    """
    registry = _registry_with_decomposition()
    resolve = competence_resolver(registry)
    domain = resolve("momentum-1", "v1")
    assert domain is not None
    assert not domain.is_competent(Regime.CRISIS), "fixture drifted; crisis now passes"

    router = PlaybookRouter(_ApprovingOracle(), competence=resolve)

    with pytest.raises(StrategyIncompetent) as caught:
        router.register(_playbook(regime=Regime.CRISIS))
    assert "crisis" in str(caught.value)

    # And the regime that WAS measured is admitted, so the refusal above is the
    # competence gate and not the oracle refusing everything.
    assert router.register(_playbook(regime=Regime.TRENDING_UP)) is not None


class _ApprovingOracle:
    """Certifies whatever it is asked about, so competence is the only gate in play.

    Stands in for `RegistryCertificationOracle`, which needs an APPROVED artifact and
    would otherwise decide the outcome before competence was consulted. Kept
    deliberately permissive: a strict oracle here would let the test pass for the
    wrong reason, which is the same mistake as a vacuous assertion.
    """

    def verdict_for(self, strategy_id: str, strategy_version: str):
        return _certified_verdict(strategy_id, strategy_version)

    def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
        return True


def _certified_verdict(
    strategy_id: str = "momentum-1", strategy_version: str = "v1"
) -> CertificationVerdict:
    """A verdict marked CERTIFIED, carrying the regime checks the derivation reads.

    `build_playbook` refuses to build from a rejection, so a playbook cannot be
    constructed at all without one of these. The regime checks are the same shape the
    real certification emits, which is what lets the derivation treat it identically
    to real output.
    """
    return CertificationVerdict(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        verdict="CERTIFIED",
        checks=[
            _regime_check("trending_up", passed=True),
            _regime_check("crisis", passed=False),
        ],
        failure_reasons=(),
        observed_sharpe=1.8,
        deflated_sharpe=1.8,
        n_trials=300,
        policy_version="v1",
        validator_id="test-derivation",
        decided_at=datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    )


def test_the_composition_root_sees_a_strategy_certified_after_it_was_built() -> None:
    """The test that would have caught defect 58, and the reason it exists.

    `create_kernel` derives competence. The registry is EMPTY at that moment --
    strategies are registered, backtested, certified and approved while the kernel is
    already running. An earlier version of this change snapshotted the registry at
    construction, so the snapshot was always empty and every strategy was
    permanently `CompetenceNotDeclared`. Five tests in
    `tests/test_playbook_composition.py` failed against it, and this file's own
    composition-root test asserted the broken behaviour with a comment calling it "the
    point worth asserting". A test that pins a defect is worse than no test.

    So: certify a strategy into a running kernel's registry, then ask that kernel's
    own router. Competence must be there, and it must refuse the regime the
    measurements rejected. The competence is NOT re-derived by hand here -- the
    assertion is about what the production router does, so it goes through the
    production router.
    """
    from kernel.bootstrap import create_kernel

    kernel = create_kernel()
    strategies = kernel.strategies

    evidence = _evidence()
    strategies.register(
        strategy_id="momentum-1",
        version="v1",
        hypothesis_id="hyp-1",
        family="trend",
        dataset_ref={"ref": "ds-1"},
    )
    strategies.begin_validation("momentum-1", "v1", validator_id="test-derivation")
    verdict = strategies.build_verdict(
        "momentum-1",
        "v1",
        observed_sharpe=2.0,
        n_trials=300,
        regime_performance={
            "trending_up": RegimeSlice(
                regime="trending_up", net_sharpe=2.5, n_observations=200
            ),
            "crisis": RegimeSlice(regime="crisis", net_sharpe=-0.5, n_observations=200),
        },
        evidence=evidence,
    )
    strategies.record_verdict("momentum-1", "v1", verdict, evidence=evidence)

    domain = kernel.playbook_router._competence("momentum-1", "v1")  # noqa: SLF001

    assert domain is not None, (
        "a strategy certified after the kernel was built has no competence, so the "
        "root snapshotted an empty registry and no playbook can ever be admitted"
    )
    assert domain.is_competent(Regime.TRENDING_UP)
    assert not domain.is_competent(Regime.CRISIS)


def test_the_check_name_comes_from_the_registry_rather_than_a_second_literal() -> None:
    """The pin promised by the constant's own docstring.

    `regime_sharpe:` was a bare f-string literal inside the certification loop, so
    nothing outside `kernel/strategy_registry.py` could refer to it and a consumer
    had to hardcode a copy. The constant exists so the two sides cannot drift, and
    this runs the real certification path and asserts the emitted check names are
    exactly `REGIME_CHECK_PREFIX + regime`. Renaming the constant on one side only
    makes the derivation silently empty -- every strategy incompetent everywhere --
    which fails CLOSED and so would read as a deliberate refusal rather than a
    broken join. This is the test that turns that into a visible failure.
    """
    registry = _registry_with_decomposition()
    verdict = registry.artifacts()[0].verdict
    assert verdict is not None

    emitted = {c.name for c in verdict.checks if c.name.startswith(REGIME_CHECK_PREFIX)}
    assert emitted == {
        f"{REGIME_CHECK_PREFIX}trending_up",
        f"{REGIME_CHECK_PREFIX}crisis",
        f"{REGIME_CHECK_PREFIX}range_bound",
    }

    # And the literal exists exactly once in the registry module: the constant.
    import kernel.strategy_registry as registry_module

    source = registry_module.__file__
    assert source is not None
    text = open(source, encoding="utf-8").read()
    assert text.count('"regime_sharpe:') == 1, (
        "the check prefix appears outside the constant, so the derivation and the "
        "certification can disagree about what the check is called"
    )


# ══════════════════════════════════════════════════════════════════════════
# Helpers needing the playbook constructor
# ══════════════════════════════════════════════════════════════════════════


def _playbook(*, regime: Regime, strategy_id: str = "momentum-1"):
    from kernel.playbook import Bound, PlaybookAction, PlaybookActionKind, build_playbook

    return build_playbook(
        playbook_id=f"pb-momentum-{regime.value}",
        version="v1",
        title=f"{regime.value} momentum",
        regime=regime,
        bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
        action=PlaybookAction(
            kind=PlaybookActionKind.TRADE, target_weight=0.15, reason="trend confirmed"
        ),
        strategy_id=strategy_id,
        strategy_version="v1",
        verdict=_certified_verdict(strategy_id=strategy_id),
        evidence=("core/quant_statistics.py",),
    )
