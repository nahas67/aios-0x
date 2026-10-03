# AIOS-0X — Current Architecture (as built)

**What this is.** `ARCHITECTURE.txt` is the frozen *target*: 1,903 lines, outside this repo,
unversioned, and never reconciled against the code. This document is the *as-built* view —
what exists today, and where it diverges from that target.

**What it is not.** Not a design doc, and not a restatement of the target. Where the two
disagree, the disagreement is the content.

**How to check any claim.** Every claim below names the file that backs it. Commands are
at the end; each was executed against the tree when this was written, not carried on trust.

**Status:** current as of 2026-10-02 · `HEAD 5f32d30` · 1762 backend tests / 139 frontend,
0 failing.

---

## 1. The two surfaces

The single most consequential structural fact. There is not one console; there are two,
and they are separate builds because §8 requires the emergency commands to *"survive
model/runtime failure"* and the analyst console opens an SSE stream and mounts sixteen
workspaces. A kill switch inside that bundle dies with whatever broke it.

| | Operator surface | Analyst console |
|---|---|---|
| Entry | `frontend/operator.html` | `frontend/index.html` |
| React root | `src/operator.tsx` | `src/main.tsx` |
| Own bundle | 10.5 KB | 413.9 KB |
| First-party modules | 7 | full graph |
| External origins | none — no font CDN, no analytics | Google Fonts |
| Renders with API down | yes (static data, no network on first paint) | n/a |

**Isolation is measured, not asserted.** `scripts/verify_operator_isolation.py` reads the
sourcemap, because the obvious check — grepping the built bundle for module names — is
worthless: Vite minifies, so `LiveTradingWorkspace` returns zero hits whether or not it is
in the graph. The forbidden set is derived from the filesystem, so a new workspace is
covered without editing the script, and a missing sourcemap is a **failure**, so "could not
check" can never look like "checked and clean".

Current result: **7 first-party modules** — `operator.tsx`, `OperatorSurface.tsx`,
`emergencyCommands.ts`, plus shared `api/client.ts`, `api/backend.ts`, `stores/identity.ts`,
`lib/control.ts`. No workspace, no hook, no chart library, no SSE client. **25 forbidden
modules checked.**

---

## 2. §8's human control plane — 3 of 8 work

Tally: **3 covered · 1 partial · 4 absent.**

| §8 command | Counterpart | State |
|---|---|---|
| `STOP` | `PAUSE_TRADING`, `TRIGGER_KILL_SWITCH` | ✅ covered |
| `NO_NEW_RISK` | `RiskGovernor` → `EMERGENCY_HALT` | 🟡 a *state*, not a command |
| `REDUCE_ONLY` | `SET_REDUCE_ONLY` → `classify_plan` | ✅ covered |
| `LIQUIDATE` | flatten loop in `_do_trigger_kill_switch` | ✅ covered |
| `DISABLE_STRATEGY` | — | ⛔ absent |
| `DISABLE_MODEL` | — | ⛔ absent |
| `DISABLE_PROVIDER` | — | ⛔ absent |
| `DISABLE_BROKER` | — | ⛔ absent |

`ControlAction` has **20 actions**. `LIQUIDATE` appears nowhere in the tree and is
implemented anyway, as a loop inside `_do_trigger_kill_switch` — found by searching for
what the code *does*. Two rows of the first mapping draft were wrong by name-search alone.

**`DEPRECATE_MODEL` (20th) retires a model version, and deliberately stops there.**
`ModelStatus.DEPRECATED` had existed since the enum's first version and was *unreachable* —
nothing set it, nothing read it — so the lifecycle had no terminal state and a PROMOTED
version stayed PROMOTED forever. Promotion now also refuses a DEPRECATED version, checked
before the EVALUATED gate so a retired model cannot be revived by re-evaluating it. Gated at
RISK_ADMIN, mirroring `PROMOTE_MODEL`.

