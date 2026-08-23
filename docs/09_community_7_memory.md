# AIOS Specification 1.9: Community 7 Specification (Memory Architecture)

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification
- **Target System**: AIOS - Community 7 (Memory Architecture)
- **Author**: AIOS System Architecture Team

---

## 1. Community Purpose & Responsibilities

### 1.1 Primary Objective
Community 7 (C7) serves as the institutional memory backbone for AIOS. Its primary objective is to build and maintain permanent organizational knowledge across short-term, long-term, vector, and time-series storage layers so that every insight, failure, and outcome persists across trading sessions, agent restarts, and system upgrades.

### 1.2 Core Responsibilities
- **Universal Event Ingestion**: Subscribe to all inter-community event bus topics and persist every payload to the appropriate storage subsystem.
- **Structured Relational Storage**: Maintain normalized, queryable records of trade specifications, verification reports, execution receipts, and observation post-mortems.
- **High-Density Time-Series Storage**: Store tick-level and bar-level price data, indicator time-series, and execution slippage logs at sub-second granularity.
- **Semantic Vector Indexing**: Convert textual research theses, debate transcripts, and post-mortem lessons into dense vector embeddings for similarity-based retrieval.
- **Counterfactual Pattern Retrieval**: Serve semantic similarity queries from Community 2 (Research) to surface historical setups, past mistakes, and regime-specific lessons.
- **Historical Performance Query Serving**: Provide structured query interfaces for rolling performance metrics, agent accuracy scorecards, and strategy decay analysis consumed by Community 8 (Evolution).

---

## 2. Memory Subsystems Architecture

Community 7 manages four distinct storage subsystems, each optimized for a specific data access pattern:

```
+-----------------------------------------------------------------------------------+
|                       COMMUNITY 7: MEMORY ARCHITECTURE                            |
+-----------------------------------------------------------------------------------+
     |                   |                        |                   |
     v                   v                        v                   v
+----------------+ +-------------------+ +-------------------+ +-------------------+
| SHORT-TERM     | | RELATIONAL AUDIT  | | TIME-SERIES       | | SEMANTIC VECTOR   |
| CACHE & BUFFER | | STORE             | | STORE             | | MEMORY            |
| (Redis)        | | (PostgreSQL)      | | (TimescaleDB)     | | (Qdrant)          |
+----------------+ +-------------------+ +-------------------+ +-------------------+
| Active session | | Trade records     | | OHLCV bars/ticks  | | Thesis embeddings |
| state, locks,  | | Verification rpts | | Indicator values  | | Debate transcripts|
| pub/sub buffer | | Strategy specs    | | Slippage logs     | | Post-mortem lessons|
| Rate-limit     | | System audit logs | | PnL time-series   | | Anomaly contexts  |
| counters       | | Promotion records | | Volume profiles   | | Market regime     |
+----------------+ +-------------------+ +-------------------+ +-------------------+
```

### 2.1 Short-Term Cache & Buffer (Redis)
- **Purpose**: Transient, high-speed key-value store for active session state that does not require permanent persistence.
- **Data Stored**:
  - Active session context (current open positions, pending orders, agent task locks).
  - Streaming pub/sub message buffers for event bus overflow handling.
  - Rate-limit counters and sliding window tokens for exchange API throttling.
  - Deduplication hash sets for Community 1 (Data Acquisition) headline filtering.
- **Retention Policy**: TTL-based expiration. Default TTL: 24 hours for session state, 1 hour for rate-limit counters.
- **Local Prototype**: In-memory Python `dict` with TTL simulation.
- **Enterprise Production**: Redis 7+ cluster with persistence (AOF + RDB snapshots).

### 2.2 Relational Audit Store (PostgreSQL)
- **Purpose**: Permanent, ACID-compliant structured storage for all business-critical records requiring complex queries, joins, and compliance auditing.
- **Schema Design** (core tables):

