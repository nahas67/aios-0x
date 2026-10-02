# AIOS-0X — Architecture Mapping

**What this file is.** The reconciliation between `ARCHITECTURE.txt` (§13 implementation
order) and `docs/goals/goals.json` (the status registry). It exists so a reader can check
one against the other without trusting either.

**Why it exists.** `docs/goals/CHECKPOINT.md` describes the program as "derived from
`ARCHITECTURE.txt`" — true of the layers, but it says nothing about the goal IDs, and the
two number differently. An independent audit found the claim unverifiable from the
repository, because `ARCHITECTURE.txt` **is not in the repository and is not
version-controlled**. This file is the written-down comparison that was missing.

**Sources.**

| Source | Role | Location |
|---|---|---|
| `ARCHITECTURE.txt` | layer and goal *naming* | **outside the repo**, unversioned, 1,903 lines |
| `docs/goals/goals.json` | goal *status* — authoritative | in-repo, 25 goals |
| `ARCHITECTURE_PLANES.md` | module → plane | in-repo, 8 planes |

---

## 1. The finding that matters

**`G010`–`G110` align exactly. From `G120` the registry is a traceable, more granular
refinement of §13** — it merges goals §13 lists separately, splits one, and inserts one
§13 never names. The offset grows by exactly one per insertion, which is what a deliberate
decomposition looks like rather than drift.

Two structural differences, both of them **the registry being better than §13**:

1. **§13 has no place for §3's six cross-cutting control planes.** It sequences the 25
   *layers* and stops. Governance, Model Governance, Observability, Security, Assurance and
   Supply Chain are declared in §3 and never sequenced. The registry gave them goals.
2. **§11's Statistical Claim Gate is never sequenced either**, yet it is one of the
   strictest requirements in the document. The registry made it `G190`.

So: **do not renumber.** Renumbering shipped goals would destroy traceability to buy a
cosmetic alignment, and would move *away* from §13 on the two points where the registry
improved on it.

---

## 2. §13 → registry, goal by goal

| §13 | §13 name | registry | registry name | relationship |
|---|---|---|---|---|
| G010 | Financial Truth | `G010` | Financial Truth | 1:1 |
| G020 | Security Master / Corporate Actions | `G020` | Security Master and Corporate Action Engine | 1:1 |
| G030 | PIT Data Fabric | `G030` | Point-in-Time Data Fabric | 1:1 |
| G040 | Evidence + Lineage | `G040` | Evidence Fabric and Claim Ledger | 1:1 |
| G050 | Agent Governance | `G050` | Agent Governance and Tool-Call Enforcement | 1:1 widened |
| G060 | Quant Factory | `G060` | Quant Research Factory | 1:1 |
| G070 | Experiment Ledger | `G070` | Immutable Experiment Ledger | 1:1 |
| G080 | Certification Firewall | `G080` | Strategy Certification Firewall | 1:1 |
| G090 | Feature Fabric | `G090` | Feature Fabric with Offline and Online Parity | 1:1 |
| G100 | Regime | `G100` | Regime Intelligence | 1:1 |
| G110 | Calibration / ABSTAIN | `G110` | Calibration and Selective Decision | 1:1 |
| G120 | Fast + Deep Intelligence | `G120` | Dual-Speed Intelligence **and** Certified Playbook Engine | **merged with §13 G130** |
| G130 | Certified Playbooks | `G120` | — | merged upward |
| G140 | Portfolio Brain | `G130` | Robust Portfolio Brain | renumbered −1 |
| G150 | Capital Firewall | `G140` | Deterministic Capital Firewall and Authorization Envelope | renumbered −1, widened |
| G160 | Execution Twin / OMS | `G150` + `G160` | Execution Kernel and Order Management · Execution Digital Twin | **split in two** |
| G170 | OMS | `G150` | — | merged into `G150` |
| G180 | Reconciliation | `G170` | Broker Reconciliation | renumbered −1 |
| G190 | Memory | `G180` | Institutional Memory, Governed Learning, and Counterfactuals | **merged with §13 G200, G210** |
| G200 | Learning | `G180` | — | merged upward |
| G210 | Counterfactuals | `G180` | — | merged upward |
| — | *(not in §13)* | `G190` | Statistical Claim Gate and Evaluation Harness | **INSERTED** — carries §11 |
| G220 | Champion/Challenger | `G200` | Champion and Challenger Arena | renumbered −2 |
| G230 | Observability | `G210` | Observability and Trace Continuity | renumbered −2, carries §3C |
| G240 | Formal Assurance | `G220` | Formal Assurance | renumbered −2, carries §3E |
| G250 | Supply Chain | `G230` (part) | Governance, Security, and Supply-Chain Planes | **merged with §3 A, D, F** |
| G260 | Disaster Recovery | — | — | **not carried** — see §4 below |
| G270 | Long SHADOW | `G240` | Long Shadow Validation | renumbered −3 |
| G280 | Canary Capital | `G250` | Canary Capital | renumbered −3 |

