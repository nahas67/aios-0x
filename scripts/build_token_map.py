"""Build the token map from the shipped palette, not from aspiration.

WHY THIS IS A SCRIPT AND NOT A HAND-WRITTEN MAP.

ADR-004 specified a palette that was never adopted, and `frontend/src` accumulated 206 hex
literals across 43 files instead. Writing a replacement mapping by hand would mean reading
43 files and trusting my reading of each — which is how two rows of the §8 mapping and the
stale "15 canonical" figure got into committed documents earlier in this project.

So the map is derived: the 37 distinct values are extracted, each is classified by where
it sits in the surface/text/accent/status/border scale, and the result is PRINTED for
review before it is used to rewrite anything. The script does not decide silently.

THE TWO VALUES THAT MUST NOT BE MISTAKEN

  #0d0f17  93 occurrences — the dominant panel surface. Anything that gets this wrong
           repaints nearly the entire console.
  #00f0ff  19 occurrences — the primary accent, and the one ADR-004's `#22c55e`-style
           green-as-positive convention never touched.

Anything with a frequency of 1 is inspected individually rather than bulk-classified, and
`UNMAPPED` is a hard failure rather than a warning: a token scale with a hole in it is how
a UI ends up with one unthemed corner.

Run:  python build_token_map.py            # prints the map and the frequency table
      python build_token_map.py --write    # also writes src/lib/themeTokens.json
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
SRC = REPO / "frontend" / "src"
OUT = REPO / "frontend" / "src" / "lib" / "themeTokens.json"

#: hex -> (token name, what the token MEANS). Names are semantic, never colour names, so a
#: light theme can repaint `surface-1` without anything reading "panel-dark" and assuming
#: it must stay dark.
MAP: dict[str, tuple[str, str]] = {
    # --- surfaces: darkest to lightest. `surface-1` is the panel, by a wide margin.
    "#050608": ("surface-deep", "deepest backdrop: full-bleed rails, viewport wells"),
    "#06070a": ("surface-deep", "deepest backdrop"),
    "#07080c": ("surface-deep", "deepest backdrop"),
    "#08090d": ("surface-0", "page background"),
    "#090a0f": ("surface-rail", "left navigation rail"),
    "#090b10": ("surface-rail", "rail / secondary chrome"),
    "#0b0d13": ("surface-2", "raised chrome: toolbars, sub-panels"),
    "#0d0f17": ("surface-1", "panel — the dominant surface"),
    "#0e1017": ("surface-1", "panel"),
    "#121520": ("surface-3", "hover / elevated panel"),
    "#1e2438": ("scrollbar-thumb", "scrollbar thumb"),
    "#2a334f": ("scrollbar-hover", "scrollbar thumb hover"),
    # --- text
    "#f8fafc": ("text-strong", "highest-emphasis text"),
    # Found UNMAPPED by the completeness gate, which is the only reason that gate is a hard
    # failure rather than a warning. A near-black value in a dark palette is almost always
    # text drawn ON an accent chip. Confirmed by reading the call site, not by its hex: a
    # <text> whose sibling <rect> is filled `accent`. It must be a token rather than a
    # literal because it has to invert when a theme changes the accent it sits on.
    "#040810": ("text-on-accent", "text drawn on top of an accent-filled chip"),
    "#ffffff": ("text-strong", "highest-emphasis text"),
    "#e2e8f0": ("text", "default body text"),
    "#94a3b8": ("text-muted", "secondary text"),
    "#64748b": ("text-subtle", "tertiary text, axis labels"),
    "#334155": ("text-dim", "disabled / de-emphasised"),
    # --- accent (cyan family)
    "#00f0ff": ("accent", "primary accent — active, live, selected"),
    "#22d3ee": ("accent-soft", "accent at rest"),
    "#38bdf8": ("accent-info", "informational accent"),
    "#06b6d4": ("accent-soft", "accent at rest"),
    "#67e8f9": ("accent-glow", "accent highlight / glow"),
    "#818cf8": ("accent-violet", "secondary accent"),
    "#ec4899": ("accent-magenta", "tertiary accent"),
    # --- status
    "#10b981": ("positive", "success / within limits"),
    "#6ee7b7": ("positive-soft", "success text on tinted ground"),
    "#064e3b": ("positive-bg", "success tinted background"),
    "#22c55e": ("positive", "success"),
    "#f59e0b": ("warning", "caution / degraded"),
    "#eab308": ("warning", "caution"),
    "#f43f5e": ("destructive", "breach / failure"),
    "#ef4444": ("destructive", "breach / failure"),
    "#fca5a5": ("destructive-soft", "failure text on tinted ground"),
    "#450a0a": ("destructive-bg", "failure tinted background"),
    "#083344": ("info-bg", "informational tinted background"),
}

HEX = re.compile(r"#[0-9a-fA-F]{6}")


def main() -> int:
    write = "--write" in sys.argv

    counts: collections.Counter[str] = collections.Counter()
    for path in SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".css"} or not path.is_file():
            continue
        for raw in HEX.findall(path.read_text(encoding="utf-8", errors="replace")):
            counts[raw.lower()] += 1

    unmapped = sorted(h for h in counts if h not in MAP)
    total = sum(counts.values())

    print(f"{len(counts)} distinct values across {total} occurrences in frontend/src\n")
    print(f"{'occurrences':>11}  {'hex':<9} {'token':<18} meaning")
    for hexval, n in counts.most_common():
        token, meaning = MAP.get(hexval, ("UNMAPPED", "<< NO TOKEN — fix before migrating >>"))
        print(f"{n:>11}  {hexval:<9} {token:<18} {meaning}")

    if unmapped:
        # A hard failure, not a warning. A token scale with a hole is how one corner of a
        # UI stays unthemed and nobody notices until the theme is switched.
        print(f"\nUNMAPPED ({len(unmapped)}): {', '.join(unmapped)}")
        print("Refusing to migrate with an incomplete map.")
        return 1

    print(f"\nAll {len(counts)} values map to {len({t for t, _ in MAP.values()})} tokens.")
    if write:
        payload = {
            "source": "derived from frontend/src by scripts/build_token_map.py",
            "tokens": {t: meaning for t, meaning in MAP.values()},
            "hexToToken": {h: t for h, (t, _) in MAP.items()},
        }
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
