"""Data contracts for inter-community communication in the AIOS trading system.

This module defines the strict Pydantic v2 data schemas used for exchanging payloads
between the decoupled AI agent communities.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def generate_uuid() -> str:
    """Generate a string representation of a random UUID."""
    return str(uuid.uuid4())


def generate_utc_now() -> datetime:
    """Generate the current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


QualityState = Literal["LIVE", "FRESH", "AGING", "STALE", "EXPIRED", "UNKNOWN", "CORRUPTED"]
SourceType = Literal["MARKET", "NEWS", "MACRO", "ONCHAIN", "SIM"]


class DataProvenance(BaseModel):
    """Provenance and quality metadata attached to data-bearing payloads.

    Implements the master-directive requirement that every dataset carries source,
    retrieval timestamp, quality state, license and hash information.
    """

    source_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the originating source/adapter (e.g. 'simulated_v1', 'ccxt:binance')",
    )
    source_type: SourceType = Field(..., description="Category of the data source")
    retrieved_at: datetime = Field(
        default_factory=generate_utc_now,
        description="UTC timestamp at which this data was retrieved/generated",
    )
    data_timestamp: datetime | None = Field(
        default=None,
        description="Exchange/event time of the underlying data if different from retrieval time",
    )
    quality_state: QualityState = Field(
        default="UNKNOWN",
        description="Data-quality state used by freshness/corruption gates",
    )
    quality_score: float | None = Field(
        default=None, ge=0.0, le=100.0, description="Optional 0-100 quality score"
    )
    license: str | None = Field(
        default=None, description="License or terms of the source data if applicable"
    )
    content_hash: str | None = Field(
        default=None,
        description="Content hash (e.g. sha256 hex) for tamper evidence where computed",
    )


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
        description="The normalized sentiment score ranging from -1.0 (very bearish) to 1.0 (very bullish)",
    )
    source: str = Field(..., min_length=1, description="The source of the news article")


class MarketDataPayload(BaseModel):
    """Payload representing raw and processed market data.

    Transmitted from Community 1 (Data Acquisition) to Community 2 (Research).
    """

    timestamp: datetime = Field(
        default_factory=generate_utc_now, description="UTC timestamp of the market data acquisition"
    )
    symbol: str = Field(
        ..., min_length=1, description="Trading symbol or pair identifier (e.g. BTC/USD, NIFTY50)"
    )
    timeframe: str = Field(
        ...,
        min_length=1,
        description="Time interval/resolution of the price data (e.g., 1m, 5m, 1h, 1d)",
    )
    price_data: PriceData = Field(
        ..., description="OHLCV price dictionary containing open, high, low, close, and volume"
    )
    news_sentiment: list[NewsSentiment] | None = Field(
        default=None, description="Optional list of related news articles and sentiment scores"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional unstructured metadata or context"
    )
    provenance: DataProvenance | None = Field(
        default=None,
        description="Source/quality metadata; required for non-simulated production data",
    )
    is_simulated: bool = Field(
        default=False,
        description="Constitutional Law 1.3 tag: MUST be True when data is simulated (ADR-002)",
    )
    lineage_parent_ids: list[str] = Field(
        default_factory=list,
        description="IDs of upstream records this payload was derived from (audit-graph edges)",
    )


class CandidateHypothesis(BaseModel):
    """Payload representing a formulated research hypothesis for trading.

    Transmitted from Community 2 (Research) to Community 3 (Verification).
    """

    hypothesis_id: str = Field(
        default_factory=generate_uuid, description="Unique UUID string representing this hypothesis"
    )
    created_at: datetime = Field(
        default_factory=generate_utc_now, description="UTC datetime when the hypothesis was created"
    )
    symbol: str = Field(..., min_length=1, description="Trading symbol of the asset")
    thesis: str = Field(
        ..., min_length=1, description="Detailed thesis presenting the Bull/Bear rationale"
    )
    supporting_arguments: list[str] = Field(
        ..., description="List of arguments supporting the thesis"
    )
    counter_arguments: list[str] = Field(
        ..., description="List of arguments warning against or contradicting the thesis"
    )
    timeframe: str = Field(
        ..., min_length=1, description="Timeframe for the expected outcome (e.g., 4h, 1d)"
    )
    expected_risk_reward_ratio: float = Field(
        ..., gt=0.0, description="Target risk to reward ratio (e.g., 2.5)"
    )