**Totals, checked.** §13 has **28** goals; the registry has **25**; delta **−3**. The
composition is: **2 merges** (`G120`+`G130`; and `G190`+`G200`+`G210` → `G180`), **1
re-pairing** (`G160`+`G170` → `G150`+`G160`, two goals to two), **1 insertion**
(registry `G190`), **1 not carried** (`G260`). That is `28 + 1 − 1 − 1 − 2 = 25`.

> A first draft of this line said "4 merges, 1 split", which does not reconcile to 25.
> The table above was right and the summary of it was wrong — worth recording because an
> unchecked total is the one part of a mapping table a reader is most likely to quote.

---

## 3. §3's control planes

§3 declares six. §13 sequences none of them.

| §3 | Plane | Carried by | State |
|---|---|---|---|
| A | Governance | `G050` + `G230` | LANDED (policy bundles replaced OPA/Rego) |
| B | **Model Governance** (MLflow: models, versions, prompts, runs, evals, datasets, features, champion/challenger, deployment, rollback) | **no goal of its own** | **GAP — see §6** |
| C | Observability (OpenTelemetry; *"Why did this trade happen?"*) | `G210` | LANDED |
| D | Security (sandboxed AI zones, OpenBao) | `G230` | **PARTIAL** — zones and OpenBao have no implementation; §3D is a requirement the tree does not meet |
| E | Assurance (TLA+) | `G220` | LANDED — 4 of §3E's 8 targets |
| F | Supply-Chain (SBOM, Syft, Trivy, Cosign, secret + license scan) | `G230` | **PARTIAL** — SBOM and secret hygiene shipped; scanner absent; signing is CI-only, therefore unverified |

---

## 4. Disaster Recovery: correcting the record

`docs/goals/CHECKPOINT.md` states DR "appears exactly once in the document, as a bare
label" and that `RPO`, `RTO`, `backup`, `restore` and `point-in-time recovery` have **zero
occurrences**.

**The evidence claim is correct.** Verified with word boundaries: `RPO` and `RTO` appear
**zero** times, as do `backup`, `restore` and `point-in-time recovery`. A naive
case-insensitive `Select-String` reports 5 `RPO` hits — all of them the substring in
`CO·RPO·RATE`, plus `BrokerPositionSnapshot` — and 1 `RTO` hit, which is `edgar·tRTO·ols`.
That is the same false-positive shape as defect #39's registry rule and the `SSE` NIT: a
substring is not a concept.

**The conclusion needs restating, though, and it is a real correction.** §13 line 1839 does
name Disaster Recovery, as goal `G260`. So DR is not an unmentioned stray — it is **a goal
in the architecture's own implementation order with zero acceptance criteria anywhere in the
document.** Those are different facts:

- *"not owed"* — wrong. §13 asks for it.
- **"named but unspecified"** — correct, and the reason it is not built is that building it
  would mean inventing RPO targets, retention windows and restore procedures, which §14's
  freeze rule exists to prevent.

`CHECKPOINT.md`'s DR paragraph should be amended to say this, and to cite §13 as the place
the name appears. The conclusion (do not build) is unchanged; the reasoning was incomplete.

---

## 5. §8's human control plane: 2 of 8 work, 2 partial, 4 absent

§8 names eight emergency commands and says they *"must be deterministic, must bypass AI,
must be audited, must survive model/runtime failure."* Checked against the tree:

