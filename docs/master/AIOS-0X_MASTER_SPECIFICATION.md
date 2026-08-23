# AIOS-0X Master Specification
**Version:** 1.0.0 | **Date:** 2026-08-23 | **Status:** ACTIVE — supersedes conflicting content; defers to frozen Phase 1 specs where consistent
**Provenance:** Every claim below was verified against the filesystem on 2026-08-23 (source paths cited).

---

## 1. MISSION (RESTATED)

Build an **AI-native investment institution** — not a chatbot, bot, or dashboard — that maximizes
long-term risk-adjusted returns subject to capital preservation, drawdown, liquidity, execution,
operational, security, tax and regulatory constraints. `NO TRADE` and `INSUFFICIENT EVIDENCE`
are first-class intelligent decisions.

---

## 2. VERIFIED CURRENT STATE (as inspected 2026-08-23)

### 2.1 Documentation Baseline (Phase 1 — Frozen & Locked, ADR-001)
- 19 numbered specifications (`docs/00…19`) + ADR-000/ADR-001 exist and are internally coherent.
- Defines 9 communities (C1 Data, C2 Research, C3 Verification, C4 Strategy, C5 Execution,
  C6 Observation, C7 Memory, C8 Evolution, C9 Portfolio), AI Constitution (4 Laws), event bus
  spec (priorities, retries, DLQ), registries & feature store, audit graph & digital-twin sims.
- Key frozen numbers: verification ≥70/100; R:R ≥1.5 (firewall) / ≥2.0 (research stage);
  position cap 5%; daily drawdown 3% ⇒ emergency shutdown; correlation ρ>0.80 ⇒ pair cap 10%.

### 2.2 Technology Acquisition (Phase 2 — active)
- 73 ZIPs verified present in `C:\Users\nahas\OneDrive\Desktop\github reserch` (count matches ledger).
- Reconciled dispositions (Phase 2 ledger): 13 research-preference, 20 benchmark-candidate,
  23 study, 6 reference, 2 deferred, 9 rejected. **FORMAL SELECTION = 0** (correct discipline).
- Benchmark Protocol v0.1 defined but **pre-execution** (`research/benchmarks/` does not exist).

### 2.3 Implemented Code (all verified by reading every file; tests executed locally)
| Area | Reality |
|---|---|
| Core | `core/event_bus.py` (in-memory asyncio bus, 8 topics, worker queue), `core/risk_firewall.py` (deterministic rules: drawdown, stop distance, R:R, size cap) |
| Agents | 6 rule-based agents: c1_data, c2_research, c3_verification, c4_strategy, c6_observation, c7_memory, c8_evolution (**c5_execution and c9_portfolio have NO code**) |
| Contracts | `schemas/contracts.py`: 7 Pydantic v2 payloads (MarketDataPayload → ObservationReport) |
| Simulation | `simulation/paper_engine.py`: single-fill paper execution, slippage+fee model |
| Persistence | **NONE** — memory = Python lists in RAM; no DB, no files written |
| LLM | **NONE** — zero model calls; all "reasoning" is string templates |
| Data | Only `SimulatedDataFetcher` (hardcoded BTC≈45000, else 100) |
| Tests | **32/32 PASS** (pytest 9.0.2, Python 3.14.4, 0.14s) |
| Packaging | **No pyproject.toml/requirements.txt/lockfile; NOT a git repository** |

### 2.4 Defects & Violations Found (evidence-backed)
1. **Fake profit feedback:** `c6_observation/observation_agent.py:83` simulates exit at `fill_price * 1.03`
   for every trade ⇒ closed loop reports ~100% win rate by construction. Violates Constitution Law 1
   spirit and Directive §73 (No Fake Features). Must be replaced with market-driven exits.
2. **Cross-community import violation:** `c8_evolution/evolution_agent.py:8` imports `communities.c7_memory.memory_agent`.
   Breaks `.cursorrules` §2 and Doc 01 isolation rules.
3. **StrategyAgent is a BUY-only template** (`strategy_agent.py:52-64`): fixed −3%/+6% levels, ignores direction,
   sentiment, volatility; `RiskFirewall.evaluate_strategy` ignores its `current_portfolio_value` parameter.
4. **PaperEngine never updates balance or holds positions** — no portfolio state exists at all.
5. **Event-topic naming drift:** code uses short topics (`data.acquired`); Docs 01/14 specify `aios.<c#>.<event>`.
6. **Doc 19 catalog conflicts** with Phase 2 Selection Ledger (vocabulary + divergent scores).
7. **67 stale absolute links** point to duplicate twin folder `Desktop\AIOS` (verified to exist) instead of `AIOS-0X`.
8. **R:R thresholds differ by stage** (2.0 research vs 1.5 downstream) without documented rationale.
9. **Verification is structural only** (checks that lists are non-empty) — no factual checking despite Doc 04's 100-point rubric.
10. **Undeclared dependencies** (pydantic, pytest installed ad-hoc); violates reproducibility mandates.

---

