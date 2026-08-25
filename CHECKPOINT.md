# AIOS Master Checkpoint & Progress Tracker

## Master System Roadmap

- [x] **Phase 1.0 – Architecture Baseline (FROZEN & LOCKED)** — See [ADR-001](docs/adrs/ADR-001_architecture_baseline_freeze.md)
- [x] **Phase 2.0 – Technology Acquisition & Validation** — COMPLETE (2026-08-23, closure table below)
- [x] **Phase 3.0 – Prototype Integration** — COMPLETE (2026-08-23, vertical-slice build Phases 1–8)
- [x] **Phase 4.0 – MVP Development** — COMPLETE (2026-08-23, all domains operational on paper/shadow)
- [ ] **Phase 5.0 – Production Deployment** — GATED (5 human-held gates listed in §Phase 5.0 below)

---

## Current Status: REAL SYSTEM BUILD — KERNEL WIRED + PG DATA LAYER · 181 tests green

**Master System Navigation Map**: [docs/00_system_map.md](docs/00_system_map.md)

---

### ZERO-TRUST BUS ACLs (§24) — communities publish only their topics (2026-08-25)

- `core/event_bus.py`: `ScopedEventBus` — per-actor bus view; off-roster
  publishes raise PermissionError and are recorded (`denied` trail).
  Listening stays unrestricted: subscribing is not authority.
- `ReplayRunner`: `_COMPONENT_BUS_SCOPES` ownership map (12 actors, incl. the
  legitimate dual-owner OPPORTUNITY_RANKED for c4+c9); every community
  component now receives its scoped view. Kernel bridge + composition-root
  keep the unscoped bus (system actor).
- Roster registrations synced to runtime scopes (c1/c5/c8/c9 updated, new
  c10-world identity) — audit log and enforcement can no longer diverge.
- `runner.acl_denials` must stay empty; integration test proves a FULL replay
  runs with ZERO off-roster publishes.

Tests: 238 hermetic / **248 passed, 1 skipped with AIOS_TEST_PG_DSN**. Ruff clean.
Tech debt #4 (per-agent ACL wiring) CLOSED.

---

### OS CLI — `python -m aios {boot,replay,summary-json,serve}` (2026-08-25)

The system boots like an operating system now:

- `aios/` package (NEW): single entrypoint over the same kernel/runner/authority
  paths the tests exercise.
  - `boot` — constitution SHA gate + kernel inventory (actors, capabilities,
    lifecycles, registries, fail-closed authority). Nothing else needed to
    prove the OS stands up.
  - `replay` — honest summary table; **exit code 1 if audit chain broken**;
    existing goldens are never rewritten (reproducibility), `--bars` honestly
    reported as ignored for pre-existing files.
  - `summary-json` — machine-readable RunSummary.
  - `serve` — replay → refuse-if-chain-broken → live command center (SSE).
- pyproject packages updated.

Verified live: `python -m aios boot` exit 0; `python -m aios replay --symbols SPY`
ran the full 730-bar golden, chain valid, alpha +3.11%, 2825 events audited.
Tests: 233 hermetic / **243 passed, 1 skipped with AIOS_TEST_PG_DSN**. Ruff clean.

---

### EVALUATION PLANE (§14) + PROMOTION/ROLLBACK (§21/§22) — fail-closed gates live (2026-08-25)

- `research/evaluation.py` (NEW): `EvaluationRecord` with PASS/FAIL/INCONCLUSIVE
  verdicts and structural honesty gates — trials under 5 trades per side are
  INCONCLUSIVE regardless of margin; models need ≥30 walk-forward predictions,
  ≥55% accuracy, brier ≤0.5.
- `ChallengeRegistry`: every evaluation now attaches a formal record (audited as
  `EVALUATION_RECORD`); **promotion requires PASS evidence — a human cannot
  overrule FAIL/INCONCLUSIVE**. Promotions flow through kernel PromotionController
  with RollbackController targets ("trial → baseline").
- `ControlPlane.promote_model` (RISK_ADMIN): fail-closed chain EVALUATED status →
  walk-forward EvaluationRecord → kernel promotion + rollback target
  (deterministic_baseline:v1); MODEL_PROMOTED audit event; registry status updated.
- API: `GET /api/v1/evaluations`.
- Legacy Phase-8 test updated to the stricter contract (FAIL now raises instead of
  soft-rejecting) — intent preserved, gate strengthened.

