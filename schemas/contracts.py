"""Data contracts for inter-community communication in the AIOS trading system.

This module defines the strict Pydantic v2 data schemas used for exchanging payloads
between the decoupled AI agent communities.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


def generate_uuid() -> str:
    """Generate a string representation of a random UUID."""
    return str(uuid.uuid4())


def generate_utc_now() -> datetime:
    """Generate the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class PriceData(BaseModel):
    """Schema representing OHLCV (Open, High, Low, Close, Volume) price data."""

    open: float = Field(..., gt=0.0, description="The opening price of the period")
    high: float = Field(..., gt=0.0, description="The highest price reached during the period")
    low: float = Field(..., gt=0.0, description="The lowest price reached during the period")
    close: float = Field(..., gt=0.0, description="The closing price of the period")
    volume: float = Field(..., ge=0.0, description="The trading volume during the period")


class NewsSentiment(BaseModel):
    """Schema representing news articles and their associated sentiment analysis."""

    title: str = Field(..., min_length=1, description="The title of the news article")
    sentiment_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="The normalized sentiment score ranging from -1.0 (very bearish) to 1.0 (very bullish)"
    )
    source: str = Field(..., min_length=1, description="The source of the news article")


class MarketDataPayload(BaseModel):
    """Payload representing raw and processed market data.

    Transmitted from Community 1 (Data Acquisition) to Community 2 (Research).
    """

    timestamp: datetime = Field(
        default_factory=generate_utc_now,
        description="UTC timestamp of the market data acquisition"
    )
    symbol: str = Field(
        ...,
        min_length=1,
        description="Trading symbol or pair identifier (e.g. BTC/USD, NIFTY50)"
    )
    timeframe: str = Field(
        ...,
        min_length=1,
        description="Time interval/resolution of the price data (e.g., 1m, 5m, 1h, 1d)"
    )
    price_data: PriceData = Field(
        ...,
        description="OHLCV price dictionary containing open, high, low, close, and volume"
    )
    news_sentiment: list[NewsSentiment] | None = Field(
        default=None,
        description="Optional list of related news articles and sentiment scores"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional unstructured metadata or context"
    )


class CandidateHypothesis(BaseModel):
    """Payload representing a formulated research hypothesis for trading.

    Transmitted from Community 2 (Research) to Community 3 (Verification).
    """

    hypothesis_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this hypothesis"
    )
    created_at: datetime = Field(
        default_factory=generate_utc_now,
        description="UTC datetime when the hypothesis was created"
    )
    symbol: str = Field(
        ...,
        min_length=1,
        description="Trading symbol of the asset"
    )
    thesis: str = Field(
        ...,
        min_length=1,
        description="Detailed thesis presenting the Bull/Bear rationale"
    )
    supporting_arguments: list[str] = Field(
        ...,
        description="List of arguments supporting the thesis"
    )
    counter_arguments: list[str] = Field(
        ...,
        description="List of arguments warning against or contradicting the thesis"
    )
    timeframe: str = Field(
        ...,
        min_length=1,
        description="Timeframe for the expected outcome (e.g., 4h, 1d)"
    )
    expected_risk_reward_ratio: float = Field(
        ...,
        gt=0.0,
        description="Target risk to reward ratio (e.g., 2.5)"
    )


class VerificationReport(BaseModel):
    """Payload representing verification results for a hypothesis.

    Transmitted from Community 3 (Verification) to Community 4 (Strategy).
    """

    report_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this verification report"
    )
    hypothesis_id: str = Field(
        ...,
        min_length=1,
        description="The target CandidateHypothesis ID being verified"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Verification confidence score from 0.0 to 100.0"
    )
    is_verified: bool = Field(
        default=False,
        description="Indicates if the hypothesis is verified (True if confidence_score >= threshold)"
    )
    verified_claims: list[str] = Field(
        ...,
        description="List of claims from the hypothesis that were successfully verified"
    )
    flagged_hallucinations: list[str] = Field(
        ...,
        description="List of assumptions or claims flagged as hallucinated or incorrect"
    )
    verification_notes: str = Field(
        ...,
        description="Detailed notes and findings from the verification process"
    )

    @model_validator(mode="after")
    def determine_is_verified(self) -> "VerificationReport":
        """Compute is_verified status based on confidence score threshold."""
        # Threshold for verification is defined as 70.0
        threshold = 70.0
        # Automatically determine is_verified if not explicitly set to True
        # If confidence score is >= threshold, it's verified.
        self.is_verified = self.confidence_score >= threshold
        return self


