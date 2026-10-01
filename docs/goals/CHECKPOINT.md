# AIOS-0X vNext — Checkpoint

**Program:** 13 workstreams (W0–W12), 25 goals (G010–G250), derived from
`ARCHITECTURE.txt` and 28 externally reviewed repositories. **`ARCHITECTURE.txt` is
not in this repository and is not version-controlled** — it sits beside the working
tree, so every `§` anchor below (2 Layer 9, 3E, 11, 14) is verifiable only by someone
holding that file. Stated here rather than left implicit because the document's
central scope claim — what the architecture *requires* — rests on a file a reader
cannot check. `CONSTITUTION.md` and the two in-tree architecture documents are
tracked, and every section reference to those resolves.

**Authority:** `docs/goals/goals.json` is the source of truth for goal status;
`tests/test_goal_registry.py` enforces its rules. This file is a human summary
and is deliberately *not* authoritative — where the two disagree, the registry
and the tests win.

**Last verified**. Measured on the working tree that became the most recent commit,
which added this block and the close-out below; the last commit *before* that change is
`5442949` (140 commits, 497 tracked files, working tree clean).

The block cannot name its own commit, and an earlier version pretended to: it said
`git rev-parse HEAD` = `75d3d5c` while reporting the figure measured after that commit,
which was impossible for the tree it named. Stating what was measured is worth more than a
hash that is stale by one commit, and defect #56's rule -- this block is what a reader
checks first, so a wrong one is worse than none -- is the reason it is said in words.

- **Full suite hermetic** (no `AIOS_TEST_PG_DSN` / `AIOS_TEST_NATS_URL`) —
  `1612 passed, 12 skipped, 76 deselected` (exit 0, 4:55). Of the 1700 tests collected with
  no live backend, the hermetic selection collects 1623. This is the authoritative current
  number, and it is the one CI runs.
- **Full suite with PostgreSQL *and* NATS JetStream up** — `1750 passed, 1 skipped`
  (exit 0, 7:11), measured on this same tree rather than carried forward from an earlier
  one. Replaces `1646 passed, 1 skipped`, which the block itself had labelled as measured
  before this cycle's additions. Re-run with
  `docker compose -f docker-compose.test.yml up -d` plus `AIOS_TEST_PG_DSN`. Counts are
  read from junit-xml rather than scraped from stdout, because `addopts = "-q"` combines
  with an explicit `-q` into `-qq`, which prints no summary line at all -- and a figure
  scraped that way is a figure nobody read.

  The gap between the two figures is **not** just the marker. Of 1751 collected with a live
  backend, 76 are excluded by `-m "not integration"` and **51 are not collected at all
  without one** -- they are the parity suites, which is the same shape as defects
  #33-#36 and #52: a test that cannot run on one tier quietly stops being the test its name
  claims. Verified by diffing collected ids with and without the two variables.

- ruff clean · mypy clean on 145 source files · anti-pattern lint clean (6 rules) ·
  constitution pin verifies at boot · architecture boundaries and goal registry pass ·
  zero secret findings in tracked content.
- **Dependency lock gate** — `scripts/lock_dependencies.py --check` exits 0. All six
  properties mutation-checked. Three narrowings are disclosed in the module docstring
  rather than assumed: transitive-closure completeness, added packages, and
  transitive version authenticity (41 of 52 locked packages carry no range pyproject
  states). See #51, #53.
