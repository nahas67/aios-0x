"""Community 2: Research Agent for formulating trading hypotheses from market data."""

import logging

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import CandidateHypothesis, MarketDataPayload

logger = logging.getLogger(__name__)


class ResearchAgent:
    """Research Agent that analyzes market data and generates candidate hypotheses."""

    def __init__(self, event_bus: BaseEventBus) -> None:
        """Initialize ResearchAgent with event bus instance.

        Args:
            event_bus: Event bus instance for inter-community messaging.
        """
        self.event_bus = event_bus

    async def analyze_and_generate_hypothesis(
        self, payload: MarketDataPayload
    ) -> CandidateHypothesis:
        """Analyze price action and news sentiment to formulate a candidate hypothesis.

        Args:
            payload: MarketDataPayload received from Data Acquisition community.

        Returns:
            CandidateHypothesis instance.
        """
        open_price = payload.price_data.open
        close_price = payload.price_data.close
        price_change_pct = ((close_price - open_price) / open_price) * 100.0

        avg_sentiment = 0.0
        if payload.news_sentiment:
            avg_sentiment = sum(item.sentiment_score for item in payload.news_sentiment) / len(
                payload.news_sentiment
            )

        # Formulate supporting arguments based on data
        supporting_arguments = []
        if price_change_pct >= 0:
            supporting_arguments.append(
                f"Bullish price movement on {payload.timeframe} timeframe with +{price_change_pct:.2f}% gain"
            )
        else:
            supporting_arguments.append(
                f"Price pullback observed on {payload.timeframe} timeframe ({price_change_pct:.2f}%)"
            )

        if avg_sentiment > 0:
            supporting_arguments.append(f"Positive news sentiment score of {avg_sentiment:.2f}")
        elif avg_sentiment < 0:
            supporting_arguments.append(f"Negative news sentiment score of {avg_sentiment:.2f}")
        else:
            supporting_arguments.append("Neutral news sentiment profile")

        # Formulate counter-arguments for balanced hypothesis
        counter_arguments = [
            f"Macroeconomic uncertainty and volatility risks on {payload.symbol}",
            "Potential false breakout or sudden liquidity squeeze",
        ]

        thesis = (
            f"Hypothesis for {payload.symbol} ({payload.timeframe}): "
            f"Price close={close_price} ({price_change_pct:+.2f}%), "
            f"Avg sentiment score={avg_sentiment:.2f}."
        )

        expected_rr = 2.0

        hypothesis = CandidateHypothesis(
            symbol=payload.symbol,
            thesis=thesis,
            supporting_arguments=supporting_arguments,
            counter_arguments=counter_arguments,
            timeframe=payload.timeframe,
            expected_risk_reward_ratio=expected_rr,
        )

        await self.event_bus.publish(EventTopic.HYPOTHESIS_GENERATED, hypothesis)
        logger.info(
            "Published CandidateHypothesis %s for %s to %s",
            hypothesis.hypothesis_id,
            hypothesis.symbol,
            EventTopic.HYPOTHESIS_GENERATED,
        )
        return hypothesis

    async def on_data_acquired(self, payload: MarketDataPayload) -> None:
        """Event handler callback triggered when new market data is acquired.

        Args:
            payload: Received MarketDataPayload event.
        """
        logger.info("ResearchAgent received DATA_ACQUIRED event for %s", payload.symbol)
        await self.analyze_and_generate_hypothesis(payload)
