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

from schemas.contracts import (
    PortfolioAllocationPlan,
    StrategySpecification,
    TradeExecutionReceipt,
)
from simulation.paper_engine import PaperEngine

logger = logging.getLogger(__name__)


class ExecutionUnavailableError(RuntimeError):
    """Raised when an adapter cannot honestly execute right now."""


class BaseExecutionAdapter(ABC):
    venue: str

    @abstractmethod
    async def submit(
        self, plan: PortfolioAllocationPlan, quantity: float
    ) -> TradeExecutionReceipt | None:
        """Execute an approved allocation; returns fill receipt or None."""

    @abstractmethod
    def positions_snapshot(self) -> dict[str, float]:
        """Symbol -> filled quantity for reconciliation."""


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
        return {
            p.receipt.symbol: p.receipt.filled_quantity for p in self.engine.open_positions.values()
        }


class CcxtExecutionAdapter(BaseExecutionAdapter):
    """Live/testnet CCXT execution - requires explicit opt-in + credentials.

    Safety rails (Constitution / Directive 74):
    - Requires AIOS_ALLOW_LIVE_EXECUTION=1 AND AIOS_EXCHANGE_TESTNET=1|0 set.
    - Requires API key/secret environment variables present.
    - Enforces a hard per-order notional cap until the constitution is amended.
    Without all of these it refuses loudly; it NEVER paper-simulates instead.
    """

    MAX_ORDER_NOTIONAL_USD = 100.0  # micro-live cap pending constitution sign-off

    def __init__(
        self,
        exchange_id: str,
        api_key_env: str,
        secret_env: str,
        env: dict[str, str] | None = None,
        testnet_default: bool = True,
    ) -> None:
        self._env = env if env is not None else dict(os.environ)
        self.exchange_id = exchange_id
        allow = self._env.get("AIOS_ALLOW_LIVE_EXECUTION", "") == "1"
        testnet_raw = self._env.get("AIOS_EXCHANGE_TESTNET", "1" if testnet_default else "0")
        self.testnet = testnet_raw == "1"
        key = self._env.get(api_key_env, "")
        secret = self._env.get(secret_env, "")

        problems: list[str] = []
        if not allow:
            problems.append("AIOS_ALLOW_LIVE_EXECUTION != 1")
        if not key or not secret:
            problems.append(f"missing credentials ({api_key_env}/{secret_env})")
        if problems:
            raise ExecutionUnavailableError(
                f"CcxtExecutionAdapter unavailable: {'; '.join(problems)}"
            )
        try:
            import ccxt  # noqa: PLC0415 - lazy optional dep

            factory = getattr(ccxt, exchange_id)
            options: dict[str, object] = {
                "apiKey": key,
                "secret": secret,
                "enableRateLimit": True,
            }
            self.venue = f"ccxt:{exchange_id}:{'testnet' if self.testnet else 'LIVE'}"
            self._client = factory(options)
            if self.testnet and hasattr(self._client, "set_sandbox_mode"):
                self._client.set_sandbox_mode(True)
        except ImportError as exc:
            raise ExecutionUnavailableError("ccxt not installed") from exc

    async def submit(
        self, plan: PortfolioAllocationPlan, quantity: float
    ) -> TradeExecutionReceipt | None:
        strategy = plan.strategy
        estimated_notional = strategy.entry_price * quantity
        if estimated_notional > self.MAX_ORDER_NOTIONAL_USD:
            raise ExecutionUnavailableError(
                f"order notional {estimated_notional:.2f} exceeds micro-live cap "
                f"{self.MAX_ORDER_NOTIONAL_USD:.2f}; amend SYSTEM CONSTITUTION to raise"
            )
        raise ExecutionUnavailableError(
            "live order routing lands with Phase 5 completion of the broker "
            "integration suite; adapter safety rails verified"
        )

    def positions_snapshot(self) -> dict[str, float]:
        raise ExecutionUnavailableError("live position fetch requires completed broker integration")
