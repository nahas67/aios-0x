# AIOS Master System Map & Documentation Index

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification (Frozen)
- **Target System**: AIOS (AI-Native Trading & Autonomous Research System)
- **Author**: AIOS System Architecture Team

---

## 1. System Map & Core Documentation Index

The AIOS architectural baseline is organized into 19 formal specification documents spanning 9 specialized AI agent communities, risk firewalls, governance rules, continuous training, infrastructure, registries, audit graphs, and technology acquisition frameworks.

```
+-----------------------------------------------------------------------------------+
|                           AIOS MASTER SYSTEM MAP                                  |
+-----------------------------------------------------------------------------------+
  01 Platform Architecture      --> Master System Overview & Inter-Community DAG
  02-05 Community Specs (C1-C4) --> Data, Research Debate, Verification, Strategy
  06 Continuous Training        --> Zero-Risk Paper, Replay, & Stress Environment
  07-10 Community Specs (C5-C8) --> Execution, Observation Audit, Memory, Evolution
  11 Supporting Systems         --> Deterministic Risk Firewall, Infrastructure
  12-14 Governance & Bus        --> AI Constitution, 5-Tier Hierarchy, Event Topics
  15 Portfolio Intelligence(C9) --> Cross-Strategy Allocation & Correlation Guard
  16 Tech Acquisition           --> 4-Step Open-Source Evaluation Framework
  17 Registries & Feature Store --> Experiment, Model, & Feature Storage
  18 Audit Graph & Digital Twin --> Line-of-Sight Provenance & Simulation Suite
  19 Master Tech Catalog        --> Open-Source Candidate Matrix (Phase 2.0)
+-----------------------------------------------------------------------------------+
```

---

## 2. Categorized Table of Contents

### Category 1: Platform Foundation & Core Architecture
- **[Doc 1.1: Overall Platform Architecture & Inter-Community Protocols](docs/01_platform_architecture.md)** (`docs/01_platform_architecture.md`)
  - AI-native paradigm, 9-community graph topology with non-linear feedback loops, pub/sub topic specs, and scalability tiers.

### Category 2: Upstream Intelligence Pipeline (C1–C4)
- **[Doc 1.2: Community 1 Specification (Data Acquisition)](docs/02_community_1_data.md)** (`docs/02_community_1_data.md`)
  - Multi-asset ingestion taxonomy, UTC ISO 8601 timestamping, ticker mapping, and price sanity filtering.
- **[Doc 1.3: Community 2 Specification (Research & Analysis)](docs/03_community_2_research.md)** (`docs/03_community_2_research.md`)
  - Multi-agent debate structure (Bull, Bear, Quant, Macro, Moderator), thesis formulation, and minimum $R:R \ge 2.0$ heuristics.
- **[Doc 1.4: Community 3 Specification (Verification Firewall)](docs/04_community_3_verification.md)** (`docs/04_community_3_verification.md`)
  - 100-point quality firewall rubric, hallucination detection, statistical fact-checking, and passing score threshold ($\ge 70.0$).
- **[Doc 1.5: Community 4 Specification (Strategy Generation)](docs/05_community_4_strategy.md)** (`docs/05_community_4_strategy.md`)
  - Parameter synthesis, price trigger rules, position sizing logic, and Risk Firewall submission protocol.

### Category 3: Portfolio Intelligence & Risk Control (C9 & Risk Firewall)
- **[Doc 1.15: Community 9 Specification (Portfolio Intelligence)](docs/15_community_9_portfolio_intelligence.md)** (`docs/15_community_9_portfolio_intelligence.md`)
  - Cross-strategy capital allocation (Fractional Kelly), asset correlation matrix analysis ($\rho > 0.80$ cap), and multi-tier drawdown guards.
- **[Doc 1.11: Supporting Systems Specification (Risk, Validation, Infrastructure)](docs/11_supporting_systems.md)** (`docs/11_supporting_systems.md`)
  - Non-LLM deterministic circuit breaker, daily drawdown limit (3.0%), max position size cap (5.0%), and panic kill-switch protocol.

### Category 4: Validation & Simulation Layer
- **[Doc 1.6: Continuous Training Environment Specification](docs/06_continuous_training.md)** (`docs/06_continuous_training.md`)
  - Zero-capital-risk sandbox, paper trading engine, walk-forward testing (90/30 rolling), event replay, and promotion gateways.
