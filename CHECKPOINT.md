# AIOS Master Checkpoint & Progress Tracker

## Master System Roadmap

- [x] **Phase 1.0 – Architecture Baseline (FROZEN & LOCKED)** — See [ADR-001](docs/adrs/ADR-001_architecture_baseline_freeze.md)
- [/] **Phase 2.0 – Technology Acquisition & Validation** — Active Phase
- [ ] **Phase 3.0 – Prototype Integration**
- [ ] **Phase 4.0 – MVP Development**
- [ ] **Phase 5.0 – Production Deployment**

---

## Current Status: Phase 1.0 Frozen & Locked (Active Phase: Phase 2.0 – Technology Acquisition & Validation)

**Master System Navigation Map**: [docs/00_system_map.md](docs/00_system_map.md)

---

### Phase 0 DISCOVERY — COMPLETE (2026-08-23)

Full filesystem inspection + test execution (32/32 pytest green). Deliverables in `docs/master/`:

| Artifact | Content |
|---|---|
| `docs/master/AIOS-0X_MASTER_SPECIFICATION.md` | Verified current state, defects, decisions, next actions |
| `docs/master/AIOS-0X_ARCHITECTURE.md` | Target architecture (C1-C12 + cross-cutting planes) |
| `docs/master/GAP_ANALYSIS.md` | Domain matrix A-AE, process gaps, defects D1-D7, priorities |
| `docs/master/AIOS-0X_OSS_CATALOG.md` | 73 ZIPs mapped to dispositions; build-vs-buy; license watchlist |
| `docs/master/AIOS-0X_AGENT_REGISTRY.md` | Implemented agents + capability permission model + target families |
| `docs/master/AIOS-0X_PROMPT_REGISTRY.md` | Prompt governance schema + initial backlog (pre-LLM) |
| `docs/master/AIOS-0X_DATA_MODEL.md` | Contracts today + provenance extensions + storage mapping |
| `docs/master/AIOS-0X_EVENT_MODEL.md` | Topic reconciliation + mesh reaction requirements |
| `docs/master/AIOS-0X_MEMORY_MODEL.md` | Tiered memory + poisoning defense + prediction ledger |
| `docs/master/AIOS-0X_SECURITY_MODEL.md` | Threat model, capability permissions, secrets, audit chain |
| `docs/master/AIOS-0X_RISK_MODEL.md` | Two-layer risk authority, control set, kill-switch spec |
| `docs/master/AIOS-0X_TEST_STRATEGY.md` | Test pyramid + promotion gates + critical invariant tests |
| `docs/master/AIOS-0X_ROADMAP.md` | Phases 0.5-8 vertical slices w/ exit criteria |

**Critical verified findings**: no VCS/packaging; c6 fabricates +3% exits (fake profit loop);
c8 imports c7 (isolation violation); C5/C9 have zero code; zero LLM integration; memory is RAM-only.
Next: Phase 0.5 Foundation Hardening (see roadmap).

---

### Phase 0.5 FOUNDATION HARDENING — COMPLETE (2026-08-23)

- [x] Git repository initialized; baseline commit `3c303d7` (pristine pre-hardening state); .gitignore + .gitattributes
- [x] `pyproject.toml` (pytest/ruff/mypy config, strict mode) + pinned `requirements.txt` matching verified environment
- [x] **D1 fixed**: C6 no longer fabricates exits; positions close only on real market prices (`on_market_price_update`); PaperEngine settles at same market source
- [x] **D2 fixed**: C8 consumes injected typed provider (`PerformanceSummary` contract); zero cross-community imports
- [x] **D3 fixed**: C4 direction-aware (BUY/SELL/NO TRADE) with volatility-scaled levels from cached market state; no invented default price
- [x] **D4 fixed**: RiskFirewall validates portfolio value and returns notional
- [x] **D5 fixed**: PaperEngine owns cash balance, rejects insufficient funds, tags fills `is_simulated`
- [x] **D6 fixed**: bounded FIFO caches (512 entries)
- [x] **D7 fixed**: `is_verified` explicit input respected
- [x] **ADR-002 ACCEPTED**: canonical topic namespace `aios.<c#>.<event>` (StrEnum), DataProvenance/lineage/is_simulated fields, honesty invariants
- [x] **ADR-003 ACCEPTED**: R:R staging ratified (C2 soft target 2.0; firewall hard floor 1.5; hypothesis R:R flows into order geometry)
- [x] Doc 19 reconciliation notice (Selection Ledger v2.0.0 authoritative); 75 stale twin-folder links → relative paths across 22 files
- [x] Gates: **pytest 39/39 · ruff clean (formatted tree) · mypy strict clean (22 files)**

