# AIOS Phase 2 — Reconciled Capability Matrix
**Document Version**: 2.0.0
**Status**: Reconciled Phase 2 Research Artifact (FORMAL SELECTION = 0)
**Created**: 2026-08-18
**Authoritative Reference**: Frozen Phase 1 Architecture (ADR-001)

---

## 1. Document Purpose & Governance

This capability matrix maps every requirement of the frozen AIOS Phase 1 architecture across 15 normalized capability domains to the OSS candidates evaluated in the 73-package research universe (`github reserch`).

### Governance Constraints:
- **FORMAL SELECTION = 0**: All candidate assignments represent **Research Preferences** or **Benchmark Candidates**, pending empirical benchmark execution and formal ADR documentation.
- **Coverage Levels**: `FULL`, `PARTIAL`, `NONE`.
- **Evidence Quality**: `SOURCE_CODE`, `OFFICIAL_DOCS`, `README_ONLY`.
- **Benchmark Status**: `BENCHMARK-REQUIRED`, `BENCHMARK-NOT-REQUIRED`, `NOT-BENCHMARKED`.

---

## 2. Capability Matrix Across 15 AIOS Domains

| Capability Domain ID | AIOS Capability Requirement | Primary Research Preference | Coverage | Evidence Quality | Confidence | Benchmark Candidate / Alternatives | Custom Build Requirement |
|----------------------|-----------------------------|-----------------------------|----------|-----------------|------------|-----------------------------------|--------------------------|
| **CAP-01** | **Market Data Ingestion & Normalization** (Crypto, Equities, Ticks, Bars, UTC alignment, Dedup) | **CCXT** (Crypto)<br>**Alpaca SDK** (Equities) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | Twelve Data, Finnhub, Polygon.io (client-python), Alpha Vantage | Social Sentiment Velocity Ingestor |
| **CAP-02** | **Event Bus & Async Messaging** (Pub/Sub, At-least-once, Priority Tiers 0-3, DLQ, Retries) | **InMemoryEventBus** (Proto)<br>**NATS JetStream** (Prod) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | RedPanda (Kafka-compat), Redis Streams | None |
| **CAP-03** | **Multi-Agent Orchestration** (Cyclic DAG, Bull/Bear debate, Gated pipelines, State Graph) | **LangGraph** | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | CrewAI, LlamaIndex, MS Agent Framework, OpenGeni, Temporal | Adversarial Debate Engine |
| **CAP-04** | **Backtesting & Simulation Engine** (Tick/bar, Walk-forward 90/30, Slippage/fee, Event replay) | **NautilusTrader** | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | LEAN (QuantConnect), VectorBT, ORE (Engine), ABIDES (Simulation Reference) | Synthetic Market Generator (GBM/GARCH/GAN) |
| **CAP-05** | **Live Execution Gateway** (Order lifecycle, TWAP/VWAP, Gateways, Panic Kill-Switch) | **CCXT**, **Alpaca SDK** | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | NautilusTrader Execution | Deterministic Risk Firewall & TWAP/VWAP Order Slicer |
| **CAP-06** | **Vector Semantic Memory** (768-dim embeddings, Cosine, 4 collections, Metadata filtering) | **Qdrant** | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | Qdrant + LlamaIndex (Group I Retrieval Abstraction), Milvus Enterprise (Phase 1 spec alternative) | None |
| **CAP-07** | **Relational Audit Store** (ACID, UUID schemas, Append-only event audit log, Monthly partition) | **PostgreSQL** (Prod)<br>**SQLite** (Proto) | FULL | OFFICIAL_DOCS | HIGH | None (Core Database) | Immutable Append-Only Ledger Wrapper |
| **CAP-08** | **Time-Series Store** (Hypertables, Ticks/Bars/Indicators/PnL, Continuous Aggregates) | **TimescaleDB** | FULL | OFFICIAL_DOCS | HIGH | Qlib Storage | Continuous Aggregates & Downsampling Rules |
| **CAP-09** | **Short-Term Cache & State** (Session context, TTL 24h, Rate-limit counters, Pub/Sub buffer) | **Redis** | FULL | OFFICIAL_DOCS | HIGH | In-Memory Dict (Local) | Throttling & Deduplication Hash Buffer |
| **CAP-10** | **LLM Observability & Tracing** (Prompt tracing, Token costs, Latency p50/p95/p99, OTel) | **LangFuse** (LLM)<br>**Grafana** (Dashboards)<br>**OpenTelemetry** (Trace) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | DeepEval, Guardrails AI (Group K Supporting Evaluation/Validation) | Metrics Exporter Integration |
| **CAP-11** | **Portfolio Intelligence & Allocation** (Fractional Kelly, Risk parity, Correlation caps, Drawdown guard) | **PyPortfolioOpt** | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | Riskfolio-Lib, ORE (Engine) | Fractional Kelly & Multi-Tier Drawdown Guard |
| **CAP-12** | **Agent Governance & Evolution** (8-Stage Lifecycle, Reputation matrix $R_{agent}$, Threshold tuning) | **AIOS Evolution Engine** (BUILD) | NONE | SOURCE_CODE (Phase 1 Specs) | HIGH | FinRL (Study), agent-governance-toolkit (Study) | Agent Lifecycle & Reputation Engine, Threshold Auto-Tuner |
| **CAP-13** | **Security & Secrets Management** (Dynamic credentials, AES-256-GCM at rest, Policy engine) | **OpenBao** (Vault)<br>**OPA** (Policy) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | Custom Python Middleware | AES-256-GCM Encryption Wrapper |
| **CAP-14** | **Experiment & Model Registry** (ExperimentRecord lineage, ModelRecord governance, litellm routing) | **MLflow** | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | ClearML | Model Record & Experiment Record Pydantic Adapters |
| **CAP-15** | **Decision Audit Graph & Provenance** (Line-of-sight provenance DAG, Backwards query API) | **Neo4j** (or PostgreSQL CTE Graph) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | NebulaGraph, DataHub (Deferred) | Line-of-Sight Decision Audit Graph API |

---

## 3. Capability Coverage Breakdown Summary

```
===================================================================================
                   CAPABILITY COVERAGE RECONCILIATION SUMMARY
===================================================================================
TOTAL FROZEN AIOS CAPABILITIES EVALUATED: ........ 15
- Capabilities with Full OSS Coverage: .......... 10  (CAP-01, 02, 06, 07, 08, 09,
                                                       10, 11, 13, 14)
- Capabilities with Partial OSS Coverage: ......... 4  (CAP-03, 04, 05, 15)
- Capabilities with ZERO OSS Coverage (Full BUILD): 1  (CAP-12 Agent Governance)

-----------------------------------------------------------------------------------
AIOS CUSTOM BUILD COMPONENTS (8 BUILD GAPS)
-----------------------------------------------------------------------------------
1. Adversarial Debate Engine (CAP-03)
2. Deterministic Risk Firewall (CAP-04/05, Doc 11)
3. TWAP/VWAP Order Slicer (CAP-05)
4. Agent Lifecycle & Reputation Engine (CAP-12)
5. Verification Threshold Auto-Tuner (CAP-12)
6. Synthetic Market Generator (CAP-04)
7. Line-of-Sight Decision Audit Graph API (CAP-15)
8. Social Sentiment Velocity Ingestor (CAP-01)
===================================================================================
```

---

*End of Reconciled Capability Matrix.*
