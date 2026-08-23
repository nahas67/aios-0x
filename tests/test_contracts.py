"""Unit tests for AIOS data contracts defined in schemas/contracts.py."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from schemas.contracts import (
    CandidateHypothesis,
    DataProvenance,
    MarketDataPayload,
    NewsSentiment,
    ObservationReport,
    PerformanceSummary,
    PriceData,
    StrategySpecification,
    TradeExecutionReceipt,
    VerificationReport,
    generate_utc_now,
    generate_uuid,
)


def test_uuid_generation() -> None:
    """Verify UUID helper generates valid UUID strings."""
    uid = generate_uuid()
    assert isinstance(uid, str)
    assert len(uid) == 36
    # Verify unique generations
    assert generate_uuid() != generate_uuid()


def test_utc_now_generation() -> None:
    """Verify datetime helper generates timezone-aware UTC datetimes."""
    now = generate_utc_now()
    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_market_data_payload() -> None:
    """Test MarketDataPayload instantiation and validations."""
    price_dict = {"open": 100.0, "high": 105.0, "low": 98.0, "close": 102.5, "volume": 1500.0}

    # Valid minimal payload
    payload = MarketDataPayload(
        symbol="BTC/USD", timeframe="1h", price_data=PriceData(**price_dict)
    )

    assert payload.symbol == "BTC/USD"
    assert payload.timeframe == "1h"
    assert isinstance(payload.price_data, PriceData)
    assert payload.price_data.close == 102.5
    assert payload.news_sentiment is None
    assert payload.metadata == {}
    assert isinstance(payload.timestamp, datetime)

    # Valid payload with sentiment and metadata
    payload_full = MarketDataPayload(
        symbol="NIFTY50",
        timeframe="1d",
        price_data=PriceData(**price_dict),
        news_sentiment=[NewsSentiment(title="Market Rises", sentiment_score=0.8, source="Reuters")],
        metadata={"source_feed": "websockets"},
    )

    assert payload_full.news_sentiment is not None
    assert len(payload_full.news_sentiment) == 1
    assert payload_full.news_sentiment[0].sentiment_score == 0.8
    assert payload_full.metadata["source_feed"] == "websockets"

    # ADR-002 defaults: provenance absent, simulation tag False, empty lineage
    assert payload.provenance is None
    assert payload.is_simulated is False
    assert payload.lineage_parent_ids == []

    # Provenance-bearing payload with simulation tag (Constitution Law 1.3)
    payload_prov = MarketDataPayload(
        symbol="BTC/USD",
        timeframe="1m",
        price_data=PriceData(**price_dict),
        is_simulated=True,
        provenance=DataProvenance(
            source_id="simulated_v1",
            source_type="SIM",
            quality_state="FRESH",
        ),
        lineage_parent_ids=["raw-1"],
    )
    assert payload_prov.is_simulated is True
    assert payload_prov.provenance is not None
    assert payload_prov.provenance.source_type == "SIM"
    assert payload_prov.lineage_parent_ids == ["raw-1"]


def test_candidate_hypothesis() -> None:
    """Test CandidateHypothesis instantiation."""
    hypothesis = CandidateHypothesis(
        symbol="ETH/USD",
        thesis="Breakout above resistance confirmed by volume",
        supporting_arguments=["Bullish flag pattern", "High volume on breakout"],
        counter_arguments=["Macro rate decisions pending"],
        timeframe="4h",
        expected_risk_reward_ratio=3.0,
    )

    assert isinstance(hypothesis.hypothesis_id, str)
    assert len(hypothesis.hypothesis_id) == 36
    assert isinstance(hypothesis.created_at, datetime)
    assert hypothesis.symbol == "ETH/USD"
    assert hypothesis.expected_risk_reward_ratio == 3.0


def test_verification_report() -> None:
    """Test VerificationReport and its automatic threshold logic for is_verified."""
    hypothesis_id = generate_uuid()

    # Under verification threshold (70.0) -> is_verified should be False
    report_unverified = VerificationReport(
        hypothesis_id=hypothesis_id,
        confidence_score=69.9,
        verified_claims=["Support holds"],
        flagged_hallucinations=["Target price too aggressive"],
        verification_notes="Hypothesis verification failed to meet confidence bar.",
    )
    assert report_unverified.is_verified is False

    # At/Above verification threshold (70.0) -> is_verified should be True
    report_verified = VerificationReport(
        hypothesis_id=hypothesis_id,
        confidence_score=70.0,
        verified_claims=["Support holds", "Trend is strong"],
        flagged_hallucinations=[],
        verification_notes="Confidence meets the threshold criteria.",
    )
    assert report_verified.is_verified is True

    # D7 fix: an explicitly provided is_verified is respected, not silently overridden
    report_explicit = VerificationReport(
        hypothesis_id=hypothesis_id,
        confidence_score=50.0,
        is_verified=True,
        verified_claims=["Explicit override respected"],
        flagged_hallucinations=[],
        verification_notes="Caller explicitly marked verified.",
    )
    assert report_explicit.is_verified is True


def test_strategy_specification() -> None:
    """Test StrategySpecification and validation rules for BUY/SELL actions."""
    hypothesis_id = generate_uuid()

    # Valid BUY specification
    buy_spec = StrategySpecification(
        hypothesis_id=hypothesis_id,
        symbol="AAPL",
        action="BUY",
        entry_price=150.0,
        stop_loss_price=145.0,  # Below entry
        take_profit_price=165.0,  # Above entry
        position_size_pct=2.0,
    )
    assert buy_spec.action == "BUY"

    # Invalid BUY specification (Stop loss above entry)
    with pytest.raises(ValidationError) as exc_info:
        StrategySpecification(
            hypothesis_id=hypothesis_id,
            symbol="AAPL",
            action="BUY",
            entry_price=150.0,
            stop_loss_price=155.0,  # Invalid
            take_profit_price=165.0,
            position_size_pct=2.0,
        )
    assert "Stop loss must be lower than entry price for a BUY strategy" in str(exc_info.value)

    # Invalid BUY specification (Take profit below entry)
    with pytest.raises(ValidationError) as exc_info:
        StrategySpecification(
            hypothesis_id=hypothesis_id,
            symbol="AAPL",
            action="BUY",
            entry_price=150.0,
            stop_loss_price=145.0,
            take_profit_price=145.0,  # Invalid
            position_size_pct=2.0,
        )
    assert "Take profit must be higher than entry price for a BUY strategy" in str(exc_info.value)

    # Valid SELL specification
    sell_spec = StrategySpecification(
        hypothesis_id=hypothesis_id,
        symbol="AAPL",
        action="SELL",
        entry_price=150.0,
        stop_loss_price=155.0,  # Above entry
        take_profit_price=135.0,  # Below entry
        position_size_pct=1.5,
    )
    assert sell_spec.action == "SELL"

    # Invalid SELL specification (Stop loss below entry)
    with pytest.raises(ValidationError) as exc_info:
        StrategySpecification(
            hypothesis_id=hypothesis_id,
            symbol="AAPL",
            action="SELL",
            entry_price=150.0,
            stop_loss_price=145.0,  # Invalid
            take_profit_price=135.0,
            position_size_pct=1.5,
        )
    assert "Stop loss must be higher than entry price for a SELL strategy" in str(exc_info.value)


def test_trade_execution_receipt() -> None:
    """Test TradeExecutionReceipt instantiation."""
    strategy_id = generate_uuid()
    receipt = TradeExecutionReceipt(
        strategy_id=strategy_id,
        symbol="BTC/USD",
        fill_price=43000.0,
        filled_quantity=0.05,
        slippage=2.5,
        fees=15.0,
    )
    assert isinstance(receipt.execution_id, str)
    assert receipt.fill_price == 43000.0
    assert receipt.filled_quantity == 0.05
    assert receipt.slippage == 2.5
    assert receipt.fees == 15.0
    assert isinstance(receipt.executed_at, datetime)


def test_observation_report() -> None:
    """Test ObservationReport instantiation."""
    execution_id = generate_uuid()
    report = ObservationReport(
        execution_id=execution_id,
        actual_pnl=250.50,
        predicted_vs_actual_deviation=0.05,
        lessons_learned=["Execution was clean", "Slippage was lower than expected"],
    )
    assert isinstance(report.observation_id, str)
    assert report.execution_id == execution_id
    assert report.actual_pnl == 250.50
    assert report.predicted_vs_actual_deviation == 0.05
    assert len(report.lessons_learned) == 2


def test_performance_summary() -> None:
    """Test typed PerformanceSummary contract used between C7 and C8 (ADR-002/D2)."""
    summary = PerformanceSummary(
        total_trades=10, cumulative_pnl=1250.5, winning_trades=6, win_rate=60.0
    )
    assert summary.total_trades == 10
    assert summary.cumulative_pnl == 1250.5
    assert summary.winning_trades == 6
    assert summary.win_rate == 60.0

    empty = PerformanceSummary()
    assert empty.total_trades == 0
    assert empty.win_rate == 0.0
