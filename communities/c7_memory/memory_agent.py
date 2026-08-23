"""Community 7: Memory Agent for institutional knowledge persistence and performance tracking."""

import logging

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import (
    ObservationReport,
    PerformanceSummary,
    TradeExecutionReceipt,
)

logger = logging.getLogger(__name__)


class MemoryAgent:
    """Memory Agent for storing receipts, observation reports, and performance analytics."""

    def __init__(self, event_bus: BaseEventBus) -> None:
        """Initialize MemoryAgent with event bus instance.

        Args:
            event_bus: Event bus instance for inter-community messaging.
        """
        self.event_bus = event_bus
        self.trade_receipts: list[TradeExecutionReceipt] = []
        self.observation_reports: list[ObservationReport] = []

    def store_trade_receipt(self, receipt: TradeExecutionReceipt) -> None:
        """Store trade execution receipt in institutional memory.

        Args:
            receipt: TradeExecutionReceipt instance.
        """
        self.trade_receipts.append(receipt)
        logger.info("Stored TradeExecutionReceipt %s in memory", receipt.execution_id)

    async def store_observation_report(self, report: ObservationReport) -> None:
        """Store post-trade observation report in institutional memory and publish MEMORY_STORED event.

        Args:
            report: ObservationReport instance.
        """
        self.observation_reports.append(report)
        logger.info(
            "Stored ObservationReport %s in memory. Total observations: %d",
            report.observation_id,
            len(self.observation_reports),
        )
        await self.event_bus.publish(EventTopic.MEMORY_STORED, report)

    def get_performance_summary(self) -> PerformanceSummary:
        """Compute institutional performance summary analytics.

        Returns:
            Typed PerformanceSummary contract (ADR-002): consumers depend on this
            schema, not on this class (removes cross-community import need).
        """
        total_trades = len(self.observation_reports)
        cumulative_pnl = sum(r.actual_pnl for r in self.observation_reports)
        winning_trades = sum(1 for r in self.observation_reports if r.actual_pnl > 0)
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

        return PerformanceSummary(
            total_trades=total_trades,
            cumulative_pnl=round(cumulative_pnl, 2),
            winning_trades=winning_trades,
            win_rate=round(win_rate, 2),
        )

    async def on_trade_executed(self, receipt: TradeExecutionReceipt) -> None:
        """Event handler callback triggered when a trade is executed."""
        self.store_trade_receipt(receipt)

    async def on_observation_completed(self, report: ObservationReport) -> None:
        """Event handler callback triggered when an observation report is published."""
        await self.store_observation_report(report)
