"""Domain of competence: where a strategy may and may not operate.

Architecture section 2, Layer 9 states ``Every strategy/model has:
DomainOfCompetence`` and gives the worked example ``valid: TREND_UP NORMAL_VOL
HIGH_LIQUIDITY / invalid: EARNINGS FLASH_CRASH LIQUIDITY_CRISIS``. Until this
file, that was the only clause of Layer 9 with no implementation anywhere in the
tree -- the registry audit recorded it as an outstanding gap under G100 rather
than letting the goal read as fully landed.

What this is not, and the distinction the module's own docstring demands: it is
not :class:`RegimeCondition`. A ``RegimeCondition`` answers *when does this
playbook fire* and is bounds arithmetic over one playbook. Competence answers
*where is this strategy valid* and is membership in a named set spanning every
playbook a strategy owns. Collapsing the two would leave "may this strategy trade
in a crisis?" with no single answer, because the answer would depend which
playbook the router happened to be holding.

The property under test throughout is the one that is easy to get backwards:

    competence is opt-in.

An unlisted regime is refused, not permitted. If it were permitted, ``valid``
would be decorative and ``invalid`` would be the only operative contract, and
every regime added to the :class:`Regime` enum would silently widen what every
strategy may trade. Each refusal test below is therefore paired with an
admission test on the same object -- otherwise "refuses an unlisted regime"
would also pass against an implementation that refuses everything.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from kernel.playbook import (
    Bound,
    CompetenceNotDeclared,
    DomainOfCompetence,
    InconsistentCompetence,
    PlaybookAction,
    PlaybookActionKind,
    PlaybookRouter,
    Regime,
    StrategyCompetence,
    StrategyIncompetent,
    build_playbook,
)
from kernel.strategy_registry import CertificationVerdict

# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════

#: The architecture's own example, translated to this module's enum. Momentum is
#: the trend strategy; a momentum book is the canonical case for being wrecked by
#: a crisis, which is why it is the one declared invalid below.
MOMENTUM = frozenset({Regime.TRENDING_UP, Regime.RANGE_BOUND})
CRISIS = frozenset({Regime.CRISIS})


def _verdict(strategy_id: str = "momentum-1", strategy_version: str = "v1") -> CertificationVerdict:
    """A real ``CertificationVerdict``, constructed directly.

    Built here rather than fetched from ``LiveOracle`` because that distinction
    is the point of two tests: a playbook can only be *built* from a verdict
    object, while *admission* is decided separately by the oracle. Routing one
    through the other would mean an uncertified strategy could never reach the
    certification check at all, and the two refusals would be indistinguishable.
    """
    from kernel.strategy_registry import CertificationCheck

    return CertificationVerdict(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        verdict="CERTIFIED",
        checks=[
            CertificationCheck(name="deflated_sharpe", passed=True, value=1.8, threshold=0.95)
        ],
        failure_reasons=(),
        observed_sharpe=1.8,
        deflated_sharpe=1.8,
        n_trials=200,
        policy_version="v1",
        validator_id="test-oracle",
        decided_at=datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    )


class LiveOracle:
    """An oracle that can revoke, so competence is not mistaken for certification.

    Deliberately separate from the competence registry: the two answer different
    questions and a test that used one to stand in for the other would pass
    without either being exercised.
    """

    def __init__(self, certified: set[tuple[str, str]] | None = None) -> None:
        self.certified = certified if certified is not None else {("momentum-1", "v1")}

    def verdict_for(self, strategy_id: str, strategy_version: str) -> Any | None:
        if (strategy_id, strategy_version) not in self.certified:
            return None
        return _verdict(strategy_id, strategy_version)

    def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
        return (strategy_id, strategy_version) in self.certified


def _domain(
    valid: frozenset[Regime] = MOMENTUM,
    invalid: frozenset[Regime] = CRISIS,
) -> DomainOfCompetence:
    """A competence declaration, with ``invalid`` emptied when ``valid`` claims CRISIS.

    The overlap validator would otherwise reject the widening cases below for a
    reason that has nothing to do with what they are testing. Written as a
    subtraction rather than by changing the call sites so the invariant under
    test -- that the two sets are disjoint -- stays visible in the tests too.
    """
    return DomainOfCompetence(valid=valid, invalid=invalid - valid)


def _playbook(
    *,
    playbook_id: str = "pb-momentum-trend",
    version: str = "v1",
    regime: Regime = Regime.TRENDING_UP,
    strategy_id: str = "momentum-1",
    strategy_version: str = "v1",
):
    return build_playbook(
        playbook_id=playbook_id,
        version=version,
        title=f"{regime.value} momentum",
        regime=regime,
        bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
        action=PlaybookAction(
            kind=PlaybookActionKind.TRADE, target_weight=0.15, reason="trend confirmed"
        ),
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        verdict=_verdict(strategy_id, strategy_version),
        evidence=("core/quant_statistics.py",),
    )


def _router(
    *, certified: set[tuple[str, str]] | None = None, competence: StrategyCompetence | None
) -> PlaybookRouter:
    return PlaybookRouter(LiveOracle(certified), competence=competence)


def _wired(
    valid: frozenset[Regime] = MOMENTUM, invalid: frozenset[Regime] = CRISIS
) -> PlaybookRouter:
    """A router with momentum-1:v1 competent, which is the common case."""
    registry = StrategyCompetence()
    registry.declare("momentum-1", "v1", _domain(valid, invalid))
    return _router(competence=registry)


# ══════════════════════════════════════════════════════════════════════════
# The declaration itself must be coherent
# ══════════════════════════════════════════════════════════════════════════


def test_a_declaration_claiming_no_regime_is_refused() -> None:
    """``valid=()`` is a strategy forbidden everywhere, not one that was never written.

    The two must not be expressible by the same value, or a forgotten declaration
    and a deliberate total prohibition would be indistinguishable.
    """
    with pytest.raises(ValidationError, match="at least one valid regime"):
        DomainOfCompetence(valid=frozenset())


def test_a_regime_cannot_be_both_valid_and_invalid() -> None:
    """A self-contradicting declaration is refused at construction, not resolved at use.

    If ``invalid`` silently overrode ``valid``, a typo in either list would resolve
    to the permissive reading with nothing to show for it.
    """
    with pytest.raises(ValidationError, match="both valid and invalid"):
        DomainOfCompetence(valid=MOMENTUM, invalid=frozenset({Regime.TRENDING_UP}))


def test_a_declaration_is_immutable() -> None:
    """Frozen. A competence that could be edited is one whose history is unknown."""
    domain = _domain()

    with pytest.raises(ValidationError):
        domain.valid = frozenset({Regime.CRISIS})


# ══════════════════════════════════════════════════════════════════════════
# Competence is opt-in -- the load-bearing property
# ══════════════════════════════════════════════════════════════════════════


def test_a_declared_valid_regime_is_competent() -> None:
    """The admission half. Without this pair, every refusal below would also pass
    against an implementation that refuses everything."""
    domain = _domain()

    assert domain.is_competent(Regime.TRENDING_UP)
    assert domain.is_competent(Regime.RANGE_BOUND)


def test_an_explicitly_invalid_regime_is_incompetent() -> None:
    domain = _domain()

    assert not domain.is_competent(Regime.CRISIS)


@pytest.mark.parametrize("regime", [Regime.HIGH_VOLATILITY, Regime.TRENDING_DOWN])
def test_a_regime_in_neither_list_is_incompetent(regime: Regime) -> None:
    """The decision that is easy to get backwards.

    Silence is not permission. If an unlisted regime were permitted, ``valid``
    would carry no weight, ``invalid`` would be the whole contract, and adding a
    member to the ``Regime`` enum would widen every strategy's permissions
    without any declaration being edited.
    """
    domain = _domain()

    assert not domain.is_competent(regime), f"{regime.value} must not be presumed permitted"


def test_every_regime_is_either_valid_invalid_or_unaddressed() -> None:
    """The three sets partition the enum, so no regime is silently both or neither.

    Written as a partition check rather than three separate facts because the
    failure mode of a fourth regime being added is that it lands in no set and
    the earlier tests keep passing.
    """
    domain = _domain()
    valid, invalid = domain.valid, domain.invalid
    unaddressed = domain.unaddressed()

    assert valid | invalid | unaddressed == frozenset(Regime)
    assert not (valid & invalid)
    assert not (valid & unaddressed)
    assert not (invalid & unaddressed)


def test_a_new_regime_member_is_not_silently_permitted() -> None:
    """The permission set is exactly what was declared, not the enum minus refusals.

    Stated as an equality over the two sets rather than a spot check on
    ``HIGH_VOLATILITY``, because "the one I remembered to test" is not the claim.
    """
    domain = _domain()

    permitted = {r for r in Regime if domain.is_competent(r)}

    assert permitted == set(MOMENTUM)


# ══════════════════════════════════════════════════════════════════════════
# A refusal says which kind of refusal it is
# ══════════════════════════════════════════════════════════════════════════


def test_a_refusal_distinguishes_recorded_unsafe_from_never_claimed() -> None:
    """The reason `invalid` earns its place.

    With ``invalid`` absent, refusing CRISIS and refusing TRENDING_DOWN would be
    the same event with the same text, and an operator debugging either would be
    guessing. "Recorded as unsafe" is a strategy that learned something; "never
    claimed" is a coverage gap. Both refuse; both say which.
    """
    domain = _domain()

    unsafe = domain.refusal(Regime.CRISIS)
    unclaimed = domain.refusal(Regime.HIGH_VOLATILITY)

    assert "unsafe" in unsafe
    assert "not a regime this strategy declared" in unclaimed
    assert unsafe != unclaimed


def test_a_competent_regime_produces_no_refusal_text() -> None:
    """``refusal`` on a competent regime returns empty rather than raising.

    A caller that has already decided a regime is invalid should not be handed a
    second opinion, but it should not be handed an exception either.
    """
    assert _domain().refusal(Regime.TRENDING_UP) == ""


def test_a_refusal_names_the_unaddressed_regimes() -> None:
    """A coverage gap is worth surfacing: silence about three regimes is the finding."""
    message = _domain().refusal(Regime.HIGH_VOLATILITY)

    assert "high_volatility" in message
    assert "trending_down" in message


# ══════════════════════════════════════════════════════════════════════════
# One competence per strategy, never two
# ══════════════════════════════════════════════════════════════════════════


def test_declaring_the_same_competence_twice_is_accepted() -> None:
    """Idempotent on equality. Re-declaring an identical declaration is a no-op,
    not a conflict -- otherwise a duplicate declaration in two composition roots
    would read as an attempt to change it."""
    registry = StrategyCompetence()

    registry.declare("momentum-1", "v1", _domain())
    registry.declare("momentum-1", "v1", _domain())

    assert registry.declared() == (("momentum-1", "v1"),)


def test_changing_a_declared_competence_is_refused() -> None:
    """The reason competence is immutable and the reason it may be checked once.

    Widening what a strategy may trade in is a new strategy version with a new
    verdict. If it were an edit, one ``strategy_id`` would mean two different
    things at two points in the same replay, and the admission-time check would
    be unsound the moment the declaration changed.
    """
    registry = StrategyCompetence()
    registry.declare("momentum-1", "v1", _domain())

    with pytest.raises(InconsistentCompetence, match="cannot replace it"):
        registry.declare("momentum-1", "v1", _domain(valid=frozenset({Regime.CRISIS})))


def test_an_undeclared_strategy_reads_as_absent_not_omitted() -> None:
    """``None`` means "never declared", which is what makes the router refuse."""
    registry = StrategyCompetence()

    assert registry.for_strategy("momentum-1", "v1") is None
    assert registry.for_strategy("unknown-9", "v1") is None


def test_competence_is_keyed_by_version() -> None:
    """v1's competence must not cover v2. Keying on strategy_id alone would let a
    new version inherit the old version's permissions without ever declaring them."""
    registry = StrategyCompetence()
    registry.declare("momentum-1", "v1", _domain())

    assert registry.for_strategy("momentum-1", "v2") is None


