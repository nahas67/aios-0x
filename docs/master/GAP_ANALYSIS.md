# AIOS-0X Gap Analysis
Version 1.0.0 | Basis: filesystem inspection + test execution 2026-08-23 vs Master Directive domains A-AE

Legend: [x] exists+verified | [~] partial/stub | [ ] missing

## 1. Domain Coverage Matrix
| Domain | Status | Evidence & Required Work |
|---|---|---|
| A Data Fabric | [ ] | Only SimulatedDataFetcher (hardcoded prices). Need real adapters (ccxt/alpaca-py/EDGAR/macro), quality states, provenance, persistence |
| B Real-Time Event Fabric | [~] | InMemoryEventBus solid for dev; missing durability, priorities, DLQ, ACL, idempotency keys |
| C World Intelligence | [ ] | No news/macro/geopolitics ingestion; no event engine |
| D Agent Runtime | [~] | 6 deterministic agents run in tested loop; no LLM gateway, no model router, no agent registry/identity |
| E Agent Society | [~] | Single agent per community; no specialization, no debate protocol, no communication types beyond payloads |
| F Memory Fabric | [ ] | RAM lists only; no raw log, vectors, prediction ledger |
| G Truth / Verification | [~] | Gatekeeping flow correct; scoring is structural (list lengths), not factual |
| H World Model | [ ] | Absent (entities/relationships/effects) |
| I Expectation Engine | [ ] | Absent - the expected-vs-actual-vs-priced-in core is nowhere |
| J Scenario Engine | [ ] | Absent |
| K Participant Model | [ ] | Absent |
| L Opportunity Engine | [ ] | Absent |
| M Strategy Laboratory | [~] | One BUY template; no families, no discovery loop |
| N Quant Research | [ ] | No backtesting integration, walk-forward, or cost models yet |
| O Portfolio Engine | [ ] | C9 spec'd frozen but zero code |
| P Risk Governor | [~] | Deterministic position gate works; portfolio-level controls + kill-switch absent |
| Q Execution Engine | [ ] | Paper fills only; no broker adapter, order lifecycle, reconciliation |
| R Accounting | [ ] | Absent |
| S Tax Administrator | [ ] | Absent |
| T CA / Finance Workflows | [ ] | Absent |
| U Fund Administration | [ ] | Absent |
| V Compliance | [ ] | Absent |
| W Audit Systems | [ ] | Lineage IDs exist on payloads; graph store/query API absent |
| X Security | [ ] | Nothing implemented (see Security Model minimums) |
| Y Observability | [ ] | Logging only; no metrics/traces/cost tracking |
| Z Evolution Engine | [~] | Win-rate signal only; no challenger/prompt-lab/reputation machinery |
| AA Human Control Plane | [ ] | Absent (no pause/cancel/freeze APIs) |
| AB UI/UX | [ ] | Absent entirely |
| AC API Platform | [ ] | Absent |
| AD Simulation Laboratory | [~] | Paper engine only; replay/stress/synthetic absent |
| AE Disaster Laboratory | [ ] | Absent |

## 2. Engineering Process Gaps
1. Not a git repository - violates reproducibility/versioning mandates (Directive 93). HIGHEST priority.
2. No pyproject.toml/requirements lock - dependencies undeclared.
3. No lint/type config despite .cursorrules mandating mypy strictness.
4. No CI runner.
5. Documentation drift: Doc 19 vs Phase 2 ledger; 67 stale links to twin folder Desktop\AIOS;
   topic naming code-vs-docs; R:R 2.0 vs 1.5 undocumented staging.

## 3. Correctness Defects (must-fix before any further feature work)
D1 Fake profit loop: c6 fabricates exit = fill*1.03 (observation_agent.py:83). Encodes 100% win rate. CRITICAL.
D2 Cross-community import c8->c7 (evolution_agent.py:8). Violates .cursorrules/D01 isolation.
D3 StrategyAgent BUY-only fixed geometry; ignores direction/volatility/state.
D4 RiskFirewall ignores current_portfolio_value argument.
D5 PaperEngine never mutates balance/positions - portfolio state nonexistent.
D6 Unbounded in-memory caches in StrategyAgent (leak over long runs).
D7 VerificationReport validator silently overrides explicit is_verified input (minor, document or fix).

## 4. Knowledge Gaps Requiring Research/Benchmarks (tracked in Phase 2B)
- Group A orchestration winner (LangGraph vs CrewAI vs MS AF vs OpenGeni) - blocks agent runtime scale-out.
- Group B backtest engine (NautilusTrader LGPL legal review vs Lean vs VectorBT) - blocks Strategy Lab.
- Group C bus (NATS vs Redpanda [+Redis]) - blocks durable deployment topology.
- Embedding dim conflict (384 local vs 768 spec) must be resolved before vector schema freeze.

## 5. Prioritized Remediation Order
P0: git init; packaging+lock; fix D1-D7; ADR-002 (topics namespace + provenance fields).
P1: parquet replay data source; SQLite memory; honest postmortems; risk telemetry stubs; observability basics.
P2: Tier-1 benchmark execution -> selection ADRs; LLM gateway + Prompt Lab v0; adversarial C2/C3 upgrade.
P3: World Intelligence C10 (events, expectation, scenarios); Opportunity Engine; Portfolio C9.
P4: Execution adapters (paper->broker sandbox); Risk Governor service; kill-switch.
P5: Finance back office (ledger/tax lots/CA workflows); compliance hooks; audit graph API.
P6: UI command center + human control plane; SIM/disaster labs; evolution/challenger full loop.
