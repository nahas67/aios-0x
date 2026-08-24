# AIOS-0X: Prototype vs Original Architecture — Gap Analysis
Version 1.0.0 | 2026-08-24

## The honest assessment

The current codebase (145 tests, ~11k LOC, 10 phases) is a **prototype** that
validated the trading logic loop. The original architecture describes an
**operating system** — a fundamentally different thing.

The prototype built the house. The original architecture is the city plan.

---

## 1. THE CORE INSIGHT WE MISSED

Our prototype organized code by **trading workflow stages** (C1 Data → C2
Research → C3 Verification → C4 Strategy → ... → C11 Finance).

The original architecture organizes by **platform capability planes**:

| Plane | Authority | Contains |
|---|---|---|
| Experience | NONE (cannot bypass control plane) | UI, API, CLI, Notifications |
| Control | ALL state transitions | Identity, Agent Registry, Capability Router, State Controller, Policy, Promotion, Rollback |
| Intelligence | PROPOSALS ONLY | Agent Runtime, Planning, Reasoning, Criticism, Evaluation, Reflection |
| Research | HYPOTHESES + EVIDENCE | Research Workspace, Evidence Collection, Hypothesis Engine, Knowledge Graph |
| Execution | ORDER INTENT (post-authorization) | Strategy Runtime, Simulation, Backtesting, Paper, Live |
| Deterministic Authority | ALLOW / DENY / REQUIRE APPROVAL | Schema Validation, Auth, Policy, Risk Limits, Kill Switch |
| Data & State | PERSISTENCE | PostgreSQL, Event Log, Registries, Provenance Graph |
| Infrastructure | RELIABILITY | Event Bus, Workflow Runtime, Secrets, Observability |

**The prototype collapsed all 8 planes into one process.** That's fine for
validating trading logic, but it means there is no operating system — just a
trading bot with good intentions.

---

## 2. WHAT THE PROTOTYPE GOT RIGHT (carries forward)

| Component | Prototype status | Original architecture mapping |
|---|---|---|
| Honest P&L (no fabricated exits) | ✅ Enforced in code | Evidence architecture |
| Hallucination detection (numeric vs evidence) | ✅ C3 VerificationAgent | Intelligence Plane → Critic |
| Risk governor (Kelly/DD/caps) | ✅ C9 PortfolioGovernor | Deterministic Authority Plane → Risk Limits |
| Kill switch + persisted lockout | ✅ RiskGovernor + audit log | Deterministic Authority Plane → Kill Switch |
| Double-entry ledger (zero-sum) | ✅ C11 Ledger | Data & State Plane → Transactional State |
| Tax lots + CA review + filing gate | ✅ C11 TaxEngine + CAWorkflow | Data & State Plane → Compliance |
| Prediction ledger + Brier | ✅ C7 PredictionRecord | Data & State Plane → Experiment Registry |
| Challenger trials + human gate | ✅ C8 ChallengeRegistry | Control Plane → Promotion Control |
| RBAC console | ✅ ControlPlane | Control Plane → Identity + Policy |
| Constitution boot pinning | ✅ SHA-256 enforced | Control Plane → Configuration |
| Reconciliation loop | ✅ Per-bar venue vs mirror | Execution Plane → Position State |
| Postmortem engine | ✅ C6 PostmortemEngine | Intelligence Plane → Post-Mortem Agent |
| Paper graduation criteria | ✅ /api/v1/graduation | Execution Plane → Paper Trading |
| Memory log (pending→resolved) | ✅ TradingMemoryLog | Data & State Plane → Memory |

---

## 3. WHAT IS ENTIRELY MISSING (the real system)

These are not "features to add." They are **architectural layers that don't
exist in any form** in the prototype.

### 3.1 AIOS KERNEL (the owned core)

