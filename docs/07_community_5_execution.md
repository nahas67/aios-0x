# AIOS Specification 1.7: Community 5 Specification (Live Trading Execution)

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification
- **Target System**: AIOS - Community 5 (Live Trading Execution)
- **Author**: AIOS System Architecture Team

---

## 1. Community Purpose & Responsibilities

### 1.1 Primary Objective
Community 5 (C5) is responsible for the safe, reliable execution of approved trading strategies on live exchanges and brokers. It manages the full order lifecycle from submission through fill confirmation, maintains real-time position awareness, and enforces emergency liquidation protocols when risk boundaries are breached.

### 1.2 Core Responsibilities
- **Order Routing**: Route structured order payloads to target exchanges or brokers via their respective API gateways (CCXT unified interface, Alpaca, Interactive Brokers).
- **Execution Optimization**: Break down large orders using TWAP (Time-Weighted Average Price) and VWAP (Volume-Weighted Average Price) algorithms to minimize market impact and slippage.
- **Real-Time Position Tracking**: Continuously monitor open positions, margin utilization, unrealized PnL, and unfulfilled order states across all connected venues.
- **Exchange API Rate-Limit Management**: Respect per-exchange rate limits, implement adaptive throttling, and queue excess requests to avoid API bans.
- **Emergency Liquidation Execution**: Execute automated panic liquidation procedures upon daily drawdown breach signals or exchange connectivity loss.

---

## 2. Agent Hierarchy & Roles

Community 5 employs a layered execution architecture with safety overrides:

```
+-----------------------------------------------------------------------------------+
|                  APPROVED STRATEGY INPUT (from Risk Firewall)                     |
|               [StrategySpecification + RiskEvaluationResult.is_approved]           |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
               +--------------------------------------------+
               |          ORDER ROUTING AGENT                |
               | (Selects exchange, constructs order)        |
               +--------------------------------------------+
                                          |
                                          v
               +--------------------------------------------+
               |      EXECUTION OPTIMIZATION AGENT           |
               | (TWAP/VWAP slicing, iceberg orders)         |
               +--------------------------------------------+
                                          |
                                          v
               +--------------------------------------------+
               |    POSITION & ACCOUNT MONITOR AGENT         |
               | (Tracks fills, margin, open positions)      |
               +--------------------------------------------+
                                          |
                                          v
                              [TradeExecutionReceipt]
                                          |
                                          v
                              Publish to Event Bus

        +-------------------------------------------------------+
        |          EMERGENCY KILL-SWITCH AGENT                   |
        | (Listens for risk breach / exchange disconnect)        |
        | (Cancels all open orders, closes all positions)        |
        +-------------------------------------------------------+
                    ^                           ^
                    |                           |
         [Risk Firewall Signal]       [Exchange Disconnect]
```

### 2.1 Order Routing Agent
- **Role**: Receives approved `StrategySpecification` payloads and translates them into exchange-specific order requests.
- **Focus**:
  - Maps AIOS unified symbols (e.g. `BTC/USD`) to exchange-native instrument identifiers.
  - Selects the optimal execution venue based on available liquidity, spread, and fee tier.
  - Constructs order type (market, limit, stop-limit) based on strategy parameters and current market distance from entry price.

### 2.2 Execution Optimization Agent
- **Role**: Minimizes market impact for orders that represent significant volume relative to the order book.
- **Focus**:
  - **TWAP**: Splits the order into equal-sized child orders executed at fixed time intervals.
  - **VWAP**: Distributes child order sizes proportionally to expected volume profiles across the execution window.
  - **Iceberg Orders**: Reveals only a fraction of total order size to the order book at any time.
- **Threshold**: Orders exceeding 1% of the 24-hour average volume for the instrument trigger automatic slicing.

### 2.3 Position & Account Monitor Agent
- **Role**: Maintains a real-time ledger of all open positions, pending orders, and account balances across connected exchanges.
- **Focus**:
  - Tracks partial fills and aggregates them into composite execution receipts.
  - Monitors margin utilization and available buying power.
  - Detects orphaned orders (submitted but never acknowledged) and triggers re-submission or cancellation after a configurable timeout (default: 30 seconds).

### 2.4 Emergency Kill-Switch Agent
- **Role**: The ultimate safety override within C5. Operates independently of all other agents and cannot be disabled by LLM logic.
- **Focus**:
  - Listens for `emergency_shutdown_triggered = True` signals from `RiskEvaluationResult`.
  - Monitors exchange WebSocket heartbeat — triggers cancel-all if heartbeat is lost for more than 5 seconds.
  - Executes a hardcoded three-step panic liquidation protocol (see Section 3.3).

---

## 3. Exchange API Gateway & Safety Protocols