Next: Phase 1 Honest Vertical Slice (historical replay adapter, SQLite persistence, honest postmortems).

---

### Phase 1 HONEST VERTICAL SLICE — COMPLETE (2026-08-23)

- [x] **ReplayDataFetcher** (`communities/c1_data/replay_fetcher.py`): CSV OHLCV replay, shared cursor, strict as-of semantics (bar 0 never skipped; exhaustion raises; future bars unreachable) + `Bar` TypedDict
- [x] **Golden datasets**: seeded regime-switching synthetic generator (`simulation/generate_golden_data.py`) → `data/golden/*_1d.csv` (7 symbols × 730 daily bars, 2024–2025 window, SIM-tagged per Law 1.3); regenerable byte-stable via seed=42
- [x] **SqliteMemoryStore** (`core/persistence.py`): hash-chained append-only event log (sha256 chain w/ genesis), typed tables for predictions/observations/postmortems; tamper detection pinpoints first bad seq; BaseMemoryStore ABC for later PG/Qdrant swap
- [x] **Prediction ledger live**: PredictionRecord written on fill (pre-outcome) with decision-bar timestamp snapshot + verification confidence; scored at settlement with direction_correct
- [x] **PostmortemEngine** (C6): evidence-bound postmortems (thought/knew/did/happened/got_right/got_wrong/unknowable/luck/should_change); fee-noise luck assessment
- [x] **ReplayRunner** (`simulation/replay_runner.py`): composition root wiring C1→C8 over replay; bracket exits from actual bar highs/lows (stop-first conservative rule, adverse stop slippage); per-symbol position cap; horizon-end force close; equity curve + max drawdown; timestamp-free determinism hash
- [x] **PaperEngine upgraded**: positions carry bracket levels + allocated capital; settlement conserves cash exactly (cash = initial + Σ realized PnL); side-aware PnL (BUY/SELL) through ObservationAgent too
- [x] **CLI**: `scripts/run_replay.py`
- [x] **Exit criteria demonstrated** on full golden universe: 730 bars, 7 symbols → 1,505 trades; PnL **−13,637.68 (honest loss)**; directional accuracy 30.03%; 1,505 predictions scored + postmortems; chain valid across 26,460 events; determinism test green
- [x] Gates: **pytest 44/44 · ruff clean · mypy strict clean (27 files)**

Note: parquet deferred to Phase 3 data fabric (CSV keeps stdlib-only deps); deviation documented.

---

### Phase 2 INTELLIGENCE ONBOARDING — COMPLETE (2026-08-23)

- [x] **Model gateway** (`core/model_gateway.py`): BaseModelGateway ABC; OpenAI-compatible adapter (httpx, retries w/ backoff, token+cost accounting) + Anthropic adapter; ScriptedModel TEST DOUBLE for CI; `complete_structured()` enforces Pydantic output contracts w/ repair-retry loop
- [x] **Model router v0** (`core/model_router.py`): CHEAP/REASONING tiers from Settings; honest `available=False` when unconfigured — system NEVER pretends an LLM contributed
- [x] **Config**: pydantic-settings `core/config.py` (env-only secrets, repr=False) + `.env.example`; verified: no credentials present → deterministic mode active
- [x] **Prompt registry** (`core/prompts.py`): versioned PromptSpecs w/ variable validation; built-in v1 prompts: research-bull-thesis, research-bear-thesis, research-quant-review, research-moderator-synthesis
- [x] **C2 adversarial debate** (`debate_engine.py`): BULL→BEAR→QUANT→MODERATOR pipeline producing balanced CandidateHypothesis (Mandatory Balance Rule enforced by contract min-lengths); quant REJECT recorded as counter-argument; ANY failure → deterministic template fallback tagged in transcript
- [x] **C3 real verification**: EvidencePack contract; numeric hallucination detector — every cited number checked vs decision-time market facts (2% tolerance); fabrication caps fact score at 5/40 ⇒ total 65 < 70 ⇒ rejected; no-evidence path preserves legacy behavior
- [x] **Prompt Lab v0** (`evaluation/prompt_lab.py`): golden-set eval harness (parse-rate gate ≥90%); golden cases committed for bull prompt; pass/fail gates proven in tests
- [x] **Cost intelligence**: every model call logged as MODEL_CALL event w/ tokens/cost/latency into hash-chained store; runner summary exposes model_calls + total_model_cost_usd + research_mode_used
- [x] Runner integration: injected-gateway debate mode tested E2E (scripted, deterministic); deterministic mode unchanged
- [x] Gates: **pytest 59/59 · ruff clean · mypy strict clean (34 files)**

