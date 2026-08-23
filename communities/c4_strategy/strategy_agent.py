"""Community 4: Strategy Agent for generating risk-evaluated trading strategy specifications.

ADR-002/D3: strategies are derived deterministically from observed market state
(momentum, sentiment, realized bar range) and the hypothesis risk/reward target.
BUY, SELL and NO TRADE are all valid outcomes; missing market state yields NO TRADE
rather than an invented default price.
"""

import logging
from collections import OrderedDict
from typing import Literal, TypeVar

from core.data_quality import _FREEZING_STATES
from core.event_bus import BaseEventBus, EventTopic
from core.risk_firewall import RiskFirewall
from schemas.contracts import (
    CandidateHypothesis,
    DataAnomalyAlert,
    MarketDataPayload,
    RegimeState,
    StrategySpecification,
    VerificationReport,
    VolRegime,
)

logger = logging.getLogger(__name__)

_DEFAULT_PROPOSED_POSITION_SIZE_PCT = 5.0
_MIN_STOP_DISTANCE_PCT = 0.5
_STOP_FRACTION_OF_RANGE = 0.5
_CACHE_MAX_ENTRIES = 512

# Volatility-regime scaling of proposed size (Directive 37 conditioning)
_VOL_SIZE_SCALAR = {
    VolRegime.HIGH: 0.5,
    VolRegime.NORMAL: 1.0,
    VolRegime.LOW: 1.0,
}

T = TypeVar("T")


def _bounded_put(cache: OrderedDict[str, T], key: str, value: T) -> None:
    """Insert into cache with FIFO eviction beyond _CACHE_MAX_ENTRIES (defect D6)."""
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _CACHE_MAX_ENTRIES:
        cache.popitem(last=False)


