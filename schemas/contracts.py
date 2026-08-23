"""Data contracts for inter-community communication in the AIOS trading system.

This module defines the strict Pydantic v2 data schemas used for exchanging payloads
between the decoupled AI agent communities.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
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
    fact_score: float | None = Field(
        default=None, ge=0.0, le=40.0, description="Rubric: fact & data verification points"
    )
    balance_score: float | None = Field(
        default=None, ge=0.0, le=30.0, description="Rubric: balanced reasoning points"
    )
    math_score: float | None = Field(
        default=None, ge=0.0, le=30.0, description="Rubric: mathematical validity points"
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
    family: str = Field(
        default="momentum",
        description="Strategy family tag (momentum | mean_reversion | ...)",
    )

    def risk_reward_ratio(self) -> float:
        """Reward distance / risk distance from entry."""
        risk = abs(self.entry_price - self.stop_loss_price)
        if risk <= 0:
            return 0.0
        return abs(self.take_profit_price - self.entry_price) / risk

    def notional_pct_of(self, portfolio_value: float) -> float:
        """Notional this trade adds as % of the given portfolio value."""
        return self.position_size_pct

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


class EvidencePack(BaseModel):
    """Market facts available at decision time; the grounding set for claim checks.

    Built from a MarketDataPayload by C3 so verification can test cited
    numbers against reality instead of trusting list lengths.
    """

    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    momentum_pct: float
    range_pct: float
    sentiment_avg: float

    @classmethod
    def from_payload(cls, payload: "MarketDataPayload") -> "EvidencePack":
        price = payload.price_data
        momentum = (price.close - price.open) / price.open * 100.0
        bar_range = (price.high - price.low) / price.open * 100.0
        sentiment = 0.0
        if payload.news_sentiment:
            sentiment = sum(s.sentiment_score for s in payload.news_sentiment) / len(
                payload.news_sentiment
            )
        return cls(
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            open=price.open,
            high=price.high,
            low=price.low,
            close=price.close,
            volume=price.volume,
            momentum_pct=momentum,
            range_pct=bar_range,
            sentiment_avg=sentiment,
        )

    def reference_numbers(self) -> list[float]:
        """Values that claims may legitimately cite (rounded variants included)."""
        base = [
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
            self.sentiment_avg,
            self.momentum_pct,
            self.range_pct,
        ]
        rounded = [round(v, 2) for v in base]
        return base + rounded


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


# ------------------------------------------------- world intelligence (C10)


class ScheduledEvent(BaseModel):
    """A scheduled world/macro event with consensus and (later) actual outcome.

    ``actual`` is None until the event resolves; the expectation engine
    computes surprise only from recorded values - never invented ones.
    """

    event_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    event_time: datetime = Field(..., description="Scheduled UTC release time")
    consensus: float | None = Field(default=None, description="Market consensus value")
    prior: float | None = Field(default=None, description="Prior printed value")
    actual: float | None = Field(default=None, description="Printed actual (None until released)")
    unit: str = Field(default="", description="Unit of the values (%, index...)")
    higher_is_better: bool = Field(
        default=True,
        description=(
            "Direction convention for surprise interpretation (Directive 12): for GDP, "
            "higher prints are 'better than expected'; for CPI/unemployment the opposite. "
            "Interpretation is ALWAYS relative to expectations, never naive good/bad."
        ),
    )
    affected_symbols: list[str] = Field(default_factory=list)
    source_tag: str = Field(default="user_calendar", min_length=1)
    is_simulated: bool = Field(default=False)


class ExpectationSnapshot(BaseModel):
    """Expected vs actual vs interpretation for one resolved event (Directive 12).

    Interpretation is relative to EXPECTATIONS (better/worse than feared),
    never a naive good-news/bad-news label.
    """

    snapshot_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=generate_utc_now)
    event_id: str
    title: str
    consensus: float | None
    actual: float
    surprise: float = Field(..., description="actual - consensus")
    surprise_pct: float = Field(..., description="surprise relative to |consensus|")
    interpretation: Literal["BETTER_THAN_EXPECTED", "WORSE_THAN_EXPECTED", "AS_EXPECTED"]
    affected_symbols: list[str]
    is_simulated: bool = False


class ScenarioCard(BaseModel):
    """One pre-event scenario with probability and invalidation condition."""

    name: Literal["BASE", "BULL", "BEAR", "UNEXPECTED", "EXTREME"]
    probability: float = Field(..., ge=0.0, le=1.0)
    expected_impact: str
    horizon_timeframe: str
    invalidation_condition: str


class ScenarioSet(BaseModel):
    """Pre-event scenario distribution (Directive 29)."""

    scenario_set_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=generate_utc_now)
    event_id: str
    title: str
    cards: list[ScenarioCard] = Field(min_length=3)
    is_simulated: bool = False

    @model_validator(mode="after")
    def validate_probabilities(self) -> "ScenarioSet":
        total = sum(c.probability for c in self.cards)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"scenario probabilities sum to {total}, expected ~1.0")
        return self


class TrendLabel(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


class VolRegime(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class RegimeState(BaseModel):
    """Deterministic regime assessment for one symbol (Directive 37)."""

    symbol: str
    trend: TrendLabel
    vol_regime: VolRegime
    realized_vol_pct: float = Field(..., ge=0.0, description="Stdev of bar returns (%)")
    ema_slope_pct: float = Field(..., description="EMA(8) slope over window (%)")
    assessed_at: datetime
    window_bars: int = Field(..., gt=0)
    is_simulated: bool = False


class DataAnomalyAlert(BaseModel):
    """Emitted when ingested data violates sanity rules (Doc 02 / Directive 9)."""

    alert_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=generate_utc_now)
    symbol: str
    anomaly_type: Literal["OHLC_INVALID", "PRICE_GAP", "VOLUME_SPIKE", "STALE_DATA", "SCHEMA_DRIFT"]
    severity: Literal["WARNING", "CRITICAL"]
    detail: str
    observed_value: float | None = None
    reference_value: float | None = None
    freezes_symbol: bool = Field(
        default=False,
        description="True when downstream strategy generation must pause for this symbol",
    )
    is_simulated: bool = False


# --------------------------------------------- portfolio & research (C9 / lab)


class OpportunityScore(BaseModel):
    """Ranked opportunity assessment for one strategy candidate (Directive 30)."""

    score_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=generate_utc_now)
    strategy_id: str
    symbol: str
    family: str
    edge_proxy: float = Field(description="confidence - breakeven probability, clipped")
    expected_rr: float
    alpha_decay_multiplier: float = Field(ge=0.0, le=1.0)
    composite_rank: float
    is_simulated: bool = False


class PortfolioStatus(StrEnum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CAUTION = "CAUTION"
    CRITICAL_HALT = "CRITICAL_HALT"


class PortfolioAllocationPlan(BaseModel):
    """C9 output: final allocation decision for a proposed strategy (Doc 15).

    Nothing executes without this plan - the governor sits between strategy
    generation and the execution/paper engine.
    """

    plan_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=generate_utc_now)
    strategy: StrategySpecification
    approved: bool
    final_position_size_pct: float = Field(ge=0.0, le=100.0)
    portfolio_status: PortfolioStatus
    drawdown_pct: float = Field(ge=0.0)
    kelly_fraction_used: float | None = Field(
        default=None, ge=0.0, description="Fractional Kelly size when calibration data allowed"
    )
    class_exposures_pct: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    is_simulated: bool = False


class IntegrityCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class IntegrityReport(BaseModel):
    """Backtest-integrity linter output (Directive 33)."""

    report_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=generate_utc_now)
    checks: list[IntegrityCheck]
    passed: bool = False

    @model_validator(mode="after")
    def derive_passed(self) -> "IntegrityReport":
        if "passed" not in self.model_fields_set:
            self.passed = bool(self.checks) and all(c.passed for c in self.checks)
        return self


class WalkWindowResult(BaseModel):
    window_index: int
    train_bars: int
    test_bars: int
    test_trades: int
    test_pnl: float
    test_sharpe: float
    test_max_dd_pct: float
    overfit_flag: bool = False


class WalkForwardReport(BaseModel):
    """Walk-forward validation results (Doc 06 defaults 90/30)."""

    report_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=generate_utc_now)
    windows: list[WalkWindowResult]
    aggregate_test_pnl: float = 0.0
    overfit_windows: int = 0
    passed: bool = True


class CalibrationBucket(BaseModel):
    confidence_low: float
    confidence_high: float
    predictions: int
    empirical_accuracy_pct: float
    avg_confidence_pct: float


class CalibrationReport(BaseModel):
    """Prediction-ledger reliability + Brier scoring (Directive 25/82)."""

    report_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=generate_utc_now)
    total_scored: int
    brier_score: float = Field(ge=0.0, le=1.0)
    directional_accuracy_pct: float
    buckets: list[CalibrationBucket]
    reliable: bool = Field(
        default=False,
        description="True when >=20 scored predictions exist (minimum for judgment)",
    )