| §8 command | Counterpart in the tree | |
|---|---|---|
| `STOP` | `ControlAction.PAUSE_TRADING`; `TRIGGER_KILL_SWITCH` | covered, named differently |
| `NO_NEW_RISK` | `RiskGovernor` escalation to `EMERGENCY_HALT`; reconciliation severity | covered as a *state* |
| `REDUCE_ONLY` | `ControlAction.SET_REDUCE_ONLY` → `classify_plan` | **partial** — see below |
| `LIQUIDATE` | the flatten loop in `_do_trigger_kill_switch` | covered, named differently |
| `DISABLE_STRATEGY` | — | **absent** |
| `DISABLE_MODEL` | — | **absent** (`PROMOTE_MODEL` exists; disabling does not) |
| `DISABLE_PROVIDER` | — | **absent** |
| `DISABLE_BROKER` | — | **absent** |

**Four of eight are absent, and they are one coherent family.** §8 asks for
*component-level* containment — stop this strategy, this model, this provider, this broker
— and the tree has a *global* containment: one kill switch that flattens every position at
an adverse price and halts.

`REDUCE_ONLY` used to belong to this family: de-risking without flattening had no
counterpart, so the only available response to deteriorating conditions was to go flat. It
now exists — `ControlAction.SET_REDUCE_ONLY`, RISK_ADMIN, audited, and enforced in
`classify_plan` — and is recorded as **partial rather than covered**, because of what the
enforcement point can see:

- **Enforced:** any plan whose *direction* increases exposure in its symbol is refused,
  including every order against a flat book; reductions and closes are permitted.
- **Not enforced:** overshoot. One oversized `SELL` against a long can still cross zero
  and open a short while nominally "reducing". Catching that needs an absolute order
  quantity, and `classify_plan` has only `position_size_pct` — a share of portfolio risk,
  which is not comparable to a venue quantity without a portfolio value that path does not
  hold. The quantity-aware half of the rule is written and unit-tested
  (`core/reduce_only.py::would_increase_exposure`) and wired to no gate.

Marking it covered would put a green tick beside a control that does not do everything its
name implies, which is the misrepresentation this document exists to prevent.

The four `DISABLE_*` commands remain a **safety** gap, not a completeness gap. They are
specified in **`docs/adrs/ADR-007_component_containment_disable_commands.md`** (PROPOSED,
awaiting human principal approval per `CONSTITUTION.md` §4.2). That ADR records three
findings that shape the work more than the command names do:

- **`DISABLE_PROVIDER` presupposes a topology the tree does not have.** The gateway is
  *provider-agnostic but single-provider* — one instance per composition root. "Disable the
  provider" is global containment wearing a component-level name.
- **`ModelStatus.DEPRECATED` is declared and never read.** So `DISABLE_MODEL` is cheaper
  than it looks (make `DEPRECATED` mean something), and in the meantime the registry can
  record a lifecycle decision that nothing acts on — the same shape as `backtest.py`'s
  original booleans.
- **A halt-vs-degrade question governs all four.** `model_gateway.py:4` documents that on
  unavailability callers "fall back to deterministic mode", while `CONSTITUTION.md` §3.2
  says missing data means "NO TRADE / UNKNOWN - never a default value". Implementing
  `DISABLE_MODEL` or `DISABLE_PROVIDER` by making a component unavailable would therefore
  **keep trading**, not halt — the opposite of what an operator expects. That question is
  answerable only once, for all four.

**Not built here, and not proposed as a small task.**

> §4's amendment procedure was re-read while building `REDUCE_ONLY` and an earlier version
> of this document over-applied it. §4 governs amendments *to the constitution itself* —
> draft ADR, human principal approves, recompute the pinned SHA-256. Adding a control action
> does not amend §1, §2 or §3, so no constitution change was required. The binding
> constraint was §2.2 (kill sequence cancel→flatten→`EMERGENCY_HALT`), and
> `set_reduce_only` deliberately does not touch that path: it cancels nothing, flattens
> nothing, and cannot lift a drawdown halt.

> Two rows here were nearly recorded as absent on the strength of a name search.
> `LIQUIDATE` has no occurrence anywhere in the tree, and it is covered anyway — the
> capability is `_do_trigger_kill_switch`'s flatten loop, found by searching for what it
> *does* rather than what it is called. Same shape as the `RPO` / `CO·RPO·RATE` false
> positive in §4 below, and the reason this table names the counterpart instead of only
> the verdict.

