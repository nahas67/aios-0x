# AIOS Specification 1.5: Community 4 Specification (Strategy Generation)

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification
- **Target System**: AIOS - Community 4 (Strategy Generation)
- **Author**: AIOS System Architecture Team

---

## 1. Community Purpose & Responsibilities

### 1.1 Primary Objective
Community 4 (C4) converts verified intelligence from Community 3 into precise, executable trading strategies. Each strategy specification defines unambiguous entry, stop-loss, take-profit, and position sizing parameters ready for deterministic risk validation and downstream execution.

### 1.2 Core Responsibilities
- **Asset & Timeframe Selection**: Match verified hypotheses to the optimal asset class and execution timeframe.
- **Entry/Exit Trigger Structuring**: Define exact price trigger levels for market entry, stop-loss placement, and take-profit targets.
- **Position Sizing & Capital Allocation**: Calculate the percentage of portfolio capital allocated to each trade based on volatility, conviction score, and risk budget.
- **Risk/Reward Optimization**: Ensure every strategy meets or exceeds the minimum risk-to-reward ratio ($R:R \ge 1.5$) enforced by the Risk Firewall.
- **Risk Firewall Submission**: Submit every candidate strategy to the deterministic `RiskFirewall.evaluate_strategy()` for approval before dispatching to execution.

---

## 2. Agent Hierarchy & Roles

Community 4 employs a pipeline of specialist agents coordinated in sequence:

```
+-----------------------------------------------------------------------------------+
|                     VERIFIED HYPOTHESIS INPUT (from C3)                           |
|                       [VerificationReport.is_verified = True]                     |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
               +--------------------------------------------+
               |     ASSET & TIMEFRAME SELECTOR AGENT       |
               | (Maps hypothesis to optimal asset/window)  |
               +--------------------------------------------+
                                          |
                                          v
               +--------------------------------------------+
               |      ENTRY / EXIT STRUCTURING AGENT        |
               | (Defines entry, stop-loss, take-profit)    |
               +--------------------------------------------+
                                          |
                                          v
               +--------------------------------------------+
               |  POSITION SIZING & CAPITAL ALLOCATION AGENT|
               | (Calculates position_size_pct allocation)  |
               +--------------------------------------------+
                                          |
                                          v
               +--------------------------------------------+
               |           RISK PROFILER AGENT              |
               | (Submits to RiskFirewall for approval)     |
               +--------------------------------------------+
                            |                     |
                     [APPROVED]              [REJECTED]
                            |                     |
                            v                     v
                  Publish to Bus         Log rejection to C7
```

### 2.1 Asset & Timeframe Selector Agent
- **Role**: Evaluates the verified hypothesis context and selects the appropriate trading symbol and execution timeframe.
- **Focus**: Cross-references the hypothesis symbol with available exchange instrument lists, validates market hours and liquidity windows, and aligns the timeframe with the thesis horizon (e.g., a `4h` thesis maps to a `4h` execution window).

### 2.2 Entry/Exit Structuring Agent
- **Role**: Translates the qualitative thesis into exact numeric order triggers.
- **Focus**:
  - **Entry Price**: Derived from current market levels, support/resistance zones, or indicator-based triggers.
  - **Stop-Loss Price**: Placed beyond the nearest invalidation level. For `BUY` strategies, stop-loss must be strictly below entry. For `SELL` strategies, stop-loss must be strictly above entry.
  - **Take-Profit Price**: Set at the thesis target level. For `BUY` strategies, take-profit must be strictly above entry. For `SELL` strategies, take-profit must be strictly below entry.

### 2.3 Position Sizing & Capital Allocation Agent
- **Role**: Determines the risk-adjusted allocation percentage for the trade.
- **Focus**: Calculates `position_size_pct` (0.0 to 100.0) based on:
  - Verification confidence score from C3.
  - Current portfolio exposure and open position count.
  - Implied volatility or ATR-based position scaling.

### 2.4 Risk Profiler Agent
- **Role**: Acts as the final gatekeeper within C4 by submitting the assembled `StrategySpecification` to the deterministic Risk Firewall.
- **Focus**: Invokes `RiskFirewall.evaluate_strategy()` and processes the `RiskEvaluationResult`:
  - **Approved**: Accepts the strategy (potentially with an adjusted `position_size_pct` cap) and publishes to the event bus.
  - **Rejected**: Logs rejection reasons and archives the failed strategy to Community 7 for post-mortem learning.

