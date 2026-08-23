# AIOS Phase 2 — Reconciled Selection Ledger
**Document Version**: 2.0.0
**Status**: Reconciled Phase 2 Research Artifact (Evidence-Based Research Preferences — FORMAL SELECTION = 0)
**Created**: 2026-08-18
**Authoritative Reference**: Frozen Phase 1 Architecture (ADR-001)

---

## 1. Document Control & Decision Rules

This ledger contains the complete, reconciled evaluation of all 73 open-source candidate packages found in the research universe (`C:\Users\nahas\OneDrive\Desktop\github reserch`).

### Key Governance Constraints:
1. **FORMAL SELECTION = 0**: "SELECTED" is strictly reserved for post-benchmark formal Architecture Decision Records (ADRs). No technology is marked `SELECTED` at this stage.
2. **"RESEARCH-PREFERENCE"**: Indicates the current primary candidate based on evidence, pending empirical benchmarking and/or formal ADR.
3. **BENCHMARK STATUS CONTROLLED VOCABULARY**:
   - `NOT-BENCHMARKED` (default state prior to benchmark execution)
   - `BENCHMARK-REQUIRED` (candidate belongs to an active benchmark competition group)
   - `BENCHMARK-NOT-REQUIRED` (uncontested baseline or infrastructure tool)
   - `BENCHMARK-FAILED` (failed benchmark evaluation)
   - `PENDING-INSPECTION` (requires deep source review)
4. **EXACTLY 73 ROWS**: Every candidate ZIP in the research universe appears exactly once with exactly ONE Primary Disposition.

---

## 2. Quantitative Evaluation Rubric (Doc 16)

$$Score = 0.30 \cdot P + 0.25 \cdot R + 0.20 \cdot I + 0.15 \cdot M + 0.10 \cdot L$$

- **P**: Performance & Latency (30 pts)
- **R**: Reliability & Maturity (25 pts)
- **I**: Integration Ease (20 pts)
- **M**: Maintainability & Docs (15 pts)
- **L**: Permissive Licensing (10 pts)

---

## 3. Master Candidate Reconciliation Table (73 Candidates)