---

## 6. The Model Governance gap

§3B asks for MLflow-equivalent tracking of **models, model versions, prompts, training
runs, evaluations, datasets, features, champion/challenger, deployment, and rollback.**
`ARCHITECTURE.txt` mentions MLflow twice, `model version` twice, `prompt` once and
`rollback` once — so the requirement is stated, not invented.

No registry goal carries it. `G060` builds models; `G200` runs the arena; `G210` traces
inference. **What has no home is lifecycle tracking of a model or a *prompt* after it
leaves the factory** — version, evaluation record, deployment, rollback.

This is a genuine gap, found by the mapping rather than asserted. It is **not** proposed
for immediate work: it needs a decision, because §4 names MLflow as core infrastructure
while `docs/DEPENDENCY_POLICY.md` admits exactly three runtime dependencies (pydantic,
pydantic-settings, httpx) and §14 requires an ADR for anything more. That conflict is
unresolved and is recorded here rather than quietly settled in either direction.

---

## 7. The live-data path: the plan's premise was wrong

The approved plan's P6 was "SSE adoption beyond SystemHealth · gate: no polling left
where a stream exists", justified by "only `SystemHealthWorkspace` reads the live
stream; the other 16 poll."

**The second clause is false, and the difference is not cosmetic.** Nothing in the
console polls.

There are exactly three timers in the whole frontend, and each is doing something other
than polling. (The count is three *calls*: a plain `setInterval` search returns four,
because `api/stream.ts:40` mentions the name in a `ReturnType<typeof …>` annotation. A
name search is not a capability search, and this file records the distinction so the next
reader does not have to rediscover it.)

| Timer | What it does | Polling? |
|---|---|---|
| `api/stream.ts:68` | SSE heartbeat | no — keeps an open stream alive |
| `hooks/useLiveExecutive.ts:123` | refetch, gated by `shouldPoll(status)` | only while the stream is **not** live |
| `components/TopSystemBar.tsx:55` | UTC clock string | no — touches no data |

`hooks/useApi.ts` is the single fetch hook and it has no timer at all: it loads on mount
and again when its `deps` change, plus an explicit `refresh()`.

So the gate is satisfied vacuously — there is no polling to remove. Reporting it as
"adoption completed" would credit the plan with a fix it did not make.

### The actual deficiency, which is larger and different

`useLiveExecutive` is stream-first with a deliberate poll fallback, which is the right
design. The problem is upstream of it: **the stream carries almost nothing.**

`api/server.py:350` publishes exactly two things every 2 seconds:

```python
payload = {
    "ts": time.time(),
    "executive": builder.executive(),
    "platform_tail": builder.platform_feed(limit=10),
}
```

The frontend reads roughly thirty endpoints (`positions`, `orders`, `executions`,
`equity`, `agents`, `alerts`, `audit`, `models`, `accounting`, `graduation`, …). Two of
them have a live path. The other seventeen fetch once and stay static until something
changes a dep — so their figures are silently as-of-load with no indication on screen.

A richer event bus already exists internally (`core/event_bus.py`, topic-scoped
`subscribe`) and is not exposed over SSE.

### What was done about it

The consumer side, because the fix belongs there. A frame arriving is already a
sufficient signal that something moved, so the SSE **payload was not changed** — that
would put more work on a two-second hot loop for every client, including ones that want
one resource, and it is a contract change.

`useStreamRefresh` (opt-in) plus a pure, unit-tested decider in
`frontend/src/lib/streamRefresh.ts` advance a counter when a frame has arrived since the
last refetch **and** a floor has elapsed. Pass it into `useApi`'s deps:

```tsx
const tick = useStreamRefresh();
const q = useApi(() => riskApi.risk(), [tick]);
```

Both conditions are required. Without the interval, sixteen workspaces on a two-second
cadence is roughly eight requests a second against an API whose `/financial/*` routes hit
SQLite with `synchronous = FULL` — trading a staleness bug for a self-inflicted load
problem. Without the frame check, an *idle* stream drives an unbounded refetch loop.

Adopted where the displayed figure is current state an operator acts on: risk, portfolio,
execution, the certification verdict, and live trading. Deliberately not adopted for audit
(an append-only log), research, settings, or design tokens.

