# AIOS Phase 2 — Reconciled Candidate Technology Stack
**Document Version**: 2.0.0
**Status**: Reconciled Candidate Proposal (FORMAL SELECTION = 0)
**Created**: 2026-08-18
**Authoritative Reference**: Frozen Phase 1 Architecture (ADR-001)

---

## 1. Executive Summary

This document presents the **Reconciled Candidate Technology Stack** for AIOS resulting from the capability mapping and technology reduction pass over the 73-package open-source research universe (`github reserch`).

### Key Architectural Constraints:
- **FORMAL SELECTION = 0**: All candidate designations represent **Research Preferences** or **Benchmark Candidates**. Formal selection occurs ONLY after empirical benchmark execution and formal Architecture Decision Record (ADR) sign-off.
- **Strict Phase 1 Compliance**: No Phase 1 specifications have been modified, expanded, or bypassed.
- **Zero Vendor Lock-in**: All stack candidates connect to AIOS via Abstract Base Class (ABC) wrappers in `core/` and `communities/`.

---

## 2. Reconciled Minimal Candidate Stack Categorization

The candidate stack is structured into 7 operational categories to distinguish application runtime dependencies from platform infrastructure services and custom-built components:

```
+-------------------------------------------------------------------------------------------------------------------+
|                                 RECONCILED CANDIDATE TECHNOLOGY STACK MATRIX                                      |
+-------------------------------------------------------------------------------------------------------------------+
| CATEGORY                        | CANDIDATE TECHNOLOGY    | ROLE & INTEGRATION BOUNDARY            | LICENSE RISK |
+---------------------------------+-------------------------+----------------------------------------+--------------+
| 1. Application Runtime          | CCXT                    | Crypto REST/WebSocket Ingestion Gateway| LOW (MIT)    |
|    Dependencies                 | Alpaca SDK              | Equities Data & Paper Broker Gateway   | LOW (Apache) |
|                                 | LangGraph               | Multi-Agent Cyclic State-Graph Engine  | LOW (MIT)    |
|                                 | NautilusTrader          | High-Performance Event Backtester      | HIGH (LGPL-3)|
|                                 | PyPortfolioOpt          | Portfolio Allocation & Kelly Optimizer | LOW (MIT)    |
|                                 | MLflow SDK              | Experiment & Model Registry Client     | LOW (Apache) |
|                                 | LangFuse SDK            | LLM Prompt Tracing & Cost Client       | LOW (MIT)    |
+---------------------------------+-------------------------+----------------------------------------+--------------+
| 2. Core Data Infrastructure     | PostgreSQL 16+          | Relational Audit Store & Event Log     | LOW (Postgres|
|                                 | TimescaleDB             | Time-Series Hypertables (Ticks/Bars)   | LOW (Apache) |
|                                 | Qdrant                  | Dense Vector Memory (768-dim)          | LOW (Apache) |
|                                 | Redis 7+                | Short-Term Cache & Session Rate-Limiter| LOW (RSAL/SSPL
+---------------------------------+-------------------------+----------------------------------------+--------------+
| 3. Messaging Infrastructure     | NATS JetStream          | Enterprise Pub/Sub & Subject Broker    | LOW (Apache) |
+---------------------------------+-------------------------+----------------------------------------+--------------+
| 4. Security & Governance Infra  | OpenBao                 | Dynamic Secrets & AES-256 Vault        | LOW (MPL-2.0)|
|                                 | Open Policy Agent (OPA) | Rego Policy & Access Gatekeeper        | LOW (Apache) |
+---------------------------------+-------------------------+----------------------------------------+--------------+
| 5. Observability Infrastructure | LangFuse Server         | Self-Hosted LLM Tracing Platform       | LOW (MIT)    |
|                                 | Grafana                 | Prometheus Metrics & System Dashboards | MEDIUM (AGPL)|
|                                 | OpenTelemetry Collector | Distributed Event Trace Collector      | LOW (Apache) |
+---------------------------------+-------------------------+----------------------------------------+--------------+
| 6. Provenance & Audit Infra     | Neo4j (or Postgres CTE)| Property Graph for Decision Lineage    | HIGH (GPL-3) |
+---------------------------------+-------------------------+----------------------------------------+--------------+
| 7. Custom AIOS Built Components | AIOS Engine (BUILD)     | 8 Custom Build Components (Section 5)  | N/A (AIOS)   |
+-------------------------------------------------------------------------------------------------------------------+
```

