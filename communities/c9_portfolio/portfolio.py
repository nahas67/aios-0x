"""Community 9: Portfolio Intelligence.

- OpportunityEngine: ranks strategy candidates by edge proxy x reward x
  alpha-decay (Directives 30/31).
- PortfolioGovernor: the Doc 15 gate between strategy generation and
  execution - drawdown tiers, class exposure caps, fractional Kelly sizing.
Nothing executes without an approved PortfolioAllocationPlan.
"""

import math
from collections.abc import Callable

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import (
    OpportunityScore,
    PortfolioAllocationPlan,
    PortfolioStatus,
    StrategySpecification,
)

_ = math  # retained for volatility-parity extension (Doc 15)

# Alpha-decay half-lives in BARS by timeframe (Directive 31; deterministic v0)
_DECAY_HALFLIFE_BARS = {
    "1m": 60.0,
    "5m": 30.0,
    "15m": 20.0,
    "1h": 12.0,
    "4h": 8.0,
    "1d": 5.0,
}

_DEFAULT_CLASS_MAP: dict[str, str] = {
    "BTC/USD": "CRYPTO",
    "ETH/USD": "CRYPTO",
    "SOL/USD": "CRYPTO",
    "AAPL": "EQUITY",
    "MSFT": "EQUITY",
    "SPY": "EQUITY",
    "QQQ": "EQUITY",
}


def alpha_decay_multiplier(timeframe: str, bars_since_signal: int) -> float:
    """Exponential decay of edge by elapsed bars vs timeframe half-life."""
    halflife = _DECAY_HALFLIFE_BARS.get(timeframe, 10.0)
    return float(0.5 ** (max(0, bars_since_signal) / halflife))


class OpportunityEngine:
    """Scores candidates: (confidence - breakeven_p) x RR x decay."""

    def __init__(self, event_bus: BaseEventBus) -> None:
        self.event_bus = event_bus

    def score(
        self,
        strategy: StrategySpecification,
        family: str,
        confidence_pct: float,
        bars_since_signal: int,
        timeframe: str = "1d",
    ) -> OpportunityScore:
        rr = max(strategy.risk_reward_ratio(), 0.01)
        breakeven_p = 1.0 / (1.0 + rr)
        edge = max(-1.0, min(1.0, confidence_pct / 100.0 - breakeven_p))
        decay = alpha_decay_multiplier(timeframe, bars_since_signal)
        return OpportunityScore(
            strategy_id=strategy.strategy_id,
            symbol=strategy.symbol,
            family=family,
            edge_proxy=round(edge, 6),
            expected_rr=round(rr, 4),
            alpha_decay_multiplier=round(decay, 6),
            composite_rank=round(edge * rr * decay, 6),
            is_simulated=True,
        )

    async def publish_ranking(self, scores: list[OpportunityScore]) -> None:
        for score in sorted(scores, key=lambda s: s.composite_rank, reverse=True):
            await self.event_bus.publish(EventTopic.OPPORTUNITY_RANKED, score)


