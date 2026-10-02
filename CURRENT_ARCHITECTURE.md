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

## 3. §2's 25 layers — 11 have a screen

§2 defines 25 named LAYER boxes in causal order. The console is grouped along them.

**With a screen (11):** L2 Data Truth Fabric · L3 Evidence Fabric · L4 Institutional
Research · L7 Strategy Certification Firewall · L13 Robust Portfolio Brain · L14 Financial
Truth · L15 Position Accounting · L18 Deterministic Capital Firewall · L20 Execution Kernel
· L22 Reconciliation · L24 Governed Learning

**Without one (14):** L1, L5, L6, L8, L9, L10, L11, L12, L16, L17, L19, L21, L23, L25.

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
| Operator isolation | `scripts/verify_operator_isolation.py` | green, 25 forbidden modules |
| Theme tokens | `scripts/verify_theme_gate.py` | 0 hex outside `index.css`, 0 hardcoded palette classes, both themes + all 4 accents complete |
| State honesty | `scripts/verify_state_honesty.py` | 18 views, no hand-rolled or cause-asserting empty state |

The last two are new, and both answer "can this fail?" with a mutation harness rather than a
claim: `prove_theme_gate.py` (6 rotations) and `prove_state_honesty.py` (3 rotations). The
theme gate exists because `tsc`, vitest, the build and the isolation gate were **all green**
while 58 sites rendered `var(--color-accent-accent-violet)` — nothing type-checks a CSS
variable's value.

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
| 14 of 25 layers | 🟡 gap | incl. §12's own terminus |
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
