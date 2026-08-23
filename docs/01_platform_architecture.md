# AIOS Specification 1.1: Overall Platform Architecture & Inter-Community Protocols

## Document Control
- **Document Version**: 1.1.0
- **Status**: Approved Specification (Frozen)
- **Target System**: AIOS (AI-Native Trading & Autonomous Research System)
- **Author**: AIOS System Architecture Team

---

## 1. System Overview & Architectural Principles

### 1.1 AI-Native Multi-Agent Paradigm
AIOS (Artificial Intelligence Operating System for Autonomous Trading) is built from the ground up as an AI-native, decoupled multi-agent platform designed for quantitative market intelligence, strategy research, automated verification, risk-managed trade execution, and dynamic portfolio optimization.

Unlike monolithic algorithmic trading architectures or traditional rule-based expert systems, AIOS isolates key responsibilities across autonomous agent groups called **Communities**. Each community operates as an independent node within a Directed Graph topology with explicit non-linear feedback loops, maintaining high specialization, minimal context pollution, and deterministic inter-community contracts.

### 1.2 The 9 Specialized Communities
The platform is organized into 9 distinct specialized communities:

1. **Community 1: Data Acquisition (C1)** - Real-time market ingestion, normalization, cross-asset alignment, timestamping, deduplication, and sentiment aggregation.
2. **Community 2: Research & Analysis (C2)** - Multi-agent thesis generation, Bull/Bear debate structures, quantitative screening, and hypothesis formulation.
3. **Community 3: Verification Firewall (C3)** - Adversarial fact-checking, hallucination detection, statistical validation, and confidence scoring.
4. **Community 4: Strategy Generation (C4)** - Parameter synthesis, risk/reward calculation, entry/exit boundary definition, and position sizing logic.
5. **Community 5: Live Trading Execution (C5)** - Order routing, exchange gateway management, low-latency execution, and order lifecycle management.
6. **Community 6: Observation & Audit (C6)** - Real-time execution tracking, slippage analysis, transaction fee auditing, and post-trade performance analytics.
7. **Community 7: Memory Architecture (C7)** - Institutional memory storage combining vector embeddings (Qdrant), relational audit log (Postgres), and high-frequency time-series datasets (TimescaleDB).
8. **Community 8: Evolution Mechanisms (C8)** - Strategy decay evaluation, prompt optimization, agent lifecycle governance (spawning/retirement), and system-wide learning.
9. **Community 9: Portfolio Intelligence (C9)** - Cross-strategy capital allocation, correlation matrix analysis, aggregate portfolio drawdown control, and position weight optimization.

### 1.3 Core Governance Principle
All state transitions across AIOS strictly follow the **Information & Portfolio Pipeline Paradigm**:

```
Information (C1) -> Verified Intelligence (C2/C3) -> Strategy (C4) -> Portfolio Allocation (C9) -> Risk Firewall -> Execution (C5) -> Observation (C6) -> Memory (C7) -> Evolution (C8)
```

**Key Governance Rules:**
- **Strict Gatekeeping**: No unverified hypothesis from C2 can bypass C3 verification. No strategy from C4 can execute without passing C9 Portfolio Allocation and the deterministic Risk Firewall.
- **State Isolation**: Communities do not expose internal mutable memory state. All communication is asynchronous and event-driven via strict, typed Pydantic payloads.
- **Fail-Safe Circuit Breaking**: Non-LLM deterministic rules enforce hard daily drawdown limits (3.0%), max position caps (5.0%), and instant panic kill-switches.

---

## 2. End-to-End System Directed Graph Topology

The data and event flow through AIOS operates as a graph topology with non-linear feedback loops from Observation, Memory, and Evolution back into Research, Verification, Strategy, and Portfolio Allocation:

