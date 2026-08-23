"""Unit tests for the Risk Firewall module in core/risk_firewall.py."""

import pytest
from schemas.contracts import generate_uuid, StrategySpecification
from core.risk_firewall import RiskConfig, RiskEvaluationResult, RiskFirewall


def test_valid_strategy_passes_evaluation() -> None:
    """Test that a valid strategy passes evaluation successfully."""
    config = RiskConfig()
    firewall = RiskFirewall(config)

    # Entry: 100.0, SL: 97.0 (3.0% dist <= 5.0%), TP: 106.0 (6.0% dist, R:R = 2.0 >= 1.5), Pos size: 3.0% (<= 5.0%)
    strategy = StrategySpecification(
        hypothesis_id=generate_uuid(),
        symbol="BTC/USD",
        action="BUY",
        entry_price=100.0,
        stop_loss_price=97.0,
        take_profit_price=106.0,
        position_size_pct=3.0,
    )

    result = firewall.evaluate_strategy(
        strategy=strategy,
        current_portfolio_value=100000.0,
        current_daily_drawdown_pct=1.0,
    )

    assert isinstance(result, RiskEvaluationResult)
    assert result.is_approved is True
    assert result.rejection_reasons == []
    assert result.adjusted_position_size_pct == 3.0
    assert result.emergency_shutdown_triggered is False


def test_rejection_wide_stop_loss() -> None:
    """Test rejection when stop-loss distance is too wide (e.g. 10%)."""
    config = RiskConfig(max_stop_loss_pct=5.0)
    firewall = RiskFirewall(config)

    # Entry: 100.0, SL: 90.0 (10.0% dist > 5.0%), TP: 120.0 (20.0% dist, R:R = 2.0)
    strategy = StrategySpecification(
        hypothesis_id=generate_uuid(),
        symbol="ETH/USD",
        action="BUY",
        entry_price=100.0,
        stop_loss_price=90.0,
        take_profit_price=120.0,
        position_size_pct=2.0,
    )

    result = firewall.evaluate_strategy(
        strategy=strategy,
        current_portfolio_value=100000.0,
        current_daily_drawdown_pct=0.5,
    )

    assert result.is_approved is False
    assert len(result.rejection_reasons) > 0
    assert any("Stop-loss distance" in reason for reason in result.rejection_reasons)
    assert result.emergency_shutdown_triggered is False


def test_rejection_low_risk_reward_ratio() -> None:
    """Test rejection when risk/reward ratio is below 1.5."""
    config = RiskConfig(min_risk_reward_ratio=1.5)
    firewall = RiskFirewall(config)

    # Entry: 100.0, SL: 97.0 (3.0% dist), TP: 103.0 (3.0% dist -> R:R = 1.0 < 1.5)
    strategy = StrategySpecification(
        hypothesis_id=generate_uuid(),
        symbol="AAPL",
        action="BUY",
        entry_price=100.0,
        stop_loss_price=97.0,
        take_profit_price=103.0,
        position_size_pct=2.0,
    )

    result = firewall.evaluate_strategy(
        strategy=strategy,
        current_portfolio_value=100000.0,
        current_daily_drawdown_pct=0.0,
    )

    assert result.is_approved is False
    assert len(result.rejection_reasons) > 0
    assert any("Risk/reward ratio" in reason for reason in result.rejection_reasons)
    assert result.emergency_shutdown_triggered is False


def test_position_size_capped_at_max() -> None:
    """Test trade approval with position size automatically capped at 5%."""
    config = RiskConfig(max_position_size_pct=5.0)
    firewall = RiskFirewall(config)

    # Valid trade parameters except position_size_pct is 10.0% (> 5.0%)
    strategy = StrategySpecification(
        hypothesis_id=generate_uuid(),
        symbol="NVDA",
        action="BUY",
        entry_price=100.0,
        stop_loss_price=97.0,
        take_profit_price=106.0,
        position_size_pct=10.0,
    )

    result = firewall.evaluate_strategy(
        strategy=strategy,
        current_portfolio_value=100000.0,
        current_daily_drawdown_pct=1.5,
    )

    assert result.is_approved is True
    assert result.rejection_reasons == []
    assert result.adjusted_position_size_pct == 5.0
    assert result.emergency_shutdown_triggered is False


def test_emergency_shutdown_daily_drawdown() -> None:
    """Test emergency shutdown trigger when daily drawdown is >= 3%."""
    config = RiskConfig(max_daily_drawdown_pct=3.0)
    firewall = RiskFirewall(config)

    strategy = StrategySpecification(
        hypothesis_id=generate_uuid(),
        symbol="SOL/USD",
        action="BUY",
        entry_price=100.0,
        stop_loss_price=98.0,
        take_profit_price=105.0,
        position_size_pct=2.0,
    )

    result = firewall.evaluate_strategy(
        strategy=strategy,
        current_portfolio_value=100000.0,
        current_daily_drawdown_pct=3.0,  # Exact threshold trigger
    )

    assert result.is_approved is False
    assert result.emergency_shutdown_triggered is True
    assert "Daily drawdown threshold exceeded" in result.rejection_reasons
    assert result.adjusted_position_size_pct == 0.0
