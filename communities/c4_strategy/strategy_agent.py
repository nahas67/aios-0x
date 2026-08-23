"""Community 4: Strategy Agent for generating risk-evaluated trading strategy specifications."""

import logging
from typing import Optional

from core.event_bus import BaseEventBus, EventTopic
from core.risk_firewall import RiskFirewall
from schemas.contracts import (
    CandidateHypothesis,
    MarketDataPayload,
    StrategySpecification,
    VerificationReport,
)

logger = logging.getLogger(__name__)


class StrategyAgent:
    """Strategy Agent that translates verified hypotheses into actionable strategy specifications."""

    def __init__(self, event_bus: BaseEventBus, risk_firewall: RiskFirewall) -> None:
        """Initialize StrategyAgent with event bus and risk firewall.

        Args:
            event_bus: Event bus instance for inter-community messaging.
            risk_firewall: Risk Firewall engine instance.
        """
        self.event_bus = event_bus
        self.risk_firewall = risk_firewall
        self._hypotheses: dict[str, CandidateHypothesis] = {}
        self._market_prices: dict[str, float] = {}

    async def generate_strategy(
        self,
        verification_report: VerificationReport,
        hypothesis: CandidateHypothesis,
        current_price: float,
        daily_drawdown_pct: float = 0.0,
    ) -> Optional[StrategySpecification]:
        """Generate strategy specification, validate against Risk Firewall, and publish if approved.

        Args:
            verification_report: Approved VerificationReport instance.
            hypothesis: Source CandidateHypothesis instance.
            current_price: Current market entry price.
            daily_drawdown_pct: Current portfolio daily drawdown percentage.

        Returns:
            StrategySpecification if approved by Risk Firewall, otherwise None.
        """
        entry_price = current_price
        stop_loss_price = round(entry_price * 0.97, 4)  # 3% stop loss
        take_profit_price = round(entry_price * 1.06, 4)  # 6% take profit (2.0 R:R)
        proposed_position_size_pct = 5.0

        strategy = StrategySpecification(
            hypothesis_id=hypothesis.hypothesis_id,
            symbol=hypothesis.symbol,
            action="BUY",
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            position_size_pct=proposed_position_size_pct,
        )

        risk_result = self.risk_firewall.evaluate_strategy(
            strategy=strategy,
            current_portfolio_value=100000.0,
            current_daily_drawdown_pct=daily_drawdown_pct,
        )

        if risk_result.is_approved:
            strategy = strategy.model_copy(
                update={"position_size_pct": risk_result.adjusted_position_size_pct}
            )
            await self.event_bus.publish(EventTopic.STRATEGY_GENERATED, strategy)
            logger.info(
                "Published approved StrategySpecification %s for %s to %s",
                strategy.strategy_id,
                strategy.symbol,
                EventTopic.STRATEGY_GENERATED,
            )
            return strategy
        else:
            logger.warning(
                "Strategy for hypothesis %s rejected by Risk Firewall. Reasons: %s",
                hypothesis.hypothesis_id,
                risk_result.rejection_reasons,
            )
            return None

    async def on_data_acquired(self, payload: MarketDataPayload) -> None:
        """Cache latest market close price for the symbol."""
        self._market_prices[payload.symbol] = payload.price_data.close

    async def on_hypothesis_generated(self, hypothesis: CandidateHypothesis) -> None:
        """Cache candidate hypothesis by hypothesis_id."""
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis

    async def on_verification_completed(self, report: VerificationReport) -> None:
        """Event handler callback triggered when a hypothesis is verified."""
        if not report.is_verified:
            logger.debug(
                "Ignoring unverified report %s in StrategyAgent", report.report_id
            )
            return

        hypothesis = self._hypotheses.get(report.hypothesis_id)
        if not hypothesis:
            logger.warning(
                "Hypothesis %s not found in StrategyAgent cache", report.hypothesis_id
            )
            return

        current_price = self._market_prices.get(hypothesis.symbol, 100.0)
        logger.info(
            "StrategyAgent processing VERIFICATION_COMPLETED event for hypothesis %s",
            hypothesis.hypothesis_id,
        )
        await self.generate_strategy(
            verification_report=report,
            hypothesis=hypothesis,
            current_price=current_price,
        )