Tests: 233 hermetic / **238 passed, 1 skipped with AIOS_TEST_PG_DSN**. Ruff clean.

---

### ML CHALLENGER — §13 loop closed: model trades, operator evaluates (2026-08-25)

- `communities/c4_strategy/ml_family.py` (NEW): `MLDirectionFamily` — the trained
  direction model as a candidate generator. Expanding-window refits on visible
  closes only; inference shares the exact training feature formulas
  (`features_for_latest`); NO TRADE default; geometry from realized vol.
- **Critical fix found by tests**: LogReg outputs were constant 0.5 (unscaled
  micro-features → vanishing gradients). Model now standardizes internally;
  mean/std are part of the artifact hash. Walk-forward metrics are real.
- `ControlPlane`: new `evaluate_trial` action (RISK_ADMIN) running champion-vs-
  challenger via injected evaluator; `ReplayRunner.evaluate_challenger(name)`
  builds isolated sandbox runners per side over identical data. Evidence lands
  in CHALLENGER_EVALUATION; PROMOTE_CHALLENGER remains the separate human gate.

Tests: 225 hermetic / **230 passed, 1 skipped with AIOS_TEST_PG_DSN**. Ruff clean.

---

### MODEL LIFECYCLE (§12) — first real model trained + evaluated (2026-08-25)

- `research/model_lab.py` (NEW): stdlib-only logistic regression predicting
  next-bar direction from OHLCV features (returns 1/2/3/5, vol 5/10, SMA
  ratios). Strictly causal alignment (window ends BEFORE its label bar);
  expanding-window walk-forward evaluation only; artifact = sha256(weights).
- Runner post-run cycle (`Settings.ml_training`, default on): trains pooled
  across replay symbols → registers `direction_logreg@v1` (feature-pinned) →
  mark_trained(artifact_hash) → mark_evaluated(walk-forward metrics) →
  MODEL_TRAINED audit event.
- API/UI: `GET /api/v1/models` + RESEARCH→"Model Registry" workspace showing
  lifecycle states, artifact hashes, walk-forward metrics per symbol.

Tests: 220 hermetic / **225 passed, 1 skipped with AIOS_TEST_PG_DSN**. Ruff clean.
Registry now holds TWO evaluated models: deterministic_baseline + direction_logreg.

---

### SPRINT 2 CLOSED — SSE live stream + model registry populated (2026-08-25)

- `api/server.py`: **`GET /api/v1/stream`** — Server-Sent Events (stdlib only):
  executive snapshot + last 10 `aios.platform.*` events every 2s per connected
  client; worker-thread loop ends on client disconnect.
- `ui/index.html`: EventSource consumer drives STATE/DD/CHAIN header pills live
  (+ "SSE LIVE" pill with last-tick time); polling remains as fallback.
- Model registry no longer empty: each run registers
  `deterministic_baseline@v1` (rule_stack, feature-pinned to ohlcv_passthrough:v1)
  and marks it EVALUATED with the run's real metrics (directional accuracy,
  cumulative pnl...). Provenance edge feature→model queryable.

Tests: 213 hermetic / **218 passed, 1 skipped with AIOS_TEST_PG_DSN**. Ruff clean.
Sprint 2: ✅ COMPLETE (personalities, RAG, AutoResearch, SSE).

---

### AUTORESEARCH — core learning loop CLOSED (2026-08-25)

The core cycle's final step — UPDATE HYPOTHESIS SPACE — is now automatic:

- `research/auto_research.py` (NEW): `AutoResearchEngine` reads settled outcomes
  from the durable research store and deterministically proposes new hypotheses:
  **INVERSION** (≥2 REJECTED, 0 SUPPORTED on a symbol → mean-reversion counter-thesis,
  parents = rejected set) and **CONTINUATION** (≥2 SUPPORTED → trend-persistence
  thesis). Signature-deduped across sessions; UNTESTED; nothing auto-promotes.
- Runner: post-run cycle synthesizes → persists via research engine → kernel-tracks
  via bridge (`c8-autoresearch` AGENT_RESEARCH actor) → stages a challenger trial
  per proposal for human-gated evaluation. `Settings.auto_research` flag (default on).
- Platform events + audit trail follow every proposal.