- **[Doc 1.18: Decision Audit Graph & Digital Twin Simulation Layer](docs/18_decision_audit_graph_and_simulation.md)** (`docs/18_decision_audit_graph_and_simulation.md`)
  - Line-of-sight decision provenance graph and 4-tier Digital Twin simulation suite (Historical Replay, Synthetic Market, Agent Arena, Black Swan).

### Category 5: Execution, Observation & Meta-Learning Pipeline (C5–C8)
- **[Doc 1.7: Community 5 Specification (Live Trading Execution)](docs/07_community_5_execution.md)** (`docs/07_community_5_execution.md`)
  - Order routing (CCXT, Alpaca), TWAP/VWAP execution slicing, rate limiting, and 3-step emergency liquidation protocol.
- **[Doc 1.8: Community 6 Specification (Observation & Audit)](docs/08_community_6_observation.md)** (`docs/08_community_6_observation.md`)
  - Realized PnL attribution, slippage variance scoring, prediction accuracy auditing, and model drift detection.
- **[Doc 1.9: Community 7 Specification (Memory Architecture)](docs/09_community_7_memory.md)** (`docs/09_community_7_memory.md`)
  - Short-term Redis cache, PostgreSQL relational audit log, TimescaleDB time-series hypertables, and Qdrant semantic vector memory.
- **[Doc 1.10: Community 8 Specification (Evolution Mechanisms)](docs/10_community_8_evolution.md)** (`docs/10_community_8_evolution.md`)
  - Auto-tuning verification thresholds, strategy alpha decay triggers (3 consecutive stop-outs / Sharpe < 1.0), and feedback routing.

### Category 6: Governance, Messaging & System Security
- **[Doc 1.12: AI Constitution & Governing Laws](docs/12_ai_constitution.md)** (`docs/12_ai_constitution.md`)
  - The 4 non-negotiable core laws: Veracity, Gateway Integrity, Decision Provenance, and Empirical Primacy.
- **[Doc 1.13: Organization, Governance, Agent Lifecycle & Reputation](docs/13_organization_and_governance.md)** (`docs/13_organization_and_governance.md`)
  - 5-layer corporate hierarchy, 8-stage agent lifecycle (Birth -> Archive), and 6-factor reputation scoring matrix.
- **[Doc 1.14: Event Bus & Messaging Architecture Specification](docs/14_event_bus_and_messaging_spec.md)** (`docs/14_event_bus_and_messaging_spec.md`)
  - Topic namespace taxonomy, priority tiers (0–3), retry policy, exponential backoff, and Dead Letter Queue (DLQ) handling.

### Category 7: Registries, Catalogs & Tech Acquisition
- **[Doc 1.16: Open-Source Technology Acquisition Framework](docs/16_technology_acquisition_framework.md)** (`docs/16_technology_acquisition_framework.md`)
  - 4-step acquisition pipeline, 100-point evaluation rubric, ABC wrappers, and zero lock-in strategy.
- **[Doc 1.17: Registries & Feature Store Specification](docs/17_registries_and_feature_store.md)** (`docs/17_registries_and_feature_store.md`)
  - Experiment Registry schema, Model Registry governance system (`litellm`), and Centralized Feature Store (TimescaleDB/Redis).
- **[Doc 1.19: Master Technology Catalog](docs/19_master_technology_catalog.md)** (`docs/19_master_technology_catalog.md`)
  - Schema and matrix for evaluating candidate open-source projects during Phase 2.0.

---

## 3. Architecture Decision Records (ADRs)
Architectural changes and freeze decisions are permanently recorded in `docs/adrs/`:
- **[ADR-000: Architecture Decision Record Template](docs/adrs/ADR-000_template.md)** (`docs/adrs/ADR-000_template.md`)
- **[ADR-001: Architecture Baseline Freeze (Phase 1.0)](docs/adrs/ADR-001_architecture_baseline_freeze.md)** (`docs/adrs/ADR-001_architecture_baseline_freeze.md`)

---

## 4. Document Verification & Compliance

This master index is tracked in [CHECKPOINT.md](CHECKPOINT.md) as the primary navigation map for **Phase 1.0 – Architecture Baseline (Frozen)**.