```
AIOS Kernel
├── Identity Model           — WHO is acting (human/agent/service/workflow)
├── Capability Model         — WHAT can be requested (AIOS.backtest, AIOS.execute...)
├── Contract Registry        — versioned interfaces for every capability
├── State Machine Engine     — formal state transitions with receipts
├── Authority Gateway        — the ONLY path to mutate high-authority state
├── Decision Receipt Engine  — every decision generates a receipt
├── Provenance Model         — full lineage graph (source→...→postmortem)
├── Promotion Controller     — controlled artifact promotion
├── Rollback Controller      — known rollback targets for every promotion
└── Plugin/Adapter Registry  — OSS implementations behind capability interfaces
```

**Why this matters:** Without a kernel, there is no operating system. The
prototype has business logic but no OS primitives. Adding a new agent, a new
data source, or a new backtest engine currently requires code changes. With a
kernel, they are registrations.

### 3.2 STATE MACHINE ENGINE

Every important object (strategy, hypothesis, experiment, dataset) has a
formal lifecycle. Transitions require:

```
current_state + requested_state + actor + reason + evidence + policy_check → receipt
```

Example (strategy):
```
IDEA → HYPOTHESIS → DRAFT → VALIDATED → BACKTESTED → EVALUATED
  → APPROVED_FOR_PAPER → PAPER → LIVE_CANDIDATE → AUTHORIZED_LIVE → LIVE
                                                    → PAUSED → RETIRED
```

No direct IDEA → LIVE. Ever.

The prototype has enum fields (`lifecycle_state`) but no state machine engine
that enforces transitions.

### 3.3 FIRST-CLASS HYPOTHESIS OBJECTS

```
Hypothesis
├── hypothesis_id
├── statement
├── rationale
├── expected_outcome
├── applicable_regime
├── assumptions
├── evidence[]          ← linked Evidence Packages
├── confidence
├── status              ← UNTESTED|TESTING|SUPPORTED|PARTIALLY_SUPPORTED|REJECTED|INVALIDATED|SUPERSEDED
└── parent_hypotheses[] ← lineage
```

The prototype has `CandidateHypothesis` as a transient debate payload. The
original architecture treats hypotheses as **persistent, versioned, linked
knowledge objects** that survive across sessions.

**Rejected hypotheses are valuable negative knowledge.** They compound.

### 3.4 EVIDENCE PACKAGES

```
EvidencePackage
├── evidence_id
├── source
├── source_version
├── retrieval_time
├── content_hash
├── claims[]
├── confidence
├── provenance
└── linked_hypotheses[]
```

The prototype has `supporting_arguments: list[str]` — free-text strings. The
original architecture requires structured, hash-addressable, linkable evidence.

### 3.5 EXPERIMENT REPRODUCIBILITY

```
ExperimentRun
├── experiment_id
├── hypothesis_id
├── strategy_version
├── dataset_version
├── feature_version
├── model_version
├── configuration
├── random_seed
├── environment
├── start_time / end_time
├── outputs
└── result
```

The prototype has no experiment tracking. A backtest run is not reproducible
because there's no dataset version, no feature version, no random seed.

### 3.6 FEATURE REGISTRY

```
Raw Data → Feature Definition → Computation → Validation → Feature Version
```

A strategy references a feature VERSION, not an ambiguous feature name. This
prevents silent feature drift beneath a backtest.

### 3.7 MODEL REGISTRY

```
Model Definition → Training → Artifact → Evaluation → Version → Promotion
```

The prototype has no models at all. The original architecture plans for them.

### 3.8 DECISION RECEIPTS

```
DecisionReceipt
├── decision_id
├── actor
├── object
├── requested_action
├── policy_version
├── input_hash
├── decision (ALLOW/DENY/REQUIRE_APPROVAL)
├── reason
├── timestamp
└── related_evidence[]
```

Every consequential decision generates one. This is the bridge between WHAT
AIOS did and WHY.

### 3.9 CAPABILITY ROUTER

```
AIOS.backtest() → Capability Interface → Implementation A | B | Future
```

The architecture owns the capability. The OSS technology is an implementation
behind it. This is what prevents lock-in — not just ABC adapters (which we
have) but a formal capability registry with version routing.

