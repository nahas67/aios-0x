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
| `communities/c10_world/*` | regime/scenario/expectation models, incl. `change_detection.py` (CUSUM + Bai-Perron with provenance) and `RegimeFeed` (live available_at-stamped features) |
| `communities/c9_portfolio/portfolio.py` | allocation PROPOSALS (the gate is authority) |
| `communities/c9_portfolio/optimizer.py` | two optimizers (inverse-vol + HRP) → proposal or disagreement finding; output cannot be submitted anywhere |
| `communities/c6_observation/*` | post-mortem agent (§3C lists it under Intelligence runtime) |
| `communities/c7_memory/*` | memory-retrieval agent (§3C); its STORAGE lives in Data & State |
| `research/model_lab.py`, `research/auto_research.py` | model training + hypothesis synthesis |
| `research/reporting.py`, `evaluation/harness.py` | declared-number reports (undeclared cut); deterministic seeded evaluation with Wilson intervals behind the claim gate |

## Research Plane — durable knowledge
| Module | Notes |
|---|---|
| `research/engine.py` | hypothesis engine (+ boot-time kernel restore) |
| `core/research_store.py` | hypotheses/evidence/knowledge-graph storage |
| `schemas/contracts.py` | Hypothesis / EvidencePackage / EvaluationRecord live here with all other contracts |
| `schemas/governance.py` | tool-call wire types: `ToolCall`, `GuardianDecision`, `ToolGuard` |

### Why the governance contract is not in the kernel

`kernel/tool_governance.py` holds the `ToolGuardian` implementation, but the
types a community needs — and the `ToolGuard` interface it depends on — live in
`schemas/governance.py`.

Community 5 routes every venue call through a guard. The direct implementation
imports `kernel.tool_governance`, which invariant 1 forbids. The two easy
responses are both wrong: dropping the guard leaves the execution path
unguarded, and relaxing the boundary makes this manifest advisory. Splitting
the contract from the implementation means a community depends only on the
interface, a composition root injects the guard, and both rules hold.

The same shape applies to any future control-plane dependency a community must
reach.

## Execution Plane — post-authorization order handling
| Module | Notes |
|---|---|
| `simulation/paper_engine.py` | venue simulation |
| `communities/c5_execution/*` | order lifecycle + adapters; `oms.py` (durable write-ahead orders), `reconciliation.py` (broker-vs-internal workflow) |
| `research/walkforward.py`, `research/integrity.py`, `research/disaster.py` | honest backtest harnesses |
| `simulation/generate_golden_data.py` | deterministic datasets |

## Deterministic Authority Plane — ALLOW/DENY/REQUIRE_APPROVAL, fail closed
| Module | Notes |
|---|---|
| `core/risk_firewall.py` | hard pre-trade limits |
| `core/risk_governor.py` | emergency machine + persisted lockout |
| `kernel/strategy_registry.py` | **certification firewall**: no sign-off without a measured verdict; validator ≠ approver; a verdict is what a playbook binds to |
| `kernel/playbook.py` | **certified policy selection**: a fast tier may select among certified playbooks and has no mutation method at all; abstention is a first-class outcome. Position sizes are *derived* (`derive_action` → `SizingBasis`, recomputable via `verify()`), never supplied; `CERTIFIED_WITH_LIMITS` cannot produce a position. Durability via module-level `persist_router`/`load_router` so the router surface stays pinned; `propose_candidates` sweeps regimes into sizes or named refusals |
| `core/backtest.py` | measured backtest primitives incl. `regime_sharpes`: per-regime net Sharpe with observation counts, which replaced the last caller-supplied boolean in the firewall |
| `core/contamination.py` | look-ahead and survivorship *detected* from timestamps and corporate actions, so a certification check cannot be asserted |
| `core/capital_firewall.py`, `core/authorization.py` | **pre-trade boundary**: 15 named checks → APPROVE/REDUCE/REJECT; sealed HMAC envelope the execution path cannot mint; wired into OMS prepare (nothing persists on REJECT) and adapter submit (no venue contact without one) |
| `core/policy_bundles.py` | versioned signed policy data compiling onto the guardian; six-operator conjunctive match language; OPA deliberately not adopted (sidecar in the deterministic path, against dependency policy) |
| `core/conformal.py`, `core/decision_gate.py` | split-conformal intervals with finite-sample correction; TRADE/WAIT/ESCALATE/ABSTAIN gate in fail-closed order, ABSTAIN first-class |
| `core/trace.py` | eleven canonical stages, one correlation id threaded plan→outbox→governed call; gaps reported, never filled |

