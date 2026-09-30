"""Promotion requires measured superiority plus an identified human (G200).

The arena stages champion-vs-challenger trials; this file pins the two gates
that make promotion honest rather than ceremonial. Measured result without a
human is auto-promotion; a human without a measured result is favouritism.
Both are refused, and a human cannot overrule the evidence in either
direction — the fail-closed rule applies to operators too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.challenger import ChallengeRegistry, TrialResult, TrialState
from core.persistence import SqliteMemoryStore
from research.evaluation import EvaluationRecord, EvaluationVerdict


@pytest.fixture()
def registry(tmp_path: Path) -> ChallengeRegistry:
    return ChallengeRegistry(SqliteMemoryStore(tmp_path / "trial.db"))


def _evaluated(
    registry: ChallengeRegistry,
    name: str = "trial-1",
    *,
    champion_pnl: float = 100.0,
    challenger_pnl: float = 200.0,
    trades: int = 30,
) -> None:
    """Drive a trial to EVALUATED with a hand-scored result. Hand-scoring is
    legitimate here because the honesty gates under test live in promote(),
    not in the scoring: this suite asks what promotion requires, not whether
    any particular backtest won."""
    from research.evaluation import evaluate_trial

    trial = registry.propose(name, metric="pnl")
    trial.champion = TrialResult("champion", trades, champion_pnl, 55.0, 2.0)
    trial.challenger = TrialResult("challenger", trades, challenger_pnl, 60.0, 1.5)
    trial.evaluation = evaluate_trial(
        champion_trades=trades,
        challenger_trades=trades,
        metric="pnl",
        champion_value=champion_pnl,
        challenger_value=challenger_pnl,
        trial_name=name,
    )
    trial.state = TrialState.EVALUATED


# ══════════════════════════════════════════════════════════════════════════
# Measured result AND explicit human action; neither alone suffices
# ══════════════════════════════════════════════════════════════════════════


def test_promotion_before_evaluation_is_refused(registry: ChallengeRegistry) -> None:
    """An unevaluated trial has no measured result. Promoting it would be
    promotion by proposal — the form thinks it already won."""
    registry.propose("trial-1", metric="pnl")
    with pytest.raises(PermissionError, match="requires EVALUATED evidence"):
        registry.promote("trial-1", "human-1")


def test_a_failing_verdict_cannot_be_overruled_by_a_human(
    registry: ChallengeRegistry,
) -> None:
    """The direction that matters most: evidence against, human in favour.
    A human who can overrule a FAIL verdict is not a gate but an audience,
    so the refusal names the verdict rather than the operator."""
    _evaluated(registry, champion_pnl=200.0, challenger_pnl=100.0)
    with pytest.raises(PermissionError, match="requires PASS"):
        registry.promote("trial-1", "human-1")
    assert registry.trials["trial-1"].state is TrialState.EVALUATED


def test_an_inconclusive_verdict_cannot_be_promoted(
    registry: ChallengeRegistry,
) -> None:
    """Too few trades is not a pass with an asterisk: INCONCLUSIVE refuses
    exactly like FAIL, because promoting on insufficient evidence is how a
    lucky small sample becomes production."""
    _evaluated(registry, trades=2)
    with pytest.raises(PermissionError, match="requires PASS"):
        registry.promote("trial-1", "human-1")


def test_promotion_without_an_identified_human_is_refused(
    registry: ChallengeRegistry,
) -> None:
    """'Promoted by nobody' is not an audit trail. An explicit human action
    means an identified human; an empty operator id is the form of the gate
    without its substance."""
    _evaluated(registry)
    for nobody in ("", "   "):
        with pytest.raises(PermissionError, match="no operator named"):
            registry.promote("trial-1", nobody)
    assert registry.trials["trial-1"].state is TrialState.EVALUATED


def test_pass_plus_human_promotes_and_records_both(
    registry: ChallengeRegistry,
) -> None:
    """The happy path, with both halves visible in the outcome: the verdict
    that permitted it and the operator who did it."""
    _evaluated(registry)
    outcome = registry.promote("trial-1", "human-1")
    assert outcome == {"promoted": True, "state": "PROMOTED"}
    trial = registry.trials["trial-1"]
    assert trial.state is TrialState.PROMOTED
    assert trial.promoted_by == "human-1"
    decisions = registry.store.iter_event_payloads("CHALLENGER_DECISION")
    assert any(
        event.get("state") == "PROMOTED" and event.get("by") == "human-1"
        for event in decisions
    )


def test_rejection_is_always_available(registry: ChallengeRegistry) -> None:
    """Rejecting needs no evidence and no verdict: stopping something must
    always be easier than shipping it. A rejection path gated on measurement
    would keep a bad trial alive by declining to evaluate it."""
    registry.propose("trial-1", metric="pnl")
    outcome = registry.reject("trial-1", "human-1", note="not convincing")
    assert outcome == {"promoted": False, "state": "REJECTED"}
    assert registry.trials["trial-1"].state is TrialState.REJECTED


def test_promotion_is_not_repeatable(registry: ChallengeRegistry) -> None:
    """A promoted trial cannot be promoted again: the second call finds a
    non-EVALUATED state and refuses, so replaying the approval cannot
    manufacture a second promotion event."""
    _evaluated(registry)
    registry.promote("trial-1", "human-1")
    with pytest.raises(PermissionError, match="requires EVALUATED"):
        registry.promote("trial-1", "human-1")


def test_evaluation_record_survives_on_the_trial(registry: ChallengeRegistry) -> None:
    """The evidence behind a promotion stays attached to the trial it
    promoted: an approval whose reasons vanished is indistinguishable from
    favouritism in hindsight."""
    _evaluated(registry)
    trial = registry.trials["trial-1"]
    assert isinstance(trial.evaluation, EvaluationRecord)
    assert trial.evaluation.verdict is EvaluationVerdict.PASS
