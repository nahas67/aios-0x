# AIOS-0X Dependency Admission Policy

## The admission test

This is the operative rule. A new technology may be added to AIOS-0X only if it
answers all three questions with specific answers:

1. Which existing AIOS layer does it improve? Name the layer.
2. Which measurable gate does it help pass? Name the gate and its current value.
3. Does it replace an existing component, or merely duplicate it? If it
   duplicates, it is refused.

If there is no clear answer, do not add it. There is no exception for
popularity, for trend, for the fact that a related project uses it, or for the
number of GitHub stars. A candidate that cannot name its layer and its gate has
not been evaluated; it has been noticed.

The third question does most of the work. The failure mode it is built to
catch is a duplicate with better documentation, and such a duplicate is also a
second source of supply-chain surface. Duplication is not a neutral outcome to
be weighed against benefits. It is a refusal.

## Three runtime dependencies

`pydantic`, `pydantic-settings`, and `httpx` are the entire runtime dependency
set. This is a deliberate property of the system, not a limitation of its
budget.

That set is what makes the deterministic financial core portable, auditable,
and free of supply-chain surface. A fresh environment installs the project and
runs its supported test suite from `pyproject.toml` alone. There is no
per-component requirements file, no compiled extension in the import path of a
financial decision, and no transitive tree that must be audited before the
ledger can be trusted. Preserve it. A fourth runtime dependency must earn its
place against the admission test above, and the burden of proof is higher for a
fourth than for a seventh.

## The zone rule

The deterministic core — ledger, risk firewall, authorization, execution,
reconciliation — may never take a dependency that can make a financial decision
non-deterministic.

Machine-learning, numerical, and vendor-SDK dependencies belong behind a
contract boundary in the market/quant or AI/research zones, never inside the
deterministic core. A model may propose; a deterministic component decides. The
boundary is what keeps that sentence true, and the boundary is only real if the
import graph respects it.

A dependency that makes a decision non-deterministic is not a dependency in the
financial core. It is a different system that happens to share a repository.

## Admission workflow

A dependency is admitted by ADR under `docs/adrs/`, using the ADR-000 template.
The proposal must carry:

1. The three answers from the admission test above, with the gate's current
   measured value attached, not a target value.
2. A measured before/after for the gate in question. A proposal with no
   measurement is a proposal with no evidence, and is returned.
3. A rollback plan: what the component becomes when the dependency is removed,
   and whether that state is reachable in one commit.
4. A license entry in `docs/LICENSES.md`, added in the same change.
5. The contract boundary, if the dependency is not runtime, named as a module
   and an interface.

The `CONSTITUTION.md` amendment procedure is additionally required for anything
that loosens a capital or risk limit: ADR plus the updated SHA-256 pin in
`core/constitution.py`, in the same commit. A dependency that changes a capital
limit is a constitutional change, not a build change. The position limit, the
daily drawdown limit, and the kill-switch are limits, and a library that
reaches them is amending the constitution by the back door.

## Proposed for admission in vNext

**Status: PROPOSED, under review. This table is not an approved change set.**
None of the seven below is currently a dependency of this repository. No row
here is authorized for merge. Each requires its own ADR.

| Proposed | Layer improved | Gate it must pass | Current value |
| :--- | :--- | :--- | :--- |
| `mapie` | Verification (C3) / AI research | Conformal calibration of the selective-decision ABSTAIN threshold, so abstention is justified by a coverage guarantee rather than a fixed score cutoff | No calibrated threshold; the ABSTAIN boundary is a fixed constant |
| `ruptures` | Market/quant (C10 world) | Regime-change detection, replacing the hand-rolled heuristic in `communities/c10_world/regime_engine.py` | 88 lines of fixed-band trend and volatility labeling |
| `skfolio` | Portfolio intelligence (C9) | Portfolio optimization, replacing hand-rolled sizing in `communities/c9_portfolio/portfolio.py` | 207 lines; Fractional Kelly and drawdown scalars computed inline, no optimizer |
| `opentelemetry-sdk` | Observability / decision-to-ledger chain | Trace continuity across the chain from decision to ledger entry | No tracing SDK; provenance is asserted by local invariants in `core/financial_kernel.py` |
| `mlflow` | Registries (Doc 17) | Model registry and champion/challenger promotion | No registry dependency; experiment records are local |
| `qdrant-client` | Memory (C7) | Real embeddings in semantic retrieval, behind the existing vector-memory contract | No embedding model is a declared dependency; the vector path is unimplemented in the runtime closure |
| `polars` or `pyarrow` | Data (C1) / market-quant | Point-in-time columnar joins over the feature store | No columnar engine; relational work runs through SQLite, with PostgreSQL as an extra tier |

Two of these replace existing hand-written code and are the strongest class of
proposal: they delete lines, not add them. The rest are net-new surface behind
contract boundaries, and each is answerable to the admission test above before it
is built.

## Refusals

| Refused | Reason |
| :--- | :--- |
| QuestDB | Remains a candidate and is not permanently excluded. `core/ibor.py` is the canonical book of record behind `BaseFinancialStore`, shipped on SQLite with a PostgreSQL tier behind the same seam. A second consistency model on top of a first that has not yet been stressed in production is an unearned tax. |
| Apache Iceberg | Same reasoning as QuestDB. A second storage format buys nothing while one financial ledger of record exists, and the ledger's own ADR names the adapter seam that a future backend must arrive through. |
| `river` | Online drift detection requires a live streaming feed. No such feed exists in the runtime posture; the dependency would be machinery for data the system does not have. Revisit when a stream does. |
| Any AGPL-licensed component | Strong copyleft is inadmissible as a runtime dependency. See `docs/LICENSES.md` for the categories and the AGPL-specific network-exposure clause. |
| Anything added to make a dashboard render a number the system cannot yet justify | A rendered number is not evidence. If the gate behind the number is unmeasured, the dependency does not make the number true; it makes the number visible. |

## Supply chain

### Active

`requirements.lock` is generated from `pyproject.toml` by
`scripts/lock_dependencies.py` and verified in CI. The CI job "Lock file is
current" runs:

```bash
python scripts/lock_dependencies.py --check
```

The check fails if the lock is stale. The lock carries a `resolved-digest`, a
SHA-256 over the resolved package set, and the check recomputes it: a dependency
that changes without the lock being regenerated fails the build.

Two further controls are active today and are described as what they are. CI
runs `ruff check .` and `mypy` over the four shipped packages, and a `security`
job greps tracked sources for `sk-` and `figd_` credential patterns and asserts
`.env` is not tracked by git. That grep is a narrow pattern check. It is not a
secret scanner, and it is not evidence that the repository is secret-free.

### Planned, not in place

The following are control-plane work. None of them is implemented, and none may
be cited as a control:

- SBOM generation.
- Vulnerability scanning of the pinned closure.
- Artifact signing.
- Full secret scanning, including entropy and history-aware detection.

Until these exist, the supply-chain posture of this repository rests on the lock
digest check, the lint and type gates, the narrow credential grep, and the
license ledger in `docs/LICENSES.md`. That is the honest list. The planned
controls do not reduce the risk the admission test is built to catch; they
reduce the consequence of getting it wrong.
