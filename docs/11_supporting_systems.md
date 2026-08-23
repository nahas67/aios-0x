# AIOS Specification 1.11: Supporting Systems Specification (Risk, Validation, & Infrastructure)

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification
- **Target System**: AIOS - Supporting Systems (Validation, Risk, & Infrastructure)
- **Author**: AIOS System Architecture Team

---

## 1. System Purpose & Architecture

### 1.1 Overview
Supporting Systems form the non-intelligence foundational wrapper of AIOS. They wrap around all 8 specialized communities to provide deterministic risk controls, multi-tier validation environments, model gateway abstractions, database persistence, event message routing, observability, and security.

### 1.2 Non-Interference Architecture Principle
Supporting systems enforce system safety, data integrity, and operational observability **without modifying or interfering with the internal reasoning flows of the AI agent communities**. 

```
+-----------------------------------------------------------------------------------+
|                            AIOS SUPPORTING SYSTEMS WRAPPER                        |
+-----------------------------------------------------------------------------------+
|  [VAL] Validation Layer (Backtest, Walk-Forward, Replay, Stress Test)            |
|  [RISK] Deterministic Risk Layer (Non-LLM Firewall, Drawdown Caps, Kill-Switch)  |
|  [INFRA] Infrastructure Layer (Model Gateway, Databases, Bus, Observability, Vault)|
+-----------------------------------------------------------------------------------+
                                          |
            Wraps around & enforces guardrails without altering agent logic
                                          v
+-----------------------------------------------------------------------------------+
|               AI AGENT COMMUNITIES (C1 -> C2 -> C3 -> C4 -> C5 -> C6 -> C7 -> C8) |
+-----------------------------------------------------------------------------------+
```

---

## 2. Validation Layer Architecture

The Validation Layer ensures that strategies are rigorously evaluated across multiple temporal and synthetic dimensions before qualifying for live execution.

### 2.1 Historical Backtesting Engine
- **Purpose**: Conduct long-horizon backtests over multi-year historical datasets to establish baseline performance metrics.
- **Capabilities**: Event-driven execution model, bar-by-bar evaluation, tick-level fill simulation, commission/fee schedules, and realistic slippage modeling.
- **Metrics Generated**: Cumulative PnL, Sharpe Ratio, Sortino Ratio, Max Drawdown, Calmar Ratio, Win Rate, Profit Factor, and Average Trade Duration.

### 2.2 Walk-Forward Testing Framework
- **Purpose**: Prevent over-fitting and curve-fitting by enforcing strict out-of-sample evaluation.
- **Methodology**: Rolling window strategy evaluation (e.g. 90-day in-sample training window followed by a 30-day out-of-sample testing window, stepped forward iteratively).
- **Validation Rule**: Out-of-sample Sharpe Ratio must stay within 50% of in-sample Sharpe Ratio; otherwise, the strategy is flagged for over-fitting.

### 2.3 Live Paper Trading Engine
- **Purpose**: Zero-capital-risk live simulation operating on live market feeds from Community 1.
- **Execution Fidelity**: Simulates real exchange order matching with injected latency (50–200ms), partial fills, and realistic market impact.
- **Required Duration**: Minimum 14 calendar days of paper trading with 20+ executed trades required for strategy promotion consideration.

### 2.4 Historical Market Replay Engine
- **Purpose**: High-fidelity replay of specific historical market crises and volatility spikes.
- **Library of Replay Events**:
  - May 2010 Equity Flash Crash
  - March 2020 COVID Liquidity Crisis
  - November 2022 FTX Liquidity Collapse
  - March 2023 SVB Banking Crisis
  - High-impact FOMC / CPI surprise releases
- **Passing Rule**: Strategy must execute stop-losses cleanly without exceeding 2× target stop distance during extreme replay volatility.

### 2.5 Synthetic Market Stress Simulator
- **Purpose**: Monte Carlo and synthetic stress generation testing strategy resilience against scenarios not present in historical data.
- **Stress Vectors**:
  - **Spread Widening**: Injects 5–10× bid-ask spreads during simulated order fills.
  - **Price Gapping**: Introduces sudden 5–15% gaps between consecutive price ticks.
  - **Correlated Volatility**: Simultaneously increases cross-asset correlation to 1.0 during sell-offs.
  - **Order Book Thinning**: Simulates 90% depth reduction in order books.

---

## 3. Deterministic Risk Layer (Non-LLM Circuit Breaker)

The Risk Layer (`RiskFirewall` in `core/risk_firewall.py`) operates as an unyielding, rule-based, non-LLM circuit breaker. AI agents cannot bypass or override this layer.

