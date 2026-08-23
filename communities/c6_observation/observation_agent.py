"""Community 6: Observation Agent for post-trade analysis and lesson extraction."""

import logging
from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import ObservationReport, TradeExecutionReceipt

logger = logging.getLogger(__name__)


class ObservationAgent:
    """Observation Agent that tracks executed trades, measures PnL, and extracts insights."""

    def __init__(self, event_bus: BaseEventBus) -> None:
        """Initialize ObservationAgent with event bus instance.

        Args:
            event_bus: Event bus instance for inter-community messaging.
        """
        self.event_bus = event_bus

    async def observe_trade_outcome(
        self, receipt: TradeExecutionReceipt, exit_price: float
    ) -> ObservationReport:
        """Calculate realized PnL, deviation score, and generate observation report.

        Args:
            receipt: TradeExecutionReceipt from Community 5 / PaperEngine.
            exit_price: Realized trade exit price.

        Returns:
            ObservationReport instance.
        """
        actual_pnl = (
            (exit_price - receipt.fill_price) * receipt.filled_quantity
        ) - receipt.fees

        price_diff_pct = abs(exit_price - receipt.fill_price) / receipt.fill_price
        slippage_pct = receipt.slippage / receipt.fill_price
        deviation = price_diff_pct + slippage_pct

        lessons_learned = []
        if actual_pnl > 0:
            lessons_learned.append(
                f"Trade on {receipt.symbol} closed profitably (+${actual_pnl:.2f})."
            )
        else:
            lessons_learned.append(
                f"Trade on {receipt.symbol} resulted in net loss (-${abs(actual_pnl):.2f})."
            )

        lessons_learned.append(
            f"Execution slippage was {receipt.slippage:.4f} with fees of ${receipt.fees:.2f}."
        )

        report = ObservationReport(
            execution_id=receipt.execution_id,
            actual_pnl=round(actual_pnl, 2),
            predicted_vs_actual_deviation=round(deviation, 4),
            lessons_learned=lessons_learned,
        )

        await self.event_bus.publish(EventTopic.OBSERVATION_COMPLETED, report)
        logger.info(
            "Published ObservationReport %s for execution %s (PnL=%.2f) to %s",
            report.observation_id,
            report.execution_id,
            report.actual_pnl,
            EventTopic.OBSERVATION_COMPLETED,
        )
        return report

    async def on_trade_executed(self, receipt: TradeExecutionReceipt) -> None:
        """Event handler callback triggered when a trade is executed.

        Args:
            receipt: Received TradeExecutionReceipt event.
        """
        logger.info(
            "ObservationAgent received TRADE_EXECUTED event for execution %s",
            receipt.execution_id,
        )
        # Simulate positive exit at 3% profit target for automated closed-loop processing
        simulated_exit_price = receipt.fill_price * 1.03
        await self.observe_trade_outcome(receipt, simulated_exit_price)