---

## 3. Abstract Base Class (ABC) Integration Boundaries

To guarantee zero vendor lock-in, every primary technology connects to AIOS through an explicit ABC wrapper:

| Abstract Base Class | Package / Module | Primary Candidate Adapter | Alternative Adapter |
|---------------------|------------------|---------------------------|---------------------|
| `BaseDataFetcher` | `communities/c1_data/` | `CCXTDataFetcher`, `AlpacaDataFetcher` | `TwelveDataFetcher`, `PolygonDataFetcher` |
| `BaseExecutionGateway` | `communities/c5_execution/` | `CCXTExecutionGateway`, `AlpacaExecutionGateway` | `NautilusExecutionGateway` |
| `BaseCommunityOrchestrator` | `core/orchestrator.py` | `LangGraphOrchestrator` | `CrewAIOrchestrator`, `TemporalOrchestrator` |
| `BaseBacktestEngine` | `core/validation.py` | `NautilusBacktestEngine` | `LeanBacktestEngine`, `VectorBTEngine` |
| `BaseVectorMemory` | `communities/c7_memory/` | `QdrantVectorStore` | `MilvusVectorStore` |
| `BaseExperimentRegistry` | `core/registries.py` | `MLflowExperimentRegistry` | `ClearMLExperimentRegistry` |
| `BasePortfolioOptimizer` | `communities/c9_portfolio/` | `PyPortfolioOptAdapter` | `RiskfolioAdapter` |
| `BaseEventBus` | `core/event_bus.py` | `InMemoryEventBus` (Proto), `NATSJetStreamBus` (Prod) | `RedPandaEventBus`, `RedisStreamsBus` |
| `BaseLLMObserver` | `core/observability.py` | `LangFuseObserver` | `DeepEvalObserver` |
| `BaseAuditGraph` | `core/audit_graph.py` | `PostgresCTEGraphAdapter` (Default) | `Neo4jGraphAdapter` |

---

## 4. Competition Groups & Benchmark Hierarchy

Every competition group was evaluated to answer: *"Could empirical testing or architectural evaluation materially change the technology decision?"*

The evaluations are structured into a 3-tier hierarchy to define clear ADR prerequisites:

### Tier 1 — Architecture-Critical Competitive Benchmarks (REQUIRED BEFORE FORMAL ADR)
| Group | Candidate Technologies | Benchmark Status | Benchmark Question / Evaluation Focus |
|-------|------------------------|------------------|---------------------------------------|
| **GROUP A** | **LangGraph** (Baseline)<br>vs **CrewAI**, **MS Agent Framework**, **OpenGeni** | **BENCHMARK-REQUIRED** | Empirical test required to verify if CrewAI, MS Agent Framework, or OpenGeni can handle cyclic C8→C2 feedback loops without state corruption compared to LangGraph. |
| **GROUP B** — Backtesting & Simulation Architecture | **PRIMARY BACKTEST COMPETITION:**<br>- NautilusTrader (Baseline)<br>- LEAN<br>- VectorBT<br><br>**SIMULATION REFERENCE:**<br>- ABIDES | **BENCHMARK-REQUIRED** | Evaluates historical backtest throughput, event replay, fee/slippage modelling, walk-forward support, determinism, memory consumption, multi-asset support, and custom strategies (NautilusTrader vs LEAN vs VectorBT), while evaluating whether ABIDES materially improves AIOS digital-twin / market-simulation capability. |
| **GROUP C** | **NATS JetStream** (Baseline)<br>vs **RedPanda** | **BENCHMARK-REQUIRED** | Empirical test required under 50,000 msg/sec load to measure P99 latency, subject routing, and DLQ behavior. |

