"""A goal marked LANDED must cite evidence that production actually runs.

THE FINDING THIS EXISTS TO CATCH
================================
Twenty-one library modules are listed as `evidence` on goals the registry marks `LANDED`,
and **no module outside `tests/` imports any of them.** A test importing a module proves the
module works. It does not prove anything reaches it. Every other gate here compares published
figures against the tree, so all of them were green while this was true.

Two levels, because they are different failures:

**Three goals have NO live library evidence at all:**

- **G090 Feature Fabric** -- `core/feature_store.py` is its only library evidence and nothing
  imports it.
- **G130 Robust Portfolio Brain** -- `communities/c9_portfolio/optimizer.py`, unimported.
- **G160 Execution Digital Twin** -- `simulation/execution_twin.py`, unimported. This is also
  why layer 21 has no screen: the twin is not on any production path.

**Eighteen more are dead modules inside otherwise-live goals.** The sharpest is G110
"Calibration and Selective Decision", whose summary promises:

    "Conformal calibration producing a calibrated probability, an uncertainty band, and a
     decision of TRADE, WAIT, ESCALATE, or ABSTAIN, where ABSTAIN is the default under
     uncertainty."

Its `core/conformal.py` and `core/decision_gate.py` are imported by nothing. The selective
decision gate ARCHITECTURE.txt section 12 places between "Certified playbook found" and
"Selective Decision = TRADE" does not run by that path. Nor is the capability missing:
`kernel/playbook.py` carries a live TRADE/WAIT/ESCALATE/ABSTAIN router wired through
`kernel/bootstrap.py` and `core/capital_firewall.py`. **The registry points at a dead
parallel implementation of a capability that is live somewhere else.**

The other three dead modules of G180 -- `kernel/memory_tiers.py`,
`kernel/retrieval_contract.py`, `kernel/counterfactuals.py` -- are why layer 23 has no
meaningful screen: Institutional Memory has a full tier and counterfactual implementation
and NO producer.

WHY TWO ALLOWLISTS, AND WHY THEY SHRINK
======================================
Every known instance is listed with a reason, because "wire it" or "correct the evidence"
is a per-goal product decision, not a lint fix. Both lists SELF-CLEAR: if a listed goal ever
gains a live module, or a listed module ever gains an importer, the gate fails and the entry
must be deleted. Debt that cannot be paid off is not debt, it is a permanent amnesty.

WHAT IS DELIBERATELY NOT CHECKED
================================
Only `.py` under library packages. `scripts/` entry points, `specs/` TLA+ files and `tests/`
are exempt: a script is *meant* to be run rather than imported.

KNOWN LIMIT, STATED RATHER THAN IMPLIED
=======================================
This is a textual import check. It cannot see a module reached only by
`importlib.import_module`, by re-export, or by attribute access through a registry, and it
does not claim the imported path is *exercised at runtime* -- only that something outside the
test suite references it. Only two modules in the tree use dynamic import
(`scripts/lock_dependencies.py`, `scripts/production_check.py`), so the blind spot is small
rather than absent.

TWO BUGS THIS GATE SHIPPED WITH, BOTH CAUGHT HERE
=================================================
Recorded because the failure mode was invisible, not because it is interesting. First, the
exclusion test `".venv" in parts` did not match `.venv-fresh`, so 4794 virtualenv modules
were counted as first-party. Second and worse: reusing a compiled regex's `.pattern`
DISCARDS its flags, so `^` anchored to the start of each file and found zero importers
anywhere -- reporting 21 of 23 LANDED goals as dead, including `core/control_plane.py`,
which `api/server.py` imports on line 42. A verification artifact that is confidently wrong
is worse than none, so `importer_pattern()` compiles from the template with `re.M` attached
and both defects are commented at the code that would reintroduce them.

Run:  python scripts/verify_landed_evidence_is_live.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
REGISTRY = REPO / "docs" / "goals" / "goals.json"

#: Evidence under these prefixes is a library module and must have a production importer.
LIBRARY_PREFIXES = (
    "core/",
    "kernel/",
    "api/",
    "communities/",
    "simulation/",
    "research/",
    "schemas/",
)

#: Directories that are never first-party source, however they are named.
SKIP_DIR_PARTS = {"tests", "node_modules", "site-packages", "__pycache__", "alembic"}

#: LANDED goals with NO live library evidence, and why each is tolerated for now.
KNOWN_DEAD_GOALS: dict[str, str] = {
    "G090": "core/feature_store.py is the entire Feature Fabric and nothing imports it. "
    "Either the online feature path is not live or the evidence is stale. Highest-value "
    "item here: ARCHITECTURE.txt section 12 places the Feature Fabric before the Fast "
    "Expert Model.",
    "G130": "communities/c9_portfolio/optimizer.py is unimported while portfolio proposals "
    "are built by the live portfolio path, so this looks like a superseded optimizer "
    "rather than a missing brain.",
    "G160": "simulation/execution_twin.py -- the Execution Digital Twin -- has no "
    "production caller. Its only consumer is tests/test_execution_twin.py, which is also "
    "why layer 21 has no screen.",
}

#: Dead evidence modules inside goals that DO have other live evidence.
KNOWN_DEAD_MODULES: dict[str, str] = {
    "core/security_master_store.py": "superseded by core/security_master.py, which is live",
    "core/seed_ingest.py": "seed ingestion has no production caller; the seed bundle is "
    "consumed by tests and the bootstrap path",
    "core/temporal.py": "point-in-time behaviour is carried by the replay fetcher instead",
    "core/dataset_version_sink.py": "unimported alongside core/temporal.py",
    "core/claim_writers.py": "the claim LEDGER (core/claim_ledger.py) is live, so this is "
    "probably a superseded writer rather than a missing capability",
    "core/policy_bundles.py": "unimported while agent governance is enforced by "
    "kernel/tool_governance.py, which is live. Resolve this one first: governance that "
    "works by a different path is worth confirming rather than assuming.",
    "kernel/factors.py": "factor definitions unimported while kernel/competence.py is live",
    "kernel/strategies.py": "strategy kernels unimported; the strategy agent is reached "
    "through communities/c4_strategy",
    "research/reporting.py": "unimported reporting helpers",
    "communities/c10_world/change_detection.py": "change detection unimported while the "
    "regime engine itself is live -- so change detection may not be on the regime path",
    "core/conformal.py": "DEAD PARALLEL IMPLEMENTATION. G110's summary promises conformal "
    "calibration; kernel/playbook.py is the live router. The registry cites a module that "
    "does not run.",
    "core/decision_gate.py": "DEAD PARALLEL IMPLEMENTATION. The TRADE/WAIT/ESCALATE/ABSTAIN "
    "gate that ARCHITECTURE.txt section 12 places before 'Selective Decision = TRADE' is "
    "live as kernel/playbook.py, not here.",
    "core/playbook_store.py": "the playbook ENGINE (kernel/playbook.py) is live; this store "
    "is not",
    "communities/c5_execution/algorithms.py": "execution algorithms unimported while the OMS "
    "and adapters are live -- worth confirming execution does not bypass its own algorithms",
    "kernel/memory_tiers.py": "G180's memory tiering has no producer, so nothing scores or "
    "expires a record. This is why layer 23 cannot have a meaningful screen.",
    "kernel/retrieval_contract.py": "the retrieval contract is never evaluated in "
    "production, so retrieval quality is unmeasured",
    "kernel/counterfactuals.py": "CounterfactualStore is instantiated NOWHERE outside tests. "
    "Every ABSTAIN/REJECT/NO_NEW_RISK restraint should retain one and nothing does.",
}

#: LANDED goals whose stated guarantee is verified ONLY against evidence that no production
#: module imports. Every gate test in these goals passes, comprehensively, about code that does
#: not run -- so the invariant is real as a statement about the module and vacuous as a
#: statement about the system.
VACUOUS_GATES: dict[str, str] = {
    "G090": "test_feature_parity.py imports only the dead core/feature_store.py. The "
    "offline/online parity invariant -- 'a model trained on one is served the other' -- is "
    "therefore verified for nothing. Production computes transforms inline in "
    "simulation/replay_runner.py; core/indicators.py serves only a chart view. This is the "
    "highest-consequence entry: it is the exact failure G090 exists to prevent.",
    "G110": "test_decision_gate.py and test_conformal.py test the dead pair while the live "
    "TRADE/WAIT/ESCALATE/ABSTAIN router is kernel/playbook.py, which no goal gate covers.",
    "G160": "test_execution_twin.py tests the dead twin. G160's whole subject is unwired, "
    "which is also why layer 21 has no screen.",
    "G130": "test_portfolio_brain.py does not reach the live portfolio path; "
    "communities/c9_portfolio/optimizer.py is the goal's only evidence and is unimported.",
    "G150": "test_execution_algorithms.py tests communities/c5_execution/algorithms.py, "
    "which nothing imports -- worth confirming execution does not bypass its own algorithms.",
    "G060": "test_quant_factory.py touches none of kernel/factors.py, kernel/strategies.py "
    "or research/reporting.py, all three of which are unimported.",
}

IMPORT_LINE = r"^\s*(?:from|import)\s+\S*\b{module}\b"


def importer_pattern(module: str) -> re.Pattern[str]:
    """Compiled with re.M every time -- see the module docstring."""
    return re.compile(IMPORT_LINE.format(module=re.escape(module)), re.M)


def production_modules() -> set[str]:
    """Every first-party module outside the test suite, repo-relative with '/' separators."""
    out: set[str] = set()
    for path in REPO.rglob("*.py"):
        parts = path.relative_to(REPO).as_posix().split("/")
        if any(part in SKIP_DIR_PARTS or part.startswith(".") for part in parts):
            continue
        out.add(path.relative_to(REPO).as_posix())
    return out


def main() -> int:
    goals = json.loads(REGISTRY.read_text(encoding="utf-8"))["goals"]
    prod = production_modules()
    sources = {rel: (REPO / rel).read_text(encoding="utf-8", errors="replace") for rel in prod}

    def is_live(entry: str) -> bool:
        pattern = importer_pattern(pathlib.Path(entry).stem)
        return any(
            rel != entry and pattern.search(text) for rel, text in sources.items()
        )

    failures: list[str] = []
    dead_modules: list[str] = []
    barren_goals: list[str] = []
    owner: dict[str, str] = {}

    for goal in goals:
        if goal.get("status") != "LANDED":
            continue
        # Citing a file that is not in the tree is its own kind of false claim, so it is
        # reported rather than filtered out. An earlier version skipped these, which meant a
        # newly invented evidence path was accepted silently -- the mutation harness caught
        # exactly that, and the fix is here rather than in the harness.
        cited = [
            e
            for e in goal.get("evidence", [])
            if e.endswith(".py") and e.startswith(LIBRARY_PREFIXES)
        ]
        missing = [e for e in cited if e not in prod]
        for entry in missing:
            failures.append(
                f"{goal['id']} cites {entry} as evidence but no such file is in the tree: "
                f"evidence must name something that exists"
            )

        evidence = [e for e in cited if e in prod]
        if not evidence:
            continue
        dead = [e for e in evidence if not is_live(e)]
        if not dead:
            continue
        dead_modules.extend(dead)
        for entry in dead:
            owner.setdefault(entry, goal["id"])
        if len(dead) == len(evidence):
            barren_goals.append(goal["id"])

    landed = sum(1 for g in goals if g.get("status") == "LANDED")
    print(f"first-party production modules : {len(prod)}")
    print(f"LANDED goals in the registry   : {landed}")
    print()

    print("goals with NO live library evidence:")
    for gid in sorted(barren_goals):
        note = KNOWN_DEAD_GOALS.get(gid)
        print(f"  {gid}  {'documented' if note else 'UNDOCUMENTED'}")
    print()
    print(f"dead evidence modules in otherwise-live goals: {len(dead_modules) - len(barren_goals)}")
    print(f"total dead evidence modules                 : {len(dead_modules)}")

    # --- a goal's GUARANTEE must be verified against code that runs --------------
    # Distinct from the checks above. A goal can have perfectly good live evidence and
    # still have every gate test aimed at its dead modules, which makes the stated
    # invariant true of a file and false of the system.
    def gate_tests(goal: dict[str, object]) -> list[str]:
        out: list[str] = []
        for gate in goal.get("gates", []) or []:
            found = re.search(r"test:(\S+)", str(gate.get("check", "")))
            if found and (REPO / found.group(1)).is_file():
                out.append(found.group(1))
        return out

    def touches(entry: str, texts: list[str]) -> bool:
        pattern = importer_pattern(pathlib.Path(entry).stem)
        return any(pattern.search(text) for text in texts)

    vacuous_now: list[str] = []
    for goal in goals:
        if goal.get("status") != "LANDED":
            continue
        evidence = [
            e
            for e in goal.get("evidence", [])
            if e.endswith(".py") and e.startswith(LIBRARY_PREFIXES) and e in prod
        ]
        dead = [e for e in evidence if not is_live(e)]
        if not dead:
            continue
        texts = [
            (REPO / t).read_text(encoding="utf-8", errors="replace")
            for t in gate_tests(goal)
        ]
        live_evidence = [e for e in evidence if is_live(e)]
        if live_evidence and any(touches(e, texts) for e in live_evidence):
            continue
        vacuous_now.append(goal["id"])
        if goal["id"] not in VACUOUS_GATES:
            failures.append(
                f"{goal['id']} is LANDED with dead evidence ({', '.join(dead)}) and none of "
                f"its gate tests reach live evidence: its guarantee is verified only against "
                f"code no production module imports. Declare it in VACUOUS_GATES with a "
                f"reason, wire it, or point the gate at live code"
            )

    for gid in VACUOUS_GATES:
        if gid not in vacuous_now:
            failures.append(
                f"{gid} is in VACUOUS_GATES but its gates now reach live evidence -- "
                f"delete the entry, the debt is paid"
            )

    print(f"goals whose gates reach NO live evidence    : {len(vacuous_now)} "
          f"{sorted(vacuous_now)}")

    # --- undocumented instances fail -------------------------------------------
    for gid in sorted(barren_goals):
        if gid not in KNOWN_DEAD_GOALS:
            failures.append(
                f"{gid} is LANDED but no production module imports any of its library "
                f"evidence: declare it in KNOWN_DEAD_GOALS with a reason, wire it, or "
                f"correct the evidence"
            )
    for entry in sorted(set(dead_modules)):
        # A module inside a goal already documented at goal level is not double-reported:
        # the goal entry carries the reason for the whole set.
        if entry not in KNOWN_DEAD_MODULES and owner.get(entry) not in KNOWN_DEAD_GOALS:
            failures.append(
                f"{entry} is LANDED evidence that no production module imports and is not "
                f"in KNOWN_DEAD_MODULES: declare it with a reason, wire it, or correct the "
                f"evidence"
            )

    # --- self-clearing: a listed instance that now has a live path is stale debt ---
    for gid, reason in KNOWN_DEAD_GOALS.items():
        goal = next((g for g in goals if g["id"] == gid), None)
        if goal is None:
            failures.append(f"{gid} is in KNOWN_DEAD_GOALS but is not in the registry")
            continue
        evidence = [
            e
            for e in goal.get("evidence", [])
            if e.endswith(".py") and e.startswith(LIBRARY_PREFIXES) and e in prod
        ]
        live = [e for e in evidence if is_live(e)]
        if live:
            failures.append(
                f"{gid} is in KNOWN_DEAD_GOALS but {', '.join(live)} now HAS a production "
                f"importer -- delete the entry, the debt is paid"
            )
    for entry in KNOWN_DEAD_MODULES:
        if entry not in dead_modules and entry in prod:
            failures.append(
                f"{entry} is in KNOWN_DEAD_MODULES but now HAS a production importer -- "
                f"delete the entry, the debt is paid"
            )

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL {failure}")
        print(f"\n{len(failures)} check(s) failed")
        return 1

    print(
        f"landed-evidence gate green: {len(barren_goals)} barren goal(s), "
        f"{len(dead_modules)} dead module(s), {len(vacuous_now)} vacuous-gate goal(s), "
        f"all documented, 0 undocumented"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
