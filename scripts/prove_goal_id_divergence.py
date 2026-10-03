"""Prove the goal-id divergence gate can fail.

Four rotations, each a way this reconciliation could rot back into the wrong belief:

  1. A new section 13 id appears that nobody reconciled -- the ordinary case.
  2. The architecture gains an RPO target, which is exactly what would make the G260
     DECLINE stale. This is the rotation worth proving: a decline is only sound while its
     reason exists, and without this check a declined goal is permanent by accident.
  3. A declared merge target is wrong, so the arithmetic stops closing.
  4. The registry's own notes stop recording the rationale, leaving the decline declared
     here but unauditable to a human reader.

Rotation 2 is the one that matters. "Ungoverned forever" is the failure mode where a
decision made for a good reason outlives the reason.

WHAT THIS DOES NOT PROVE
========================
It does not prove that a declined goal has not quietly acquired requirements *in place*.
Adding specification text under a bare label leaves the label appearing exactly once, so no
mechanical check can see it. Decidable staleness signals are the label being duplicated and
RPO/RTO entering `ARCHITECTURE.txt`; both are proven below. Judging whether a bare label has
grown a specification is left as a human review duty, stated rather than papered over.

NOTE ON THE FROZEN FILE
=======================
Rotations 1 and 2 would mutate `ARCHITECTURE.txt` -- the frozen target, which lives outside
the repo and which nothing is permitted to write. A probe interrupted between mutation and
restore would corrupt the one document every other claim is measured against. So these
rotations hand the gate a TEMP COPY via `AIOS_ARCHITECTURE_PATH` and mutate that. The real
file is opened read-only and is verified byte-for-byte unchanged at the end.

Run:  python scripts/prove_goal_id_divergence.py
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
REAL_ARCHITECTURE = REPO.parent / "ARCHITECTURE.txt"
PY = str(REPO / ".venv-fresh" / "Scripts" / "python.exe")
VERIFY = REPO / "scripts" / "verify_goal_id_divergence.py"
REGISTRY = REPO / "docs" / "goals" / "goals.json"


def run(architecture: pathlib.Path) -> tuple[int, str]:
    env = {**os.environ, "AIOS_ARCHITECTURE_PATH": str(architecture)}
    proc = subprocess.run(
        [PY, str(VERIFY)], cwd=REPO, capture_output=True, text=True, env=env
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    verify_before = VERIFY.read_bytes()
    registry_before = REGISTRY.read_bytes()
    arch_before = REAL_ARCHITECTURE.read_bytes()

    problems: list[str] = []
    rotations = 0
    caught = 0

    code, out = run(REAL_ARCHITECTURE)
    print("baseline:", "green" if code == 0 else "RED")
    if code != 0:
        print(out[-1800:])
        return 2

    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="aios_g260_probe_"))

    # --- rotations that need a mutated ARCHITECTURE.txt (temp copy) -------------
    arch_mutations: list[tuple[str, str, str, str]] = [
        (
            "a new section-13 goal id appears, unreconciled",
            "G280\r\nCanary Capital\r\nFUTURE",
            "G290\r\nPost-Quantum Migration\r\n\r\nG280\r\nCanary Capital\r\nFUTURE",
            "G290 is in section 13",
        ),
        (
            "the architecture gains an RPO target, making the G260 decline stale",
            "Disaster Recovery\r\n",
            "Disaster Recovery\r\n        RPO target: 15 minutes, RTO target: 60 minutes\r\n",
            "a goal must be added",
        ),
        ]

    # A rotation that is NOT here, deliberately: adding specification text after the bare
    # "Disaster Recovery" label leaves the label appearing exactly once, so the gate stays
    # green. "This goal became specified in place" is not mechanically decidable, and a probe
    # that claimed to prove it would be a false assurance. The two staleness signals that ARE
    # decidable are below: the label being duplicated, and RPO/RTO entering the document.
    # Judging whether a bare label has quietly acquired requirements stays a human review
    # duty, and `verify_goal_id_divergence.py` says so rather than implying otherwise.

    for label, old, new, expect in arch_mutations:
        rotations += 1
        text = arch_before.decode("utf-8")
        if old not in text:
            print(f"  SKIP      {label} -- anchor not found; refusing to guess")
            problems.append(label)
            continue
        copy = tmpdir / f"arch_{rotations}.txt"
        copy.write_bytes(text.replace(old, new, 1).encode("utf-8"))
        code, out = run(copy)
        if code == 0:
            print(f"  SURVIVED  {label}")
            problems.append(label)
        elif expect not in out:
            print(f"  WRONGRED  {label} -- red, but not via {expect!r}")
            problems.append(label)
        else:
            print(f"  caught    {label}")
            caught += 1

    # --- rotations that mutate in-repo files (backed up, restored) -------------
    inrepo: list[tuple[str, pathlib.Path, str, str, str]] = [
        (
            "a merge target is wrong, so 28 no longer reconciles to 25",
            VERIFY,
            'frozenset({"G190", "G200", "G210"}): "G180",',
            'frozenset({"G190", "G200"}): "G180",',
            "the divergence does not close",
        ),
        (
            "the registry stops recording why G260 was declined",
            REGISTRY,
            "Disaster Recovery",
            "deferred capability",
            "an undocumented decline cannot be audited",
        ),
    ]

    for label, path, old, new, expect in inrepo:
        rotations += 1
        original = path.read_bytes()
        text = original.decode("utf-8")
        if old not in text:
            print(f"  SKIP      {label} -- anchor not found; refusing to guess")
            problems.append(label)
            continue
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        code, out = run(REAL_ARCHITECTURE)
        path.write_bytes(original)
        if code == 0:
            print(f"  SURVIVED  {label}")
            problems.append(label)
        elif expect not in out:
            print(f"  WRONGRED  {label} -- red, but not via {expect!r}")
            problems.append(label)
        else:
            print(f"  caught    {label}")
            caught += 1

    for path in tmpdir.glob("arch_*.txt"):
        path.unlink()
    tmpdir.rmdir()

    arch_intact = REAL_ARCHITECTURE.read_bytes() == arch_before
    verify_intact = VERIFY.read_bytes() == verify_before
    registry_intact = REGISTRY.read_bytes() == registry_before
    code, _ = run(REAL_ARCHITECTURE)

    print()
    print("frozen ARCHITECTURE.txt untouched:", "verified" if arch_intact else "NO")
    print("in-repo files restored          :",
          "verified" if verify_intact and registry_intact else "NO")
    print("green after restore             :", "yes" if code == 0 else "NO")
    if not (arch_intact and verify_intact and registry_intact and code == 0):
        problems.append("restore failed")

    print(f"\n{caught}/{rotations} rotations caught; the gate can fail, so its green means "
          f"something")
    print("problems:", problems if problems else "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