class VerificationReport(BaseModel):
    """Payload representing verification results for a hypothesis.

    Transmitted from Community 3 (Verification) to Community 4 (Strategy).
    """

    report_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this verification report",
    )
    hypothesis_id: str = Field(
        ..., min_length=1, description="The target CandidateHypothesis ID being verified"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=100.0, description="Verification confidence score from 0.0 to 100.0"
    )
    is_verified: bool = Field(
        default=False,
        description="Indicates if the hypothesis is verified (True if confidence_score >= threshold)",
    )
    verified_claims: list[str] = Field(
        ..., description="List of claims from the hypothesis that were successfully verified"
    )
    flagged_hallucinations: list[str] = Field(
        ..., description="List of assumptions or claims flagged as hallucinated or incorrect"
    )
    verification_notes: str = Field(
        ..., description="Detailed notes and findings from the verification process"
    )

    @model_validator(mode="after")
    def determine_is_verified(self) -> "VerificationReport":
        """Auto-compute is_verified from confidence score unless explicitly provided.

        Per ADR-002/D7: gatekeeping default derives from the 70.0 threshold, but an
        explicitly supplied is_verified value is respected so callers cannot have their
        input silently overridden.
        """
        if "is_verified" not in self.model_fields_set:
            self.is_verified = self.confidence_score >= 70.0
        return self


class StrategySpecification(BaseModel):
    """Payload representing detailed strategy actions and boundaries.

    Transmitted from Community 4 (Strategy) to Training/Execution modules.
    """

    strategy_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this strategy specification",
    )
    hypothesis_id: str = Field(
        ..., min_length=1, description="The source hypothesis ID leading to this strategy"
    )
    symbol: str = Field(..., min_length=1, description="The target trading symbol")
    action: Literal["BUY", "SELL", "HOLD"] = Field(..., description="Action to execute")
    entry_price: float = Field(..., gt=0.0, description="Target entry price trigger")
    stop_loss_price: float = Field(..., gt=0.0, description="Hard stop loss price level")
    take_profit_price: float = Field(..., gt=0.0, description="Take profit target price level")
    position_size_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of total portfolio risk allocated to this position (0.0 to 100.0)",
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
        description="Unique UUID string representing this execution receipt",
    )
    strategy_id: str = Field(
        ..., min_length=1, description="The strategy ID triggering this execution"
    )
    symbol: str = Field(..., min_length=1, description="Trading symbol of the filled trade")
    fill_price: float = Field(
        ..., gt=0.0, description="Average price at which the order was filled"
    )
    filled_quantity: float = Field(..., gt=0.0, description="Total quantity filled")
    slippage: float = Field(
        ...,
        ge=0.0,
        description="Price slippage encountered during execution (absolute difference or deviation)",
    )
    fees: float = Field(..., ge=0.0, description="Execution and transaction fees incurred")
    executed_at: datetime = Field(
        default_factory=generate_utc_now, description="UTC datetime when the execution took place"
    )
    venue: str = Field(
        default="paper",
        description="Execution venue identifier (e.g. 'paper', 'ccxt:binance', 'alpaca')",
    )
    provenance: DataProvenance | None = Field(
        default=None,
        description="Source/quality metadata for the execution record",
    )
    is_simulated: bool = Field(
        default=False,
        description="Constitutional Law 1.3 tag: MUST be True for paper/simulated fills (ADR-002)",
    )
    lineage_parent_ids: list[str] = Field(
        default_factory=list,
        description="IDs of upstream records (strategy_id implied; additional refs allowed)",
    )


class PerformanceSummary(BaseModel):
    """Typed institutional performance summary shared between C7 memory and C8 evolution.

    Introduced by ADR-002 to remove cross-community implementation imports (defect D2):
    consumers depend on this contract, not on MemoryAgent.
    """

    total_trades: int = Field(default=0, ge=0, description="Number of observed closed trades")
    cumulative_pnl: float = Field(
        default=0.0, description="Sum of realized PnL across observations"
    )
    winning_trades: int = Field(default=0, ge=0, description="Count of trades with positive PnL")
    win_rate: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Winning trades as percentage of total"
    )


ExitReason = Literal["TARGET_HIT", "STOP_HIT", "HORIZON_END"]


class ObservationReport(BaseModel):
    """Payload representing trade performance and learning insights.

    Transmitted from Community 6 (Observation) to Community 7 (Memory) and Community 8 (Evolution).
    """

    observation_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this observation report",
    )
    execution_id: str = Field(
        ..., min_length=1, description="The execution receipt ID associated with this observation"
    )
    actual_pnl: float = Field(..., description="The actual realized profit and loss of the trade")
    predicted_vs_actual_deviation: float = Field(
        ..., description="Deviation measure between expected strategy outcome and actual results"
    )
    lessons_learned: list[str] = Field(
        ..., description="Key takeaways, insights, or updates extracted from the observation"
    )
    symbol: str | None = Field(default=None, description="Symbol of the observed trade when known")
    strategy_id: str | None = Field(
        default=None, description="Originating strategy id for lineage when known"
    )
    exit_reason: ExitReason | None = Field(
        default=None, description="Market-driven reason the position was closed"
    )
    direction_correct: bool | None = Field(
        default=None,
        description="Whether realized price movement matched the intended direction",
    )