class PortfolioGovernor:
    """Doc 15 gatekeeper: approves/rejects/sizes strategies before execution.

    Dependencies are injected as typed providers (isolation rule): equity and
    exposure snapshots come from the composition root, calibration from C7's
    prediction ledger when available.
    """

    def __init__(
        self,
        event_bus: BaseEventBus,
        initial_equity: float,
        equity_provider: Callable[[], float],
        exposure_by_class_provider: Callable[[], dict[str, float]],
        win_rate_provider: Callable[[str], tuple[float, int]] | None = None,
        asset_class_map: dict[str, str] | None = None,
        max_class_exposure_pct: float = 35.0,
        warning_dd_pct: float = 1.5,
        caution_dd_pct: float = 2.5,
        halt_dd_pct: float = 3.0,
    ) -> None:
        if initial_equity <= 0:
            raise ValueError("initial_equity must be positive")
        self.event_bus = event_bus
        self.initial_equity = initial_equity
        self._equity_provider = equity_provider
        self._exposure_provider = exposure_by_class_provider
        self._win_rate_provider = win_rate_provider
        self._classes = {**_DEFAULT_CLASS_MAP, **(asset_class_map or {})}
        self.max_class_exposure_pct = max_class_exposure_pct
        self.warning_dd_pct = warning_dd_pct
        self.caution_dd_pct = caution_dd_pct
        self.halt_dd_pct = halt_dd_pct
        self._peak_equity = initial_equity

    # ------------------------------------------------------------- internals

    def current_drawdown_pct(self) -> float:
        equity = self._equity_provider()
        self._peak_equity = max(self._peak_equity, equity)
        if self._peak_equity <= 0:
            return 0.0
        return round((self._peak_equity - equity) / self._peak_equity * 100.0, 4)

    def status_for(self, drawdown_pct: float) -> PortfolioStatus:
        if drawdown_pct >= self.halt_dd_pct:
            return PortfolioStatus.CRITICAL_HALT
        if drawdown_pct >= self.caution_dd_pct:
            return PortfolioStatus.CAUTION
        if drawdown_pct >= self.warning_dd_pct:
            return PortfolioStatus.WARNING
        return PortfolioStatus.HEALTHY

    @staticmethod
    def _dd_size_scalar(status: PortfolioStatus) -> float:
        return {"HEALTHY": 1.0, "WARNING": 0.75, "CAUTION": 0.5}.get(status.value, 0.0)

    def _kelly_fraction(
        self, symbol: str, strategy: StrategySpecification
    ) -> tuple[float | None, float]:
        """Return (kelly_fraction|None, calibrated_win_prob).

        Fractional Kelly f* = k*(pb - q)/b with b=R:R; falls back to breakeven
        probability when no calibration data exists (honest ignorance).
        """
        b = max(strategy.risk_reward_ratio(), 0.01)
        if self._win_rate_provider is None:
            p = 1.0 / (1.0 + b)
            return None, p
        empirical_p, samples = self._win_rate_provider(symbol)
        if samples < 20:
            p = 1.0 / (1.0 + b)
            return None, p
        p = max(0.01, min(0.99, empirical_p))
        q = 1.0 - p
        full_kelly = (p * b - q) / b
        fractional = max(0.0, 0.5 * full_kelly)  # half-Kelly per Doc 15
        return fractional, p

    def evaluate(
        self,
        strategy: StrategySpecification,
        confidence_pct: float = 70.0,
    ) -> PortfolioAllocationPlan:
        dd = self.current_drawdown_pct()
        status = self.status_for(dd)
        reasons: list[str] = []

        exposures = self._exposure_provider()
        total_equity = self._equity_provider()
        class_exposure_pct = {
            cls: round(notional / total_equity * 100.0, 4) for cls, notional in exposures.items()
        }

        approved = True
        final_size = strategy.position_size_pct

        if status == PortfolioStatus.CRITICAL_HALT:
            approved = False
            reasons.append(f"CRITICAL_HALT at drawdown {dd:.2f}% (Doc 15 tier)")
            final_size = 0.0

        symbol_class = self._classes.get(strategy.symbol, "OTHER")
        existing = class_exposure_pct.get(symbol_class, 0.0)
        added = strategy.notional_pct_of(total_equity)
        if approved and existing + added > self.max_class_exposure_pct:
            room = max(0.0, self.max_class_exposure_pct - existing)
            if room <= 0.5:
                approved = False
                reasons.append(
                    f"Class {symbol_class} exposure {existing:.2f}% at cap "
                    f"{self.max_class_exposure_pct:.0f}%"
                )
                final_size = 0.0
            else:
                scaled = strategy.position_size_pct * room / max(added, 1e-9)
                final_size = min(final_size, round(scaled, 2))
                reasons.append(
                    f"Sized down to respect {symbol_class} cap ({self.max_class_exposure_pct:.0f}%)"
                )

        kelly_fraction, calibrated_p = self._kelly_fraction(strategy.symbol, strategy)
        scalar = self._dd_size_scalar(status)
        if approved:
            if kelly_fraction is not None:
                kelly_pct = round(kelly_fraction * 100.0, 2)
                final_size = min(final_size, kelly_pct)
                reasons.append(f"Half-Kelly cap {kelly_pct}% (calibrated p={calibrated_p:.2f})")
            if scalar < 1.0:
                final_size = round(final_size * scalar, 2)
                reasons.append(f"Drawdown-tier scaling x{scalar:g} ({status.value})")
            if not reasons:
                reasons.append("Approved within limits.")

        adjusted = (
            strategy.model_copy(update={"position_size_pct": max(0.0, final_size)})
            if approved
            else strategy
        )
        return PortfolioAllocationPlan(
            strategy=adjusted,
            approved=approved,
            final_position_size_pct=max(0.0, final_size),
            portfolio_status=status,
            drawdown_pct=dd,
            kelly_fraction_used=kelly_fraction,
            class_exposures_pct=class_exposure_pct,
            reasons=reasons,
            is_simulated=True,
        )

    async def on_strategy_generated(self, strategy: StrategySpecification) -> None:
        plan = self.evaluate(strategy)
        topic = EventTopic.PORTFOLIO_ALLOCATED if plan.approved else EventTopic.PORTFOLIO_REJECTED
        await self.event_bus.publish(topic, plan)