Tests: 209 hermetic / **214 passed, 1 skipped with AIOS_TEST_PG_DSN**. Ruff clean.
Sprint 2 item "AutoResearch" ✅ (evaluation of staged trials remains operator-triggered).

---

### ORIGINAL-ARCHITECTURE BUILD: D/E bridge — durable receipts + research surface — COMPLETE (2026-08-25)

- `kernel/receipts.py`: `ReceiptStore(sink)` — EVERY receipt (gateway + state-machine
  co-receipts) mirrors into the hash-chained log via one persistence path;
  `create_kernel(receipt_sink=...)`; KernelBridge's per-call mirroring removed.
- `api/views.py` + `api/server.py` + runner wiring: **research plane is now visible** —
  `GET /api/v1/knowledge` (status counts + recent hypotheses with evidence tallies),
  `GET /api/v1/knowledge/{id}` (full record + evidence graph incl. content hashes),
  `GET /api/v1/platform-events` (typed aios.platform.* stream, newest-first).
- `ui/index.html`: new RESEARCH nav group — "Hypothesis Graph" workspace (summary cards,
  status badges, per-hypothesis evidence drawer) + "Platform Events" live stream view.

Tests: 201 hermetic / **206 passed, 1 skipped with AIOS_TEST_PG_DSN**. Ruff clean.

---

### ORIGINAL-ARCHITECTURE BUILD: Phase D typed platform events — COMPLETE (2026-08-25)

Per `ARCHITECTURE_GAP_ANALYSIS.md` §3.10 / original architecture §18:

- `core/platform_events.py` (NEW): `PlatformEventType` (15 canonical
  ``aios.platform.*`` events: dataset_version_created, experiment_started/completed,
  hypothesis_created/rejected, evaluation_completed, order_requested/authorized/denied,
  risk_decision_made, execution_completed, post_mortem_created, promotion_approved/denied,
  rollback_triggered) + validated `PlatformEvent` payload (actor, object ref, reason,
  receipt_ids, metadata) with per-type factory constructors.
- `core/event_bus.py`: PLATFORM_* topics added to canonical EventTopic.
- KernelBridge emits at every mutation point; runner's catch-all audit logger persists
  them into the hash-chained log automatically (single persistence path, no double log).
  ExperimentCompleted now fires BEFORE bus shutdown (was silently dropped).
- Control-plane consumers can subscribe to any platform topic directly (tested).
- Counts reconcile with trading reality: post_mortem_created == executions ==
  trades_closed; every fill preceded by order_authorized.

Tests: 197 passed hermetic; **202 passed / 1 skipped with AIOS_TEST_PG_DSN**.

---

### ORIGINAL-ARCHITECTURE BUILD: Phase C Research Plane — COMPLETE (2026-08-25)

Per `ARCHITECTURE_GAP_ANALYSIS.md` Phase C: durable knowledge that survives sessions.

- `schemas/contracts.py`: **`Hypothesis`** (persistent first-class object: statement,
  rationale, expected_outcome, regime, assumptions, evidence_ids[], confidence, status
  UNTESTED→TESTING→SUPPORTED/REJECTED/…, parent_hypotheses[] lineage) + **`EvidencePackage`**
  (hash-addressable via `content_hash()`, claims/counter_claims, provenance) + `HypothesisStatus`.
- `core/research_store.py` (NEW): `BaseResearchStore` with SQLite + PostgreSQL backends
  (same DATABASE_URL selection as memory store). Tables: hypotheses / evidence
  (deduped on source+content_hash) / hypothesis_evidence links ("supports" |
  "contradicts" | "outcome"). Factory: `build_research_store()` → `<store>.research.db` locally.
- `research/engine.py` (NEW): **HypothesisEngine** — CandidateHypothesis→durable row;
  VerificationReport→EvidencePackage (+status TESTING when verified); postmortem outcome→
  outcome evidence + SUPPORTED/REJECTED; one-outcome-per-hypothesis idempotency;
  cross-session restore into fresh kernel state machines (`wire_kernel_to_engine`);
  `knowledge_summary()` status counts.
- Runner wiring: research store built alongside memory store; KernelBridge persists at
  every hook (on_hypothesis / on_verification / on_settled). `bridge.stats()["research"]`.
