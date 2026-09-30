"""Detecting contamination instead of being told about it (vNext goal G080).

The certification firewall had two checks that took a boolean:
``look_ahead=False`` and ``survivorship_bias=False``. Both were promises. This
module makes them measurements, and it is the last place in the firewall where
a caller could assert a result rather than produce one.

**Look-ahead** is detectable from timestamps. If a feature was not knowable at
the moment the decision was made, the decision used the future. That is
checkable whenever a system records *when its inputs became available*, which
is why the six-clock :class:`~core.temporal.TemporalInstant` and the
``available_at`` join key exist: without them, look-ahead is unfalsifiable, and
an unfalsifiable check is a comment.

Two distinct failures are separated, because they are fixed differently:

*Direct contamination* — a feature that was not yet knowable at decision time.
The fix is a pipeline bug.

*Cross-sectional contamination* — the panel was assembled so that some
instruments had data at a moment when their peers did not. A backtest that
resamples an incomplete cross-section at a single instant is using the
composition of the panel as an oracle, and no per-row timestamp check catches
it. The fix is a universe rule.

**Survivorship** is detectable from the security master. If instruments were
delisted during the test window and none of them appear in the tested universe,
the result was produced on survivors alone. The absence is the evidence, which
is why this needs a query that reaches closed identities rather than current
ones — a delisted instrument has a superseded ``recorded_to``, and a lookup that
only reads current beliefs is structurally blind to the thing it is looking for.

Both detectors return a report naming what was found, not a pass/fail flag, so
a certification record states the evidence rather than a conclusion.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from core.security_master import ActionType, CorporateAction

__all__ = [
    "ContaminationReport",
    "LookAheadFinding",
    "ObservationTiming",
    "PanelTiming",
    "SurvivorshipFinding",
    "SurvivorshipReport",
    "detect_look_ahead",
    "detect_survivorship",
]


# ══════════════════════════════════════════════════════════════════════════
# Look-ahead
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ObservationTiming:
    """One decision's inputs, with when each became knowable.

    ``feature_available_at`` is the join key, not the feature's own timestamp.
    A feature computed at 09:00 from a bar published at 09:30 is contaminated
    even though the computation happened first.
    """

    observation_id: str
    decision_time: datetime
    feature_available_at: datetime
    label_available_at: datetime | None = None

    def is_contaminated(self) -> bool:
        """Whether any input post-dates the decision."""
        if self.feature_available_at > self.decision_time:
            return True
        return self.label_available_at is not None and self.label_available_at > self.decision_time


@dataclass(frozen=True)
class LookAheadFinding:
    """One contaminated observation, named."""

    observation_id: str
    decision_time: datetime
    feature_available_at: datetime
    reason: str
    lag: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "decision_time": self.decision_time.isoformat(),
            "feature_available_at": self.feature_available_at.isoformat(),
            "reason": self.reason,
            "lag": self.lag,
        }


@dataclass(frozen=True)
class ContaminationReport:
    """What a look-ahead sweep found across a set of observations."""

    checked: int
    contaminated: int
    findings: list[LookAheadFinding] = field(default_factory=list)
    #: True when no input post-dated any decision.
    clean: bool = True

    @property
    def rate(self) -> float:
        """Fraction of observations contaminated. 0.0 for an empty set."""
        if self.checked == 0:
            return 0.0
        return self.contaminated / self.checked

    def as_dict(self) -> dict[str, object]:
        return {
            "checked": self.checked,
            "contaminated": self.contaminated,
            "rate": self.rate,
            "clean": self.clean,
            "findings": [f.as_dict() for f in self.findings],
        }

    def summary(self) -> str:
        if self.clean:
            return f"no look-ahead in {self.checked} observation(s)"
        return (
            f"{self.contaminated} of {self.checked} observation(s) used data that was not "
            f"knowable at decision time ({self.rate:.1%}); first: {self.findings[0].reason}"
            if self.findings
            else "contaminated"
        )


def detect_look_ahead(observations: Sequence[ObservationTiming]) -> ContaminationReport:
    """Find every decision whose inputs were not knowable at decision time.

    Returns a report naming each offending observation, capped for readability
    while the counts stay exact. A summary that said "some were contaminated"
    without saying which would not be actionable.
    """
    findings: list[LookAheadFinding] = []
    contaminated = 0
    for observation in observations:
        if observation.feature_available_at > observation.decision_time:
            contaminated += 1
            findings.append(
                LookAheadFinding(
                    observation_id=observation.observation_id,
                    decision_time=observation.decision_time,
                    feature_available_at=observation.feature_available_at,
                    reason=(
                        f"feature became knowable "
                        f"{(observation.feature_available_at - observation.decision_time).total_seconds():.0f}s "
                        f"after the decision"
                    ),
                    lag=(observation.feature_available_at - observation.decision_time).total_seconds(),
                )
            )
        elif (
            observation.label_available_at is not None
            and observation.label_available_at > observation.decision_time
        ):
            contaminated += 1
            findings.append(
                LookAheadFinding(
                    observation_id=observation.observation_id,
                    decision_time=observation.decision_time,
                    feature_available_at=observation.feature_available_at,
                    reason=(
                        "label was not fully formed at decision time, so the training "
                        "window overlaps the test window"
                    ),
                    lag=(
                        observation.label_available_at - observation.decision_time
                    ).total_seconds(),
                )
            )
    return ContaminationReport(
        checked=len(observations),
        contaminated=contaminated,
        findings=findings[:20],
        clean=contaminated == 0,
    )


@dataclass(frozen=True)
class PanelTiming:
    """The knowable cross-section at one decision time.

    In a correctly assembled panel every instrument has a feature available by
    the decision time. When some do not and others do, the panel's composition
    at that instant is itself the signal, and a strategy that only trades
    whichever names happened to be ready is reading the future through the
    universe.
    """

    decision_time: datetime
    ready: tuple[str, ...]
    not_ready: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return not self.not_ready

    @property
    def coverage(self) -> float:
        total = len(self.ready) + len(self.not_ready)
        if total == 0:
            return 0.0
        return len(self.ready) / total


def detect_panel_leakage(panels: Sequence[PanelTiming]) -> ContaminationReport:
    """Find decision times whose cross-section was assembled unevenly.

    Separate from :func:`detect_look_ahead` because a per-row check cannot see
    it: every individual row may be correctly timed while the *set* of rows
    available at the decision encodes future information.
    """
    findings: list[LookAheadFinding] = []
    for panel in panels:
        if panel.is_complete:
            continue
        findings.append(
            LookAheadFinding(
                observation_id=f"panel@{panel.decision_time.isoformat()}",
                decision_time=panel.decision_time,
                feature_available_at=panel.decision_time,
                reason=(
                    f"{len(panel.not_ready)} of "
                    f"{len(panel.ready) + len(panel.not_ready)} instruments were not "
                    f"knowable at this decision time; the panel composition leaks "
                    f"the future"
                ),
            )
        )
    return ContaminationReport(
        checked=len(panels),
        contaminated=len(findings),
        findings=findings[:20],
        clean=not findings,
    )


# ══════════════════════════════════════════════════════════════════════════
# Survivorship
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SurvivorshipFinding:
    """An instrument that disappeared during the window and was not tested."""

    instrument_id: str
    action_type: str
    effective_at: datetime
    successor: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "action_type": self.action_type,
            "effective_at": self.effective_at.isoformat(),
            "successor": self.successor,
        }


@dataclass(frozen=True)
class SurvivorshipReport:
    """Which instruments left the world during the test window."""

    tested_universe_size: int
    disappeared_in_window: int
    excluded_from_universe: int
    findings: list[SurvivorshipFinding] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True when no instrument that disappeared was left out.

        Any excluded delisting is evidence of bias, however small the universe:
        one omitted bankruptcy can invert a backtest's conclusion.
        """
        return self.excluded_from_universe == 0

    @property
    def clean(self) -> bool:
        """Alias matching :class:`ContaminationReport`.

        Both report types are consumed by the same code, so they share the
        attribute name. A caller that had to branch on the concrete type to ask
        "was this clean?" would be a place one of the two gets the answer wrong.
        """
        return self.is_clean

    @property
    def exclusion_rate(self) -> float:
        """Fraction of disappearing instruments that were never tested."""
        if self.disappeared_in_window == 0:
            return 0.0
        return self.excluded_from_universe / self.disappeared_in_window

    def as_dict(self) -> dict[str, object]:
        return {
            "tested_universe_size": self.tested_universe_size,
            "disappeared_in_window": self.disappeared_in_window,
            "excluded_from_universe": self.excluded_from_universe,
            "exclusion_rate": self.exclusion_rate,
            "clean": self.is_clean,
            "findings": [f.as_dict() for f in self.findings],
        }

    def summary(self) -> str:
        if self.disappeared_in_window == 0:
            return (
                f"no instrument delisted or was renamed during the window; "
                f"universe of {self.tested_universe_size} carries no survivorship signal"
            )
        if self.is_clean:
            return (
                f"all {self.disappeared_in_window} instrument(s) that left during the window "
                "were present in the tested universe"
            )
        return (
            f"{self.excluded_from_universe} of {self.disappeared_in_window} instrument(s) "
            f"that delisted or were renamed during the window were absent from the tested "
            f"universe ({self.exclusion_rate:.1%}); the result was produced on survivors"
        )


