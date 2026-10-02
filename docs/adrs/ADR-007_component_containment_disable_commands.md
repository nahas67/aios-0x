# ADR-007: §8 component-level containment — the four DISABLE_* commands

## Context

`ARCHITECTURE.txt` §8 names eight emergency commands that *"must be deterministic, must
bypass AI, must be audited, must survive model/runtime failure."* Six now exist:

| §8 command | State |
|---|---|
| `STOP` | covered (`PAUSE_TRADING`, `TRIGGER_KILL_SWITCH`) |
| `NO_NEW_RISK` | covered as a *state* (RiskGovernor escalation) |
| `REDUCE_ONLY` | **partial** — see ADR context in `ARCHITECTURE_MAPPING.md` §5 |
| `LIQUIDATE` | covered (`_do_trigger_kill_switch` flatten loop) |
| `DISABLE_STRATEGY` | **absent** |
| `DISABLE_MODEL` | **absent** |
| `DISABLE_PROVIDER` | **absent** |
| `DISABLE_BROKER` | **absent** |

The four absent commands are one coherent family. §8 asks for *component-level*
containment — stop this strategy, this model, this provider, this broker — and the tree has
only *global* containment: one kill switch that flattens every position at an adverse
price and escalates to `EMERGENCY_HALT`. An operator whose problem is isolated to one
strategy, one model or one venue must currently flatten the entire book.

`REDUCE_ONLY` was built under ADR-006-era practice and is recorded as **partial**, not
covered, because `classify_plan` can enforce direction but cannot detect an overshoot
without an absolute order quantity. The same discipline applies here: none of the four is
a small addition, and each would be dishonest to call "covered" on partial enforcement.

`CONSTITUTION.md` §4 requires a human principal to approve an ADR before it takes effect,
and §2.2 requires the kill sequence `cancel→flatten→EMERGENCY_HALT` to stay intact. This
ADR does neither: it specifies the four precisely so the decision can be made on evidence
rather than on the shape of the command names.

### What exists today, per command

Searched by capability, not by name — the same discipline that found `LIQUIDATE`
implemented inside `_do_trigger_kill_switch` despite having zero occurrences in the tree.

**`DISABLE_MODEL`.** A registry exists: `kernel.registries` exposes a models registry with
a `ModelStatus` enum (`DEFINED`, `TRAINED`, `EVALUATED`, `PROMOTED`, `DEPRECATED`),
reached from the control plane as `self.kernel_bridge.kernel.models`
(`core/control_plane.py:416`), where `_do_promote_model` already reads
`models.get(model_id, version)` and refuses to promote a model not in `EVALUATED`. So there
is a target, a status vocabulary, and a precedent for fail-closed refusal.

The finding that changes the estimate: **`ModelStatus.DEPRECATED` is declared and never
read.** Searching the whole tree, `DEPRECATED` appears only where it is declared —
`kernel/registries.py:317` for `ModelStatus`, and separately at line 42 as a member of a
*different* enum whose transition map (`DRAFT → VALIDATED → ACTIVE → DEPRECATED`, lines
104–106) belongs to that other lifecycle, not to models. Nothing consults a model's
`DEPRECATED` value, so a model marked deprecated is still promotable and still loadable.

That cuts two ways, and both matter for sequencing:

- **Cheaper than assumed.** The natural implementation is probably to make
  `DEPRECATED` actually mean something — refuse to promote or load a deprecated model —
  rather than to invent a new status. The vocabulary already exists and already says the
  right thing; it is simply not enforced.
- **And it is a latent gap in its own right.** Today the registry can record a lifecycle
  decision that nothing acts on, which is the same failure shape as `core/backtest.py`'s
  original booleans: a conclusion stored without an enforcement consequence. Worth fixing
  whether or not §8's `DISABLE_MODEL` is approved, because an unenforced status is worse
  than an absent one — it reads as though something is in control.

**Still unresolved:** whether disabling a model should also withdraw it from in-flight use
immediately, or only block future promotion and loading. Those are different safety
properties, and §8 does not say which it wants.

**`DISABLE_PROVIDER`.** There is no provider registry to enumerate. `core/model_gateway.py`
is *provider-agnostic but single-provider*: one gateway instance is wired per composition
root and exposes a `provider` property. "Disable the provider" therefore means disabling
the only provider, which is not component-level containment — it is global by another
name. **This is the finding that most changes the picture:** the command presupposes a
multi-provider topology the tree does not have. Either the topology changes first (a much
larger decision), or the honest rendering is "the provider is unavailable", which is not
the same capability.

**`DISABLE_STRATEGY`.** Strategies are identified by `strategy_id` throughout the store and
by the challenge registry wired into the control plane. A gate is feasible in principle:
refuse to *promote* a disabled strategy, and refuse to *generate plans* from one.
**Blocking unknown:** whether disabling must also flatten that strategy's existing
positions, or merely stop new ones. Those are materially different safety properties and
§8 does not say which it wants.

**`DISABLE_BROKER`.** A venue exists but is micro-live only and off by default:
`AIOS_ALLOW_LIVE_EXECUTION=1` plus credentials, with a `$100` per-order notional cap in
`CcxtExecutionAdapter`. So the target is real but nearly dormant. **Hard blocker, and an
operational one rather than a design one:** the enforcement point is
`communities/c5_execution/adapters.py`, which another work stream currently has uncommitted
edits to. Implementing this ADR's fourth command requires that file, and touching it now
would collide with in-flight work.