# ══════════════════════════════════════════════════════════════════════════
# Enforcement at the router
# ══════════════════════════════════════════════════════════════════════════


def test_a_playbook_inside_competence_is_admitted() -> None:
    """The admission half at the router, for the same reason as the model tests."""
    router = _wired()

    assert router.register(_playbook(regime=Regime.TRENDING_UP)).ref


def test_a_playbook_in_an_explicitly_invalid_regime_is_refused() -> None:
    """The case that motivates the whole clause.

    Momentum is certified for TRENDING_UP and is trusted there. It is not trusted
    in a crisis, and a playbook carrying it into a crisis is the strategy being
    asked to do the one thing it recorded it cannot do.
    """
    router = _wired()

    with pytest.raises(StrategyIncompetent, match="crisis"):
        router.register(_playbook(playbook_id="pb-momentum-crisis", regime=Regime.CRISIS))


def test_a_playbook_in_an_undeclared_regime_is_refused() -> None:
    """Silence is not permission, at the router as well as in the model."""
    router = _wired()

    with pytest.raises(StrategyIncompetent, match="high_volatility"):
        router.register(
            _playbook(playbook_id="pb-momentum-hv", regime=Regime.HIGH_VOLATILITY)
        )


def test_a_playbook_for_an_undeclared_strategy_is_refused() -> None:
    """No declaration means no permission at all.

    If an undeclared strategy could register freely, competence would be opt-in
    only for strategies that someone remembered to declare -- which is the same
    silent-widening hole as presuming unlisted regimes permitted, one level up.
    """
    registry = StrategyCompetence()
    registry.declare("momentum-1", "v1", _domain())
    router = _router(
        certified={("momentum-1", "v1"), ("never-declared", "v1")},
        competence=registry,
    )

    with pytest.raises(CompetenceNotDeclared, match="no domain of competence"):
        router.register(_playbook(strategy_id="never-declared"))


