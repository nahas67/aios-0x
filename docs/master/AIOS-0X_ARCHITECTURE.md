# AIOS-0X Target Architecture
Version 1.0.0 | Status: PROPOSED (amendments to frozen Doc 01-18 require ADR-002)

## 0. Design Principles
1. Evolve the frozen 9-community topology. Event-driven mesh, never a linear pipeline.
2. Typed Pydantic contracts on every boundary; zero cross-community imports.
3. Heterogeneous intelligence: LLMs, deterministic code, statistics, simulations. Right intelligence per problem; expensive reasoning only where justified (Model Router).
4. Independent risk authority; immutable constitution; humans own capital, security, legal acts.
5. Full traceability: decision -> model -> prompt -> memory -> evidence -> source -> timestamp -> outcome.
6. No look-ahead ever; preserve information snapshots at decision time.
7. Assume component failure everywhere: timeouts, retries, fallbacks, circuit breakers, reconciliation.

## 1. Community Map (current state -> target state)

| Community | Current State | Target Additions |
|---|---|---|
| C1 Data Fabric | SimulatedDataFetcher only | Multi-source ingestion (CCXT, alpaca-py, EDGAR, macro calendars, news); data-quality states LIVE/FRESH/AGING/STALE/EXPIRED/UNKNOWN/CORRUPTED; dedup/sanity; provenance (source, retrieval_ts, license, hash); persistence; feature store per Doc 17 |
| C2 Research | Template hypothesis strings | Adversarial debate (Bull/Bear/Quant/Macro/Moderator) via LLM structured outputs; prediction ledger writes; regime-conditioned memory lookup |
| C3 Verification / Truth | Structural checks only | Evidence graph (claim->evidence->source->document->timestamp); source-independence counting; numerical re-validation; real 100-point rubric; calibration tracking |
| C4 Strategy Lab | BUY-only fixed template | Multi-family strategy generation; Opportunity Engine ranking (expected return x probability, costs, liquidity, alpha decay, correlation, tail risk); alpha-decay routing |
| C5 Execution | ABSENT (paper_engine substitutes) | Broker adapters behind ABC (ccxt/alpaca-py); order lifecycle (validate/route/cancel/partial/retry/reconcile); TWAP/VWAP slicer; 3-step kill-switch implementation |
| C6 Observation | Fabricated +3% exits | Market-driven outcome measurement; performance attribution (alpha/beta/timing/execution/luck); postmortem engine; counterfactual engine; decision-quality scoring |
| C7 Memory | RAM lists | Tiered fabric: raw immutable store -> validated -> belief -> summary with source refs; SQLite/PG + Qdrant vectors + cache; prediction ledger; regime memory |
| C8 Evolution | Trivial win-rate signal | Challenger architecture; Prompt Lab (mutate/evaluate/regression-gate prompts); agent reputation (conditional, multi-dimensional); team composition learning; promotion pipeline only |
| C9 Portfolio | ABSENT | Fractional Kelly + vol parity; correlation caps rho>0.80; drawdown guard tiers; PortfolioAllocationPlan |

## 2. New Communities / Services (required by master directive)

| ID | Name | Responsibility |
|----|------|----------------|
| C10 | World Intelligence | Real-time event engine; expectation engine (expected vs actual vs priced-in); pre-event scenario cards (base/bull/bear/unexpected/extreme with probabilities); market participant model; world model graph (entities, first/second/third-order effects) |
| C11 | Finance Back Office | Accounting ledger (double-entry), tax lots/cost basis/jurisdiction rules with cited law + confidence, CA review workflows, fund administration (NAV, fees, subscriptions/redemptions), compliance surveillance, audit exports |
| C12 | System Platform | Model Router, cost intelligence, observability (OTel + LangFuse + Prometheus/Grafana), security (RBAC, capability permissions per agent, secret isolation, OpenBao-class vault, OPA-class policy), API platform, health model |
| SIM | Simulation + Disaster Labs | Historical replay, synthetic generator, agent arena, black-swan suite, chaos scenarios (exchange outage, data corruption, memory poisoning, model failure) per Docs 18 + Directive 60 |
| GOV | Governance Plane | Immutable SYSTEM CONSTITUTION; human control plane APIs (pause, cancel, freeze, limits, approvals); ADR registry; emergency states NORMAL..EMERGENCY_HALT |

## 3. Event Backbone
- Local mode: current InMemoryEventBus retained for tests/dev.
- Durable mode: NATS JetStream adapter implementing BaseEventBus (per Doc 16 ABC rule): priorities, at-least-once + idempotency keys, retries 100ms/500ms/2s, DLQ with replay, topic namespace `aios.<community>.<event>`.
- Cross-cutting reactions required: market shock can halt execution; data-integrity event can freeze strategy publishing; tax event touches accounting/portfolio/reporting.

## 4. Data Architecture
Polyglot per Doc 09/Directive 55: relational (PostgreSQL/SQLite local) for ledgers/audit; time-series (Timescale) for ticks/bars/features; vector (Qdrant) for semantic memory; object storage (parquet) for raw history; event log append-only. No single-database forcing.

## 5. Intelligence & Model Routing
Router chooses: deterministic code > cheap model > specialist > reasoning model > multi-agent debate > simulation, by task complexity/latency/cost/accuracy needs. All LLM calls via gateway (litellm-class) with provider failover; every call logged (model version, prompt version, tokens, cost, latency).

## 6. Security Model (summary; full: AIOS-0X_SECURITY_MODEL.md)
Capability-based permissions per agent family; no universal credentials; secrets only via pydantic-settings/vault; execution service holds broker creds in isolation - agents never see them; signed audit events; least privilege enforced at bus level (topics are capabilities).

## 7. Deployment Topology (target)
Phase A (local): single process, SQLite + parquet + embedded vector store, paper-only.
Phase B (workstation): dockerized PG/Timescale/Qdrant/NATS; UI served locally; shadow trading.
Phase C (production): K8s or hardened VM set, HA data stores, live capital gated by constitution + human approvals.

## 8. Key Invariants (machine-checkable)
1. Every StrategySpecification carries hypothesis_id lineage to raw evidence.
2. No trade executes without RiskGovernor.approve() recorded in audit log.
3. Every persisted observation references actual market prices, never fabricated exits.
4. All simulated artifacts tagged is_simulated=True end-to-end.
5. Decision-time snapshot stored for every executed or rejected strategy.
6. Constitution file hash verified at boot; mismatch = refuse to start.