## 3. GAP ANALYSIS SUMMARY (full detail: `GAP_ANALYSIS.md`)

Of the 31 directive domains (A–AE): **2 partially implemented** (D agent runtime — skeleton;
P risk governor — position-level only). **29 missing or stub-only**, including: real data fabric,
world/event intelligence, expectation/scenario/participant models, opportunity engine, strategy lab,
quant/backtest pipeline, portfolio engine, execution/broker layer, accounting, tax, CA, fund admin,
compliance, audit graph, security, observability, human control plane, UI/UX, API, disaster lab.

**Process gaps:** no VCS, no packaging, no CI, no lint/type gates (mypy named in .cursorrules, unconfigured).

---

## 4. TARGET ARCHITECTURE (summary — full detail: `AIOS-0X_ARCHITECTURE.md`)

Evolve, don't discard: the frozen 9-community topology is sound and maps directly onto directive domains.
Additions required:

```
                    ┌─────────────── HUMAN CONTROL PLANE + UI/UX + API ───────────────┐
  WORLD ──► C1 DATA FABRIC (+quality/provenance) ──► C10 WORLD INTELLIGENCE            │
                │        (events, expectation, scenarios, participants)               │
                ▼                                                                     │
           C2 RESEARCH ⇄ C3 VERIFICATION/TRUTH (evidence graph)                       │
                ▼                                                                     │
           C4 STRATEGY LAB ◄── OPPORTUNITY ENGINE ◄── REGIME ENGINE                   │
                ▼                                                                     │
           C9 PORTFOLIO ENGINE ──► RISK GOVERNOR (independent, kill-switch)           │
                ▼                                                                     │
           C5 EXECUTION (paper→live brokers, TWAP/VWAP, reconciliation)               │
                ▼                                                                     │
           C6 OBSERVATION (attribution, postmortems, counterfactuals)                 │
                ▼                                                                     │
           C7 MEMORY FABRIC (raw→validated→belief→summary; tiered storage)            │
                ▼                                                                     │
           C8 EVOLUTION (challenger, prompt lab, agent reputation)                    │
                                                                                │
  CROSS-CUTTING: C11 FINANCE BACK OFFICE (accounting/tax/CA/fund admin/          │
                 compliance/audit) • SECURITY/RBAC • OBSERVABILITY • EVENT BUS   │
                 (NATS-class, DLQ, idempotency) • MODEL ROUTER (LLM+deterministic)│
                 • SIMULATION/DISASTER LABS • SYSTEM CONSTITUTION (immutable)    │
```

Non-negotiables carried forward: typed Pydantic contracts only; zero cross-community imports;
deterministic non-LLM risk authority; append-only audit lineage; simulation tagged `is_simulated`;
no look-ahead; staged capital (backtest→paper→shadow→limited→live).

---

## 5. BUILD-BUY DECISIONS (per Directive §67; details in `AIOS-0X_OSS_CATALOG.md`)
- **Reuse via ABC adapters** (already mandated by Doc 16): LangGraph-class orchestration (pending Group A
  benchmarks), NATS JetStream-class bus, PostgreSQL/TimescaleDB, Qdrant, CCXT/alpaca-py, MLflow,
  OpenTelemetry/LangFuse, PyPortfolioOpt, OPA/OpenBao.
- **Build (confirmed custom, matches Phase 2 BUILD list):** adversarial debate engine, risk governor
  extensions, TWAP/VWAP slicer, agent lifecycle/reputation, verification auto-tuner, synthetic market
  generator, audit-graph API, sentiment-velocity ingestor — plus everything in §3 marked missing with
  no viable OSS (accounting/tax/fund-admin cores, expectation engine, participant model).
- **Gate:** formal selections remain blocked behind Tier-1 benchmarks (Groups A/B/C) per Phase 2B.

## 6. IMMEDIATE NEXT ACTIONS (approved roadmap head — full: `AIOS-0X_ROADMAP.md`)
1. **Foundation hardening (Phase 2F):** git init + .gitignore, pyproject.toml + lockfile, ruff+mypy
   config, CI runner, fix defects §2.4 items 1–4, reconcile event-topic naming (ADR-002), archive twin-folder links.
2. **Vertical Slice 1:** replayable historical data adapter (parquet/CSV) → C1 → C2/C3 → C4 → risk →
   paper fills → C6 → SQLite-persisted C7 → honest postmortem (market-driven exits only).
3. **Tier-1 benchmarks (A/B/C)** to unlock formal technology selection ADRs.
4. Then proceed per roadmap phases 3–17 (data fabric → world intelligence → … → production readiness).

## 7. DECISIONS REQUESTED FROM HUMAN PRINCIPAL (per Directive §47)
None blocking Slice 0–1 (all local, zero capital). Required before later phases:
- Broker/exchange accounts + data licenses for live/paid data (C5/C1 expansion).
- Jurisdiction(s) for tax/compliance/fund administration (India CA workflows vs others).
- Risk appetite sign-off on System Constitution values before any live capital.