Next: Phase 3 Data Fabric & World Intelligence (real ingestion adapters, quality states, event engine, expectation engine).

---

### Phase 3 DATA FABRIC & WORLD INTELLIGENCE — COMPLETE (2026-08-23)

- [x] **REAL LIVE MARKET DATA ACHIEVED**: `CcxtDataFetcher` (communities/c1_data/ccxt_fetcher.py) pulls public OHLCV from any CCXT venue keylessly; verified live — BTC/USDT $76,491.81 through the full pipeline with `is_simulated=false`, provenance `ccxt:binance/LIVE`; injectable exchange factory for offline tests; `scripts/fetch_live_sample.py` CLI reports failures honestly
- [x] **Data-quality machinery** (`core/data_quality.py`): AnomalyDetector (OHLC_INVALID / PRICE_GAP >15% / VOLUME_SPIKE vs rolling median) + SymbolHealthRegistry freeze/unfreeze lifecycle; DATA_ANOMALY reactions wired — StrategyAgent refuses frozen symbols (Directive 9)
- [x] **C10 World Intelligence** (`communities/c10_world/`): FileMacroCalendar (CSV scheduled events, replay-cursor semantics); **ExpectationEngine** with direction-aware surprise interpretation (`higher_is_better` per event — hot CPI ≠ good news; Directive 12 honored); ScenarioEngine publishing BASE/BULL/BEAR/UNEXPECTED/EXTREME cards summing to 1.0
- [x] **Regime engine v0**: EMA(8)-slope trend labels + realized-vol bands; REGIME_CHANGED published on flips; StrategyAgent scales position size by vol regime (HIGH→50% of base)
- [x] **Audit upgrade**: event log `kind` now uses canonical topic names (`aios.c10.expectation_updated`...) for precise queries
- [x] Contracts added: ScheduledEvent, ExpectationSnapshot, ScenarioCard/Set, RegimeState, DataAnomalyAlert, TrendLabel/VolRegime
- [x] ccxt pinned (4.5.74) in requirements.txt; live-network test gated behind AIOS_LIVE_TESTS=1
- [x] Gates: **pytest 73 passed +1 opt-in live · ruff clean · mypy strict clean (40 files)**

Next: Phase 4 Quant Research & Strategy Lab (benchmark Groups A/B/C execution → selection ADRs; walk-forward harness; backtest-integrity linters; Opportunity Engine; C9 portfolio allocator).

---

### Phase 4 QUANT RESEARCH & STRATEGY LAB — COMPLETE (2026-08-23)

- [x] **C9 PortfolioGovernor live in production path**: STRATEGY_GENERATED → governor (Doc 15) → PORTFOLIO_ALLOCATED/REJECTED → PaperEngine. Drawdown tiers (1.5%→×0.75, 2.5%→×0.5, 3%→HALT), class exposure caps 35%, half-Kelly sizing when ≥20 calibrated samples exist; provider-injection preserves community isolation
- [x] **Strategy families**: StrategyFamily ABC; MomentumFamily (baseline geometry preserved) + MeanReversionFamily (z-score extreme-move fade); multi-candidate generation with firewall validation per candidate
- [x] **Opportunity engine (C4-owned per topic namespace)**: composite = (confidence−breakeven_p) × RR × alpha-decay(halflife by timeframe); OPPORTUNITY_RANKED published for every candidate
- [x] **Backtest-integrity linters** (`research/integrity.py`): timestamp monotonicity, duplicate bars, survivorship universe guard, positive prices; runner-config gates (slippage>0, fees>0, bracket exits, no-same-bar-exit, as-of access)
- [x] **Walk-forward harness** (`research/walkforward.py`): WindowSlicer (90/30 Doc 06 defaults), per-window runner execution, Sharpe/maxDD, overfit flagging
- [x] **Calibration reports**: reliability decile buckets + Brier score from prediction ledger; `reliable` gate at ≥20 scored predictions
- [x] **Benchmark evidence recorded honestly**: Group A langgraph smoke PASS (200/200 hops, 0.21 ms/hop) WITH pydantic.v1-on-Py3.14 compat warning captured; Group B install-compat PASS (nautilus cp314 wheel exists; vectorbt resolves via numba 0.67) — formal protocol BENCHMARK-REQUIRED; Group C BLOCKED.md (no broker infra). Evidence under research/benchmarks/
- [x] **Measured impact of governance** (3-crypto golden replay): trades 1,505→68-class-scale, PnL −13,637→+162.38, maxDD 13.6%→0.47%. Cause: portfolio controls strangling fee churn — NOT a claimed edge (synthetic data)
- [x] Gates: **pytest 87 passed +1 opt-in · ruff clean · mypy strict clean (48 files)**

