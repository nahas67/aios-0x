"""Paper Trading Simulation Engine for executing strategy specifications in AIOS."""

import logging
from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import StrategySpecification, TradeExecutionReceipt

logger = logging.getLogger(__name__)


class PaperEngine:
    """Simulated paper trading execution engine."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        initial_balance: float = 100000.0,
        slippage_pct: float = 0.05,
    ) -> None:
        """Initialize PaperEngine.

        Args:
            event_bus: Event bus instance for inter-community messaging.
            initial_balance: Initial portfolio capital balance.
            slippage_pct: Execution slippage percentage model.
        """
        self.event_bus = event_bus
        self.balance = initial_balance
        self.slippage_pct = slippage_pct

    async def execute_paper_trade(
        self, strategy: StrategySpecification
    ) -> TradeExecutionReceipt:
        """Simulate trade execution for a strategy specification.

        Args:
            strategy: StrategySpecification instance to execute.

        Returns:
            TradeExecutionReceipt instance with fill details.
        """
        if strategy.action == "BUY":
            fill_price = strategy.entry_price * (1.0 + self.slippage_pct / 100.0)
        else:
            fill_price = strategy.entry_price * (1.0 - self.slippage_pct / 100.0)

        allocated_capital = self.balance * (strategy.position_size_pct / 100.0)
        filled_quantity = round(allocated_capital / fill_price, 6)
        slippage = abs(fill_price - strategy.entry_price)
        fees = round(allocated_capital * 0.001, 2)  # 0.1% simulated exchange fee

        receipt = TradeExecutionReceipt(
            strategy_id=strategy.strategy_id,
            symbol=strategy.symbol,
            fill_price=round(fill_price, 4),
            filled_quantity=filled_quantity,
            slippage=round(slippage, 4),
            fees=fees,
        )

        await self.event_bus.publish(EventTopic.TRADE_EXECUTED, receipt)
        logger.info(
            "Executed paper trade %s for strategy %s on %s at fill_price=%.4f",
            receipt.execution_id,
            receipt.strategy_id,
            receipt.symbol,
            receipt.fill_price,
        )
        return receipt

    async def on_strategy_generated(self, strategy: StrategySpecification) -> None:
        """Event handler callback triggered when a strategy specification is generated.

        Args:
            strategy: Received StrategySpecification event.
        """
        logger.info(
            "PaperEngine received STRATEGY_GENERATED event for strategy %s",
            strategy.strategy_id,
        )
        await self.execute_paper_trade(strategy)
