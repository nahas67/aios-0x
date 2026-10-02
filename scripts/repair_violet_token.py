"""Repair the violet-token rename across the tree, per utility.

The first migration mapped violet to a token named `accent-violet`. That collided with
Tailwind's `accent-color` utility: `accent-violet-400` became `accent-accent-violet`, which
resolves to nothing. 58 sites were left silently unstyled while `tsc`, vitest, the build
and the operator-isolation gate all passed — every check was green and the UI was broken.

The token is now `violet`. This propagates that rename, and the distinction that matters is
per utility:

  text-violet / stroke-violet / fill-violet / bg-violet   <- came from text-violet-400 etc.
  accent-violet                                           <- ALREADY CORRECT: the CSS
                                                             accent-color utility, and
                                                             `accent-violet` is exactly
                                                             what it should read

So a blind rename of every `accent-violet` would "fix" the 58 by breaking the correct ones.
This walks utility by utility instead.

Run:  python scripts/repair_violet_token.py [--apply]
"""

from __future__ import annotations

import pathlib
import re
import sys

SRC = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X\frontend\src")

#: Utilities whose token changed name. `accent` is deliberately ABSENT: its output
#: `accent-violet` was already right, and renaming it would be the mirror-image bug.
COLOUR_UTILITIES = ("text", "stroke", "fill", "bg", "border", "from", "to", "via", "ring", "divide")

#: (pattern, replacement) applied in order across .ts/.tsx
RULES: list[tuple[re.Pattern[str], str]] = [
    # The doubled name from the collision, in both class and var() form.
    (re.compile(r"\baccent-accent-violet\b"), "accent-violet"),
    (re.compile(r"--color-accent-accent-violet\b"), "--color-violet"),
    # The old token name under a real colour utility.
    *[
        (
            re.compile(rf"\b{u}-accent-violet\b"),
            f"{u}-violet",
        )
        for u in COLOUR_UTILITIES
    ],
    (re.compile(r"--color-accent-violet\b"), "--color-violet"),
    (re.compile(r"--accent-accent-violet\b"), "--violet"),
]


def main() -> int:
    apply = "--apply" in sys.argv
    edits: list[tuple[str, int]] = []
    backups: dict[pathlib.Path, str] = {}

    try:
        for path in sorted(SRC.rglob("*")):
            if path.suffix not in {".ts", ".tsx"} or not path.is_file():
                continue
            original = path.read_text(encoding="utf-8")
            text = original
            count = 0
            for pattern, replacement in RULES:
                text, n = pattern.subn(replacement, text)
                count += n
            if text != original:
                backups[path] = original
                edits.append((str(path.relative_to(SRC.parent.parent)), count))
                if apply:
                    path.write_text(text, encoding="utf-8")

        total = sum(n for _, n in edits)
        verb = "repaired" if apply else "would repair"
        print(f"{total} sites {verb} across {len(edits)} files")
        for rel, n in edits:
            print(f"  {n:>3}  {rel}")
        if not apply:
            print("\nDRY RUN. Re-run with --apply.")
        return 0
    except Exception:
        for path, data in backups.items():
            path.write_text(data, encoding="utf-8")
        print(f"\nERROR — restored {len(backups)} files.")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