- Tests: `tests/test_phase_c_research.py` — evidence dedupe/hash, lifecycle surviving
  simulated restart, contradicting-evidence path, kernel restore, runner end-to-end +
  cross-session read-back, PG parity (live-verified).

**Verification**: 194 passed / 1 skipped with `AIOS_TEST_PG_DSN` set (all live-PG active);
181 passed / 5 skipped hermetic default. Ruff clean on all touched files.

---

### ORIGINAL-ARCHITECTURE BUILD: Phase A completion + Phase B data layer — COMPLETE (2026-08-25)

Per `ARCHITECTURE_GAP_ANALYSIS.md` migration strategy. The kernel is no longer shelfware.

**Phase A completion — kernel wired into the runner:**
- `simulation/kernel_bridge.py` (NEW): the ReplayRunner boots on `create_kernel()`.
  - Community actors registered as kernel identities with least-privilege roles
    (c1=SERVICE_DATA, c2=AGENT_RESEARCH, c3=AGENT_CRITIC, c4=AGENT_STRATEGY,
    c5=SERVICE_EXECUTION, c9=RISK_ADMIN).
  - Replay CSVs registered via **DatasetRegistry** as a versioned, content-hashed,
    state-machine-tracked dataset (DRAFT→VALIDATED→ACTIVE) + feature
    (`ohlcv_passthrough@v1`) via **FeatureRegistry**.
  - The entire replay is an **ExperimentRun** pinned to dataset version + seed +
    config; reproducibility hash surfaced on `RunSummary.experiment_reproducibility_hash`
    and proven stable across identical runs.
  - Hypotheses are first-class tracked objects: UNTESTED → TESTING (on C3 verified)
    → SUPPORTED / REJECTED at postmortem. Rejected hypotheses persist (negative knowledge).
  - Strategies walk IDEA → HYPOTHESIS → DRAFT → VALIDATED → BACKTESTED → EVALUATED;
    every hop authorized by the **AuthorityGateway** (capability + role + policy, fail closed).
  - Plan→order dispatch passes through `authorize_execution` (AIOS.execute); governor
    rejections recorded as DENY receipts.
  - Every ALLOW/DENY mirrored into the hash-chained audit log as `DECISION_RECEIPT` events.
  - Provenance graph links dataset → hypothesis → strategy → experiment → execution
    → postmortem; `lineage_backward(execution_id)` resolves to DATASET_VERSION.
- `kernel/bootstrap.py`: registries attached to AIOSKernel; new capabilities
  (`AIOS.register.dataset`, `AIOS.register.feature`, `AIOS.experiment`) declared+granted.
- Tests: `tests/test_kernel_wiring.py` (11 tests).

**Phase B — PostgreSQL Data & State Plane:**
- `core/pg_store.py` (NEW): `PostgresMemoryStore(BaseMemoryStore)` — psycopg3,
  byte-identical hash-chain semantics to SQLite (genesis + canonical JSON), same
  typed tables, tamper detection pinpoints seq, thread-safe, fail-closed connects.
- `core/store_factory.py` (NEW): `select_store_class()` / `build_memory_store()`;
  runner auto-promotes to PG when `DATABASE_URL` is set, SQLite stays default.
- `core/config.py`: `database_url` setting (repr-hidden). `.env.example` documented.
- requirements.txt pinned `psycopg[binary]==3.3.4`.
- Tests: `tests/test_phase_b_postgres.py` — factory/selection hermetic; live PG
  round-trips (chain, typed tables, tamper drill, FULL REPLAY ON POSTGRES) env-gated:
  set `AIOS_TEST_PG_DSN=postgresql://...` to activate (local PG18 server detected
  running but credentials unknown).

**Verification**: 181 passed, 5 skipped (4 = live-PG gated, 1 legacy). Ruff clean on all
new/modified files. No behavior change to trading logic — determinism hash unchanged.

---

### Phase 2.0 CLOSURE — Technology Acquisition & Validation (completed 2026-08-23)

