"""Derive a strategy's domain of competence from the verdict that certified it.

WHY THIS IS A DERIVATION, NOT A DECLARATION.

The Layer 9 gate (`PlaybookRouter._check_competence`) has been implemented and
correct since `6b80af2` and wired nowhere in production, so it enforces nothing
outside tests. The blocker was recorded as "a decision about which strategies are
competent where" -- too pessimistic, because certification already makes that
decision.

For each regime in the supplied decomposition, certification adds a check named
`REGIME_CHECK_PREFIX + name`, and it passes only when the regime is neither too thin
to support a playbook nor losing money net of costs. A verdict therefore already
records, per regime, whether the strategy was measured good enough to trade. So:

    competent in R  <=>  the verdict carries a PASSING `regime_sharpe:R` check

Non-circular, and that is the whole reason to prefer it. Deriving competence from
the playbooks would be circular -- a strategy's competence would be whatever its own
playbooks happen to assert, and the gate would approve of anything it was shown.
Deriving it from the verdict means a playbook is checked against the measurements
that justified the strategy, which is what the certification step exists to
establish, and a playbook cannot widen its own permissions by existing.

The three states map onto the three `DomainOfCompetence` needs:

  passing check   -> valid        measured good enough to trade
  failing check   -> invalid      measured thin or losing -- recorded explicitly,
                                 so a refusal can say WHY
  no check        -> unaddressed, and therefore INCOMPETENT

The last is the same rule the router and the TLA+ spec both apply: silence is not
permission. A regime certification never decomposed is not a regime the strategy was
vouched for.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .playbook import DomainOfCompetence, Regime
from .strategy_registry import REGIME_CHECK_PREFIX

__all__ = [
    "CompetenceResolver",
    "IncompetentInEveryMeasuredRegime",
    "competence_from_verdict",
    "competence_resolver",
]


def competence_from_verdict(verdict: Any) -> DomainOfCompetence:
    """The regimes in which this verdict says the strategy may trade.

    Raises twice, and the two are deliberately different kinds of failure.

    No per-regime checks at all: that is the honest answer for a strategy nobody
    measured per-regime, and it is raised rather than returned empty because an
    empty declaration reads two ways -- "competent nowhere" and "never declared"
    -- and only one of them is what the data says.

    Measured in every regime and competent in none: `IncompetentInEveryMeasuredRegime`,
    which names the regimes and their measured Sharpes. Raised before the
    constructor can, because the constructor's own refusal is about the model's
    shape rather than about this strategy, and reporting the most informative case
    as the least informative one is what the `invalid` set exists to prevent.
    """
    checks = getattr(verdict, "checks", None) or ()
    by_value = {regime.value: regime for regime in Regime}

    valid: set[Regime] = set()
    invalid: set[Regime] = set()

    for check in checks:
        name = getattr(check, "name", None)
        if not isinstance(name, str) or not name.startswith(REGIME_CHECK_PREFIX):
            continue
        regime = by_value.get(name[len(REGIME_CHECK_PREFIX):])
        if regime is None:
            # A check naming a regime this build does not know. Not an error: the
            # verdict may come from a newer registry, and refusing to trade an
            # unknown regime is the same default as an unmeasured one. Silently
            # skipping it would be the alternative, and that would make competence
            # depend on which build reads the verdict.
            continue
        if getattr(check, "passed", False):
            valid.add(regime)
        else:
            invalid.add(regime)

    if not valid and not invalid:
        raise ValueError(
            f"verdict for {getattr(verdict, 'strategy_id', '?')}:"
            f"{getattr(verdict, 'strategy_version', '?')} carries no "
            f"`{REGIME_CHECK_PREFIX}<regime>` checks, so it records no per-regime "
            "measurement and therefore no domain of competence. Certify with a "
            "regime decomposition before trading this strategy; declaring one by "
            "hand here would be a claim the measurements do not support."
        )

    if not valid and invalid:
        # Checked BEFORE the constructor, because the constructor's own refusal for an
        # empty valid set is a statement about the model's shape ("a domain of
        # competence must name at least one valid regime") and says nothing about this
        # strategy. Which is precisely the confusion: the most informative case in the
        # design was being reported as the least informative one.
        detail = ", ".join(
            f"{regime.value} (net Sharpe {value:.4f})"
            for regime, value in sorted(
                (r, _value_of(verdict, r)) for r in invalid
            )
        )
        raise IncompetentInEveryMeasuredRegime(
            f"{getattr(verdict, 'strategy_id', '?')}:"
            f"{getattr(verdict, 'strategy_version', '?')} was measured in "
            f"{len(invalid)} regime(s) and is competent in none of them: {detail}. "
            "A regime that was measured and lost is not the same as a regime nobody "
            "measured, and the difference is the actionable part: these regimes were "
            "tried. Amending the measurement means certifying a new version, which is "
            "the only way a verdict changes -- deliberately, rather than by a "
            "declaration made here, which would be the circular version of this whole "
            "arrangement."
        )

    return DomainOfCompetence(valid=frozenset(valid), invalid=frozenset(invalid))


def _value_of(verdict: Any, regime: Any) -> float:
    """The net Sharpe the verdict recorded for one regime, for the message.

    Reads the same check the pass/fail decision was made from, so the number quoted
    is the one the gate used rather than a second lookup that could disagree. Returns
    0.0 if the check has no numeric value, because a message that says "0.0000" is
    better than one that raises while explaining a refusal.
    """
    for check in getattr(verdict, "checks", None) or ():
        name = getattr(check, "name", None)
        if isinstance(name, str) and name == f"{REGIME_CHECK_PREFIX}{regime.value}":
            value = getattr(check, "value", None)
            return float(value) if isinstance(value, (int, float)) else 0.0
    return 0.0


class IncompetentInEveryMeasuredRegime(RuntimeError):
    """The strategy was measured in every regime it decomposed, and lost in all of them.

    Distinct from "no decomposition" on purpose, and deliberately NOT a `ValueError`:
    `competence_resolver` catches `ValueError` to turn an absent decomposition into
    `None`, so an error deriving from it would be swallowed into exactly the refusal
    this class exists to replace. Deriving from `RuntimeError` makes the separation
    structural rather than a matter of ordering two excepts.

    The state is reachable and not exotic. Regime slices are classified OPERATIONAL by
    `build_verdict`, so a strategy that clears deflated Sharpe, PSR and PBO and then
    loses money in every decomposed regime is `CERTIFIED_WITH_LIMITS` -- which
    `is_certified` accepts. It is a real strategy, admitted by the firewall, that may
    trade nowhere. Saying so is the whole point.
    """


#: What a resolver is handed and must return: the competence of one
#: (strategy_id, strategy_version), or ``None`` when there is none to give.
CompetenceResolver = Callable[[str, str], DomainOfCompetence | None]


def competence_resolver(registry: Any) -> CompetenceResolver:
    """Resolve a strategy's competence from the registry, at the moment it is asked.

    Lazy rather than a snapshot, and the laziness is the whole point. A snapshot
    taken at construction describes the registry as it was when the process started,
    which is before any strategy has been certified -- so a boot-time snapshot is
    always empty and every strategy is permanently incompetent. Resolving per
    admission reads the verdict that exists at the time the playbook is offered.

    Sound as a one-time check, which is all `_check_competence` claims to be, because
    a recorded verdict is immutable: the competence of a given
    (strategy_id, strategy_version) is fixed once its verdict is, so a check made at
    admission cannot go stale. Were a verdict ever overwritable in place, this would
    stop being true and admission-time checking would need to move onto selection.

    Returns ``None`` -- which `_check_competence` reports as `CompetenceNotDeclared`,
    with the reason -- for an unknown strategy, an uncertified one, and one whose
    verdict carries no per-regime decomposition. All three mean the same thing to a
    caller: no competence can be shown, so none is granted.

    One case does NOT come back as ``None``. A verdict that measured every regime it
    decomposed and passed none of them raises `IncompetentInEveryMeasuredRegime` out
    of here, and so out of `PlaybookRouter.register`. That is a caller-visible
    behaviour change, made because folding it into the same ``None`` reported a
    strategy that had been measured and had lost as one nobody had measured -- and
    pointed the operator at hand-declaring a competence, the one remedy this design
    forbids. Callers that catch gate failures broadly should note that
    `CompetenceNotDeclared` and `StrategyIncompetent` are the two refusals, and this
    is a third, raised rather than returned.
    """

    def resolve(strategy_id: str, strategy_version: str) -> DomainOfCompetence | None:
        try:
            artifact = registry.get(strategy_id, strategy_version)
        except KeyError:
            return None
        verdict = getattr(artifact, "verdict", None)
        if verdict is None:
            return None
        try:
            return competence_from_verdict(verdict)
        except ValueError:
            # An absent decomposition only. `IncompetentInEveryMeasuredRegime` is a
            # RuntimeError precisely so it arrives here as a raised error rather than
            # being folded into this `None` -- folding it in is what made a strategy
            # that lost in every measured regime indistinguishable from one nobody
            # measured.
            return None

    return resolve
