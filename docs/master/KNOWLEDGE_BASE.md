# AIOS-0X Complete Knowledge Base
Last updated: 2026-08-24 | This file contains 100% of project context for session continuity.

## 1. PROJECT IDENTITY

- **Name**: AIOS-0X
- **Path**: C:\Users\nahas\OneDrive\Desktop\AIOS-0X
- **OSS Research**: C:\Users\nahas\OneDrive\Desktop\github reserch (74 zips)
- **What it is**: AI-native investment/trading operating system
- **What it is NOT**: a trading bot, a dashboard, a chatbot
- **Current status**: Prototype complete (Phases 0-2 of original architecture), kernel built (Phase A), data architecture built (Phase B)
- **Original architecture**: 6 planes (Experience, Control, Intelligence, Research, Execution, Deterministic Authority) + Data/State + Infrastructure
- **Key principle**: AI generates → AIOS validates → Policy constrains → Risk authorizes → State controls → Execution acts → Provenance remembers → Post-mortem learns

## 2. CURRENT STATE (exact)

- **Tests**: 194 passed, 1 skipped (PG active) / 181+5 hermetic
- **Source files**: 85 Python files across core/, kernel/, schemas/, communities/, simulation/, evaluation/, research/, api/
- **Git commits**: ~25 from baseline `3c303d7` to latest
- **Python**: 3.14.4 on win32
- **Key deps**: pydantic==2.12.5, ccxt==4.5.74, qdrant-client==1.19.0, httpx, pydantic-settings==2.13.1

### Git log (chronological)
```
3c303d7 Baseline: pristine pre-hardening state
063fed2 Phase 0.5: fix D1-D7 defects, ADR-002/003, packaging
5f18c64 Phase 1: honest vertical slice (replay, ledger, predictions, postmortems)
cfb1a1a Phase 2: intelligence onboarding (gateway, router, prompts, debate, hallucination detection)
2e11e94 Phase 3: data fabric & world intelligence (CCXT live, anomalies, expectation/scenario engines)
b72c3ea Phase 4: quant research & strategy lab (governor gate, multi-family, opportunity ranking)
4fbf37a Phase 5: execution & risk hardening (order lifecycle, kill switch, reconciliation, shadow mode)
916c411 Phase 6: finance back office (ledger, tax lots, CA review, compliance, audit graph)
ac50834 Phase 7: control plane & command center (RBAC, API, UI, Prometheus)
63fc805 Phase 8: evolution & resilience (challenger trials, reputation, disaster drills)
aadc801 Live provider integrations (LLM, Finnhub, FRED, composite fetcher)
28d393c Production hardening (constitution, CCXT execution suite, walk-forward)
b088f1f Phase 2.0-4.0 checkpoint closure (Group A benchmark, Qdrant, bus baseline)
875c4d5 fix: benchmark script paths
9493313 Competitive analysis (vs TradingAgents/Samvid/Swarm/Thales/Nexus)
3b07b12 Sprint plan (4 sprints)
421ed68 Sprint 1+2: SPY benchmark, Docker, Telegram, graduation, personality agents, RAG
6d222c6 UI/UX depth pass (charts, P&L, Strategy Center, CA, Alerts, presets, grouped search)
a081e52 Architecture gap analysis (prototype ~15% of original vision)
68a86ff AIOS Kernel Phase A (identity, capability, state machine, authority, receipts, provenance, promotion/rollback)
a3cdb25 Phase B: Data Architecture (dataset/feature/model/experiment registries)
```

## 3. ARCHITECTURE — WHAT EXISTS

### 3.1 AIOS Kernel (kernel/)
The operating system primitives. Everything registers here.

