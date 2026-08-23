"""Risk Firewall engine and models for validating strategy specifications in AIOS."""

import logging

from pydantic import BaseModel, Field

from schemas.contracts import StrategySpecification

logger = logging.getLogger(__name__)


class RiskConfig(BaseModel):
    """Configuration parameters for the Risk Firewall engine."""

    max_position_size_pct: float = Field(
        default=5.0,
        ge=0.0,
        le=100.0,
        description="Maximum allowed % of portfolio capital for a single trade",
    )
    max_stop_loss_pct: float = Field(
        default=5.0,
        ge=0.0,
        le=100.0,
        description="Maximum allowed stop loss distance from entry price percentage",
    )
    min_risk_reward_ratio: float = Field(
        default=1.5,
        gt=0.0,
        description="Minimum take-profit to stop-loss ratio required",
    )
    max_daily_drawdown_pct: float = Field(
        default=3.0,
        ge=0.0,
        le=100.0,
        description="Maximum allowed daily portfolio loss before emergency shutdown",
    )


class RiskEvaluationResult(BaseModel):
    """Result of risk evaluation for a proposed strategy."""

    is_approved: bool = Field(
        ..., description="Indicates whether the strategy passed risk evaluation"
    )
    rejection_reasons: list[str] = Field(
        default_factory=list,
        description="List of reasons for rejection if trade is not approved",
    )
    adjusted_position_size_pct: float = Field(
        ..., description="Final position size percentage after applying risk caps"
    )
    position_notional_value: float = Field(
        default=0.0,
        ge=0.0,
        description="Notional capital at risk derived from portfolio value and adjusted size",
    )
    emergency_shutdown_triggered: bool = Field(
        default=False,
        description="Indicates if emergency shutdown threshold was triggered",
    )


class RiskFirewall:
    """Risk Firewall Engine evaluating trading strategies against risk boundaries."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        """Initialize RiskFirewall with configuration.

        Args:
            config: RiskConfig instance. If None, default RiskConfig is used.
        """
        self.config = config if config is not None else RiskConfig()

    def evaluate_strategy(
        self,
        strategy: StrategySpecification,
        current_portfolio_value: float = 100000.0,
        current_daily_drawdown_pct: float = 0.0,
    ) -> RiskEvaluationResult:
        """Evaluate a strategy specification against risk rules.

        Evaluation Rules:
        1. Portfolio Sanity: If current_portfolio_value <= 0, reject with
           "Invalid portfolio value".
        2. Daily Drawdown Check: If current_daily_drawdown_pct >= config.max_daily_drawdown_pct,
           reject trade immediately, set emergency_shutdown_triggered = True, and append
           "Daily drawdown threshold exceeded".
        3. Stop-Loss Validation: Calculate stop-loss distance percentage abs(entry - stop_loss) / entry * 100.
           If > max_stop_loss_pct or stop-loss is missing/invalid, reject trade.
        4. Risk/Reward Ratio Check: Calculate abs(take_profit - entry) / abs(entry - stop_loss).
           If < min_risk_reward_ratio, reject trade.
        5. Position Size Adjustment: If strategy.position_size_pct > config.max_position_size_pct,
           cap adjusted_position_size_pct at max_position_size_pct and add a warning (do not reject if all other checks pass).
        The approved notional (portfolio_value * adjusted_size_pct / 100) is returned in
        position_notional_value for downstream sizing (defect D4 fix: the portfolio value
        parameter is now materially used).
        """
        rejection_reasons: list[str] = []

        # 1. Portfolio Sanity
        if current_portfolio_value <= 0:
            rejection_reasons.append("Invalid portfolio value")

        # 2. Daily Drawdown Check
        if current_daily_drawdown_pct >= self.config.max_daily_drawdown_pct:
            rejection_reasons.append("Daily drawdown threshold exceeded")
            return RiskEvaluationResult(
                is_approved=False,
                rejection_reasons=rejection_reasons,
                adjusted_position_size_pct=0.0,
                position_notional_value=0.0,
                emergency_shutdown_triggered=True,
            )

        # 2. Stop-Loss Validation
        if strategy.entry_price <= 0 or strategy.stop_loss_price <= 0:
            rejection_reasons.append("Invalid entry price or stop-loss price")
        else:
            stop_loss_dist_pct = (
                abs(strategy.entry_price - strategy.stop_loss_price) / strategy.entry_price * 100.0
            )
            if stop_loss_dist_pct > self.config.max_stop_loss_pct:
                rejection_reasons.append(
                    f"Stop-loss distance ({stop_loss_dist_pct:.2f}%) exceeds maximum allowed ({self.config.max_stop_loss_pct:.2f}%)"
                )

        # 3. Risk/Reward Ratio Check
        sl_distance = abs(strategy.entry_price - strategy.stop_loss_price)
        tp_distance = abs(strategy.take_profit_price - strategy.entry_price)
        if sl_distance == 0:
            rejection_reasons.append("Stop-loss price cannot equal entry price")
        else:
            risk_reward_ratio = tp_distance / sl_distance
            if risk_reward_ratio < self.config.min_risk_reward_ratio:
                rejection_reasons.append(
                    f"Risk/reward ratio ({risk_reward_ratio:.2f}) is below minimum required ({self.config.min_risk_reward_ratio:.2f})"
                )

        # 4. Position Size Adjustment
        adjusted_position_size_pct = strategy.position_size_pct
        if strategy.position_size_pct > self.config.max_position_size_pct:
            adjusted_position_size_pct = self.config.max_position_size_pct
            logger.warning(
                f"Position size {strategy.position_size_pct}% exceeds max position size "
                f"{self.config.max_position_size_pct}%. Capping position size."
            )

        is_approved = len(rejection_reasons) == 0
        adjusted_position_size_pct = adjusted_position_size_pct if is_approved else 0.0
        position_notional_value = round(
            current_portfolio_value * adjusted_position_size_pct / 100.0, 2
        )

        return RiskEvaluationResult(
            is_approved=is_approved,
            rejection_reasons=rejection_reasons,
            adjusted_position_size_pct=adjusted_position_size_pct,
            position_notional_value=position_notional_value,
            emergency_shutdown_triggered=False,
        )