```
+-----------------------------------------------------------------------------------+
|                                 WORLD DATA SOURCES                                |
|                 (Exchanges, Financial News, Orderbooks, Macro Data)              |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                       COMMUNITY 1: DATA ACQUISITION (C1)                          |
|             (Ingestion, Normalization, Deduplication, Sentiment Tagging)          |
+-----------------------------------------------------------------------------------+
                                          |
                                          | [MarketDataPayload]
                                          v
+-----------------------------------------------------------------------------------+
|                       COMMUNITY 2: RESEARCH & ANALYSIS (C2)                       |<---+
|           (Thesis Generation, Bull/Bear Agent Debates, Risk/Reward Setup)        |    |
+-----------------------------------------------------------------------------------+    |
                                          |                                              |
                                          | [CandidateHypothesis]                        |
                                          v                                              |
+-----------------------------------------------------------------------------------+    |
|                      COMMUNITY 3: VERIFICATION FIREWALL (C3)                      |<---| (Anti-patterns
|         (Hallucination Detection, Statistical Fact-Check, Confidence Scoring)     |    |  & Prompt
+-----------------------------------------------------------------------------------+    |  Updates)
                                          |                                              |
                                          | [VerificationReport (is_verified=True)]      |
                                          v                                              |
+-----------------------------------------------------------------------------------+    |
|                       COMMUNITY 4: STRATEGY GENERATION (C4)                       |    |
|          (Entry/Exit Rules, Stop-Loss/Take-Profit, Position Sizing Logic)         |    |
+-----------------------------------------------------------------------------------+    |
                                          |                                              |
                                          | [StrategySpecification]                      |
                                          v                                              |
+-----------------------------------------------------------------------------------+    |
|                     COMMUNITY 9: PORTFOLIO INTELLIGENCE (C9)                      |    |
|      (Cross-Strategy Allocation, Correlation Matrix, Portfolio Drawdown Control)  |    |
+-----------------------------------------------------------------------------------+    |
                                          |                                              |
                                          | [PortfolioAllocationPlan]                    |
                                          v                                              |
+-----------------------------------------------------------------------------------+    |
|                CONTINUOUS TRAINING & PAPER SIMULATION ENVIRONMENT                 |    |
|             (Walk-Forward Backtesting, Synthetic Stress Tests, Paper Engine)      |    |
+-----------------------------------------------------------------------------------+    |
                                          |                                              |
                                          v                                              |
+-----------------------------------------------------------------------------------+    |
|                      DETERMINISTIC RISK FIREWALL (NON-LLM)                        |    |
|        (Daily Drawdown Caps, Max Exposure Limits, Hard Stop Circuit Breakers)     |    |
+-----------------------------------------------------------------------------------+    |
                                          |                                              |
                                          | [Passed Strategy Order]                      |
                                          v                                              |
+-----------------------------------------------------------------------------------+    |
|                      COMMUNITY 5: LIVE TRADING EXECUTION (C5)                     |    |
|           (Order Management System, Exchange Gateways, Latency Control)           |    |
+-----------------------------------------------------------------------------------+    |
                                          |                                              |
                                          | [TradeExecutionReceipt]                      |
                                          v                                              |
+-----------------------------------------------------------------------------------+    |
|                       COMMUNITY 6: OBSERVATION & AUDIT (C6)                       |    |
|           (Slippage Tracking, Fee Auditing, PnL Attribution, Deviation Analysis)  |    |
+-----------------------------------------------------------------------------------+    |
                                          |                                              |
                                          | [ObservationReport]                          |
                                          v                                              |
+-----------------------------------------------------------------------------------+    |
|                       COMMUNITY 7: MEMORY ARCHITECTURE (C7)                       |    |
|        (Vector Store: Qdrant | Relational DB: Postgres | Time-Series: Timescale)    |    |
+-----------------------------------------------------------------------------------+    |
                                          |                                              |
                                          | [Historical Context & Lessons]               |
                                          v                                              |
+-----------------------------------------------------------------------------------+    |
|                       COMMUNITY 8: EVOLUTION MECHANISMS (C8)                      |----+
|         (Strategy Decay Rules, Prompt Optimization, Agent Spawning/Retirement)   |
+-----------------------------------------------------------------------------------+
```

---

## 3. Inter-Community Communication Protocols

### 3.1 Pub/Sub Event Bus Architecture
Inter-community communication is decoupled using an asynchronous Event Bus.
- **Local Prototype Mode**: `InMemoryEventBus` backed by Python `asyncio.Queue` or thread-safe channels.
- **Enterprise Production Mode**: NATS JetStream or Redis Streams topic hierarchy.

#### Event Topic Naming Convention:
- `aios.c1.market_data.<symbol>`
- `aios.c2.hypothesis.<symbol>`
- `aios.c3.verification.<hypothesis_id>`
- `aios.c4.strategy.<symbol>`
- `aios.c9.portfolio_allocation`
- `aios.c5.execution.<strategy_id>`
- `aios.c6.observation.<execution_id>`
- `aios.c7.memory.index`
- `aios.c8.evolution.update`

### 3.2 Message Delivery Guarantees
- **At-Least-Once Delivery**: Events must be acknowledged (`ACK`) by subscriber handlers upon successful validation and processing.
- **Idempotency**: All payload contracts require unique identifiers (`hypothesis_id`, `report_id`, `strategy_id`, `plan_id`, `execution_id`, `observation_id`) to ensure idempotent processing across retries.
- **Audit Logging**: Every event published on the bus is appended to an immutable append-only event log table in relational storage for compliance and replay analysis.