### The tension that must be resolved before any of them

`CONSTITUTION.md` §3.2 states *"Missing data ⇒ NO TRADE / UNKNOWN - never a default
value."* But `core/model_gateway.py:4` documents the opposite behaviour for its own
failure path: *"No credentials configured → `ModelUnavailableError`; callers fall back to
deterministic mode. The system NEVER pretends an LLM was consulted."*

Those are reconcilable — the gateway is honest about *not* consulting an LLM, and
deterministic mode is a labelled mode rather than a fabricated answer — but they pull in
opposite directions for containment. If `DISABLE_MODEL` or `DISABLE_PROVIDER` is
implemented by making the model or provider unavailable, the system's documented behaviour
is to **fall back to deterministic mode and keep trading**, not to halt. That is the
opposite of what an operator disabling a model during an incident is asking for, and no
amount of correct auditing makes it the right behaviour.

So the first substantive decision in this ADR is not per-command. It is:

> When a component is deliberately disabled, does the system **halt** (constitutionally
> conservative, §3.2) or **degrade to a labelled fallback** (the gateway's existing
> behaviour, §2-style "the system NEVER pretends")?

This ADR does not choose. It flags the choice because picking wrong in either direction is
dangerous, and because it applies to all four commands at once.

## Decision

**PROPOSED — no component-level containment command is implemented by this ADR.**

What this ADR does decide is the shape of the work, so that approval can be item-by-item
rather than all-or-nothing:

1. **Resolve the halt-vs-degrade question first.** It governs all four commands and is not
   answerable per command. Nothing should be built before it is settled.
2. **Then implement in order of real exposure:** `DISABLE_MODEL` (make `DEPRECATED` mean
   something — the vocabulary exists and is unenforced, so this is cheaper than it looks,
   and the gap is worth closing regardless), then `DISABLE_STRATEGY` (a real multi-target
   problem with an existing id, but it needs the disable-vs-flatten question answered),
   then `DISABLE_PROVIDER` (blocked on a topology decision that may make it meaningless as
   written), then `DISABLE_BROKER` (blocked on file ownership, and nearly dormant while
   live routing is off).
3. **Each command gets its own ADR** once the shared question is settled, so that approving
   one does not silently approve the fail-open semantics of another.
4. **`REDUCE_ONLY` stays recorded as partial.** It does not become "covered" by association,
   and its overshoot gap is unrelated to these four.

The alternative — implementing all four now, each with its own guess at the semantics —
would put four safety-critical components on invented behaviour, which is the specific
failure this repository's honesty laws exist to prevent.

## Status

- **State**: PROPOSED — awaiting human principal approval, per `CONSTITUTION.md` §4.2
- **Date**: 2026-10-02
- **Authors**: AIOS System Architecture Team

## Consequences

### Positive Consequences

- The remaining §8 gap is specified with evidence rather than left as a list of names.
- `DISABLE_PROVIDER` is identified as presupposing a topology the tree lacks — the single
  most valuable finding here, because implementing it literally would have produced a
  command that looks component-level and behaves globally.
- The halt-vs-degrade tension is surfaced before code exists, not after.
- Ordering is justified by real exposure rather than by the order §8 lists the names.
- `DISABLE_BROKER`'s blocker is recorded as file ownership, which is temporary and
  visible, rather than as a mysterious unimplemented command.

### Negative Consequences / Trade-offs

- Containment stays global in the meantime: an isolated component failure still requires
  flattening the whole book. This is the real, ongoing cost, and it is a safety cost.
- Nothing here is implemented, so nothing here is tested.
- If the halt-vs-degrade answer turns out to be "degrade", §3.2 may need an explicit
  amendment to stay coherent, which is a larger process than writing four commands.

## Compliance & Verification

Once approved and implemented, each command must satisfy:

- **Deterministic, AI-free** (§8): the gate is a lookup, never a model call.
- **Audited** (§8, §3): a dedicated event, not only the generic `CONTROL_ACTION` envelope —
  the same standard `set_reduce_only` meets with `REDUCE_ONLY_SET`.
- **RBAC**: RISK_ADMIN. These are standing capital constraints of the same class as
  `SET_MAX_POSITION_PCT`, `SET_AUTONOMY` and `SET_REDUCE_ONLY`.
- **Off by default**: never enabled implicitly.
- **Independent tests** — the rule as pure functions in `core/`, mutation-checked, plus
  integration tests against the real call site. Two defects in the `REDUCE_ONLY` work were
  invisible to unit tests and caught only by integration tests against the actual wiring:
  an unreachable gate, and a positions contract read the wrong way round.
- **Honest partial coverage**: recorded as partial wherever enforcement is partial. The
  operator surface must never show a green tick beside a control that does not do
  everything its name implies.
- **§2.2 untouched**: no component command may cancel, flatten, or lift a drawdown halt.
  Only the kill switch owns that sequence.
- Counts in `frontend/src/lib/emergencyCommands.ts` are pinned by test, so implementing any
  of these forces the §8 tally to be restated rather than left stale.