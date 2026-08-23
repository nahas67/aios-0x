# AIOS-0X Agent Registry
Version 1.0.0 | Status: ACTIVE (registry of implemented + planned agents)

## 1. Implemented Agents (verified 2026-08-23)

| Agent | Path | Type | Inputs | Outputs | Defects |
|---|---|---|---|---|---|
| DataAcquisitionAgent | communities/c1_data/data_agent.py | Deterministic | BaseDataFetcher | MarketDataPayload -> DATA_ACQUIRED | Only SimulatedDataFetcher exists |
| ResearchAgent | communities/c2_research/research_agent.py | Deterministic template | MarketDataPayload | CandidateHypothesis -> HYPOTHESIS_GENERATED | No LLM; fixed R:R=2.0; no debate protocol |
| VerificationAgent | communities/c3_verification/verification_agent.py | Structural checker | CandidateHypothesis | VerificationReport -> VERIFICATION_COMPLETED | Scores = list-length checks, not facts |
| StrategyAgent | communities/c4_strategy/strategy_agent.py | Deterministic template | VerificationReport + caches | StrategySpecification -> STRATEGY_GENERATED | BUY-only, fixed levels; holds unbounded caches; violates isolation via core import is OK but logic placeholder |
| ObservationAgent | communities/c6_observation/observation_agent.py | Deterministic | TradeExecutionReceipt + exit price | ObservationReport -> OBSERVATION_COMPLETED | on_trade_executed fabricates exit at fill*1.03 (CRITICAL - fake profit loop) |
| MemoryAgent | communities/c7_memory/memory_agent.py | In-RAM store | receipts/reports | MEMORY_STORED + summary dict | No persistence; lost on restart |
| EvolutionAgent | communities/c8_evolution/evolution_agent.py | Rule signal | memory summary | EvolutionSignal -> EVOLUTION_TRIGGERED | Cross-community import of c7 (violates .cursorrules); no enforcement mechanism |

Supporting: RiskFirewall (core/risk_firewall.py, deterministic), PaperEngine (simulation/paper_engine.py),
InMemoryEventBus (core/event_bus.py). Missing entirely: C5 execution agents, C9 portfolio agents.

## 2. Target Agent Architecture

### 2.1 Agent Record Schema (every agent must register)
```
AgentRecord:
  agent_id: uuid
  family: enum(C1..C12 per architecture)
  role: str
  class_name, version
  capabilities: list[Capability]        # enforced permissions
  models: list[ModelBinding]            # LLM/deterministic/statistical
  prompt_ids: list[prompt_id]
  reputation: ReputationScore           # conditional, multi-dimensional
  lifecycle_state: BIRTH|TRAINING|PAPER|EVALUATION|SHADOW|LIVE|PROBATION|RETIRED|ARCHIVED
```

### 2.2 Capability Permissions (Directive 79; enforced at bus/service layer)
- NEWS_AGENT: READ_NEWS, WRITE_RESEARCH
- RESEARCH_*: READ_DATA, READ_MEMORY, WRITE_HYPOTHESIS
- VERIFICATION_*: READ_RESEARCH, READ_MEMORY, WRITE_VERIFICATION
- STRATEGY_*: READ_RESEARCH, CREATE_STRATEGY (no data-write, no execute)
- RISK_GOVERNOR: READ_PORTFOLIO, APPROVE_OR_REJECT (cannot be overridden)
- EXECUTION_SERVICE: EXECUTE_APPROVED_ORDER (sole broker credential holder)
- OBSERVATION: READ_EXECUTIONS, WRITE_OBSERVATION
- MEMORY: READ_ALL_TOPICS (append-only), WRITE_MEMORY
- EVOLUTION: READ_MEMORY, WRITE_EVALUATION, PROPOSE_CHANGES (never direct prod mutation)
- TAX_AGENT: READ_LEDGER, WRITE_TAX_RECORDS
- COMPLIANCE: READ_ALL, WRITE_COMPLIANCE_FLAGS
No universal super-agent. Bus topics are capabilities: publish/subscribe rights are explicit per agent.

### 2.3 Planned Agent Families (activate incrementally; never all at once)
C1: market-data, news-ingestor, macro-calendar, dedup-sanitizer, quality-scorer
C2: bull-thesis, bear-thesis, quant-alpha, macro-analyst, debate-moderator (LLM-backed, structured output)
C3: fact-checker, source-validator, math-validator, confidence-gatekeeper, hallucination-hunter
C4: strategy-family specialists (momentum/mean-reversion/event/vol/options/crypto/macro), opportunity-ranker
C5: order-manager, slicer (TWAP/VWAP), reconciliation-agent, kill-switch-executor
C6: attribution-agent, postmortem-writer, counterfactual-evaluator
C7: persistence, embedder, retrieval, prediction-ledger-keeper
C8: evaluator, prompt-evolver, challenger-runner, reputation-auditor
C9: allocator (Kelly/vol-parity), correlation-controller, drawdown-guard
C10: event-detector, expectation-modeler, scenario-builder, participant-modeler
C11: bookkeeper, reconciler, tax-lot-accountant, ca-reviewer, nav-engineer, compliance-surveillor
C12: model-router, cost-accountant, health-monitor

### 2.4 Diversity Rule (Directive 17)
No two same-role agents share identical (model, prompt) pairs in adversarial settings. Mix LLM providers,
sizes, plus deterministic/statistical agents that carry veto power on quantitative claims.

### 2.5 Communication Types
PROPOSAL, EVIDENCE, QUESTION, COUNTERARGUMENT, REQUEST_DATA, REQUEST_VERIFICATION, HYPOTHESIS,
SCENARIO, PREDICTION, RISK_WARNING, DECISION, ESCALATION - all as typed Pydantic payloads with lineage IDs.

## 3. Reputation Model (Directive 26)
R_agent in [0,100] = 0.30*accuracy + 0.25*calibration + 0.20*verification_quality + 0.15*regime_conditionality
+ 0.10*contribution_to_decisions; separately track hallucination count, latency, cost.
Profit alone never determines rank (decision quality != outcome luck).

## 4. Migration Actions (immediate)
1. Fix c8 cross-community import (inject performance provider interface defined in schemas or core).
2. Remove fabricated exit price in c6; require real/simulated-market exit input.
3. Register all current agents with capability lists before adding new ones.
