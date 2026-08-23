# AIOS-0X OSS Catalog (Verified)
Version 1.0.0 | Source: C:\Users\nahas\OneDrive\Desktop\github reserch (73 ZIPs counted 2026-08-23)
Authoritative dispositions live in AIOS_PHASE2_SELECTION_LEDGER.md (v2.0.0). This catalog maps the physical archive to the ledger and flags integration notes. FORMAL SELECTION = 0 until Tier-1 benchmarks pass.

## 1. Physical Archive Verification
- ZIP count on disk: **73** = ledger total. Duplicates: 0. Missing: 0.

## 2. Catalog by Capability (disposition per Phase 2 ledger)

### Market Data / Broker Access
| Package | Disposition | Integration note |
|---|---|---|
| ccxt-master | RESEARCH-PREFERENCE (94) | Primary crypto exchange adapter behind BaseDataFetcher/BaseExecutionAdapter ABCs |
| alpaca-py-master | RESEARCH-PREFERENCE (86) | US equities adapter; same ABC boundary |
| client-python-master (Polygon.io) | BENCHMARK-CANDIDATE | Paid license required; Group H |
| twelvedata-python-master | BENCHMARK-CANDIDATE | Group H supplementary data |
| finnhub-python-master | BENCHMARK-CANDIDATE | Group H supplementary data |
| alpha_vantage-develop | BENCHMARK-CANDIDATE | Group H supplementary data |
| yfinance-main | REJECTED | ToS/reliability risk - do not integrate |

### Backtesting / Simulation
| Package | Disposition | Integration note |
|---|---|---|
| nautilus_trader-develop | RESEARCH-PREFERENCE (89, LGPL legal review) | Group B benchmark; event-native matches our architecture |
| Lean-master | BENCHMARK-CANDIDATE (88) | C# runtime; heavier integration |
| vectorbt-master | BENCHMARK-CANDIDATE | Fast array backtests; research tooling |
| backtrader-master, bt-master, qstrader-master | REJECTED | Unmaintained/GPL or stale |
| abides-master | REFERENCE | Market-simulation reference for SIM lab |
| StockSim-main | REJECTED | Immature |

### Orchestration / Agents
| Package | Disposition | Integration note |
|---|---|---|
| langgraph-main | RESEARCH-PREFERENCE (91) | Group A benchmark; graph orchestration fits community mesh |
| crewAI-main | BENCHMARK-CANDIDATE (86) | Group A |
| agent-framework-main (MS) | BENCHMARK-CANDIDATE | Group A |
| opengeni-main | BENCHMARK-CANDIDATE | Group A |
| langchain ecosystem (llama_index-main) | BENCHMARK-CANDIDATE (90) | Retrieval abstraction Group I |
| MetaGPT-main, agentscope-main, deepagents-main, OpenHands-main, hermes-agent-main, computer-main, paperclip-master, buzz-main | STUDY/REFERENCE | Patterns only; no direct integration path |
| AI-Trader-main, FinRobot-master, QuantMuse-main, quant-mind-master, MiroFish-main, Horizon-main, ContextLattice-main, semantica-main | STUDY | LLM-trading research references for C2/C10 design |

### Messaging / Streaming
| Package | Disposition | Integration note |
|---|---|---|
| nats-server-main | RESEARCH-PREFERENCE (96) | Group C benchmark; durable bus implementing BaseEventBus |
| redpanda-dev | BENCHMARK-CANDIDATE | Group C (BSL license note) |
| temporal-main | BENCHMARK-CANDIDATE | Workflow durability (Group J) |

### Storage / Memory
| Package | Disposition | Integration note |
|---|---|---|
| qdrant-master | RESEARCH-PREFERENCE (94) | Vector memory behind BaseVectorMemory ABC (to be created in core/) |
| neo4j-2026.06 | BENCHMARK-CANDIDATE (GPL-3 legal review) | Audit-graph Group F; PostgreSQL recursive CTE is baseline competitor |
| nebula-master | BENCHMARK-CANDIDATE | Graph alternative |
| TencentDB-Agent-Memory-feat-server_team | STUDY | Agent-memory design patterns |
| lakeFS-master, datahub-master | DEFERRED (Phase 4-5) | Data versioning/catalog at scale |

### Quant / Portfolio Math
| Package | Disposition | Integration note |
|---|---|---|
| PyPortfolioOpt-master | RESEARCH-PREFERENCE (90) | C9 allocation math behind portfolio ABC |
| Riskfolio-Lib-master | BENCHMARK-CANDIDATE | Group D comparison |
| Engine-master (ORE) | BENCHMARK-CANDIDATE | Institutional analytics reference |
| FinRL-master, FinRL-Trading-master, FinGPT-master, qlib-main | STUDY | RL/features research inputs for Strategy Lab |

### Governance / Security / Policy
| Package | Disposition | Integration note |
|---|---|---|
| opa-main | RESEARCH-PREFERENCE (92) | Policy-as-code for permissions/compliance rules |
| openbao-main | RESEARCH-PREFERENCE (88) | Secrets vault (MPL-2.0); local dev fallback = env vars |
| guardrails-main | BENCHMARK-CANDIDATE | LLM output validation (Group K) vs Pydantic-first approach |
| agent-governance-toolkit-main, agent-registry-main | STUDY | Governance patterns for C12 |

### Observability / MLOps
| Package | Disposition | Integration note |
|---|---|---|
| mlflow-master | RESEARCH-PREFERENCE (92) | Experiment/model registry per Doc 17 (Group E) |
| clearml-master | BENCHMARK-CANDIDATE | Group E alternative |
| langfuse-main | RESEARCH-PREFERENCE (88) | LLM tracing/prompts (Group CG-10) |
| opentelemetry-collector-main | RESEARCH-PREFERENCE (94) | Metrics/traces backbone |
| grafana-main | RESEARCH-PREFERENCE (90, AGPL note) | Dashboards; server-side AGPL consideration |
| deepeval-main | BENCHMARK-CANDIDATE | Prompt/agent eval harness (Group K) |
| last30days.zip | REFERENCE | Social/research signal sampling utility |

## 3. Build-vs-Buy Conclusion (unchanged from Phase 2, ratified here)
CUSTOM BUILD (no adequate OSS): Adversarial Debate Engine; Risk Governor extensions; TWAP/VWAP slicer;
Agent Lifecycle & Reputation; Verification Auto-Tuner; Synthetic Market Generator; Audit Graph API;
Sentiment-Velocity Ingestor; Expectation Engine; Participant Model; Accounting/Tax/Fund-Admin cores.

## 4. License Watchlist (legal review before selection)
NautilusTrader (LGPL-3, dynamic linking), Neo4j (GPL-3), Grafana (AGPL-3), Redpanda (BSL 1.1),
Redis-class alternatives (RSALv2/SSPL if chosen). All tracked in Phase 2B protocol Section: LEGL.
