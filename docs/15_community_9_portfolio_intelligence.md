# AIOS Specification 1.15: Community 9 Specification (Portfolio Intelligence)

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification (Frozen)
- **Target System**: AIOS - Community 9 (Portfolio Intelligence & Allocation)
- **Author**: AIOS System Architecture Team

---

## 1. Community Purpose & Responsibilities

### 1.1 Primary Objective
Community 9 (C9) acts as the central portfolio risk manager, capital allocator, and correlation orchestrator for AIOS. While Community 4 (Strategy Generation) formulates individual trade strategies in isolation, Community 9 steps back to evaluate the portfolio as a holistic system.

Its primary objective is to dynamically allocate portfolio capital across active strategies, eliminate cross-strategy position correlation risks, optimize aggregate Sharpe ratio, and enforce portfolio-wide drawdown protection.

### 1.2 Core Responsibilities
- **Cross-Strategy Capital Allocation**: Dynamically allocate portfolio capital to approved strategy candidates based on Kelly Criterion, volatility parity, and historical Sharpe performance.
- **Cross-Asset Correlation Analysis**: Measure real-time correlation matrices across active strategies to prevent concentrated exposure (e.g. preventing simultaneous long BTC, long ETH, and long SOL positions that exceed portfolio concentration limits).
- **Total Portfolio Drawdown Management**: Continuously aggregate unrealized and realized PnL across all strategies to enforce system-wide portfolio drawdown limits.
- **Position Weight Optimization**: Rebalance strategy position weights dynamically as market volatility or regime conditions change.
- **Allocation Plan Publishing**: Output structured `PortfolioAllocationPlan` payloads to the event bus topic `aios.c9.portfolio_allocation`.

---

## 2. Agent Hierarchy & Roles

Community 9 operates four specialized portfolio management agents:

```
+-----------------------------------------------------------------------------------+
|               VERIFIED STRATEGIES INPUT (from C4 Strategy Generation)             |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                 CROSS-STRATEGY CAPITAL ALLOCATION AGENT                           |
|       (Applies Fractional Kelly & Volatility Parity sizing across strategies)     |
+-----------------------------------------------------------------------------------+
                                          |
     +------------------------------------+------------------------------------+
     |                                                                         |
     v                                                                         v
+------------------------------------+                       +------------------------------------+
|  CORRELATION & CONCENTRATION AGENT |                       | PORTFOLIO DRAWDOWN GUARD AGENT     |
| (Calculates cross-asset covariance) |                       | (Monitors aggregate PnL & caps)    |
+------------------------------------+                       +------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                 PORTFOLIO OPTIMIZATION & REBALANCING AGENT                        |
|            (Generates finalized PortfolioAllocationPlan payload)                  |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
                              Publish to Event Bus
```

### 2.1 Cross-Strategy Capital Allocation Agent
- **Role**: Computes baseline capital allocation for each active strategy candidate.
- **Methodology**: Uses Fractional Kelly Criterion ($f^* = 0.5 \cdot \frac{p \cdot b - q}{b}$) combined with inverse-variance volatility parity weighting.

### 2.2 Correlation & Concentration Agent
- **Role**: Monitors real-time asset covariance and returns correlation matrices.
- **Rules**:
  - **Pairwise Correlation Limit**: If two active strategies trade assets with correlation $\rho > 0.80$, aggregate exposure to the pair is capped at 10% total portfolio capital.
  - **Asset Class Limit**: Maximum capital allocated to a single asset class (e.g. Crypto, Tech Equities) is capped at 35% of total portfolio capital.

### 2.3 Portfolio Drawdown Guard Agent
- **Role**: Tracks holistic portfolio equity curve in real time.
- **Rules**:
  - **Portfolio Warning Tier (1.5% Drawdown)**: Scale down all strategy position sizes by 25%.
  - **Portfolio Caution Tier (2.5% Drawdown)**: Scale down all strategy position sizes by 50%. Pause new strategy activations.
  - **Portfolio Critical Breach (3.0% Drawdown)**: Trigger non-LLM Risk Firewall emergency shutdown. Halt all trading and panic-liquidate open positions.

### 2.4 Portfolio Optimization & Rebalancing Agent
- **Role**: Synthesizes inputs from allocation, correlation, and drawdown agents into a unified, actionable `PortfolioAllocationPlan`.

---

## 3. Output Schema & Event Bus Routing

### 3.1 Output Schema Definition
Community 9 outputs instances of `PortfolioAllocationPlan`:

```python
class StrategyAllocation(BaseModel):
    strategy_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    approved_position_size_pct: float = Field(..., ge=0.0, le=100.0)
    correlation_penalty_applied: bool = Field(default=False)
    allocation_notes: str = Field(...)

class PortfolioAllocationPlan(BaseModel):
    plan_id: str = Field(default_factory=generate_uuid)
    timestamp: datetime = Field(default_factory=generate_utc_now)
    allocations: list[StrategyAllocation] = Field(...)
    total_portfolio_exposure_pct: float = Field(..., ge=0.0, le=100.0)
    current_portfolio_drawdown_pct: float = Field(..., ge=0.0)
    portfolio_status: Literal["HEALTHY", "WARNING", "CAUTION", "CRITICAL_HALT"] = Field(...)
```

### 3.2 Event Bus Routing
- **Subscription Topics**: `strategy.generated` (`EventTopic.STRATEGY_GENERATED`), `trade.executed` (`EventTopic.TRADE_EXECUTED`).
- **Publication Topic**: `aios.c9.portfolio_allocation`.
- **Target Subscribers**: Continuous Training Environment, Community 5 (Live Trading Execution).

---

## 4. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/CHECKPOINT.md) under **Doc 1.15: Community 9 Specification (Portfolio Intelligence)**.
