"""Prove the theme gate can fail.

The first version of this gate reported zero violations on a tree where 58 sites were
silently broken, because it could not tell a design token from a Tailwind colour of the same
name. A gate that passes while the feature it guards does not work is worse than no gate,
which is the whole reason this exists rather than a comment in ADR-008.

Each mutant reintroduces one way the theme layer can rot, and asserts the specific check
that must fire. Everything is restored byte-for-byte.

Run:  python prove_theme_gate.py
"""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
PY = str(REPO / ".venv-fresh" / "Scripts" / "python.exe")
VERIFY = REPO / "scripts" / "verify_theme_gate.py"
CSS = REPO / "frontend" / "src" / "index.css"
SURFACE = REPO / "frontend" / "src" / "components" / "LeftIntelligenceRail.tsx"

# Anchors are read from the file, not assumed. The first version of this harness used
# `text-text-muted` and `bg-[var(--color-surface-1)]`, neither of which exists in the rail,
# so one mutant was skipped and a second mutated nothing while still reporting a result.
# Guessing an anchor and then trusting the outcome is how a proof ends up proving nothing.
MUTANTS = [
    (
        "a hardcoded hex literal reappears in a component",
        SURFACE,
        "bg-[var(--color-surface-rail)]",
        "bg-[#090a0f]",
        "hex literals outside index.css",
    ),
    (
        "a hardcoded Tailwind palette class reappears",
        SURFACE,
        "var(--color-accent)",
        "#00f0ff",
        "hex literals outside index.css",
    ),
    (
        "a token is referenced but never defined",
        SURFACE,
        "var(--color-accent)",
        "var(--color-accent-invented)",
        "tokens referenced but not defined",
    ),
    (
        "a token is defined for one theme only, so the other falls back",
        CSS,
        "  --color-violet: #4f46e5;",
        "",
        "defined for :root but not for the paper theme",
    ),
]


def verify() -> tuple[int, str]:
    proc = subprocess.run([PY, str(VERIFY)], cwd=REPO, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    backups = {p: p.read_bytes() for p in (CSS, SURFACE)}
    code, out = verify()
    print("baseline:", "green" if code == 0 else "RED")
    if code != 0:
        print(out[-1500:])
        return 2

    problems: list[str] = []
    try:
        for label, path, old, new, expect in MUTANTS:
            text = path.read_bytes().decode("utf-8")
            if old not in text:
                print(f"  SKIP      {label} -- anchor not found; refusing to guess")
                problems.append(label)
                continue
            mutated = text.replace(old, new, 1)
            if mutated == text:
                print(f"  NO-OP     {label}")
                problems.append(label)
                continue

            path.write_bytes(mutated.encode("utf-8"))
            code, out = verify()
            path.write_bytes(backups[path])

            if code == 0:
                print(f"  SURVIVED  {label} -- the rot went undetected")
                problems.append(label)
            elif expect not in out:
                print(f"  WRONGRED  {label} -- went red, but not via {expect!r}")
                problems.append(label)
            else:
                print(f"  caught    {label}")
    finally:
        for path, data in backups.items():
            path.write_bytes(data)

    restored = all(p.read_bytes() == b for p, b in backups.items())
    code, _ = verify()
    green_after = code == 0
    print("\nrestore byte-for-byte:", "verified" if restored else "NO")
    print("green after restore:", "yes" if green_after else "NO")
    if not restored:
        print("RESTORE FAILED — inspect before continuing")
        return 2
    if problems:
        print(f"problems: {problems}")
        return 1
    print(f"\nall {len(MUTANTS)} rotations caught; the gate can fail, so its green means something")
    return 0


if __name__ == "__main__":
    sys.exit(main())
