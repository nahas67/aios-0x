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
| G260 | Disaster Recovery | — | — | **not carried** — see §3 below |
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
| B | **Model Governance** (MLflow: models, versions, prompts, runs, evals, datasets, features, champion/challenger, deployment, rollback) | **no goal of its own** | **GAP — see §5** |
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

## 5. The Model Governance gap

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

## 6. Verification

How to re-check every claim above:

| Claim | Command |
|---|---|
| registry titles and count | `python -c "import json;d=json.load(open('docs/goals/goals.json'));print([(g['id'],g['title']) for g in d['goals']])"` |
| §13 goal list | read `ARCHITECTURE.txt` §13, lines 1754–1852 |
| DR evidence, correctly | `Select-String -Path ..\ARCHITECTURE.txt -Pattern '\bRPO\b\|\bRTO\b'` → expect no matches |
| control-plane state | read `goals.json` entries `G050`, `G210`, `G220`, `G230` |

**Not verifiable in-repo:** `ARCHITECTURE.txt` itself. That is the finding this file exists
to make visible, and the reason the first row of the table above is worth reading twice.
