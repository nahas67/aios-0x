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

#: The repository root, for the one test that scans `kernel/` for a duplicated
#: check prefix. `parents[1]` because this file is `<repo>/tests/<name>.py`.
import pathlib
from datetime import UTC, datetime

import pytest

from kernel.competence import (
    IncompetentInEveryMeasuredRegime,
    competence_from_verdict,
    competence_resolver,
)
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

REPO = pathlib.Path(__file__).resolve().parents[1]

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
    verdict: str = "REJECTED",
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
        verdict=verdict,
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


def test_competence_depends_on_the_verdict_and_on_nothing_else() -> None:
    """Verdict-sensitivity: same playbook shape, different verdicts, different answers.

    Renamed from `..._not_from_the_playbook`, which it never earned. The old name
    claimed to demonstrate non-circularity; this test constructs no playbook at all,
    so it demonstrated only that the derivation reads the verdict. That is this
    repo's defect #54 again -- a test satisfied by something other than what it names.

    The non-circularity guarantee is real, and it is STRUCTURAL rather than tested
    here: `competence_from_verdict` takes a verdict and nothing else, so there is no
    parameter through which playbook data could enter. The test below asserts that
    signature directly, which is a stronger statement than any fixture could be,
    because no fixture can prove the absence of a code path.

    What remains here is the property a fixture CAN show: two strategies whose verdicts
    disagree about the same regime come out with different competences. If competence
    came from playbooks, and the playbooks were interchangeable, they would match.
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


def test_the_derivation_cannot_see_a_playbook_because_it_takes_no_parameters_for_one() -> None:
    """The structural half of non-circularity, asserted on the signature.

    A fixture can show that the derivation RESPONDS to a verdict. It cannot show that
    the derivation is INDEPENDENT of playbooks, because any such test would have to
    vary the playbooks and observe no change -- which a reader cannot distinguish from
    a test that forgot to vary anything. The signature can: if the function accepts a
    verdict and one optional verdict-shaped argument, there is no route by which
    playbook state could reach it.

    Checked by name and by shape, so a parameter renamed to something playbook-ish
    fails here rather than passing on a technicality.
    """
    import inspect

    from kernel import competence as competence_module

    params = list(inspect.signature(competence_module.competence_from_verdict).parameters)

    assert params == ["verdict"], (
        f"competence_from_verdict takes {params}; non-circularity depends on there "
        "being no route by which playbook state could reach the derivation"
    )
    assert not hasattr(competence_module.competence_from_verdict, "__wrapped__"), (
        "the derivation is wrapped, so the signature above may not be the real one"
    )


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
    # Matched on the message, not merely the type: `DomainOfCompetence` rejects an
    # empty valid set with a ValidationError that is also a ValueError, so a bare
    # `pytest.raises(ValueError)` is satisfied whether the derivation raised or merely
    # returned something the model then rejected. Two docstrings above this one explain
    # that; using the bare form here anyway is how the same defect returns next door.
    with pytest.raises(ValueError, match="per-regime"):
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


def test_the_check_prefix_is_a_constant_and_not_a_literal_anywhere_else_in_kernel() -> None:
    """The pin promised by the constant's docstring -- and it was too narrow.

    The first version of this test counted occurrences of the literal inside
    `kernel/strategy_registry.py` alone, and passed. An independent review then found
    two MORE copies in `kernel/playbook.py`, one of them on the production publish
    path. So the test certified a coupling that was still broken twice over: rename the
    constant and certification plus `competence.py` would have stayed in agreement
    while `build_measured_playbook` and `propose_candidates` silently stopped finding
    their checks -- and the former fails CLOSED, so it would have read as "this
    strategy does not work in that regime" rather than as a broken join.

    Two changes, both from that. The scan covers every module in `kernel/`, not one
    file. And it walks the AST for string CONSTANTS rather than counting text, because
    docstrings legitimately quote `regime_sharpe:<regime>` while explaining it -- a
    text count flags documentation of the rule as a violation of it, and a check that
    cries wolf gets deleted rather than fixed.

    The real certification path is also run, so the assertion is about the names the
    registry actually emits and not about a constant agreeing with itself.
    """
    import ast as _ast

    registry = _registry_with_decomposition()
    emitted = {c.name for c in registry.artifacts()[0].verdict.checks}
    assert f"{REGIME_CHECK_PREFIX}trending_up" in emitted
    assert f"{REGIME_CHECK_PREFIX}crisis" in emitted
    assert f"{REGIME_CHECK_PREFIX}range_bound" in emitted

    offenders: list[str] = []
    for module in sorted((REPO / "kernel").glob("*.py")):
        tree = _ast.parse(module.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Constant) or not isinstance(node.value, str):
                continue
            if not node.value.startswith("regime_sharpe:"):
                continue
            # The constant's own definition is the one legitimate occurrence.
            if module.name == "strategy_registry.py" and node.value == REGIME_CHECK_PREFIX:
                continue
            offenders.append(f"{module.name}:{node.lineno} = {node.value!r}")

    assert not offenders, (
        "the check prefix is duplicated in executable code; rename the constant and "
        f"these sites stop finding their checks silently: {offenders}"
    )


# ══════════════════════════════════════════════════════════════════════════
# Regressions for the four review findings fixed alongside this file
# ══════════════════════════════════════════════════════════════════════════


def test_a_strategy_that_lost_in_every_measured_regime_says_so() -> None:
    """The case `invalid` exists for must not be reported as "never measured".

    Before the fix these two produced a byte-identical `CompetenceNotDeclared`
    reading "has declared no domain of competence", and neither named the regimes. The
    message also pointed at hand-declaring a competence, which is the one remedy this
    design forbids -- `competence.py` calls it circular. So the most informative case
    in the whole arrangement was reported as the least informative one, and the
    operator was sent to invent a declaration for a strategy that had been measured
    and had lost.

    The error is asserted by TYPE as well as content, because the type is the load-
    bearing part: it is deliberately not a `ValueError`, so the resolver's
    `except ValueError` provably cannot fold it into the same `None` the absent-
    decomposition case returns. Asserting only the message would let a future change
    re-derive it as a `ValueError` and pass.
    """
    verdict = _handmade_verdict(
        [_regime_check("trending_up", passed=False), _regime_check("crisis", passed=False)]
    )

    with pytest.raises(IncompetentInEveryMeasuredRegime) as caught:
        competence_from_verdict(verdict)

    message = str(caught.value)
    assert "trending_up" in message and "crisis" in message, (
        "the refusal must name the regimes that were tried"
    )
    assert "competent in none" in message
    assert not isinstance(caught.value, ValueError), (
        "this error must not be a ValueError, or the resolver's except clause will "
        "swallow it back into the never-declared refusal"
    )


def test_the_two_kinds_of_no_competence_produce_different_refusals() -> None:
    """Measured-and-lost and never-measured must stay distinguishable.

    Asserted on the two messages together rather than on either alone, because the
    defect was precisely that they were the same string. A test on each case in
    isolation passed while they were identical.
    """
    from kernel.playbook import CompetenceNotDeclared

    loses = _handmade_verdict(
        [_regime_check("trending_up", passed=False), _regime_check("crisis", passed=False)]
    )
    unmeasured = _handmade_verdict([])

    with pytest.raises(IncompetentInEveryMeasuredRegime):
        competence_from_verdict(loses)
    with pytest.raises(ValueError, match="per-regime"):
        competence_from_verdict(unmeasured)

    assert issubclass(IncompetentInEveryMeasuredRegime, RuntimeError)
    assert not issubclass(IncompetentInEveryMeasuredRegime, CompetenceNotDeclared)


def test_a_recorded_verdict_cannot_be_re_pointed_at_a_wider_one() -> None:
    """Immutability is now enforced, not merely asserted in a docstring.

    `record_verdict` always refused a second verdict, but only through the METHOD, and
    `StrategyArtifact.verdict` was a plain field on a mutable model with the registry
    reachable as a public kernel attribute. Demonstrated before the guard: a strategy
    recorded as losing money in crisis became competent there, silently, for every
    playbook already admitted.

    That gap is worse than it looks, and the docstring on the guard says why:
    `PlaybookRouter.register` re-asks the oracle about certification on EVERY
    selection because a verdict can be revoked at any instant, while competence is
    checked once at admission. Competence would have inherited the verdict's
    mutability without inheriting the re-check.

    The first assignment must still work, or `record_verdict` cannot function -- so
    this asserts both halves, because a guard that blocked the first write would look
    identical to one that worked.
    """
    from kernel.strategy_registry import ValidationError

    registry = _registry_with_decomposition()
    artifact = registry.artifacts()[0]
    assert artifact.verdict is not None, "record_verdict failed to attach one"

    wider = _handmade_verdict([_regime_check("crisis", passed=True)])
    with pytest.raises(ValidationError, match="immutable"):
        artifact.verdict = wider

    domain = competence_resolver(registry)("momentum-1", "v1")
    assert domain is not None
    assert not domain.is_competent(Regime.CRISIS), (
        "competence widened after the refused assignment; the guard raised but did not "
        "prevent the change"
    )


def test_a_regime_performance_key_must_match_the_slice_it_names() -> None:
    """The key is what competence is read back through, so the two must agree.

    `build_verdict` named each per-regime check from the `regime_performance` dict
    KEY, while the resolver maps check names back through `Regime.value`. A caller
    passing `{"UP": RegimeSlice("trending_up", ...)}` therefore produced
    `regime_sharpe:UP`, which maps to nothing -- and the strategy was reported as never
    decomposed when it had been, which is the one diagnosis this module exists to get
    right. Pre-existing, but this change made the reader.

    Both halves asserted: the mismatch is refused, and the matching form still certifies
    with the name the resolver expects.
    """
    from kernel.strategy_registry import ValidationError

    registry = StrategyRegistry()
    registry.register(
        strategy_id="mismatch-1", version="v1", hypothesis_id="h", family="trend",
        dataset_ref={"ref": "d"},
    )
    registry.begin_validation("mismatch-1", "v1", validator_id="test-derivation")
    evidence = _evidence()

    with pytest.raises(ValidationError, match="does not match"):
        registry.build_verdict(
            "mismatch-1", "v1", observed_sharpe=2.0, n_trials=300,
            regime_performance={"UP": RegimeSlice("trending_up", 2.5, 300)},
            evidence=evidence,
        )

    ok = registry.build_verdict(
        "mismatch-1", "v1", observed_sharpe=2.0, n_trials=300,
        regime_performance={"trending_up": RegimeSlice("trending_up", 2.5, 300)},
        evidence=evidence,
    )
    assert f"{REGIME_CHECK_PREFIX}trending_up" in {c.name for c in ok.checks}


def test_the_resolver_lets_the_all_invalid_refusal_through() -> None:
    """The seam between the two functions is where the defect was, so test the seam.

    `competence_from_verdict` raising correctly is not the property that was broken.
    The defect was `competence_resolver` catching that raise and returning the same
    `None` it returns for a strategy nobody measured -- so the two cases reached the
    operator as one indistinguishable refusal. Every existing all-invalid test calls
    the derivation DIRECTLY and therefore passed throughout, while the resolver went on
    swallowing.

    Found by mutation: widening `except ValueError` to `except Exception` -- the tidy-up
    a future editor would plausibly make -- restored the swallowing and left the suite
    green. This test is the one that notices.

    A stand-in registry is used rather than a real one because the property is about
    what the resolver does with the raise, and building a real CERTIFIED_WITH_LIMITS
    verdict means fabricating a backtest that clears deflated-Sharpe, PSR and CSCV --
    declined for the same reason as in the rest of this file.
    """
    verdict = _handmade_verdict(
        [_regime_check("trending_up", passed=False), _regime_check("crisis", passed=False)],
        verdict="CERTIFIED_WITH_LIMITS",
    )

    class _Registry:
        def get(self, strategy_id: str, version: str):
            return type("_Artifact", (), {"verdict": verdict})()

    with pytest.raises(IncompetentInEveryMeasuredRegime) as caught:
        competence_resolver(_Registry())("loser-1", "v1")

    assert "trending_up" in str(caught.value) and "crisis" in str(caught.value)


def test_the_resolver_still_returns_none_when_nothing_was_measured() -> None:
    """The other half of the seam, so the fix cannot be made by swallowing both.

    Asserted separately and immediately after the propagation test on purpose. A
    change that made the resolver propagate EVERYTHING would also pass the test above,
    and would be a strictly worse regression: a strategy that was simply never certified
    would raise out of the admission path instead of being refused with an explanation.
    The two cases must diverge, and both directions have to be pinned.
    """
    verdict = _handmade_verdict([])

    class _Registry:
        def get(self, strategy_id: str, version: str):
            return type("_Artifact", (), {"verdict": verdict})()

    assert competence_resolver(_Registry())("loser-1", "v1") is None

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