| Table | Primary Key | Description |
| :--- | :--- | :--- |
| `market_data_log` | `id` (serial) | Archived `MarketDataPayload` records with symbol, timeframe, and timestamp indices. |
| `hypotheses` | `hypothesis_id` (UUID) | All `CandidateHypothesis` records from Community 2. |
| `verification_reports` | `report_id` (UUID) | All `VerificationReport` records from Community 3 with `is_verified` flag. |
| `strategy_specifications` | `strategy_id` (UUID) | All `StrategySpecification` records from Community 4. |
| `risk_evaluations` | `id` (serial) | `RiskEvaluationResult` records from Risk Firewall evaluations. |
| `execution_receipts` | `execution_id` (UUID) | All `TradeExecutionReceipt` records (both simulated and live). |
| `observation_reports` | `observation_id` (UUID) | All `ObservationReport` post-mortem records from Community 6. |
| `promotion_records` | `id` (serial) | Strategy promotion/demotion/retirement lifecycle events. |
| `event_audit_log` | `id` (serial) | Immutable append-only log of every event published on the bus. |

- **Retention Policy**: Permanent. No automatic deletion. Partitioned by month for query performance.
- **Local Prototype**: SQLite (`aios_local.db`) with equivalent schema.
- **Enterprise Production**: PostgreSQL 16+ with read replicas.

### 2.3 Time-Series Store (TimescaleDB)
- **Purpose**: Optimized columnar storage for high-density, time-indexed numerical data requiring fast range queries and downsampling.
- **Hypertables**:

| Hypertable | Time Column | Chunk Interval | Description |
| :--- | :--- | :---: | :--- |
| `price_ticks` | `timestamp` | 1 day | Raw tick-level price data (bid, ask, last, volume). |
| `price_bars` | `timestamp` | 7 days | Aggregated OHLCV bars at 1m, 5m, 15m, 1h, 4h, 1d intervals. |
| `indicator_values` | `timestamp` | 7 days | Computed indicator time-series (RSI, EMA, MACD, ATR). |
| `slippage_log` | `executed_at` | 7 days | Per-execution slippage measurements and fill quality scores. |
| `pnl_series` | `timestamp` | 30 days | Rolling PnL, equity curve, and drawdown time-series. |

- **Retention Policy**: Raw ticks retained for 90 days, then downsampled to 1m bars. Bars and indicators retained permanently.
- **Continuous Aggregates**: Pre-computed materialized views for 1h, 4h, and 1d bar rollups from raw 1m data.
- **Local Prototype**: SQLite with manual timestamp indexing.
- **Enterprise Production**: TimescaleDB extension on PostgreSQL 16+.

### 2.4 Semantic Vector Memory (Qdrant)
- **Purpose**: Dense vector store enabling semantic similarity search over unstructured textual knowledge — research theses, debate transcripts, post-mortem lessons, and market regime descriptions.
- **Collections**:

| Collection | Vector Dimension | Distance Metric | Description |
| :--- | :---: | :--- | :--- |
| `research_theses` | 768 | Cosine | Embeddings of `CandidateHypothesis.thesis` and supporting/counter arguments. |
| `debate_transcripts` | 768 | Cosine | Full debate round transcripts from Community 2 agent discussions. |
| `post_mortem_lessons` | 768 | Cosine | Embeddings of `ObservationReport.lessons_learned` entries. |
| `market_regimes` | 768 | Cosine | Regime description embeddings (Risk-On, Risk-Off, High-Vol, Low-Vol). |

- **Embedding Model**: Configurable. Default: `all-MiniLM-L6-v2` (384-dim) for local prototype, `text-embedding-3-small` (768-dim) for production.
- **Payload Metadata**: Each vector point stores metadata including `symbol`, `timestamp`, `hypothesis_id`, `observation_id`, and `actual_pnl` for filtered retrieval.
- **Local Prototype**: In-memory Qdrant or local file-based Qdrant instance.
- **Enterprise Production**: Distributed Qdrant cluster with replication factor 2.

---

## 3. Agent Hierarchy & Roles

Community 7 operates three specialized agents for ingestion, embedding, and retrieval:

```
+-----------------------------------------------------------------------------------+
|                 ALL EVENT BUS TOPICS (subscribed by C7)                           |
+-----------------------------------------------------------------------------------+
                                          |
               +--------------------------+--------------------------+
               |                                                     |
               v                                                     v
+-----------------------------+                       +-----------------------------+
|  INGESTION & PERSISTENCE    |                       |   VECTOR EMBEDDING AGENT    |
|         AGENT               |                       | (Text -> Dense Vectors)     |
| (Writes to PG + Timescale)  |                       | (Indexes in Qdrant)         |
+-----------------------------+                       +-----------------------------+
                                                                     |
                                                                     v
                                                      +-----------------------------+
                                                      | COUNTERFACTUAL RETRIEVAL    |
                                                      |         AGENT               |
                                                      | (Similarity Search for C2)  |
                                                      +-----------------------------+
```

