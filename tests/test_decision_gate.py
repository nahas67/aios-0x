"""The gate decides; the model proposes (goal G110).

TRADE / WAIT / ESCALATE / ABSTAIN, each with the triggering condition
recorded. The properties that matter: ABSTAIN is first-class rather than a
fallthrough default, the checks run in fail-closed order so the reason always
names the most safety-relevant problem, and the outcome vocabulary matches
the playbook's by value so no translation layer can drift.
"""

from __future__ import annotations

from core.decision_gate import GateInputs, decide


def _inputs(**overrides) -> GateInputs:
    base = {
        "interval_width": 0.5,
        "max_interval_width": 2.0,
        "deflated_sharpe": 1.4,
        "sharpe_bar": 0.95,
        "stable_bars": 60,
        "min_stable_bars": 30,
        "n_calibration": 200,
    }
    base.update(overrides)
    return GateInputs(**base)


# ══════════════════════════════════════════════════════════════════════════
# Each outcome, with its trigger recorded
# ══════════════════════════════════════════════════════════════════════════


def test_a_strong_edge_on_tight_ground_trades() -> None:
    """The only combination that authorises action: edge above the bar,
    tight interval, stable regime. Everything else is a refusal with a name."""
    decision = decide(_inputs())
    assert decision.outcome == "TRADE"
    assert "1.4000" in decision.trigger
    assert "60 bars" in decision.trigger


def test_an_unmeasurable_interval_abstains_first() -> None:
    """Fail-closed order starts here: without an uncertainty statement no
    other measurement matters, because every other check assumes one."""
    for bad_width in (float("inf"), float("nan"), -1.0):
        decision = decide(_inputs(interval_width=bad_width))
        assert decision.outcome == "ABSTAIN"
        assert "no uncertainty statement" in decision.trigger


def test_an_uncalibrated_interval_abstains() -> None:
    """Zero calibration means no interval was earned. Acting on an unearned
    interval is the same as acting on none."""
    decision = decide(_inputs(n_calibration=0))
    assert decision.outcome == "ABSTAIN"
    assert "no interval was earned" in decision.trigger


def test_a_moving_regime_abstains() -> None:
    """A decision priced against a state that may already be gone is priced
    against nothing. Stability is checked before strength."""
    decision = decide(_inputs(stable_bars=5))
    assert decision.outcome == "ABSTAIN"
    assert "ground is moving" in decision.trigger


def test_honest_ignorance_abstains() -> None:
    """An interval wider than tolerance is an honest statement of ignorance,
    and the correct response to ignorance is to not trade — not to trade
    'carefully' at a smaller size. Sizing is the playbook's job; the gate's
    job is permission."""
    decision = decide(_inputs(interval_width=3.0))
    assert decision.outcome == "ABSTAIN"
    assert "honest ignorance" in decision.trigger


def test_a_trustworthy_weak_edge_escalates() -> None:
    """Below the bar on a tight interval: the measurement is good and the
    edge is weak, which is a judgment call for a human. The bar may be wrong
    for this regime — an automatic no would hide that question forever."""
    decision = decide(_inputs(deflated_sharpe=0.4, interval_width=0.5))
    assert decision.outcome == "ESCALATE"
    assert "human decides" in decision.trigger


def test_an_untrustworthy_weak_edge_waits() -> None:
    """Below the bar on a wide-but-acceptable interval: gather evidence,
    change nothing. Escalating noise would page a human for weather."""
    decision = decide(_inputs(deflated_sharpe=0.4, interval_width=1.5))
    assert decision.outcome == "WAIT"
    assert "gather evidence" in decision.trigger


def test_the_outcome_vocabulary_matches_the_playbook() -> None:
    """By value, not by convention: a translation layer between the gate and
    the playbook is a place for the two vocabularies to drift apart."""
    from kernel.playbook import PlaybookActionKind

    playbook_values = {kind.value for kind in PlaybookActionKind}
    for outcome in ("TRADE", "WAIT", "ESCALATE", "ABSTAIN"):
        assert outcome in playbook_values


def test_the_decision_describes_itself() -> None:
    """An audit reads decisions, not inputs. The string form carries both."""
    decision = decide(_inputs())
    assert str(decision).startswith("TRADE:")
    assert "1.4000" in str(decision)


def test_fail_closed_order_prefers_the_safety_problem() -> None:
    """Several things wrong at once: the reason names the most
    safety-relevant one (unmeasurable interval), not the first evaluated or
    the most flattering."""
    decision = decide(_inputs(interval_width=float("nan"), stable_bars=0, deflated_sharpe=-5.0))
    assert decision.outcome == "ABSTAIN"
    assert "no uncertainty statement" in decision.trigger
