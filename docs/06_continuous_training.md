# AIOS Specification 1.6: Continuous Training & Validation Environment

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification
- **Target System**: AIOS - Continuous Training & Validation Environment
- **Author**: AIOS System Architecture Team

---

## 1. Environment Purpose & Responsibilities

### 1.1 Primary Objective
The Continuous Training & Validation Environment is a zero-capital-risk sandbox that trains, tests, evaluates, and benchmarks all AI agents and strategies before they are promoted to live market deployment via Community 5. No strategy may enter live execution without first passing through this environment's promotion gateway.

### 1.2 Core Responsibilities
- **Live Paper Trading Simulation**: Execute strategy orders in real-time against live market feeds with realistic slippage models, exchange fee schedules, and latency simulation — without risking actual capital.
- **Walk-Forward Historical Analysis**: Run out-of-sample backtests across rolling historical windows to detect curve-fitting and over-optimization.
- **Historical Market Replay**: Replay specific high-impact market events (flash crashes, CPI releases, FOMC announcements) at tick-level fidelity to stress-test strategy behavior.
- **Synthetic Market Stress Testing**: Generate artificial adversarial scenarios (liquidity crunches, extreme gapping, correlated sell-offs) to probe strategy resilience under tail-risk conditions.
- **Agent Performance Benchmarking**: Track and compare agent-level metrics across strategies, timeframes, and market regimes to inform Community 8 (Evolution) decisions.

---

## 2. Core Components & Architecture

```
+-----------------------------------------------------------------------------------+
|                   CONTINUOUS TRAINING & VALIDATION ENVIRONMENT                     |
+-----------------------------------------------------------------------------------+
                                          |
     +-------------------+---------------+---------------+-------------------+
     |                   |                               |                   |
     v                   v                               v                   v
[Paper Trading      [Walk-Forward         [Historical Market     [Synthetic Stress
 Engine]             Historical Engine]     Replay Engine]         Simulator]
                                          |
                                          v
                          +-------------------------------+
                          |   EVALUATION & PROMOTION      |
                          |         GATEWAY               |
                          | (Benchmark Scoring & Gating)  |
                          +-------------------------------+
                               |                |
                        [PROMOTED]          [DEMOTED]
                               |                |
                               v                v
                          C5 (Live)       C7/C8 (Memory/Evolution)
```

### 2.1 Live Paper Trading Engine
- **Function**: Receives `StrategySpecification` events that have passed the Risk Firewall and executes simulated orders against live streaming market data from Community 1.
- **Slippage Model**: Applies configurable slippage (default: 0.05% of fill price) and exchange fee schedules (default: maker 0.1%, taker 0.15%).
- **Latency Simulation**: Introduces artificial order-to-fill latency (configurable, default: 50–200ms uniform random) to model real-world execution delays.
- **Output**: Generates `TradeExecutionReceipt` instances with simulated `fill_price`, `slippage`, and `fees` fields.

### 2.2 Walk-Forward Historical Engine
- **Function**: Partitions historical data into sequential train/test windows and runs the strategy on each out-of-sample test window.
- **Window Configuration**:
  - Training window: 90 calendar days (default).
  - Test window: 30 calendar days (default).
  - Step size: 30 calendar days (rolling forward).
- **Over-Fit Detection**: If in-sample Sharpe Ratio exceeds out-of-sample Sharpe by more than 50%, the strategy is flagged as potentially over-fitted and blocked from promotion.

### 2.3 Historical Market Replay Engine
- **Function**: Replays tick-by-tick or bar-by-bar historical data from specific high-volatility events at original market speed or accelerated replay rates.
- **Event Library** (expandable):
  - Flash Crash (May 6, 2010 — equity)
  - COVID-19 Sell-Off (March 2020 — multi-asset)
  - FTX Collapse (November 2022 — crypto)
  - Silicon Valley Bank Failure (March 2023 — banking/macro)
  - CPI Surprise Release scenarios (synthetic templates)
- **Evaluation**: Strategy must demonstrate controlled drawdown and proper stop-loss execution during replay events. Strategies that exceed 2× their configured stop-loss distance during replay are flagged as structurally fragile.