| Original checklist item | Status | Evidence |
|---|---|---|
| Multi-Agent Frameworks (LangGraph vs. LlamaIndex vs. CrewAI) | BENCHMARKED (functional) | `research/benchmarks/group_a/groupA_benchmark.json` — LangGraph PASS 20.3ms vs native bus 0.2ms per 100-hop cycle (10 reps, integrity asserted); smoke + pydantic-v1/Py3.14 warning captured (`langgraph_result.yaml`). CrewAI/LlamaIndex arms remain BENCHMARK-REQUIRED for the full ADR |
| Message Bus & Streaming (NATS JetStream vs Redis vs Kafka) | BASELINE RECORDED; broker runs INFRA-BLOCKED | `group_c/baseline_inmemory.json` — native bus ≈750k msg/s local baseline; NATS/Redpanda require services → `group_c/BLOCKED.md` |
| Databases & Vector Memory (PostgreSQL/TimescaleDB + Qdrant/Milvus) | VECTOR HALF DELIVERED | `core/vector_memory.py` — BaseVectorMemory ABC + Qdrant **local-mode** adapter (real engine, no server) + pure-python fallback; contract-tested parity incl. semantic retrieval order. Relational: SQLite hash-chained store shipped; PG/Timescale swap is deployment-phase adapter work (Doc 16) |
| Market Data Ingestion Pipelines (CCXT, Alpaca, Polygon.io) | CCXT LIVE-VERIFIED | BTC $76,491.81 through full pipeline with `is_simulated=false`; execution suite testnet rails contract-tested → `research/benchmarks/market_data_evidence.md`. Alpaca/Polygon key-gated |
| Backtesting & Simulation Engines (NautilusTrader vs Lean vs VectorBT) | COMPAT VERIFIED; same-task protocol REQUIRED | Both publish Py3.14 wheels (`group_b/install_compat.yaml`); own event-driven runner + walk-forward harness built and honestly executed (`research/reports/walk_forward_300b_90t30s.json`) |

Formal selection ADRs stay blocked exactly where the protocol demands more
evidence. Nothing was selected without evidence — that discipline held.

### Phase 3.0 CLOSURE — Prototype Integration (completed 2026-08-23)

Every designed domain was integrated end-to-end across build sessions
Phases 1–8 (log at bottom): data fabric → adversarial intelligence → strategy
lab → portfolio gate → order lifecycle → observation/postmortems → memory +
prediction ledger → finance back office → control plane/command center →
evolution & resilience drills. 124 tests green; determinism, no-look-ahead and
honesty invariants machine-enforced.

### Phase 4.0 CLOSURE — MVP Development (completed 2026-08-23)

MVP = AI-native institution on paper/shadow venues: live CCXT ingestion,
LLM debate w/ honest fallback, hallucination-checking verification firewall,
multi-family strategies, opportunity ranking, Kelly/DD-tier governor,
bracket-exit engine (+shadow), double-entry books, FIFO tax lots + CA gates,
compliance surveillance, audit-graph provenance walks, kill-switch +
reconciliation, RBAC console + command-center UI/API/metrics, challenger
trials, agent reputation, disaster drills, constitution-pinned boot.

### Phase 5.0 — Production Deployment: HUMAN-HELD GATES

1. Broker testnet credentials + shadow validation of the CCXT execution suite on a real venue
2. Tier-1 benchmark completion → formal selection ADRs
3. Licensed real-market data replacing synthetic goldens
4. Tax rules signed by a licensed professional for target jurisdiction(s)
5. Principal records APPROVE_LIVE_CAPITAL and amends CONSTITUTION §1 via ADR

---

### RE-INSPECTION & INTEGRATION PASS — COMPLETE (2026-08-23)

Fresh audit: 190 code files / ~10.9k LOC · 129→132 tests green · OSS archive 74 zips
(1 duplicate copy of an already-catalogued repo; no new entries). Four target
architectures verified against code reality; genuine gaps closed:

| Target | Verified working | Gap found & CLOSED this pass |
|---|---|---|
| Multi-agent research/verification | DebateEngine BULL→BEAR→QUANT→MODERATOR w/ structured contracts + fallback; C3 evidence-grounded hallucination detection | **Agent roster**: `core/agents.py` AgentIdentity registrations persisted as AGENT_REGISTERED events for all 11 operational components |
| Provenance + memory + evaluation | Hash-chained store, prediction ledger, calibration/Brier, postmortems | **Vector memory wired in**: every settlement upserts lessons (`postmortem_lessons`); DebateEngine retrieves similar past lessons into moderator context (MEMORY turn in transcript) — retrieval failures can never break research |
| Risk/governor controls | Governor gate, kill-switch+persisted lockout, reconciliation, emergency machine, constitution boot pin | ACL mechanism shipped earlier; per-agent bus wiring documented as deployment-phase (composition-root trust domain today) |
| Accounting/tax/CA | Double-entry books balanced across replays; FIFO lots; cited rules; filing gate | **Auto-finalization wired**: run end aggregates all disposals → single cited TaxComputation (TAX_COMPUTATION event) → CA review item auto-PREPARED; export still blocked without human APPROVED_BY_CA |

