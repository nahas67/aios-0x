"""Enumerate every syntactic form a hex literal takes, before migrating any of them.

WHY NOT JUST REPLACE. A colour literal reaches a stylesheet four different ways, and each
needs a different translation:

    bg-[#0d0f17]                  -> bg-surface-1
    bg-[#0d0f17]/50                -> bg-surface-1/50
    stopColor="#00f0ff"            -> style={{ stopColor: 'var(--color-accent)' }}
    { backgroundColor: '#0d0f17' }  -> { backgroundColor: 'var(--color-surface-1)' }

Case 3 is the trap. An SVG *attribute* does not resolve `var()`, so a literal swap
produces `stopColor="var(--color-accent)"`, which is inert — the chart keeps rendering with
no gradient and nothing throws. A migration that looks complete and silently breaks a chart
is worse than no migration, so the forms are counted first and the counts are compared
before and after.

Run:  python audit_hex_sites.py
"""

from __future__ import annotations

import collections
import pathlib
import re

SRC = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X\frontend\src")

HEX = re.compile(r"#[0-9a-fA-F]{6}")

#: (label, regex) — order matters only for reporting; the counts are what matter.
FORMS = [
    # The `[` opening Tailwind's arbitrary value is escaped; inside the group the literal
    # bracket that closes it must not open a character class.
    ("tailwind arbitrary, no opacity", re.compile(r"\b(?:bg|text|border|stroke|fill|from|to|via|shadow|ring|outline|decoration|accent|caret)-\[#([0-9a-fA-F]{6})\](?!/)")),
    ("tailwind arbitrary, with opacity", re.compile(r"\b(?:bg|text|border|stroke|fill|from|to|via|shadow|ring|outline|decoration|accent|caret)-\[#([0-9a-fA-F]{6})\]/([0-9]+)")),
    ("svg attribute", re.compile(r"\b(stopColor|stroke|fill)=\"(#[0-9a-fA-F]{6})\"")),
    ("css object key", re.compile(r"\b(backgroundColor|color|borderColor|stopColor|stroke|fill)\s*:\s*(['\"])#[0-9a-fA-F]{6}\2")),
    ("bare hex in quotes", re.compile(r"(['\"])#[0-9a-fA-F]{6}\1")),
    ("bare hex, anything", re.compile(r"#[0-9a-fA-F]{6}")),
]

#: SVG attributes that must move to `style` to resolve var().
SVG_ATTRS = {"stopColor", "stroke", "fill"}


def main() -> int:
    totals: collections.Counter[str] = collections.Counter()
    uncovered: list[tuple[str, int, str]] = []
    files = 0

    for path in sorted(SRC.rglob("*")):
        if path.suffix not in {".ts", ".tsx", ".css"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not HEX.search(text):
            continue
        files += 1
        rel = path.name

        consumed = [False] * len(text)
        for label, pattern in FORMS[:-1]:
            for m in pattern.finditer(text):
                # Only count if not already inside a longer, earlier-listed form.
                if any(consumed[m.start() : m.end()]):
                    continue
                totals[label] += 1
                for i in range(m.start(), m.end()):
                    consumed[i] = True

        for m in HEX.finditer(text):
            if consumed[m.start()]:
                continue
            line = text.count("\n", 0, m.start()) + 1
            ctx = text[max(0, m.start() - 45) : m.end() + 25].replace("\n", " ")
            uncovered.append((rel, line, ctx))

    print(f"{files} files with colour literals\n")
    for label, _ in FORMS[:-1]:
        print(f"  {totals[label]:>4}  {label}")
    classified = sum(totals.values())
    total = sum(1 for p in sorted(SRC.rglob('*'))
                if p.suffix in {'.ts', '.tsx', '.css'} and p.is_file()
                for _ in HEX.findall(p.read_text(encoding='utf-8', errors='replace')))
    print(f"\n  {total:>4}  TOTAL occurrences")
    print(f"  {total - classified:>4}  not matched by any form below")

    if uncovered:
        print(f"\n{len(uncovered)} unmatched sites — these are the ones a naive")
        print("find-and-replace would leave behind or silently break:")
        for rel, line, ctx in uncovered[:40]:
            print(f"  {rel}:{line}  …{ctx}…")

    print("\nSVG attributes needing `style={...}` (attributes do not resolve var()):")
    for attr in sorted(SVG_ATTRS):
        n = sum(
            len(re.findall(rf"\b{attr}=\"#[0-9a-fA-F]{{6}}\"", p.read_text(encoding="utf-8", errors="replace")))
            for p in SRC.rglob("*")
            if p.suffix in {".ts", ".tsx"} and p.is_file()
        )
        print(f"  {n:>4}  {attr}=...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
