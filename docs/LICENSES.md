# AIOS-0X License Policy

## The rule

Every new dependency and every vendored asset must have its license recorded in
this file and in the adopting ADR, before merge. A contribution carrying
unknown, missing, or incompatible licensing is not admissible and is not merged
pending clarification.

This is a screening rule, not a formality. The license is recorded at the moment
of adoption, because license facts decay: a project relicenses, a transitive
dependency changes its terms, an extra graduates from optional to required. A
ledger written at adoption time and never amended is a ledger that is already
wrong.

## License admissibility

| Category | Licenses | Admissibility |
| :--- | :--- | :--- |
| **PERMISSIVE** | MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, PSF-2.0 and equivalents | Admissible anywhere, including the deterministic financial core. No isolation argument required. |
| **WEAK COPYLEFT** | LGPL, MPL-2.0, EPL | Admissible only with a documented isolation argument recorded in the ADR: dynamic linking, or no source redistribution of the combined work. A weak-copyleft obligation that cannot be discharged by the deployment model is not admissible. |
| **STRONG COPYLEFT** | GPL-3.0, AGPL-3.0 | **INADMISSIBLE as a runtime dependency.** Patterns may be reimplemented in AIOS code with attribution recorded, but the code must not be imported, vendored, or linked. AGPL is additionally inadmissible even for a network-exposed service, so a self-hosted or embedded FinceptTerminal-class component is out of bounds entirely. |
| **NO LICENSE FILE** | absent | **INADMISSIBLE.** An absent license is "all rights reserved", not "free". Default copyright applies. |
| **NON-COMMERCIAL / RESEARCH-ONLY / CUSTOM** | bespoke terms restricting use | **INADMISSIBLE** for anything on a capital path. Admissible only in research or evaluation tooling that cannot reach a venue. |

The deterministic financial core — ledger, risk firewall, authorization,
execution, reconciliation — takes PERMISSIVE only. Weak copyleft is permitted
behind a contract boundary in the market/quant and AI/research zones; strong
copyleft and unlicensed code are permitted nowhere.

## Reference patterns

The projects below were examined during design and technology acquisition. They
are recorded for study and lineage only.

**Listing a project here confers no permission to use it and is not an
endorsement.** Presence in this table is not an admission decision. An admission
decision is made by ADR, against the categories above, at adoption time.

| Project | License | Note |
| :--- | :--- | :--- |
| anthropics/skills | Mixed | Most components Apache-2.0; document skills are source-available, not open source. |
| obra/superpowers | MIT | |
| mem0ai/mem0 | Apache-2.0 | |
| HKUDS/Vibe-Trading | MIT | |
| plur-ai/plur | Apache-2.0 | |
| diqierjia/StrataGate-AgentMemory | MIT | |
| Graphify-Labs/graphify | Apache-2.0 | |
| Egonex-AI/Understand-Anything | MIT | |
| alphaXiv/OpenResearch | MIT | |
| NandhaKishorM/laya | Apache-2.0 | |
| guangxiangdebizi/FinanceMCP | MIT | |
| JerBouma/FinanceDatabase | MIT | |
| Panniantong/Agent-Reach | MIT | |
| Untrivial-ai/agent-orchestrator | Apache-2.0 | |
| sopersone/cabbage-trading-machine | Apache-2.0 | |
| zjunlp/SkillNet | MIT | |
| Sumanth077/Hands-On-AI-Engineering | MIT | |
| ayghri/i-have-adhd | MIT | |
| mobile-next/mobile-mcp | Apache-2.0 | |
| earendil-works/pi | MIT | |
| gnekt/My-Brain-Is-Full-Crew | MIT | |
| The-Swarm-Corporation/AutoHedge | MIT | |

### Entries requiring an individual note

**Fincept-Corporation/FinceptTerminal — AGPL-3.0-or-later.**
Inadmissible as a dependency. Three mechanisms are recorded here as study
results and may be reimplemented in Python: the DataHub one-fetch /
many-subscribers topic pub-sub, the TopicPolicy freshness/TTL contract, and the
`BaseRepository<T>` pattern. Reimplementation means independent code written
against the described behaviour. The AGPL text must not be copied verbatim into
AIOS code, comments, or documentation. No linking of any kind is permitted, and
no derived work may be distributed. GitHub's license classifier reports
`NOASSERTION` for this repository because the copyright header is customized;
the `LICENSE` file is the AGPL v3 text carrying the "or any later version"
grant, so the category is STRONG COPYLEFT, not "unlicensed".

**666ghj/MiroFish — AGPL-3.0.**
Inadmissible as a dependency and inadmissible as a basis for adoption. This
entry corrects an earlier working assumption that the repository carried no
license file. The repository does ship a `LICENSE`; it is the GNU Affero
General Public License v3. The disposition is unchanged — AGPL-3.0 is strong
copyleft, and STRONG COPYLEFT is inadmissible — but the reason is the license
that is present, not the license that is missing.

**GenAI-Security-Project/agent-control-standard — code Apache-2.0,
specification prose CC BY-SA 4.0.**
The code and the prose carry different terms and must be treated separately.
Porting the hook contract to Python is an independent reimplementation: a hook
contract is an interface, and an independently written implementation of an
interface is not a derivative work of the source. If any CC BY-SA specification
prose is copied rather than independently written, it must be attributed and the
resulting document carries share-alike terms on the copied material.

