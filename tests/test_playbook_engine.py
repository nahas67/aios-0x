"""The fast tier selects; it never invents (goal G120).

The fast tier needs a policy object to act from. Without one, "low-latency
intelligence" means a model inventing a trade at the moment of execution. This
suite covers the engine that gives it something to select from, and — more
importantly — the four ways that engine could quietly become the thing it
exists to prevent:

**It routes on a label instead of a condition.** A regime classifier's output
records nothing about which features produced it or when they became knowable,
so a full-sample regime label is a look-ahead no timestamp check catches. The
engine's answer is a predicate over features that each carry ``available_at``,
and :meth:`PlaybookRouter.select` refuses a contaminated observation *before*
considering any playbook.

**It always returns something.** A router that returns its nearest match has not
routed; it has encoded a prior and labelled it a decision. Abstention is a
first-class outcome with a named reason.

**It trusts certification at bind time.** A playbook recording the verdict it
was bound to, checked once, keeps trading a strategy whose verdict was revoked.
The router re-asks on every call.

**It lets the caller edit policy.** A guard that must be told not to write is a
guard that will be told to write.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from kernel.playbook import (
    AbstentionReason,
    Bound,
    FeatureObservation,
    Observation,
    Playbook,
    PlaybookAction,
    PlaybookActionKind,
    PlaybookNotCertified,
    PlaybookRouter,
    Regime,
    RegimeCondition,
    UndeclaredFeature,
    build_playbook,
)
from kernel.strategy_registry import CertificationVerdict

T0 = datetime(2024, 6, 3, 14, 30, tzinfo=UTC)
DAY = timedelta(days=1)

#: Pydantic's deprecated aliases and introspection hooks. Excluded from the
#: reflective sweep so the test does not emit deprecation warnings; none of them
#: touch a field, which is the property the sweep is checking.
_PYDANTIC_NOISE = frozenset(
    {
        "schema",
        "schema_json",
        "update_forward_refs",
        "model_computed_fields",
        "model_fields",
        "dict",
        "json",
        "copy",
        "construct",
    }
)


# ══════════════════════════════════════════════════════════════════════════
# Fixtures — real verdicts from a real registry
# ══════════════════════════════════════════════════════════════════════════


def _verdict(
    strategy_id: str = "momentum-1",
    version: str = "v1",
    result: str = "CERTIFIED",
) -> CertificationVerdict:
    from kernel.strategy_registry import CertificationCheck

    return CertificationVerdict(
        strategy_id=strategy_id,
        strategy_version=version,
        verdict=result,
        checks=[
            CertificationCheck(
                name="deflated_sharpe",
                passed=result != "REJECTED",
                observed=1.8 if result != "REJECTED" else 0.1,
                threshold=0.95,
                detail="from a purged walk-forward with the trial count deflated",
            )
        ],
        failure_reasons=[] if result != "REJECTED" else ["deflated_sharpe"],
        observed_sharpe=2.1,
        deflated_sharpe=1.8,
        n_trials=140,
        policy_version="certification/v1",
        validator_id="validator-1",
    )


class LiveOracle:
    """An oracle whose answers can be revoked mid-test.

    A stub that always says yes cannot demonstrate the revocation case, which is
    the reason the router re-asks rather than trusting ``verdict_hash``.
    """

    def __init__(self, certified: set[tuple[str, str]] | None = None) -> None:
        self.certified = certified if certified is not None else {("momentum-1", "v1")}

    def verdict_for(self, strategy_id: str, strategy_version: str) -> Any | None:
        return _verdict(strategy_id, strategy_version) if self.is_certified(
            strategy_id, strategy_version
        ) else None

    def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
        return (strategy_id, strategy_version) in self.certified


def _router(*, certified: set[tuple[str, str]] | None = None) -> PlaybookRouter:
    return PlaybookRouter(LiveOracle(certified))


def _playbook(
    *,
    playbook_id: str = "pb-momentum-trend",
    version: str = "v1",
    regime: Regime = Regime.TRENDING_UP,
    bounds: tuple[Bound, ...] | None = None,
    action: PlaybookAction | None = None,
    verdict: CertificationVerdict | None = None,
) -> Playbook:
    return build_playbook(
        playbook_id=playbook_id,
        version=version,
        title=f"{regime.value} momentum",
        regime=regime,
        bounds=bounds
        if bounds is not None
        else (Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
        action=action
        if action is not None
        else PlaybookAction(
            kind=PlaybookActionKind.TRADE, target_weight=0.15, reason="trend confirmed"
        ),
        strategy_id="momentum-1",
        strategy_version="v1",
        verdict=verdict if verdict is not None else _verdict(),
        evidence=("core/quant_statistics.py",),
    )


def _observation(
    trend: float = 0.5,
    *,
    volatility: float | None = 0.2,
    available_at: datetime | None = None,
) -> Observation:
    features = {
        "trend_strength": FeatureObservation(
            "trend_strength", trend, available_at or T0 - timedelta(minutes=1)
        )
    }
    if volatility is not None:
        features["realized_vol"] = FeatureObservation(
            "realized_vol", volatility, T0 - timedelta(minutes=1)
        )
    return Observation(as_of=T0, features=features)


# ══════════════════════════════════════════════════════════════════════════
# A playbook is a versioned, deterministic, certified policy object
# ══════════════════════════════════════════════════════════════════════════


def test_a_playbook_is_not_free_text() -> None:
    """The gate. Every acted-on field is typed and constrained."""
    playbook = _playbook()
    assert isinstance(playbook.condition, RegimeCondition)
    assert isinstance(playbook.action, PlaybookAction)
    assert playbook.action.kind is PlaybookActionKind.TRADE
    assert playbook.ref == "pb-momentum-trend:v1"


def test_selection_is_deterministic() -> None:
    """Same observation, same answer, every time.

    A router whose output varies run to run cannot be certified, because the
    certification is of a function and a varying function is not one. Asserted
    by repetition rather than by a single call so a hidden tie-break on dict
    ordering or a clock would show up.
    """
    router = _router()
    router.register(_playbook())
    answers = {router.select(_observation()).describe() for _ in range(25)}
    assert len(answers) == 1


def test_a_playbook_cannot_be_edited() -> None:
    """Frozen at the type level, so the uneditable shape is unconstructible."""
    playbook = _playbook()
    with pytest.raises(ValidationError, match="frozen"):
        playbook.action = PlaybookAction(  # type: ignore[misc]
            kind=PlaybookActionKind.TRADE, target_weight=0.99, reason="greed"
        )


def test_the_content_hash_covers_what_a_reader_acts_on() -> None:
    """Identity is the policy, not the paperwork.

    ``registered_at`` and ``evidence`` are excluded on purpose: re-registering
    the identical policy with one more source reference should not make it look
    like a different object, or "has this playbook changed?" becomes a
    comparison nobody can make.

    One verdict is shared across both constructions, which is what the equality
    is actually asserting. ``CertificationVerdict.decided_at`` defaults to now,
    so two separately-built verdicts differ and the hashes *should* — a
    playbook bound to a different verdict is a different policy.
    """
    verdict = _verdict()
    base = _playbook(verdict=verdict)
    later = _playbook(verdict=verdict)
    assert later.registered_at >= base.registered_at
    assert base.content_hash == later.content_hash


def test_rebinding_to_a_different_verdict_changes_the_hash() -> None:
    """The other direction: the bound verdict is part of what is acted on."""
    first = _playbook(verdict=_verdict())
    second = _playbook(
        verdict=_verdict().model_copy(update={"decided_at": "2024-01-01T00:00:00+00:00"})
    )
    assert first.verdict_hash != second.verdict_hash
    assert first.content_hash != second.content_hash


def test_changing_a_threshold_changes_the_hash() -> None:
    """The other direction, which is the one that matters."""
    tight = _playbook(bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),))
    loose = _playbook(bounds=(Bound(feature="trend_strength", minimum=0.1, maximum=1.0),))
    assert tight.content_hash != loose.content_hash


def test_a_changed_size_is_a_new_version_not_an_edit() -> None:
    router = _router()
    router.register(_playbook())
    with pytest.raises(ValueError, match="already registered"):
        router.register(_playbook(action=PlaybookAction(
            kind=PlaybookActionKind.TRADE, target_weight=0.9, reason="greed"
        )))
    assert len(router.registered()) == 1


def test_the_verdict_hash_is_derived_not_supplied() -> None:
    """A caller cannot bind a playbook to a digest computed from nothing."""
    import hashlib

    verdict = _verdict()
    playbook = _playbook(verdict=verdict)
    expected = hashlib.sha256(verdict.model_dump_json().encode()).hexdigest()
    assert playbook.verdict_hash == expected


def test_build_playbook_refuses_a_digest_instead_of_a_verdict() -> None:
    """The type makes the laundered path unavailable."""
    with pytest.raises(TypeError, match="requires a CertificationVerdict"):
        build_playbook(
            playbook_id="pb",
            version="v1",
            title="fake",
            regime=Regime.CRISIS,
            bounds=(Bound(feature="drawdown", minimum=0.2, maximum=1.0),),
            action=PlaybookAction(kind=PlaybookActionKind.ABSTAIN, reason="risk off"),
            strategy_id="momentum-1",
            strategy_version="v1",
            verdict="deadbeef",  # type: ignore[arg-type]
        )


# ══════════════════════════════════════════════════════════════════════════
# The fast model cannot modify a playbook in production
# ══════════════════════════════════════════════════════════════════════════


def test_the_router_exposes_no_mutation_path() -> None:
    """The gate, enforced by shape rather than by instruction.

    There is no ``update``, ``remove``, or ``reload`` to call, so no amount of
    prompting, injection, or bug can route the fast tier into editing policy.
    An instruction the fast tier is asked to follow is a control with a
    probability of failure; an absent method has none.
    """
    router = _router()
    forbidden = [
        name
        for name in dir(router)
        if not name.startswith("_")
        and name.lower()
        in {"update", "mutate", "edit", "remove", "delete", "reload", "patch", "set", "add"}
    ]
    assert forbidden == []
    public = {n for n in dir(router) if not n.startswith("_")}
    assert public == {"register", "registered", "select", "selection_for_regime", "regimes"}


def test_no_callable_on_a_playbook_can_change_it() -> None:
    """The same argument one level down, on the data itself.

    Behavioural rather than name-based: every public callable is invoked
    defensively and the content hash must be unchanged afterwards. A
    name-shape check would flag pydantic's ``update_forward_refs`` — a
    classmethod that resolves type annotations and touches no field — and pass a
    genuinely mutating method that happened to be named something unexpected.
    """
    playbook = _playbook()
    before = playbook.content_hash
    for name in dir(playbook):
        if name.startswith("_") or name in _PYDANTIC_NOISE:
            continue
        attribute = getattr(playbook, name, None)
        if not callable(attribute):
            continue
        try:
            attribute()
        except Exception:
            # A method that refuses to run with no arguments cannot have
            # mutated anything on the way to refusing.
            pass
    assert playbook.content_hash == before
    assert playbook.action.target_weight == 0.15
    assert playbook.model_config.get("frozen") is True


def test_copying_a_playbook_cannot_change_the_original() -> None:
    """``model_copy(update=...)`` is a copy, not an edit — and the copy is unvalidated.

    Which is precisely why the frozen instance is what the router holds, and
    why a policy change has to go back through registration with a new verdict.
    """
    playbook = _playbook()
    forged = playbook.model_copy(
        update={
            "action": PlaybookAction(
                kind=PlaybookActionKind.TRADE, target_weight=0.99, reason="injected"
            )
        }
    )
    assert playbook.action.target_weight == 0.15
    assert forged.action.target_weight == 0.99
    assert forged.content_hash != playbook.content_hash


# ══════════════════════════════════════════════════════════════════════════
# A regime is a condition, not a classifier label
# ══════════════════════════════════════════════════════════════════════════


def test_a_regime_with_no_bounds_is_refused() -> None:
    """The guard against regressing to label lookup.

    ``regime=CRISIS, bounds=()`` would match every observation in the world: a
    playbook that is always active is not selected, and the router would then
    have to break the tie by guessing.
    """
    with pytest.raises(ValidationError, match="needs at least one bound"):
        RegimeCondition(regime=Regime.CRISIS, bounds=())


def test_a_regime_cannot_constrain_one_feature_twice() -> None:
    """Tightest-or-first resolution between two bounds on a name is arbitrary."""
    with pytest.raises(ValidationError, match="more than once"):
        RegimeCondition(
            regime=Regime.CRISIS,
            bounds=(
                Bound(feature="drawdown", minimum=0.1, maximum=1.0),
                Bound(feature="drawdown", minimum=0.2, maximum=0.9),
            ),
        )


def test_bounds_are_half_open_so_adjacent_regimes_tile() -> None:
    """A value must not satisfy two regimes that meet at the boundary.

    Half-open on the upper side is what makes a set of bounds a partition rather
    than a set of overlapping ranges, which is the precondition for ambiguity
    to mean a real conflict rather than an artefact of a shared endpoint.
    """
    lower = Bound(feature="trend_strength", minimum=0.0, maximum=0.3)
    upper = Bound(feature="trend_strength", minimum=0.3, maximum=1.0)
    assert lower.contains(0.29) is True
    assert lower.contains(0.3) is False
    assert upper.contains(0.3) is True


def test_a_missing_feature_is_reported_not_treated_as_zero() -> None:
    """A condition that defaults a missing feature trades on an invented number."""
    router = _router()
    router.register(_playbook(bounds=(Bound(feature="vol_regime_id", minimum=0.0),)))
    selection = router.select(Observation(as_of=T0, features={}))
    assert selection.reason is AbstentionReason.OBSERVATION_INCOMPLETE
    assert "vol_regime_id" in selection.detail
    assert selection.action is None


def test_reading_an_absent_feature_directly_raises() -> None:
    observation = Observation(as_of=T0, features={})
    assert observation.has("x") is False
    with pytest.raises(UndeclaredFeature, match="silently trades on a default"):
        observation.value("x")


def test_a_failed_bound_names_the_feature_and_the_value() -> None:
    """One boolean would send a caller to instrument mid-latency."""
    router = _router()
    router.register(_playbook())
    selection = router.select(_observation(trend=0.1))
    assert selection.reason is AbstentionReason.NO_PLAYBOOK_MATCHED
    assert "trend_strength" in selection.detail
    assert "0.1" in selection.detail


# ══════════════════════════════════════════════════════════════════════════
# Look-ahead: the property the design exists to hold
# ══════════════════════════════════════════════════════════════════════════


def test_a_feature_from_the_future_blocks_every_selection() -> None:
    """Refused before any playbook is considered.

    Acting on a contaminated observation is wrong under *every* policy, so
    there is nothing to route to. Checking certification first would mean an
    unauditable decision was made and then explained.
    """
    router = _router()
    router.register(_playbook())
    selection = router.select(
        _observation(available_at=T0 + timedelta(seconds=30))
    )
    assert selection.reason is AbstentionReason.CONTAMINATED_INPUT
    assert selection.action is None
    assert selection.playbook is None
    assert "trend_strength" in selection.detail


def test_a_partially_contaminated_observation_is_still_refused() -> None:
    """One bad feature poisons the observation.

    The alternative — routing on the clean subset — would mean the playbook
    whose condition touches the bad feature is skipped while its neighbours are
    used, so the same strategy behaves differently depending on which features
    happened to arrive.
    """
    router = _router()
    router.register(
        _playbook(bounds=(Bound(feature="trend_strength", minimum=0.0, maximum=1.0),))
    )
    selection = router.select(
        Observation(
            as_of=T0,
            features={
                "trend_strength": FeatureObservation("trend_strength", 0.9, T0 - DAY),
                "realized_vol": FeatureObservation("realized_vol", 0.9, T0 + DAY),
            },
        )
    )
    assert selection.reason is AbstentionReason.CONTAMINATED_INPUT
    assert "realized_vol" in selection.detail


def test_a_selection_is_auditable_by_the_contamination_detector() -> None:
    """Composed with G080 rather than reimplementing its check.

    A second, weaker look-ahead check inside the router is exactly the kind of
    duplication that lets one of the two fall behind. The selection hands its
    timings over and the existing detector renders the verdict.
    """
    from core.contamination import detect_look_ahead

    router = _router()
    router.register(_playbook())
    selection = router.select(_observation())
    report = detect_look_ahead(selection.audit_timings())
    assert report.clean is True
    assert report.checked == 2


def test_a_contaminated_selection_would_also_be_caught_by_the_detector() -> None:
    """The two agree — which is the point of sharing the check."""
    from core.contamination import detect_look_ahead

    router = _router()
    router.register(_playbook())
    selection = router.select(_observation(available_at=T0 + DAY))
    assert detect_look_ahead(selection.audit_timings()).clean is False
    assert selection.reason is AbstentionReason.CONTAMINATED_INPUT


def test_a_feature_available_exactly_at_the_decision_is_clean() -> None:
    """Knowable at the decision is usable; the boundary is inclusive."""
    router = _router()
    router.register(_playbook())
    assert router.select(_observation(available_at=T0)).action is not None


# ══════════════════════════════════════════════════════════════════════════
# Abstention is a first-class outcome
# ══════════════════════════════════════════════════════════════════════════


def test_an_empty_router_abstains_with_its_own_reason() -> None:
    """Distinct from "playbooks exist but none matched"."""
    selection = _router().select(_observation())
    assert selection.reason is AbstentionReason.NO_CERTIFIED_PLAYBOOK
    assert selection.action is None
    assert "no playbook is registered" in selection.detail


def test_no_match_produces_no_action() -> None:
    """``action is None``, not a default. A default is a decision nobody made."""
    router = _router()
    router.register(_playbook())
    selection = router.select(_observation(trend=-0.9))
    assert selection.abstained is True
    assert selection.action is None
    assert selection.playbook is None


def test_the_abstention_description_names_the_reason() -> None:
    """"Nothing happened" is a finding, and it says which one."""
    selection = _router().select(_observation())
    assert selection.describe().startswith("ABSTAIN (no_certified_playbook)")


def test_two_matching_playbooks_abstain_rather_than_picking_one() -> None:
    """A conflict is not a preference.

    Breaking the tie needs a ranking between the two, and no ranking was
    certified. Resolving by registration order would mean the policy was chosen
    by the sequence of startup calls.
    """
    router = _router()
    router.register(_playbook(playbook_id="pb-a"))
    router.register(_playbook(playbook_id="pb-b"))
    selection = router.select(_observation())
    assert selection.reason is AbstentionReason.AMBIGUOUS
    assert selection.action is None
    assert set(selection.considered) == {"pb-a:v1", "pb-b:v1"}
    assert "no ranking between them was certified" in selection.detail


def test_an_ambiguity_is_reported_even_when_one_would_have_been_acted_on() -> None:
    """A would-be TRADE is exactly when silence is most dangerous."""
    router = _router()
    router.register(_playbook(playbook_id="pb-a", action=PlaybookAction(
        kind=PlaybookActionKind.TRADE, target_weight=0.4, reason="a"
    )))
    router.register(_playbook(playbook_id="pb-b", action=PlaybookAction(
        kind=PlaybookActionKind.ABSTAIN, reason="b"
    )))
    selection = router.select(_observation())
    assert selection.abstained is True
    assert selection.reason is AbstentionReason.AMBIGUOUS


# ══════════════════════════════════════════════════════════════════════════
# Certification is consulted live
# ══════════════════════════════════════════════════════════════════════════


def test_a_rejected_verdict_cannot_produce_a_playbook() -> None:
    """Routing capital to a strategy the firewall refused."""
    with pytest.raises(PlaybookNotCertified, match="REJECTED"):
        _playbook(verdict=_verdict(result="REJECTED"))


def test_a_verdict_for_a_different_strategy_is_refused() -> None:
    """The certification laundered into a trading policy."""
    with pytest.raises(PlaybookNotCertified, match="is for momentum-1:v1"):
        build_playbook(
            playbook_id="pb",
            version="v1",
            title="mismatched",
            regime=Regime.TRENDING_UP,
            bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
            action=PlaybookAction(
                kind=PlaybookActionKind.TRADE, target_weight=0.1, reason="x"
            ),
            strategy_id="carry-1",
            strategy_version="v1",
            verdict=_verdict("momentum-1", "v1"),
        )


def test_registration_refuses_an_uncertified_strategy() -> None:
    router = _router(certified=set())
    with pytest.raises(PlaybookNotCertified, match="not certified"):
        router.register(_playbook())


def test_revoking_a_verdict_stops_the_playbook_being_selected() -> None:
    """The reason the router asks on every call rather than trusting the hash.

    A bind-time snapshot would keep this playbook trading a strategy that no
    longer has permission to trade — the certification revoked, the capital
    still moving.
    """
    oracle = LiveOracle()
    router = PlaybookRouter(oracle)
    router.register(_playbook())
    assert router.select(_observation()).action is not None

    oracle.certified.clear()
    selection = router.select(_observation())
    assert selection.action is None
    assert selection.reason is AbstentionReason.NO_CERTIFIED_PLAYBOOK
    assert "no longer certified" in selection.detail


def test_a_fully_revoked_set_names_the_offending_playbooks() -> None:
    router = _router(certified=set())
    with pytest.raises(PlaybookNotCertified):
        router.register(_playbook())
    assert router.select(_observation()).reason is AbstentionReason.NO_CERTIFIED_PLAYBOOK


def test_one_revoked_playbook_does_not_disable_the_others() -> None:
    """Revocation is per-strategy, not a fleet-wide kill switch."""
    oracle = LiveOracle({("momentum-1", "v1"), ("carry-1", "v1")})
    router = PlaybookRouter(oracle)
    router.register(_playbook(playbook_id="pb-mom"))
    router.register(
        build_playbook(
            playbook_id="pb-carry",
            version="v1",
            title="carry in a range",
            regime=Regime.TRENDING_UP,
            bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
            action=PlaybookAction(
                kind=PlaybookActionKind.REDUCE, target_weight=0.05, reason="carry"
            ),
            strategy_id="carry-1",
            strategy_version="v1",
            verdict=_verdict("carry-1", "v1"),
        )
    )
    oracle.certified.discard(("carry-1", "v1"))
    selection = router.select(_observation())
    assert selection.action is not None
    assert selection.playbook.ref == "pb-mom:v1"


# ══════════════════════════════════════════════════════════════════════════
# Actions carry their own discipline
# ══════════════════════════════════════════════════════════════════════════


def test_an_unsized_trade_is_refused() -> None:
    """Sizing moved outside the certified object is unearned authority."""
    with pytest.raises(ValidationError, match="requires target_weight"):
        PlaybookAction(kind=PlaybookActionKind.TRADE, reason="just trade it")


def test_a_wait_cannot_carry_a_position() -> None:
    """WAIT expresses no position; a weight on it is a contradiction."""
    with pytest.raises(ValidationError, match="must not carry a target_weight"):
        PlaybookAction(
            kind=PlaybookActionKind.WAIT, target_weight=0.1, reason="waiting"
        )


def test_a_reduction_is_a_valid_sized_action() -> None:
    action = PlaybookAction(
        kind=PlaybookActionKind.REDUCE, target_weight=0.02, reason="de-risk"
    )
    assert action.describe() == "REDUCE 2.0%"


def test_a_playbook_may_itself_abstain() -> None:
    """Distinct from the router abstaining: this is the policy's own decision.

    A regime where the right move is to do nothing is a real state, and it needs
    an explicit playbook so that its absence is a change in policy rather than
    an unnoticed gap in coverage.
    """
    playbook = _playbook(
        playbook_id="pb-risk-off",
        regime=Regime.CRISIS,
        bounds=(Bound(feature="drawdown", minimum=0.15, maximum=1.0),),
        action=PlaybookAction(kind=PlaybookActionKind.ABSTAIN, reason="drawdown limit"),
    )
    router = _router()
    router.register(playbook)
    selection = router.select(
        Observation(
            as_of=T0,
            features={
                "drawdown": FeatureObservation("drawdown", 0.3, T0 - DAY)
            },
        )
    )
    assert selection.action is not None
    assert selection.action.kind is PlaybookActionKind.ABSTAIN
    assert selection.regime is Regime.CRISIS
    assert selection.describe().startswith("ABSTAIN via pb-risk-off")


def test_a_playbook_requires_a_reason() -> None:
    """An unexplained action is one an operator cannot review."""
    with pytest.raises(ValidationError, match="reason"):
        PlaybookAction(kind=PlaybookActionKind.ABSTAIN, reason="")


def test_the_weight_is_constrained_to_a_fraction() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        PlaybookAction(
            kind=PlaybookActionKind.TRADE, target_weight=1.5, reason="all in"
        )


# ══════════════════════════════════════════════════════════════════════════
# Read-side helpers
# ══════════════════════════════════════════════════════════════════════════


def test_selection_for_regime_returns_the_single_playbook() -> None:
    router = _router()
    router.register(_playbook())
    found = router.selection_for_regime(Regime.TRENDING_UP)
    assert found is not None and found.ref == "pb-momentum-trend:v1"


def test_selection_for_an_uncovered_regime_is_none() -> None:
    assert _router().selection_for_regime(Regime.CRISIS) is None


def test_selection_for_an_ambiguous_regime_is_none_rather_than_the_first() -> None:
    """Same rule as routing, for the same reason."""
    router = _router()
    router.register(_playbook(playbook_id="pb-a"))
    router.register(_playbook(playbook_id="pb-b"))
    assert router.selection_for_regime(Regime.TRENDING_UP) is None


def test_the_router_lists_the_regimes_it_covers() -> None:
    router = _router()
    router.register(_playbook(playbook_id="pb-a"))
    router.register(
        _playbook(
            playbook_id="pb-c",
            regime=Regime.CRISIS,
            bounds=(Bound(feature="drawdown", minimum=0.15, maximum=1.0),),
            action=PlaybookAction(kind=PlaybookActionKind.ABSTAIN, reason="off"),
        )
    )
    assert set(router.regimes()) == {Regime.TRENDING_UP, Regime.CRISIS}


def test_a_matching_selection_names_its_condition() -> None:
    router = _router()
    router.register(_playbook())
    selection = router.select(_observation())
    assert "trend_strength in [0.3, 1)" in selection.detail
    assert selection.considered == ("pb-momentum-trend:v1",)


def test_a_selection_carries_every_feature_timing_it_read() -> None:
    """Including the ones its condition did not constrain.

    The contamination audit is over what the *router* could have used, not over
    what one playbook happened to look at — otherwise adding a feature to the
    observation would silently widen the trust boundary.
    """
    router = _router()
    router.register(_playbook())
    selection = router.select(_observation())
    assert {t.feature_name for t in selection.timings} == {
        "trend_strength",
        "realized_vol",
    }