```
+-----------------------------------------------------------------------------------+
|                        DETERMINISTIC RISK FIREWALL (NON-LLM)                      |
+-----------------------------------------------------------------------------------+
   Check 1: Daily Drawdown Cap (default: max 3.0% daily loss limit)
   Check 2: Hard Position Size Limit (default: max 5.0% portfolio allocation)
   Check 3: Stop-Loss Distance Limit (default: max 5.0% distance from entry)
   Check 4: Minimum Risk/Reward Ratio (default: min 1.5 R:R)
   Check 5: Emergency Panic Liquidation Kill Switch
+-----------------------------------------------------------------------------------+
```

### 3.1 Hard Position Limits
- **Single Trade Cap**: `max_position_size_pct` defaults to **5.0%** of total portfolio capital. Position sizing requests exceeding this threshold are automatically capped by `RiskFirewall`.
- **Max Stop Loss Distance**: `max_stop_loss_pct` defaults to **5.0%** from entry price. Orders proposing wider stop-loss margins are rejected.

### 3.2 Portfolio Exposure & Concentration Controls
- **Max Open Positions**: Hard limit on maximum concurrent open positions per asset class (default: 5 positions max).
- **Correlated Exposure Cap**: Aggregated exposure across highly correlated assets (e.g. BTC + ETH) capped at 15% total portfolio capital.

### 3.3 Daily Drawdown Protection
- **Threshold**: `max_daily_drawdown_pct` defaults to **3.0%** daily loss limit.
- **Automatic Enforcement**: If cumulative daily loss reaches or exceeds 3.0%, `RiskFirewall` immediately halts all trading for the remainder of the trading day, triggers `emergency_shutdown_triggered = True`, and prevents new order submissions.

### 3.4 Emergency Panic Liquidation Kill Switch
- **Hardcoded Protocol**:
  1. Instantly issue cancel-all commands for all open limit/stop orders across all exchanges.
  2. Issue aggressive market orders to close all open positions across all connected venues.
  3. Lock system state to `EMERGENCY_LOCKOUT` and require explicit operator intervention to reset.
- **Trigger Conditions**: Daily drawdown breach, total WebSocket disconnect (> 10s), or manual emergency override.

---

## 4. Infrastructure Layer Specifications

### 4.1 AI Model Gateway Abstraction
- **Unified Interface**: Integrates `litellm` / standard model router interface to decouple community agents from specific LLM providers.
- **Provider Support**: OpenAI (GPT-4o, o3-mini), Anthropic (Claude 3.5 Sonnet), Google (Gemini 1.5/2.0), and local models (Ollama, vLLM via OpenAI-compatible endpoints).
- **Resilience Controls**: Automatic failover routing (e.g. primary Claude 3.5 Sonnet → fallback GPT-4o on provider rate limit / 5xx error), request retries with exponential backoff, and token usage tracking.

### 4.2 Database Architecture
The database stack supports four specialized access patterns:

| Subsystem | Technology | Storage Focus |
| :--- | :--- | :--- |
| **Relational Audit Store** | PostgreSQL 16+ (SQLite for local prototype) | Trade records, verification reports, strategy specs, execution receipts, audit logs. |
| **Time-Series Store** | TimescaleDB | Raw price ticks, OHLCV bars, indicator values, slippage logs, equity curves. |
| **Semantic Vector Memory** | Qdrant | Vector embeddings (768-dim) of research theses, debate transcripts, post-mortem lessons. |
| **Short-Term Cache & Buffer**| Redis 7+ | Session state, rate-limit counters, streaming pub/sub message buffers, locks. |

### 4.3 Message Bus Architecture
- **Local Prototype Mode**: `InMemoryEventBus` backed by `asyncio.Queue` with `wait_until_idle()` synchronization.
- **Enterprise Production Mode**: NATS JetStream or Redis Streams topic hierarchy.
- **Topic Hierarchy**: Standardized naming convention (`aios.<community>.<event_type>`).

### 4.4 Observability & Monitoring
- **Distributed Tracing**: OpenTelemetry instrumentation tracking event propagation across community handlers.
- **LLM Observability**: Integration with LangFuse / Arize Phoenix for tracking LLM prompt templates, token consumption, latency, and cost per community.
- **System Metrics**: Prometheus exporter exposing metrics scraped by Grafana dashboards:
  - Event bus queue depth and processing latency.
  - Active position count and daily drawdown % gauge.
  - Risk Firewall approval/rejection rates.
  - LLM API error rate and latency percentiles (p50, p95, p99).

### 4.5 Security & Vault Specifications
- **Secrets Management**: Credentials loaded exclusively from environment variables via `pydantic-settings` models. Hardcoded secrets are strictly forbidden.
- **API Key Encryption**: Exchange API keys and secrets encrypted at rest using AES-256-GCM.
- **Immutable Audit Logging**: Every event published to the event bus and every risk evaluation decision is written to an immutable append-only database table for compliance auditing.

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/CHECKPOINT.md) under **Doc 1.11: Supporting Systems Specification (Risk, Validation, Infrastructure)**. With the completion of this document, **Phase 1 (Architecture First Documentation & Specifications) is 100% Complete**.