Gates after integration: **pytest 132 passed · ruff clean · mypy strict clean (71 files)**

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

### Phase 7 CONTROL PLANE & COMMAND CENTER — COMPLETE (2026-08-23)

- [x] **RBAC control plane** (`core/control_plane.py`): 4 roles × 10 actions matrix; every attempt (granted or denied) appended to the hash-chained audit log as CONTROL_ACTION; blank operator ids refused; actions wired to live components (freeze sets StrategyAgent state, reset clears RiskGovernor lockout, kill-switch flattens via adverse pricing)
- [x] **Command-center API** (`api/views.py` + `api/server.py`): zero-dependency stdlib HTTP server; endpoints executive / executions / decisions/{id} / risk / accounting / research / health; POST /api/v1/control/{action} enforces RBAC over HTTP (403 denials); Prometheus text exposition at /metrics
- [x] **Decision drill-down implemented** (Directive 53/54): DECISION→REASON→EVIDENCE→COUNTERARGS→VERIFICATION(scores+flags)→RISK(levels)→OUTCOME(pnl/exit/lessons) with chain_complete integrity flag
- [x] **UI v0** (`ui/index.html`): dark institutional theme, status pills (STATE/DD/CHAIN/CASH), auto-refreshing cards, executions table with click-through drill-down, risk/accounting tabs — vanilla JS, no framework
- [x] **Thread-safe persistence**: SqliteMemoryStore now shares its connection across event-loop + server threads under RLock
- [x] **Live demo executed**: replay → serve() → all endpoints verified → OPERATOR pause over HTTP → chain_complete drilldown → DEMO OK
- [x] Gates: **pytest 110 passed +1 opt-in · ruff clean · mypy strict clean (63 files)**

Deferred honestly: OTel/LangFuse SDK integration (Prometheus exposition shipped); richer UI framework decision deferred until product phase.

Next: Phase 8 Evolution & Resilience (challenger architecture, agent reputation from calibration, disaster-lab chaos drills, hardening pass).

---

### PHASE 9+ PRODUCTION-READINESS HARDENING — IN PROGRESS (2026-08-23)

#### Session: Constitution + Broker Suite + Walk-Forward Execution
- [x] **SYSTEM CONSTITUTION RATIFIED** (`CONSTITUTION.md` v1.0.0): capital limits, authority boundaries, honesty laws, amendment procedure — **SHA-256 pinned** in `core/constitution.py`; every runner boot verifies (`enforce_at_boot`), mismatch refuses startup; tamper test proves detection; pin script shipped (`scripts/pin_constitution.py`)
- [x] **CCXT execution suite completed**: real market-order routing, venue response→receipt mapping (avg price/filled/fee), sell-side routing, symbol-map round-trip on positions_snapshot, cancel_all delegation, sandbox-mode verification — all contract-tested against a fake client mirroring ccxt API shapes; **real-money gate enforced in code**: LIVE venue requires `allow_real_money=True` which the composition root grants only after reading a LIVE_CAPITAL_APPROVAL audit event
- [x] **Walk-forward harness executed for real**: 7 windows (300 bars, 90/30) → aggregate test PnL −305.89, 0 overfit windows, integrity gates passed pre-run → `research/reports/walk_forward_300b_90t30s.json`
- [x] Gates: **pytest 124 passed +1 opt-in · ruff clean · mypy strict clean (67 files)**

#### Remaining before ANY live capital (constitution-gated)
1. Broker testnet keys + live shadow validation of the CCXT suite against a real venue
2. Tier-1 benchmark ADRs (Group C requires broker infra; A/B require full protocol runs)
3. Licensed real-market data replacing synthetic goldens
4. Jurisdiction-specific tax rules signed by licensed professional (CA/CPA)
5. Human principal records APPROVE_LIVE_CAPITAL + amends CONSTITUTION §1 via ADR

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