| File | Component | Key classes |
|---|---|---|
| `kernel/identity.py` | Identity Model | `Actor`, `ActorType`, `Role`, `IdentityRegistry` |
| `kernel/capability.py` | Capability Router | `CapabilitySpec`, `CapabilityRouter` (declare→register→resolve) |
| `kernel/state_machine.py` | State Machine Engine | `StateMachineDefinition`, `StateMachineEngine`, `TransitionError` |
| `kernel/authority.py` | Authority Gateway | `AuthorityRequest`, `AuthorityResult`, `AuthorityGateway` (ONLY path to mutation) |
| `kernel/receipts.py` | Decision Receipts | `Decision`, `DecisionReceipt`, `ReceiptStore` |
| `kernel/provenance.py` | Provenance Graph | `NodeType`, `ProvenanceNode`, `ProvenanceEdge`, `ProvenanceGraph` (forward/backward traversal) |
| `kernel/promotion.py` | Promotion + Rollback | `PromotionController`, `RollbackController`, `PromotionState` |
| `kernel/bootstrap.py` | Bootstrap | `create_kernel()` → `AIOSKernel` (wires everything, registers 3 lifecycles) |
| `kernel/registries.py` | Data Registries | `DatasetRegistry`, `FeatureRegistry`, `ModelRegistry`, `ExperimentRegistry` |
| `kernel/memory_log.py` | Trading Memory | `TradingMemoryLog` (pending→resolved, two-tier retrieval, from TradingAgents) |
| `kernel/config.py` | Settings | `Settings` (pydantic-settings, .env) |
| `kernel/model_gateway.py` | LLM Gateway | `OpenAICompatibleGateway`, `AnthropicGateway`, `ScriptedModel`, `complete_structured()` |
| `kernel/model_router.py` | Model Router | `ModelRouter`, `TaskTier` (CHEAP/REASONING) |
| `kernel/prompts.py` | Prompt Registry | `PromptSpec`, `PromptRegistry`, 8 built-in prompts |
| `kernel/security.py` | ACL | `ACLBus`, `AgentPrincipal` |
| `kernel/risk_governor.py` | Emergency Machine | `RiskGovernor`, `load_lockout_from_store` |
| `kernel/notifications.py` | Telegram | `TelegramNotifier`, `NotificationHub` |
| `kernel/control_plane.py` | RBAC Console | `ControlPlane`, `OperatorRole`, `ControlAction` |
| `kernel/challenger.py` | Challenger | `ChallengeRegistry`, `ChallengerTrial`, `TrialState` |
| `kernel/reputation.py` | Reputation | `compute_reputations()` |
| `kernel/data_quality.py` | Quality | `AnomalyDetector`, `SymbolHealthRegistry` |
| `kernel/persistence.py` | Store | `SqliteMemoryStore` (hash-chained event log + typed tables) |
| `kernel/constitution.py` | Constitution | `enforce_at_boot()`, `_PINNED_SHA256` |
| `kernel/agents.py` | Agent Registry | `AgentIdentity`, `register_roster()` |
| `kernel/vector_memory.py` | Vector Memory | `BaseVectorMemory`, `QdrantLocalMemory`, `InMemoryVectorMemory` |

### 3.2 Communities (communities/)
| Directory | Purpose | Key files |
|---|---|---|
| `c1_data/` | Data Fabric | `data_agent.py`, `replay_fetcher.py`, `ccxt_fetcher.py`, `news_providers.py` |
| `c2_research/` | Research | `research_agent.py`, `debate_engine.py` |
| `c3_verification/` | Verification | `verification_agent.py` (numeric hallucination detection) |
| `c4_strategy/` | Strategy | `strategy_agent.py`, `families.py`, `opportunity.py` |
| `c5_execution/` | Execution | `adapters.py`, `execution.py` (OrderManager, KillSwitch) |
| `c6_observation/` | Observation | `observation_agent.py`, `postmortem_engine.py` |
| `c7_memory/` | Memory | `memory_agent.py` |
| `c8_evolution/` | Evolution | `evolution_agent.py` |
| `c9_portfolio/` | Portfolio | `portfolio.py` (PortfolioGovernor) |
| `c10_world/` | World Intel | `macro_calendar.py`, `world_engines.py`, `regime_engine.py`, `fred.py` |
| `c11_finance/` | Back Office | `ledger.py`, `tax.py`, `ca_review.py`, `compliance.py`, `audit_graph.py` |

### 3.3 Core (core/)
| File | Purpose |
|---|---|
| `core/event_bus.py` | InMemoryEventBus, EventTopic (canonical `aios.c#.event` names) |
| `core/risk_firewall.py` | Deterministic RiskFirewall (position cap, stop distance, R:R, drawdown) |
| `core/persistence.py` | SqliteMemoryStore (hash-chained event log + typed tables) |
| `core/config.py` | Settings (pydantic-settings, .env) |
| `core/llm_*` | (in kernel/) model_gateway, model_router |
| `core/control_plane.py` | RBAC ControlPlane (roles × actions matrix) |

### 3.4 Simulation (simulation/)
| File | Purpose |
|---|---|
| `simulation/replay_runner.py` | ReplayRunner (composition root, wires ALL communities) |
| `simulation/paper_engine.py` | PaperEngine (cash, positions, bracket exits, shadow mode) |
| `simulation/generate_golden_data.py` | Seeded synthetic OHLCV generator |