class PredictionRecord(BaseModel):
    """Prediction-ledger entry recorded BEFORE the outcome is known (Directive 25).

    Written at decision time with an information snapshot; scored later so
    accuracy/calibration can be measured honestly.
    """

    prediction_id: str = Field(
        default_factory=generate_uuid, description="Unique UUID for this prediction"
    )
    created_at: datetime = Field(
        default_factory=generate_utc_now, description="UTC time the prediction was recorded"
    )
    hypothesis_id: str = Field(..., min_length=1, description="Source hypothesis id")
    strategy_id: str | None = Field(
        default=None,
        description="Strategy id if this prediction became a trade; reserved for NO_TRADE entries",
    )
    symbol: str = Field(..., min_length=1)
    direction: Literal["BUY", "SELL"] = Field(..., description="Predicted direction")
    entry_reference_price: float = Field(..., gt=0.0, description="Decision-time reference price")
    target_price: float = Field(..., gt=0.0, description="Expected take-profit level")
    stop_price: float = Field(..., gt=0.0, description="Invalidation (stop) level")
    horizon_timeframe: str = Field(..., min_length=1, description="Expected resolution window")
    confidence_score: float = Field(
        ..., ge=0.0, le=100.0, description="Verification confidence at decision time"
    )
    expected_risk_reward_ratio: float = Field(..., gt=0.0)
    decision_bar_timestamp: datetime = Field(
        ..., description="Timestamp of the decision bar (information snapshot)"
    )
    is_simulated: bool = Field(default=False, description="True when derived from simulated data")
    model_version: str = Field(
        default="deterministic_baseline_v1", description="Reasoning model/version tag"
    )
    status: Literal["PENDING", "SCORED"] = Field(default="PENDING")
    exit_price: float | None = Field(default=None, gt=0.0)
    exit_reason: ExitReason | None = None
    realized_pnl: float | None = None
    direction_correct: bool | None = None
    scored_at: datetime | None = None

    @model_validator(mode="after")
    def validate_scored_fields(self) -> "PredictionRecord":
        """A SCORED prediction must carry its full outcome set."""
        if self.status == "SCORED":
            missing = [
                name
                for name in (
                    "exit_price",
                    "exit_reason",
                    "realized_pnl",
                    "direction_correct",
                    "scored_at",
                )
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"SCORED prediction missing outcome fields: {missing}")
        return self

    def score(
        self,
        exit_price: float,
        exit_reason: ExitReason,
        realized_pnl: float,
        direction_correct: bool,
        scored_at: datetime | None = None,
    ) -> "PredictionRecord":
        """Return a SCORED copy of this prediction (immutable update)."""
        return self.model_copy(
            update={
                "status": "SCORED",
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "realized_pnl": round(realized_pnl, 2),
                "direction_correct": direction_correct,
                "scored_at": scored_at or generate_utc_now(),
            }
        )


class PostmortemRecord(BaseModel):
    """Structured post-mortem for a closed trade (Directive 65).

    Separates decision quality from outcome luck; every field is filled from
    recorded evidence only.
    """

    postmortem_id: str = Field(
        default_factory=generate_uuid, description="Unique UUID for this postmortem"
    )
    created_at: datetime = Field(default_factory=generate_utc_now, description="UTC creation time")
    execution_id: str = Field(..., min_length=1)
    prediction_id: str | None = None
    hypothesis_id: str = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    what_we_thought: str = Field(..., description="The original thesis")
    what_we_knew: list[str] = Field(default_factory=list, description="Evidence available then")
    what_we_did: str = Field(..., description="Action taken with levels and sizing")
    what_happened: str = Field(..., description="Market-driven outcome summary")
    got_right: list[str] = Field(default_factory=list)
    got_wrong: list[str] = Field(default_factory=list)
    unknowable: list[str] = Field(
        default_factory=list, description="Information unavailable at decision time"
    )
    luck_assessment: str = Field(..., description="Honest separation of skill vs variance")
    should_change: list[str] = Field(
        default_factory=list, description="Concrete process changes proposed"
    )