| # | Canonical Name | ZIP File | AIOS Capability | Layer | Coverage | Evidence | Confidence | Total Score | License Risk | Primary Disposition | Research Value | Benchmark Status | Competition Group | Decision Rationale & Notes |
|---|---------------|----------|-----------------|-------|----------|----------|------------|-------------|--------------|---------------------|----------------|------------------|-------------------|----------------------------|
| 1 | CCXT | ccxt-master.zip | Market Data Ingestion & Live Execution | C1, C5 | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 94 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-NOT-REQUIRED | GROUP H (Baseline) | Standard unified crypto exchange gateway (100+ exchanges). REST+WS support. MIT license. |
| 2 | alpaca-py | alpaca-py-master.zip | US Equities Data & Paper Broker | C1, C5, Continuous Training | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 86 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-NOT-REQUIRED | GROUP H (Baseline) | Official Alpaca Python SDK. Equities/crypto REST & WS API + paper trading gateway. Apache 2.0. |
| 3 | LangGraph | langgraph-main.zip | Multi-Agent DAG Orchestration | C2, C3, C4, C8 | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 91 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-REQUIRED | GROUP A | Best-in-class state graph for cyclic multi-agent DAGs with non-linear feedback loops. MIT. |
| 4 | CrewAI | crewAI-main.zip | Role-Based Multi-Agent Orchestration | C2, C4, C8 | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 86 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP A | Role-based agent crews (Bull/Bear debate). Benchmarked against LangGraph for cyclic DAG fit. MIT. |
| 5 | LlamaIndex | llama_index-main.zip | RAG & Vector Memory Indexing | C2, C7 | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 90 | LOW | **BENCHMARK-CANDIDATE** | COMPLEMENTARY | BENCHMARK-REQUIRED | GROUP I (Retrieval Abstraction) | Optional retrieval/indexing abstraction over Qdrant. Evaluated for memory retrieval, chunking, and metadata filtering in C7. MIT. |
| 6 | NautilusTrader | nautilus_trader-develop.zip | High-Performance Backtesting & Execution | Continuous Training, C5 | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 89 | REQUIRES-LEGAL-REVIEW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-REQUIRED | GROUP B (Primary Backtest) | Rust-core event-driven backtesting engine with Python API. Primary backtest competitor. LGPL-3 license requires legal review. |
| 7 | LEAN (QuantConnect) | Lean-master.zip | Multi-Asset Backtesting Platform | Continuous Training | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 89 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP B (Primary Backtest) | Battle-tested C# multi-asset backtesting platform. Primary backtest competitor. Apache 2.0. |
| 8 | VectorBT | vectorbt-master.zip | Vectorized Backtesting & Screening | Continuous Training | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 94 | LOW | **BENCHMARK-CANDIDATE** | COMPLEMENTARY | BENCHMARK-REQUIRED | GROUP B (Primary Backtest) | NumPy/Numba vectorized backtester for fast parameter sweeps. Primary backtest competitor. Apache 2.0. |
| 9 | Qdrant | qdrant-master.zip | Dense Vector Semantic Memory | C7 | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 94 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-NOT-REQUIRED | GROUP I (Vector Layer Baseline) | Named in Phase 1 arch. Vector/storage layer baseline; Rust-core; 768-dim embeddings; metadata payload filtering. Apache 2.0. |
| 10 | MLflow | mlflow-master.zip | Experiment & Model Registry | Doc 17 (Registries) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 92 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-REQUIRED | GROUP E | Industry standard experiment tracking and model registry. Apache 2.0. Maps to ExperimentRecord schema. |
| 11 | ClearML | clearml-master.zip | MLOps & Experiment Registry | Doc 17 (Registries) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 87 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP E | Full MLOps suite with experiment tracking and model versioning. Apache 2.0. Benchmarked against MLflow. |
| 12 | NATS JetStream | nats-server-main.zip | Enterprise Pub/Sub Event Bus | Event Bus (Enterprise) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 96 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-REQUIRED | GROUP C | Sub-millisecond latency broker with JetStream persistence, subject routing, and native DLQ. Apache 2.0. |
| 13 | RedPanda | redpanda-dev.zip | Kafka-Compatible Streaming Engine | Event Bus (Enterprise) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 93 | REQUIRES-LEGAL-REVIEW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP C | High-throughput C++ Kafka-compatible streaming. BSL license requires commercial use review. |
| 14 | LangFuse | langfuse-main.zip | LLM Observability & Cost Tracing | Doc 11 (Observability) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 88 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-NOT-REQUIRED | CG-10A | Named in Phase 1. Prompt tracing, token cost calculation, latency breakdown, self-hostable. MIT. |
| 15 | Grafana | grafana-main.zip | Metrics & Infrastructure Dashboards | Doc 11 (Observability) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 90 | REQUIRES-LEGAL-REVIEW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-NOT-REQUIRED | CG-10B | Named in Phase 1. Prometheus scraping, real-time alert rules, system metrics dashboards. AGPL-3. |
| 16 | OpenTelemetry Collector | opentelemetry-collector-main.zip | Distributed Event Tracing | Doc 11 (Observability) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 94 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-NOT-REQUIRED | CG-10C | Named in Phase 1. OpenTelemetry collector for tracing event propagation across community handlers. Apache 2.0. |
| 17 | OpenBao | openbao-main.zip | Dynamic Secrets & Security Vault | Doc 11 (Security) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 88 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-REQUIRED | GROUP G | Open-source fork of HashiCorp Vault (MPL-2.0). Dynamic secrets, API key encryption, AES-256 at rest. |
| 18 | Open Policy Agent (OPA) | opa-main.zip | Policy Engine & Access Control | Doc 11, Doc 12 (AI Constitution)| FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 92 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-REQUIRED | GROUP G | CNCF policy engine using Rego. Enforces AI Constitution Law 2 & gateway access rules. Apache 2.0. |
| 19 | PyPortfolioOpt | PyPortfolioOpt-main.zip | Portfolio Capital Allocation | C9 | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 90 | LOW | **RESEARCH-PREFERENCE** | PRIMARY | BENCHMARK-REQUIRED | GROUP D | Fractional Kelly Criterion, mean-variance optimization, risk parity, asset correlation caps. MIT. |
| 20 | Riskfolio-Lib | Riskfolio-Lib-master.zip | Portfolio Risk Optimization | C9 | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 89 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP D | Advanced risk budgeting, CVaR, hierarchical risk parity. BSD-3. Benchmarked against PyPortfolioOpt. |
| 21 | DataHub | datahub-master.zip | Enterprise Data Lineage | CAP-15 (Provenance) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 83 | LOW | **DEFERRED** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-07B, CG-15B | Platform data lineage catalog. Apache 2.0. Deferred to Phase 4-5 enterprise deployment. |
| 22 | LakeFS | lakeFS-master.zip | Data Lake Versioning | CAP-07 (Data Versioning) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 83 | LOW | **DEFERRED** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-07B | Git-like dataset versioning for data lakes. Apache 2.0. Deferred to Phase 4-5 training pipeline. |
| 23 | Neo4j | neo4j-2026.06.zip | Property Graph Database | CAP-15 (Audit Graph) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 88 | REQUIRES-LEGAL-REVIEW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP F | Cypher query graph DB for decision provenance. Community Edition is GPL-3 (legal review required). |
| 24 | NebulaGraph | nebula-master.zip | Distributed Graph Database | CAP-15 (Audit Graph) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | MEDIUM | 80 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP F | Distributed graph database using GQL. Apache 2.0. Benchmarked against Neo4j and PostgreSQL CTEs. |
| 25 | ABIDES | abides-master.zip | Agent-Based Market Simulator | Continuous Training (Digital Twin) | FULL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 86 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP B (Simulation Reference) | Interactive Discrete Event Simulator evaluated for digital-twin / market-simulation reference (not direct backtest competitor). BSD-3. |
| 26 | DeepEval | deepeval-main.zip | LLM Output Quality Evaluation | C3 (Verification Audit) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 85 | LOW | **BENCHMARK-CANDIDATE** | COMPLEMENTARY | BENCHMARK-REQUIRED | GROUP K (Supporting Evaluation) | Automated LLM evaluation framework. Supporting evaluation tool for C3 (does not replace deterministic AIOS Risk Firewall). Apache 2.0. |
| 27 | Guardrails AI | guardrails-main.zip | LLM Output Validation | C3 (Quality Firewall) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 84 | LOW | **BENCHMARK-CANDIDATE** | COMPLEMENTARY | BENCHMARK-REQUIRED | GROUP K (Supporting Validation) | Structured validation for LLM outputs. Supporting validation tool for C3 (does not replace deterministic AIOS Risk Firewall). Apache 2.0. |
| 28 | Temporal | temporal-main.zip | Durable Workflow Execution Engine | C8 (Evolution Loops) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 90 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP J | Durable execution engine for long-running C8 evolution & agent lifecycle tasks. MIT. |
| 29 | MetaGPT | MetaGPT-main.zip | Multi-Agent SOP Framework | C2 (Research Debate) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 83 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03A | Multi-agent framework with Standard Operating Procedures. MIT. Evaluated as research study. |
| 30 | FinGPT | FinGPT-master.zip | Financial LLM Fine-Tuning | C2, C1 (Sentiment) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | MEDIUM | 77 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-01D, CG-01F | Open-source financial LLM fine-tuning pipelines and sentiment models. MIT. Study value. |
| 31 | FinRobot | FinRobot-master.zip | AI Agentic Finance Platform | C2 (Research Patterns) | PARTIAL | SOURCE_CODE | MEDIUM | 75 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-01D, CG-03C | Financial agent platform built on LangChain. MIT. Study value for financial agent prompts. |
| 32 | FinRL | FinRL-master.zip | Reinforcement Learning for Finance | C8 (Evolution) | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | MEDIUM | 80 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04C, CG-12B | Deep RL framework for quantitative trading. MIT. Study value for agent policy evolution. |
| 33 | FinRL-Trading | FinRL-Trading-master.zip | Extended FinRL Trading Environments | C8 (Evolution) | PARTIAL | SOURCE_CODE | MEDIUM | 75 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04C | Extended trading environments for FinRL. MIT. Study value for synthetic training environments. |
| 34 | Backtrader | backtrader-master.zip | Legacy Python Backtester | Continuous Training | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 83 | LOW | **REJECTED** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-04A | Python backtesting framework. Unmaintained; superseded by NautilusTrader & VectorBT. GPL-3. |
| 35 | bt | bt-master.zip | Flexible Backtesting for Python | Continuous Training | PARTIAL | SOURCE_CODE | HIGH | 79 | LOW | **REJECTED** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04B | High-level backtest framework. Superseded by VectorBT for vectorized performance. MIT. |
| 36 | QStrader | qstrader-master.zip | Academic Quantitative Backtester | Continuous Training | PARTIAL | SOURCE_CODE | MEDIUM | 73 | LOW | **REJECTED** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04A | Academic event-driven backtester. Insufficient scale and features for AIOS. MIT. |
| 37 | Barter-rs | barter-rs-main.zip | Rust Quantitative Trading Engine | Continuous Training, C5 | PARTIAL | SOURCE_CODE | MEDIUM | 77 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04A, CG-05A | Rust trading and backtesting engine. MIT. Study value for Rust trading architecture. |
| 38 | Qlib | qlib-main.zip | Quant AI Research Platform | C4, CAP-14 | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 85 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04C, CG-14B | Microsoft Qlib quant ML platform. MIT. Study value for factor research and alpha models. |
| 39 | DataContract Specification | datacontract-specification-main.zip | Data Contract Specification | C1 (Contracts) | PARTIAL | SOURCE_CODE | HIGH | 79 | LOW | **REFERENCE** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-07C | Data contract specification tool. MIT. Reference pattern for Pydantic schema validation. |
| 40 | Alpha Vantage | alpha_vantage-develop.zip | Financial Data API Client | C1 (Stocks, Forex, Macro) | PARTIAL | SOURCE_CODE | HIGH | 78 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP H | Python API wrapper for Alpha Vantage. MIT. Benchmarked for supplementary macro data. |
| 41 | Twelve Data | twelvedata-python-master.zip | Real-Time Market Data API | C1 (Bars, Ticks, News) | PARTIAL | SOURCE_CODE | HIGH | 83 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP H | Python client for Twelve Data REST + WebSocket API. MIT. Benchmarked for market feed coverage. |
| 42 | Finnhub | finnhub-python-master.zip | Market News & Fundamentals API | C1 (News, Fundamentals) | PARTIAL | SOURCE_CODE | HIGH | 78 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP H | Python client for Finnhub REST API. Apache 2.0. Benchmarked for news/sentiment feeds. |
| 43 | yfinance | yfinance-main.zip | Yahoo Finance Data Scraper | C1 | PARTIAL | SOURCE_CODE | HIGH | 72 | REQUIRES-LEGAL-REVIEW | **REJECTED** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-01C | Unofficial Yahoo Finance scraper. Apache 2.0. Rejected due to ToS and reliability risks. |
| 44 | client-python (Polygon.io) | client-python-master.zip | Institutional Market Data API | C1 (Ticks, Bars) | PARTIAL | SOURCE_CODE | MEDIUM | 87 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP H | Python client for Polygon.io REST & WebSocket API. MIT. Benchmarked for equities tick data. |
| 45 | AgentScope | agentscope-main.zip | Multi-Agent Application Platform | C2, C3 | PARTIAL | SOURCE_CODE | MEDIUM | 77 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03A | Alibaba multi-agent platform. Apache 2.0. Study value for agent communication protocols. |
| 46 | Hermes Agent | hermes-agent-main.zip | Autonomous Agent Environment | C2, C8 | PARTIAL | SOURCE_CODE | LOW | 73 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03C | Nous Research autonomous agent platform. MIT. Inspected: study value for agent prompts. |
| 47 | TencentDB Agent Memory | TencentDB-Agent-Memory-feat-server_team.zip | Agent Memory Infrastructure | C7 (Memory) | PARTIAL | SOURCE_CODE | MEDIUM | 72 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-06C | Tencent agent memory architecture. Inspected: study value for multi-tier memory layout. |
| 48 | DeepAgents | deepagents-main.zip | Deep Research Agent System | C2 (Research) | PARTIAL | SOURCE_CODE | LOW | 71 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03C | Autonomous deep research agent framework. MIT. Study value for research agent workflows. |
| 49 | OpenHands | OpenHands-main.zip | Software Development Agent System | C8 | PARTIAL | SOURCE_CODE + OFFICIAL_DOCS | HIGH | 85 | LOW | **REFERENCE** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-03C | Autonomous coding agent platform. MIT. Reference model for autonomous agent task execution. |
| 50 | agent-framework | agent-framework-main.zip | Microsoft Agent Framework | C2, C3, C4 | PARTIAL | SOURCE_CODE | MEDIUM | 79 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP A | Microsoft Agent Framework (Python/TS SDK). MIT. Inspected: benchmarked for persistent agent state. |
| 51 | agent-governance-toolkit | agent-governance-toolkit-main.zip | Agent Governance Framework | C8, Doc 13 | PARTIAL | SOURCE_CODE | MEDIUM | 72 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-12A | Agent governance patterns. Inspected: study value for AIOS agent lifecycle implementation. |
| 52 | agent-registry | agent-registry-main.zip | Agent Registry & Discovery | CAP-14 | PARTIAL | SOURCE_CODE | MEDIUM | 68 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-12A | Agent discovery registry. Inspected: study value for model & agent registry contracts. |
| 53 | OpenGeni | opengeni-main.zip | Enterprise Agentic Platform Runtime | C3, C8, CAP-12 | PARTIAL | SOURCE_CODE | MEDIUM | 78 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP A | OpenGeni agent runtime platform. Inspected: Rust/TS agent harness, WASM kernel, observability dashboards. |
| 54 | Semantica | semantica-main.zip | Semantic Knowledge Engine | C2, C7 | PARTIAL | SOURCE_CODE | LOW | 71 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03B | Semantic text extraction engine. MIT. Study value for unstructured research processing. |
| 55 | ContextLattice | ContextLattice-main.zip | LLM Context Management System | C2, C3 | PARTIAL | SOURCE_CODE | LOW | 71 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03B | Context window optimization for LLMs. Inspected: study value for debate agent prompt buffers. |
| 56 | Rakazo | rakazo-main.zip | AI Teammate Runtime (Grok Alternative) | C2, C8 | PARTIAL | SOURCE_CODE | LOW | 72 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03C | Open-source Grok bot / AI teammate framework built with Cursor/Grok. Inspected: study value. |
| 57 | Last30Days | last30days.zip | Market News & X/Twitter Search Agent | C1, C2 | PARTIAL | SOURCE_CODE | LOW | 74 | LOW | **REFERENCE** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-01D | X/Twitter 30-day search agent & skill. Inspected: reference for social sentiment ingestion. |
| 58 | PDF Inspector | pdf-inspector-main.zip | PDF Document Inspector | C2 | PARTIAL | SOURCE_CODE | MEDIUM | 75 | LOW | **REFERENCE** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-01D | PDF parsing and inspection utility. MIT. Reference for research document parsing. |
| 59 | Data Formulator | data-formulator-main.zip | Data Transformation & Visualization | Research | PARTIAL | SOURCE_CODE | LOW | 69 | LOW | **REFERENCE** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-07E | Data visualization tool (Microsoft Research). MIT. Reference utility for analyst UI. |
| 60 | Book-to-Skill | book-to-skill-master.zip | Document-to-Skill Extractor | C8 | PARTIAL | SOURCE_CODE | LOW | 65 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-12B | Extracts agent skills from documents. Inspected: study value for agent evolution skills. |
| 61 | Buzz | buzz-main.zip | Audio Speech-to-Text Transcriber | None | NONE | README_ONLY | HIGH | N/A | LOW | **REJECTED** | NONE | BENCHMARK-NOT-REQUIRED | N/A | Open-source Whisper desktop transcription tool. MIT. Rejected as completely irrelevant to AIOS. |
| 62 | Cloudflare Computer | computer-main.zip | Virtual Filesystem in Durable Objects | Infrastructure | PARTIAL | SOURCE_CODE | LOW | 65 | LOW | **REJECTED** | STUDY | BENCHMARK-NOT-REQUIRED | N/A | Virtual filesystem inside Cloudflare Durable Objects. MIT. Inspected: rejected for Python backend. |
| 63 | Open Source Risk Engine (ORE) | Engine-master.zip | Financial Risk Analytics Engine | C4, C9, CAP-11 | FULL | SOURCE_CODE | HIGH | 86 | LOW | **BENCHMARK-CANDIDATE** | SECONDARY | BENCHMARK-REQUIRED | GROUP D | Open Source Risk Engine (ORE). C++/Python financial risk analytics, Value at Risk (VaR), stress testing. BSD-3. |
| 64 | MiroFish | MiroFish-main.zip | Multi-Agent Prediction & Simulation | C2, C4 | PARTIAL | SOURCE_CODE | MEDIUM | 74 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03C | Multi-agent AI prediction and market simulation system. Inspected: study value for C2 debate models. |
| 65 | StockSim | StockSim-main.zip | Basic Stock Market Simulator | Continuous Training | PARTIAL | SOURCE_CODE | LOW | 62 | LOW | **REJECTED** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04D | Basic stock trading simulator. Insufficient features and fidelity for AIOS requirements. MIT. |
| 66 | AI-Trader | AI-Trader-main.zip | Small AI Trading Agent | C5 | PARTIAL | SOURCE_CODE | LOW | 63 | LOW | **REJECTED** | STUDY | BENCHMARK-NOT-REQUIRED | CG-05B | Small AI trading agent repository. Immature codebase and zero test suite. MIT. Rejected. |
| 67 | QuantMuse | QuantMuse-main.zip | Quantitative Trading System | C4, C5 | PARTIAL | SOURCE_CODE | MEDIUM | 76 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04A | Quantitative trading system with AI analysis & risk management. Inspected: study value. MIT. |
| 68 | QuantMind | quant-mind-master.zip | Financial Knowledge Transformation System | C2, C4 | PARTIAL | SOURCE_CODE | MEDIUM | 75 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03C | System transforming financial knowledge into actionable insights. Inspected: study value. MIT. |
| 69 | Siftly | Siftly-main.zip | X/Twitter Bookmark Manager | C1 (Social Data) | PARTIAL | SOURCE_CODE | LOW | 72 | LOW | **REFERENCE** | REFERENCE | BENCHMARK-NOT-REQUIRED | CG-01D | Self-hosted X/Twitter bookmark manager with AI tagging. Inspected: reference pattern for social feed ingestion. |
| 70 | Paperclip | paperclip-master.zip | Agent Orchestration & Page Publisher | C2, C8 | PARTIAL | SOURCE_CODE | HIGH | 82 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-03A | Agent orchestration and paperclip skill runtime. Inspected: study value for agent skill deployment. |
| 71 | Horizon | Horizon-main.zip | RL Environment for Decision Making | Continuous Training | PARTIAL | SOURCE_CODE | MEDIUM | 71 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04D | Open-source RL platform for decision making. Apache 2.0. Study value for RL continuous training. |
| 72 | OpenSandbox | OpenSandbox-main.zip | Trading Simulation Sandbox | Continuous Training | PARTIAL | SOURCE_CODE | MEDIUM | 73 | LOW | **STUDY** | STUDY | BENCHMARK-NOT-REQUIRED | CG-04D | Trading simulation sandbox environment. Apache 2.0. Study value for Continuous Training sandbox. |
| 73 | Repowise | repowise-main.zip | Repository Code Analysis Agent | None | NONE | SOURCE_CODE | LOW | N/A | LOW | **REJECTED** | NONE | BENCHMARK-NOT-REQUIRED | N/A | Repository analysis agent. Apache 2.0. Rejected as irrelevant to AIOS financial trading platform. |