### 3.5 API + UI
| File | Purpose |
|---|---|
| `api/views.py` | SystemSnapshotBuilder (all view payloads) |
| `api/server.py` | CommandCenterServer (stdlib HTTP, /api/v1/*, /metrics) |
| `ui/index.html` | Full SPA (15+ workspaces, dark OLED institutional) |

### 3.6 Schemas (schemas/contracts.py)
All Pydantic contracts: PriceData, MarketDataPayload, CandidateHypothesis, VerificationReport, StrategySpecification, TradeExecutionReceipt, ObservationReport, EvidencePack, PredictionRecord, PostmortemRecord, ScheduledEvent, ExpectationSnapshot, ScenarioSet, RegimeState, DataAnomalyAlert, OpportunityScore, PortfolioAllocationPlan, IntegrityReport, WalkForwardReport, CalibrationReport, OrderRequest, ReconciliationReport, EmergencyEvent, Posting, TaxLotOpen, Disposal, TaxComputation, ReviewItem, ComplianceAlert, DataProvenance, PerformanceSummary

### 3.7 Research (research/)
| File | Purpose |
|---|---|
| `research/integrity.py` | Backtest-integrity linters |
| `research/walkforward.py` | Walk-forward harness + calibration |
| `research/disaster.py` | Disaster drills (4 scenarios) |

## 4. KEY ARCHITECTURAL DECISIONS

| ADR | Decision |
|---|---|
| ADR-001 | Phase 1 architecture baseline FROZEN |
| ADR-002 | Canonical topics (`aios.c#.event`), provenance fields, honesty invariants |
| ADR-003 | R:R staging (C2 soft 2.0, firewall hard 1.5) |
| ADR-004 | UI shell: zero-dependency SPA, vanilla JS, no framework |
| CONSTITUTION | v1.0.0 ratified, SHA-256 pinned: `310bc83f...`, boot-enforced |

## 5. THE ORIGINAL ARCHITECTURE (what we're building toward)

Six planes: Experience, Control, Intelligence, Research, Execution, Deterministic Authority + Data/State + Infrastructure.

Key concepts the prototype LACKS:
- **State Machine Engine wired into runner** (kernel has it, runner doesn't use it yet)
- **First-class Hypothesis objects** (persistent, versioned, linked)
- **Evidence Packages** (structured, hash-addressable)
- **Experiment reproducibility** (kernel has registries, runner doesn't use them)
- **Feature Registry** (kernel has it, runner doesn't use it)
- **Model Registry** (kernel has it, no models exist)
- **Capability Router wired** (kernel has it, runner bypasses it)
- **PostgreSQL** (SQLite is fine for now but architecture calls for PG)
- **Multi-process/multi-service** (everything is one process)
- **Frontend framework** (vanilla JS works but won't scale)

## 6. LIVE PROVIDERS (all verified working)

| Provider | Key | Purpose | Status |
|---|---|---|---|
| xkiro.com (LLM) | sk-xt-c919... | deepseek/deepseek-v4-flash via OpenAI-compatible | ✅ VERIFIED |
| Finnhub | da3cqppr... | News headlines + sentiment | ✅ VERIFIED |
| FRED | 4a5d5451... | Macro actuals (CPI, FedFunds, Unemployment) | ✅ VERIFIED |
| GNews | c0d887d3... | News (backup provider) | Key stored, not yet integrated |
| NewsData.io | pub_0fe1d... | News (backup provider) | Key stored, not yet integrated |
| MarketStack | d8ef4f72... | Stock data | Key stored, not yet integrated |
| CCXT/Binance | None needed | Live crypto OHLCV (public endpoint) | ✅ VERIFIED ($76,491 BTC) |

## 7. COMPETITIVE ANALYSIS SUMMARY

**12 unique capabilities AIOS-0X has that NO competitor has:**
Hash-chained audit, double-entry accounting, tax/CA pipeline, constitution boot-pinning, RBAC console, prediction calibration, postmortem engine, kill-switch lockout, reconciliation, hallucination detection, challenger governance, compliance surveillance.

**Top competitors:**
- TradingAgents (99K stars) — debate + memory log + ReAct; NO accounting/tax/audit/verification
- Samvid Trading Core — IBKR+MT5, DrawdownLadder, RiskInvariants; NO LLM intelligence
- Swarm Trader — 20 agents (13 personalities), AutoResearch, SEC EDGAR; NO verification/audit
- Thales — 11-service polyglot, ML ensemble, arbitrage; NO accounting/tax
- Nexus AI — DL/RL models, RAG, Angular; NO governance/audit

**Our gaps (from COMPETITIVE_ANALYSIS.md):**
1. Real broker execution (testnet) — CRITICAL
2. Docker — DONE in Sprint 1
3. Benchmark — DONE in Sprint 1
4. WebSocket/SSE — pending
5. ML price prediction — future
6. RAG news — partially done (vector memory wired)
7. Personality agents — DONE in Sprint 2
8. AutoResearch — pending
9. Telegram — DONE in Sprint 1

## 8. OSS INTEGRATION (from 74 ZIPs)

**14 ADOPT** (integrate): alpaca-py, ccxt, PyPortfolioOpt, bt, FinRL-Trading, qdrant, mlflow, langfuse, otel, nats, finnhub, twelvedata, yfinance, agent-registry

**19 ADAPT** (steal patterns): qlib (PIT+rolling), nautilus (sizing+bus), Lean (IRiskManagement), qstrader (AlphaModel), Riskfolio (CVaR), FinGPT (RAG), vectorbt (walk-forward), semantica (PROV-O), TencentDB (L0-L3 memory), deepeval (eval metrics), guardrails (validators), crewAI (personalities), MetaGPT (SOP), FinRobot (financial agents), governance-toolkit (policy), datacontract (schema), alpha_vantage (layout), Horizon (news UX), quant-mind

**License traps**: backtrader (GPL-3.0 VIRAL), vectorbt (Commons Clause), grafana (AGPL)

## 9. SPRINT PLAN STATUS

| Sprint | Focus | Status |
|---|---|---|
| 1 (Credibility) | Benchmark, Docker, Telegram, graduation | ✅ COMPLETE |
| 2 (Intelligence) | Personalities, RAG, SSE, AutoResearch | 3/4 done (SSE + AutoResearch pending) |
| 3 (Production) | Testnet, short selling, constitution amendment | Not started (needs keys) |
| 4 (Scale) | ML models, multi-asset, advanced orders, customization | Not started |

## 10. KEY NUMBERS

| Metric | Value |
|---|---|
| Tests | 181 passed, 5 skipped (4 PG-gated) |
| Source files | 85 Python |
| LOC | ~11,000 |
| Kernel modules | 20 files |
| Community modules | 11 directories, ~30 files |
| LLM cost per debate | ~$0.001-0.005 (deepseek flash) |
| Debate latency | 0.9-6.2s per call (parallel bull/bear) |
| Full replay (730 bars × 7 symbols) | ~145s |
| Bus throughput baseline | ~750k msg/s (in-memory) |
| Group A benchmark | LangGraph 20.3ms vs native 0.2ms per 100 hops |

## 11. KNOWN ISSUES / TECH DEBT

1. ~~Runner doesn't use kernel yet~~ FIXED 2026-08-25: simulation/kernel_bridge.py wires lifecycles through the authority gateway; PostgreSQL data layer added (core/pg_store.py + store_factory, DATABASE_URL)
2. SSE live updates not implemented (5s polling)
3. AutoResearch not automated (challenger exists but manual)
4. Per-agent ACL wiring pending (mechanism exists, not enforced in runner)
5. Parquet deferred to Phase 3 (CSV keeps stdlib-only)
6. OTel/LangFuse not integrated (Prometheus shipped)
7. No real models exist (model registry ready but empty)
8. Experiment registry not wired into runner
9. Feature registry not wired into runner
10. Provenance graph not fully wired (transitions tracked manually)

## 12. FILE PATHS QUICK REFERENCE

```
AIOS-0X/
├── CONSTITUTION.md          ← ratified, SHA-256 pinned
├── CHECKPOINT.md            ← progress tracker (READ THIS FIRST)
├── pyproject.toml           ← pytest/ruff/mypy config
├── requirements.txt         ← pinned deps
├── .env                     ← LIVE KEYS (gitignored)
├── .env.example             ← template
├── kernel/                  ← AIOS OS primitives
├── core/                    ← shared infrastructure
├── schemas/                 ← Pydantic contracts
├── communities/             ← C1-C11 domain logic
├── simulation/              ← runner, paper engine, golden data
├── api/                     ← views + HTTP server
├── evaluation/              ← prompt lab
├── research/                ← integrity, walk-forward, disaster
├── ui/index.html            ← command center SPA
├── scripts/                 ← CLI tools
├── tests/                   ← 163 tests
├── docs/master/             ← all planning docs
├── docs/adrs/               ← ADR-000 through ADR-004
├── docs/adrs/ADR-004        ← UI architecture
└── research/benchmarks/     ← evidence files
```