### 2.4 Synthetic Market Stress Simulator
- **Function**: Generates artificial adversarial market conditions that may not exist in historical records.
- **Stress Scenarios**:
  - **Liquidity Crunch**: Simulates order book thinning with 5–10× normal slippage and partial fills.
  - **Extreme Gapping**: Introduces price gaps of 5–15% between consecutive bars with no intermediate fills available.
  - **Correlated Sell-Off**: Simultaneously drops all correlated assets by 10–20% to test portfolio-level risk.
  - **Whipsaw Noise**: Injects rapid price reversals within a single bar to test stop-loss hunting resilience.
- **Pass Criteria**: Strategy must survive all synthetic stress scenarios without exceeding the configured `max_daily_drawdown_pct` (default 3.0%) from `RiskConfig`.

---

## 3. Evaluation Metrics & Strategy Promotion Gateways

### 3.1 Benchmark Criteria
Every strategy must meet or exceed the following quantitative thresholds across its paper trading validation window before promotion to live execution:

| Metric | Minimum Threshold | Description |
| :--- | :---: | :--- |
| **Sharpe Ratio** | `> 1.5` | Risk-adjusted return measure (annualized). |
| **Maximum Drawdown** | `< 10.0%` | Largest peak-to-trough portfolio decline during the test period. |
| **Win Rate** | `> 55.0%` | Percentage of trades that are profitable. |
| **Profit Factor** | `> 1.3` | Ratio of gross profits to gross losses. |
| **Walk-Forward Consistency** | Out-of-sample Sharpe within 50% of in-sample | Validates the strategy is not over-fitted. |
| **Stress Test Survival** | All synthetic scenarios passed | No scenario exceeds daily drawdown cap. |

### 3.2 Promotion Workflow
The lifecycle of a strategy through the training environment follows a strict, gated pipeline:

```
+---------------------------+     +---------------------------+     +---------------------------+
|   STRATEGY CANDIDATE      | --> |  PAPER TESTING WINDOW     | --> |  LIVE TRADING CANDIDATE   |
| (From C4 via Risk FW)     |     | (Min 14 calendar days)    |     | (Promoted to C5)          |
+---------------------------+     +---------------------------+     +---------------------------+
                                         |
                                  [BENCHMARK MET?]
                                   /           \
                                 YES            NO
                                  |              |
                                  v              v
                           [PROMOTE]      [DEMOTE / RETIRE]
```

- **Minimum Validation Window**: 14 calendar days of paper trading with a minimum of 20 simulated trades.
- **Promotion Decision**: All benchmark criteria must be simultaneously satisfied. Partial compliance does not qualify.
- **Promotion Record**: Upon promotion, a promotion event is logged to Community 7 (Memory) containing the full benchmark scorecard.

### 3.3 Strategy Demotion & Retirement Rules
Strategies already promoted to live trading are subject to continuous rolling evaluation:
- **Rolling Review Window**: 30 calendar days of live trading performance.
- **Demotion Trigger**: If any single benchmark metric falls below its threshold for two consecutive review windows, the strategy is automatically demoted back to paper trading status.
- **Retirement Trigger**: If a demoted strategy fails to recover benchmark compliance within one additional paper trading validation window (14 days), it is permanently retired and archived to Community 7 with a full post-mortem record for Community 8 (Evolution) analysis.

---

## 4. Output Schema & Event Bus Routing

### 4.1 Output Schema Definition
The Continuous Training Environment generates simulated `TradeExecutionReceipt` instances defined in `schemas/contracts.py`:

```python
class TradeExecutionReceipt(BaseModel):
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
    slippage: float = Field(..., ge=0.0, description="Price slippage encountered during execution")
    fees: float = Field(..., ge=0.0, description="Execution and transaction fees incurred")
    executed_at: datetime = Field(
        default_factory=generate_utc_now, description="UTC datetime when the execution took place"
    )
```

### 4.2 Event Bus Routing
- **Subscription Topic**: `strategy.generated` (`EventTopic.STRATEGY_GENERATED`).
- **Publication Topic**: `trade.executed` (`EventTopic.TRADE_EXECUTED`).
- **Target Subscribers**: Community 6 (Observation & Audit) for performance tracking, Community 7 (Memory) for historical record indexing.

### 4.3 Metadata Tagging
All simulated `TradeExecutionReceipt` payloads generated by the training environment are tagged with execution context metadata to distinguish them from live trades:
- `source: "paper_trading" | "walk_forward" | "market_replay" | "stress_test"`
- `is_simulated: True`

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](CHECKPOINT.md) under **Doc 1.6: Continuous Training Environment Specification**. Risk thresholds align with `RiskConfig` defaults in [risk_firewall.py](core/risk_firewall.py).