---

## 4. Disposition Summary & Reconciliation Check

```
===================================================================================
                  MASTER DISPOSITION RECONCILIATION SUMMARY
===================================================================================
TOTAL CANDIDATES IN RESEARCH UNIVERSE: ......... 73
FORMAL SELECTED (Post-Benchmark): .............. 0  (Mandatory Constraint Met)
DUPLICATE ROWS: ................................ 0
MISSING ROWS: .................................. 0

-----------------------------------------------------------------------------------
PRIMARY DISPOSITION TALLY
-----------------------------------------------------------------------------------
1. RESEARCH-PREFERENCE (Primary Candidates): ... 13
2. BENCHMARK-CANDIDATE (Active Benchmark): ..... 20
3. STUDY (Architecture & Concept Study): ....... 23
4. REFERENCE (Implementation Reference): ........ 6
5. DEFERRED (Phase 4-5 Enterprise Scope): ...... 2
6. REJECTED (Unsuitable / Irrelevant): ......... 9
7. ADAPT: ...................................... 0  (Subsumed cleanly under STUDY/REFERENCE)
8. PENDING (Uninspected): ...................... 0  (All 73 inspected and reconciled)
-----------------------------------------------------------------------------------
TOTAL PRIMARY DISPOSITIONS: .................... 73  (Mathematical Match: 13+20+23+6+2+9 = 73)
===================================================================================
```

---

*End of Reconciled Selection Ledger. All 73 candidates accounted for.*