- **TLA+ model-checked** — `scripts/run_tlc.ps1`, **four** specs, no property violated:
  OrderLifecycle 70 generated / 42 distinct / depth 4; Outbox 16 / 13 / depth 7;
  KillSwitch 88 / 48 / depth 11; Reconciliation 793,036 / 1,494 / depth 3.
  `CHECK_DEADLOCK` is off in every `.cfg` because each terminal state is deliberately
  a dead end. Of the eight targets architecture §3E names, four are modelled; the
  other four are covered by existing specs or unspecified (#48).
- **Frontend** — `tsc -b --noEmit` clean · `vite build` succeeds · **21 vitest files /
  86 tests** pass. The SSE stream is consumed; the frame's `executive` was verified
  field-for-field against `GET /api/v1/executive` on a live server, so no translation
  sits between socket and screen.
- **Docker image builds** (`aios-0x:test`, `backends importable`), container serves
  `/api/v1/health` and `/`, image's own HEALTHCHECK reports `healthy`, constitution
  pin verifies inside the container. Re-verified this cycle: the image serves
  `/api/v1/health` with `audit_chain_valid: true` and carries CONSTITUTION.md.
- **Release archive builds and self-verifies** — 312 files, manifest agrees with member
  names, `verify_archive` true. SBOM: CycloneDX 1.5, 52 components.
  All four bullets above re-measured on the tree this block describes. Two were
  WRONG and are corrected here: KillSwitch's search depth is 11, not the 4 recorded,
  and the archive holds 312 files, not 306. The KillSwitch state counts were right,
  which is why the error survived — a reader checking the headline sees matching
  numbers. Four specs model-check clean in 18 seconds, so re-running cost almost
  nothing, and this block is the thing a reader trusts without checking. That is
  also why defect #56's rule cuts both ways: copying the previous block forward is
  how the depth got wrong in the first place.

Every CI step is green. The one that used not to be -- "Lock file is current" -- is
now green because it checks the lock against `pyproject.toml` rather than against
whatever versions one machine happened to install (#51). The CI workflow itself has
not been executed here, since no GitHub activity is permitted.
---

## 1. Where the program stands

| Status | Count | Goals |
|---|---|---|
| `LANDED` | 23 | G010, G020, G030, G040, G050, G060, G070, G080, G090, G100, G110, G120, G130, G140, G150, G160, G170, G180, G190, G200, G210, G220, G230 |
| `PARTIAL` | 0 | — |
| `NOT_STARTED` | 0 | — |
| `BLOCKED` | 2 | G240 G250 |

Progress this cycle: G080 closed entirely; G070's lineage and failure reasons,
G050's durable decision sink, and G120's playbook engine all landed. G220 gained
a third model-checked spec (`KillSwitch`) covering the third of the architecture's
eight assurance targets that had been specified but unimplemented, and that work
surfaced a constitutional defect (#41) rather than merely a missing artifact.
G100's objective was corrected (#43): it had claimed a type that exists nowhere
and a capability nobody built. The `PARTIAL` count is a poor progress signal on
its own — the honest read is in the per-goal notes in section 4.

**Twenty-three goals are genuinely complete.** G010 (Financial Truth) and G170 (Broker
Reconciliation) were the pre-existing foundation. **G080 (Certification
Firewall)** was the first goal landed and closed entirely in this cycle — the
distinction is that every one of its checks is now *measured*, and a check that
cannot be faked is a gate rather than a form. **G070 (Immutable Experiment
Ledger)** is the second: failures with reasons, verdicts, lineage, and the
trial denominator all survive the process. **G020 (Security Master)** is the
third: a populated, bitemporal, cross-dialect book with a real delisting for
the survivorship detector to find. **G050 (Agent Governance)** is the fourth:
durable log, PG tier, and policy as signed data. **G150 (Execution
Algorithms)** is the fifth: exact-arithmetic schedulers inside the governed
path. **G190 (Evaluation Harness)** is the sixth: a deterministic runner
behind the claim gate with every result carrying an interval. **G140 (Capital
Firewall)** is the seventh: the envelope is now an enforced boundary, not a
tested object — no venue submit without one. **G040 (Evidence Fabric)** is
the eighth: producers write through the ledger, on both tiers, with replays
as no-ops rather than twins. **G030 (PIT Data Fabric)** is the ninth: dataset
versions durable with resume, and backfill that assigns knowability without
ever inventing it. **G100 (Regime)** is the tenth: detection with provenance
instead of labels. **G110 (Calibration)** is the eleventh: intervals that
earn coverage plus a gate that decides. **G060 (Quant Factory)** is the
twelfth: typed immutable factor and strategy-spec registries with warmup
refusals, gap poisoning, named bind violations, and reports where every
shipped number is declared. **G090 (Feature Fabric)** is the thirteenth: one
shared transform for offline and online, parity as a checked claim with its
own epsilon, and a decision path structurally verified to make no network
calls.

**G120 (Playbook Engine)** is the fourteenth: durable policies with
revocation-safe loading, a live regime feed, and an offline proposer that
reports per-regime derivations or named refusals.

**G180 (Memory)** is the fifteenth: decay that actually demotes — recall
blends tier salience into ranking with expired records excluded rather than
sunk, SAFETY surviving every horizon, and every blended match recording how
it was ranked. **G130 (Portfolio Brain)** is the sixteenth: inverse-volatility
and HRP over distributions plus covariance, disagreement raising a finding
instead of averaging, output a proposal that cannot be submitted anywhere.
**G160 (Execution Twin)** is the seventeenth: per-stage latency decomposition
with queue, partials, and impact over a closed-form fixture, comparing
20/50/100/200 ms with latency as the only variable. **G200 (Arena)** is the
eighteenth: promotion gates measured result plus identified human, with no
overrule and no repeats. **G210 (Trace Continuity and Observability)** is the nineteenth:
eleven canonical stages, one id threaded from plan to outbox to governed
call, gaps reported instead of filled.

**G220 (Formal Assurance)** is the twentieth: TLA+ for the order lifecycle
and the outbox, with drift tests pinning spec to implementation. **Both specs
are now genuinely model-checked** — `scripts/run_tlc.ps1` runs TLC in a
container, so no Java toolchain is admitted to a Python project. OrderLifecycle
explores 42 distinct states to depth 4; Outbox 13 to depth 7. Running them
refuted several properties, including one that was simply false; see defect #39.
**G230 (Governance, Security and Supply-Chain planes)** is the
twenty-first: generated SBOM covering exactly the lock, self-verifying
releases by manifest, and a tree with no secrets in it.

**Zero `PARTIAL`, zero `NOT_STARTED`.** Every engineerable goal is landed.
What remains is `BLOCKED`: two goals no engineering completes.

---

## 2. Completed in this cycle

Six workstreams and one follow-on were executed in order, each making the previous
one load-bearing. Every item below is enforced by a test that fails if the property
is removed.

### W0 — Contract freeze *(gates everything)*

- **Goal registry** — `docs/goals/goals.json` + `docs/goals/README.md`. The
  repository previously contained **zero** `G0xx` tokens in any file, so "is G040
  done?" had no authoritative answer. 25 goals with status, gates, evidence.
- **Registry validator** — 19 tests. The load-bearing one: `LANDED` requires
  evidence paths that exist, and G080/G120 are cross-checked against source, so
  a document cannot promote a goal without code behind it.
- **Authority-chain tests** — 54 tests in `tests/test_authority_chain.py` plus 7 in
  `tests/test_architecture_boundaries.py`; 61 was never the count of the file named.
  I1–I10
  as static source analysis: no LLM import or aliased call in the deterministic
  core, no venue call from the intelligence plane, cap guards must compare `>`
  not `<`, role-checked lockout release, no in-place `UPDATE` on claims, no
  performance claim leaving the API ungated, constitution pin verifies.
- **Anti-pattern lint** — 6 rules (AP1–AP6) over the 28-repo sweep, a build gate
  in CI. Catches env-key signing on agent-reachable paths, prompt-requested
  position sizes, permissive control defaults, model numbers reaching order size
  parameters, unsourced safety claims, unqualified return figures.
- **Statistical claim gate** — `core/claim_gate.py`, 20 tests. 14 required
  provenance fields; a bare accuracy figure cannot be presented as a result.
  A measured `0` counts as supplied, `None`/`""`/`NaN` do not.
- **mypy widened** 80 → 109 files, closing the regression gap recorded as manual.
  Now **145 files**, which is the list CI checks.
- **License + dependency policy** — `docs/LICENSES.md`, `docs/DEPENDENCY_POLICY.md`.
  Strong copyleft is inadmissible as a runtime dependency; a CI check enforces it.
- **`.deepeval/`** — empty directory advertising a harness that did not exist;
  resolved.
- **The `$100` cap** — my plan called it a placeholder to delete. Reading
  `CONSTITUTION.md:21`, it is a ratified constitutional limit enforced by a
  SHA-256 pin. **Kept**, and now guarded by a test. Deleting it would have been
  an unratified constitutional change.

### W1 — Security Master + Corporate Actions

- Bitemporal `InstrumentIdentity`: `valid_from/valid_to` (what was true) ×
  `recorded_from/recorded_to` (what we believed). Two independent query paths,
  `as_of` and `as_known`, proven to return *different* answers during a
  correction window — which is the entire justification for bitemporality.
- Supersession is one atomic transaction. Rejected source assertions are
  recorded in `identity_conflicts`, not discarded: a source that was wrong once
  is evidence.
- Corporate action engine with **back-adjustment relative to an explicit anchor**
  and exactly invertible transforms.
- Migration v3, DDL for both dialects. 47 + 19 tests.

### W2 — Point-in-Time Data Fabric

- Six-clock `TemporalInstant` with non-decreasing order enforced at construction.
- `assert_no_lookahead` / `filter_as_of`: refuse data whose knowable time is
  future **or unknown**. An unknown timestamp is not "probably fine"; it is the
  absence of the required proof.
- `DataProvenance.available_at` as the PIT join key, distinct from
  `retrieved_at`. `DatasetVersion.is_pit_qualified()`. 19 tests.

### W3 — Evidence Fabric + Claim Ledger

- Content-addressed `SourceArtifact`, hash verified **on read**.
- Append-only `Claim`; supersession inserts, never updates.
- `confidence=1.0` requires two independent refs; duplicates do not count.
- Evidence refs capped at 8. 23 tests.
- This closes the gap all three reviewed research repos left open: no persisted
  claim → source → page → quote chain a verifier can re-check.

### W4 — Agent Governance

- `ToolGuardian`: per-argument provenance **required at the type level**, five
  dispositions, HMAC-signed envelopes, rolling tamper-evident chain hash,
  fail-closed on any rule or evaluator error.
- Deterministic before agent: the model may narrow an allow, never widen a modify
  or unlock a deny.
- Four defects of the reference implementation (`agent-control-standard` v0.1.0)
  fixed rather than inherited: unsigned envelopes, fail-open default, per-call
  rather than per-argument taint, no `modify` power.
- `DecisionSink` lives in `schemas/governance.py` beside `ToolGuard`, because it
  is a contract both `kernel/` and `core/` need — neither imports the other to
  express it. The guarantee is carried by the *absence* of methods: no
  `update`, no `delete`, so no caller can reach for one.
- **`core/decision_sink.py` + migration v4: the audit log now outlives the
  process.** Append-only is enforced by *database triggers*, not by application
  discipline — a tamper that must be defeated by every call site being correct
  succeeds the first time one is not. Four tamper classes are refused
  separately (`UPDATE`, `DELETE`, out-of-sequence `INSERT`, out-of-chain
  `INSERT`), each naming itself so a refusal sends an operator to the right
  place. `ToolGuardian.resume()` adopts a stored head rather than opening a
  second chain over the top of the first. 33 tests.
- **The load-bearing finding, and the one worth keeping: a hash chain does not
  detect truncation.** The chain is a rolling digest over the entries present, so
  removing the last three decisions leaves a shorter log whose every remaining
  link still recomputes correctly. Any audit stopping at "the links hold" passes
  a log that has had its tail cut — the tamper an operator would most want to
  catch, and the one a green suite would have declared safe.
  `GovernanceSeal` closes it: an HMAC over the head with a key the log cannot
  reach, so a truncated log presents a head no seal covers. An unsealed log
  reports **unanchored, not clean**, because "nobody ever called `seal()`" and
  "everything checked out" must not look alike.

### W4b — Governance wired into the execution path

- Every `BaseExecutionAdapter` requires a guard; constructing one without
  refuses. No venue call is reachable without a per-call verdict.
- The venue receives the **governed** value, and the constitutional cap is
  checked *after* the clamp.
- Contract split into `schemas/governance.py` to preserve the
  community→kernel boundary. Documented in `ARCHITECTURE_PLANES.md`.

### W5 — Certification Firewall · **`LANDED`**

- `core/quant_statistics.py`: purged/embargoed k-fold, CPCV, PSR, DSR, PBO
  (CSCV), Bonferroni, Benjamini-Hochberg. Stdlib only, every formula cited.
  `normal_ppf` round-trips to 1e-16. PBO calibrated: **0.49** on pure noise over
  120 seeds, **0.00** on a real edge, **1.0** for in-sample-only.
- `StrategyRegistry`: no sign-off without a verdict, validator ≠ approver,
  adaptation resets evidence, recorded verdicts immutable, rejection reachable
  from every state.
- `core/backtest.py` + `CertificationEvidence`: the cost, capacity, stress, and
  execution checks are **derived from numbers**, replacing four booleans a
  caller could simply assert. Capacity measured via the square-root law.
- `core/contamination.py`: look-ahead detected from `available_at` versus
  `decision_time`, plus **cross-sectional panel leakage** — a failure no
  per-row check can see, where every row is correctly timed but the *set* of
  rows available encodes the future. Survivorship detected as an **absence**
  via the corporate-action history, which reaches superseded identities.
- **A detector that never ran reports `None` and fails.** This is what closed
  the goal: previously `look_ahead=False` was a promise. Now skipping the
  detector cannot pass by default — the same class of fix as refusing a
  backtest whose net and gross series are identical.

---

## 3. Defects found and fixed in this cycle

Sixty-eight. Twenty-seven were found by a test written to assert the property, not by
inspection — the point of writing the test first. The other thirty-seven (#28–#68)
were found by *running the artifact* rather than reading it: building the image,
starting the container, calling the release packager, standing up PostgreSQL and
NATS, model-checking the TLA+ specs, and diffing the frozen architecture against
the tree.

That split is the finding worth carrying forward. A green Python suite says
nothing about whether a Dockerfile flattens your package layout, whether your
interpreter was the one the code actually has to run on, whether a second
process can see what you wrote, whether the specification you shipped is the
one the model checker accepts, or whether a dashboard is showing you numbers
anyone measured. Every defect from #28 on was invisible to the suite — not
because the suite was weak, but because the suite could not see those
dimensions.

**#42 is the sharpest version of that.** A 92.6% benchmark accuracy sat in the
product's own UI, in a view that called no endpoint, while the API it needed was
implemented, typed, and served. Nothing in CI could catch it: the backend tests
passed because the backend was honest, and there are no component or view tests
in the frontend at all. **An honest backend does not make an honest frontend**,
and a suite that only tests the former will never notice the latter.

| # | Defect | Consequence had it shipped |
|---|---|---|
| 1 | Split adjustment direction inverted | Pre/post-split prices did not reconcile |
| 2 | Adjustment relative to observation, not anchor | "Adjust to what?" unanswerable; results depended on which rows loaded |
| 3 | Chained splits accumulated Decimal rounding | A split chain drifted from the exact ratio |
| 4 | `MERGER`/`SPINOFF` missing from terminal actions | An acquired listing stayed `ACTIVE` in the master |
| 5 | `zip(ordered, ordered[1:], strict=True)` | Every `TemporalInstant` raised on construction |
| 6 | Only the first clamp rule fired | Two configured limits, one enforced |
| 7 | `evaluate()` then `authorize()` evaluated twice | Two audit entries per order |
| 8 | `communities/` imported `kernel/` | Plane manifest violated (caught by the existing test) |
| 9 | Purging deleted the entire post-test tail | 80 of 80 training rows removed on fold 0 |
| 10 | PBO relative rank oriented backwards | Best in-sample *and* out-of-sample scored as worst |
| 11 | BH scanned from the top and broke early | Rejected nothing even at p=0.001; wrong hypotheses rejected |
| 12 | `expected_max_sharpe` accepted `n_observations` and ignored it | A parameter that looks load-bearing and is not |
| 13 | `SurvivorshipReport` exposed `is_clean` where the sibling type exposed `clean` | Callers would branch on concrete type to ask "was this clean?" — one place would get it wrong |
| 14 | `_statements` split DDL on every `;`, so a `CREATE TRIGGER` body became one fragment per inner statement | Latent in shared migration infrastructure; surfaced the moment a migration needed a trigger, and reported as `incomplete input` far from the cause |
| 15 | `verify_chain` compared the recomputed head to the *live* guardian's head | A log read back from storage could never verify — the read side was unusable before there was anything durable to read back |
| 16 | `register_deny_rule` defaulted `rule_id="deny"`, producing the reasoning `"denied by deny"` | An audit entry that names nothing; a reader would need a lookup to learn why a call was refused |
| 17 | `PlaybookRouter.select` discarded each `ConditionMatch` and emitted a generic "nothing matched" | Collapsed "the observation was missing a field" into "the regime did not match" - opposite repairs, and the caller had to re-evaluate every condition in the latency path |
| 18 | `build_verdict` took `regime_decomposition: bool` and believed it | A strategy could certify as regime-aware on the strength of a boolean - the same class of self-assertion the contamination detectors had just removed |
| 19 | Verdicts were recorded without their evidence, and `publish` accepted a hand-written `action` | The position size reached the market with no measurement behind it; a strong verdict could be paired with any convenient numbers at publish time |
| 20 | Sink-first write ordering with the fallible step after it | An illegal transition would have left a phantom event in a log that cannot un-write — resume would then honour a programming error as durable history; fixed by pre-checking legality via `check_transition` before touching the sink |
| 21 | `CounterfactualStore.resolve` left the superseded original in the open set | A resolved counterfactual would appear both as open and as history — the exact double-counting the append-only discipline exists to prevent; `open_items()` now excludes superseded ids |
| 22 | Outbox event mutated after construction to add the authorization | Stored an event that failed its own `payload_hash` check on read — the hash doing its job against its own author; the event is now rebuilt with the authorization included so the hash vouches for the verdict too |
| 23 | CUSUM break estimate pointed at bar 0 | Evidence runs were never reset across the burn-in boundary, so every delay was overstated by the whole burn-in length; the run now starts when calibration ends |
| 24 | Noiseless step scored confidence 0 | The 0/0 contrast fallback pointed the wrong way — a perfect step is maximal evidence, not minimal; infinite contrast now maps to 1.0 |
| 25 | Partial-lane `ParityReport` constructor omitted two required fields | The happy-path constructor was never executed before handoff; absorbed after review and fixed on arrival — partial work is unverified work |
| 26 | Identical claim re-record raised instead of no-op | Pipelines replay, and twins would double-count judgments; deliberately changed to the OMS idempotency-key semantic, with the old pinning test rewritten to the new contract rather than deleted |
| 27 | Outbox event rebuilt via `model_copy(update=...)` stored an empty `payload_hash` | Pydantic v2 `model_copy` does not run validators — verified empirically after assuming otherwise. Every order persisted with an unattested hash until the financial invariant caught it. Hash now recomputed explicitly at the rebuild site. Companion lesson: a stash-based bisection is unsound on a branch with interdependent uncommitted work — reverting adapters without the replay runner that depends on the new kwarg produced a failure misattributed as pre-existing |
| 28 | Docker image could never build: `COPY aios api … /app/` flattened every package into one directory | Docker treats a multi-source COPY as merging each source's *contents* into one destination, so `core/`, `kernel/` and `scripts/` all landed as `/app/*.py`. `import core` could not resolve. The symptom (`ModuleNotFoundError` after a *successful* `pip install`) reads like a packaging bug and is not one — the wheel was empty because the layout it was pointed at did not exist. One COPY per package, each with its own destination |
| 29 | `communities/c5_execution/execution.py` could not be imported on Python ≤3.13 | PEP 649 made annotations lazy by default in 3.14, and the local venv is 3.14, so an annotation naming a `TYPE_CHECKING`-only import never evaluated and the bug was invisible locally. On 3.12 — declared supported, and what CI and the image run — it raised `NameError` at class-definition time. **The most dangerous defect in this cycle, because the local suite was green throughout.** Both annotations now quoted; `tests/test_python_version_compat.py` pins the property structurally rather than trusting one interpreter |
| 30 | `.dockerignore` and the release packager both excluded `CONSTITUTION.md` | Both exclude prose, and `core/constitution.py` verifies the file against a SHA-256 pin at boot. An image or archive without it cannot enforce the pin — skipping the check is the failure the pin exists to prevent. Same root cause in `.gitignore` for `data/golden`, which the Dockerfile `COPY`s and `docker-compose` mounts. Each was found by *running* the thing, not reading it |
| 31 | `should_exclude` returned on the first pattern match, so negations were dead code | `*.md` preceded `!README.md`, so README.md — named in `INCLUDE_FILES` — has never shipped in a release archive. Matching is now order-independent with negations applied last, and a negation matches an exact path rather than a prefix, so `!README.md` cannot quietly re-include `docs/README.md` |
| 32 | CI's secret gate matched ordinary English | `grep "sk-[a-zA-Z0-9]"` matches `risk-bot`, `risk-governor` and `task-tier` — firing on ~45 lines of ordinary source in files tracked on `master`. A gate that cries wolf on a hundred false hits is a gate nobody runs, which is worse than none because it *looks* like a check that is not running. Pattern now requires a provider prefix and a 32-char base62 body |
| 33 | Migration v4 could never be applied to PostgreSQL | The sequencing and chain triggers were `WHEN` clauses, and PostgreSQL forbids a subquery inside a `WHEN` condition (and requires it parenthesised). Both checks *are* subqueries, so the form is unrepresentable, not just malformed — every such `CREATE TRIGGER` was a syntax error. **The append-only, sequencing and chain guarantees the ledgers document have never run on the production tier.** Found by bringing up the project's own compose file and running `aios db migrate`. Checks moved into plpgsql functions |
| 34 | Every seal on the Postgres tier failed its own audit | Seals are HMACs over an ISO timestamp. SQLite stores TEXT and returns that string; PostgreSQL stores TIMESTAMPTZ and returns a `datetime`, and `str(datetime)` renders a space where `isoformat()` renders `T`. The recomputed HMAC covered different bytes, so `audit()` reported tampering that never happened — on the component whose only job is detecting tampering. Normalised on read (`ts_str`) rather than re-signed per dialect, keeping one canonical string on both tiers |
| 35 | An idempotent claim re-record deleted the claim it absorbed | `record_claim`'s unique-violation handler called `rollback()` after psycopg's `transaction()` block had already rolled back the failed `INSERT`. The second rollback reached the enclosing transaction and discarded the first successful insert: the call returned the correct claim and then removed it. It also read through a plain cursor where a mapping was required, so `dict(tuple)` raised `ValueError` before it could even compare |
| 36 | `identity_digest()` made the same belief hash differently per tier | `NUMERIC` declares a scale, so PostgreSQL returns `Decimal("0.01")` as `Decimal("0.010000000000")` while SQLite returns it untouched. `upsert()` uses the digest to decide a re-assertion is a no-op, so on the production tier the no-op never fired, the re-assertion fell through to the insert, and the PK refused it — a nightly feed reload crashed on Postgres and worked on SQLite. Decimals normalised by value; distinct values still hash distinctly |
| 37 | Three "parity" tests were SQLite-only in effect | They passed the literal `"t"` as a recorded timestamp. SQLite accepts it in a `TEXT` column; PostgreSQL rejects it in a `TIMESTAMPTZ` one. So the tests meant to compare the tiers exercised only the reference tier — hiding precisely the divergence they exist to catch. **The lesson is structural, not local: a parity test that cannot run on one tier silently stops being a parity test** |
| 38 | No durable sink actually committed | All four PostgreSQL sinks wrapped their INSERT in `conn.transaction()` and returned without committing. `transaction()` brackets a statement; it does not commit it. With autocommit off, each row stayed inside its connection's open transaction — visible to that store's own reads, invisible to every other connection, and discarded on close. The playbook store's docstring promises "a restart loses the router's memory, not its policies"; a restart lost every policy. Every in-process test passed because every in-process test read through the same connection that wrote — **the one vantage point that cannot observe this defect.** `tests/test_pg_durability.py` counts rows from a second connection |
| 39 | Every TLA+ property was mis-shaped for TLC, and two were unsound | G220 recorded that TLC "could not be run here" because no JVM existed. True, and avoidable — TLC runs in a container, so no Java toolchain needs admitting to a Python project. Running it refuted the specs: an `INVARIANT` must be a state predicate (four were not), `[]` demands an action of the form `[A]_v` (two were not), and **"every event eventually reaches an ending" is simply false** — because `Spec` uses `[Next]_vars`, an infinite stuttering trace is legal, so no liveness property holds. That claim is removed rather than repaired. Replaced by what a bounded-retry queue actually guarantees and TLC can check: retries are capped. `ENABLED` replaced the terminality claims, which is also stronger — it covers an action added later |
| 40 | A vacuity check found `HashBindsKey` weaker than it looked | Removing the `hashOk` guard from `FailPermanent` left it satisfied, because that action never sets `applied`. It asserted a mismatched event is not applied *if it happens to be dead lettered*, not that it can never be applied. `MismatchIsNeverApplied` carries the real weight. A second mutation (requeueing a dead letter) was caught by `DeadLetterTerminal`, confirming that one is not vacuous. **A property that cannot fail is not evidence** — both mutations were reverted after the check |
| 41 | The kill switch never cancelled open orders | `CONSTITUTION.md` §2.2 mandates **cancel → flatten → halt**; the code did two of the three. `DurableOrderManager.cancel` and `cancel_all_orders` both existed and both were reachable from the runner (`self.oms`, built at `replay_runner.py:409`) — nothing invoked them. An order placed before the emergency could still fill, `apply_fill` has no emergency guard, and `locked_out` gates only *new* submissions (`execution.py:130`). So the system could take on exposure after an emergency stop. Found by reading §2.2 against the implementation, after the architecture named `kill switch` as a required assurance target that had no spec |
| 42 | `ModelGovernanceWorkspace.tsx` rendered a wholly fabricated registry | Four invented models, weights hashes, latencies, context lengths, evaluation dates, a system prompt hash, a sampling temperature, and **"BENCHMARK ACCURACY: 92.6% AVERAGE"** — with no backend call behind any of it. `modelsApi`/`evaluationsApi` existed, were typed, and were served on two routes; neither was called. That is a direct breach of architecture §11 (a claim needs 14 companions), of `core/claim_gate.py` (the implementation of exactly that rule), and of §3 Honesty Law 1. The backend was already honest — `models_registry_view` returns `{available: false, models: []}`, documented *"never a fabricated roster"* — so the lie was entirely client-side, which is the more expensive kind: a lying server can be diffed, and a lying client looks exactly like a working feature. Rewritten to read the endpoint, with `tests/test_model_governance_contract.py` pinning the backend side so a future "helpful" placeholder roster cannot be added silently |
| 43 | The goal registry asserted five dead gates and one artifact that does not exist | The registry is what the project defers to — this file says so: *"where the two disagree, the registry and the tests win"* — so a discrepancy in it is not a documentation nit. Five gates on **LANDED** goals named test files that never existed (G010, G170, G110 ×3, G100), and G100's objective read *"RegimeSnapshot ... plus a per-strategy domain of competence"* when the engine has always exposed `RegimeState` and "competence" appears nowhere in the tree. The existing rule only checked the path ended in `.py`, and its docstring said unwritten goals may name missing files — right for BLOCKED work, exactly wrong for finished work. Four gates repointed at the tests that actually own the property; the domain-of-competence gate **deleted** rather than repointed, and the gap recorded as outstanding. Two new derived rules now prevent recurrence: LANDED gates must exist on disk, and CamelCase identifiers in any objective must appear in source. **The second rule generalises a test that already guarded this exact failure mode but hardcoded two goals, so only two were ever checked** |
| 44 | The new registry rule passed its own mutation | `_source_blob()` read every `*.py`, including the test whose docstrings quote `RegimeSnapshot` to explain what it is checking — so reintroducing that name into G100 satisfied the lookup with the rule's own explanation. Found only because the rule was mutation-checked. The blob now excludes `tests/` and `docs/`, as the sibling rule already did, and the docstring records that the exclusion is load-bearing rather than tidiness. The same failure had already appeared twice this cycle as a shipped tautology (`HashBindsKey`, `FlattenPrecedesHalt`) and once as an unawaited coroutine in a passing test |
| 45 | A vacuity harness destroyed the implementation it was testing | The harness ended each mutation with `git checkout -- kernel/playbook.py`, which is correct hygiene when the edits are committed and a deletion when they are not. The competence work was uncommitted, so the first mutation's revert erased every change to the file - the classes, the import, the gate method, the `__all__` entries - and the run then reported the mutation *caught* because the suite failed against a file that no longer contained the feature at all. **A vacuity check that destroys its subject will always report success.** Two changes of method followed: the implementation was committed before mutating, and every mutation now also asserts the suite failed for a reason other than a syntax error, so a botched edit cannot masquerade as a caught mutation. Fourth such defect this cycle after #44, the `HashBindsKey` tautology and `FlattenPrecedesHalt` - which is why the harness itself is now treated as something to verify |
| 46 | TLC found a reconciliation state no snapshot can justify | `CursorCannotDeriveInternalOnly` was refuted with a three-state trace: discover an internal-only execution under `FULL_SNAPSHOT` (legitimate), then switch mode to `CURSOR`. The finding survived, so a CURSOR-mode state carried a finding that mode cannot support. `ReconciliationMode`'s own docstring says a delta "proves nothing about executions it did not mention, so internal-only findings cannot be derived" -- inferring that the venue has no execution the blotter lacks, from a payload that never claimed to list executions, is a **fabricated negative**, and no test asserted it. Fixed by refusing the transition rather than clearing the finding, because discarding a real discrepancy because a query mode changed is the dishonesty the spec exists to catch. Second time a TLA+ spec has found something the Python suite could not, and the sharper of the two: the invariant encodes a docstring rather than a behaviour |
| 47 | Four of the reconciliation invariants could not fail | A mutation check found a disjunction implied by the constructor (a tautology), a biconditional restating a sibling invariant, a structural guarantee dressed up as a check, and a claim about transitions that no TLC form accepts -- `[]` demands an action of the form `[A]_v`, so a transition predicate is rejected; `[A]_v => pred` is rejected as mixing a temporal formula with an action; `ENABLED` over a primed-only action is rejected. All four were replaced or dropped rather than shipped as decoration, and the replacements have isolating mutations that TLC refutes. The spec now states which of its invariants are **not** independently verified: `TypeOK` cannot be broken alone by design, and `NoOpenFindingIsResolved` is implied by `TypeOK` plus the action definitions, so all three mutations that could break it produce states `TypeOK` rejects. Sixth instance this cycle of a check that could not fail (#44, `HashBindsKey`, `FlattenPrecedesHalt`, the unawaited coroutine, the registry rule reading its own docstring, and the harness that destroyed its subject) |
| 48 | G220 claimed four assurance targets it does not model | Its summary named fills, duplicate delivery, reconciliation and failover. Duplicate delivery and the fill sequence **are** covered (Outbox's `DuplicateDeliver`/`AtMostOnceEffect`, OrderLifecycle's `PARTIALLY_FILLED`/`FillMonotone`/`NoPhantomFill`); reconciliation is now modelled; **failover has no specification anywhere**. It appears exactly once in the architecture, as a bare word in the section 3E list -- no scope, no layer, no service, no acceptance criterion, no implementation. Same reasoning that declined Disaster Recovery: one bare mention is not a specification, and modelling it would mean inventing the requirements. Corrected, with the reasoning **recorded rather than dropped**, because a corrected summary with no reason invites the next reader to re-add failover from the list alone, which is how it got there. Its gate also read that a specification exists for two named things, which cannot fail: presence is not a property, and a file containing a single character satisfies it. Rewritten to assert the invariant-to-cfg correspondence and the taxonomy coverage |
| 49 | A complete SSE implementation on both sides was never started | `api/server.py` has served `/api/v1/stream` since G210, emitting an executive snapshot every two seconds, and `frontend/src/api/stream.ts` has implemented a correct, authenticated, reconnecting client since the same commit — using `fetch` + `ReadableStream` rather than `EventSource` precisely because `EventSource` cannot send an `Authorization` header. Nothing ever called `startStream()`. Not a registry overclaim: G210's stated deliverable is one correlation chain across eleven stages, which is delivered and tested by `tests/test_trace_continuity.py`. This is unconsumed surface, and the expensive kind — a feature that looks finished because both halves exist and type-check, while every view polls. Now consumed by `useLiveExecutive`, with the load-bearing assumption **verified rather than assumed**: a probe against a live server confirms the stream's `executive` has an identical field set to `GET /api/v1/executive` with every value agreeing, which is what allows a frame to be used with no translation layer |
| 50 | A malformed-frame guard was imported and never called | `useLiveExecutive` imported `frameExecutive` — the function that stops a malformed frame replacing a good value with `undefined` — and then never invoked it, because the guard had been written before the state it guards and the wiring was superseded. `tsc` caught it as an unused import. Worth its own row because the shape is specific and easy to repeat: an import that documents an intent the code does not carry out reads as protection and provides none. The consequence was concrete — `undefined` on screen where a number belongs reads as a measurement of zero, which is the exact shape of defect #42 in miniature. A second pair of unused setters went with it, and their removal mattered as much: holding a second copy of a server value is how a client comes to disagree with its backend |
| 51 | The dependency lock gate asserted one machine's resolution reproduces everywhere | `lock_dependencies.py --check` compared the committed lock against a closure recomputed from `importlib.metadata`, so it asked "are the versions pip resolved on THIS machine the versions in the lock" -- which for a lock means nothing, since a lock's job is to *define* the environment rather than describe one. CI made it worse: the step installed **unpinned** ranges (`psycopg[binary]>=3.3,<4`, `nats-py>=2.15,<3`, `ccxt>=4.5,<5`) precisely so the gate could recompute the closure, then asserted the result equalled one Windows machine's resolution. Every release anywhere in the 52-package closure broke it, and it printed the single word "stale", so there was nothing to act on. It was left red and described as "structurally environment-dependent by construction" -- true, and curable. **The lock was never the problem:** measured before any change, the lock and a fresh resolution agree on all 52 packages with the same set (0 added, 0 dropped) and differ only in 21 versions, and every locked version satisfies its pyproject specifier. The gate now compares the lock against `pyproject.toml`, which does not vary by machine, and the environment comparison survives as `--check-installed` -- a report, not a gate. **The property the old gate could not check at all:** a locked version violating its declared specifier, because it only ever asked whether that version happened to be installed |
| 52 | Two of ten new lock tests passed or failed for reasons unrelated to the gate | Recorded because it is the seventh instance this cycle of a check that could not be trusted, and the first two found in code written specifically to prevent that. `test_all_problems_are_reported_not_just_the_first` appended a duplicate with `text + "packaging==1.0\n"` after `"\n".join(text.splitlines())` -- and `splitlines` drops the trailing newline, so the append was glued onto the previous line as `zlib-ng==1.0.0packaging==1.0`. The duplicate never existed, and the test failed while asserting a property its own setup had not created: a test that reports a failure its setup did not cause sends you to fix correct code. `test_a_locked_version_violating_pyproject_fails` recomputed its digest over the header comment lines as well as the package lines, so the digest never matched and the test passed because of a digest mismatch -- a second copy of the hand-edit test wearing the wrong name. Both were found only because the mutation was debugged through the gate's own return value rather than by reasoning about it |
| 53 | The lock gate's headline claim was false for extras-provided packages | `--check` passed with `psycopg-binary` deleted from `requirements.lock`, the digest recomputed so the lock was otherwise internally perfect: `requirements.lock agrees with pyproject (51 package(s), digest c86072dce399)`. Found by an independent review, then reproduced end to end before changing anything. The cause is a one-line inconsistency between two functions in the same module: `declared_requirements` contributes a `base-extra` root for `psycopg[binary]`, so GENERATION resolved the extras-providing distribution, while `declared_specifiers` -- which drives the presence and specifier checks -- recorded only `requirement.name` and never looked for it. The two halves disagreed about what pyproject declares and the gate consulted one, so the docstring's claim that "every distribution pyproject declares is present in the lock" was false for exactly the distributions extras provide. It matters more than an ordinary missing package: this is the database driver's binary, so a lock without it installs a psycopg that cannot connect to anything, and the lock is what a deployment installs from. Fixed by contributing the extras providers as presence-required with NO invented range -- pyproject states `>=3.3,<4` for `psycopg` and nothing for `psycopg-binary`, so inheriting the parent's range would invent a constraint pyproject does not declare and pass a `psycopg-binary` incompatible with the psycopg beside it. **AND IT SURVIVED A MUTATION CHECK**, which is the general form: every property I chose to mutate turned the suite red, so the check proves the properties I thought to attack are load-bearing and says nothing about the ones I did not think of. The coverage of one's imagination is not a property, and that is now stated as a rule rather than as an anecdote |
| 54 | The stream's provenance label lied, in the mirror direction | `reconcileExecutive`'s stale-frame branch returned `source: "poll"` for a value the SSE stream delivered, and `SystemHealthWorkspace` renders that as **FALLBACK POLL**. A console parked in `auth_required` with no poll yet was therefore told its state came from a fallback poll that had not run. Found by an independent review. The commit that introduced this module says the feed status and the snapshot's provenance are "never merged", and that claiming live delivery for a polled value is the dishonesty to avoid -- this is the mirror of that dishonesty, in the same commit that named it. The type was the cause: `"stream" \| "poll" \| null` has no way to say "the stream said this and the stream has since stopped". A fourth member `stream_stale` is added rather than overloading either existing one, because "polled" and "stale" are different facts: the first says where a number came from, the second says how much to trust it now. **The paired test that should have caught it asserted only `expect(view.source).not.toBe("stream")`**, which is satisfied by `"poll"` and by anything else -- a negative assertion cannot distinguish two wrong answers from each other, and the claim is about identity. Now asserted exactly, from both directions. Found by an independent review while the mutation check was green, and the eighth time this cycle that the discipline which was supposed to catch this did not |
| 55 | Three statements in the tree that were untrue, or could not fail | All three from the same review. (1) `test_formal_assurance.py` asserted `sorted(SCOPE_RANK, key=-rank)[0] is max(SCOPE_RANK, key=rank)`, which holds for **any** mapping -- demonstrated on the real table plus two arbitrary ones, one with ties and one all-equal. It asserted nothing about the spec, which is what its docstring claimed it pinned, and its `widest_first` binding was left orphaned when it was removed. (2) `Reconciliation.tla` carried the header and body of a deleted property, including the normative sentence "the resolution ledger only grows, and no action can bring a closed finding back into the open set", attached to nothing -- while `Discover` sets `resolved' = {}` and therefore **shrinks** the ledger, so after Discover -> Resolve -> Discover a resolved kind is re-derivable. A spec asserting a guarantee its own machine contradicts is worse than a spec that is silent. Removing the orphaned prose also deleted the independently-verified scope note, which a drift test pins; the test caught it and the note was restored, which is that test doing its job. (3) the lock docstring disclosed ONE narrowing when there are three: transitive-closure completeness, **added** packages (the old byte-compare caught anything no root reached, so an invented package with a correct digest now passes), and transitive version **authenticity** -- 41 of 52 locked packages have no range pyproject states, so `cryptography==3.0.1` passes despite known CVEs. All three are now stated, with the blast radius: nothing installs from the lock, so the exposure is the SBOM and audit surface |
| 56 | The checkpoint's headline verification figures were twelve commits stale | The "Last verified" block read `6f9ff81`, 117 commits, 489 tracked files, `1539 passed` -- every figure from before P1. Nine commits of work were added to the defect table while the block kept describing the tree from three items earlier: the domain of competence, the reconciliation spec, the SSE consumer and the lock-gate rewrite all landed underneath a verification line that claimed none of them. The file's own rule is that a defect table whose prose and split disagree is this same drift, and the verified block is the one thing a reader is certain to check first, so a stale headline is worse than no headline: it is trusted. **Rewritten from measured values**, with the commit hash, counts and suite figures read from the repository and the measurement file rather than retyped, and a post-condition that refuses to write any figure it could not obtain. The with-services figure is kept and explicitly labelled as measured before these additions, because quoting a stale number as current is the same error in the other direction. Recorded because the discipline that was supposed to prevent it -- update the checkpoint in the same change -- was applied to the defect table nine times and to the verified line not at all |
| 57 | The resolver iterated `registry.artifacts` as if it were a property | `StrategyRegistry.artifacts` is a plain method (`def artifacts(self) -> list[StrategyArtifact]`), so the loop iterated a bound method and raised `TypeError` on first real use. The signature is textually identical to a property's getter, and an earlier probe printed the getter's source without the decorator, so reading it correctly and calling it correctly are different acts. Found by a probe, before any test ran — but only because the probe was executed rather than reasoned about. Seventh instance this cycle of the calling convention being inferred from a signature. The post-condition that now guards it CALLS the function on a real registry and reads the declarations back, because a grep for `registry.artifacts()` would be satisfied by the very text it is meant to verify |
| 58 | Production derived competence from a snapshot of an empty registry | `create_kernel` and `build_playbook_router` read the registry once, at construction, and passed a finished `StrategyCompetence`. The registry is empty at boot — strategies are registered, backtested, certified and approved while the kernel is already running — so the snapshot was always empty, every strategy was permanently `CompetenceNotDeclared`, and **no playbook could ever be admitted**. Five tests in `tests/test_playbook_composition.py` failed against it, and their fixtures were innocent: they certify with a real `regime_performance` decomposition, exactly as production requires. The gate was not wrong; it was reading a registry from before time began. Resolution is now lazy, at admission, which is sound as a one-time check precisely because a recorded verdict is immutable — were that ever false, admission-time checking would have to move onto selection. **The second half is the part worth keeping.** My own test for the composition root observed this behaviour and asserted it, with a comment calling it “the point worth asserting”. I had seen the defect, disliked it, and written it down as a finding. A test that pins a defect is worse than no test, because it makes the defect look like a decision — and a mutation check would not have caught it, since pinning the behaviour is precisely what the test was for |
| 59 | “Measured in every regime and competent in none” was reported exactly as “never measured” | Both produced a byte-identical `CompetenceNotDeclared` reading “has declared no domain of competence”, and neither named the regimes. The one case where the measurement *is* the answer got the least informative message, and the message pointed at hand-declaring a competence — the one remedy `competence.py`'s own docstring calls circular. Cause: the derivation raised its own `ValueError` only when nothing was measured; when everything was measured and all of it failed, the `DomainOfCompetence` constructor raised instead, and the resolver's single `except ValueError` could not tell the two apart. Reachable and not exotic: regime slices are classified OPERATIONAL, so a strategy clearing deflated-Sharpe, PSR and PBO and then losing money in every decomposed regime is `CERTIFIED_WITH_LIMITS` and tradeable. Fixed with a distinct error, deliberately not a `ValueError`, so the existing handler provably cannot swallow it. Found by independent review, reproduced by execution before the fix, per the rule defect #53 left behind |
| 60 | Nothing stopped a recorded verdict being re-pointed at a wider one | `record_verdict` always refused a second verdict, but only through the METHOD. `StrategyArtifact` is a mutable pydantic model, `verdict` a plain field, and `StrategyRegistry` a public attribute of the kernel — so `artifact.verdict = <wider>` reassigned it, and `competence_resolver` reads that field. Demonstrated before the guard: a strategy recorded as **losing money in crisis** became competent there, silently, for every playbook already admitted. Worse than it looks, because the two facts are treated differently downstream on purpose: `register()` re-asks the oracle about certification on EVERY selection “because a verdict can be revoked by the oracle at any instant”, while competence is checked ONCE at admission, justified by the claim that a recorded verdict is immutable. Competence would have inherited the verdict's mutability without inheriting the re-check, and the justification was a docstring. Enforced with `__setattr__` rather than `validate_assignment`, because a field validator is handed the new value and cannot know whether one was already recorded |
| 61 | Two more hardcoded copies of the check prefix survived the constant introduced to remove them | `kernel/playbook.py:441` (on the production publish path) and `:1049` each built `regime_sharpe:` from a literal, immediately after `REGIME_CHECK_PREFIX` was created precisely to stop that. Rename the constant and certification plus `competence.py` stay in agreement while `build_measured_playbook` and `propose_candidates` silently stop finding their checks — and the former fails CLOSED, so it would read as “this strategy does not work in that regime” rather than as a broken join. Both now import the constant, and the pin test was widened from one file to every module in `kernel/`. **The test was what made this survive a green suite**: it counted literals inside `strategy_registry.py` alone, so it certified a coupling still broken twice over. It now walks the AST for string constants rather than counting text, because docstrings legitimately quote `regime_sharpe:<regime>` while explaining it, and a text count flags documentation of a rule as a violation of it |
| 62 | The fix for #59 was verified at the layer it was written, not the layer it was for | Both all-invalid tests called `competence_from_verdict` **directly**. The defect was never in that function — it raised correctly and the message was right; the defect was that `competence_resolver` collapsed its raise into the same `None` the absent-decomposition case returns, and no test passed an all-invalid verdict to the resolver. Widening `except ValueError` to `except Exception` — the tidy-up a future editor would plausibly make — restored the swallowing and left the suite green, so the hole was found by mutation rather than by reading. The gap was in the SEAM between two functions, which is where the bug actually was. Two tests now drive the case through the resolver, in both directions, because a change that made it propagate everything would also pass the first. **The general form, and the seventh time this cycle**: a green suite plus a mutation check reporting 6 of 7 still left the load-bearing property untested |
| 63 | `load_router` rebuilt the router with the Layer 9 gate silently off | Three `PlaybookRouter` construction sites existed. Two were wired with derived competence when the gap was closed; this one was missed, and it is the one most likely to be reached for — the function whose entire docstring is about production restarts, rebuilding from the durable store after a process dies. Worse than a missing parameter: `load_router` populates `router._playbooks` **directly** rather than through `register()` — deliberately, since the store is the source of truth after a restart — and that insertion meant `_check_competence`, which `register()` calls, ran on **no path through the function at all**. So the obvious fix, adding a `competence=` parameter, would have been **inert**: a caller could pass a fully enforcing resolver and receive none, with nothing to indicate it. Found by reading the function while checking an independent review's *declined-to-judge* list, which had it right on the narrow point (nothing in production calls it) and the wrong question. Both halves now present, with the check called explicitly, and the `None` default documented as disabling the gate rather than left to be assumed. Not wired, because nothing calls it: inventing a restart path would be the duplication `docs/DEPENDENCY_POLICY.md` refuses, so the parameter is here and the gap is named. Three mutations aimed at it and all three caught, including the check moved into the `else` branch — the shape a careless edit takes, and one that would leave every “a playbook was refused” test green |
| 64 | Running the documented SBOM step left the tree dirty | `scripts/sbom.py` writes `sbom.json` to the repository root by default, and it was not in `.gitignore`, so a verification step left an untracked file behind. Found by re-running the steps the block asserts rather than copying its previous figures forward — the same act that caught two wrong figures in the same pass. It matters more than untidy: the block asserts "working tree clean" as a measured fact, and **a cleanliness signal that the documented procedure breaks is not a signal**. Ignored rather than committed, on the dependency policy's own terms — the SBOM is fully derived from `requirements.lock`, with `test_sbom_covers_exactly_the_lock` asserting the component set matches and `test_sbom_is_byte_stable` asserting the output is reproducible byte for byte, so a committed copy carries no information the lock does not. The counter-argument was checked rather than assumed: `package_release.py` does not reference it, and the archive ships `scripts/sbom.py` and NOT `sbom.json`, so the means of production already travels and the product is rebuilt. Verified by running the step and asking git, not by reading `.gitignore` |
| 65 | G230's `LANDED` summary named five deliverables the tree does not contain | Its summary read "OPA/Rego policy, sandboxed AI zones, OpenBao secrets, SBOM, vulnerability scanning, and signed releases" while its OWN notes said "OPA was deliberately replaced by signed policy bundles" and listed live scanning among things "explicitly deferred, not pretended". The registry contradicted itself, which is the defect #48 was closed for on G220 **in the same commit that corrected G220's summary**; G230 was missed. Counted first-party only, since the initial count was polluted by an unrelated untracked `.vt-study/` directory: policy bundles present (4 files), CycloneDX present (4), SHA256 manifest present (2), **cosign/sigstore zero**, one prose mention of a scanner and none that runs. Rewritten to be true in three directions -- shipped, absent, and UNVERIFIED -- because signing is applied in CI, which cannot be executed here, so calling it unimplemented would have been its own false claim in the opposite direction. **The fix for this row then broke a test**, which is the part worth keeping: explaining the unverified case, I wrote "no GitHub activity is permitted" into the summary, and `test_goals_do_not_name_artifacts_the_code_lacks` failed -- correctly, since a goal naming an artifact the code lacks is the defect this row is about. Loosening that test to tolerate a mention in a negative context was the wrong repair: a rule that cannot tell a claim from a disclaimer is not a rule. Said the same thing without the noun instead. An audit found one defect, its repair produced a second, and the suite caught the second |
| 66 | The document's last line said the work was uncommitted | "**Nothing is committed.** 49 files are modified or new on `feat/command-center-ui` with a clean tree otherwise. Commit and review before proceeding further." Reality: 139 commits on `main`, 497 tracked files, clean tree, and that branch 0 ahead and 38 behind. It was the **last line of the document**, which is where a skimming reader lands, and it was the single most misleading sentence in the file -- a reader would have believed the cycle's work was unsaved and started by committing it. Found by an independent audit of the document against the tree rather than by reading it, which is the point: I had read this file dozens of times this cycle and never noticed a sentence that was wrong in the most consequential direction available |
| 67 | A figure was corrected in the headline and left wrong in the body | KillSwitch's TLA+ search depth was given as 4 in section 4 and 11 in the verified block. I corrected the block at `899f442` and left section 4 alone -- **the same incomplete correction as #63, one commit later**, and the second time in a row, which is what makes it a shape rather than an accident. A figure corrected in one place and not another is worse than a figure wrong everywhere: a reader who finds the corrected one concludes the document is reliable and stops checking, and the stale copy is the one that survives grep. Found by the same audit, along with `Reconciliation` being missing from section 4's spec list while named in the block above |
| 68 | Ten test counts in this document were never true, and nothing pins any of them | Registry validator 17→19, authority-chain 61→54 (61 was 54 plus 7 from a file it did not name), security master 46→47, corporate actions 18→19, PIT fabric 20→19, claim ledger 22→23, experiment sink 30→34, playbook derivation 33→35, frontend decisions 18→20, and "Of 1750 tests in the tree" where the tree collects 1700 without a live backend and 1751 with one. Recounted with `pytest --collect-only`, which sees parametrised tests a `def test_` grep cannot, so a grep would have been wrong in the other direction too. Two of the ten were found by ME, not the audit: the frontend count I had myself made stale, and a count my own script asserted from memory that the document never claimed. **The general form: an inventory of figures in prose is unpinned data.** Nothing fails when one drifts, so every one of them is a small lie that survives indefinitely, and the whole class collapses at once when someone finally runs the inventory against the tree |

Three of these deserve emphasis. **#10** is the class of bug that makes a
statistic meaningless while looking perfectly healthy: PBO returned 1.0 for
both pure noise and a genuine edge, because PBO counts `λ ≤ 0` and the rank
was oriented so that winning produced a large *negative* logit. **#12** is
subtler — a parameter in a signature that does nothing is worse than a missing
one, because every caller reads it as load-bearing. **#29** is the one worth
remembering longest, because it was invisible to the only test suite anyone was
running: the local interpreter was 3.14 and the deployed one was 3.12, and a
language change between them decided whether the module imported at all. The
lesson is not "add a quote" — it is that a green suite certifies the
interpreter you ran it on, so a compatibility claim needs a test that does not
inherit the local runtime's opinion. **#38** is the same shape and the most
expensive instance: every durable ledger reported writes that were never
committed, and every test passed, because every test read through the same
connection that wrote. A suite can only certify what it can observe, and one
connection cannot observe durability. **#40** is the corrective to the whole
exercise: a property that cannot fail is not evidence, so the model checker was
used to try to break its own invariants, and one of them did not break.

---

## 4. Remaining, by workstream

Each entry names the specific gap, not the goal title. `docs/goals/goals.json`
carries the same information per goal plus its blocker text.

### W0 — G190 Statistical Claim Gate · **`LANDED`**

`evaluation/harness.py`: a deterministic runner behind the fixed gate
contract — seeded suites, version pins refused when absent, errors counted
against coverage but excluded from the pass-rate denominator
(`min_coverage=1.0` default, so a 1.0 rate with any error still fails),
empty suites refused (0/0 is not 100%), every result carrying a Wilson
interval via the existing `normal_ppf` helper (method recorded, no quantile
logic reimplemented), `to_gate_claim()` covering all 14 gate fields. Failed
executions are recorded as errors, never silently dropped — dropping them
inflates the pass rate, which is the exact fraud the gate exists to prevent.
No remaining gaps in the goal's own gates; the `EvaluationResult`→`Claim`
ledger mapping is an explicit unmade policy decision, recorded as such
rather than silently coupled.

### W1 — G020 Security Master · **`LANDED`**

- `PostgresSecurityMasterStore` mirrors SQLite statement-for-statement with a
  mechanical `?`→`%s` rewrite, so the two dialects cannot drift into two
  different queries wearing the same name. The row mappers already accepted
  native datetime/date/Decimal objects, which is what makes the mirror exact.
  Production PG never migrates on open (`auto_migrate` is opt-in for tests).
- `tests/test_security_master_parity.py`: every behavioural assertion runs on
  both tiers — round-trip exact decimals, supersession, ticker-reuse
  separation, conflicts, action immutability, windowed enumeration, delisted
  visibility, `as_of`/`as_known`/ISIN. The PG leg runs wherever
  `AIOS_TEST_PG_DSN` is set and skips otherwise; the v3 DDL cross-checks
  (tables, indexes, triggers, columns) run hermetically everywhere, so a
  schema fork fails without a database.
- **The PG legs have now actually been exercised**, and they were not healthy.
  Bringing up the project's own `docker-compose.test.yml` (Postgres 16 on
  loopback:5433, NATS JetStream on :54222) and running the parity suites for
  the first time found four defects that no SQLite-only suite could see, because
  each is a dialect divergence rather than a logic error — see defects #33–#36.
  Migration v4 had *never applied* to PostgreSQL on any machine. Every seal on
  the production tier failed its own audit. An idempotent claim re-record
  deleted the claim it was absorbing. `identity_digest()` made the same belief
  hash differently per tier, so a nightly feed reload crashed on Postgres and
  worked on SQLite. The parity tests also passed a literal `"t"` as a timestamp,
  which SQLite accepts and PostgreSQL rejects — so three tests meant to compare
  the tiers were in effect SQLite-only, hiding exactly the class of divergence
  they exist to catch. `tests/test_dialect_divergence.py` now pins each of these
  hermetically, so the next one fails without a database in the loop.
- Seed ingest (`core/seed_ingest.py` + `data/seed/bootstrap_v1.json`): a
  versioned-bundle importer. Validation through the domain models completes
  before the first write — one bad row records nothing. Identities upsert,
  actions are immutable, re-ingest reports skips. The shipped corpus carries
  eight listings and nine actions with per-record provenance, including a real
  delisting (TWTR) for the survivorship detector and a symbol change (FB→META)
  with stable identity. No remaining gaps.

Two defects closed on the way, both found by the seed work rather than by
inspection:

- **The store wrote rows the model refused to read.** Same-instant
  supersession (a backfill asserting two revisions with one recorded
  timestamp) closed the prior row with `recorded_to == recorded_from`, which
  the model rejected — so first ingest succeeded and re-ingest crashed on
  read-back. Zero-duration recorded intervals are now an empty truth, not a
  contradiction (strict inversion still refused); the pinning test asserts
  both directions.
- **`upsert` crashed re-asserting superseded history.** The no-op covered
  only the current belief, so a nightly-style full-history reload died on the
  first closed row with a PK conflict. Re-assertion of an assertion already
  in the log is now a no-op at any depth.

One observation recorded for G140 rather than fixed here: `resolve()` orders
by revision only, so with two current rows for one ticker the tie-break is
unspecified — asserting either outcome would make the parity suite pass per
tier or per run. Whether resolution should prefer live listings belongs to
the authorization envelope, which is the first consumer that must choose.

### W2 — G030 PIT Data Fabric · **`LANDED`** · no remaining gaps (hot-store policy out of scope)

**Dataset versions are durable** (`core/dataset_version_sink.py` + migration
v7): one event per REGISTERED/VALIDATED/ACTIVATED transition with the full
snapshot, per-key `supersedes` linkage, seal over (count, head), both tiers.
The registry writes the sink before committing memory with legality
pre-checked, and `resume()` rebuilds versions, state objects at stored status
without replaying transitions, and provenance nodes. **Backfill assigns
knowability without inventing it** (`scripts/backfill_available_at.py`):
`published_at` preferred as the latest demonstrably-held moment,
`occurred_at` as a flagged lower-bound fallback, rows with neither witness
left `as_of_unknown` forever; dry-run by default, present values never
overwritten with presence re-checked at apply time, every derivation carrying
its source field and policy id in a report artifact.

### W3 — G040 Evidence Fabric · **`LANDED`** · no remaining gaps

**Producers write through the ledger** (`core/claim_writers.py`): verification
reports land as one claim each (verified strings as evidence refs, capped at
eight; hallucinations as contraindications), evidence packages land documented
with their findings hash and counter-claims. Confidence is never upgraded at
the boundary — a perfect score with one reference records 0.99. Claim ids are
deterministic per producer id, so replays are no-ops returning the stored row
while same-id-different-content is refused. That last point changed an old
contract deliberately: identical re-record used to raise, but pipelines replay
and twins would double-count judgments — the OMS idempotency-key semantic
(same key plus same content returns what exists) applied to judgments.
`PostgresClaimLedger` mirrors SQLite method-for-method; migration v6 (whose
DDL predated registration as unregistered constants — found and registered,
not rewritten) covers both dialects. No UPDATE exists in either tier, pinned
structurally.

### W4 — G050 Agent Governance · **`LANDED`** · no remaining gaps

**The durable sink is done** — `core/decision_sink.py`, migration v4, triggers
enforcing append-only, HMAC seals catching the truncation a chain cannot. Two
findings from building it are worth carrying forward:

- The chain was never going to catch truncation on its own. See W4 above.
- `verify_chain` compared the recomputed head to the *live* guardian's head, so
  a log read back from storage could never verify — the read side was unusable
  before there was anything to read back. Fixed by skipping the head comparison
  when an explicit list is supplied.

**Policy is data, not code** (`core/policy_bundles.py`, `policies/capital_v1.json`).
Versioned, HMAC-signed bundles compile onto the guardian; the match language is
six conjunctive comparison operators and stays there on purpose — anything
richer would inherit a programming language's audit burden while pretending to
be data. Unknown operators fail at compile time; inapplicable rules do not
match rather than error; clamps scope via a new optional `when` predicate so a
broker-notional ceiling does not clamp unrelated tools. OPA/Rego was
deliberately not adopted: a sidecar would add a network dependency and a
non-Python runtime to the deterministic core's most sensitive path, against
the dependency policy — the substance (externalized, versioned, signed policy)
is all here.

**PostgreSQL tier done** (`PostgresDecisionSink`, `tests/test_ledger_parity.py`).
Same trigger-enforced shape, dialect-agnostic `audit_log`/`GovernanceSeal`
shared, both tiers held to identical behaviour. No remaining gaps.

### W5 — G060 Quant Factory · **`LANDED`** · G070 Experiment Ledger · **`LANDED`**

**G070 lineage and failure reasons are done.** `parent_id`, `failure_reason`,
`failed_at`, `attach_verdict`, plus `lineage()`, `children()`, `failures()`, and
`attempt_count()`. A failure with no recorded reason is *refused*, because an
unexplained failure is indistinguishable from a run that was never attempted —
which is how the trial denominator stops being auditable, and a Sharpe quoted
without that denominator is an anecdote with a decimal point. The
reproducibility hash deliberately excludes `parent_id` and `result`: lineage is
navigational and a result is an output, so hashing either would make identical
configurations differ by how they were reached.

**The ledger is durable** (`core/experiment_sink.py` + migration v5, 34 tests in
`tests/test_experiment_sink.py`). Same enforcement shape as the governance
ledger, adapted: one event per transition carrying the full run snapshot, with
current state as the latest event per experiment. Append-only is enforced by
database triggers — `UPDATE`, `DELETE`, out-of-sequence `INSERT`, and off-head
`supersedes` each refused by name. Each event links to its experiment's head,
so a forged rewrite of a FAILED run becomes a visible head rather than a hidden
edit, and an HMAC seal over `(count, head)` catches the truncation a linkage
check cannot see — the specific prize of a cut tail being a manufactured track
record with the failures removed. The registry writes the sink *before*
committing memory (a durable event the memory lacks heals on resume; a memory
state the sink lacks is gone permanently), with legality pre-checked via the
new `StateMachineEngine.check_transition` so an illegal transition leaves no
phantom event in a log that cannot un-write. `resume()` rebuilds runs,
state-machine objects at their stored status without replaying transitions, and
provenance nodes and edges, in first-seen order so parent links resolve. No
remaining gaps.

**G060 registries are done** (`kernel/factors.py`, `kernel/strategies.py`,
`research/reporting.py`, `tests/test_quant_factory.py` — the gate file the
goal pointed at but never had): immutable factor definitions with
deterministic computation (effective warmup is max(declared, lookback+1),
gaps poison windows without interpolation, flat-context z-score undefined
while flat vol is 0.0, every value `available_at`-stamped); immutable
strategy specs with `bind_artifact` naming every violation (family,
hypothesis, unknown/missing/out-of-range/non-finite params including
bool-is-not-int, dataset ref drift); reports where every shipped number
carries kind plus source and undeclared figures quarantine to a public cut
list. No remaining gaps.

### W5 — G080 Certification Firewall · **`LANDED`** · no remaining gaps

Complete. Every check is measured; none can be asserted.

### W6 — G090 Feature Fabric · **`LANDED`** · no remaining gaps

**The split is built** (`core/feature_store.py`, `tests/test_feature_parity.py`
— the gate file the goal pointed at but never had): one shared
`transform_step` for offline batch and online serving (sma, momentum,
rolling_sum/max/min, ema), so parity holds by construction; a `ParityReport`
that records its own epsilon; warmup as a named refusal, never silent NaN;
online ticks carrying `available_at`; code-hash pinning with recomputation
refusing foreign hashes; online state serializing for restart resume.
Absorbed from a partial parallel lane after review (one missing-field
constructor fixed on arrival). The decision path is structurally verified to
make no network calls outside the market feed.

### W7 — G100 Regime · **`LANDED`** · G110 Calibration · **`LANDED`** · no remaining gaps

**Detection replaces labelling** (`communities/c10_world/change_detection.py`,
`core/conformal.py`, `core/decision_gate.py`, 30 tests): two-sided online
CUSUM with an explicit burn-in that cannot alarm by construction, plus
Bai-Perron-style offline segmentation whose breaks are honestly dated at the
sample end. Split-conformal intervals with the finite-sample correction, and
an empirical-coverage test plus a test demonstrating the training-residual
collapse (which is why the split lives in the caller's pipeline). The
TRADE/WAIT/ESCALATE/ABSTAIN gate runs in fail-closed order with ABSTAIN
first-class, in the playbook's vocabulary by value. The old EMA labelling
engine remains for its existing consumers; the detector is the path new code
takes, and detections convert to `available_at`-stamped features rather than
bare labels.

### W8 — G120 Playbook Engine · **`LANDED`** · no remaining gaps

`kernel/playbook.py`: a frozen, content-hashed `Playbook`, predicate regimes
over point-in-time features, a read-only router with first-class abstention,
live certification, derived sizes with recomputable bases, durable policies,
a live regime feed, and an offline proposer.

Four decisions were forced by a specific failure rather than chosen:

- **A regime is a predicate, not a classifier label.** A label records nothing
  about which features produced it or when they became knowable, so a
  full-sample regime label is a look-ahead that no timestamp check will ever
  catch. `RegimeCondition` *refuses* a bounds-free regime precisely because
  that would match every observation and let the router regress to guessing.
  Selection also refuses a contaminated observation **before** considering any
  playbook — acting on one is wrong under every policy — and
  `Selection.audit_timings()` hands its timings to G080's `detect_look_ahead`
  rather than reimplementing a weaker second check.
- **Abstention is a first-class outcome**, with five named reasons. A router
  that always returns its nearest match has not routed; it has encoded a prior
  and labelled it a decision. Two simultaneous matches abstain rather than
  breaking the tie, because no ranking between them was certified — and
  resolving by registration order means the policy was chosen by the sequence
  of startup calls.
- **Certification is re-asked live** through a `CertificationOracle` protocol
  on every call, never snapshotted at bind time. A bind-time check keeps a
  revoked strategy trading forever through any playbook bound to it.
- **The router has no mutation method at all.** That is the whole enforcement
  of "the fast model cannot modify a playbook in production". An instruction
  the fast tier is asked to follow is a control with a probability of failure;
  an absent method has none.

**The composition is wired** (`kernel/bootstrap.py`, 11 tests in
`tests/test_playbook_composition.py`). `create_kernel` now wires
`StrategyRegistry`, `RegistryCertificationOracle`, and `PlaybookRouter` onto
`AIOSKernel`, and `publish_playbook` derives a playbook from an approved
artifact. The oracle is a **separate type** rather than a `StrategyRegistry`
handed to the router, on purpose: the router's question is narrower — *may this
be traded right now* — and passing the whole registry would put `approve`,
`reject`, and `record_verdict` on the fast tier's own collaborator. The wiring
means the firewall and the router have now been observed refusing the same
strategy for the same reason, on the same object, with nothing stubbed.

**The size is derived, not supplied** (35 tests in
`tests/test_playbook_derivation.py`). `publish_playbook` no longer takes an
`action` parameter at all — there is no argument for a caller under deadline to
reach for. The size is `required_notional / book`, the mandate's own number,
and the measurements contribute *permission*: costs, capacity, stress,
execution, and contamination must all be measured; the regime must carry a
passing `regime_sharpe` check; the mandate must fit the measured ceiling and
the book; the weight must clear the 1% policy floor. The first failure names
itself in the refusal, and there is deliberately no fallback size — a fallback
is a human judgment wearing arithmetic's clothes.

Three supporting changes made this honest rather than decorative:

- `record_verdict` **requires the evidence** and binds it: the verdict's
  observed Sharpe must be the evidence's gross Sharpe, the same trial's number
  in two places. A strong verdict can no longer be recorded alongside weak
  measurements, and the artifact retains both so `publish` reads the ceiling
  off the artifact instead of accepting a fresh number.
- `core/backtest.py` gained `regime_sharpes`, which **replaced the
  `regime_decomposition` boolean** in `build_verdict` — the last caller-supplied
  boolean in the firewall besides the CV plumbing. Each regime gets its own
  `regime_sharpe:<name>` check recorded *inside* the hashed verdict, so the
  playbook's `verdict_hash` covers the regime performance it gates on. Thin or
  losing regimes limit without rejecting: they constrain *where* the strategy
  may trade the way a low ceiling constrains *how much*.
- `SizingBasis` records every input the size depends on, `verify()` recomputes
  it, and the content hash covers the basis — the same action with different
  measurements behind it is a different playbook.

Two deliberate refusals-as-design: `CERTIFIED_WITH_LIMITS` cannot produce a
position — limits qualify the certification and a qualified certification needs
a human before capital moves — and the bounds stay caller-supplied, because
deriving thresholds from the backtest that justifies them is selection bias,
and the gate is that the regime was measured profitable.

**Remainder closed.** Durable policies (`core/playbook_store.py` + migration
v8): snapshot rows with rewrite-under-version refused, seal over (count,
set-hash) so same-count substitution fails. Module-level
`persist_router`/`load_router` — the engine test caught router-method growth
and forced the move, which is the shape-check working as designed.
`load_router` re-asks certification per policy: revoked strategies stay
stored but never join, with skipped refs returned alongside. `RegimeFeed`
streams CUSUM detections as `available_at`-stamped features plus on-demand
stability counts. `propose_candidates` sweeps measured regimes per certified
strategy into derived sizes with bases or named refusals, with unmapped
regime names reported as taxonomy gaps. No remaining gaps.

### W9 — G130 Portfolio Brain · **`LANDED`** · G140 Capital Firewall · **`LANDED`** · no remaining gaps

**Two optimizers, one proposal or one finding** (`communities/c9_portfolio/optimizer.py`,
`tests/test_portfolio_brain.py`): closed-form inverse-volatility plus stdlib
HRP (single-linkage on correlation distance, recursive bisection, ties by
sorted symbol). Divergence beyond 5 points of weight raises
`OptimizationDisagreement` with per-symbol weights instead of averaging.
`PortfolioProposal` carries no venue, order id, side, or submit path by type.
Inputs validated (dispersion required, zero-vol refused, asymmetric covariance
refused); caps refuse rather than rescale when they cannot fit.

Recorded as not owed rather than remaining: a real optimizer (zero occurrences of `pypfopt`, `skfolio`,
`riskfolio`).

**The firewall engine is built** (`core/authorization.py`,
`core/capital_firewall.py`, 41 tests): a sealed HMAC envelope the execution
path cannot mint (no `issue()` outside the firewall factory), and 15 named
checks — 11 hard REJECTs (signature, expiry, scope-identity, resolve, live,
certified, look-ahead, survivorship including missing-report, daily-loss halt,
venue, uniqueness, actor) plus 4 sizing REDUCEs (scope-qty, the $100
constitutional cap, lot floor-down-only, exposure). Delisted instruments are
refused at point-in-time (`as_of` + `is_live`), not just at resolve, and the
order's `instrument_id` must equal the `resolve(ticker, mic)` result, closing
the ticker-reuse splice the parity suite deliberately left open.

**The wiring is done** (`tests/test_envelope_wiring.py`, 11 tests): a
firewall-bound OMS evaluates before persisting — REJECT persists nothing,
REDUCE persists the approved quantity — with the verdict and envelope id in
the outbox payload; a secret-bound adapter verifies signature plus
quantity/notional scope before `govern()` runs. Both boundaries are
configuration-conditional, so every pre-existing caller keeps working, and
the authority chain now structurally requires every `submit` implementation
to touch the envelope boundary. No remaining gaps.

One catch worth recording: the first version mutated the outbox payload after
construction, which stored an event that failed its own `payload_hash` check
on read — exactly what the hash exists to prevent. The event is now rebuilt
with the authorization included and the hash recomputed, so the hash vouches
for the verdict too.

### W10 — G150 Execution Kernel · **`LANDED`** · G160 Execution Twin · **`LANDED`** · no remaining gaps

**The schedulers are built** (`communities/c5_execution/algorithms.py`, 39
property tests): TWAP, VWAP, POV as pure deterministic functions returning
immutable schedules. Exact-integer Hamilton apportionment — children sum
exactly to the total, enforced by construction and re-enforced by a model
validator so even hand-built schedules cannot create or lose dust. Down-only
lot flooring with named remainder bars, sub-lot totals refused, caps enforced
at the boundary with breaches raising rather than reshaping, VWAP degrading
to TWAP with a named reason on empty profiles, POV pausing on zero-volume
bars. Schedulers propose quantities only; execution stays on the existing
governed adapter path — no orders placed, no venue contact. One documented
trade-off, not hidden: largest-remainder exhibits the Alabama paradox, so
VWAP keeps quota over cross-total monotonicity per Balinski-Young (tracking
is its purpose), and monotonicity across totals is claimed only for TWAP/POV.

**The twin is built** (`simulation/execution_twin.py`, 12 tests): tick replay
with per-stage latency decomposition (30/20/30/20 shares, fixed not fitted),
queue position consumed by prints, partial fills staying partial, square-root
impact capped per bar. Latency acts as staleness — decisions execute against
the later book — so the 20/50/100/200 comparison attributes price differences
to latency alone. The fixture is closed-form deterministic, no seeded
generator to pin.

### W11 — G180 Memory · **`LANDED`** · no remaining gaps

**The modules are built** (`kernel/memory_tiers.py`,
`kernel/retrieval_contract.py`, `kernel/counterfactuals.py`, 9 tests):
M0–M9 frozen tier configs, SAFETY criticality never decaying or expiring,
decay as a pure function with `now` passed explicitly, a versioned retrieval
contract that rejects sufficient-with-stale-evidence, and append-only
counterfactuals resolved by superseding record rather than mutation (a
supersede that left the original in the open set was caught and fixed
in-test).

**Recall is wired** (`tests/test_recall_blend.py`): vector search accepts an
injected salience callable — core never imports the tier definitions — with
explicit `now`, oversampled blend pool, and min-max normalized convex
blending recorded per match. `salience_for` maps document metadata to scores
with neutral-1.0 fallback on missing or unparseable metadata (recall degrades
open, never closed) and exclusion only on computable expiry. The tier
horizons themselves remain judgment calls recorded in the tier table, and the
M7+ human-review rules remain descriptive — both stated, neither hidden.

### W12 — G200 Arena · **`LANDED`** · G210 Observability · **`LANDED`** ·
### G220 Formal Assurance · **`LANDED`** · G230 Control Planes · **`LANDED`** · no remaining gaps

**The arena gates are pinned** (`tests/test_champion_challenger.py`, the gate
file the goal pointed at but never had): promotion requires EVALUATED state
plus a PASS verdict plus an identified human — a human cannot overrule FAIL
or INCONCLUSIVE, an empty operator id is refused, rejection stays always
available, promotion is not repeatable, and the evidence stays attached to
the trial it promoted.

**Trace continuity is threaded** (`core/trace.py`): eleven canonical stages
in a closed vocabulary, structureless hex ids, an in-memory recorder that
reports gaps instead of filling them, and `why_trade` assembling spans plus
order events with missing stages named. OMS stamps the outbox `trace_id`
column (queryable across tiers, outside the hashed payload); adapters thread
it into the governed call session; execution mints-with-warning when absent
— observability is not authorization, so a missing id never refuses an
order. The OpenTelemetry SDK stays deliberately deferred.

**TLA+ exists with drift pins, and is model-checked**
(`specs/OrderLifecycle.tla`, `specs/Outbox.tla`, `specs/*.cfg`,
`tests/test_formal_assurance.py`, `scripts/run_tlc.ps1`): seven lifecycle states
mirroring the implementation, terminal set mirrored, transitions covered; outbox
with duplicate-delivery stutter and hash-mismatch quarantine. `run_tlc.ps1` runs
TLC in a throwaway container — the JDK image and `tla2tools.jar` are cached by
Docker and neither is vendored into the repository, because a build input is not
source and a 2 MB binary in git is exactly what the release packager refuses.

Verified results, all four specs, re-measured: OrderLifecycle 70 states generated /
42 distinct / depth 4; Outbox 16 / 13 / depth 7; KillSwitch 88 / 48 / depth **11**;
Reconciliation 793,036 / 1,494 / depth 3. No property violated. *KillSwitch's depth
was given as 4 here and is 11, and `Reconciliation` was missing from this list while
being named in the verified block above. Correcting the headline and leaving the
body is defect #63's shape, repeated.*
The specs were wrong when first run and are now correct: an `INVARIANT` must be
a state predicate, `[]` needs an action of the form `[A]_v`, terminality is
stated with `ENABLED` (stronger than the original claim), and the liveness
property that TLC refuted has been removed rather than quietly weakened. The
`.cfg` files are committed so the gate is reproducible without knowing which
properties to check.

The third spec is where the payoff showed. `KillSwitch.tla` encodes
`CONSTITUTION.md` §2.2 — cancel, flatten, halt, exit only by human reset — rather
than the implementation, so TLC could say where reality diverged from the
mandate. It refuted the spec on its first run, correctly, and the bug was in the
spec: `EngageHalt` was guarded on exposure alone, letting the model reach the
halt with a live order still open. Following that thread back to the code is what
found defect #41. The architecture names eight targets for formal properties and
**four are modelled and one of the remaining four is deliberately not.** Fills,
partial fills and duplicate deliveries are covered by `OrderLifecycle` and `Outbox`;
`Reconciliation` has its own spec. Only `failover` is outstanding, and it is
outstanding by decision rather than omission — one bare word in the source, no scope,
no layer, no acceptance criterion (#48). *This said the remaining five were still
owed, which contradicted line 51 of this same file: a reader who found both had no
way to tell which was current.*

**Supply chain enforced locally** (`scripts/sbom.py`,
`tests/test_supply_chain.py`): byte-stable CycloneDX covering exactly the
lock (unpinned and duplicate lines refused), releases self-verifying by
SHA256 manifest (missing manifest, hash mismatch, unlisted member, and
secrets each fail), no tracked `.env`, gitignored env, no key material in
the tree, valueless secret-named example vars. Scanner runs, authority
signing in CI, and OpenBao stay explicitly deferred — stated, not pretended.

### W12 — G240 Long Shadow · `BLOCKED` · G250 Canary Capital · `BLOCKED`

Both correctly blocked, and engineering cannot unblock them. G240's former
engineering dependencies (G080/G110/G140/G160) are all LANDED; what remains
is a validated broker testnet connection (needs network and credentials —
neither exists here), a full shadow cycle against it, and the five human-held
Phase 5.0 gates. The shadow-cycle gate file does not exist yet because a
shadow cycle with no venue to shadow would be theater; it gets written
against the testnet connection when a human provisions it. G250 is a
governance blocker, not an engineering one: constitutionally forbidden until
`approve_live_capital` is recorded and `CONSTITUTION.md` §1 is amended by
ADR. The control action, the gates endpoint, and the amendment path all
exist. What remains is humans deciding — which is the entire point of the
gate. These two stay `BLOCKED` with their blockers named, not `LANDED` by
redefinition: that distinction is the difference between a registry and a
wishlist.

---

## 5. Recommended next step

**Review, then hand the two BLOCKED goals to humans.** The verification and
commit items that stood here are done and their numbers are in the verified line
at the top; the list below is what is genuinely outstanding.

**Done, and struck from this list:**

- ~~Full verification~~ — suite run with PostgreSQL and NATS up *and* hermetic,
  ruff, mypy, lint, constitution pin, architecture boundaries, Docker build and
  smoke test, `run_tlc.ps1`, `tsc`, `vite build`, frontend tests. Figures above.
- ~~PostgreSQL parity legs are exercised~~ — `docker compose -f
  docker-compose.test.yml up -d` plus `AIOS_TEST_PG_DSN` turns "written,
  skipped" into "exercised", and immediately found six defects (#33–#38) that
  years of CI could not see, because the hermetic job has no database. It was on
  this list because it was written off rather than scheduled.
- ~~TLC runs~~ — `scripts/run_tlc.ps1` needs no JVM on the host, only Docker.
  G220 is closed with a model checker rather than a comment saying the specs look
  right. Also on this list for the same reason.
- ~~Disaster Recovery~~ — **investigated and deliberately not built.** It is a
  rung on the architecture's ladder, so it looked like the obvious gap, but it
  appears exactly once in the document, as a bare label: `RPO`, `RTO`, `backup`,
  `restore` and `point-in-time recovery` have **zero occurrences**. Building it
  would have meant inventing the requirements, which is what §14's freeze rule
  exists to prevent. Not owed; unspecified.

**Outstanding:**

1. ~~Review~~ -- **done** at `198ba13`, and it was worth doing. An independent
   review of the four code commits this session returned NEEDS-CHANGES: 2 MAJOR,
   4 MINOR, 4 NIT. Both MAJORs are in code written specifically to prevent the class
   of defect they exhibit, and **both survived a mutation check** (#53, #54). Every
   property I chose to mutate turned the suite red, which proves those are
   load-bearing and says nothing about the properties I did not think of -- and the
   coverage of one's imagination is not a property. That lesson is now the most
   repeated in this file and is stated as a rule in #53.
   **Closed since this was written.** `competence=` is now derived from the
   certification verdict and wired at both production construction sites, and a third
   site -- `load_router`, which rebuilds the router from the durable store -- turned
   out to bypass the gate entirely because it inserts into `_playbooks` rather than
   registering (defects #58, #60, #63). Two independent reviews then found seven more
   defects in that work, including two that had shipped in it.
   **One NIT genuinely remains,** restated precisely because the original wording
   overstated it: `reconcileExecutive`'s carry-through branch is *covered by tests*
   (20 of them), and what is true is narrower -- `useLiveExecutive` always passes the
   `EMPTY_VIEW` constant as `current`, so the branch is unreachable *from the hook*.
   That is not untested code, and threading real state would change no behaviour
   today, so it is recorded rather than churned. The review's third NIT, a FRAME AGE
   readout that froze while the stream was parked, was classified as cosmetic and
   turned out not to be: it is the one readout whose job is to say how current the
   figure beside it is, so a stale number there is the failure section 3 is about.
   Fixed at `7549d52` by exposing the frame TIMESTAMP rather than only a duration --
   a timestamp is a fact, a duration is a reading, and only the first can be
   recomputed later. Recording a fix as outstanding would be this file's own defect
   class: a claim that does not match what the code does.
2. **Humans decide G240/G250** — testnet credentials, shadow cycle, five
   Phase 5.0 gates, `approve_live_capital`, ADR amending §1. In that order; no
   step is skippable and none is mine to take.
3. **Publish** — `gh auth login`, then
   `pwsh -ExecutionPolicy Bypass -File scripts\publish_private.ps1`. The
   repository exists and is empty; the script reuses it and refuses rather than
   guessing. No GitHub action has been taken.
4. ~~Per-strategy domain of competence~~ - **delivered** at `6b80af2`, and it
   was the one genuine capability gap the previous cycle found and did not
   close. Architecture section 2 Layer 9 mandates it ("Every strategy/model
   has: DomainOfCompetence") and nothing implemented it. Now
   `DomainOfCompetence` + `StrategyCompetence` in `kernel/playbook.py`,
   enforced once at admission by `PlaybookRouter`, with 28 mutation-checked
   tests, plus 25 more for the derivation. **This entry's reason for staying on the
   list was wrong in both halves, and the correction is the interesting part.**
   It said the capability was "available and correct but not switched on" -- true
   then, false now: it is derived and wired at every construction site. And it said
   the outstanding work was "a decision about which strategies are competent where
   rather than a build." It was not a decision at all. Certification already records
   per-regime competence, as a `regime_sharpe:<regime>` check that passes only when
   the regime is neither too thin to support a playbook nor losing money net of costs,
   so the answer was *derivable* from the verdict already in hand. Deriving it beats
   declaring it for a reason this file has circled before: a hand-declared competence
   is the strategy approving itself, which is the circular version of the check. The
   blocker was recorded as a decision because nobody had looked inside the verdict
   to see that the decision had already been made.
5. ~~SSE is unconsumed~~ -- **consumed** at `a165877`. `api/stream.ts` and
   `/api/v1/stream` were complete, correct and authenticated on both sides, and
   `startStream()` was never called, so the console polled for everything while
   a live feed sat idle beside it. Now `useLiveExecutive` starts the stream,
   prefers a frame's executive, and keeps polling as a fallback -- deliberately,
   because the stream parks in `auth_required` whenever the server answers 401
   (which it does for an unauthenticated console) and a reconnect can take 30
   seconds, so a live-only design would show either nothing or a frozen number
   with no hint it was frozen. The core assumption was verified rather than
   assumed: a probe against a live server confirms the stream's `executive` has
   an identical field set to `GET /api/v1/executive` with every value agreeing,
   which is what lets a frame be used with no translation layer.
   **Left partly open, stated rather than glossed:** the decisions are
   pure functions with 20 tests and six caught mutations, but the React
   re-render wiring is untested, because the frontend has no
   `@testing-library/react`, no `jsdom` and no `happy-dom`. Only one consumer is
   wired (`SystemHealthWorkspace`, reporting feed status and snapshot
   provenance); the rest of the console still polls.
6. ~~CI's lock gate will fail~~ -- **fixed** at `8c77a90`. It compared the lock
   against a closure recomputed from the installed environment, so it could only
   ever pass on the machine that generated the lock, and CI made that worse by
   priming the environment with UNPINNED ranges before running it. It now checks
   the lock against `pyproject.toml`; all six properties are mutation-checked.
   **One honest narrowing, recorded in the module docstring rather than assumed:**
   the gate no longer verifies that the lock's transitive closure is COMPLETE,
   because that needs the metadata of the packages in the lock -- exactly the
   environment dependence the rewrite removes. A lock missing a transitive
   dependency passes it. The CI step itself has not been run here (no GitHub
   activity), so its reasoning is in the step comment where a failure would be
   diagnosable.

---

## 6. Standing constraints

These hold regardless of which workstream is next.

- **The architecture freeze rule.** A new technology answers all three
  questions — which layer, which gate, does it replace or duplicate — or it is
  not added. See `docs/DEPENDENCY_POLICY.md`.
- **Three runtime dependencies is a feature.** `pydantic`, `pydantic-settings`,
  `httpx` is what makes the deterministic core portable and auditable.
  Preserve it. Weak copyleft behind a contract boundary; strong copyleft
  nowhere.
- **The deterministic core takes no ML/quant dependency** that could make a
  financial decision non-deterministic.
- **A goal is `LANDED` only when a test enforces it.** A document asserting
  completion is the failure mode `docs/goals/README.md` exists to prevent.
- **Every test that guards a property names the defect it prevents**, so a
  future maintainer can find the reasoning without archaeology.
- **A pre-existing boundary leak, recorded rather than fixed in passing.**
  `core/challenger.py` imports `kernel.promotion`, and `core/control_plane.py`
  imports `kernel.registries` and `research.evaluation`. Both predate this
  cycle and neither file was touched here, so invariant 1 (`communities/` never
  imports `kernel/`) still holds and `tests/test_architecture_boundaries.py`
  passes. But `core/` importing `kernel/` is the same class of leak one layer
  in, and the likely real cause is that both files are composition roots
  living in the wrong directory rather than genuine domain modules. It is worth
  a decision rather than a drive-by: moving them changes the plane map, so it
  should be its own change with its own review. The new `core/` modules in this
  cycle (`decision_sink.py`, `contamination.py`) import only `schemas/`.
- **Everything is committed.** 139 commits on `main`, 497 tracked files, working tree
  clean. `feat/command-center-ui` still exists and is 0 commits ahead and 38 behind
  `main`, so it is superseded rather than pending. *This said the opposite —
  "Nothing is committed. 49 files are modified or new" — and it was the last line of
  the document, which is where a skimming reader lands. A status line decays exactly
  as a figure does (#56); the difference is that nobody re-measures either unless
  something forces them to.*

---

## 7. Cycle close-out

Written to be read on its own, by someone who has not read the rest of this document.

**Where the program stands.** 13 workstreams, 25 goals: **23 `LANDED`, 2 `BLOCKED`, zero
`PARTIAL`, zero `NOT_STARTED`.** 92 test gates, every one on a `LANDED` goal naming a file
that exists and contains tests. 68 defects recorded this cycle, each recorded with the
mechanism rather than the symptom.

**What is finished.** Every workstream's engineering. The last capability gap the cycle
found -- a strategy's domain of competence, mandated by the architecture, implemented but
wired nowhere in production -- is closed. Closing it took two independent reviews and seven
further defects, two of which had shipped inside the fix itself.

**What is blocked, and why engineering cannot move it.** G240 (Long Shadow) needs a
validated broker testnet connection, a full shadow cycle against it, and five human-held
Phase 5.0 gates. G250 (Canary Capital) needs `approve_live_capital` recorded and
`CONSTITUTION.md` §1 amended by ADR. Both are decisions rather than work, and they stay
`BLOCKED` with their blockers named instead of being marked `LANDED` by redefinition --
that distinction is the whole difference between a registry and a wishlist.

**What is outstanding.** Two items, both requiring a human: those decisions, and
`gh auth login` followed by
`pwsh -ExecutionPolicy Bypass -File scripts\publish_private.ps1` to publish the private
repository. The repository exists and no GitHub action has been taken.

**What is UNVERIFIED rather than done, and named as such.** The CI workflow has not been
executed here, because executing it means GitHub activity. Every gate it runs has been run
locally and every step's reasoning is in the step comment where a failure would be
diagnosable. Release signing is applied in CI over the manifested bytes, so it is
unverified for the same reason -- and the SHA256 manifest that *is* in the tree is
integrity, not authenticity. Both are recorded rather than omitted, because an omitted
claim and a passing claim look identical to a reader going quickly, which is the subject of
defect #66.

**The one engineering item left open,** restated precisely because the original wording
overstated it: `reconcileExecutive` has a carry-through branch its production caller never
reaches, because `useLiveExecutive` always passes a constant. The branch is covered by
tests; what is true is the narrower claim. Left recorded rather than churned, since
threading real state would change no behaviour today.

---