#: Actions that remove an instrument from trade under its own identity. A
#: symbol change does not remove it, but a naive backtest that joins on the
#: ticker will silently drop the pre-rename history, so it is counted too.
_TERMINAL = frozenset({ActionType.DELISTING, ActionType.MERGER, ActionType.SPINOFF})
_IDENTITY_BREAKING = frozenset({ActionType.SYMBOL_CHANGE})


def detect_survivorship(
    tested_universe: Iterable[str],
    corporate_actions: Sequence[CorporateAction],
    *,
    window_start: datetime,
    window_end: datetime,
) -> SurvivorshipReport:
    """Compare the tested universe against what actually left during a window.

    The detectable signature of survivorship bias is an *absence*: instruments
    that stopped trading while the backtest ran, and do not appear in the
    universe that produced the result. That is exactly the class of evidence a
    point-in-time query over current beliefs cannot produce, which is why this
    takes the full corporate-action history rather than a per-instrument lookup.

    A symbol change is counted as excluded when the tested universe contains the
    instrument but not its post-rename ticker, because a backtest keyed on the
    new ticker has silently discarded the history under the old one.
    """
    universe = set(tested_universe)
    in_window = [
        action
        for action in corporate_actions
        if window_start <= action.effective_at <= window_end
        and action.action_type in (_TERMINAL | _IDENTITY_BREAKING)
    ]

    findings: list[SurvivorshipFinding] = []
    for action in in_window:
        present = action.instrument_id in universe
        if action.action_type is ActionType.SYMBOL_CHANGE:
            # Present under the old identity but joined on the new ticker means
            # the pre-rename series was dropped.
            renamed_away = (
                present
                and action.new_ticker is not None
                and action.new_ticker not in universe
            )
            if not present or not renamed_away:
                continue
            findings.append(
                SurvivorshipFinding(
                    instrument_id=action.instrument_id,
                    action_type=str(action.action_type),
                    effective_at=action.effective_at,
                    successor=action.new_ticker,
                )
            )
            continue
        if present:
            continue
        findings.append(
            SurvivorshipFinding(
                instrument_id=action.instrument_id,
                action_type=str(action.action_type),
                effective_at=action.effective_at,
                successor=action.successor_instrument_id,
            )
        )

    return SurvivorshipReport(
        tested_universe_size=len(universe),
        disappeared_in_window=len(in_window),
        excluded_from_universe=len(findings),
        findings=findings[:20],
    )
