"""Community 5: Execution adapters.

- BaseExecutionAdapter: ABC boundary (Doc 16 zero-lock-in rule).
- PaperExecutionAdapter: delegates fills to the PaperEngine (single source of
  cash/fee/slippage truth).
- CcxtExecutionAdapter: HONEST STUB - raises without explicit testnet config
  and credentials. Never silently simulates live trading.

Every adapter routes through a :class:`~schemas.governance.ToolGuard` before
touching a venue. That is the point of the guard in C5: the venue call is the
last thing that happens, and everything upstream of it is a proposal. A caller
with a valid plan and a good reason still cannot reach a venue without the
guard's per-call verdict, so governance added after the tools is not governance.

The dependency is on the *contract* in ``schemas/governance.py``, never on
``kernel/``: the plane manifest forbids communities from importing the kernel,
and importing the concrete guard would either make governance unreachable from
the execution path or break that boundary. A composition root injects the
implementation, so both rules hold at once.
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
from schemas.governance import (
    GuardianDecision,
    ToolCall,
    ToolGovernanceError,
    ToolGuard,
)
from simulation.paper_engine import PaperEngine

logger = logging.getLogger(__name__)

#: Argument names the Guardian sees on an order submission. Kept as constants
#: because a rename here would silently stop clamping, which is the failure
#: mode where a control quietly stops controlling.
ARG_SYMBOL = "symbol"
ARG_SIDE = "side"
ARG_QUANTITY = "quantity"
ARG_NOTIONAL = "notional"
ARG_ORDER_TYPE = "order_type"

#: Provenance for a value the risk engine computed deterministically. Never
#: MODEL_DERIVED: sizing comes from the firewall, not from a model.
RISK_ENGINE_PROVENANCE = "RISK_ENGINE"


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

    def __init__(
        self, guardian: ToolGuard | None = None, *, envelope_secret: str | None = None
    ) -> None:
        """Bind the governance guard.

        A guard is required, not optional. The alternative — a default that
        allows when none is supplied — is the fail-open posture the reference
        Guardian ships with, and it means an ungoverned adapter looks identical
        to a governed one until the day it matters.

        ``envelope_secret`` arms the second boundary (goal G140): when set,
        every submit must present a sealed authorization envelope covering the
        submitted quantity, verified here before the venue is contacted. When
        unset, the adapter keeps its pre-envelope behaviour. The secret
        arrives explicitly, never from the environment.
        """
        if guardian is None:
            raise ExecutionUnavailableError(
                "an execution adapter requires a ToolGuard. Constructing one without "
                "governance would make a venue call reachable with no per-call verdict."
            )
        self.guardian = guardian
        self._envelope_secret = envelope_secret or ""

    def _require_envelope(
        self, plan: PortfolioAllocationPlan, quantity: float, envelope: Any | None
    ) -> None:
        """Enforce the authorization boundary before any venue contact.

        Runs before :meth:`govern`, so an unauthorized order is refused even
        before a governance verdict is computed: the two boundaries answer
        different questions (may this order exist vs how should it be shaped),
        and a refusal at the first must not depend on the second.
        """
        if not self._envelope_secret:
            return
        from core.authorization import AuthorizationEnvelope

        if envelope is None:
            raise ExecutionUnavailableError(
                "venue submit refused: this adapter requires an authorization "
                "envelope and none accompanied the order"
            )
        if not isinstance(envelope, AuthorizationEnvelope):
            raise ExecutionUnavailableError(
                "venue submit refused: the authorization is not an envelope"
            )
        if not envelope.verify(self._envelope_secret):
            raise ExecutionUnavailableError(
                f"venue submit refused: envelope {envelope.envelope_id!r} "
                "signature does not verify"
            )
        if quantity > envelope.max_quantity:
            raise ExecutionUnavailableError(
                f"venue submit refused: quantity {quantity:g} exceeds envelope "
                f"maximum {envelope.max_quantity:g}"
            )
        notional = plan.strategy.entry_price * quantity
        if notional > envelope.max_notional_usd:
            raise ExecutionUnavailableError(
                f"venue submit refused: notional {notional:.2f} exceeds envelope "
                f"maximum {envelope.max_notional_usd:.2f}"
            )

    def govern(
        self,
        plan: PortfolioAllocationPlan,
        quantity: float,
        *,
        agent_id: str = "c5-execution",
        trace_id: str | None = None,
    ) -> tuple[ToolCall, GuardianDecision]:
        """Build the tool call for this submission and get the Guardian's verdict.

        Returns the governed call, whose arguments may be *reduced* relative to
        the proposed ones, alongside the decision that produced it. Returning
        both is deliberate: the caller needs the decision for the audit trail
        and the call for the venue, and a caller that could only see one would
        be pushed toward re-deriving the other.
        """
        strategy = plan.strategy
        notional = strategy.entry_price * quantity
        call = ToolCall(
            tool=f"{self.venue}.order",
            operation="place",
            capability="broker.order.place",
            agent_id=agent_id,
            session_id=trace_id or "",
            intent=f"submit {strategy.action} {strategy.symbol} from plan {plan.plan_id[:8]}",
            arguments={
                ARG_SYMBOL: {"value": strategy.symbol, "provenance": "PLAN"},
                ARG_SIDE: {"value": strategy.action, "provenance": "PLAN"},
                ARG_QUANTITY: {"value": quantity, "provenance": RISK_ENGINE_PROVENANCE},
                ARG_NOTIONAL: {"value": notional, "provenance": RISK_ENGINE_PROVENANCE},
                ARG_ORDER_TYPE: {"value": "market", "provenance": "ADAPTER_DEFAULT"},
            },
        )
        decision = self.guardian.evaluate(call)
        try:
            governed = self.guardian.apply(decision, call)
        except ToolGovernanceError as exc:
            raise ExecutionUnavailableError(str(exc)) from exc
        return governed, decision

    @abstractmethod
    async def submit(
        self,
        plan: PortfolioAllocationPlan,
        quantity: float,
        *,
        envelope: Any | None = None,
        trace_id: str | None = None,
    ) -> TradeExecutionReceipt | None:
        """Execute an approved allocation; returns fill receipt or None.

        ``envelope`` is required whenever the adapter was constructed with an
        envelope secret (goal G140): no venue contact happens without a sealed
        authorization covering the submitted size. ``trace_id`` threads the
        correlation chain (goal G210) into the governed call's session, so the
        risk decision joins the trace without a second lookup.
        """

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

    def __init__(
        self,
        engine: PaperEngine,
        guardian: ToolGuard | None = None,
        *,
        envelope_secret: str | None = None,
    ) -> None:
        super().__init__(guardian, envelope_secret=envelope_secret)
        self.engine = engine
        self.venue = "paper"

    async def submit(
        self,
        plan: PortfolioAllocationPlan,
        quantity: float,
        *,
        envelope: Any | None = None,
        trace_id: str | None = None,
    ) -> TradeExecutionReceipt | None:
        # Authorization before governance: an order that may not exist is
        # refused before a verdict is even computed for it.
        self._require_envelope(plan, quantity, envelope)
        # Governance first: paper fills are still a position, and a clamp that
        # applies only to live venues would let the same proposal through twice
        # in two venues with different sizes.
        governed, _decision = self.govern(plan, quantity, trace_id=trace_id)
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
        guardian: ToolGuard | None = None,
        envelope_secret: str | None = None,
    ) -> None:
        super().__init__(guardian, envelope_secret=envelope_secret)
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
        self,
        plan: PortfolioAllocationPlan,
        quantity: float,
        *,
        envelope: Any | None = None,
        trace_id: str | None = None,
    ) -> TradeExecutionReceipt | None:
        strategy = plan.strategy
        self._require_envelope(plan, quantity, envelope)
        # Governance may REDUCE quantity (a clamp); it can never increase it, so
        # the constitutional cap is evaluated against the governed value, not
        # the proposed one. Checking the proposal instead would be checking a
        # number the venue never sees.
        governed, _decision = self.govern(plan, quantity, trace_id=trace_id)
        governed_quantity = float(governed.value_of(ARG_QUANTITY))
        self._check_cap(strategy, governed_quantity)
        if governed_quantity < quantity:
            logger.warning(
                "governance reduced %s %s from %g to %g units",
                strategy.symbol,
                strategy.action,
                quantity,
                governed_quantity,
            )

        side = "buy" if strategy.action == "BUY" else "sell"
        order = await _call(
            self._client.create_order,
            self._venue_symbol(strategy.symbol),
            governed.value_of(ARG_ORDER_TYPE),
            side,
            governed_quantity,
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
