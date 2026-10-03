"""Prove the dead-settings gate can fail.

Three rotations, each a way the gate could be defeated:

  1. A NEW dead field is added and not documented -- the case the gate exists for.
  2. A field that WAS documented as inert gets wired -- the self-clearing half. If this
     does not fire, KNOWN_INERT becomes a permanent amnesty.
  3. A KNOWN_INERT entry names a field that no longer exists -- a stale exemption that
     would sit there forever doing nothing.

Rotation 1 is the ordinary case. Rotation 2 is the one worth proving: an allowlist that
cannot shrink is just a suppression file with a longer name.

Run:  python scripts/prove_dead_settings_gate.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
PY = str(REPO / ".venv-fresh" / "Scripts" / "python.exe")
VERIFY = REPO / "scripts" / "verify_no_dead_settings.py"
TYPES = REPO / "frontend" / "src" / "types.ts"
VIEW = REPO / "frontend" / "src" / "components" / "views" / "SettingsWorkspace.tsx"

MUTANTS = [
    (
        "a new dead settings field ships undocumented",
        TYPES,
        "  var95DailyLimitUsd: number;",
        "  var95DailyLimitUsd: number;\n  brandNewUnwiredKnob: string;",
        "brandNewUnwiredKnob",
    ),
    (
        "a documented-inert field gets wired, but stays on the list",
        VIEW,
        "<LayoutPanel",
        "<span>{formState.maxGrossLeverage}</span>\n              <LayoutPanel",
        "delete its entry",
    ),
    (
        "a KNOWN_INERT entry names a field that no longer exists",
        VERIFY,
        '    "tradingViewClientId": "third-party widget not integrated",',
        '    "tradingViewClientId": "third-party widget not integrated",\n'
        '    "fieldThatWasDeletedLongAgo": "stale exemption",',
        "no longer a SystemSettings field",
    ),
]


def run() -> tuple[int, str]:
    proc = subprocess.run([PY, str(VERIFY)], cwd=REPO, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    backups = {p: p.read_bytes() for p in (TYPES, VIEW, VERIFY)}
    code, out = run()
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
    print("\nrestore byte-for-byte:", "verified" if restored else "NO")
    print("green after restore:", "yes" if code == 0 else "NO")
    if not restored or code != 0:
        problems.append("restore failed")
    print("problems:", problems if problems else "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
