"""Paper Trading Simulation Engine for executing strategy specifications in AIOS.

ADR-002/D5: the engine owns cash and open-position state. Fills debit cash,
settlement credits proceeds, and insufficient funds are rejected rather than
silently executed. All fills are tagged ``is_simulated=True`` per Constitution
Law 1.3.
"""

import logging
from dataclasses import dataclass

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import (
    DataProvenance,
    PortfolioAllocationPlan,
    StrategySpecification,
    TradeExecutionReceipt,
)

logger = logging.getLogger(__name__)

_DEFAULT_TAKER_FEE_PCT = 0.1


@dataclass
class OpenPaperPosition:
    """An open simulated position awaiting settlement, with its bracket levels."""

    receipt: TradeExecutionReceipt
    action: str
    stop_loss_price: float
    take_profit_price: float
    allocated_capital: float


class PaperEngine:
    """Simulated paper trading execution engine with honest balance accounting."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        initial_balance: float = 100000.0,
        slippage_pct: float = 0.05,
        taker_fee_pct: float = _DEFAULT_TAKER_FEE_PCT,
        max_open_positions_per_symbol: int = 1,
    ) -> None:
        """Initialize PaperEngine.

        Args:
            event_bus: Event bus instance for inter-community messaging.
            initial_balance: Initial portfolio capital balance (must be positive).
            slippage_pct: Execution slippage percentage model.
            taker_fee_pct: Simulated exchange fee percentage applied to notional.
            max_open_positions_per_symbol: Portfolio control limiting stacked
                exposure per symbol (Doc 11 control set; deterministic).
        """
        if initial_balance <= 0:
            raise ValueError("initial_balance must be positive")
        if max_open_positions_per_symbol < 1:
            raise ValueError("max_open_positions_per_symbol must be >= 1")
        self.event_bus = event_bus
        self.initial_balance = initial_balance
        self.cash_balance = initial_balance
        self.slippage_pct = slippage_pct
        self.taker_fee_pct = taker_fee_pct
        self.max_open_positions_per_symbol = max_open_positions_per_symbol
        self.open_positions: dict[str, OpenPaperPosition] = {}

    async def execute_paper_trade(
        self, strategy: StrategySpecification
    ) -> TradeExecutionReceipt | None:
        """Simulate trade execution for a strategy specification.

        Debits allocated capital plus fees from the cash balance. Rejects (returns
        None without publishing) when funds are insufficient.

        Args:
            strategy: StrategySpecification instance to execute.

        Returns:
            TradeExecutionReceipt with fill details, or None when rejected.
        """
        allocated_capital = round(self.cash_balance * (strategy.position_size_pct / 100.0), 2)
        fill_price = strategy.entry_price * (
            1.0 + self.slippage_pct / 100.0
            if strategy.action == "BUY"
            else 1.0 - self.slippage_pct / 100.0
        )
        fees = round(allocated_capital * self.taker_fee_pct / 100.0, 2)
        total_debit = allocated_capital

        open_for_symbol = sum(
            1 for p in self.open_positions.values() if p.receipt.symbol == strategy.symbol
        )
        if open_for_symbol >= self.max_open_positions_per_symbol:
            logger.warning(
                "Rejected paper order for %s: position limit reached (%d)",
                strategy.symbol,
                self.max_open_positions_per_symbol,
            )
            return None

        if allocated_capital <= 0 or total_debit + fees > self.cash_balance:
            logger.warning(
                "Rejected paper order for %s: insufficient funds (cash=%.2f required=%.2f)",
                strategy.symbol,
                self.cash_balance,
                total_debit + fees,
            )
            return None

        filled_quantity = round(allocated_capital / fill_price, 6)
        slippage = abs(fill_price - strategy.entry_price)
        self.cash_balance = round(self.cash_balance - allocated_capital, 2)

        receipt = TradeExecutionReceipt(
            strategy_id=strategy.strategy_id,
            symbol=strategy.symbol,
            fill_price=round(fill_price, 4),
            filled_quantity=filled_quantity,
            slippage=round(slippage, 4),
            fees=fees,
            venue="paper",
            is_simulated=True,
            provenance=DataProvenance(
                source_id="paper_engine_v1",
                source_type="SIM",
                quality_state="LIVE",
            ),
        )
        self.open_positions[receipt.execution_id] = OpenPaperPosition(
            receipt=receipt,
            action=strategy.action,
            stop_loss_price=strategy.stop_loss_price,
            take_profit_price=strategy.take_profit_price,
            allocated_capital=allocated_capital,
        )

        await self.event_bus.publish(EventTopic.TRADE_EXECUTED, receipt)
        logger.info(
            "Executed paper %s %s for strategy %s at fill_price=%.4f; cash=%.2f",
            strategy.action,
            receipt.symbol,
            receipt.strategy_id,
            receipt.fill_price,
            self.cash_balance,
        )
        return receipt

    def settle_position(self, execution_id: str, exit_price: float) -> float | None:
        """Settle an open paper position at a market-supplied exit price.

        Credits the allocated capital plus realized PnL back to cash, preserving
        exact conservation: cash_delta per trade == realized PnL (cent-rounded).

        Args:
            execution_id: Execution identifier of the open position.
            exit_price: Actual exit price from market data (never invented here).

        Returns:
            Realized PnL, or None when the execution id is unknown or already settled.
        """
        if exit_price <= 0:
            raise ValueError("Exit price must be positive")
        position = self.open_positions.pop(execution_id, None)
        if position is None:
            return None

        r = position.receipt
        if position.action == "SELL":
            pnl = (r.fill_price - exit_price) * r.filled_quantity - r.fees
        else:
            pnl = (exit_price - r.fill_price) * r.filled_quantity - r.fees

        realized = round(pnl, 2)
        proceeds = round(position.allocated_capital + realized, 2)
        self.cash_balance = round(self.cash_balance + proceeds, 2)
        logger.info(
            "Settled paper position %s at %.4f; realized_pnl=%.2f; cash=%.2f",
            execution_id,
            exit_price,
            realized,
            self.cash_balance,
        )
        return realized

    def on_market_price(self, symbol: str, price: float) -> list[float]:
        """Settle every open position for a symbol at an actual market price.

        Composition roots call this alongside ObservationAgent.on_market_price_update
        so observation and cash accounting share one market-driven exit source.

        Args:
            symbol: Symbol whose market price arrived.
            price: Actual observed market price (never invented).

        Returns:
            Realized PnL per settled position, in registration order.
        """
        if price <= 0:
            raise ValueError("Market price must be positive")
        ids = [eid for eid, p in self.open_positions.items() if p.receipt.symbol == symbol]
        return [pnl for eid in ids if (pnl := self.settle_position(eid, price)) is not None]

    async def on_plan(self, plan: PortfolioAllocationPlan) -> None:
        """Execute an approved PortfolioAllocationPlan (Doc 15 production path).

        The plan carries the final position size decided by the C9 governor;
        the embedded strategy is re-sized before execution.
        """
        if not plan.approved:
            logger.warning("PaperEngine received unapproved plan %s; ignored", plan.plan_id)
            return
        strategy = plan.strategy.model_copy(
            update={"position_size_pct": plan.final_position_size_pct}
        )
        await self.execute_paper_trade(strategy)

    async def on_strategy_generated(self, strategy: StrategySpecification) -> None:
        """Event handler callback triggered when a strategy specification is generated."""
        logger.info(
            "PaperEngine received STRATEGY_GENERATED event for strategy %s",
            strategy.strategy_id,
        )
        await self.execute_paper_trade(strategy)
