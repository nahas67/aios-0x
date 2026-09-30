"""Community 5: Execution adapters.

- BaseExecutionAdapter: ABC boundary (Doc 16 zero-lock-in rule).
- PaperExecutionAdapter: delegates fills to the PaperEngine (single source of
  cash/fee/slippage truth).
- CcxtExecutionAdapter: HONEST STUB - raises without explicit testnet config
  and credentials. Never silently simulates live trading.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from schemas.contracts import (
    PortfolioAllocationPlan,
    StrategySpecification,
    TradeExecutionReceipt,
)
from simulation.paper_engine import PaperEngine

logger = logging.getLogger(__name__)


class ExecutionUnavailableError(RuntimeError):
    """Raised when an adapter cannot honestly execute right now."""


def _build_exchange(exchange_id: str, options: dict[str, Any]) -> Any:
    """Factory boundary: builds a real ccxt exchange instance (injectable in tests)."""
    try:
        import ccxt  # noqa: PLC0415 - lazy optional dep
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise ExecutionUnavailableError("ccxt is not installed") from exc
    factory = getattr(ccxt, exchange_id, None)
    if factory is None:
        raise ValueError(f"unknown ccxt exchange id: {exchange_id!r}")
    return factory(options)


class BaseExecutionAdapter(ABC):
    venue: str

    @abstractmethod
    async def submit(
        self, plan: PortfolioAllocationPlan, quantity: float
    ) -> TradeExecutionReceipt | None:
        """Execute an approved allocation; returns fill receipt or None."""

    @abstractmethod
    def positions_snapshot(self) -> dict[str, float]:
        """Symbol -> *signed net* quantity, as the venue would report it.

        Reconciliation compares this against the IBOR's signed position, so an
        implementation that returns unsiged magnitudes or lets one symbol
        overwrite another will manufacture divergences that do not exist. Shorts
        are negative; several positions in one symbol are summed.
        """


class PaperExecutionAdapter(BaseExecutionAdapter):
    """Paper venue backed by the PaperEngine."""

    def __init__(self, engine: PaperEngine) -> None:
        self.engine = engine
        self.venue = "paper"

    async def submit(
        self, plan: PortfolioAllocationPlan, quantity: float
    ) -> TradeExecutionReceipt | None:
        strategy: StrategySpecification = plan.strategy.model_copy(
            update={"position_size_pct": plan.final_position_size_pct}
        )
        receipt = await self.engine.execute_paper_trade(strategy)
        if receipt is not None:
            # Quantity derived from sizing; keep authoritative engine value.
            logger.debug("paper fill %s qty=%s", receipt.execution_id, receipt.filled_quantity)
            _ = quantity  # informational only in paper mode
        return receipt

    def positions_snapshot(self) -> dict[str, float]:
        """Signed net position per symbol.

        Two defects lived here and both produced phantom reconciliation findings
        once the durable engine started comparing quantities:

        * ``TradeExecutionReceipt.filled_quantity`` is an unsigned magnitude, so
          keying on it alone reported a short as a positive quantity — the venue
          appeared to hold a long the book had never opened. Direction comes from
          the position's action.
        * A dict comprehension keyed by symbol let the *last* open position for a
          symbol overwrite the others instead of netting them.
        """
        net: dict[str, float] = {}
        for position in self.engine.open_positions.values():
            magnitude = position.receipt.filled_quantity
            signed = -magnitude if position.action == "SELL" else magnitude
            symbol = position.receipt.symbol
            net[symbol] = round(net.get(symbol, 0.0) + signed, 12)
        return net


class CcxtExecutionAdapter(BaseExecutionAdapter):
    """Live/testnet CCXT execution - requires explicit opt-in + credentials.

    Safety rails (Constitution / Directive 74):
    - Requires AIOS_ALLOW_LIVE_EXECUTION=1 AND credentials present.
    - Live routing is constitutionally disabled in the current release,
      regardless of credentials, environment variables, ADMIN approval, or
      ``allow_real_money``. Only the testnet venue can be constructed.
    - Enforces a hard per-order notional cap until the constitution is amended.
    Without the rails it refuses loudly; it NEVER paper-simulates instead.
    """

    MAX_ORDER_NOTIONAL_USD = 100.0  # micro-live cap pending constitution amendment

    def __init__(
        self,
        exchange_id: str,
        api_key_env: str,
        secret_env: str,
        env: dict[str, str] | None = None,
        testnet_default: bool = True,
        allow_real_money: bool = False,
        symbol_map: dict[str, str] | None = None,
        client_builder: Any = None,
    ) -> None:
        self._env = env if env is not None else dict(os.environ)
        self.exchange_id = exchange_id
        self.symbol_map = symbol_map or {}
        allow = self._env.get("AIOS_ALLOW_LIVE_EXECUTION", "") == "1"
        testnet_raw = self._env.get("AIOS_EXCHANGE_TESTNET", "1" if testnet_default else "0")
        self.testnet = testnet_raw == "1"
        self.allow_real_money = allow_real_money
        key = self._env.get(api_key_env, "")
        secret = self._env.get(secret_env, "")

        problems: list[str] = []
        if not allow:
            problems.append("AIOS_ALLOW_LIVE_EXECUTION != 1")
        if not key or not secret:
            problems.append(f"missing credentials ({api_key_env}/{secret_env})")
        if not self.testnet:
            # The ratified constitution currently forbids live routing. Keep
            # this invariant inside the adapter so no caller, environment
            # variable, or boolean argument can turn a test configuration into
            # a real-money venue before a ratified amendment and a separate
            # production composition root exist.
            problems.append(
                "real-money routing is constitutionally disabled (CONSTITUTION §1); "
                "testnet is the only supported CCXT venue"
            )
        if problems:
            raise ExecutionUnavailableError(
                f"CcxtExecutionAdapter unavailable: {'; '.join(problems)}"
            )

        builder = client_builder or _build_exchange
        self.venue = f"ccxt:{exchange_id}:{'testnet' if self.testnet else 'LIVE'}"
        self._client: Any = builder(
            exchange_id, {"apiKey": key, "secret": secret, "enableRateLimit": True}
        )
        if self.testnet and hasattr(self._client, "set_sandbox_mode"):
            self._client.set_sandbox_mode(True)

    def _venue_symbol(self, symbol: str) -> str:
        return self.symbol_map.get(symbol, symbol)

    def _check_cap(self, strategy: StrategySpecification, quantity: float) -> None:
        notional = strategy.entry_price * quantity
        if notional > self.MAX_ORDER_NOTIONAL_USD:
            raise ExecutionUnavailableError(
                f"order notional {notional:.2f} exceeds micro-live cap "
                f"{self.MAX_ORDER_NOTIONAL_USD:.2f}; amend SYSTEM CONSTITUTION to raise"
            )

    async def submit(
        self, plan: PortfolioAllocationPlan, quantity: float
    ) -> TradeExecutionReceipt | None:
        strategy = plan.strategy
        self._check_cap(strategy, quantity)

        side = "buy" if strategy.action == "BUY" else "sell"
        order = await _call(
            self._client.create_order,
            self._venue_symbol(strategy.symbol),
            "market",
            side,
            quantity,
        )
        filled = float(order.get("filled") or order.get("amount") or 0.0)
        avg_price = float(order.get("average") or order.get("price") or strategy.entry_price)
        fee_cost = float((order.get("fee") or {}).get("cost") or 0.0)

        receipt = TradeExecutionReceipt(
            strategy_id=strategy.strategy_id,
            symbol=strategy.symbol,
            fill_price=round(avg_price, 4),
            filled_quantity=round(filled, 6),
            slippage=round(abs(avg_price - strategy.entry_price), 4),
            fees=round(fee_cost, 4),
            venue=self.venue,
            is_simulated=False,
        )
        logger.warning(
            "%s FILL %s %s qty=%.6f @ %.4f (order %s)",
            self.venue.upper(),
            strategy.action,
            strategy.symbol,
            receipt.filled_quantity,
            receipt.fill_price,
            order.get("id"),
        )
        return receipt

    async def cancel_all_orders(self, symbol: str | None = None) -> int:
        target = self._venue_symbol(symbol) if symbol else None
        result = await _call(self._client.cancel_all_orders, target)
        logger.info("cancel_all_orders on %s: %s", self.venue, result)
        return 1

    def positions_snapshot(self) -> dict[str, float]:
        positions = self._client.fetch_positions()
        out: dict[str, float] = {}
        for position in positions or []:
            raw_symbol = str(position.get("symbol", ""))
            aios_symbol = raw_symbol
            for base, mapped in self.symbol_map.items():
                if mapped == raw_symbol:
                    aios_symbol = base
                    break
            qty = float(position.get("contracts") or 0.0)
            if qty != 0.0:
                out[aios_symbol] = out.get(aios_symbol, 0.0) + qty
        return out


async def _call(fn: Any, *args: Any) -> Any:
    import asyncio

    return await asyncio.to_thread(fn, *args)