### 3.10 EVENT-DRIVEN ARCHITECTURE (typed)

```
HypothesisCreated, HypothesisRejected, DatasetVersionCreated,
ExperimentStarted, ExperimentCompleted, EvaluationCompleted,
RiskDecisionMade, PromotionApproved, PromotionDenied,
OrderRequested, OrderAuthorized, OrderDenied,
ExecutionCompleted, PostMortemCreated, RollbackTriggered
```

The prototype has trading events (data_acquired, order_filled). The original
architecture has PLATFORM events (hypothesis lifecycle, experiment lifecycle,
promotion lifecycle) that enable the control plane to orchestrate.

---

## 4. WHAT NEEDS REDESIGNING (exists but wrong shape)

| Prototype component | Problem | Original architecture shape |
|---|---|---|
| Communities C1-C11 | Organized by workflow stage, not platform plane | Services within planes |
| InMemoryEventBus | No durability, no typed platform events | Event bus with typed events + multiple consumer types |
| SQLite | Single file, no concurrency | PostgreSQL for transactional state + object storage for artifacts |
| Vanilla JS UI | No framework, no routing, no state management | Professional frontend (framework TBD) |
| Monolithic runner | Everything in one asyncio loop | Separate services per plane |
| CandidateHypothesis (payload) | Transient, not persistent | Persistent Hypothesis object in DB |
| VerificationReport (payload) | Transient | Persistent Evaluation Record |
| RiskFirewall (class) | Embedded in runner | Deterministic Authority Plane (independent service) |

---

## 5. MIGRATION STRATEGY

### Phase A: Build the AIOS Kernel (the operating system)
- Identity Model (actor types: human/agent/service/workflow)
- Capability Model + Contract Registry
- State Machine Engine (formal transitions with receipts)
- Authority Gateway (the only path to state mutation)
- Decision Receipt Engine
- Provenance Model (lineage graph)
- Promotion + Rollback Controllers
- Plugin/Adapter Registry

### Phase B: Data Architecture
- Migrate SQLite → PostgreSQL (transactional state)
- Dataset Registry (versioned, hashed, reproducible)
- Feature Registry (versioned features)
- Model Registry (versioned models)
- Experiment Registry (reproducible runs)

### Phase C: Research Plane
- Research Workspace (bounded context per problem)
- Hypothesis Engine (first-class hypothesis objects)
- Evidence Architecture (structured evidence packages)
- Knowledge Graph (hypothesis relationships)

### Phase D: Re-house Existing Logic
- Move C1-C11 logic into the appropriate planes
- Wire everything through the kernel (no direct state mutation)
- Replace direct event bus calls with typed platform events
- Every decision generates a receipt

### Phase E: Experience Plane
- Rebuild UI on the new API
- All existing UI concepts preserved (command center, decisions, risk, etc.)
- New: research workspace, hypothesis graph, experiment tracking

---

## 6. THE HONEST TRUTH

The prototype is ~15% of the original architecture.

What it got right: the trading logic loop, the honesty invariants, the
deterministic risk authority, the audit concept.

What it missed: everything that makes it an OPERATING SYSTEM rather than a
TRADING BOT. The kernel, the state machine, the capability router, the
promotion controller, the provenance graph, the experiment registry, the
feature registry, the model registry, the decision receipts, the identity
model, the policy engine.

These are not features. They are the platform itself.

---

## 7. THE PATH FORWARD

The prototype is not wasted. It proved:
1. The trading logic loop works
2. The honesty invariants are enforceable
3. The risk governance is effective
4. The command center concept is viable

The original architecture requires:
1. A new AIOS kernel (the OS primitives)
2. PostgreSQL + proper data architecture
3. A frontend framework
4. Multi-process/multi-service deployment
5. Formal state machines for all object lifecycles

**Recommended approach:** Build the AIOS kernel first. It is small, it is
the foundation, and everything else attaches to it. The prototype's trading
logic then becomes services that register with the kernel.