Opt-in rather than built into `useApi`: it serves everything including one-shot fetches
that must not repeat, and making it self-refreshing would change every existing call site
at once, invisibly.

Ten tests, seven mutations all caught. The subtle one is the stamp: recording the *frame*
time instead of `now` lets a stale timestamp suppress a later legitimate refetch, so a
workspace silently stops updating with nothing thrown and no obvious red test.

### Still open

The stream still carries only `executive` and `platform_tail`, so this is a liveness
signal rather than a data channel — workspaces refetch to discover what changed instead of
being told. That is the right trade at sixteen workspaces, but a topic-delta design off
`core/event_bus.py` would remove the refetch entirely. That is a contract change and a
larger piece of work, not a small task.

---

## 8. An unexplained flake in the multi-process concurrency tests

Not architecture, but found while verifying the above and recorded because it is real,
rare, and currently undiagnosable.

### What is observed

Two failures, both `sqlite` tier, both in `tests/test_v1a2_concurrency.py`, both only
under load:

1. `test_two_outbox_workers_claim_disjoint_batches[sqlite]` — once, in a full-suite run.
   **The assertion is unknown**: that run used `--tb=no`, so only the test name survived.
2. `test_two_processes_cannot_overfill_one_order[sqlite]` — once, under 6 CPU spinners,
   as `AssertionError: worker failed (1)` with **empty stdout AND empty stderr**.

Different tests, same file, so the fault is not in either test's logic.

### The clue

A handled Python exception always writes a traceback to stderr. Empty stderr with a
non-zero exit is not that. A subprocess that dies silently is indistinguishable from one
that was killed, one that timed out, and one that exited through a path that prints
nothing — and `run_workers` reports all four with the same message, then lets pytest
truncate the evidence.

SQLite contention is *not* an adequate explanation: `core/financial_kernel.py:877` sets
`PRAGMA busy_timeout = 10000` with WAL, against a 120 s worker timeout.

### What was ruled out

| Attempt | Result |
|---|---|
| single test, 12 runs | 12 pass |
| whole file, 10 runs, no load | 10 pass |
| whole file under 6 then 10 CPU spinners, 24 runs | 24 pass |
| full suite, 5 runs | 5 pass |
| standalone two-process race, 8 attempts under load | 8 pass |

### Why there is no fix here

Adding diagnostics changed the timing enough to stop the fault appearing at all — a
heisenbug cannot be pinned down by making the system slower. **A speculative fix would be
worse than none**, so none was written.

What was done instead is make the next occurrence diagnosable: `run_workers` now appends
one JSON line per worker (mode, returncode, stdout/stderr length and tail) to
`$AIOS_WORKER_DIAG` when that variable is set, and does nothing when it is unset. Verified
to capture 320 records across a 14-iteration run.

```powershell
$env:AIOS_WORKER_DIAG="$env:TEMP\worker.jsonl"
python -m pytest tests/test_v1a2_concurrency.py -q
```

This is a diagnostic, not a control, and it fixes nothing. The flake remains open and
needs a capture to close.

---

## 9. §4's infrastructure and the three-dependency rule: there is no conflict

This session opened with an open question recorded as *"§4's Qdrant/MLflow vs the
three-dependency rule — unresolved, needs you."* **That framing was wrong.** It asserted a
conflict between two documents without checking either against the tree.

`ARCHITECTURE.txt` §4 opens *"Preserve the current strong AIOS foundation"* and lists six
infrastructure roles. Read against the actual dependency model:

| §4 role | In this tree | Verdict |
|---|---|---|
| PostgreSQL — financial truth | `postgres = ["psycopg[binary]>=3.3,<4"]` | correct: optional extra |
| NATS JetStream — event transport | `nats = ["nats-py>=2.15,<3"]` | correct: optional extra |
| Qdrant — semantic memory | `qdrant = ["qdrant-client>=1.19,<2"]` | correct: optional extra |
| MLflow — model/experiment governance | **not a dependency at all** | see below |
| QuestDB — hot tick data | absent | §4 itself labels it *"candidate"* |
| Iceberg — historical/PIT datasets | absent | §4 itself labels it *"candidate"* |

Two facts dissolve the apparent conflict:

1. **The two rules govern different things.** The three-dependency rule covers *required
   runtime imports*, and `pyproject.toml` says so in its own comment: *"Imported by shipped
   modules at import time, so these are not optional."* PostgreSQL, NATS and Qdrant are
   infrastructure the system **connects to**, not libraries it imports — which is exactly
   what an optional extra is for. Nothing about declaring them as extras violates a rule
   about required imports.

2. **MLflow was never a dependency here.** It appears in the tree only inside
   `AIOS_PHASE2_CANDIDATE_TECHNOLOGY_STACK.md` and
   `AIOS_PHASE2B_BENCHMARK_PROTOCOL_v0.1.md`, in both cases as the **baseline being
   evaluated against ClearML** ("Does ClearML offer materially lower… overhead than
   MLflow"). It is not installed and not imported by a single module. So there is no
   MLflow dependency to reconcile against a rule — it is an unadopted candidate, and §4's
   "preserve the current foundation" framing means an absent MLflow is not a violation.

QuestDB and Iceberg are the cleanest confirmation of the reading: §4 labels them
*"candidate"* itself, and they are correctly absent.

**Consequence:** no ADR is needed, no dependency is admitted, and the question this session
carried open is closed. The recorded lesson is the third instance of one pattern — asserting
a conflict from memory instead of reading both sides against the tree, the same shape as the
"mypy is broken" claim in this session's verification notes. Both were checked in minutes
once actually looked at.

---

## 10. Verification

How to re-check every claim above:

| Claim | Command |
|---|---|
| registry titles and count | `python -c "import json;d=json.load(open('docs/goals/goals.json'));print([(g['id'],g['title']) for g in d['goals']])"` |
| §13 goal list | read `ARCHITECTURE.txt` §13, lines 1754–1852 |
| DR evidence, correctly | `Select-String -Path ..\ARCHITECTURE.txt -Pattern '\bRPO\b\|\bRTO\b'` → expect no matches |
| control-plane state | read `goals.json` entries `G050`, `G210`, `G220`, `G230` |
| §8 command names, verbatim | `Select-String ..\ARCHITECTURE.txt` for each of the eight names, anchored — 8 matches |
| §8 coverage: 2 full, 2 partial, 4 none | `core/control_plane.py` `ControlAction` (19 actions) and `_do_trigger_kill_switch`; `core/reduce_only.py` for REDUCE_ONLY; `frontend/src/lib/emergencyCommands.ts` is the tested source of these counts |
| §4's four infrastructure roles are all optional extras, and MLflow is not a dependency | read `pyproject.toml` `[project.optional-dependencies]` for `postgres`/`nats`/`qdrant`; `rg -n mlflow` finds only the two candidate-technology docs |
| §4 labels QuestDB and Iceberg as candidates | read `ARCHITECTURE.txt` §4, lines 1323–1365 |
| `ModelStatus.DEPRECATED` is declared but never read | `rg -n DEPRECATED` → `kernel/registries.py:317` (ModelStatus) and line 42 (a different enum's member); no consumer of the model's own value |
| only 3 timers exist, none polling | `rg -n "setInterval\s*\(" frontend/src` → expect exactly 3 hits: `api/stream.ts:68`, `hooks/useLiveExecutive.ts:123`, `components/TopSystemBar.tsx:55`. **Not** `rg -n "setInterval"`, which returns 4 — the extra hit is `api/stream.ts:40`, a `ReturnType<typeof setInterval>` type annotation, not a timer |
| `useApi` never polls | read `frontend/src/hooks/useApi.ts` — no timer; loads on mount and on `deps` |
| stream payload is 2 keys | read `api/server.py:350` — `executive` and `platform_tail` only |
| stream-driven refetch is coalesced | `frontend/src/lib/streamRefresh.ts`; 10 tests, 7 mutations caught |
| which workspaces subscribe | `rg -n "useStreamRefresh" frontend/src/components/views` — risk, portfolio, execution, certification, live trading |
| §2's 25 layers, and which have a screen | `frontend/src/lib/architectureLayers.ts`; gate is `architectureLayers.test.ts` (29 tests, 13 mutations caught) |
| operator surface shares no runtime | `python scripts/verify_operator_isolation.py` — reads sourcemaps, not comments |

**Not verifiable in-repo:** `ARCHITECTURE.txt` itself. That is the finding this file exists
to make visible, and the reason the first row of the table above is worth reading twice.