class StrategySpecification(BaseModel):
    """Payload representing detailed strategy actions and boundaries.

    Transmitted from Community 4 (Strategy) to Training/Execution modules.
    """

    strategy_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this strategy specification"
    )
    hypothesis_id: str = Field(
        ...,
        min_length=1,
        description="The source hypothesis ID leading to this strategy"
    )
    symbol: str = Field(
        ...,
        min_length=1,
        description="The target trading symbol"
    )
    action: Literal["BUY", "SELL", "HOLD"] = Field(
        ...,
        description="Action to execute"
    )
    entry_price: float = Field(
        ...,
        gt=0.0,
        description="Target entry price trigger"
    )
    stop_loss_price: float = Field(
        ...,
        gt=0.0,
        description="Hard stop loss price level"
    )
    take_profit_price: float = Field(
        ...,
        gt=0.0,
        description="Take profit target price level"
    )
    position_size_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of total portfolio risk allocated to this position (0.0 to 100.0)"
    )

    @model_validator(mode="after")
    def validate_price_levels(self) -> "StrategySpecification":
        """Validate that stop loss and take profit are consistent with action type."""
        if self.action == "BUY":
            if self.stop_loss_price >= self.entry_price:
                raise ValueError("Stop loss must be lower than entry price for a BUY strategy")
            if self.take_profit_price <= self.entry_price:
                raise ValueError("Take profit must be higher than entry price for a BUY strategy")
        elif self.action == "SELL":
            if self.stop_loss_price <= self.entry_price:
                raise ValueError("Stop loss must be higher than entry price for a SELL strategy")
            if self.take_profit_price >= self.entry_price:
                raise ValueError("Take profit must be lower than entry price for a SELL strategy")
        return self


class TradeExecutionReceipt(BaseModel):
    """Payload representing trade fulfillment results.

    Transmitted from Community 5 (Execution) to Community 6 (Observation).
    """

    execution_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this execution receipt"
    )
    strategy_id: str = Field(
        ...,
        min_length=1,
        description="The strategy ID triggering this execution"
    )
    symbol: str = Field(
        ...,
        min_length=1,
        description="Trading symbol of the filled trade"
    )
    fill_price: float = Field(
        ...,
        gt=0.0,
        description="Average price at which the order was filled"
    )
    filled_quantity: float = Field(
        ...,
        gt=0.0,
        description="Total quantity filled"
    )
    slippage: float = Field(
        ...,
        ge=0.0,
        description="Price slippage encountered during execution (absolute difference or deviation)"
    )
    fees: float = Field(
        ...,
        ge=0.0,
        description="Execution and transaction fees incurred"
    )
    executed_at: datetime = Field(
        default_factory=generate_utc_now,
        description="UTC datetime when the execution took place"
    )


class ObservationReport(BaseModel):
    """Payload representing trade performance and learning insights.

    Transmitted from Community 6 (Observation) to Community 7 (Memory) and Community 8 (Evolution).
    """

    observation_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this observation report"
    )
    execution_id: str = Field(
        ...,
        min_length=1,
        description="The execution receipt ID associated with this observation"
    )
    actual_pnl: float = Field(
        ...,
        description="The actual realized profit and loss of the trade"
    )
    predicted_vs_actual_deviation: float = Field(
        ...,
        description="Deviation measure between expected strategy outcome and actual results"
    )
    lessons_learned: list[str] = Field(
        ...,
        description="Key takeaways, insights, or updates extracted from the observation"
    )