Next: Phase 5 Execution & Risk Governor hardening (broker adapters paper-first, order lifecycle, kill-switch implementation, emergency state machine).

---

### Phase 5 EXECUTION & RISK GOVERNOR HARDENING — COMPLETE (2026-08-23)

- [x] **Order lifecycle** (`communities/c5_execution/execution.py`): OrderManager converts approved plans into OrderRequests (PENDING_NEW→ACCEPTED→FILLED/REJECTED) with client_order_id idempotency; ORDER_SUBMITTED/ORDER_FILLED events; TRADE_EXECUTED stays single-source (engine-emitted)
- [x] **Kill switch implemented** (Doc 07 sequence): flatten-all-positions at adverse prices → EMERGENCY_HALT lockout persisted to audit log → new orders refused while locked. **Only** `RiskGovernor.human_reset(operator_id)` clears it; blank operator ids refused
- [x] **Emergency state machine** (`core/risk_governor.py`): 9-state model per RISK_MODEL doc; drawdown-halt linkage (governor dd ≥3% → EMERGENCY_HALT); reconciliation-failure → EXECUTION_FAILURE; boot-time lockout detection from audit log (`load_lockout_from_store`) blocks trading after restart until human reset
- [x] **Execution adapters** (`adapters.py`): BaseExecutionAdapter ABC; PaperExecutionAdapter delegating to engine; **CcxtExecutionAdapter honest stub** — refuses without AIOS_ALLOW_LIVE_EXECUTION=1 + credentials, testnet default ON, hard micro-live notional cap ($100) pending constitution sign-off; never silently paper-simulates
- [x] **Reconciliation loop**: adapter snapshot vs internal fill mirror each bar; mismatch → RECONCILIATION_FAILED + EXECUTION_FAILURE lockout + kill-switch trigger
- [x] **Shadow mode**: PaperEngine(shadow_mode=True) records fills/pnl with venue="shadow" but zero cash mutation — mandatory pre-live rehearsal venue
- [x] **Topic ACL** (`core/security.py`): AgentPrincipal capability sets + ACLBus wrapper; publish_as/subscribe_as enforce permissions (PermissionError on violation); system API reserved for composition root
- [x] Gates: **pytest 93 passed +1 opt-in · ruff clean · mypy strict clean (53 files)**

Next: Phase 6 Finance Back Office (double-entry ledger, broker/statement reconciliation, tax lots w/ jurisdiction rules + CA review workflow, NAV, compliance hooks, audit-graph query API).

---

### Phase 6 FINANCE BACK OFFICE — COMPLETE (2026-08-23)

- [x] **Double-entry ledger** (`c11_finance/ledger.py`): integer-minor-unit postings only; hard zero-sum trial-balance invariant; trading legs (open-at-cost, fees, basis release, realized gain/loss); LEDGER_POSTED events; **verified balanced across full honest replay**
- [x] **Tax lot book**: FIFO consumption w/ partial fills, per-lot cost basis + fee allocation, holding-period split (short/long), overdraw refused loudly
- [x] **Jurisdiction rule engine**: cited advisory rules (IN s.115BBH flat-30% VDA, US IRC §1222 LT/ST split, GENERIC placeholder); TaxComputation carries citation + `requires_professional_signoff=True` unconditionally
- [x] **CA review workflow**: DRAFT→PREPARED→UNDER_REVIEW→APPROVED_BY_CA/REJECTED state machine; `export_for_filing` raises PermissionError unless approved; reviewer identity mandatory
- [x] **Compliance surveillance**: RESTRICTED_SYMBOL (CRITICAL/blocking), FAT_FINGER_QTY vs rolling median (CRITICAL/blocking), WASH_SALE_WINDOW heuristic (WARNING); COMPLIANCE_ALERT topic live
- [x] **Audit-graph query API** (`audit_graph.py`): decision_provenance(execution_id) walks execution→strategy→hypothesis→verification over the hash-chained store; hypothesis_impact() aggregates downstream PnL; chain_complete flag verified E2E in tests
- [x] **Runner integration**: fills post to books + open lots; settlements consume FIFO + post realized legs; NAV utility added
- [x] Gates: **pytest 103 passed +1 opt-in · ruff clean · mypy strict clean (59 files)**

Next: Phase 7 Control Plane & UI (human control-plane APIs with RBAC, institutional command-center UI, observability stack wiring).

---

