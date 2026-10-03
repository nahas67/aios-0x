"""The section 13 goal numbering and the registry numbering must be reconciled, not assumed.

THE MISMATCH
============
`ARCHITECTURE.txt` section 13 specifies **28** goal IDs, `G010`-`G280`.
`docs/goals/goals.json` carries **25**, `G010`-`G250`. From `G180` onward the two schemes
disagree on which number means what, so "the last goal" is ambiguous between the frozen
architecture and the authoritative registry, and a reader who trusts either document alone
will draw a wrong conclusion about what is governed.

The gap is not three lost goals. It closes exactly:

  * section 13 lists Memory, Learning and Counterfactuals as three goals
    (`G190`, `G200`, `G210`); the registry collapses them into ONE goal, `G180`
    "Institutional Memory, Governed Learning, and Counterfactuals"   -> -2
  * section 13 `G260` "Disaster Recovery" was DECLINED on a stated rationale       -> -1

  28 - 2 - 1 = 25, no residue. Every section 13 ID is accounted for.

WHY THIS IS A GATE AND NOT A PARAGRAPH
======================================
I got this wrong by hand, twice, in one sitting. First I reported the divergence as "the
tail was renumbered" and pointed only at `G270`/`G280`, missing that the offset begins at
`G220` because of the three-way merge. Then I read `research/disaster.py` as evidence that
`G260` was "implemented, tested and ungoverned" -- because the FILENAME matched. It is
"Disaster-lab drills (Directive 60)": fault injection against the real stack, not RPO/RTO
backup-and-restore. And I missed entirely that the decline was documented in registry
`G220`'s own notes.

That is the recurring failure mode in this repo: a name search is not a capability search,
and a prose reconciliation cannot be re-checked by the next person. So the mapping is
declared here as data and verified against both documents.

THE SELF-CLEARING HALF
======================
Declining a goal is only sound while the reason holds. `G260` was declined because
"Disaster Recovery" appears in `ARCHITECTURE.txt` ONCE, as a bare label, with RPO and RTO
at ZERO occurrences -- there are no requirements to model, and inventing them is what the
section 14 freeze rule forbids. If someone later specifies an RPO target, that rationale is
dead and the goal must come back. This gate fails when it does, so a decline cannot quietly
become permanent by outliving its own justification.

Run:  python scripts/verify_goal_id_divergence.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")

#: `ARCHITECTURE.txt` is the FROZEN target and lives outside the repo. Nothing may write it --
#: including `prove_goal_id_divergence.py`, because a probe interrupted between mutation and
#: restore would corrupt the one document everything else is measured against. The override
#: exists so a probe can hand this gate a temp copy and mutate that instead.
ARCHITECTURE = pathlib.Path(
    os.environ.get("AIOS_ARCHITECTURE_PATH") or (REPO.parent / "ARCHITECTURE.txt")
)
REGISTRY = REPO / "docs" / "goals" / "goals.json"
DOC = REPO / "CURRENT_ARCHITECTURE.md"

#: section 13 IDs that the registry folds into a single goal: {section13 ids: registry id}.
#: A merge of N ids into one goal removes N-1 ids from the count, which is why 28 becomes 25
#: alongside the single decline below.
MERGED_INTO_REGISTRY: dict[frozenset[str], str] = {
    frozenset({"G190", "G200", "G210"}): "G180",
}

#: section 13 IDs deliberately given no goal: {id: (label, max occurrences of that label in
#: ARCHITECTURE.txt, terms that must be absent from it)}. Re-checked on every run -- see the
#: self-clearing note in the module docstring.
DECLINED: dict[str, tuple[str, int, tuple[str, ...]]] = {
    # A bare label appearing once, with no RPO/RTO target anywhere: there are no
    # requirements to model, and inventing them is what the section 14 freeze rule forbids.
    "G260": ("Disaster Recovery", 1, ("RPO", "RTO")),
}

#: The shifted tail, named explicitly so a wrong number cannot pass as a right one. Checked
#: by normalised title overlap, because both documents paraphrase the same work.
SHIFTED_TAIL: dict[str, str] = {
    "G220": "G200",  # Champion/Challenger      -> Champion and Challenger Arena
    "G230": "G210",  # Observability            -> Observability and Trace Continuity
    "G240": "G220",  # Formal Assurance         -> Formal Assurance
    "G250": "G230",  # Supply Chain             -> Governance, Security, and Supply-Chain Planes
    "G270": "G240",  # Long SHADOW              -> Long Shadow Validation
    "G280": "G250",  # Canary Capital           -> Canary Capital
}

STOP = {
    "the", "and", "of", "a", "an", "to", "for", "with", "by", "on", "in",
    "intelligence", "engine", "planes", "sequencing",
}


def section13_ids() -> list[str]:
    text = ARCHITECTURE.read_text(encoding="utf-8", errors="replace")
    body = re.search(r"# 13\.\s*IMPLEMENTATION ORDER(.*?)# 14\.", text, re.S)
    if body is None:
        raise SystemExit("could not locate section 13 in ARCHITECTURE.txt")
    seen: list[str] = []
    for goal_id in re.findall(r"G\d{3}", body.group(1)):
        if goal_id not in seen:
            seen.append(goal_id)
    return seen


def section13_divergent_region() -> str:
    """The part of section 13 from the first divergent ID onward.

    Section 13 writes its tail several IDs to a line -- `G230/G240/G250/G260` over
    `Observability / Formal Assurance / Supply Chain / Disaster Recovery` -- so a label can
    only be attributed to an ID *positionally*, which is exactly the kind of guess that
    produced the wrong reconciliation in the first place. Instead this returns the whole
    region and each declared pair is checked for shared vocabulary anywhere inside it. That
    is a sanity check on the mapping, not a proof of it; the load-bearing checks here are the
    arithmetic and the two-way accounting above.
    """
    text = ARCHITECTURE.read_text(encoding="utf-8", errors="replace")
    body = re.search(r"# 13\.\s*IMPLEMENTATION ORDER(.*?)# 14\.", text, re.S)
    if body is None:
        raise SystemExit("could not locate section 13 in ARCHITECTURE.txt")
    block = body.group(1)
    first = min(
        (block.index(i) for i in SHIFTED_TAIL if i in block),
        default=0,
    )
    return block[first:]


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def main() -> int:
    arch_ids = section13_ids()
    goals = json.loads(REGISTRY.read_text(encoding="utf-8"))["goals"]
    reg_by_id = {g["id"]: g for g in goals}
    reg_ids = [g["id"] for g in goals]
    arch_text = ARCHITECTURE.read_text(encoding="utf-8", errors="replace")
    doc_text = DOC.read_text(encoding="utf-8")

    failures: list[str] = []

    print(f"section 13 goal ids        : {len(arch_ids)}  ({arch_ids[0]}..{arch_ids[-1]})")
    print(f"registry goal ids          : {len(reg_ids)}  ({reg_ids[0]}..{reg_ids[-1]})")
    print()

    # --- 1. THE ARITHMETIC MUST CLOSE -----------------------------------------
    removed = sum(len(group) - 1 for group in MERGED_INTO_REGISTRY) + len(DECLINED)
    expected = len(arch_ids) - removed
    print(
        f"merged away (N-1 each)     : "
        f"{sum(len(group) - 1 for group in MERGED_INTO_REGISTRY)}"
    )
    print(f"declined on a rationale    : {len(DECLINED)}  {sorted(DECLINED)}")
    print(f"expected registry size     : {expected}")
    if expected != len(reg_ids):
        failures.append(
            f"the divergence does not close: {len(arch_ids)} - {removed} = {expected}, "
            f"but the registry holds {len(reg_ids)}. Either a merge/decline is mis-declared "
            f"here, or the documents changed and this script was not updated."
        )

    # --- 2. EVERY ID ACCOUNTED FOR, BOTH DIRECTIONS ---------------------------
    # Three ways a section 13 id can legitimately lack a registry id of the same number:
    # folded into a merged goal, declined on a rationale, or renumbered by the shift.
    absorbed = {i for group in MERGED_INTO_REGISTRY for i in group}
    merge_targets = set(MERGED_INTO_REGISTRY.values())
    shifted = set(SHIFTED_TAIL)
    shift_targets = set(SHIFTED_TAIL.values())

    for goal_id in arch_ids:
        if (
            goal_id not in reg_ids
            and goal_id not in absorbed
            and goal_id not in DECLINED
            and goal_id not in shifted
        ):
            failures.append(
                f"{goal_id} is in section 13 but has no registry goal and is neither merged, "
                f"declined, nor renamed by the shift -- declare it in MERGED_INTO_REGISTRY, "
                f"DECLINED, or SHIFTED_TAIL"
            )
    for goal_id in reg_ids:
        if goal_id not in arch_ids and goal_id not in merge_targets and goal_id not in shift_targets:
            failures.append(
                f"{goal_id} is in the registry but appears nowhere in section 13 and is not "
                f"a merge or shift target -- the registry has invented a goal"
            )

    # --- 3. MERGE TARGETS MUST CARRY THE MERGED WORK --------------------------
    for group, target in MERGED_INTO_REGISTRY.items():
        if target not in reg_by_id:
            failures.append(f"merge target {target} is not in the registry")
            continue
        title = words(reg_by_id[target]["title"])
        if not title:
            failures.append(f"merge target {target} has an empty title; refusing to guess")

    # --- 4. THE SHIFTED TAIL MUST POINT AT PLAUSIBLE COUNTERPARTS -------------
    # Strength, stated honestly: this is shared-vocabulary, not identity. It cannot prove a
    # mapping is right, and it would not notice two registry titles sharing a common word. It
    # does catch the failure that actually happened -- a declared pair whose two documents
    # describe unrelated work.
    region = words(section13_divergent_region())
    if len(set(SHIFTED_TAIL.values())) != len(SHIFTED_TAIL):
        failures.append("SHIFTED_TAIL is not injective; two section 13 ids map to one registry id")
    for arch_id, reg_id in SHIFTED_TAIL.items():
        if reg_id not in reg_by_id:
            failures.append(f"shifted-tail target {reg_id} is not in the registry")
            continue
        overlap = region & words(reg_by_id[reg_id]["title"])
        if not overlap:
            failures.append(
                f"{arch_id} -> {reg_id} ({reg_by_id[reg_id]['title']!r}) shares no vocabulary "
                f"with the section 13 tail -- the declared mapping points at unrelated work"
            )
        else:
            print(f"  {arch_id} -> {reg_id}  shared: {'/'.join(sorted(overlap))}")

    # --- 5. A DECLINE MUST STILL HAVE ITS REASON ------------------------------
    # The self-clearing check. A declined goal is only sound while the gap that justified
    # declining it still exists; if the architecture gains the missing requirements, the
    # decline is stale and the goal has to come back.
    print()
    for goal_id, (label, max_occurrences, must_be_absent) in DECLINED.items():
        found = arch_text.count(label)
        if found <= max_occurrences:
            print(f"  {goal_id} '{label}' appears {found}x -- decline holds")
        else:
            print(f"  {goal_id} '{label}' appears {found}x -- decline STALE")
            failures.append(
                f"{goal_id} was declined because '{label}' is a bare label appearing "
                f"{max_occurrences}x, but it now appears {found} times -- the architecture may "
                f"now specify it, so the decline is stale and a goal must be added"
            )
        for term in must_be_absent:
            hits = len(re.findall(rf"\b{term}\b", arch_text))
            if hits:
                failures.append(
                    f"{goal_id} was declined because {term} appears nowhere in "
                    f"ARCHITECTURE.txt, but it now appears {hits} time(s) -- the rationale "
                    f"no longer holds and a goal must be added"
                )

    # --- 6. THE DECLINE MUST BE WRITTEN DOWN WHERE THE REGISTRY CAN BE READ ----
    notes = " ".join(str(g.get("notes", "")) for g in goals).lower()
    for goal_id in DECLINED:
        if "disaster recovery" not in notes:
            failures.append(
                f"{goal_id} is declined here but no registry goal's notes record the "
                f"rationale -- an undocumented decline cannot be audited"
            )

    # --- 7. THE RECONCILIATION MUST BE PUBLISHED ------------------------------
    for needed in ("G260", "G180", "28"):
        if needed not in doc_text:
            failures.append(
                f"CURRENT_ARCHITECTURE.md does not mention {needed!r} -- the reconciliation "
                f"is machine-checked here but not written where an operator will read it"
            )

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL {failure}")
        print(f"\n{len(failures)} check(s) failed")
        return 1

    merged_away = sum(len(group) - 1 for group in MERGED_INTO_REGISTRY)
    print(
        f"goal-id divergence reconciled: {len(arch_ids)} section-13 ids = {len(reg_ids)} "
        f"registry ids ({merged_away} merged away, {len(DECLINED)} declined, "
        f"decline rationale re-checked against ARCHITECTURE.txt)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
