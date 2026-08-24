# AIOS-0X OSS Integration Report
Version 2.0.0 | 2026-08-24 | All 74 ZIPs inspected and scored

## Executive Summary

74 open-source projects inspected. **14 ADOPT**, **19 ADAPT**, **18 REFERENCE**, **23 SKIP**.

Highest-leverage finding: **FinRL-Trading's AlpacaManager + TradeExecutor._apply_risk_checks + weight-vector contract** is a near-drop-in blueprint for our #1 gap (real broker execution). Combined with **alpaca-py** and **bt**'s AlgoStack pattern, this closes our biggest gap in ~1 sprint.

Second: **qlib's PIT data + rolling retrain + online serving** solves strategy evolution, proven at Microsoft scale.

Third: **semantica's W3C PROV-O provenance** upgrades our audit graph to standards-compliant lineage.

---

## 1. ADOPT — Integrate as dependency (14)

| # | Project | License | Take | Gap closed |
|---|---|---|---|---|
| 1 | alpaca-py | Apache-2.0 | TradingClient, StreamClient, RESTClient retry, TimeFrame enums | Broker execution, WebSocket, multi-timeframe |
| 2 | ccxt | MIT | Unified exchange API, Precise math, throttler, error taxonomy | Crypto execution, arbitrage, rate limiting |
| 3 | PyPortfolioOpt | MIT | discrete_allocation (weights→shares), Black-Litterman (LLM views→returns) | Portfolio optimization |
| 4 | bt | MIT | AlgoStack pipeline (governor veto=terminal False), AlmgrenChrissCostModel, rebalance triggers | Risk governor as pipeline stage |
| 5 | FinRL-Trading | Apache-2.0 | AlpacaManager, TradeExecutor._apply_risk_checks, weight-vector contract, benchmark_metrics, docker-compose.yml | Broker execution, benchmark, Docker |
| 6 | qdrant | Apache-2.0 | Already integrated (local mode) | Vector memory |
| 7 | mlflow | Apache-2.0 | Experiment tracking, model registry, artifacts | Experiment registry |
| 8 | langfuse | MIT | LLM tracing, prompt mgmt, cost tracking | LLM observability |
| 9 | opentelemetry-collector | Apache-2.0 | Traces/metrics/logs pipeline | Observability |
| 10 | nats-server | Apache-2.0 | JetStream durable messaging | Durable event bus |
| 11 | finnhub-python | Apache-2.0 | Endpoint checklist (news/sentiment/calendar/insider) | RAG news feeds |
| 12 | twelvedata-python | MIT | TDWebSocket self-heal, multi-interval | WebSocket resilience |
| 13 | yfinance | Apache-2.0 | Persistent cache, session rotation, failover | Data caching |
| 14 | agent-registry | Apache-2.0 | OCI registry, A2A AgentCard, promotion lifecycle | Agent roster upgrade |

## 2. ADAPT - Steal patterns (19)

| # | Project | License | What to steal | Gap |
|---|---|---|---|---|
| 15 | qlib (Microsoft) | MIT | PITProvider point-in-time data, RollingStrategy online serving, IC/RankIC evaluation, Recorder artifacts | Strategy evolution, honest backtests |
| 16 | nautilus_trader | LGPL-3.0 | calculate_fixed_risk_position_size, MessageBus topic routing, adapter pattern, Decimal-exact money | Position sizing, event bus, ledger precision |
| 17 | Lean (QuantConnect) | Apache-2.0 | IBrokerage.cs event contract, IRiskManagementModel.ManageRisk(targets), IShortableProvider | Broker adapter, governor pipeline, short selling |
| 18 | qstrader | MIT | AlphaModel.__call__(dt)->weights, PortfolioConstructionModel weight->order, fee models | Strategy-execution interface |
| 19 | Riskfolio-Lib | BSD-3 | CVaR/EVaR, constraint DSL, HTML tearsheets | Downside-aware limits |
| 20 | FinGPT | MIT | FinGPT_RAG multisource_retrieval pipeline, Forecaster prompt format | RAG news ingestion, prediction format |
| 21 | vectorbt | Apache+CC | from_signals() API, walk-forward, Telegram alerts | Fast backtester. WARNING: Commons Clause - do NOT redistribute |
| 22 | semantica | MIT | W3C PROV-O provenance (doc->chunk->entity->KG->query), audit-grade source tracking | Audit graph upgrade |
| 23 | TencentDB-Agent-Memory | Apache-2.0 | L0-L3 memory hierarchy (conversations->atomic->scenarios->profiles), hybrid retrieval, consolidation | Memory model upgrade |
| 24 | deepeval | Apache-2.0 | LLM eval metrics (faithfulness, relevance, hallucination), test framework | Prompt Lab evaluation |
| 25 | guardrails | Apache-2.0 | Validator composition (input/output guards, deterministic+LLM mixed) | Verification firewall |
| 26 | crewAI | MIT | Agent role/goal/backstory pattern, task delegation, hierarchical process | Investor personality agents |
| 27 | MetaGPT | MIT | SOP-based structured communication (documents not chat), assembly-line paradigm | Agent communication protocol |
| 28 | FinRobot | MIT | Financial agent platform (market forecasting, document analysis, trade strategy) | Financial domain agents |
| 29 | agent-governance-toolkit | MIT | Policy-as-code, permission boundaries, safety filters | Governance plane |
| 30 | datacontract-specification | MIT | Data contract schema (quality, freshness, SLA) | Data fabric contracts |
| 31 | alpha_vantage | MIT | Domain-module layout (fundamentals/technicals/FX separate) | Data layer organization |
| 32 | Horizon | MIT | News aggregation + AI summarization pipeline | News ingestion UX |
| 33 | quant-mind | MIT | Financial knowledge transformation patterns | Research center |