### 3.1 Connection & Resilience
All exchange connectivity follows strict resilience rules:

| Protocol | Requirement |
| :--- | :--- |
| **Primary Channel** | WebSocket for real-time order updates, fills, and account state. |
| **Fallback Channel** | REST API polling at 1-second intervals when WebSocket is unavailable. |
| **Heartbeat Monitoring** | Exchange WebSocket heartbeat must be received within 5-second intervals. |
| **Cancel on Disconnect** | All open orders are automatically cancelled if WebSocket connection is lost and cannot be re-established within 10 seconds. |
| **Reconnection Strategy** | Exponential backoff: 1s → 2s → 4s → 8s → 16s → max 30s, with jitter. |
| **Session Authentication** | API keys loaded exclusively via `pydantic-settings` environment models. Never hardcoded. |

### 3.2 Rate Limiting & Error Handling

#### Rate Limit Management
| Exchange Category | Default Rate Limit | AIOS Safety Margin |
| :--- | :---: | :---: |
| Crypto (Binance/Coinbase) | 1200 req/min | 80% utilization cap (960 req/min) |
| Equities (Alpaca) | 200 req/min | 80% utilization cap (160 req/min) |
| Forex (OANDA) | 120 req/min | 80% utilization cap (96 req/min) |

#### Error Handling Protocol
- **Order Acknowledgement**: Every submitted order must receive an exchange acknowledgement (order ID) within 5 seconds. If no acknowledgement, the order is treated as failed and retried once.
- **Exchange Error Codes**: Map exchange-specific error codes to AIOS-internal error categories:
  - `INSUFFICIENT_FUNDS` → Cancel order, alert C6 (Observation).
  - `RATE_LIMIT_EXCEEDED` → Back off for 60 seconds, re-queue order.
  - `INSTRUMENT_HALTED` → Cancel order, log to C7 (Memory), alert C6.
  - `UNKNOWN_ERROR` → Cancel order, log full error payload, alert C6.
- **Retry Strategy**: Maximum 2 retries with exponential backoff (1s → 3s). If all retries fail, the order is abandoned and a failure record is published to Community 6.

### 3.3 Emergency Kill-Switch Protocol
When triggered, the Kill-Switch Agent executes the following hardcoded, non-overridable procedure:

```
EMERGENCY KILL-SWITCH PROCEDURE (NON-LLM, DETERMINISTIC)
=========================================================
Step 1: CANCEL ALL OPEN ORDERS
   - Issue cancel-all on every connected exchange.
   - Verify cancellation acknowledgement within 5 seconds.
   - If any cancel fails, retry once, then force-close via market order.

Step 2: CLOSE ALL OPEN POSITIONS
   - Submit market sell/cover orders for every open long position.
   - Submit market buy/cover orders for every open short position.
   - Use aggressive market orders — no limit orders during emergency.

Step 3: LOCK & REPORT
   - Set system state to EMERGENCY_LOCKOUT.
   - Reject all new strategy submissions until manual operator review.
   - Publish emergency report to C6 (Observation) and C7 (Memory).
   - Send critical alert notification (email/webhook/Slack).
```

**Kill-Switch Triggers**:
- `RiskEvaluationResult.emergency_shutdown_triggered = True` (daily drawdown exceeded).
- WebSocket heartbeat lost on all connected exchanges simultaneously.
- Manual operator kill-switch activation.

---

## 4. Output Schema & Event Bus Routing

### 4.1 Output Schema Definition
Community 5 outputs live `TradeExecutionReceipt` instances defined in `schemas/contracts.py`:

```python
class TradeExecutionReceipt(BaseModel):
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
        description="Price slippage encountered during execution"
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
```

### 4.2 Metadata Distinction from Paper Trading
Live execution receipts are distinguished from paper/simulated receipts by metadata:
- `source: "live_execution"`
- `is_simulated: False`
- `exchange: "<exchange_name>"` (e.g. `"binance"`, `"alpaca"`)
- `exchange_order_id: "<native_order_id>"`

### 4.3 Event Bus Routing
- **Subscription Topic**: `strategy.generated` (`EventTopic.STRATEGY_GENERATED`) — only for strategies that have been promoted through the Continuous Training Environment.
- **Publication Topic**: `trade.executed` (`EventTopic.TRADE_EXECUTED`).
- **Target Subscribers**: Community 6 (Observation & Audit), Community 7 (Memory Architecture).

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/CHECKPOINT.md) under **Doc 1.7: Community 5 Specification (Live Trading Execution)**. Emergency kill-switch thresholds align with `RiskConfig.max_daily_drawdown_pct` in [risk_firewall.py](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/core/risk_firewall.py). API credentials must follow the secrets management rules defined in [.cursorrules](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/.cursorrules).