## Current dependency license ledger

Version bounds are the declarations in `pyproject.toml`; pins are the resolved
versions in `requirements.lock`. Licenses were read from installed package
metadata in this repository's environment. Where that was not possible, the
source is named at the point of use below.

| Dependency | Bound (lock pin) | License | Category | Admissible |
| :--- | :--- | :--- | :--- | :--- |
| pydantic | `>=2.12,<3` (2.12.5) | MIT | Permissive | Yes |
| pydantic-settings | `>=2.13,<3` (2.13.1) | MIT | Permissive | Yes |
| httpx | `>=0.28,<0.29` (0.28.1) | BSD-3-Clause | Permissive | Yes |
| psycopg[binary] (`postgres`) | `>=3.3,<4` (3.3.4) | LGPL-3.0-only | Weak copyleft | Yes as an optional extra; the isolation argument is owed and not yet recorded |
| nats-py (`nats`) | `>=2.15,<3` (2.15.0) | Apache-2.0 | Permissive | Yes |
| ccxt (`ccxt`) | `>=4.5,<5` (4.5.74) | MIT | Permissive | Yes |
| qdrant-client (`qdrant`) | `>=1.19,<2` (not in lock) | Apache-2.0 | Permissive | Yes |
| pytest (`dev`) | `>=9.0,<10` (9.0.2) | MIT | Permissive | Yes |
| pytest-asyncio (`dev`) | `>=1.4,<2` (1.4.0) | Apache-2.0 | Permissive | Yes |
| pytest-timeout (`dev`) | `>=2.3,<3` (2.4.0) | MIT | Permissive | Yes |
| pytest-xdist (`dev`) | `>=3.8,<4` (3.8.0) | MIT | Permissive | Yes |
| ruff (`dev`) | `>=0.16,<0.17` (0.16.4) | MIT | Permissive | Yes |
| mypy (`dev`) | `>=2.3,<3` (2.3.1) | MIT | Permissive | Yes |

The `all` extra repeats the four backend extras and adds no new license.

One entry above is outside the lock. `qdrant-client` is declared in
`pyproject.toml` but does not appear in `requirements.lock`, which is generated
for the `dev,postgres,nats,ccxt` extras. Its license was read from published
package metadata, not from a local install. It is Apache-2.0.

One obligation in this table is open. `psycopg` is weak copyleft, so it is
admissible only with a documented isolation argument recorded in an ADR, and no
such argument exists yet. ADR-005 records the opposite position: the SQLite tier
is the only shipped financial backend, and `BaseFinancialStore` is the adapter
seam through which a PostgreSQL tier would arrive. The obligation falls due
before the PostgreSQL tier is promoted from extra to default, not before the
extra is used in a test environment.

The three runtime dependencies are entirely permissive. The wider pinned
closure is not, and the difference is worth stating plainly rather than rounding
away. `requirements.lock` pins 52 packages. 49 of them are installed in this
environment and their licenses were read from their own `METADATA` files. Three
are not installed; their licenses were read from published package metadata. Two
installed packages carry no `License` field and were also resolved from
published metadata. Every one of the 52 is accounted for.

Weak copyleft is present in the closure:

| Package | Pin | License | Source |
| :--- | :--- | :--- | :--- |
| psycopg | 3.3.4 | LGPL-3.0-only | installed metadata |
| psycopg-binary | 3.3.4 | LGPL-3.0-only | installed metadata |
| certifi | 2025.11.12 | MPL-2.0 | installed metadata |
| orjson | 3.11.9 | MPL-2.0 AND (Apache-2.0 OR MIT) | installed metadata |
| pathspec | 1.1.1 | MPL-2.0 | published metadata; no license field installed |

The `orjson` expression is a conjunction, not a choice: the MPL-2.0 obligation
applies alongside the permissive Apache-2.0-or-MIT option, so the package is
weak copyleft for policy purposes.

The three packages that are not installed here:

| Package | Pin | License | Category | Source |
| :--- | :--- | :--- | :--- | :--- |
| colorama | 0.4.6 | BSD (upstream classifier does not name a version) | Permissive | published metadata |
| packaging | 26.0 | Apache-2.0 OR BSD-2-Clause | Permissive, dual-licensed | published metadata |
| Pygments | 2.19.2 | BSD-2-Clause | Permissive | published metadata |

`annotated-types` is installed but its metadata carries no license field; its
published license is MIT.

No package in the closure is strong copyleft, unlicensed, or restricted to
non-commercial use. Preserving the permissive runtime core while the closure
picks up weak copyleft in a transport package, a test-runner dependency, and the
optional PostgreSQL driver is the deliberate property. A future change that
introduces strong copyleft, a non-commercial term, or a missing license into the
closure is refused against the admissibility table above, without further
discussion.

## Attribution practice for reimplemented patterns

When a pattern is reimplemented rather than imported, the adopting ADR records
three things: the source project, the license it was read under, and the
specific mechanism taken. Not the general idea — the mechanism, named.

The purpose is that lineage stays auditable without a code dependency. Six
months later, the question "where did this come from" must have an answer that
does not require reading a commit that no longer exists. Attribution also keeps
the reimplementation defensible: an independent implementation of a described
behaviour is not a derivative work, and the record is what shows that.

Attribution appears in the ADR. It does not require a header comment on every
function, and it does not require a NOTICE file. The lineage must be findable,
not verbose.
