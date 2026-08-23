"""Community 10: expectation + scenario engines.

ExpectationEngine (Directive 12): computes expected-vs-actual surprise for
resolved scheduled events. Interpretation is ALWAYS relative to expectations
("better than feared" can be bearish if priced in) - never naive good/bad news.

ScenarioEngine (Directive 29): publishes pre-event probability cards with
invalidation conditions. Probabilities are deterministic v0 priors; LLM-driven
calibration arrives with later phases.
"""

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import (
    ExpectationSnapshot,
    ScenarioCard,
    ScenarioSet,
    ScheduledEvent,
)

_AS_EXPECTED_TOLERANCE_PCT = 0.25


class ExpectationEngine:
    """Converts resolved events into expectation snapshots."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        as_expected_tolerance_pct: float = _AS_EXPECTED_TOLERANCE_PCT,
    ) -> None:
        self.event_bus = event_bus
        self.tolerance_pct = as_expected_tolerance_pct

    def process(self, event: ScheduledEvent) -> ExpectationSnapshot | None:
        """Build a snapshot when the event carries an actual; else None."""
        if event.actual is None:
            return None
        consensus = event.consensus
        surprise = event.actual - (consensus if consensus is not None else 0.0)
        denom = abs(consensus) if consensus not in (None, 0.0) else max(abs(event.actual), 1e-9)
        surprise_pct = round(surprise / denom * 100.0, 4)

        # Directive 12: direction convention matters. Hot inflation vs hot GDP
        # are opposite surprises relative to expectations.
        effective_surprise = surprise if event.higher_is_better else -surprise

        if abs(surprise_pct) <= self.tolerance_pct:
            interpretation: str = "AS_EXPECTED"
        elif effective_surprise > 0:
            interpretation = "BETTER_THAN_EXPECTED"
        else:
            interpretation = "WORSE_THAN_EXPECTED"

        snapshot = ExpectationSnapshot(
            event_id=event.event_id,
            title=event.title,
            consensus=consensus,
            actual=event.actual,
            surprise=round(surprise, 6),
            surprise_pct=surprise_pct,
            interpretation=interpretation,  # type: ignore[arg-type]
            affected_symbols=event.affected_symbols,
            is_simulated=event.is_simulated,
        )
        return snapshot

    async def on_event(self, event: ScheduledEvent) -> ExpectationSnapshot | None:
        snapshot = self.process(event)
        if snapshot is not None:
            await self.event_bus.publish(EventTopic.EXPECTATION_UPDATED, snapshot)
        return snapshot


class ScenarioEngine:
    """Publishes deterministic pre-event scenario cards."""

    _DEFAULT_CARDS: list[ScenarioCard] = [
        ScenarioCard(
            name="BASE",
            probability=0.45,
            expected_impact="Print near consensus; muted reaction; positioning unchanged.",
            horizon_timeframe="1d",
            invalidation_condition="Actual deviates >0.5% from consensus.",
        ),
        ScenarioCard(
            name="BULL",
            probability=0.20,
            expected_impact="Softer-than-feared print supports risk assets.",
            horizon_timeframe="1d",
            invalidation_condition="Reaction fails to hold initial direction within 3 bars.",
        ),
        ScenarioCard(
            name="BEAR",
            probability=0.20,
            expected_impact="Hotter-than-feared print pressures risk assets.",
            horizon_timeframe="1d",
            invalidation_condition="Reaction fully retraces within 3 bars.",
        ),
        ScenarioCard(
            name="UNEXPECTED",
            probability=0.10,
            expected_impact="Mixed print; cross-asset divergence likely.",
            horizon_timeframe="2d",
            invalidation_condition="Correlated move across affected symbols.",
        ),
        ScenarioCard(
            name="EXTREME",
            probability=0.05,
            expected_impact="Far-outside print; volatility spike and gap risk.",
            horizon_timeframe="2d",
            invalidation_condition="Volatility collapses back within one bar.",
        ),
    ]

    def __init__(self, event_bus: BaseEventBus) -> None:
        self.event_bus = event_bus

    async def on_event(self, event: ScheduledEvent) -> ScenarioSet:
        scenario_set = ScenarioSet(
            event_id=event.event_id,
            title=event.title,
            cards=list(self._DEFAULT_CARDS),
            is_simulated=event.is_simulated,
        )
        await self.event_bus.publish(EventTopic.SCENARIOS_PUBLISHED, scenario_set)
        return scenario_set
