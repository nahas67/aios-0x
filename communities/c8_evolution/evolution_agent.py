"""Community 8: Evolution Agent for continuous self-evaluation and meta-adaptation."""

import logging
from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, Field

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import PerformanceSummary, generate_utc_now, generate_uuid

logger = logging.getLogger(__name__)


class EvolutionSignal(BaseModel):
    """Payload representing an evolution and system adaptation signal."""

    signal_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this evolution signal",
    )
    timestamp: datetime = Field(
        default_factory=generate_utc_now,
        description="UTC timestamp of the evolution trigger",
    )
    adjustment_needed: bool = Field(
        ..., description="Indicates if system parameter adjustment is recommended"
    )
    recommendations: list[str] = Field(
        ..., description="List of meta-learning system recommendations"
    )
    performance_summary: PerformanceSummary = Field(
        ..., description="Typed performance snapshot at evaluation time"
    )


class EvolutionAgent:
    """Evolution Agent that analyzes performance summaries and triggers self-adaptation signals.

    ADR-002/D2: this agent depends on the PerformanceSummary contract via an injected
    provider callable - never on another community's implementation class.
    """

    def __init__(
        self,
        event_bus: BaseEventBus,
        performance_provider: Callable[[], PerformanceSummary],
    ) -> None:
        """Initialize EvolutionAgent.

        Args:
            event_bus: Event bus instance for inter-community messaging.
            performance_provider: Zero-argument callable returning a typed
                PerformanceSummary (typically backed by C7 memory).
        """
        self.event_bus = event_bus
        self._performance_provider = performance_provider

    async def evaluate_and_evolve(self) -> EvolutionSignal:
        """Query the performance provider and generate a system adaptation signal.

        Returns:
            The published EvolutionSignal.
        """
        summary = self._performance_provider()
        total_trades = summary.total_trades
        win_rate = summary.win_rate

        recommendations: list[str] = []
        adjustment_needed = False

        if total_trades >= 3 and win_rate < 50.0:
            adjustment_needed = True
            recommendations.append("Tighten verification confidence threshold to 80%")
            recommendations.append("Reduce default max_position_size_pct cap to 3.0%")
        else:
            recommendations.append(
                "System performing within expected parameters. Maintain active configuration."
            )

        signal = EvolutionSignal(
            adjustment_needed=adjustment_needed,
            recommendations=recommendations,
            performance_summary=summary,
        )

        await self.event_bus.publish(EventTopic.EVOLUTION_TRIGGERED, signal)
        logger.info(
            "Published EvolutionSignal %s (adjustment_needed=%s) to %s",
            signal.signal_id,
            adjustment_needed,
            EventTopic.EVOLUTION_TRIGGERED,
        )
        return signal

    async def on_memory_stored(self, payload: BaseModel) -> None:
        """Event handler callback triggered when new memory is stored."""
        logger.info("EvolutionAgent received MEMORY_STORED event. Triggering self-evaluation.")
        await self.evaluate_and_evolve()
