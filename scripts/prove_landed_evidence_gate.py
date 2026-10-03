"""Prove the landed-evidence gate can fail.

Four rotations:

  1. A new dead evidence module appears on a LANDED goal, undocumented -- the ordinary case.
  2. A goal becomes barren: its last live evidence module loses its importer. This is the
     failure the gate is named for, and it is the one a figure-comparing gate cannot see,
     because every published figure stays identical while a goal quietly stops running.
  3. A KNOWN_DEAD_GOALS entry gains a live module -- the self-clearing half. Without this the
     allowlist is a permanent amnesty.
  4. A KNOWN_DEAD_MODULES entry gains an importer -- the same at module granularity.

Rotation 2 is worth proving hardest: a module can keep passing every other gate in this repo
while nothing reaches it, because the gate that would notice is the one checking imports.

Run:  python scripts/prove_landed_evidence_gate.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
PY = str(REPO / ".venv-fresh" / "Scripts" / "python.exe")
VERIFY = REPO / "scripts" / "verify_landed_evidence_is_live.py"
REGISTRY = REPO / "docs" / "goals" / "goals.json"

MUTANTS: list[tuple[str, pathlib.Path, str, str, str]] = [
    (
        "a goal goes barren: G190's live evidence is swapped for a dead one",
        REGISTRY,
        '"core/claim_gate.py"',
        '"core/feature_store.py"',
        "no production module imports any of its library evidence",
    ),
    (
        "evidence names a file that is not in the tree at all",
        REGISTRY,
        '"core/risk_firewall.py"',
        '"core/risk_firewall.py",\n        "core/never_written_module.py"',
        "no such file is in the tree",
    ),
    (
        "a KNOWN_DEAD_GOALS entry gains a live module (self-clearing, goal level)",
        VERIFY,
        '"G160": "simulation/execution_twin.py -- the Execution Digital Twin -- has no "',
        '"G190": "simulation/execution_twin.py -- the Execution Digital Twin -- has no "',
        "delete the entry, the debt is paid",
    ),
    (
        "a KNOWN_DEAD_MODULES entry gains an importer (self-clearing, module level)",
        VERIFY,
        '"core/decision_gate.py": "DEAD PARALLEL IMPLEMENTATION.',
        '"kernel/playbook.py": "DEAD PARALLEL IMPLEMENTATION.',
        "delete the entry, the debt is paid",
    ),
]


def run() -> tuple[int, str]:
    proc = subprocess.run([PY, str(VERIFY)], cwd=REPO, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    backups = {p: p.read_bytes() for p in {REGISTRY, VERIFY}}
    code, out = run()
    print("baseline:", "green" if code == 0 else "RED")
    if code != 0:
        print(out[-1800:])
        return 2

    problems: list[str] = []
    try:
        for label, path, old, new, expect in MUTANTS:
            text = path.read_bytes().decode("utf-8")
            if old not in text:
                print(f"  SKIP      {label} -- anchor not found; refusing to guess")
                problems.append(label)
                continue
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            code, out = run()
            path.write_bytes(backups[path])
            if code == 0:
                print(f"  SURVIVED  {label}")
                problems.append(label)
            elif expect not in out:
                print(f"  WRONGRED  {label} -- red, but not via {expect!r}")
                problems.append(label)
            else:
                print(f"  caught    {label}")
    finally:
        for path, data in backups.items():
            path.write_bytes(data)

    restored = all(p.read_bytes() == b for p, b in backups.items())
    code, _ = run()
    print()
    print("restore byte-for-byte:", "verified" if restored else "NO")
    print("green after restore :", "yes" if code == 0 else "NO")
    if not restored or code != 0:
        problems.append("restore failed")
    print("problems:", problems if problems else "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