def test_the_refusal_names_the_strategy_and_its_valid_set() -> None:
    """An operator holding this error can act on it without opening the registry."""
    router = _wired()

    with pytest.raises(StrategyIncompetent) as caught:
        router.register(_playbook(playbook_id="pb-mc", regime=Regime.CRISIS))

    message = str(caught.value)
    assert "momentum-1:v1" in message
    assert "trending_up" in message
    assert "crisis" in message


def test_a_refused_playbook_is_not_left_registered() -> None:
    """Refusal must be atomic. A playbook that raised and then appeared in the
    registry would let the next, differently-shaped registration pass on top of it."""
    router = _wired()

    with pytest.raises(StrategyIncompetent):
        router.register(_playbook(playbook_id="pb-momentum-crisis", regime=Regime.CRISIS))

    assert router.registered() == ()


def test_competence_is_checked_against_the_strategy_not_the_playbook() -> None:
    """Two playbooks, one strategy, one answer.

    The reason competence is not a playbook field: if each playbook carried its
    own, "may this strategy trade in a crisis?" would depend which playbook the
    router was holding. Both playbooks here belong to a strategy that forbids
    CRISIS, and both are refused for the same reason.
    """
    router = _wired()
    router.register(_playbook(playbook_id="pb-a", regime=Regime.TRENDING_UP))

    with pytest.raises(StrategyIncompetent):
        router.register(_playbook(playbook_id="pb-b", regime=Regime.CRISIS))