## Data & State Plane — persistence + lineage
| Module | Notes |
|---|---|
| `core/persistence.py`, `core/pg_store.py`, `core/store_factory.py` | hash-chained memory store (SQLite/PG) |
| `core/financial_kernel.py` | **deterministic financial state** (ADR-005): durable orders/transitions/fills/cash postings/positions, transactional outbox, consumer inbox, reconciliation records, `verify_invariants()` |
| `core/ibor.py` | **Investment Book of Record** (ADR-006): the single source of portfolio truth |
| `communities/c1_data/*` | ingestion/normalization/validation (§10 data architecture pipeline) |
| `core/event_recovery.py` | §26 durable replay read-side |
| `kernel/registries.py`, `kernel/provenance.py` | versioned artifacts + lineage graph |
| `core/research_store.py` | research knowledge tables |
| `core/decision_sink.py` | **durable append-only governance ledger**; append-only is enforced by database triggers, and a hash chain alone cannot detect truncation so the head is anchored by an HMAC seal |
| `core/experiment_sink.py` | **durable append-only experiment ledger**; one event per transition carrying the full run snapshot (current state = latest event per experiment), per-experiment `supersedes` linkage instead of a global chain, seal over `(count, head)` — the truncation prize here is a manufactured track record |
| `core/dataset_version_sink.py` | durable dataset versions, same event-log shape (migration v7); `scripts/backfill_available_at.py` assigns knowability (published preferred, occurrence flagged fallback, witness-less stays unknown), dry-run by default |
| `core/claim_ledger.py`, `core/claim_writers.py` | content-addressed sources verified on read, claims appended only against stored artifacts, replays as idempotent no-ops; verification reports and research evidence flow through writers (migration v6) |
| `core/playbook_store.py` | durable immutable policies, rewrite-under-version refused, seal over (count, set-hash) so same-count substitution fails (migration v8) |
| `core/seed_ingest.py`, `data/seed/bootstrap_v1.json` | versioned-bundle importer: models validate before first write, identities upsert, actions immutable |
| `core/feature_store.py` | one shared transform for offline batch and online serving; parity as a checked claim with its own epsilon; warmup refuses, gaps poison, code-hash pinned |
| `core/challenger.py` | champion-vs-challenger trials; promotion needs EVALUATED + PASS + identified human, no overrule, no repeats |
| `core/security_master.py`, `core/security_master_store.py` | bitemporal instrument identity (migration v3) — "what is this symbol" with an `as_of` |
| `core/temporal.py` | six clocks + the look-ahead tripwire; `available_at` is the join key, not a feature's own timestamp |
| `kernel/memory_log.py`, `kernel/vector_memory.py`, `core/data_quality.py` | trading memory tiers |
| `communities/c11_finance/*` | double-entry books + tax/CA records (state); compliance surveillance ENFORCES authority rules but writes alerts as data |

### Why `DecisionSink` sits in `schemas/`, and the oracle in `kernel/`

Two small contracts, both placed so that neither side has to import the other.

`DecisionSink` lives beside `ToolGuard` in `schemas/governance.py` because
`kernel/tool_governance.py` depends on it and `core/decision_sink.py` satisfies
it. Its central guarantee is carried by the *absence* of methods: there is no
`update` and no `delete`, so no caller can reach for one. `core/decision_sink.py`
adds the SQLite implementation and the seal, and imports only the schema.

`RegistryCertificationOracle` lives in `kernel/bootstrap.py` and is a separate
type rather than a `StrategyRegistry` handed to `PlaybookRouter`. The router's
question is narrower — *may this be traded right now* — and passing the whole
registry would put `approve`, `reject`, and `record_verdict` on the fast tier's
own collaborator. Narrowing the surface is the control; a thin adapter is the
cheapest way to keep the authority one refactor away from unreachable.

## Infrastructure Plane — transport + runtime services
| Module | Notes |
|---|---|
| `core/event_bus.py` | in-memory bus + scoped zero-trust views (§24) |
| `core/config.py` | settings (env-only secrets) |
| `core/notifications.py` | telegram hub |
| `core/model_gateway.py`, `core/model_router.py`, `core/prompts.py` | LLM plumbing (deterministic when absent) |

## Composition Roots — allowed to touch everything, touch nothing else's job
`kernel/bootstrap.py` (`create_kernel` → `AIOSKernel`: the one place
`StrategyRegistry`, `RegistryCertificationOracle`, and `PlaybookRouter` are
connected, so a playbook can only ever be published against a verdict this
kernel holds), `simulation/replay_runner.py`, `simulation/kernel_bridge.py`,
`aios/cli.py` (boot path), `tests/*`.

## Authority notes introduced by the financial kernel
- The financial store is **mutation authority** for orders/fills/cash; agents never
  write to it directly. Communities reach it through composition roots, exactly
  like the kernel (invariant 1 below).
- `core/ibor.py` and `core/financial_kernel.py` are AIOS-owned authoritative
  components (spec §58) — third-party engines may adapt to them, never replace
  them as the source of financial truth.

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
