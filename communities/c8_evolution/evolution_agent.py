"""Community 8: Evolution Agent for continuous self-evaluation and meta-adaptation."""

import logging
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from communities.c7_memory.memory_agent import MemoryAgent
from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import generate_utc_now, generate_uuid

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
    performance_summary: dict[str, Any] = Field(
        ..., description="Snapshot of performance analytics at evaluation time"
    )


class EvolutionAgent:
    """Evolution Agent that analyzes memory insights and triggers self-adaptation signals."""

    def __init__(self, event_bus: BaseEventBus, memory_agent: MemoryAgent) -> None:
        """Initialize EvolutionAgent with event bus and memory agent reference.

        Args:
            event_bus: Event bus instance for inter-community messaging.
            memory_agent: Reference to MemoryAgent for accessing performance analytics.
        """
        self.event_bus = event_bus
        self.memory_agent = memory_agent

    async def evaluate_and_evolve(self) -> dict[str, Any]:
        """Query performance summary and generate system adaptation recommendations.

        Returns:
            Dictionary containing adjustment_needed, recommendations, and performance_summary.
        """
        summary = self.memory_agent.get_performance_summary()
        total_trades = summary.get("total_trades", 0)
        win_rate = summary.get("win_rate", 0.0)

        recommendations = []
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

        return {
            "adjustment_needed": adjustment_needed,
            "recommendations": recommendations,
            "performance_summary": summary,
        }

    async def on_memory_stored(self, payload: BaseModel) -> None:
        """Event handler callback triggered when new memory is stored.

        Args:
            payload: Memory stored event payload.
        """
        logger.info("EvolutionAgent received MEMORY_STORED event. Triggering self-evaluation.")
        await self.evaluate_and_evolve()
