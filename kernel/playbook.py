"""Certified playbooks and the router that selects among them (goal G120).

The fast tier needs a policy object to act from. Without one, "low-latency
intelligence" means a model inventing a trade at the moment of execution — the
exact thing the rest of this system exists to prevent. So the fast tier gets the
narrower and more useful power: it may **select** among playbooks that were
certified offline, and it may never create or alter one.

Three design decisions carry the goal, and each was forced by a specific failure
rather than chosen for elegance.

**A regime is a predicate, not a classifier label.** The obvious design is "train
a regime classifier, let the router look up the current label." That is
unfalsifiable: nothing records which features produced the label or when they
became knowable, so a regime label computed over a full sample is a look-ahead
that no timestamp check will ever catch. Instead a playbook declares its
activation condition as explicit bounds on named features, every one of which
carries an ``available_at``. Selection becomes arithmetic, and the look-ahead
becomes checkable — :class:`Selection` hands its feature timings straight to
G080's ``detect_look_ahead``.

**Abstention is a first-class outcome, not an error.** A router that always
returns its nearest match has not routed anything; it has encoded a prior and
labelled it a decision. When no certified playbook's condition is satisfied the
router abstains, and the caller gets no action. This is G110's
TRADE/WAIT/ESCALATE/ABSTAIN gate, and the router is where it is decided.

**Selection consults live certification state.** A playbook records the verdict
it was bound to, but the router re-asks the oracle on every call. A verdict that
is revoked after binding must stop the playbook being selectable, and a snapshot
taken at bind time would keep trading a strategy that no longer has permission
to trade.

The router has no mutation method. That is the whole enforcement of "the fast
model cannot modify a playbook in production": there is nothing to call. Adding
one would be a change to the guarantee rather than a feature.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

from schemas.observations import FeatureObservation, FeatureTiming

__all__ = [
    "AbstentionReason",
    "CandidatePlaybook",
    "CertificationOracle",
    "CompetenceNotDeclared",
    "DerivationRefused",
    "DomainOfCompetence",
    "InconsistentCompetence",
    "FeatureObservation",
    "Playbook",
    "PlaybookAction",
    "PlaybookActionKind",
    "PlaybookNotCertified",
    "PlaybookRouter",
    "Regime",
    "RegimeCondition",
    "Selection",
    "StrategyCompetence",
    "StrategyIncompetent",
    "SizingBasis",
    "UndeclaredFeature",
    "build_measured_playbook",
    "derive_action",
    "load_router",
    "persist_router",
    "propose_candidates",
]


# ══════════════════════════════════════════════════════════════════════════
# Failure modes
# ══════════════════════════════════════════════════════════════════════════


class PlaybookNotCertified(RuntimeError):
    """A playbook was bound to a verdict that does not certify it."""


class UndeclaredFeature(ValueError):
    """A condition referenced a feature the observation does not carry."""


class AbstentionReason(StrEnum):
    """Why no action was taken. Named, because "nothing happened" is a finding."""

    NO_PLAYBOOK_MATCHED = "no_playbook_matched"
    NO_CERTIFIED_PLAYBOOK = "no_certified_playbook"
    AMBIGUOUS = "ambiguous_match"
    OBSERVATION_INCOMPLETE = "observation_incomplete"
    CONTAMINATED_INPUT = "contaminated_input"


# ══════════════════════════════════════════════════════════════════════════
# What the fast tier can see
# ══════════════════════════════════════════════════════════════════════════


# FeatureObservation and FeatureTiming are imported at top level from
# schemas/observations.py and re-exported through __all__ below, so every
# existing importer keeps working against the single definition.


@dataclass(frozen=True)
class Observation:
    """The point-in-time state a router decides against."""

    as_of: datetime
    features: dict[str, FeatureObservation] = field(default_factory=dict)

    def value(self, name: str) -> float:
        feature = self.features.get(name)
        if feature is None:
            raise UndeclaredFeature(
                f"observation carries no feature named {name!r}. A condition that "
                "silently treats a missing feature as zero is a condition that "
                "silently trades on a default."
            )
        return feature.value

    def has(self, name: str) -> bool:
        return name in self.features

    def timings(self) -> list[FeatureTiming]:
        return [f.as_timing(self.as_of) for f in self.features.values()]


# ══════════════════════════════════════════════════════════════════════════
# Regimes
# ══════════════════════════════════════════════════════════════════════════


class Regime(StrEnum):
    """Named market states a playbook can govern.

    An enumeration rather than free text, because a regime named by a string
    that nothing validates is a regime whose membership nobody can check. These
    four are the states the certified playbooks actually distinguish, and adding
    one is a deliberate act rather than a typo.
    """

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    HIGH_VOLATILITY = "high_volatility"
    RANGE_BOUND = "range_bound"
    CRISIS = "crisis"


class Bound(BaseModel):
    """An inclusive lower and exclusive upper bound on one feature."""

    model_config = {"frozen": True}

    feature: str = Field(..., min_length=1)
    #: ``None`` means unbounded on that side.
    minimum: float | None = None
    maximum: float | None = None

    def contains(self, value: float) -> bool:
        """Whether ``value`` falls inside. Half-open, so adjacent bounds tile."""
        if self.minimum is not None and value < self.minimum:
            return False
        if self.maximum is not None and value >= self.maximum:
            return False
        return True

    def describe(self) -> str:
        low = "-inf" if self.minimum is None else f"{self.minimum:g}"
        high = "+inf" if self.maximum is None else f"{self.maximum:g}"
        return f"{self.feature} in [{low}, {high})"


class RegimeCondition(BaseModel):
    """When a playbook applies: every bound must hold.

    A conjunction, not a disjunction or a learned score. A playbook that governs
    "high volatility *and* falling" is describing a specific state, and a router
    that could satisfy it with either one is routing on a different policy than
    the one that was certified.
    """

    model_config = {"frozen": True}

    regime: Regime
    bounds: tuple[Bound, ...] = ()

    @model_validator(mode="after")
    def _require_bounds_for_a_named_regime(self) -> RegimeCondition:
        """A named regime with no bounds is a label, not a condition.

        This is the guard that keeps the engine from regressing to classifier
        lookup. ``regime=CRISIS, bounds=()`` would match every observation in
        the world, which is a playbook that is always active and therefore never
        selected — the exact ambiguity the router would then have to resolve by
        guessing.
        """
        if not self.bounds:
            raise ValueError(
                f"regime {self.regime.value!r} needs at least one bound. A regime with "
                "no bounds matches everything, which is a label rather than a condition."
            )
        names = [b.feature for b in self.bounds]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(
                f"regime {self.regime.value!r} constrains {sorted(duplicates)} more than "
                "once; the tighter-or-first resolution would be arbitrary"
            )
        return self

    def evaluate(self, observation: Observation) -> ConditionMatch:
        """Check the condition, reporting every bound rather than the first failure.

        A single boolean would send a caller to instrument the features to find
        out which bound failed — during a latency-sensitive path, which is the
        worst time to be discovering that.
        """
        for bound in self.bounds:
            if not observation.has(bound.feature):
                return ConditionMatch(
                    satisfied=False,
                    reason=AbstentionReason.OBSERVATION_INCOMPLETE,
                    detail=f"observation carries no feature named {bound.feature!r}",
                )
        unsatisfied = [b for b in self.bounds if not b.contains(observation.value(b.feature))]
        if unsatisfied:
            return ConditionMatch(
                satisfied=False,
                reason=AbstentionReason.NO_PLAYBOOK_MATCHED,
                detail="; ".join(
                    f"{b.describe()} but observed {observation.value(b.feature):g}" for b in unsatisfied
                ),
            )
        return ConditionMatch(
            satisfied=True,
            reason=AbstentionReason.NO_PLAYBOOK_MATCHED,
            detail="; ".join(b.describe() for b in self.bounds),
        )


@dataclass(frozen=True)
class ConditionMatch:
    satisfied: bool
    reason: AbstentionReason
    detail: str


# ══════════════════════════════════════════════════════════════════════════
# Actions
# ══════════════════════════════════════════════════════════════════════════


class PlaybookActionKind(StrEnum):
    """G110's decision gate, decided by the router rather than by a model.

    ``ABSTAIN`` is present in the enum because a playbook may *itself* decide to
    abstain for a regime where the right move is to do nothing — distinct from
    the router abstaining because nothing matched.
    """

    TRADE = "TRADE"
    REDUCE = "REDUCE"
    WAIT = "WAIT"
    ESCALATE = "ESCALATE"
    ABSTAIN = "ABSTAIN"


class PlaybookAction(BaseModel):
    """What to do, deterministically. No prose, no model in the loop."""

    model_config = {"frozen": True}

    kind: PlaybookActionKind
    #: Sized by the certified backtest, not by the caller. A playbook that
    #: cannot state a size cannot be held to a capacity ceiling.
    target_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    max_notional_usd: float | None = Field(default=None, gt=0.0)
    reason: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _a_trade_must_be_sized(self) -> PlaybookAction:
        """An unsized TRADE is the shape of an unbounded position.

        A playbook that says "trade" without saying how much has moved the
        sizing decision out of the certified object and into whatever the
        execution path defaults to — which is the same unearned authority the
        whole certification plane exists to remove.
        """
        if self.kind is PlaybookActionKind.TRADE and self.target_weight is None:
            raise ValueError(
                "a TRADE action requires target_weight. An unsized trade delegates "
                "position sizing to the execution path, outside anything certified."
            )
        if self.kind in {PlaybookActionKind.WAIT, PlaybookActionKind.ESCALATE}:
            if self.target_weight is not None:
                raise ValueError(
                    f"a {self.kind.value} action must not carry a target_weight; it "
                    "expresses no position to take"
                )
        return self

    def describe(self) -> str:
        if self.target_weight is None:
            return self.kind.value
        return f"{self.kind.value} {self.target_weight:.1%}"


# ══════════════════════════════════════════════════════════════════════════
# Derivation: the size comes from the backtest, not from a person
# ══════════════════════════════════════════════════════════════════════════


class DerivationRefused(RuntimeError):
    """A playbook could not be derived from the measurements.

    Refusal rather than a default, because every silent fallback here is a
    position size nobody measured: a zero weight that reads as caution, a
    capped weight that reads as prudence, a guessed weight that reads as a
    policy. The only honest answer to "the measurements do not support a
    position" is no playbook.
    """


class SizingBasis(BaseModel):
    """The measured inputs a derived action was computed from.

    Recorded on the playbook so the size is recomputable by whoever reads it:
    ``target_weight`` must equal ``required_notional_usd / book_size_usd``,
    and every input must be traceable to the verdict the playbook binds to.
    A size whose basis is absent is a claim; a size whose basis is present is
    a consequence, and the two must not look alike.
    """

    model_config = {"frozen": True}

    book_size_usd: float = Field(..., gt=0.0)
    capacity_ceiling_usd: float = Field(..., gt=0.0)
    required_notional_usd: float = Field(..., gt=0.0)
    net_sharpe: float
    deflated_sharpe: float
    regime: Regime
    regime_net_sharpe: float
    policy_version: str = Field(..., min_length=1)

    @property
    def target_weight(self) -> float:
        """The weight this basis justifies. Recomputed, never stored.

        Stored would mean two sources of truth for one number, and the one a
        reader checks would be the one nobody verified.
        """
        return self.required_notional_usd / self.book_size_usd

    def verify(self, action: PlaybookAction) -> bool:
        """Whether ``action`` is exactly what this basis derives.

        Exact to 1e-9 rather than approximate: both numbers are ratios of the
        same recorded inputs, so any difference is a different size rather
        than rounding.
        """
        if action.target_weight is None:
            return False
        if action.max_notional_usd is None:
            return False
        return (
            abs(action.target_weight - self.target_weight) <= 1e-9
            and abs(action.max_notional_usd - self.required_notional_usd) <= 1e-6
        )


def derive_action(
    *,
    verdict: Any,
    evidence: Any,
    regime: Regime,
    book_size_usd: float,
) -> tuple[PlaybookAction, SizingBasis]:
    """Derive a trade action from certification measurements.

    The position size is ``required_notional / book`` — the mandate's own
    size, not a human's. What the measurements contribute is permission:
    every check below must hold, and the first one that does not names itself
    in the refusal. There is deliberately no fallback size, because a fallback
    is a human judgment wearing arithmetic's clothes.

    ``CERTIFIED_WITH_LIMITS`` is refused outright. Limits mean a sub-metric
    was weak — capacity unmeasured, stress unrun, a regime unprofitable — and
    a weak sub-metric is exactly what a position size must not be built on.
    The middle verdict state exists so the firewall does not have to lie, not
    so the fast tier can trade through a qualification nobody resolved.
    """
    from kernel.strategy_registry import CertificationEvidence, CertificationVerdict

    if not isinstance(verdict, CertificationVerdict):
        raise TypeError(
            "derive_action requires a CertificationVerdict. A size derived from "
            "anything else is a size nobody certified."
        )
    if not isinstance(evidence, CertificationEvidence):
        raise TypeError(
            "derive_action requires CertificationEvidence. The capacity ceiling "
            "and the mandate size live there, and a derivation without them "
            "would be inventing both."
        )
    if verdict.verdict != "CERTIFIED":
        raise DerivationRefused(
            f"cannot derive a position from a {verdict.verdict} verdict. "
            + (
                "Limits qualify the certification, and a qualified certification "
                "needs a human to resolve the qualification before capital moves."
                if verdict.verdict == "CERTIFIED_WITH_LIMITS"
                else "The firewall refused this strategy; deriving a size from "
                "its measurements would route around the refusal."
            )
        )
    for measured, name in (
        (evidence.costs_applied, "costs"),
        (evidence.capacity_measured, "capacity"),
        (evidence.stress_measured, "stress"),
        (evidence.execution_measured, "execution"),
        (evidence.contamination_measured, "contamination"),
    ):
        if not measured:
            raise DerivationRefused(
                f"cannot derive a position: {name} was not measured "
                f"({getattr(evidence, name + '_detail', 'no detail recorded')}). "
                "A size built on an unmeasured check inherits the check's "
                "absence rather than its passing."
            )
    regime_check_name = f"regime_sharpe:{regime.value}"
    regime_checks = [c for c in verdict.checks if c.name == regime_check_name]
    if not regime_checks:
        raise DerivationRefused(
            f"cannot derive a position for regime {regime.value!r}: the verdict "
            "carries no measurement for it. A playbook for an unmeasured regime "
            "is a policy for a state the strategy was never observed in."
        )
    regime_check = regime_checks[0]
    if not regime_check.passed:
        raise DerivationRefused(
            f"cannot derive a position for regime {regime.value!r}: "
            f"{regime_check.detail}. Trading a regime the backtest lost money "
            "in is not contrarianism, it is ignoring the measurement."
        )
    if book_size_usd <= 0:
        raise DerivationRefused(
            f"cannot derive a position against a book of {book_size_usd}. A weight "
            "is a fraction of something, and that something must exist."
        )
    if evidence.required_notional_usd > evidence.capacity_ceiling_usd:
        raise DerivationRefused(
            f"cannot derive a position: the mandate needs "
            f"{evidence.required_notional_usd:,.0f} but the measured ceiling is "
            f"{evidence.capacity_ceiling_usd:,.0f}. The edge does not scale to "
            "the mandate, and sizing past a measured ceiling is precisely what "
            "the ceiling exists to prevent."
        )
    weight = evidence.required_notional_usd / book_size_usd
    if weight > 1.0:
        raise DerivationRefused(
            f"cannot derive a position: the mandate needs {weight:.1%} of the book. "
            "A playbook cannot allocate more than the book holds; leverage is "
            "not modelled anywhere in the certification."
        )
    from kernel.strategy_registry import certification_policy

    dust = certification_policy()["min_playbook_weight"]
    if weight < dust:
        raise DerivationRefused(
            f"cannot derive a position: {weight:.3%} of the book is below the "
            f"{dust:.1%} policy floor. A position that small cannot move "
            "portfolio-level outcomes beyond noise, so publishing a playbook "
            "for it manufactures a precision the portfolio cannot feel."
        )
    regime_sharpe = regime_check.value if regime_check.value is not None else 0.0
    basis = SizingBasis(
        book_size_usd=book_size_usd,
        capacity_ceiling_usd=evidence.capacity_ceiling_usd,
        required_notional_usd=evidence.required_notional_usd,
        net_sharpe=evidence.net_sharpe,
        deflated_sharpe=verdict.deflated_sharpe,
        regime=regime,
        regime_net_sharpe=regime_sharpe,
        policy_version=verdict.policy_version,
    )
    action = PlaybookAction(
        kind=PlaybookActionKind.TRADE,
        target_weight=weight,
        max_notional_usd=evidence.required_notional_usd,
        reason=(
            f"derived from certification {verdict.policy_version}: net Sharpe "
            f"{evidence.net_sharpe:.2f} (deflated {verdict.deflated_sharpe:.2f}), "
            f"{regime.value} regime net Sharpe {regime_sharpe:.2f}, mandate "
            f"{evidence.required_notional_usd:,.0f} within measured ceiling "
            f"{evidence.capacity_ceiling_usd:,.0f}"
        ),
    )
    return action, basis


# ══════════════════════════════════════════════════════════════════════════
# The playbook
# ══════════════════════════════════════════════════════════════════════════


class Playbook(BaseModel):
    """A versioned, deterministic, certified policy object.

    Frozen. Not because immutability is tidy but because a playbook is the thing
    a verdict was issued *about* — if it could be edited after certification,
    the verdict would describe an object that no longer exists. Versioning is
    how a policy changes: a new object, a new verdict, and the old one retained.

    ``content_hash`` covers every field a reader acts on and excludes the
    bookkeeping, so a re-registration with a different expiry or note is still
    recognisably the same policy and a changed threshold is not.
    """

    model_config = {"frozen": True}

    playbook_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    condition: RegimeCondition
    action: PlaybookAction
    #: The certified strategy this playbook operationalises. A playbook with no
    #: strategy behind it is a preference, and preferences do not trade.
    strategy_id: str = Field(..., min_length=1)
    strategy_version: str = Field(..., min_length=1)
    #: SHA-256 of the verdict that certified it. Checked on every selection,
    #: not just at registration.
    verdict_hash: str = Field(..., min_length=1)
    evidence: tuple[str, ...] = ()
    #: The measurements the action was derived from, when it was derived rather
    #: than supplied. Present means an auditor can recompute the size from the
    #: recorded inputs; absent means the action was written by hand and the
    #: size is a claim rather than a consequence.
    sizing_basis: SizingBasis | None = None
    registered_at: str = ""

    @property
    def ref(self) -> str:
        return f"{self.playbook_id}:{self.version}"

    @property
    def content_hash(self) -> str:
        """Digest of everything a reader acts on.

        Excludes ``registered_at`` and ``evidence`` deliberately: those are
        provenance metadata, and including them would mean re-registering the
        identical policy with one more source reference changes its identity —
        which would make "has this playbook changed?" unanswerable by hash.
        Includes ``sizing_basis`` when present, because the basis is what the
        size *is*: the same action with different measurements behind it is a
        different claim about the world.
        """
        payload = json.dumps(
            {
                "playbook_id": self.playbook_id,
                "version": self.version,
                "condition": self.condition.model_dump(mode="json"),
                "action": self.action.model_dump(mode="json"),
                "strategy_id": self.strategy_id,
                "strategy_version": self.strategy_version,
                "verdict_hash": self.verdict_hash,
                "sizing_basis": (
                    self.sizing_basis.model_dump(mode="json")
                    if self.sizing_basis is not None
                    else None
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
# Certification
# ══════════════════════════════════════════════════════════════════════════


class CertificationOracle(Protocol):
    """Answers "is this strategy still certified?" — live, not snapshotted.

    A ``Protocol`` rather than a ``StrategyRegistry`` import so the router
    depends on the question rather than the registry, and so a test can supply
    an oracle that revokes on demand. That revocation case is the reason the
    router asks every time instead of trusting ``verdict_hash``.
    """

    def verdict_for(self, strategy_id: str, strategy_version: str) -> Any | None:
        """The current verdict, or ``None`` if there is none."""

    def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
        """Whether that strategy may currently be traded."""


# ══════════════════════════════════════════════════════════════════════════
# Selection
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Selection:
    """The router's answer, including when it declined to answer.

    ``action`` is ``None`` on any abstention, so a caller cannot accidentally
    read an action off a selection that did not produce one — the failure being
    a default that looks like a decision.
    """

    action: PlaybookAction | None
    playbook: Playbook | None
    reason: AbstentionReason
    detail: str
    #: Features consulted, so the selection can be audited for look-ahead.
    timings: tuple[FeatureTiming, ...] = ()
    #: Every playbook whose condition was satisfied, for the ambiguity case.
    considered: tuple[str, ...] = ()

    @property
    def abstained(self) -> bool:
        return self.action is None

    @property
    def regime(self) -> Regime | None:
        return self.playbook.condition.regime if self.playbook else None

    def audit_timings(self) -> list[Any]:
        """Feature timings as ``detect_look_ahead`` observations.

        Imported lazily and typed as ``Any`` because the contamination module
        would otherwise be a hard import cycle: it depends on
        ``schemas.governance`` for nothing, but keeping the direction one-way
        means the router does not own the detector's vocabulary.
        """
        from core.contamination import ObservationTiming

        return [
            ObservationTiming(
                observation_id=t.feature_name,
                decision_time=t.decision_time,
                feature_available_at=t.available_at,
            )
            for t in self.timings
        ]

    def describe(self) -> str:
        if self.action is None or self.playbook is None:
            return f"ABSTAIN ({self.reason.value}): {self.detail}"
        return f"{self.action.describe()} via {self.playbook.ref} in {self.regime}"


# ══════════════════════════════════════════════════════════════════════════
# The router
# ══════════════════════════════════════════════════════════════════════════


class PlaybookRouter:
    """Selects among certified playbooks. Reads only.

    The absence of any mutating method is the enforcement of "the fast model
    cannot modify a playbook in production". A guard that must be told not to
    write is a guard that will be told to write; a router with no write path is
    a router the fast tier cannot corrupt, regardless of what it is asked.

    Registration is therefore the *only* write, it happens offline, and it
    refuses a playbook whose strategy is not certified. There is no ``update``,
    no ``remove``, no ``reload`` — a changed policy is a new playbook with a
    new verdict.
    """

    def __init__(
        self,
        oracle: CertificationOracle,
        competence: StrategyCompetence | None = None,
    ) -> None:
        self._oracle = oracle
        self._playbooks: dict[str, Playbook] = {}
        #: ``None`` disables the competence gate entirely, which is what every
        #: existing caller does. That is recorded rather than hidden: a router
        #: with no competence registry enforces no competence, and the flag is
        #: here so a composition root that meant to wire one cannot do so
        #: silently and believe it is enforcing one.
        self._competence = competence

    # ------------------------------------------------------------- registration

    def register(self, playbook: Playbook) -> Playbook:
        """Admit a playbook whose strategy is currently certified.

        Certification is checked here *and* on every selection. Checking once
        would make a revoked strategy permanently tradable through any playbook
        bound to it, which is the specific hole that a bind-time snapshot opens.
        """
        if not self._oracle.is_certified(playbook.strategy_id, playbook.strategy_version):
            raise PlaybookNotCertified(
                f"{playbook.ref} binds to {playbook.strategy_id}:{playbook.strategy_version}, "
                "which is not certified. A playbook is the operational form of a verdict; "
                "without one it is a preference."
            )
        self._check_competence(playbook)
        if playbook.ref in self._playbooks:
            raise ValueError(
                f"{playbook.ref} is already registered. A playbook version is immutable: "
                "a changed policy is a new version with a new verdict, not an edit."
            )
        self._playbooks[playbook.ref] = playbook
        return playbook

    def _check_competence(self, playbook: Playbook) -> None:
        """Refuse a playbook whose strategy is not competent in its own regime.

        Checked once, at admission, and not again on selection. That asymmetry is
        deliberate and differs from the certification check above: a verdict can
        be revoked by the oracle at any instant, so re-checking is the only thing
        that stops a revoked strategy staying tradable. A competence declaration
        cannot change -- :class:`StrategyCompetence` is immutable, and amending
        one means declaring a new strategy version. So the admission-time check
        cannot be invalidated by the passage of time, and a second identical
        check on every selection would be a second guard with no additional
        failure mode behind it. One check, placed where the failure can occur.
        """
        if self._competence is None:
            return
        domain = self._competence.for_strategy(
            playbook.strategy_id, playbook.strategy_version
        )
        if domain is None:
            raise CompetenceNotDeclared(
                f"{playbook.ref} binds to {playbook.strategy_id}:"
                f"{playbook.strategy_version}, which has declared no domain of "
                f"competence. Architecture section 2 Layer 9 requires every "
                f"strategy to have one. A strategy with no declaration is not "
                f"competent everywhere -- competence is opt-in, because an "
                f"undeclared strategy treated as universally competent would "
                f"make the declaration decorative and would silently widen with "
                f"every new {Regime.__name__} member."
            )
        regime = playbook.condition.regime
        if not domain.is_competent(regime):
            raise StrategyIncompetent(
                f"{playbook.ref} activates in {regime.value!r}, which is outside "
                f"the declared competence of {playbook.strategy_id}:"
                f"{playbook.strategy_version} (valid: "
                f"{sorted(r.value for r in domain.valid)}; invalid: "
                f"{sorted(r.value for r in domain.invalid)}). A playbook that "
                f"activates where its strategy declared itself incompetent is a "
                f"strategy being asked to do the one thing it recorded that it "
                f"cannot do."
            )

    def registered(self) -> tuple[str, ...]:
        return tuple(self._playbooks)

    # ----------------------------------------------------------------- routing

    def select(self, observation: Observation) -> Selection:
        """Choose one certified playbook, or abstain with a named reason.

        Order of checks is deliberate and is the fail-closed ordering:

        1. **Look-ahead first.** A contaminated observation is refused before
           any playbook is considered, because acting on it is wrong regardless
           of which policy would have matched. Checking certification before this
           would mean an unauditable decision was made and then explained.
        2. **Certification live.** A playbook whose strategy lost its verdict
           this instant is not a candidate.
        3. **Condition.** Bounds over point-in-time features.
        4. **Ambiguity.** Two certified playbooks satisfied by the same
           observation is a conflict, not a preference. The router resolves it
           toward abstention, because picking the "best" one requires a ranking
           the certification never established — and a tie broken by insertion
           order is a policy chosen by nothing.
        """
        look_ahead = [t for t in observation.timings() if t.is_look_ahead]
        if look_ahead:
            return Selection(
                action=None,
                playbook=None,
                reason=AbstentionReason.CONTAMINATED_INPUT,
                detail=(
                    f"{len(look_ahead)} feature(s) were not knowable at the decision time: "
                    + ", ".join(sorted(t.feature_name for t in look_ahead))
                    + ". No playbook is selected, because the correct action under any "
                    "policy is unknown when the inputs are from the future."
                ),
                timings=tuple(observation.timings()),
            )

        candidates: list[Playbook] = []
        uncertified: list[str] = []
        misses: list[tuple[str, ConditionMatch]] = []
        for playbook in self._playbooks.values():
            if not self._oracle.is_certified(playbook.strategy_id, playbook.strategy_version):
                uncertified.append(playbook.ref)
                continue
            match = playbook.condition.evaluate(observation)
            if match.satisfied:
                candidates.append(playbook)
            else:
                misses.append((playbook.ref, match))

        timings = tuple(observation.timings())

        if not candidates:
            if not self._playbooks:
                return Selection(
                    action=None,
                    playbook=None,
                    reason=AbstentionReason.NO_CERTIFIED_PLAYBOOK,
                    detail="no playbook is registered at all",
                )
            if len(self._playbooks) == len(uncertified):
                return Selection(
                    action=None,
                    playbook=None,
                    reason=AbstentionReason.NO_CERTIFIED_PLAYBOOK,
                    detail=(
                        "every registered playbook binds to a strategy that is no longer "
                        f"certified: {', '.join(sorted(uncertified))}"
                    ),
                )
            return Selection(
                action=None,
                playbook=None,
                reason=self._abstention_reason(misses),
                detail=self._abstention_detail(misses, uncertified),
                timings=timings,
            )

        if len(candidates) > 1:
            return Selection(
                action=None,
                playbook=None,
                reason=AbstentionReason.AMBIGUOUS,
                detail=(
                    f"{len(candidates)} certified playbooks hold simultaneously "
                    f"({', '.join(sorted(p.ref for p in candidates))}); the router resolves "
                    "toward abstention because no ranking between them was certified"
                ),
                timings=timings,
                considered=tuple(sorted(p.ref for p in candidates)),
            )

        chosen = candidates[0]
        return Selection(
            action=chosen.action,
            playbook=chosen,
            reason=AbstentionReason.NO_PLAYBOOK_MATCHED,
            detail=chosen.condition.evaluate(observation).detail,
            timings=timings,
            considered=(chosen.ref,),
        )

    @staticmethod
    def _abstention_reason(misses: Sequence[tuple[str, ConditionMatch]]) -> AbstentionReason:
        """The most specific reason among the playbooks that did not match.

        Incomplete data outranks a genuine mismatch, because the two demand
        opposite responses: one is a data-pipeline fault to fix, the other is
        the router working correctly. Reporting "nothing matched" for both sends
        an engineer to instrument features that were already fine.
        """
        if any(m.reason is AbstentionReason.OBSERVATION_INCOMPLETE for _, m in misses):
            return AbstentionReason.OBSERVATION_INCOMPLETE
        return AbstentionReason.NO_PLAYBOOK_MATCHED

    @staticmethod
    def _abstention_detail(
        misses: Sequence[tuple[str, ConditionMatch]],
        uncertified: Sequence[str],
    ) -> str:
        """Say which playbook wanted what, and what it saw instead.

        The per-playbook detail is kept rather than collapsed into a count. A
        caller that cannot tell "the regime did not match" from "the observation
        was missing a field" has to re-evaluate every condition itself, which
        duplicates the router's work in the latency-sensitive path.
        """
        head = f"no certified playbook's condition holds ({len(misses)} evaluated"
        if uncertified:
            head += f"; {len(uncertified)} no longer certified"
        head += "): "
        return head + "; ".join(f"{ref} wanted {match.detail}" for ref, match in misses)

    def selection_for_regime(self, regime: Regime) -> Playbook | None:
        """The single playbook governing ``regime``, or ``None``.

        A read-side convenience for composition roots and diagnostics. Returns
        ``None`` for a regime with zero or several playbooks rather than
        picking one, for the same reason :meth:`select` abstains on ambiguity.
        """
        matching = [
            p for p in self._playbooks.values() if p.condition.regime is regime
        ]
        if len(matching) != 1:
            return None
        return matching[0]

    def regimes(self) -> tuple[Regime, ...]:
        return tuple(sorted({p.condition.regime for p in self._playbooks.values()}, key=str))


def build_playbook(
    *,
    playbook_id: str,
    version: str,
    title: str,
    regime: Regime,
    bounds: Iterable[Bound],
    action: PlaybookAction,
    strategy_id: str,
    strategy_version: str,
    verdict: Any,
    evidence: Sequence[str] = (),
    sizing_basis: SizingBasis | None = None,
) -> Playbook:
    """Construct a playbook bound to a real ``CertificationVerdict``.

    Takes the verdict rather than a hash string so a caller cannot bind a
    playbook to a digest they computed themselves from nothing. The hash is
    derived here, from the verdict, at the moment of construction.

    ``sizing_basis`` records the measurements a derived action was computed
    from. It is optional here because this is the low-level constructor — the
    governed production path is :func:`build_measured_playbook`, which derives
    rather than accepts. A playbook built here with a hand-written action and
    no basis carries no ``sizing_basis``, and that absence is visible to
    whoever reads it.
    """
    from kernel.strategy_registry import CertificationVerdict

    if not isinstance(verdict, CertificationVerdict):
        raise TypeError(
            "build_playbook requires a CertificationVerdict, not a digest. A hash "
            "supplied by the caller is a claim about a verdict rather than the verdict."
        )
    if not verdict.is_certified:
        raise PlaybookNotCertified(
            f"cannot build a playbook from a {verdict.verdict} verdict. A playbook is "
            "how a certified strategy gets traded; one built from a rejection would "
            "route capital to a strategy the firewall refused."
        )
    if verdict.strategy_id != strategy_id or verdict.strategy_version != strategy_version:
        raise PlaybookNotCertified(
            f"verdict is for {verdict.strategy_id}:{verdict.strategy_version}, not "
            f"{strategy_id}:{strategy_version}. Binding a playbook to a verdict about a "
            "different strategy is the certification laundered into a trading policy."
        )
    if sizing_basis is not None and not sizing_basis.verify(action):
        raise DerivationRefused(
            "the supplied action is not what its sizing basis derives. A basis "
            "that does not match its action is provenance for a size nobody "
            "computed, which is worse than no basis at all."
        )
    return Playbook(
        playbook_id=playbook_id,
        version=version,
        title=title,
        condition=RegimeCondition(regime=regime, bounds=tuple(bounds)),
        action=action,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        verdict_hash=hashlib.sha256(verdict.model_dump_json().encode()).hexdigest(),
        evidence=tuple(evidence),
        sizing_basis=sizing_basis,
        registered_at=datetime.now(UTC).isoformat(),
    )


@dataclass(frozen=True)
class CandidatePlaybook:
    """One slow-tier proposal: either a derived size or a named refusal.

    Proposals are not policies. A candidate with an action still needs bounds
    from a human and registration through the governed path; a refused
    candidate records why the measurements did not support a position, so the
    refusal itself becomes reviewable evidence rather than silence. The sweep
    that produces these is the slow reasoner's whole job: scan certified
    strategies against measured regimes and say, per pair, what the numbers
    justify.
    """

    strategy_id: str
    strategy_version: str
    regime: Regime | None
    action: PlaybookAction | None
    basis: SizingBasis | None
    refused_reason: str = ""

    @property
    def viable(self) -> bool:
        return self.action is not None

    def describe(self) -> str:
        where = self.regime.value if self.regime is not None else "unmapped-regime"
        if self.viable:
            assert self.action is not None
            return f"{self.strategy_id}:{self.strategy_version} in {where}: {self.action.describe()}"
        return (
            f"{self.strategy_id}:{self.strategy_version} in {where}: "
            f"no position ({self.refused_reason})"
        )


def propose_candidates(
    *,
    verdict: Any,
    evidence: Any,
    book_size_usd: float,
) -> list[CandidatePlaybook]:
    """Sweep every regime the verdict measured, deriving where possible.

    For each ``regime_sharpe:<name>`` check in the verdict, attempt the same
    derivation publishing uses. Successes carry action plus basis; failures
    carry the refusal reason. Names that are not known regimes are reported
    as refused rather than skipped: a measurement the proposer cannot map is
    a taxonomy gap, and taxonomy gaps hidden by filters become regimes nobody
    watches.
    """
    from kernel.strategy_registry import CertificationVerdict

    if not isinstance(verdict, CertificationVerdict):
        raise TypeError("propose_candidates requires a CertificationVerdict")
    prefix = "regime_sharpe:"
    candidates: list[CandidatePlaybook] = []
    for check in verdict.checks:
        if not check.name.startswith(prefix):
            continue
        raw = check.name[len(prefix):]
        try:
            regime = Regime(raw)
        except ValueError:
            candidates.append(
                CandidatePlaybook(
                    strategy_id=verdict.strategy_id,
                    strategy_version=verdict.strategy_version,
                    regime=None,
                    action=None,
                    basis=None,
                    refused_reason=(
                        f"measured regime {raw!r} is not a known regime: "
                        "extend the Regime taxonomy before trading it"
                    ),
                )
            )
            continue
        try:
            action, basis = derive_action(
                verdict=verdict,
                evidence=evidence,
                regime=regime,
                book_size_usd=book_size_usd,
            )
        except DerivationRefused as exc:
            candidates.append(
                CandidatePlaybook(
                    strategy_id=verdict.strategy_id,
                    strategy_version=verdict.strategy_version,
                    regime=regime,
                    action=None,
                    basis=None,
                    refused_reason=str(exc),
                )
            )
            continue
        candidates.append(
            CandidatePlaybook(
                strategy_id=verdict.strategy_id,
                strategy_version=verdict.strategy_version,
                regime=regime,
                action=action,
                basis=basis,
            )
        )
    return candidates


def persist_router(router: PlaybookRouter, sink: Any) -> int:
    """Write every registered playbook to a durable store. Returns the count
    written (already-stored identical rows are no-ops rather than duplicates).

    A module function rather than a router method, on purpose: the router's
    public surface is the fast tier's contract, and the engine test pins it
    exactly. Durability is a composition concern that lives beside the router,
    not on it — growing the router's surface is how "reads only" erodes.
    """
    written = 0
    for ref in router.registered():
        playbook = router._playbooks[ref]
        sink.save(
            playbook.playbook_id,
            playbook.version,
            playbook.content_hash,
            playbook.model_dump_json(),
            playbook.registered_at,
        )
        written += 1
    return written


def load_router(
    oracle: CertificationOracle, sink: Any
) -> tuple[PlaybookRouter, tuple[str, ...]]:
    """Rebuild a router from a durable store after a restart. Returns the
    router plus the refs skipped as uncertified.

    Every stored playbook whose strategy is *currently* certified joins;
    a playbook whose verdict was revoked while the process was down stays in
    the store but never joins the router. The skipped refs return alongside
    rather than hiding: silently dropping them would hide a revocation,
    silently admitting them would trade it. What must never happen is trading
    a revoked strategy because its playbook survived a restart that its
    verdict did not.
    """
    router = PlaybookRouter(oracle)
    skipped: list[str] = []
    for ref, _content_hash, payload in sink.read_all():
        playbook = Playbook.model_validate_json(payload)
        if oracle.is_certified(playbook.strategy_id, playbook.strategy_version):
            router._playbooks[playbook.ref] = playbook
        else:
            skipped.append(ref)
    return router, tuple(skipped)


def build_measured_playbook(
    *,
    playbook_id: str,
    version: str,
    title: str,
    regime: Regime,
    bounds: Iterable[Bound],
    strategy_id: str,
    strategy_version: str,
    verdict: Any,
    evidence: Any,
    book_size_usd: float,
    sources: Sequence[str] = (),
) -> Playbook:
    """Build a playbook whose action is derived from measurements.

    This is the governed production path. The caller supplies the regime, the
    bounds, and the book — everything a person can legitimately know — and the
    action comes from :func:`derive_action`, which refuses rather than guesses
    whenever the measurements do not support a position.

    The bounds stay caller-supplied on purpose, and that is the one place this
    function trusts a person. Deriving thresholds from the same backtest that
    justifies them is selection bias wearing a derivation's clothes: the data
    cannot both choose the threshold and vouch for it, which is the overfitting
    the PBO check exists to catch. What the measurements do instead is gate:
    the regime must have been measured profitable, and the bounds are then
    recorded under the content hash alongside the basis that justifies trading
    them.
    """
    action, basis = derive_action(
        verdict=verdict, evidence=evidence, regime=regime, book_size_usd=book_size_usd
    )
    return build_playbook(
        playbook_id=playbook_id,
        version=version,
        title=title,
        regime=regime,
        bounds=bounds,
        action=action,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        verdict=verdict,
        evidence=sources,
        sizing_basis=basis,
    )


# ══════════════════════════════════════════════════════════════════════════
# Domain of competence  (architecture section 2, Layer 9)
# ══════════════════════════════════════════════════════════════════════════
#
# "Every strategy/model has: DomainOfCompetence" -- with the worked example
#
#     valid:   TREND_UP  NORMAL_VOL  HIGH_LIQUIDITY
#     invalid: EARNINGS  FLASH_CRASH  LIQUIDITY_CRISIS
#
# This is the one clause of Layer 9 with no implementation anywhere in the tree,
# which the goal registry audit recorded as an outstanding gap under G100 rather
# than letting it pass as claimed. It is built here.
#
# The clause is NOT satisfied by `RegimeCondition`, which is the tempting thing
# to point at. The two answer different questions:
#
#   RegimeCondition       WHEN does this playbook fire?  bounds arithmetic,
#                         evaluated per observation, one playbook.
#   DomainOfCompetence    WHERE is this strategy valid?  membership in a named
#                         set, one strategy across every playbook it owns.
#
# So a competence declaration is deliberately *not* a field on `Playbook`. If it
# were, two playbooks binding the same strategy could declare different
# competences, and the question "may this strategy trade in a crisis?" would have
# no single answer -- it would depend which playbook the router happened to be
# holding. A strategy has one competence or the concept is not a concept.


class CompetenceNotDeclared(RuntimeError):
    """A playbook bound to a strategy that has declared no competence."""


class StrategyIncompetent(RuntimeError):
    """A playbook would activate outside its strategy's declared competence."""


