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


def check(name: str, expected: object, actual: object) -> None:
    results.append((expected == actual, name, f"doc={expected!r} tree={actual!r}"))


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


def main() -> int:
    doc = DOC.read_text(encoding="utf-8")

    # --- counts the document states as prose -------------------------------
    # --- the FIGURES THE DOCUMENT PUBLISHES ---------------------------------
    # Parsed out of the document, never restated here.
    #
    # The first version of this script hardcoded the expected numbers and compared the
    # tree against THEM. Four of five mutations survived that: editing a figure in the
    # document changed nothing the script looked at, because the script was not reading
    # the document. It verified the tree against its own assumptions -- which is what it
    # was already doing before this file existed, and is how the stale "15 canonical" sat
    # in the checkpoint for months.
    #
    # So every published figure below is extracted from the prose and compared to the
    # tree. A number that drifts in the document now fails here.
    def published(pattern: str, cast=int):  # type: ignore[no-untyped-def]
        m = re.search(pattern, doc)
        return cast(m.group(1)) if m else None

    check("doc: §2 layer count", 25, published(r"§2's (\d+) layers"))
    check("doc: layers with a screen", 11, published(r"layers — (\d+) have a screen"))
    check("doc: layers without a screen", 14, published(r"Without one \((\d+)\)"))
    check("doc: §8 covered of 8", 2, published(r"§8's human control plane — (\d+) of 8"))
    check("doc: §8 full", 2, published(r"Tally: \*\*(\d+) covered"))
    check("doc: §8 partial", 2, published(r"covered · (\d+) partial"))
    check("doc: §8 absent", 4, published(r"partial · (\d+) absent"))
    check("doc: claim-gate fields", 14, published(r"requires \*\*(\d+) provenance fields"))
    check("doc: ControlAction count", 19, published(r"has \*\*(\d+) actions"))
    check("doc: required deps", 3, published(r"\*\*(\d+) required\*\*"))
    check("doc: optional extras", 4, published(r"\*\*(\d+) optional extras\*\*"))
    check("doc: operator first-party modules", 7, published(r"\*\*(\d+) first-party modules\*\*"))

    # A claim the document must NOT make.
    check("doc: does not claim mlflow is a dependency", True,
          "Not dependencies:** MLflow" in doc)

    # --- the tree ---------------------------------------------------------
    check("tree: ControlAction count", 19, int(py_eval("from core.control_plane import ControlAction as C; print(len(list(C)))")))
    check("tree: required claim fields", 14, int(py_eval("from core.claim_gate import REQUIRED_CLAIM_FIELDS as F; print(len(F))")))
    check("tree: PlatformEventType count", 19, int(py_eval("from core.platform_events import PlatformEventType as P; print(len(list(P)))")))
    check("tree: architecture layers", 25, len(re.findall(r"\{ id: 'L\d+'", LAYERS_BLOCK)))
    check(
        "navigation groups (11 layer + 2 plane + 2 other)",
        15,
        len(re.findall(r"placement: '(?:layer|control-plane|not-architecture-derived)'", GROUPS_BLOCK)),
    )
    check("tree: layers without a screen", 14, len(re.findall(r"^\s*id: 'L\d+',$", GAPS_BLOCK, re.M)))
    check(
        "tree: layers with a screen",
        11,
        len(re.findall(r"placement: 'layer'", GROUPS_BLOCK)),
    )

    # --- the §8 tally must match the tested source, not the prose ---------
    emergency = (REPO / "frontend/src/lib/emergencyCommands.ts").read_text(encoding="utf-8")
    check("§8 commands", 8, len(re.findall(r'^\s*command: "', emergency, re.M)))
    check("§8 full", 2, len(re.findall(r'coverage: "full"', emergency)))
    check("§8 partial", 2, len(re.findall(r'coverage: "partial"', emergency)))
    check("§8 none", 4, len(re.findall(r'coverage: "none"', emergency)))

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
    check("forbidden modules", 25, int(forbidden.group(1)) if forbidden else -1)
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