class StrategyAgent:
    """Strategy Agent that translates verified hypotheses into actionable strategy specifications."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        risk_firewall: RiskFirewall,
        portfolio_value_estimate: float = 100000.0,
    ) -> None:
        """Initialize StrategyAgent with event bus and risk firewall.

        Args:
            event_bus: Event bus instance for inter-community messaging.
            risk_firewall: Risk Firewall engine instance.
            portfolio_value_estimate: Portfolio value supplied to the firewall for
                notional sizing (owned by the composition root until C9 exists).
        """
        if portfolio_value_estimate <= 0:
            raise ValueError("portfolio_value_estimate must be positive")
        self.event_bus = event_bus
        self.risk_firewall = risk_firewall
        self._portfolio_value_estimate = portfolio_value_estimate
        self._hypotheses: OrderedDict[str, CandidateHypothesis] = OrderedDict()
        self._market_payloads: OrderedDict[str, MarketDataPayload] = OrderedDict()
        self._frozen_symbols: set[str] = set()
        self._regimes: dict[str, RegimeState] = {}

    async def generate_strategy(
        self,
        verification_report: VerificationReport,
        hypothesis: CandidateHypothesis,
        daily_drawdown_pct: float = 0.0,
    ) -> StrategySpecification | None:
        """Generate a strategy specification from cached market state and firewall rules.

        Args:
            verification_report: Approved VerificationReport instance.
            hypothesis: Source CandidateHypothesis instance.
            daily_drawdown_pct: Current portfolio daily drawdown percentage.

        Returns:
            StrategySpecification if a tradeable setup passed the Risk Firewall,
            otherwise None (NO TRADE / insufficient evidence).
        """
        payload = self._market_payloads.get(hypothesis.symbol)
        if payload is None:
            logger.info(
                "NO TRADE for hypothesis %s: no market state cached for %s",
                hypothesis.hypothesis_id,
                hypothesis.symbol,
            )
            return None

        if hypothesis.symbol in self._frozen_symbols:
            logger.info(
                "NO TRADE for hypothesis %s: %s frozen by data anomaly (Directive 9 reaction)",
                hypothesis.hypothesis_id,
                hypothesis.symbol,
            )
            return None

        price_data = payload.price_data
        entry_price = price_data.close
        momentum_pct = (price_data.close - price_data.open) / price_data.open * 100.0

        avg_sentiment = 0.0
        if payload.news_sentiment:
            avg_sentiment = sum(i.sentiment_score for i in payload.news_sentiment) / len(
                payload.news_sentiment
            )

        action: Literal["BUY", "SELL"]
        if momentum_pct > 0 and avg_sentiment >= 0:
            action = "BUY"
        elif momentum_pct < 0 and avg_sentiment <= 0:
            action = "SELL"
        else:
            logger.info(
                "NO TRADE for hypothesis %s on %s: mixed signal (momentum=%.2f%%, sentiment=%.2f)",
                hypothesis.hypothesis_id,
                hypothesis.symbol,
                momentum_pct,
                avg_sentiment,
            )
            return None

        max_stop_pct = self.risk_firewall.config.max_stop_loss_pct * 0.8
        bar_range_pct = (price_data.high - price_data.low) / price_data.open * 100.0
        stop_distance_pct = min(
            max(bar_range_pct * _STOP_FRACTION_OF_RANGE, _MIN_STOP_DISTANCE_PCT),
            max_stop_pct,
        )
        target_distance_pct = stop_distance_pct * hypothesis.expected_risk_reward_ratio

        if action == "BUY":
            stop_loss_price = round(entry_price * (1.0 - stop_distance_pct / 100.0), 4)
            take_profit_price = round(entry_price * (1.0 + target_distance_pct / 100.0), 4)
        else:
            stop_loss_price = round(entry_price * (1.0 + stop_distance_pct / 100.0), 4)
            take_profit_price = round(entry_price * (1.0 - target_distance_pct / 100.0), 4)

        regime = self._regimes.get(hypothesis.symbol)
        scalar = _VOL_SIZE_SCALAR.get(regime.vol_regime, 1.0) if regime else 1.0
        proposed_size = round(_DEFAULT_PROPOSED_POSITION_SIZE_PCT * scalar, 2)

        strategy = StrategySpecification(
            hypothesis_id=hypothesis.hypothesis_id,
            symbol=hypothesis.symbol,
            action=action,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            position_size_pct=proposed_size,
        )

        portfolio_value = self._portfolio_value_estimate
        risk_result = self.risk_firewall.evaluate_strategy(
            strategy=strategy,
            current_portfolio_value=portfolio_value,
            current_daily_drawdown_pct=daily_drawdown_pct,
        )

        if risk_result.is_approved:
            strategy = strategy.model_copy(
                update={"position_size_pct": risk_result.adjusted_position_size_pct}
            )
            await self.event_bus.publish(EventTopic.STRATEGY_GENERATED, strategy)
            logger.info(
                "Published approved %s StrategySpecification %s for %s (notional=%.2f) to %s",
                action,
                strategy.strategy_id,
                strategy.symbol,
                risk_result.position_notional_value,
                EventTopic.STRATEGY_GENERATED,
            )
            return strategy

        logger.warning(
            "Strategy for hypothesis %s rejected by Risk Firewall. Reasons: %s",
            hypothesis.hypothesis_id,
            risk_result.rejection_reasons,
        )
        return None

    async def on_data_acquired(self, payload: MarketDataPayload) -> None:
        """Cache latest market payload per symbol (bounded); clean arrivals unfreeze."""
        _bounded_put(self._market_payloads, payload.symbol, payload)
        quality = payload.provenance.quality_state if payload.provenance else "FRESH"
        if payload.is_simulated or quality not in _FREEZING_STATES:
            self._frozen_symbols.discard(payload.symbol)

    async def on_data_anomaly(self, alert: DataAnomalyAlert) -> None:
        """Directive 9 reaction: freeze the symbol when the alert demands it."""
        if alert.freezes_symbol:
            self._frozen_symbols.add(alert.symbol)
            logger.warning(
                "Symbol %s frozen for strategy generation: %s (%s)",
                alert.symbol,
                alert.anomaly_type,
                alert.detail,
            )

    async def on_regime_changed(self, state: RegimeState) -> None:
        """Track latest regime per symbol for volatility-scaled sizing."""
        self._regimes[state.symbol] = state

    async def on_hypothesis_generated(self, hypothesis: CandidateHypothesis) -> None:
        """Cache candidate hypothesis by hypothesis_id (bounded)."""
        _bounded_put(self._hypotheses, hypothesis.hypothesis_id, hypothesis)

    async def on_verification_completed(self, report: VerificationReport) -> None:
        """Event handler callback triggered when a hypothesis is verified."""
        if not report.is_verified:
            logger.debug("Ignoring unverified report %s in StrategyAgent", report.report_id)
            return

        hypothesis = self._hypotheses.get(report.hypothesis_id)
        if not hypothesis:
            logger.warning("Hypothesis %s not found in StrategyAgent cache", report.hypothesis_id)
            return

        if hypothesis.symbol not in self._market_payloads:
            logger.info(
                "NO TRADE for hypothesis %s: market state missing at decision time",
                report.hypothesis_id,
            )
            return

        logger.info(
            "StrategyAgent processing VERIFICATION_COMPLETED event for hypothesis %s",
            hypothesis.hypothesis_id,
        )
        await self.generate_strategy(
            verification_report=report,
            hypothesis=hypothesis,
        )