class InconsistentCompetence(ValueError):
    """A competence declaration that contradicts itself."""


class DomainOfCompetence(BaseModel):
    """The named states in which one strategy is permitted to operate.

    Competence is **opt-in**: :meth:`is_competent` is true only for a regime the
    strategy explicitly listed. A regime that appears in neither list is
    incompetent.

    That is the load-bearing decision, and it is the opposite of the intuitive
    one. If an unlisted regime were treated as permitted, then `valid` would be
    decorative and `invalid` would be the only real contract -- and the set of
    regimes a strategy may trade in would silently widen every time a new
    `Regime` member was added to this module. A refusal is not the absence of a
    permission, so the safe reading is that nothing is permitted.

    Why `invalid` exists at all, given unlisted is already a refusal: it makes
    the refusal *specific*. Without it, a refusal in CRISIS and a refusal in an
    unrelated regime are indistinguishable in the operator's log, which is the
    "nothing happened is a finding" problem this module treats as a defect. An
    explicitly invalid regime is one the strategy has recorded going wrong, and
    saying so is worth more than a generic "not permitted".
    """

    model_config = {"frozen": True}

    #: Regimes the strategy operates in. Must be non-empty.
    valid: frozenset[Regime]
    #: Regimes the strategy has recorded as unsafe for itself. Disjoint from
    #: `valid`; a regime cannot be both.
    invalid: frozenset[Regime] = frozenset()

    @model_validator(mode="after")
    def _must_claim_something(self) -> DomainOfCompetence:
        """A strategy competent in no state is a different claim, and is refused.

        ``valid=()`` with an empty ``invalid`` describes a strategy that is
        everywhere forbidden. That is a legitimate thing to want, but it is not
        a domain of competence, and letting it through would mean an empty
        declaration could not be distinguished from a forgotten one.
        """
        if not self.valid:
            raise InconsistentCompetence(
                "a domain of competence must name at least one valid regime. An "
                "empty valid set describes a strategy forbidden everywhere, "
                "which is a different statement from one that was never written."
            )
        return self

    @model_validator(mode="after")
    def _must_not_contradict_itself(self) -> DomainOfCompetence:
        """A regime cannot be both valid and invalid.

        Rejected at declaration rather than resolved at use. If `invalid` were
        allowed to override `valid`, a typo in either list would resolve silently
        to the more permissive reading, and a self-contradicting declaration
        would be indistinguishable from a coherent one. Failing here means the
        contradiction is reported where it can still be fixed.
        """
        both = self.valid & self.invalid
        if both:
            raise InconsistentCompetence(
                f"regime(s) {sorted(r.value for r in both)} declared both valid "
                "and invalid. Competence cannot be both permitted and refused; "
                "a declaration that says so is a contradiction, not a priority."
            )
        return self

    def is_competent(self, regime: Regime) -> bool:
        """True only for an explicitly valid regime."""
        return regime in self.valid

    def refusal(self, regime: Regime) -> str:
        """Why this strategy may not operate in ``regime``.

        Distinct messages for the two refusal kinds, because the operator
        reading them is debugging different problems: "I said this was unsafe"
        is a strategy that has learned something, and "I never claimed this" is
        a gap in coverage. Both refuse, and both say which.
        """
        if regime in self.invalid:
            return (
                f"{regime.value} is explicitly outside this strategy's "
                "competence, having been recorded as unsafe for it"
            )
        if regime not in self.valid:
            unclaimed = sorted(r.value for r in self.unaddressed())
            return (
                f"{regime.value} is not a regime this strategy declared "
                f"competence for; unaddressed regimes: {unclaimed}"
            )
        return ""  # not a refusal

    def unaddressed(self) -> frozenset[Regime]:
        """Regimes this declaration is silent about.

        Exposed so coverage can be audited rather than assumed. A declaration
        naming one of five regimes is not wrong, but it is worth being able to
        see that it is silent about the other four.
        """
        return frozenset(Regime) - self.valid - self.invalid

    def coverage(self) -> tuple[frozenset[Regime], frozenset[Regime]]:
        """``(valid, unaddressed)`` -- what is permitted and what is silent."""
        return self.valid, self.unaddressed()


