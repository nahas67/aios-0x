"""Prove the state-honesty gate can fail.

Each mutant reintroduces one way the console can lie about absence, and asserts the specific
rule that must fire. A gate whose mutants all survive is decoration.

Run:  python scripts/prove_state_honesty.py
"""
import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
PY = str(REPO / ".venv-fresh" / "Scripts" / "python.exe")
VERIFY = REPO / "scripts" / "verify_state_honesty.py"
SURFACE = REPO / "frontend" / "src" / "components" / "views" / "FinancialKernelWorkspace.tsx"
TRADING = REPO / "frontend" / "src" / "components" / "views" / "LiveTradingWorkspace.tsx"

#: Anchor read from the file, not assumed. The first version of this harness injected raw
#: source text before a `<StateView` and both mutants SURVIVED — correctly, because what it
#: produced was not JSX and so was not a rendered caption. A mutant that does not reproduce
#: the bug tests nothing while reporting a result.
ANCHOR = "<StateView state={classifyList(q.data.fills, KERNEL_FILLS_SOURCE)}"

MUTANTS = [
    ("a hand-rolled empty caption reappears",
     SURFACE, ANCHOR,
     '<div className="p-4 text-center text-text-subtle text-xs">No fills recorded.</div>\n'
     '              ' + ANCHOR, "hand-rolled empty state"),
    ("an empty state asserts a cause again",
     SURFACE, ANCHOR,
     '<div className="p-4 text-center text-text-subtle text-xs">Book holds no positions.</div>\n'
     '              ' + ANCHOR, "asserts a CAUSE"),
    ("an unavailable source is collapsed to [] again",
     TRADING, "const positionsState = useMemo(() => classifyList(positions, POSITIONS_SOURCE), [positions]);",
     "const positionsState = useMemo(() => {\n    if (positions && \"unavailable\" in positions) return { kind: 'empty' };\n    return classifyList(positions, POSITIONS_SOURCE);\n  }, [positions]);",
     "launders an unavailability marker"),
]


def verify():
    p = subprocess.run([PY, str(VERIFY)], cwd=REPO, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    backups = {p: p.read_bytes() for p in (SURFACE, TRADING)}
    code, out = verify()
    print("baseline:", "green" if code == 0 else "RED")
    if code != 0:
        print(out[-1200:])
        return 2

    problems = []
    try:
        for label, path, old, new, expect in MUTANTS:
            text = path.read_bytes().decode("utf-8")
            if old not in text:
                print(f"  SKIP      {label} -- anchor not found; refusing to guess")
                problems.append(label)
                continue
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            code, out = verify()
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

    ok = all(p.read_bytes() == b for p, b in backups.items())
    code, _ = verify()
    print("\nrestore byte-for-byte:", "verified" if ok else "NO")
    print("green after restore:", "yes" if code == 0 else "NO")
    if not ok or code != 0:
        problems.append("restore failed")
    print("problems:", problems if problems else "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