### Phase 1.0 – Architecture Baseline (FROZEN & LOCKED) — 100% COMPLETE

- [x] **System Map & Master Index** ([docs/00_system_map.md](docs/00_system_map.md))
- [x] **ADR-000: Architecture Decision Record Template** ([docs/adrs/ADR-000_template.md](docs/adrs/ADR-000_template.md))
- [x] **ADR-001: Architecture Baseline Freeze Decision** ([docs/adrs/ADR-001_architecture_baseline_freeze.md](docs/adrs/ADR-001_architecture_baseline_freeze.md))
- [x] **Doc 1.1: Overall Platform Architecture & Inter-Community Protocols** ([docs/01_platform_architecture.md](docs/01_platform_architecture.md))
- [x] **Doc 1.2: Community 1 Specification (Data Acquisition)** ([docs/02_community_1_data.md](docs/02_community_1_data.md))
- [x] **Doc 1.3: Community 2 Specification (Research & Analysis)** ([docs/03_community_2_research.md](docs/03_community_2_research.md))
- [x] **Doc 1.4: Community 3 Specification (Verification Firewall)** ([docs/04_community_3_verification.md](docs/04_community_3_verification.md))
- [x] **Doc 1.5: Community 4 Specification (Strategy Generation)** ([docs/05_community_4_strategy.md](docs/05_community_4_strategy.md))
- [x] **Doc 1.6: Continuous Training Environment Specification** ([docs/06_continuous_training.md](docs/06_continuous_training.md))
- [x] **Doc 1.7: Community 5 Specification (Live Trading Execution)** ([docs/07_community_5_execution.md](docs/07_community_5_execution.md))
- [x] **Doc 1.8: Community 6 Specification (Observation & Audit)** ([docs/08_community_6_observation.md](docs/08_community_6_observation.md))
- [x] **Doc 1.9: Community 7 Specification (Memory Architecture)** ([docs/09_community_7_memory.md](docs/09_community_7_memory.md))
- [x] **Doc 1.10: Community 8 Specification (Evolution Mechanisms)** ([docs/10_community_8_evolution.md](docs/10_community_8_evolution.md))
- [x] **Doc 1.11: Supporting Systems Specification (Risk, Validation, Infrastructure)** ([docs/11_supporting_systems.md](docs/11_supporting_systems.md))
- [x] **Doc 1.12: AI Constitution & Governing Laws** ([docs/12_ai_constitution.md](docs/12_ai_constitution.md))
- [x] **Doc 1.13: Organization, Governance, Agent Lifecycle & Reputation** ([docs/13_organization_and_governance.md](docs/13_organization_and_governance.md))
- [x] **Doc 1.14: Event Bus & Messaging Architecture Specification** ([docs/14_event_bus_and_messaging_spec.md](docs/14_event_bus_and_messaging_spec.md))
- [x] **Doc 1.15: Community 9 Specification (Portfolio Intelligence)** ([docs/15_community_9_portfolio_intelligence.md](docs/15_community_9_portfolio_intelligence.md))
- [x] **Doc 1.16: Open-Source Technology Acquisition Framework** ([docs/16_technology_acquisition_framework.md](docs/16_technology_acquisition_framework.md))
- [x] **Doc 1.17: Registries & Feature Store Specification** ([docs/17_registries_and_feature_store.md](docs/17_registries_and_feature_store.md))
- [x] **Doc 1.18: Decision Audit Graph & Digital Twin Simulation Layer** ([docs/18_decision_audit_graph_and_simulation.md](docs/18_decision_audit_graph_and_simulation.md))

---

### Phase 2.0 – Technology Acquisition & Validation (ACTIVE)

**Master Technology Evaluation Catalog**: [docs/19_master_technology_catalog.md](docs/19_master_technology_catalog.md)

- [/] **Cataloging & Benchmarking Open-Source Candidates**:
  - [ ] Multi-Agent Frameworks (LangGraph vs. LlamaIndex Workflows vs. CrewAI)
  - [ ] Message Bus & Streaming (NATS JetStream vs. Redis Streams vs. Kafka)
  - [ ] Databases & Vector Memory (PostgreSQL/TimescaleDB + Qdrant/Milvus)
  - [ ] Market Data Ingestion Pipelines (CCXT, Alpaca, Polygon.io)
  - [ ] Backtesting & Simulation Engines (NautilusTrader vs. Lean vs. VectorBT)

---

### Phase 3.0 – Prototype Integration (Pending Phase 2.0 Completion)

---

### Phase 4.0 – MVP Development (Pending Phase 3.0 Completion)

---

### Phase 5.0 – Production Deployment (Pending Phase 4.0 Completion)