class StrategyCompetence:
    """One :class:`DomainOfCompetence` per strategy, immutable once declared.

    Keyed by ``(strategy_id, strategy_version)`` because that is the identity the
    certification oracle uses, and competence must not be looser than
    certification. A strategy's competence is fixed at declaration and never
    amended: changing it is declaring a new strategy version, exactly as changing
    a playbook's policy is a new playbook version with a new verdict. That is
    what lets `PlaybookRouter._check_competence` run once at admission and stay
    correct.
    """

    def __init__(
        self, declarations: Mapping[tuple[str, str], DomainOfCompetence] | None = None
    ) -> None:
        self._by_strategy: dict[tuple[str, str], DomainOfCompetence] = dict(
            declarations or {}
        )

    def declare(
        self,
        strategy_id: str,
        strategy_version: str,
        domain: DomainOfCompetence,
    ) -> DomainOfCompetence:
        """Record a strategy's competence, or refuse to change it."""
        key = (strategy_id, strategy_version)
        existing = self._by_strategy.get(key)
        if existing is not None and existing != domain:
            raise InconsistentCompetence(
                f"{strategy_id}:{strategy_version} already declared competence "
                f"valid={sorted(r.value for r in existing.valid)} / "
                f"invalid={sorted(r.value for r in existing.invalid)}, and a "
                "different one cannot replace it. Widening or narrowing what a "
                "strategy may trade in is a new strategy version with a new "
                "verdict, not an edit -- otherwise the same strategy_id would "
                "mean two different things at two points in one replay."
            )
        self._by_strategy[key] = domain
        return domain

    def for_strategy(
        self, strategy_id: str, strategy_version: str
    ) -> DomainOfCompetence | None:
        """The declared competence, or ``None`` if never declared.

        ``None`` is meaningful and not a lookup miss: it is the answer that
        makes the router refuse, because competence is opt-in.
        """
        return self._by_strategy.get((strategy_id, strategy_version))

    def declared(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._by_strategy))