## 3. REFERENCE - Study ideas (18)

| # | Project | Why reference only |
|---|---|---|
| 34 | FinRL | RL research; reward-shaping template; superseded by FinRL-Trading |
| 35 | backtrader | GPL-3.0 viral - study broker-parity, do NOT integrate |
| 36 | Lean | Too large; steal IBrokerage + IRiskManagement patterns only |
| 37 | grafana | AGPL-3.0; external dashboard only |
| 38 | lakeFS | Git-like data versioning; study branching model |
| 39 | datahub | Data catalog; study discovery UX |
| 40 | llama_index | Massive RAG; study retrieval patterns, don't vendor |
| 41 | MetaGPT | Study SOP paradigm; too opinionated for direct use |
| 42 | temporal | Workflow durability; study retry/timeout semantics |
| 43 | opa | Policy-as-code; study Rego language for governance |
| 44 | openbao | Secrets management; study dynamic secrets pattern |
| 45 | neo4j | Graph DB; study Cypher patterns for audit graph |
| 46 | nebula | Graph DB alternative; compare with neo4j |
| 47 | redpanda | Kafka-compatible; benchmark target for Group C |
| 48 | abides | Market simulation; study limit order book model |
| 49 | Engine (ORE) | Institutional analytics; study risk measure definitions |
| 50 | clearml | MLOps; compare with mlflow |

## 4. SKIP (24)

buzz (audio), computer (Cloudflare), Siftly (Twitter bookmarks), pdf-inspector, paperclip (S3), rakazo (chatbot), OpenSandbox, repowise, data-formulator, ContextLattice, QuantMuse (immature), StockSim (immature), AI-Trader (immature), hermes-agent (wrong scope), OpenHands (coding agent), last30days (already using), Riskfolio duplicate, + remaining infra already categorized above.

## 5. GAP TO SOLUTION MAPPING

### Gap 1: Real Broker Execution - CLOSE THIS SPRINT
- alpaca-py TradingClient -> wrap in BaseExecutionAdapter
- FinRL-Trading AlpacaManager + _apply_risk_checks -> copy pre-trade check chain into RiskGovernor
- Lean IBrokerage.cs -> redesign adapter from request/response to event-stream
- ccxt create_order -> extend CcxtExecutionAdapter beyond stub
- nautilus calculate_fixed_risk_position_size -> wire into governor

### Gap 2: Benchmark Comparison - CLOSE THIS SPRINT
- FinRL-Trading BacktestResult.benchmark_metrics (SPY/QQQ defaults)
- Fetch SPY data via yfinance/CCXT, compute alpha in P&L workspace

### Gap 3: Docker - CLOSE THIS SPRINT
- FinRL-Trading docker-compose.yml as template
- Multi-stage build, non-root, health checks

### Gap 4: WebSocket Live Updates
- twelvedata TDWebSocket self-heal pattern (heartbeat -> reconnect ladder)
- nautilus MessageBus topic routing as the backbone
- alpaca-py StreamClient subscription management

### Gap 5: RAG News Ingestion
- FinGPT_RAG multisource_retrieval pipeline (query enrichment -> dedup -> LLM scoring)
- finnhub structured endpoints (company_news, sentiment, earnings_calendar)
- Qdrant local already wired; needs ingestion pipeline

### Gap 6: Strategy Evolution
- qlib RollingStrategy + online serving (champion/challenger with IC threshold)
- Swarm Trader AutoResearch pattern (fitness = Sharpe x 0.35 + Sortino x 0.25 + ...)
- Our challenger trials already have the governance; needs automation

### Gap 7: Investor Personality Agents
- crewAI role/goal/backstory pattern
- Swarm Trader 13 personalities (Buffett, Munger, Burry, Wood, Lynch, etc.)
- Add personality prompts to our PromptRegistry

### Gap 8: Short Selling
- Lean IShortableProvider (borrow rate query)
- qstrader long_short.py order sizer
- bt Margin/HedgeSecurity algos

### Gap 9: Telegram Alerts
- vectorbt Telegram notification approach
- Telegram Bot API (simple HTTP POST)

## 6. LICENSE WATCHLIST
- backtrader: GPL-3.0 VIRAL - never integrate
- vectorbt: Commons Clause - internal use OK, never redistribute
- grafana: AGPL-3.0 - external tool only
- nautilus_trader: LGPL-3.0 - dynamic linking OK, modifications to nautilus must be open
- Everything else: MIT/Apache/BSD - integration safe