---

## 3. Strategy Structuring Rules & Risk Firewall Submission

### 3.1 Entry & Exit Conditions
Every `StrategySpecification` must define unambiguous price triggers:

| Parameter | Constraint | Description |
| :--- | :--- | :--- |
| `action` | `BUY` / `SELL` / `HOLD` | The directional trade action. |
| `entry_price` | `> 0.0` | The exact trigger price for entering the position. |
| `stop_loss_price` | `> 0.0`, directionally valid | Must be below entry for `BUY`, above entry for `SELL`. |
| `take_profit_price` | `> 0.0`, directionally valid | Must be above entry for `BUY`, below entry for `SELL`. |
| `position_size_pct` | `0.0` to `100.0` | Percentage of portfolio capital allocated. |

### 3.2 Mandatory Risk Parameters
- **Stop-Loss**: Every strategy MUST include a valid `stop_loss_price`. Strategies without stop-loss protection are rejected unconditionally.
- **Take-Profit**: Every strategy MUST include a valid `take_profit_price` defining the target exit.
- **Risk/Reward Ratio**: The ratio $R:R = \frac{|\text{take\_profit} - \text{entry}|}{|\text{entry} - \text{stop\_loss}|}$ must satisfy $R:R \ge 1.5$.

### 3.3 Risk Firewall Integration Protocol
Before any strategy is published to the event bus, it must pass through the deterministic `RiskFirewall`:

```python
class RiskFirewall:
    def evaluate_strategy(
        self,
        strategy: StrategySpecification,
        current_portfolio_value: float = 100000.0,
        current_daily_drawdown_pct: float = 0.0,
    ) -> RiskEvaluationResult:
        """
        Evaluation Rules:
        1. Daily Drawdown Check: If daily drawdown >= max_daily_drawdown_pct (default 3.0%),
           reject immediately with emergency_shutdown_triggered = True.
        2. Stop-Loss Validation: If stop-loss distance > max_stop_loss_pct (default 5.0%),
           reject the strategy.
        3. Risk/Reward Ratio: If R:R < min_risk_reward_ratio (default 1.5), reject.
        4. Position Size Cap: If position_size_pct > max_position_size_pct (default 5.0%),
           cap at max (warn, do not reject if all other checks pass).
        """
```

| Risk Check | Default Threshold | Outcome on Failure |
| :--- | :---: | :--- |
| Daily Drawdown | `3.0%` | Immediate rejection, `emergency_shutdown_triggered = True` |
| Stop-Loss Distance | `5.0%` | Rejection with reason logged |
| Risk/Reward Ratio | `1.5` | Rejection with reason logged |
| Position Size Cap | `5.0%` | Capped (warning only, not a rejection) |

---

## 4. Output Schema & Event Bus Routing

### 4.1 Output Schema Definition
Community 4 outputs instances of `StrategySpecification` defined in `schemas/contracts.py`:

```python
class StrategySpecification(BaseModel):
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
        description="Percentage of total portfolio risk allocated (0.0 to 100.0)"
    )

    @model_validator(mode="after")
    def validate_price_levels(self) -> "StrategySpecification":
        """Validate stop-loss and take-profit consistency with action type."""
        if self.action == "BUY":
            if self.stop_loss_price >= self.entry_price:
                raise ValueError("Stop loss must be lower than entry for BUY")
            if self.take_profit_price <= self.entry_price:
                raise ValueError("Take profit must be higher than entry for BUY")
        elif self.action == "SELL":
            if self.stop_loss_price <= self.entry_price:
                raise ValueError("Stop loss must be higher than entry for SELL")
            if self.take_profit_price >= self.entry_price:
                raise ValueError("Take profit must be lower than entry for SELL")
        return self
```

### 4.2 Event Bus Routing
- **Subscription Topic**: `verification.completed` (`EventTopic.VERIFICATION_COMPLETED`).
- **Publication Topic**: `strategy.generated` (`EventTopic.STRATEGY_GENERATED`).
- **Target Subscribers**: Continuous Training Environment (paper/backtest engine), Community 5 (Live Execution — gated by Risk Firewall approval).

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/CHECKPOINT.md) under **Doc 1.5: Community 4 Specification (Strategy Generation)**. The Risk Firewall implementation resides in `core/risk_firewall.py` with unit tests in `tests/test_risk_firewall.py`.
