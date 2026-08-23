# AIOS-0X Roadmap
Version 1.0.0 | Vertical-slice driven (Directive 72): every milestone ships a working, tested system.
Maps directive phases 0-17 onto verified current state.

## Phase 0 - DISCOVERY [COMPLETE 2026-08-23]
Inspected AIOS-0X + OSS archive; mapped docs, code, tests; executed suite (32/32); produced
docs/master/* deliverables. Key findings in GAP_ANALYSIS.md.

## Phase 0.5 - FOUNDATION HARDENING (immediate; no new features)
- git init; .gitignore (.env, caches, data/, __pycache__)
- pyproject.toml + locked deps (pydantic v2, pytest, pytest-asyncio, ruff, mypy)
- Fix defects D1-D7 (see GAP_ANALYSIS section 3) with tests encoding the fixes
- ADR-002: canonical event topics + provenance/lineage fields on payloads
- ADR-003: R:R staging documented (C2 >=2.0 research heuristic vs firewall >=1.5 hard floor) or unified
- Reconcile Doc 19 catalog to ledger vocabulary; fix twin-folder links to relative paths
- Exit criteria: clean lint+mypy+tests; reproducible env from lockfile

## Phase 1 - HONEST VERTICAL SLICE (local, zero capital, zero LLM cost)
- Historical replay source adapter (parquet golden sets per Phase 2B universe) implementing BaseDataFetcher
- SQLite persistence: observations, predictions (ledger), postmortems, risk decisions; raw event file sink
- C6 rewrite: market-driven exits only; attribution fields; postmortem records
- C4 upgrade: direction-aware strategies w/ volatility-scaled levels (deterministic baseline)
- Risk telemetry stubs + decision audit log w/ hash chain
- Exit criteria: full loop over 2024-2025 dataset produces honest PnL series, calibration-ready
  prediction ledger, and postmortems; determinism test passes

## Phase 2 - INTELLIGNCE ONBOARDING (LLM layer)
- Model gateway via litellm-class ABC; model router v0 (cheap vs reasoning tiers)
- Prompt Lab v0 + initial prompts per PROMPT_REGISTRY backlog; structured outputs enforced
- C2 adversarial debate (bull/bear/quant/moderator) replacing template hypotheses
- C3 real verification: evidence packs, claim checking vs retrieved data, hallucination detection;
  confidence = rubric computation, not list lengths
- Cost accounting per decision recorded
- Gate: prompt eval harness green; hallucination rate below threshold on golden set

## Phase 3 - DATA FABRIC + WORLD INTELLIGENCE
- Real ingestion adapters behind ABCs (CCXT sandbox, alpaca-py paper, EDGAR/macro calendars, news API trial)
- Quality states + anomaly detection; DATA_ANOMALY reactions wired
- C10 event engine: classification, severity, affected assets; expectation engine v1
  (consensus vs actual vs priced-in for scheduled macro/earnings events); scenario cards pre/post events
- Regime engine v0 (vol/trend/liquidity labels) feeding memory + strategy conditioning

## Phase 4 - QUANT RESEARCH + STRATEGY LAB + PORTFOLIO
- Benchmark Group A/B/C execution -> formal selection ADRs (unblocks stack scale-out)
- Strategy families beyond baseline; walk-forward harness; backtest-integrity linters; cost/slippage models
- Opportunity engine ranking + alpha-decay routing; C9 portfolio allocator (Kelly-fraction/vol-parity,
  correlation caps) per frozen Doc 15
- Prediction ledger scoring live: Brier/calibration dashboards feed agent reputation v1

## Phase 5 - EXECUTION + RISK GOVERNOR
- Broker adapters (paper first, then micro live caps per constitution); order lifecycle + reconciliation
- Risk Governor as independent service owning drawdown truth, portfolio controls, kill-switch sequence,
  emergency state machine; bus ACL enforcement tests
- Shadow mode mandatory before any live routing

## Phase 6 - FINANCE BACK OFFICE
- Double-entry ledger; broker/statement reconciliation; tax lots + jurisdiction rule engine (cited rules +
  confidence; human/professional sign-off gate for filings); CA review workflow states; NAV computation;
  compliance surveillance hooks; audit graph query API (provenance walks)

## Phase 7 - CONTROL PLANE + UI
- Human control plane APIs (pause/cancel/freeze/limits/approvals) with RBAC
- Institutional command-center UI per Directive 53/54 views; decision drill-down:
  DECISION->REASON->EVIDENCE->AGENTS->COUNTERARGS->RISK->OUTCOME
- Observability complete: OTel traces, Prometheus metrics, LangFuse LLM tracing, cost dashboards

## Phase 8 - EVOLUTION + RESILIENCE
- Challenger architecture: candidate agents/prompts/strategies run shadow vs production; promotion ladder
- Agent reputation conditional scoring; team-composition learning
- SIM lab: synthetic generator, agent arena; DISASTER lab: crash/outage/data-corruption/memory-poisoning drills
- Hardening pass: chaos tests, security audit, performance at target throughputs

## Continuous (post-Phase 8)
Postmortems -> lessons -> prompt/policy updates via labs; OSS re-scan quarterly; model re-eval;
constitution changes only via ratified ADR + human approval.

## Sequencing Rules (binding)
1. No phase exit without exit criteria demonstrated by tests/evidence - never claimed without execution.
2. Any live-capital step requires explicit human authorization record.
3. Frozen Doc amendments require ADR (per ADR-001 governance).