def test_a_router_without_a_competence_registry_enforces_no_competence() -> None:
    """The gate is opt-in at the router, and that is stated rather than hidden.

    Every pre-existing caller constructs a router this way, so this must keep
    working. It is also the honest boundary of the feature: wiring a registry is
    what turns enforcement on, and a composition root that meant to enforce and
    did not wire one would otherwise believe it had.
    """
    router = _router(competence=None)

    assert router.register(_playbook(regime=Regime.CRISIS)).ref


def test_certification_and_competence_are_separate_refusals() -> None:
    """An uncertified strategy is refused for the certification reason even when it
    is competent, so neither check can be mistaken for having covered the other."""
    registry = StrategyCompetence()
    registry.declare("uncleared-1", "v1", _domain(valid=frozenset({Regime.TRENDING_UP})))
    router = _router(certified={("momentum-1", "v1")}, competence=registry)

    with pytest.raises(Exception) as caught:
        router.register(_playbook(strategy_id="uncleared-1"))

    assert "not certified" in str(caught.value)
    assert "competence" not in str(caught.value)


def test_a_competent_and_certified_strategy_admits_in_every_valid_regime() -> None:
    """Not just the one regime tested above: competence admits where declared."""
    router = _wired()

    admitted = [
        router.register(
            _playbook(playbook_id=f"pb-{r.value}", version="v1", regime=r)
        ).ref
        for r in sorted(MOMENTUM, key=str)
    ]

    assert len(admitted) == 2
    assert len(set(admitted)) == 2, "each registration must be distinct"


def test_widening_competence_requires_a_new_strategy_version() -> None:
    """The end-to-end form of immutability, and the path a widening actually takes.

    v2 gets a wider declaration and is admitted in CRISIS while v1 is refused
    there -- which is only possible because competence is keyed by version and is
    immutable per version.
    """
    registry = StrategyCompetence()
    registry.declare("momentum-1", "v1", _domain())
    registry.declare(
        "momentum-1", "v2", _domain(valid=frozenset({Regime.TRENDING_UP, Regime.CRISIS}))
    )
    router = _router(certified={("momentum-1", "v1"), ("momentum-1", "v2")}, competence=registry)

    with pytest.raises(StrategyIncompetent):
        router.register(
            _playbook(playbook_id="pb-v1-crisis", strategy_version="v1", regime=Regime.CRISIS)
        )

    admitted = router.register(
        _playbook(
            playbook_id="pb-v2-crisis", strategy_version="v2", regime=Regime.CRISIS
        )
    )
    assert admitted.strategy_version == "v2"


def test_coverage_reports_what_is_permitted_and_what_is_silent() -> None:
    """Exposed so coverage can be audited rather than assumed."""
    valid, unaddressed = _domain().coverage()

    assert valid == MOMENTUM
    assert unaddressed == frozenset({Regime.HIGH_VOLATILITY, Regime.TRENDING_DOWN})
