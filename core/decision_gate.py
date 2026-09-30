"""The TRADE / WAIT / ESCALATE / ABSTAIN gate (goal G110).

A model output is a proposal; this gate is the decision. It consumes the
measurements the rest of the system produces — the conformal interval width,
the deflated Sharpe against its bar, the regime stability in bars — and
returns one of four outcomes, each with the triggering condition recorded.
ABSTAIN is first-class, never a default fallthrough: a gate that abstains
only when nothing else matched has not decided anything.

The outcome vocabulary matches ``kernel.playbook.PlaybookActionKind`` by
value (TRADE, WAIT, ESCALATE, ABSTAIN), so a gate decision can flow into a
playbook-shaped action without translation. REDUCE is deliberately absent:
sizing down is the playbook derivation's job, and a gate that also sizes
would split one decision across two places.

Order of checks is the fail-closed ordering, and each check is independent:
the first failure in this order decides, so the reason always names the most
safety-relevant problem rather than the first one evaluated.

1. **ABSTAIN on an unmeasurable interval.** Infinite or NaN width, or a
   non-positive calibration count, means there is no uncertainty statement
   to act on. Acting without one is wrong under every policy.
2. **ABSTAIN on an unstable regime.** Fewer stable bars than the minimum
   means the ground is moving; a decision made now is priced against a state
   that may already be gone.
3. **ABSTAIN on excessive width.** An interval wider than the tolerance is
   an honest statement of ignorance, and the correct response to ignorance
   is to not trade — not to trade "carefully".
4. **ESCALATE on a weak edge with a tight interval.** The measurement is
   trustworthy and says the edge is below the bar. That is a judgment call
   for a human, not an automatic no: the bar may be wrong for this regime.
5. **WAIT on a weak edge with a wide interval.** Untrustworthy measurement
   of a weak edge: gather evidence, change nothing.
6. **TRADE otherwise.** Edge above the bar, tight interval, stable regime —
   the only combination that authorises action.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from schemas.contracts import DecisionAction

__all__ = [
    "GateDecision",
    "GateInputs",
    "decide",
]

#: The gate's outcome vocabulary IS the schema's closed decision vocabulary:
#: no translation layer exists to drift. A gate outcome anything else cannot
#: be expressed, which is the point.
GateOutcome = DecisionAction


@dataclass(frozen=True)
class GateInputs:
    """Everything the gate may consider. All fields are measurements or bars.

    No prices, no predictions, no model outputs: the gate judges the quality
    of the evidence, and evidence quality is fully described by how uncertain
    the estimate is (interval width), how strong the edge is (deflated Sharpe
    against its bar), and how long the world has held still (stable bars).
    """

    interval_width: float
    max_interval_width: float
    deflated_sharpe: float
    sharpe_bar: float
    stable_bars: int
    min_stable_bars: int
    n_calibration: int = 0


@dataclass(frozen=True)
class GateDecision:
    """One gate outcome with the condition that triggered it.

    ``trigger`` names the check and the numbers behind it, so a decision can
    be audited without re-running the gate. ``outcome`` uses the shared
    vocabulary by value.
    """

    outcome: GateOutcome
    trigger: str

    def __str__(self) -> str:
        return f"{self.outcome}: {self.trigger}"


def decide(inputs: GateInputs) -> GateDecision:
    """Apply the gate in fail-closed order. Pure function of its inputs."""
    if not math.isfinite(inputs.interval_width) or inputs.interval_width < 0.0:
        return GateDecision(
            DecisionAction.ABSTAIN,
            f"interval width {inputs.interval_width!r} is not a measurement; "
            "no uncertainty statement, no action",
        )
    if inputs.n_calibration <= 0:
        return GateDecision(
            DecisionAction.ABSTAIN,
            f"calibration count {inputs.n_calibration} means no interval was "
            "earned; no uncertainty statement, no action",
        )
    if inputs.stable_bars < inputs.min_stable_bars:
        return GateDecision(
            DecisionAction.ABSTAIN,
            f"regime stable for {inputs.stable_bars} bars, below the "
            f"{inputs.min_stable_bars}-bar minimum: the ground is moving",
        )
    if inputs.interval_width > inputs.max_interval_width:
        return GateDecision(
            DecisionAction.ABSTAIN,
            f"interval width {inputs.interval_width:.4f} exceeds tolerance "
            f"{inputs.max_interval_width:.4f}: honest ignorance, no trade",
        )
    if inputs.deflated_sharpe < inputs.sharpe_bar:
        if inputs.interval_width <= inputs.max_interval_width / 2.0:
            return GateDecision(
                DecisionAction.ESCALATE,
                f"deflated Sharpe {inputs.deflated_sharpe:.4f} below bar "
                f"{inputs.sharpe_bar:.4f} on a tight interval: trustworthy "
                "measurement of a weak edge, a human decides whether the bar "
                "is wrong for this regime",
            )
        return GateDecision(
            DecisionAction.WAIT,
            f"deflated Sharpe {inputs.deflated_sharpe:.4f} below bar "
            f"{inputs.sharpe_bar:.4f} on a wide interval: gather evidence, "
            "change nothing",
        )
    return GateDecision(
        DecisionAction.TRADE,
        f"deflated Sharpe {inputs.deflated_sharpe:.4f} clears bar "
        f"{inputs.sharpe_bar:.4f}, interval width {inputs.interval_width:.4f} "
        f"within tolerance, regime stable {inputs.stable_bars} bars",
    )
