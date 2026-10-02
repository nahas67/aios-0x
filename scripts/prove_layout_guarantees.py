"""Prove the Phase 6 layout guarantees can fail.

Two properties, both of which can be broken by a one-line edit and neither of which tsc
notices:

  - the layout editor stays reachable (hiding Settings is a one-way door)
  - a layout can never change WHICH workspaces exist

The assertion is made through vitest, so this runs the real suite rather than reimplementing
the rules in Python -- a harness that duplicated the logic would prove nothing about it.
"""
import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
FRONTEND = REPO / "frontend"
VITEST = FRONTEND / "node_modules" / ".bin" / "vitest.cmd"
LAYOUT = FRONTEND / "src" / "lib" / "layout.ts"
LAYERS = FRONTEND / "src" / "lib" / "architectureLayers.test.ts"

MUTANTS = [
    ("settings becomes hideable again",
     LAYOUT,
     "export const NON_HIDEABLE: readonly WorkspaceTab[] = ['settings'];",
     "export const NON_HIDEABLE: readonly WorkspaceTab[] = [];",
     "keeps the layout editor itself reachable"),
    ("a stored layout is trusted instead of re-normalised",
     LAYOUT,
     "if (!canHide(entry as WorkspaceTab)) continue;",
     "",
     "corrects a stored layout that hid Settings"),
    ("a layout is allowed to drop workspaces entirely",
     LAYERS,
     "expect(new Set(layout.order)).toEqual(new Set(WORKSPACE_TABS));",
     "expect(new Set(layout.order)).toEqual(new Set(['risk']));",
     "never lets a layout change which workspaces EXIST"),
]


def run():
    p = subprocess.run([str(VITEST), "run", "src/lib/architectureLayers.test.ts", "src/lib/layout.test.ts"],
                       cwd=FRONTEND, capture_output=True, text=True, shell=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    backups = {p: p.read_bytes() for p in (LAYOUT, LAYERS)}
    code, out = run()
    print("baseline:", "green" if code == 0 else "RED")
    if code != 0:
        print(out[-1500:])
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

    ok = all(p.read_bytes() == b for p, b in backups.items())
    code, _ = run()
    print("\nrestore byte-for-byte:", "verified" if ok else "NO")
    print("green after restore:", "yes" if code == 0 else "NO")
    if not ok or code != 0:
        problems.append("restore failed")
    print("problems:", problems if problems else "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
