"""Community 6: Observation Agent for post-trade analysis and lesson extraction.

ADR-002/D1 (honesty invariant): exit prices must originate from market data
supplied by the caller. This agent NEVER fabricates an exit price. Trades stay
open until an actual market price arrives via ``on_market_price_update`` or an
explicit ``observe_trade_outcome`` call.
"""

import logging

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import ObservationReport, TradeExecutionReceipt

logger = logging.getLogger(__name__)


class ObservationAgent:
    """Observation Agent that tracks executed trades and measures realized PnL."""

    def __init__(self, event_bus: BaseEventBus) -> None:
        """Initialize ObservationAgent with event bus instance.

        Args:
            event_bus: Event bus instance for inter-community messaging.
        """
        self.event_bus = event_bus
        self._open_positions: dict[str, TradeExecutionReceipt] = {}

    @property
    def open_position_count(self) -> int:
        """Number of executed fills awaiting a market-driven exit."""
        return len(self._open_positions)

    def observe_trade_outcome_sync(
        self,
        receipt: TradeExecutionReceipt,
        exit_price: float,
        side: str = "BUY",
    ) -> float:
        """Compute realized PnL for a receipt at an externally-supplied exit price.

        Args:
            receipt: TradeExecutionReceipt from Community 5 / PaperEngine.
            exit_price: Realized trade exit price from market data (never invented).
            side: Position side ("BUY" long / "SELL" short) governing profit direction.

        Returns:
            Realized PnL in quote currency.
        """
        if exit_price <= 0:
            raise ValueError("Exit price must be positive")
        if side == "SELL":
            return round(
                (receipt.fill_price - exit_price) * receipt.filled_quantity - receipt.fees,
                2,
            )
        return round(
            (exit_price - receipt.fill_price) * receipt.filled_quantity - receipt.fees,
            2,
        )

    async def observe_trade_outcome(
        self,
        receipt: TradeExecutionReceipt,
        exit_price: float,
        exit_reason: str | None = None,
        side: str = "BUY",
    ) -> ObservationReport:
        """Calculate realized PnL, deviation score, and generate observation report.

        Args:
            receipt: TradeExecutionReceipt from Community 5 / PaperEngine.
            exit_price: Realized trade exit price sourced from market data.
            exit_reason: Market-driven close reason (TARGET_HIT/STOP_HIT/HORIZON_END).
            side: Position side ("BUY"/"SELL") for correct PnL direction.

        Returns:
            ObservationReport instance.
        """
        actual_pnl = self.observe_trade_outcome_sync(receipt, exit_price, side=side)

        price_diff_pct = abs(exit_price - receipt.fill_price) / receipt.fill_price
        slippage_pct = receipt.slippage / receipt.fill_price
        deviation = price_diff_pct + slippage_pct

        lessons_learned = [
            (
                f"Trade on {receipt.symbol} closed profitably (+${actual_pnl:.2f})."
                if actual_pnl > 0
                else f"Trade on {receipt.symbol} resulted in net loss (-${abs(actual_pnl):.2f})."
            ),
            (
                f"Execution slippage was {receipt.slippage:.4f} with fees of "
                f"${receipt.fees:.2f}. Exit price was supplied by market data."
            ),
        ]

        report = ObservationReport(
            execution_id=receipt.execution_id,
            actual_pnl=actual_pnl,
            predicted_vs_actual_deviation=round(deviation, 4),
            lessons_learned=lessons_learned,
            symbol=receipt.symbol,
            strategy_id=receipt.strategy_id,
            exit_reason=exit_reason,  # type: ignore[arg-type]
            direction_correct=actual_pnl > 0,
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
        """Register an executed fill as an open position awaiting a real exit price."""
        self._open_positions[receipt.execution_id] = receipt
        logger.info(
            "ObservationAgent registered open position for execution %s (%s); "
            "awaiting market-driven exit price",
            receipt.execution_id,
            receipt.symbol,
        )

    async def on_market_price_update(self, symbol: str, price: float) -> list[ObservationReport]:
        """Close all open positions for a symbol at an actual market price.

        Args:
            symbol: Symbol whose latest market price is available.
            price: Actual observed market price for the symbol.

        Returns:
            Observation reports published for each closed position (possibly empty).
        """
        if price <= 0:
            raise ValueError("Market price must be positive")

        closed_ids = [
            execution_id for execution_id, r in self._open_positions.items() if r.symbol == symbol
        ]
        reports: list[ObservationReport] = []
        for execution_id in closed_ids:
            receipt = self._open_positions.pop(execution_id)
            report = await self.observe_trade_outcome(receipt, price)
            reports.append(report)
        return reports

    async def on_observation_completed(self, report: ObservationReport) -> None:
        """Hook for downstream consumers; observations are published by this agent itself."""
        return None

    def mark_all_closed_external(self) -> None:
        """Test/ops helper: drop tracked open positions without inventing exits."""
        self._open_positions.clear()