### 3.1 Ingestion & Persistence Agent
- **Role**: Universal event listener that subscribes to all event bus topics and writes every payload to the appropriate relational or time-series store.
- **Subscriptions**: `DATA_ACQUIRED`, `HYPOTHESIS_GENERATED`, `VERIFICATION_COMPLETED`, `STRATEGY_GENERATED`, `TRADE_EXECUTED`, `OBSERVATION_COMPLETED`, `EVOLUTION_TRIGGERED`.
- **Write Guarantees**: At-least-once persistence. Each write is wrapped in a database transaction with retry logic (max 3 retries, exponential backoff).
- **Immutable Audit Log**: Every ingested event is additionally appended to the `event_audit_log` table for compliance replay.

### 3.2 Vector Embedding Agent
- **Role**: Converts textual content from research theses, debate transcripts, and observation lessons into dense vector embeddings and indexes them in Qdrant.
- **Trigger**: Activated upon ingestion of `CandidateHypothesis`, `VerificationReport` (notes), and `ObservationReport` (lessons_learned) events.
- **Embedding Pipeline**:
  1. Extract text fields (thesis, arguments, lessons_learned, verification_notes).
  2. Tokenize and embed using the configured embedding model.
  3. Upsert vector point into the appropriate Qdrant collection with full metadata payload.

### 3.3 Counterfactual Retrieval Agent
- **Role**: Serves semantic similarity queries from Community 2 and Community 8 to surface historically relevant setups, past mistakes, and regime-matched lessons.
- **Query Types**:
  - **Similar Setup Search**: Given a new hypothesis embedding, retrieve the top-K most similar past theses and their associated `ObservationReport` outcomes.
  - **Lesson Retrieval**: Given a symbol and market regime, retrieve the most relevant post-mortem lessons.
  - **Performance History**: Given an agent ID or strategy pattern, retrieve rolling performance metrics from the relational store.

---

## 4. Query Protocols & Event Bus Routing

### 4.1 Query Interfaces
Community 7 exposes the following query methods to other communities (primarily C2 and C8):

```python
async def get_recent_performance(
    symbol: str | None = None,
    window_days: int = 30,
) -> list[dict]:
    """Retrieve recent trade performance metrics from relational store.

    Args:
        symbol: Optional filter by trading symbol.
        window_days: Lookback window in calendar days.

    Returns:
        List of performance summary dicts (PnL, win_rate, sharpe, max_drawdown).
    """

async def search_similar_historical_setups(
    embedding: list[float],
    k: int = 5,
    symbol: str | None = None,
) -> list[dict]:
    """Semantic similarity search over past research theses in Qdrant.

    Args:
        embedding: Dense vector embedding of the query thesis.
        k: Number of nearest neighbors to return.
        symbol: Optional filter by trading symbol.

    Returns:
        List of dicts containing matched thesis, similarity score,
        and associated ObservationReport outcome.
    """

async def get_post_mortem_lessons(
    symbol: str,
    k: int = 10,
) -> list[str]:
    """Retrieve the most relevant post-mortem lessons for a symbol.

    Args:
        symbol: Trading symbol to query lessons for.
        k: Maximum number of lessons to return.

    Returns:
        List of lesson strings from past ObservationReports.
    """
```

### 4.2 Event Bus Routing
- **Subscription Topics**: All topics — `DATA_ACQUIRED`, `HYPOTHESIS_GENERATED`, `VERIFICATION_COMPLETED`, `STRATEGY_GENERATED`, `TRADE_EXECUTED`, `OBSERVATION_COMPLETED`, `EVOLUTION_TRIGGERED`.
- **Publication Topic**: `memory.stored` (`EventTopic.MEMORY_STORED`) — emitted after successful persistence of any ingested event, enabling downstream acknowledgement.
- **Target Subscribers**: Community 8 (Evolution Mechanisms) listens for `MEMORY_STORED` to trigger periodic learning cycles.

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/CHECKPOINT.md) under **Doc 1.9: Community 7 Specification (Memory Architecture)**. Event topics are defined in [event_bus.py](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/core/event_bus.py). Scalability tiers (local SQLite/in-memory vs. enterprise PostgreSQL/TimescaleDB/Qdrant) are documented in [01_platform_architecture.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/docs/01_platform_architecture.md) Section 5.
