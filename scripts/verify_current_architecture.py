"""Verify every factual claim in CURRENT_ARCHITECTURE.md against the tree.

A status document that lies is worse than no status document: it is the thing a reader
trusts instead of looking. One claim was already wrong when this file was written --
`PlatformEventType` was recorded as 15 types and is 19 -- and the pre-existing
CHECKPOINT.md carried the same stale 15. Both are corrected; this script exists so a
corrected claim cannot silently drift back.

Every assertion below is a NUMBER or a NAME taken from the document, checked against code
or against a running interpreter. No claim is taken on trust, including the ones this
script was written after reading.

Run:  python verify_current_architecture.py
Exits non-zero if any published number disagrees with the tree.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
DOC = REPO / "CURRENT_ARCHITECTURE.md"
PY = str(REPO / ".venv-fresh" / "Scripts" / "python.exe")
VITE = str(REPO / "frontend" / "node_modules" / ".bin" / "vite.cmd")

results: list[tuple[bool, str, str]] = []


def check(name: str, tree: object, doc: object) -> None:
    """Record one doc-vs-tree comparison.

    Parameter order is (tree, doc) and the labels say so. The first version took
    `(name, expected, actual)` and printed `doc={expected} tree={actual}`, which is INVERTED
    relative to what it was given — every call site passes the tree value as `expected`. So a
    failure reported `doc=20 tree=19` when the document said 19 and the tree said 20, sending
    a reader to fix the wrong file. A gate that misdirects on failure is worse than one that
    is merely silent.
    """
    results.append((tree == doc, name, f"tree={tree!r} doc={doc!r}"))


def note(name: str, ok: bool, detail: str) -> None:
    """A check that is not a doc/tree figure comparison — e.g. "is the doc SILENT?".

    Same result plumbing as `check`, separate entry point so a reader can tell at a glance
    which assertions compare numbers and which assert something structural.
    """
    results.append((ok, name, detail))


def py_eval(expr: str):  # type: ignore[no-untyped-def]
    """Run a snippet and return stdout.

    Every snippet must end in an explicit `print(...)`. A bare trailing expression is a
    statement in `python -c`, not a value, so it prints nothing -- which is how the first
    run of this script returned an empty string and crashed on `int("")`.
    """
    proc = subprocess.run(
        [PY, "-c", expr], cwd=REPO, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return f"ERROR: {proc.stderr.strip().splitlines()[-1:]}"
    return proc.stdout.strip()


def block(text: str, start: str) -> str:
    """Extract one declaration, from `start` to the first line that opens with `]`.

    Three earlier terminators failed in three different ways and each failure was SILENT --
    it produced a number rather than raising, which is what made them dangerous:

      * a literal `\\n];` breaks on a list that closes with a bare `]` (pyproject.toml);
      * a literal `\\n  ];` breaks on one that closes unindented;
      * falling back to the next `\\nexport ` runs to end-of-file in a file with no
        `export`, silently counting every remaining entry (30 instead of 3).

    A line-anchored `]` is the only terminator that survives all three shapes.
    """
    i = text.index(start)
    m = re.search(r"^\s*\]", text[i:], re.M)
    if m is None:
        return text[i:]
    return text[i : i + m.start()]


layers_ts = (REPO / "frontend/src/lib/architectureLayers.ts").read_text(encoding="utf-8")
LAYERS_BLOCK = block(layers_ts, "export const LAYERS = [")
GROUPS_BLOCK = block(layers_ts, "export const NAV_GROUPS")
GAPS_BLOCK = block(layers_ts, "export const LAYERS_WITHOUT_WORKSPACE")


#: Operator-facing subsystems that must be named in CURRENT_ARCHITECTURE.md.
#:
#: A gate that compares published figures cannot detect that a document is SILENT about a
#: subsystem — six commits of new surface passed this script untouched because it only knew
#: to look for claims it had been written against. This list is that missing check.
COVERAGE_REQUIRED = (
    "core/agent_advisory.py",
    "core/chat_console.py",
    "frontend/src/index.css",
    "frontend/src/lib/layout.ts",
    "frontend/src/lib/theme.ts",
    "frontend/src/lib/stateView.ts",
    "frontend/src/components/ChatPanel.tsx",
    "frontend/src/components/LayoutPanel.tsx",
    "scripts/verify_theme_gate.py",
    "scripts/verify_state_honesty.py",
    "scripts/verify_no_dead_settings.py",
    "scripts/verify_goal_id_divergence.py",
    "scripts/prove_goal_id_divergence.py",
    "scripts/verify_landed_evidence_is_live.py",
    "scripts/prove_landed_evidence_gate.py",
    # ARCHITECTURE.txt layer 25, Champion/Challenger Arena. LAYERS_WITHOUT_WORKSPACE called
    # it "the terminus of 12" with `promote_model` existing without a view -- and worse, a
    # sibling view asserted no promotion endpoint existed while both were wired and
    # RISK_ADMIN-gated. Surfacing a governance surface that works is the fix; keeping the
    # read model honest (INSUFFICIENT_EVIDENCE is not a number, unwired is not empty) is
    # what stops the new screen repeating the old lie.
    "frontend/src/adapters/arena.ts",
    "frontend/src/components/views/ArenaWorkspace.tsx",
    # ARCHITECTURE.txt 13 G260 "Disaster Recovery" has NO goal in the registry -- and that is
    # a deliberate, documented decline, not an oversight. Registry G220's notes record it
    # alongside failover: each appears in ARCHITECTURE.txt once, as a bare label, with
    # RPO/RTO/backup/restore at zero occurrences, so modelling either would mean inventing
    # requirements -- what the section 14 freeze rule exists to prevent.
    #
    # What this entry guards is a NAMING COLLISION, which is the actual hazard here.
    # research/disaster.py is "Disaster-lab drills (Directive 60)": OutageThenHealFetcher
    # injects ConnectionError at chosen bars mid-replay and the drill asserts the run freezes
    # or escalates instead of fabricating results. That is fault injection against the real
    # stack, NOT RPO/RTO backup-and-restore. An earlier draft of CURRENT_ARCHITECTURE.md read
    # it as the G260 capability because the filename matched -- the same "a name search is not
    # a capability search" error made about execution_twin.py and L21. Keeping the module in
    # this list means the distinction stays written down where the next reader will hit it.
    "research/disaster.py",
)

def main() -> int:
    doc = DOC.read_text(encoding="utf-8")

    def published(pattern: str, cast=int):  # type: ignore[no-untyped-def]
        m = re.search(pattern, doc)
        return cast(m.group(1)) if m else None

    # --- TREE FIRST --------------------------------------------------------
    # Everything below compares a figure PUBLISHED IN THE DOCUMENT against the value the
    # tree actually has. The tree is computed first so those comparisons can be
    # doc-vs-tree rather than doc-vs-a-constant.
    #
    # Both earlier arrangements were wrong in the same way and had to be undone:
    #   * comparing the tree to numbers hardcoded here meant editing a figure in the
    #     document changed nothing this script looked at -- four of five mutations
    #     survived;
    #   * then "fixing" it by parsing the document but still asserting a hardcoded
    #     expected value, which merely moved the constant and went stale the moment
    #     REDUCE_ONLY became fully covered.
    #
    # A hardcoded constant appears here ONLY where it is a genuine invariant of the
    # architecture rather than a restatement of something measurable -- §2 defines 25
    # layers, §8 names 8 commands, pyproject declares 3 required imports.
    emergency = (REPO / "frontend/src/lib/emergencyCommands.ts").read_text(encoding="utf-8")
    tree_commands = len(re.findall(r'^\s*command: "', emergency, re.M))
    tree_full = len(re.findall(r'coverage: "full"', emergency))
    tree_partial = len(re.findall(r'coverage: "partial"', emergency))
    tree_absent = len(re.findall(r'coverage: "none"', emergency))
    tree_layers = len(re.findall(r"\{ id: 'L\d+'", LAYERS_BLOCK))
    tree_with_screen = len(re.findall(r"placement: 'layer'", GROUPS_BLOCK))
    tree_without = len(re.findall(r"^\s*id: 'L\d+',$", GAPS_BLOCK, re.M))
    tree_claim_fields = int(py_eval("from core.claim_gate import REQUIRED_CLAIM_FIELDS as F; print(len(F))"))
    tree_actions = int(py_eval("from core.control_plane import ControlAction as C; print(len(list(C)))"))

    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    required_block = block(pyproject, "\ndependencies = [")
    tree_required_deps = len(re.findall(r'^\s{4}"', required_block, re.M))
    # Extras are counted by NAME, not by a loose `name = [` pattern: that pattern matches
    # `requires`, `include`, `testpaths`, `markers` and the ruff/mypy tables too, and an
    # earlier version of this check reported 5 because the section slice ended early.
    tree_extras = sum(
        1 for name in ("postgres", "nats", "ccxt", "qdrant", "dev", "all")
        if re.search(rf"^{name} = \[", pyproject, re.M)
    )

    # --- ARCHITECTURAL INVARIANTS (constants that are architecture, not restatements)
    check("§2 defines exactly 25 layers", 25, tree_layers)
    check("§8 names exactly 8 commands", 8, tree_commands)
    check("§8 coverage rows account for every command", tree_commands,
          tree_full + tree_partial + tree_absent)
    check("§2 layers: with + without a screen = total", tree_layers,
          tree_with_screen + tree_without)

    # --- PUBLISHED FIGURES vs TREE -----------------------------------------
    check("doc/tree: layers", tree_layers, published(r"§2's (\d+) layers"))
    check("doc/tree: layers with a screen", tree_with_screen, published(r"layers — (\d+) have a screen"))
    check("doc/tree: layers without a screen", tree_without, published(r"Without one \((\d+)\)"))
    check("doc/tree: §8 covered of 8", tree_full, published(r"§8's human control plane — (\d+) of 8"))
    check("doc/tree: §8 full", tree_full, published(r"Tally: \*\*(\d+) covered"))
    check("doc/tree: §8 partial", tree_partial, published(r"covered · (\d+) partial"))
    check("doc/tree: §8 absent", tree_absent, published(r"partial · (\d+) absent"))
    check("doc/tree: claim-gate fields", tree_claim_fields, published(r"requires \*\*(\d+) provenance fields"))
    check("doc/tree: ControlAction count", tree_actions, published(r"has \*\*(\d+) actions"))
    check("doc/tree: required deps", tree_required_deps, published(r"\*\*(\d+) required\*\*"))
    check("doc/tree: optional extras", tree_extras, published(r"\*\*(\d+) optional extras\*\*"))

    # A claim the document must NOT make.
    check("doc: does not claim mlflow is a dependency", True,
          "Not dependencies:** MLflow" in doc)

    # --- the tree ---------------------------------------------------------
    # PlatformEventType has no published figure of its own beyond the prose assertion
    # below, so it is counted directly.
    check("tree: PlatformEventType count", 19, int(py_eval("from core.platform_events import PlatformEventType as P; print(len(list(P)))")))
    check(
        "navigation groups = with-screen + control-plane + non-architecture",
        tree_with_screen
        + len(re.findall(r"placement: 'control-plane'", GROUPS_BLOCK))
        + len(re.findall(r"placement: 'not-architecture-derived'", GROUPS_BLOCK)),
        len(re.findall(r"placement: '(?:layer|control-plane|not-architecture-derived)'", GROUPS_BLOCK)),
    )

    # --- COVERAGE: can the document be SILENT about a subsystem? --------------------
    # Everything above compares a figure the document PUBLISHES against the tree. That
    # makes silence invisible: a whole subsystem can be added and this script still reports
    # "all 30 claims agree", because it only knows to look for claims it was written against.
    #
    # That is not hypothetical. Six commits added a token layer, runtime themes, an agent
    # advisory bridge, a chat panel, a layout system and a state-honesty layer. The document
    # was last touched before the first of them, mentioned none of them, and passed.
    #
    # So: every module that carries an operator-facing surface must be NAMED here. A new
    # subsystem that is not recorded here fails, which is the property a figure check can
    # never have.
    for rel in COVERAGE_REQUIRED:
        note(
            f"documented: {rel}",
            rel in doc,
            "named in CURRENT_ARCHITECTURE.md"
            if rel in doc
            else "SILENT — an operator-facing subsystem exists in the tree and is not recorded",
        )

    # The registry must keep retirement separate from the mutable status field. A gate
    # reading `status` looked correct and passed every test, while `mark_evaluated` overwrote
    # that field and made retirement reversible through a workflow that already existed. The
    # mutation harness found it; these assertions stop the shape from regressing silently.
    registries = (REPO / "kernel" / "registries.py").read_text(encoding="utf-8")
    check(
        "ModelVersion records retirement in a sticky field",
        True,
        "deprecated_at: str | None" in registries,
    )
    check(
        "mark_evaluated cannot overwrite a retirement",
        True,
        "was deprecated at" in registries,
    )
    control_plane_src = (REPO / "core" / "control_plane.py").read_text(encoding="utf-8")
    check(
        "promotion refuses retirement via the sticky field",
        True,
        "mv.deprecated_at is not None" in control_plane_src,
    )

    # --- dependency model --------------------------------------------------
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    # Anchored with a leading newline on purpose: a bare "dependencies = [" matches as a
    # SUBSTRING of "[project.optional-dependencies]", which silently counted 30 entries
    # spanning every extra. Third defect in this script, and the second silent one -- both
    # of which reported a number rather than raising, which is what made them dangerous.
    required_block = block(pyproject, "\ndependencies = [")
    check("required dependencies", 3, len(re.findall(r'^\s{4}"', required_block, re.M)))
    for extra in ("postgres", "nats", "ccxt", "qdrant"):
        check(f"extra `{extra}` declared", True, f"{extra} = [" in pyproject)
    check("mlflow is NOT a dependency", False, "mlflow" in pyproject.lower())

    # --- the document must not still claim the stale 15 -------------------
    check("no stale '15 canonical' in doc", False, "15 canonical" in doc)
    check("doc states 19 PlatformEvent", True, "**19** `PlatformEventType`" in doc)

    # --- isolation gate, measured ------------------------------------------
    proc = subprocess.run(
        [PY, str(REPO / "scripts" / "verify_operator_isolation.py")],
        cwd=REPO, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    check("operator isolation gate green", 0, proc.returncode)
    forbidden = re.search(r"(\d+) forbidden modules checked", out)
    # 26, not 25: the isolation gate derives its pattern list from the filesystem
    # (FORBIDDEN_DIRS = components/views + hooks), so adding the L25 Arena workspace widened
    # the set of modules the operator surface must never reach. The operator's isolation
    # therefore covers a new workspace without anyone editing the isolation gate -- which is
    # the property worth having, and the reason this number moves when a screen is added.
    check("forbidden modules", 26, int(forbidden.group(1)) if forbidden else -1)
    modules = re.search(r"first-party modules reachable from operator\.html: (\d+)", out)
    check("operator first-party modules", 7, int(modules.group(1)) if modules else -1)
    # The document quotes the operator entry's size in prose; asserted as a substring
    # because a regenerated bundle carries a content hash in its filename and the exact
    # kilobyte figure moves with it.
    check("doc quotes the operator bundle size", True, "10.5 KB" in doc)

    # --- report -----------------------------------------------------------
    failed = [r for r in results if not r[0]]
    width = max(len(n) for _, n, _ in results)
    for ok, name, detail in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name.ljust(width)}  {detail}")
    print()
    if failed:
        print(f"{len(failed)} of {len(results)} published claims DISAGREE with the tree")
        return 1
    print(f"all {len(results)} published claims agree with the tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