### Tier 2 — Candidate-Specific Comparative Evaluations (SUPPORTING EVIDENCE / OPTIONAL BEFORE INITIAL ADR)
| Group | Candidate Technologies | Benchmark Status | Benchmark Question / Evaluation Focus |
|-------|------------------------|------------------|---------------------------------------|
| **GROUP D** | **PyPortfolioOpt** (Baseline)<br>vs **Riskfolio-Lib**, **ORE (Engine)** | **BENCHMARK-REQUIRED** | Compatibility and numerical stability test required for Fractional Kelly sizing and CVaR calculations under illiquid market regimes. |
| **GROUP E** | **MLflow** (Baseline)<br>vs **ClearML** | **BENCHMARK-REQUIRED** | Feature and latency comparison for real-time model resolution in `litellm` gateway and metadata retrieval. |
| **GROUP F** | **PostgreSQL CTE Graph** (Baseline)<br>vs **Neo4j**, **NebulaGraph** | **BENCHMARK-REQUIRED** | Benchmarking PostgreSQL recursive CTE graph query latency vs standalone Neo4j and NebulaGraph to evaluate if a separate graph DB is operationally justified. |
| **GROUP I** — Memory / Retrieval Architecture | **BASELINE:**<br>- Direct Qdrant integration (Vector Layer)<br><br>**ALTERNATIVE ARCHITECTURE:**<br>- Qdrant + LlamaIndex (Retrieval Abstraction) | **BENCHMARK-REQUIRED** | Evaluates whether adding LlamaIndex on top of Qdrant storage materially improves retrieval quality, metadata filtering, hybrid retrieval, chunking flexibility, context assembly, and developer productivity enough to justify the additional abstraction, complexity, and dependencies. |
| **GROUP J** | **LangGraph Checkpointers / NATS** (Baseline)<br>vs **Temporal** | **BENCHMARK-REQUIRED** | Durable Workflow Execution Substrate evaluation measuring long-running state durability and step replayability for C8 evolution loops. |
| **GROUP K** — LLM Quality / Validation / Deterministic Safety Architecture | **AIOS AUTHORITATIVE BASELINE:**<br>- Pydantic<br>- AIOS Deterministic Risk/Safety Firewall<br><br>**OPTIONAL SUPPORTING TECHNOLOGIES:**<br>- DeepEval<br>- Guardrails AI | **BENCHMARK-REQUIRED** | Evaluates whether DeepEval or Guardrails materially improve evaluation coverage, test-case generation, LLM output validation, and hallucination detection without overriding, weakening, or replacing the authoritative deterministic AIOS Risk Firewall. |

### Tier 3 — Security, Architecture & Data Provider Evaluations (SUPPORTING EVIDENCE)
| Group | Candidate Technologies | Evaluation Type | Evaluation Criteria & Focus |
|-------|------------------------|-----------------|-----------------------------|
| **GROUP G** | **OpenBao / OPA**<br>vs **Custom Python Middleware** (Baseline) | **Architecture / Security Evaluation** | Evaluates sidecar security isolation (OpenBao/OPA) vs embedded Python middleware across 7 criteria: secret isolation, policy enforcement latency, failure recovery, operational complexity, latency overhead, auditability, and emergency bypass. |
| **GROUP H** | **CCXT + Alpaca SDK** (Baseline)<br>vs **Twelve Data**, **Finnhub**, **Polygon.io**, **Alpha Vantage** | **Supplementary Data Provider Evaluation** | Evaluates whether supplementary market data providers materially improve market-data coverage, tick reliability, news/fundamentals sentiment, or WebSocket stability for feeds not satisfied by CCXT + Alpaca. |

---

## 5. Custom BUILD Component Reconciliation

The following 8 custom AIOS BUILD COMPONENTS (BUILD GAPS) cannot be satisfied by any open-source package and MUST be custom-built within AIOS:

1. **Adversarial Debate Engine (C2, CAP-03)**: Multi-agent debate loop with mandatory counter-argument balance rules (Doc 03).
2. **Deterministic Risk Firewall (Doc 11, CAP-04/05)**: Pure non-LLM Python guard enforcing 3.0% daily drawdown caps and 5.0% position limits (`core/risk_firewall.py`).
3. **TWAP/VWAP Order Slicer (C5, CAP-05)**: Volume-profile order slicing engine built on top of exchange gateways (Doc 07).
4. **Agent Lifecycle & Reputation Engine ($R_{agent}$) (C8, CAP-12)**: 6-factor quantitative reputation matrix ($0.30W + 0.25A + 0.20V + 0.15Q + 0.05L + 0.05R$).
5. **Verification Threshold Auto-Tuner (C8, CAP-12)**: Automated tightening of Community 3 verification thresholds upon win-rate decay (Doc 10).
6. **Synthetic Market Generator (CAP-04)**: Stochastic (GBM/GARCH/GAN) price path generator for stress testing (Digital Twin Tier 2, Doc 18).
7. **Line-of-Sight Decision Audit Graph API (CAP-15)**: Provenance query engine linking `execution_id` backwards to raw market feeds (Doc 18).
8. **Social Sentiment Velocity Ingestor (C1, CAP-01)**: Aggregator for social volume velocity across X/Twitter, Reddit, and Telegram (Doc 02).

---

## 6. License Risk Analysis

| Candidate Package | License | Risk Level | Rationale & Legal Review Requirement |
|-------------------|---------|------------|--------------------------------------|
| **NautilusTrader** | LGPL-3 | **HIGH** | LGPL-3 permits dynamic linking in Python, but proprietary strategy code built on top requires legal verification to ensure source disclosure is not triggered. |
| **Neo4j Community** | GPL-3 | **HIGH** | GPL-3 imposes copyleft obligations if distributed or linked in-process. Network socket connection is acceptable, but legal review is required prior to commercial deployment. |
| **Grafana** | AGPL-3 | **MEDIUM** | AGPL-3 contains a network-use copyleft clause. Self-hosted internal use is permitted, but modified distribution requires legal check. |
| **RedPanda** | BSL 1.1 | **MEDIUM** | Business Source License transitions to Apache 2.0 after 4 years. Commercial production deployment requires checking user quota limits. |
| **OpenBao** | MPL-2.0 | **LOW** | Mozilla Public License 2.0 is a file-level copyleft license; clean separation via Python wrappers prevents copyleft contamination. |
| **LangGraph / Qdrant / MLflow / CCXT / OPA** | MIT / Apache 2.0 | **LOW** | Highly permissive commercial licenses. Zero copyleft risk. |

---

## 7. Summary of Unresolved Items & Benchmark Entry Criteria

Before formal technology selection via Architecture Decision Records (ADR) can occur, the benchmark entry criteria are prioritized as follows:

### Required Before Formal ADR (Tier 1 Benchmarks)
1. **Tier 1 Benchmark Execution**: Run empirical performance benchmarks for Groups A, B, and C under standardized synthetic load scripts to establish baseline latency, throughput, and state integrity metrics.

### Supporting Evidence (Tier 2 & Tier 3 Evaluations)
2. **PostgreSQL CTE Graph Validation (Group F)**: Test if PostgreSQL recursive CTE queries satisfy sub-50ms provenance graph retrieval without Neo4j.
3. **Security Architecture Evaluation (Group G)**: Conduct structured security evaluation of sidecar OpenBao/OPA vs embedded Python security wrappers.
4. **Supplementary Data Provider Evaluation (Group H)**: Verify WebSocket connection stability and rate-limit behavior for supplementary feeds.
5. **NautilusTrader LGPL-3 Legal Assessment**: Obtain legal confirmation regarding LGPL-3 import compliance in commercial trading contexts prior to production deployment.

---

*End of Reconciled Candidate Technology Stack.*