It moves no capital. Whether deprecating a live model should flatten, reduce, or leave its
positions alone is [ADR-007](docs/adrs/ADR-007_component_containment_disable_commands.md)'s
halt-vs-degrade question, and answering it inside a component would be that component deciding
a capital question that is not its own. The action's return value states `capital_effect:
none` rather than leaving an operator to assume otherwise.

**`REDUCE_ONLY` was partial, and closing that gap is the most recent change.** It could
only ask whether an order's *direction* increases exposure, so an oversized `SELL` against
a long passed directionally and would cross through zero to open a short. The fix was two
missing inputs rather than new logic: `ReplayRunner._positions_view` now projects
`filled_quantity` from the fill receipt, and `ControlPlane` accepts a `portfolio_value`
callable so `position_size_pct` can become an absolute quantity. The rule itself
(`core/reduce_only.py`) was already written and tested — it had simply been wired to no
gate that could feed it.

Where no portfolio value is supplied the directional rule still refuses every increase and
only the overshoot refinement is skipped. That fallback is a recorded decision, not an
oversight: failing closed would let an optional constructor argument halt the whole book.

---

## 3. §2's 25 layers — 12 have a screen

§2 defines 25 named LAYER boxes in causal order. The console is grouped along them.

**With a screen (11):** L2 Data Truth Fabric · L3 Evidence Fabric · L4 Institutional
Research · L7 Strategy Certification Firewall · L13 Robust Portfolio Brain · L14 Financial
Truth · L15 Position Accounting · L18 Deterministic Capital Firewall · L20 Execution Kernel
· L22 Reconciliation · L24 Governed Learning

**Without one (13):** L1, L5, L6, L8, L9, L10, L11, L12, L16, L17, L19, L21, L23.

**L25 Champion/Challenger Arena now has one** — see §7bb. It was the terminus of §12's own
chain, and `LAYERS_WITHOUT_WORKSPACE` used to say so while `promote_model` existed without a
view. **L23 Institutional Memory is the remaining terminus**, and `/api/v1/memory` reaches
only `aios.c6.observation_completed` payloads — not the tiers, counterfactuals or promotion
records that make the layer what it is.

Three of the missing are load-bearing rather than incidental:

- **L23 Institutional Memory** and **L25 Champion/Challenger Arena** are the *terminus* of
  §12's own chain (`Memory → Counterfactual evaluation → Champion/Challenger statistics`).
  The console cannot show either end of the system's stated flow.
- **L12 Certified Playbook Engine** and **L11 Calibration & Selective Decision** are named
  in §12 as the precondition for any trade.

The rest are listed with reasons in `frontend/src/lib/architectureLayers.ts`; that file is
the single source of truth, and its gate fails if a layer is added, moved, or listed as both
present and missing.

---

## 4. Not every workspace is a layer

Placement records three kinds, because flattening them would hide the finding:

| Kind | Workspaces |
|---|---|
| On a §2 layer | the 11 listed above |
| §3 control plane | `models` (§3B Model Governance), `system` (§3C Observability) — §3 says its planes *cut across* layers, so a plane is not a layer |
| Not architecture-derived | `overview`, `trading` (genuinely cross-cutting, verified by what they mount), `design_system`, `settings` (tooling and configuration) |

---

## 5. §3's control planes

| Plane | As-built |
|---|---|
| A Governance | `CONSTITUTION.md` SHA-256 pinned in `core/constitution.py`, verified at boot |
| B Model Governance | 🟡 `kernel/registries.py` — and `ModelStatus.DEPRECATED` is **declared and never read** |
| C Observability | **19** `PlatformEventType` topics, hash-chained audit log, `SystemHealthWorkspace` |
| D Security | RBAC matrix in `core/control_plane.py`; scoped bus ACLs in `core/event_bus.py` |
| E Assurance | `research/evaluation.py` — PASS/FAIL/INCONCLUSIVE, promotion cannot be overruled |
| F Supply-Chain | `scripts/sbom.py`, `scripts/lock_dependencies.py` → `requirements.lock` |

**The `DEPRECATED` gap is worth stating plainly:** the registry can record a lifecycle
decision that nothing acts on. A model marked deprecated is still promotable and still
loadable. That is the same failure shape as `core/backtest.py`'s original booleans — a
conclusion stored without an enforcement consequence — and it reads as though something is
in control when nothing is.

---

## 6. §11's claim gate

`core/claim_gate.py` requires **14 provenance fields** on any reported figure:

`metric_definition`, `accepted_n`, `coverage`, `time_period`, `asset_universe`,
`regime_coverage`, `net_of_cost`, `out_of_sample`, `confidence_interval`, `max_drawdown`,
`tail_risk`, `experiment_count`, `model_version`, `dataset_version`.

A criterion can pass its threshold and still be `NOT_REPORTABLE`. The Layer 7 certification
view renders those as **two separate columns** for exactly that reason: a Sharpe of 1.6
against a 1.0 threshold PASSES and is still not a result. `ready_for_live` is typed `false`
at the API boundary and is not recomputed — live routing is constitutionally disabled in
this release, and the view says so rather than implying a metric is pending.

---

## 7. Dependencies

**3 required** — imported by shipped modules at import time: `pydantic`,
`pydantic-settings`, `httpx`.

**6 optional extras** — 4 infrastructure the system connects to, not libraries it imports:
`postgres` (psycopg), `nats` (nats-py), `ccxt`, `qdrant` (qdrant-client); plus `dev` (the
test/lint/type toolchain) and `all` (an aggregate that repeats the four, deliberately
rather than by reference — see the comment in `pyproject.toml`).

**Not dependencies:** MLflow — it appears only in two candidate-technology documents, as
the baseline being compared *against* ClearML. Not installed, not imported. §4 labels
QuestDB and Iceberg *"candidate"* itself, and they are correctly absent.

---

## 7b. The operator surface, and what it may not do

Added after `84d456d`. Recorded here because the figure gate in §10 cannot detect *silence*:
it compares numbers the document publishes, so a whole subsystem can be added to the tree
without failing a single check. The coverage check in §10 exists because of that.

| Surface | Where | Authority |
|---|---|---|
| Design tokens | `frontend/src/index.css` (36 tokens, `@theme`) | presentation |
| Themes + accent presets | `frontend/src/lib/theme.ts` → `dark-oled`/`paper` × `CYAN`/`EMERALD`/`AMBER`/`VIOLET` | presentation |
| Workspace layout | `frontend/src/lib/layout.ts`, edited via `frontend/src/components/LayoutPanel.tsx` | presentation |
| Chat: queries | `core/chat_console.py` → read-only snapshot builders | **none** |
| Chat: agent advisory | `core/agent_advisory.py` | **none** |
| Chat: commands | `core/control_plane.py` under the operator's own role | audited |
| Chat UI | `frontend/src/components/ChatPanel.tsx` → `frontend/src/lib/chatView.ts` | **none** |
| Empty/unreadable states | `frontend/src/lib/stateView.ts` → `StateView` | presentation |

**The advisory carries no authority, and that is structural rather than a promise.**
`core/agent_advisory.py` imports neither `core.control_plane` nor any order sink, and
`tests/test_agent_advisory.py` asserts that from the module's AST. Advisory routing is matched
*before* command routing, so a question containing a command verb cannot execute at any role.
Agents are not invoked: they are event-bus sinks whose `on_*` methods mutate state, so an
advisor reports what an agent has already recorded rather than waking it.

**Reads are an allowlist.** `READ_ONLY_VIEWS` is a closed `frozenset`; `_gather` raises on
anything absent from it. `SystemSnapshotBuilder` mixes `risk_state()` with
`settings_plane_put()`, so a dynamically-dispatched view name would have been one careless
edit from a chat message changing platform settings.

**Empty is not the same as unreadable.** `CONSTITUTION.md` §3.2 forbids substituting a default
for missing data. `frontend/src/lib/stateView.ts` makes `empty` require an `observedFrom`
naming the source that reported zero and `unavailable` require a reason — the distinction is in
the type, so omitting it is a compile error. `LiveTradingWorkspace` previously collapsed an
unavailable source to `[]` and then captioned it "reported by /api/v1/orders", asserting a
reading it never took.

**Hiding a workspace cannot disable anything.** `layout.ts` is presentation; the risk
firewall, kill switch and RBAC are server-side. `NON_HIDEABLE` keeps `settings` visible
because it holds the layout editor — hiding it would be a one-way door created by a cosmetic
toggle.

---

## 7bb. L25 Champion/Challenger Arena: a governance surface that worked, and said it did not

The arena was fully built and fully wired, and the console claimed otherwise.

`StrategyResearchWorkspace.tsx` carried the sentence *"Promotion to production is not wired:
no promotion endpoint exists."* Both endpoints exist — `POST /api/v1/control/promote_challenger`
and `POST /api/v1/control/evaluate_trial`, both `RISK_ADMIN`, dispatched from
`core/control_plane.py` — and `scripts/serve_command_center.py` passes the single
`ControlPlane` that `ReplayRunner` builds with both a `challenge_registry` and a
`trial_evaluator` attached. `lib/control.ts` already carried the metadata. Nothing called it.

That is `CONSTITUTION.md` §3.1 pointing the *opposite* way from the LIVE badge: not a control
claiming a capability it lacks, but a view denying one the code has. An operator reading that
sentence would not have gone looking for the control that does the work.

I checked the sibling claims rather than assume they shared the defect. Order submission,
trim and flatten really do have no endpoint — every route is GET except `control/{action}`
and `chat` — so those notes stand.

**Underneath the missing screen, promotion was silently unsafe.** `promote()` guarded the
kernel promotion receipt and the rollback-target registration with
`if self._promotions is not None and self._rollbacks is not None:`, so a registry built
without those controllers promoted the challenger, wrote a `CHALLENGER_DECISION` reading
PROMOTED, and returned `{"promoted": True}` having registered nothing that could undo it.
And `ReplayRunner` had two factories for that singleton which disagreed about the
dependencies, both guarded on `hasattr`, so whichever ran first won — and staging calls
`build_challenge_registry()`. Promotion now refuses before any state change or audit write,
and there is one factory.

The read model keeps four facts apart, because collapsing any of them is a lie:

| Fact | Meaning |
|---|---|
| `wired: false` | no registry on this composition root — a wiring fact, **not** an empty arena |
| `recommendation: INSUFFICIENT_EVIDENCE` | the trial has not been run on both sides — **not** a number, a narrow loss, or a tie |
| `verdict: null` | no `EvaluationRecord`; promotion is refused without one |
| `kernel_wired: false` | the promote button would be refused — say so before the press |

`frontend/src/adapters/arena.ts` carries these and derives the preconditions;
`frontend/src/components/views/ArenaWorkspace.tsx` renders them. The adapter refuses to
recompute the recommendation client-side — that would be authority the view must not have —
so `INSUFFICIENT_EVIDENCE` arrives with every figure null rather than as a zero. Both control
actions go through `runControl`, nothing local is mutated on click, and the arena is re-read
from the server after every accepted action, so a refusal cannot leave a promoted-looking
trial on screen.

**L23 Institutional Memory is now the last terminus without a screen.**

---

---

## 7bb2. LANDED is a claim about evidence, and 21 pieces of evidence are unreachable

A goal marked `LANDED` cites files as `evidence`. **Twenty-one of those files are imported by
nothing outside `tests/`.** A test importing a module proves the module works; it does not
prove anything reaches it. Every other gate here compares published *figures* against the
tree, so all of them were green.

**Three goals have no live library evidence at all:**

| Goal | Sole library evidence | Consequence |
|---|---|---|
| G090 Feature Fabric | `core/feature_store.py` | §12 places the Feature Fabric before the Fast Expert Model |
| G130 Portfolio Brain | `communities/c9_portfolio/optimizer.py` | portfolio proposals come from the live path instead |
| G160 Execution Digital Twin | `simulation/execution_twin.py` | **this is why layer 21 has no screen** — the twin is not on any production path |

**The sharpest of the other eighteen is G110.** Its summary promises *"conformal calibration
producing … a decision of TRADE, WAIT, ESCALATE, or ABSTAIN, where ABSTAIN is the default
under uncertainty."* Its `core/conformal.py` and `core/decision_gate.py` are imported by
nothing. The capability is not missing — `kernel/playbook.py` carries a live
TRADE/WAIT/ESCALATE/ABSTAIN router, wired through `kernel/bootstrap.py` and
`core/capital_firewall.py`. **The registry cites a dead parallel implementation of something
that is live elsewhere.**

Three more are why **L23 cannot yet have a meaningful screen**: `kernel/memory_tiers.py`,
`kernel/retrieval_contract.py` and `kernel/counterfactuals.py` are all unimported.
`CounterfactualStore` is instantiated *nowhere* outside tests — every ABSTAIN / REJECT /
NO_NEW_RISK restraint should retain one and nothing does. A screen over that would render an
empty list and call the layer delivered.

`scripts/verify_landed_evidence_is_live.py` now enforces this, with every instance listed and
a reason, and both lists self-clear: a listed goal that gains a live module, or a listed
module that gains an importer, fails the gate and the entry must go. It also fails when a
goal cites a file that is not in the tree at all.

**Two bugs this gate shipped with, both caught by its own harness.** The exclusion test
`".venv" in parts` did not match `.venv-fresh`, counting 4794 virtualenv modules as
first-party. Worse: reusing a compiled regex's `.pattern` **discards its flags**, so `^`
anchored to the start of each file and found zero importers anywhere — reporting 21 of 23
LANDED goals as dead, including `core/control_plane.py`, which `api/server.py` imports on
line 42. I reported that bogus number as a finding before catching it. Both defects are
commented at the code that would reintroduce them, because a verification artifact that is
confidently wrong is worse than no artifact.

**Stated limit:** this is a textual import check. It cannot see `importlib.import_module`, a
re-export, or attribute access through a registry, and it does not claim the imported path is
exercised at runtime — only that something outside the test suite references it. Two modules
in the tree use dynamic import, so the blind spot is small rather than absent.

---

## 7c. Where the tree stands against `ARCHITECTURE.txt` §13, and three things the goals do not say

### The goal numbering does not match

`ARCHITECTURE.txt` §13 specifies **28** goal IDs (`G010`–`G280`). `docs/goals/goals.json`
carries **25** (`G010`–`G250`), and the two schemes disagree on which number means what from
`G180` onward. Previously unrecorded; §7c below now resolves it exactly.

### The 28-to-25 arithmetic closes exactly, and G260 was declined on purpose

The 28-vs-25 gap is not three dropped goals. It resolves completely:

| Cause | §13 IDs | Effect |
|---|---|---|
| `Memory`, `Learning`, `Counterfactuals` collapsed into one goal | `G190`, `G200`, `G210` | −2 → registry `G180` *Institutional Memory, Governed Learning, and Counterfactuals* |
| `Disaster Recovery` declined | `G260` | −1 |

`28 − 2 − 1 = 25`, with no residue — so **every** §13 ID is accounted for, and nothing was
silently lost. The renumbering I first reported as "the tail was renumbered" actually begins
at `G220`→`G200`, because the three-way merge above shifts every later ID by one. §13 `G180`
(`OMS`) is covered by registry `G150` *Execution Kernel and Order Management*.

**`G260` was declined deliberately, with a stated reason.** Registry `G220`'s notes record it
alongside failover: both appear in `ARCHITECTURE.txt` **once, as a bare label**, with
`RPO`/`RTO`/`backup`/`restore` at **zero occurrences**. Modelling either would mean inventing
the requirements, which is what the §14 freeze rule exists to prevent. The decline is sound.

**`research/disaster.py` is not that capability.** It is *"Disaster-lab drills (Directive
60): chaos scenarios against the REAL stack"* — `OutageThenHealFetcher` injects `ConnectionError`
at chosen bars mid-replay and the drill asserts the run freezes, escalates or blocks rather
than fabricating results. That is **resilience testing against the real stack**, and it is
governed work under other goals. It shares a name with §13 `G260` and implements something
else: fault injection, not `RPO`/`RTO` backup-and-restore.

An earlier draft of this section recorded `G260` as "implemented, tested and ungoverned".
That was wrong twice over — it read `research/disaster.py` as the capability because the
filename matched, and it missed the decline recorded in `G220`'s notes. `scripts/
verify_goal_id_divergence.py` now makes the whole mapping machine-checked, and re-checks the
`G260` rationale against the tree so the decline cannot quietly become stale.

### Twenty per cent of the settings API is inert

Measured across the 83 fields of `SystemSettings`: **17 have no consumer in any
component.** Four more were found and removed — `accentTheme`, `highDensityMode`,
`numberFont`, and `defaultExecutionMode`, the last of which had **two** controls writing it
(a `TopSystemBar` toggle and a `SettingsWorkspace` button pair) while rendering *"LIVE
GATEWAY"* in amber. `defaultExecutionMode` had **zero backend occurrences**: venue selection
is governed entirely by `AIOS_ALLOW_LIVE_EXECUTION` and `AIOS_EXCHANGE_TESTNET`, which no UI
could reach. A console that says LIVE while the adapter refuses real-money routing is
`CONSTITUTION.md` §3.1 — a fabricated capability.

`scripts/verify_no_dead_settings.py` now enforces this. It **fails on any unlisted dead
field** and **fails when a listed field gains a consumer**, so the list shrinks itself and
"we'll get to it" cannot quietly become permanent. 17 entries are listed with reasons,
mostly reserved capital-governance parameters (`var95DailyLimitUsd`, `maxSectorBetaCap`,
`mandatoryChallengerGate`) whose deletion is a product decision rather than a bug fix.

**The architecture does not describe a console execution-mode toggle at all.** §13 specifies
a staged progression — `G270` Long Shadow, then `G280` Canary Capital — which is a
governance gate. Removing the toggle is therefore working *exact* the architecture, not
departing from it.

### What remains is not engineering

`G240` and `G250` are the only two goals not LANDED, and both are human-held: a broker
testnet connection plus the five Phase 5.0 gates, and the `CONSTITUTION.md` §1 amendment
respectively. The buildable backlog is not the goal list — it is the **ten layers that have
a LANDED goal and no screen** (L1, L5, L6, L8, L9, L10, L11, L21, L23, L25).

---

## 8. Verification gates, and their real numbers

| Gate | Command | Result |
|---|---|---|
| Backend tests | `pytest -q` | 1798 run · 1753 passed · 45 skipped · **0 failed** |
| Frontend tests | `vitest run` | 230 across 28 files |
| Types | `mypy --python-version 3.12 --follow-imports=silent core api communities schemas` | clean, 110 files |
| Lint | `ruff check .` | clean |
| Anti-patterns | `scripts/anti_pattern_lint.py` | clean, 6 rules |
| Frontend types | `tsc -b --noEmit` | clean |
| Build | `vite build` | two entries |
| Operator isolation | `scripts/verify_operator_isolation.py` | green, **26** forbidden modules — the list is derived from the filesystem, so adding a workspace widens the operator's isolation automatically |
| Theme tokens | `scripts/verify_theme_gate.py` | 0 hex outside `index.css`, 0 hardcoded palette classes, both themes + all 4 accents complete |
| State honesty | `scripts/verify_state_honesty.py` | 18 views, no hand-rolled or cause-asserting empty state |
| Dead settings | `scripts/verify_no_dead_settings.py` | 83 fields, 17 documented inert, **0 undocumented** |
| Goal-ID divergence | `scripts/verify_goal_id_divergence.py` | 28 §13 IDs = 25 registry IDs, arithmetic closes, `G260` decline re-checked |
| Landed evidence | `scripts/verify_landed_evidence_is_live.py` | 23 LANDED goals, **3 with no live evidence at all**, 21 dead modules, 0 undocumented |

Five of these gates are new, and each answers "can this fail?" with a mutation harness rather
than a claim: `scripts/prove_theme_gate.py` (6 rotations),
`scripts/prove_state_honesty.py` (3), `scripts/prove_dead_settings_gate.py` (3),
`scripts/prove_goal_id_divergence.py` (4) and `scripts/prove_landed_evidence_gate.py` (4).
A gate that has never been observed red is an assertion about itself, not about the tree.

Two of those gates exist because everything else was green while the tree was wrong. The
theme gate: `tsc`, vitest, the build and the isolation gate were **all green** while 58 sites
rendered `var(--color-accent-accent-violet)` — nothing type-checks a CSS variable's value.
The dead-settings gate: four inert controls, one rendering *"LIVE GATEWAY"*, passed every
type and test check, because a field with no consumers is valid TypeScript.

`scripts/prove_goal_id_divergence.py` mutates a **temp copy** of `ARCHITECTURE.txt` via
`AIOS_ARCHITECTURE_PATH`, never the frozen file: a probe interrupted between mutation and
restore would corrupt the one document every other claim is measured against. It also
declares what it cannot prove — whether a bare label has quietly acquired requirements *in
place* is not mechanically decidable, so that stays a human review duty.

**The type gate's command matters.** `--python-version 3.12` is not optional in this
environment: numpy 2.5.3's stubs use PEP 695 `type` statements, which a 3.11 target
rejects outright. CI runs the narrow scope above; a *wider* manual sweep exists and can
regress silently until CI is widened — an honest residual carried forward.

---

## 9. Known divergences and open work

Ordered by consequence, with the blocker named rather than implied.

| Item | State | Blocker |
|---|---|---|
| `REDUCE_ONLY` overshoot | 🟡 partial | needs an absolute quantity at the classification point |
| 4 × `DISABLE_*` | ⛔ absent | [ADR-007](docs/adrs/ADR-007_component_containment_disable_commands.md) — one halt-vs-degrade decision governs all four |
| `ModelStatus.DEPRECATED` | 🟡 latent gap | ADR-007 approval; same enforcement point as `DISABLE_MODEL` |
| Multi-process flake | 🟠 open | `worker failed (1)` with empty stdout **and** stderr, load-sensitive; instrumentation suppresses it, so it needs a capture |
| 13 of 25 layers | 🟡 gap | §12's terminus (L25 Arena) now has a screen; **L23 Institutional Memory** is the remaining terminus |
| SSE payload | 🟡 2 keys | consumer-side coalescing landed; topic-delta is a contract change |
| `DISABLE_BROKER` | ⛔ blocked | enforcement point `communities/c5_execution/adapters.py` has another work stream's uncommitted edits |
| UI layout | 🔵 reserved | the §2 spine is built; the visual arrangement is deliberately unchosen |

**The one decision that unblocks the most:** when a component is deliberately disabled,
does the system **halt** (`CONSTITUTION.md` §3.2 — *"Missing data ⇒ NO TRADE / UNKNOWN -
never a default value"*) or **degrade to a labelled fallback** (`core/model_gateway.py:4` —
*"callers fall back to deterministic mode"*)? Implementing `DISABLE_MODEL` or
`DISABLE_PROVIDER` by making a component unavailable would currently **keep trading**. That
is the opposite of what an operator disabling a model mid-incident is asking for, and no
amount of correct auditing makes it right.

---

## 10. Verifying this document

```powershell
# gates
python -m pytest -q                                     # 1762 / 1717 / 45 / 0 failed
Push-Location frontend; .\node_modules\.bin\vitest.cmd run; .\node_modules\.bin\tsc.cmd -b --noEmit; Pop-Location
python -m mypy --python-version 3.12 --follow-imports=silent core api communities schemas
python -m ruff check .
python scripts/anti_pattern_lint.py
python scripts/verify_operator_isolation.py             # reads sourcemaps

# specific claims
Select-String -Path ARCHITECTURE_MAPPING.md -Pattern '^\|'   # every claim has a command there
```

`ARCHITECTURE_MAPPING.md` holds the detailed gap analysis with per-claim commands;
`ARCHITECTURE_PLANES.md` the module→plane manifest; `ARCHITECTURE_ZONES.json` the trust-zone
map enforced by `tests/test_trust_zones.py`.
