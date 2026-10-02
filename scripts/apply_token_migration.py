"""Apply the token migration to every colour site in frontend/src. Dry run by default.

WHAT THIS REWRITES, and why each form needs different handling:

  1. `bg-[#0d0f17]`            -> `bg-surface-1`      Tailwind arbitrary value
  2. `bg-[#0d0f17]/50`         -> `bg-surface-1/50`   arbitrary value + opacity
  3. `shadow-[0_0_8px_#00f0ff]`-> `shadow-[0_0_8px_var(--color-accent)]`
  4. `text-slate-400`          -> `text-text-muted`   palette class, keyed by UTILITY
  5. `stopColor="#00f0ff"`    -> `style={{stopColor:'var(--color-accent)'}}`

Case 5 is the one that makes a literal find-and-replace unsafe. An SVG *attribute* does not
resolve `var()`; `stopColor="var(--color-accent)"` renders as nothing, the chart loses its
gradient, and no error is thrown. So SVG colour attributes are rewritten to `style={{...}}`,
which is unambiguously CSS.

Cases 1â€“3 produce `var(--color-â€¦)` rather than a bare token name, because an arbitrary
Tailwind value must contain a real CSS expression. Cases 4 and 5 come from the generated
(utility, colour) map.

Every file is backed up in memory, the rewrite is reported per file, and `--apply` is
required to write. On failure the tree is restored byte-for-byte from those backups, which
matters because this touches 44 files and a half-finished migration is worse than none.

Run:  python apply_token_migration.py            # dry run, prints the plan
      python apply_token_migration.py --apply    # write it
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
SRC = ROOT / "frontend" / "src"
PALETTE = ROOT / "scripts" / "token-map" / "paletteMigration.json"
TOKENS = ROOT / "scripts" / "token-map" / "themeTokens.json"

CLASS = re.compile(
    r"\b(text|bg|border|ring|from|to|via|fill|stroke|shadow|divide|outline|decoration|placeholder|caret|accent)"
    r"-((?:white|black|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal"
    r"|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)(?:-[0-9]{2,3})?(?:/\[[^\]]*\]|/\d+)?)"
)

#: Tailwind arbitrary value: `bg-[#0d0f17]` or `bg-[#0d0f17]/50`.
TAILWIND_HEX = re.compile(
    r"\b(bg|text|border|stroke|fill|from|to|via|shadow|ring|outline|decoration|accent|caret)"
    r"-\[#([0-9a-fA-F]{6})\](/([0-9]+))?"
)

#: Tailwind arbitrary shadow with an embedded hex.
SHADOW_HEX = re.compile(r"shadow-\[([^\]\[]*?)_?#([0-9a-fA-F]{6})([^\]]*?)\]")

#: SVG colour presentation attributes. The trailing group captures the element's own
#: closing bracket (`/>` or `>`) so it can be re-emitted after `style={{...}}`.
SVG_ATTR = re.compile(r"\b(stopColor|stroke|fill)=\"(#[0-9a-fA-F]{6})\"(\s*/?>)")

#: Any remaining bare hex in a quoted string, e.g. a palette array or a ternary.
BARE_HEX = re.compile(r"(?P<q>['\"])(#[0-9a-fA-F]{6})(?P=q)")


def main() -> int:
    apply = "--apply" in sys.argv

    hex_map = json.loads(TOKENS.read_text(encoding="utf-8"))["hexToToken"]
    palette = json.loads(PALETTE.read_text(encoding="utf-8"))["pairs"]

    def css(token: str) -> str:
        return f"var(--color-{token})"

    # Union of every token the migration can emit, checked against index.css before any
    # write. A token referenced but not defined renders as nothing, which is precisely the
    # silent failure this migration is otherwise full of.
    defined = set(
        re.findall(r"--color-([a-z0-9-]+)\s*:", (SRC / "index.css").read_text(encoding="utf-8"))
    )
    needed = set(hex_map.values()) | set(palette.values())
    missing = sorted(needed - defined)
    if missing:
        print(f"index.css does not define {len(missing)} tokens the migration emits:")
        for token in missing:
            print(f"  --color-{token}")
        print("\nRefusing to apply. Add them first.")
        return 1

    backups: dict[pathlib.Path, bytes] = {}
    changes: list[tuple[str, int, int]] = []

    try:
        for path in sorted(SRC.rglob("*")):
            if path.suffix not in {".ts", ".tsx"} or not path.is_file():
                continue
            original = path.read_text(encoding="utf-8")
            if "#" not in original and "slate-" not in original and "cyan-" not in original:
                continue

            text = original
            before = len(text)

            # 1. shadow arbitrary with hex
            text = SHADOW_HEX.sub(
                lambda m: f"shadow-[{m.group(1)}_var(--color-{hex_map.get('#' + m.group(2).lower(), m.group(2))}){m.group(3)}]",
                text,
            )

            # 2. SVG colour attributes -> style={{...}}, because attributes do not resolve var().
            # Built by concatenation, not an f-string: the target contains four literal
            # braces (`style={{x:'y'}}`) and f-string brace escaping turns that into a
            # syntax error rather than the text. In a plain string `{{` is just two chars.
            def svg_sub(m: re.Match[str]) -> str:
                token = hex_map.get(m.group(2).lower())
                if not token:
                    return m.group(0)
                return "style={{" + m.group(1) + ": '" + css(token) + "'}}" + m.group(3)

            text = SVG_ATTR.sub(svg_sub, text)

            # 3. Tailwind arbitrary values
            text = TAILWIND_HEX.sub(
                lambda m: f"{m.group(1)}-[{css(hex_map.get('#' + m.group(2).lower(), m.group(2)))}]"
                + (f"/{m.group(3)}" if m.group(3) else ""),
                text,
            )

            # 4. bare quoted hex (palette arrays, ternaries)
            def bare_sub(m: re.Match[str]) -> str:
                token = hex_map.get(m.group(2).lower())
                if not token:
                    return m.group(0)
                return f"{m.group('q')}{css(token)}{m.group('q')}"

            text = BARE_HEX.sub(bare_sub, text)

            # 5. Tailwind palette classes, keyed by (utility, colour)
            text = CLASS.sub(
                lambda m: f"{m.group(1)}-{palette.get(f'{m.group(1)}-{m.group(2)}', f'{m.group(1)}-{m.group(2)}')}",
                text,
            )

            if text != original:
                changes.append((str(path.relative_to(ROOT)), before, len(text)))
                backups[path] = original.encode("utf-8")
                if apply:
                    path.write_text(text, encoding="utf-8")

        print(f"{len(changes)} files would change" if not apply else f"{len(changes)} files changed")
        for rel, before, after in changes[:12]:
            print(f"  {rel}  {before} -> {after} bytes")
        if len(changes) > 12:
            print(f"  â€¦ and {len(changes) - 12} more")
        if not apply:
            print("\nDRY RUN. Re-run with --apply to write.")
        return 0
    except Exception:
        for path, data in backups.items():
            path.write_bytes(data)
        print(f"\nERROR â€” restored {len(backups)} files byte-for-byte.")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