### 3.3 Data Payload Contract Definitions
All inter-community communication uses strict Pydantic v2 schemas defined in `schemas/contracts.py`:

```python
class MarketDataPayload(BaseModel):
    timestamp: datetime = Field(default_factory=generate_utc_now)
    symbol: str = Field(..., min_length=1)
    timeframe: str = Field(..., min_length=1)
    price_data: PriceData
    news_sentiment: list[NewsSentiment] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class CandidateHypothesis(BaseModel):
    hypothesis_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=generate_utc_now)
    symbol: str = Field(..., min_length=1)
    thesis: str = Field(..., min_length=1)
    supporting_arguments: list[str]
    counter_arguments: list[str]
    timeframe: str = Field(..., min_length=1)
    expected_risk_reward_ratio: float = Field(..., gt=0.0)

class VerificationReport(BaseModel):
    report_id: str = Field(default_factory=generate_uuid)
    hypothesis_id: str = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0.0, le=100.0)
    is_verified: bool = Field(default=False)
    verified_claims: list[str]
    flagged_hallucinations: list[str]
    verification_notes: str

class StrategySpecification(BaseModel):
    strategy_id: str = Field(default_factory=generate_uuid)
    hypothesis_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    action: Literal["BUY", "SELL", "HOLD"]
    entry_price: float = Field(..., gt=0.0)
    stop_loss_price: float = Field(..., gt=0.0)
    take_profit_price: float = Field(..., gt=0.0)
    position_size_pct: float = Field(..., ge=0.0, le=100.0)

class PortfolioAllocationPlan(BaseModel):
    plan_id: str = Field(default_factory=generate_uuid)
    timestamp: datetime = Field(default_factory=generate_utc_now)
    allocations: list[StrategyAllocation]
    total_portfolio_exposure_pct: float
    current_portfolio_drawdown_pct: float
    portfolio_status: Literal["HEALTHY", "WARNING", "CAUTION", "CRITICAL_HALT"]

class TradeExecutionReceipt(BaseModel):
    execution_id: str = Field(default_factory=generate_uuid)
    strategy_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    fill_price: float = Field(..., gt=0.0)
    filled_quantity: float = Field(..., gt=0.0)
    slippage: float = Field(..., ge=0.0)
    fees: float = Field(..., ge=0.0)
    executed_at: datetime = Field(default_factory=generate_utc_now)

class ObservationReport(BaseModel):
    observation_id: str = Field(default_factory=generate_uuid)
    execution_id: str = Field(..., min_length=1)
    actual_pnl: float
    predicted_vs_actual_deviation: float
    lessons_learned: list[str]
```

---

## 4. State Management & Isolation Rules

### 4.1 Strict Community State Isolation
To guarantee modularity, agent focus, and system reliability, communities operate under strict state encapsulation:
- **Zero Direct Access**: No community may directly read or mutate another community's internal state or local memory.
- **Event-Driven & Query-Based Access**: Information sharing occurs exclusively via published bus events or explicitly indexed read-only queries against Community 7 (Memory Architecture).
- **Context Window Protection**: Isolating communities prevents large-context LLMs from deteriorating in performance due to prompt pollution across domain boundaries.

### 4.2 Deterministic Risk Firewall Positioning
A critical safety feature of AIOS is the positioning of a **non-LLM Deterministic Risk Firewall** directly between Community 9 (Portfolio Intelligence) / Community 4 (Strategy) and Execution (C5 / Continuous Training Engine).

---

## 5. System Scalability Strategy

AIOS is architected for seamless transition between single-machine local prototyping and distributed enterprise deployment:

| Architectural Dimension | Local Prototyping Mode | Enterprise Scaled Production |
| :--- | :--- | :--- |
| **Event Messaging** | In-Memory Async Queue / `InMemoryEventBus` | NATS JetStream / Apache Kafka / Redis Streams |
| **Relational Storage** | SQLite (`aios_local.db`) | PostgreSQL + TimescaleDB extension cluster |
| **Vector Memory** | In-Memory / Local File Qdrant | Distributed Qdrant Cluster / Milvus Enterprise |
| **Agent Execution** | Local Python Async Tasks | Containerized Kubernetes Pods (K8s) per Community |
| **Market Ingestion** | REST / Single WebSocket feed (CCXT / Mock) | Distributed Ingestion Nodes (CCXT, Alpaca, Polygon.io) |
| **Risk Firewall** | Embedded In-Process Guard (`RiskFirewall`) | Dedicated High-Availability Gateway Service |

---

## 6. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/CHECKPOINT.md) under **Doc 1.1: Overall Platform Architecture & Inter-Community Protocols**. Any proposed architectural modifications must update this specification document alongside Pydantic schemas in `schemas/contracts.py`.
