# AIOS-0X Plane Manifest

The authoritative module → architectural-plane mapping (original architecture
§3, gap analysis §1). `tests/test_architecture_boundaries.py` enforces the
invariants listed at the bottom — the planes are not documentation; they are
machine-checked.

Judgment calls are documented inline where a module spans planes.

## Experience Plane — zero authority, cannot bypass the control plane
| Module | Notes |
|---|---|
| `ui/index.html` | command-center SPA |
| `api/server.py`, `api/views.py` | read-only views over live state |
| `aios/cli.py` | operator entrypoint (`boot/replay/serve/events/tail`) |

## Control Plane — ALL lifecycle authority
| Module | Notes |
|---|---|
| `kernel/identity.py` | WHO may act |
| `kernel/capability.py` | WHAT may be requested |
| `kernel/state_machine.py` | formal lifecycles + recovery API |
| `kernel/authority.py` | the ONLY mutation path (fail closed) |
| `kernel/receipts.py` | every decision leaves a receipt |
| `kernel/promotion.py` | §21/§22 promotion + rollback controllers |
| `core/control_plane.py` | audited operator console (RBAC) |
| `core/security.py`, `core/agents.py` | ACL primitives + agent roster |
| `core/challenger.py` | human-gated trials |

## Intelligence Plane — proposals only, never direct mutation
| Module | Notes |
|---|---|
| `communities/c2_research/*` | research/debate agents |
| `communities/c3_verification/*` | numeric hallucination critic |
| `communities/c4_strategy/*` | strategy families incl. `ml_family.py` |
| `communities/c8_evolution/*` | reflection/reflection triggers |
| `communities/c10_world/*` | regime/scenario/expectation models |
| `communities/c9_portfolio/portfolio.py` | allocation PROPOSALS (the gate is authority) |
| `communities/c6_observation/*` | post-mortem agent (§3C lists it under Intelligence runtime) |
| `communities/c7_memory/*` | memory-retrieval agent (§3C); its STORAGE lives in Data & State |
| `research/model_lab.py`, `research/auto_research.py` | model training + hypothesis synthesis |

## Research Plane — durable knowledge
| Module | Notes |
|---|---|
| `research/engine.py` | hypothesis engine (+ boot-time kernel restore) |
| `core/research_store.py` | hypotheses/evidence/knowledge-graph storage |
| `schemas/contracts.py` | Hypothesis / EvidencePackage / EvaluationRecord live here with all other contracts |

## Execution Plane — post-authorization order handling
| Module | Notes |
|---|---|
| `simulation/paper_engine.py` | venue simulation |
| `communities/c5_execution/*` | order lifecycle + adapters |
| `research/walkforward.py`, `research/integrity.py`, `research/disaster.py` | honest backtest harnesses |
| `simulation/generate_golden_data.py` | deterministic datasets |

## Deterministic Authority Plane — ALLOW/DENY/REQUIRE_APPROVAL, fail closed
| Module | Notes |
|---|---|
| `core/risk_firewall.py` | hard pre-trade limits |
| `core/risk_governor.py` | emergency machine + persisted lockout |

## Data & State Plane — persistence + lineage
| Module | Notes |
|---|---|
| `core/persistence.py`, `core/pg_store.py`, `core/store_factory.py` | hash-chained memory store (SQLite/PG) |
| `communities/c1_data/*` | ingestion/normalization/validation (§10 data architecture pipeline) |
| `core/event_recovery.py` | §26 durable replay read-side |
| `kernel/registries.py`, `kernel/provenance.py` | versioned artifacts + lineage graph |
| `core/research_store.py` | research knowledge tables |
| `kernel/memory_log.py`, `kernel/vector_memory.py`, `core/data_quality.py` | trading memory tiers |
| `communities/c11_finance/*` | double-entry books + tax/CA records (state); compliance surveillance ENFORCES authority rules but writes alerts as data |

## Infrastructure Plane — transport + runtime services
| Module | Notes |
|---|---|
| `core/event_bus.py` | in-memory bus + scoped zero-trust views (§24) |
| `core/config.py` | settings (env-only secrets) |
| `core/notifications.py` | telegram hub |
| `core/model_gateway.py`, `core/model_router.py`, `core/prompts.py` | LLM plumbing (deterministic when absent) |

## Composition Roots — allowed to touch everything, touch nothing else's job
`simulation/replay_runner.py`, `simulation/kernel_bridge.py`,
`aios/cli.py` (boot path), `tests/*`.

## Enforced invariants (`tests/test_architecture_boundaries.py`)
1. **No business logic touches the OS directly**: nothing under `communities/`
   imports `kernel.*`. Mutation flows only through composition roots.
2. **No cross-community imports**: communities communicate exclusively via
   schema contracts and bus topics.
3. **Experience Plane is read-only**: `api/` never appends events or writes
   typed stores.
4. **No private-state access outside the kernel/composition roots**: patterns
   like `_objects[`, `_receipts[`, `_versions[` are forbidden outside their
   owning modules. Recovery uses public APIs (`restore_object`).
