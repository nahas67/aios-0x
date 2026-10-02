"""Which UTILITY does each Tailwind palette colour get used with?

This decides whether a palette override is safe or whether it silently mis-themes.

Overriding `--color-slate-400` with a *text* token repaints every `text-slate-400` — and
also every `border-slate-400` and `bg-slate-400`. If a colour is used in more than one
role, one override cannot be right for all of them, and the failure is invisible: the
console still renders, just with the wrong colour on some surfaces.

So the question is not "how many" but "in how many roles". A colour used only as
`text-*` can be overridden with a text token safely. A colour used as both `text-*` and
`border-*` cannot.

Run:  python audit_palette_roles.py
"""

from __future__ import annotations

import collections
import pathlib
import re

SRC = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X\frontend\src")

CLASS = re.compile(
    r"\b(text|bg|border|ring|from|to|via|fill|stroke|shadow|divide|outline|decoration|placeholder|caret|accent)"
    r"-((?:white|black|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal"
    r"|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)(?:-[0-9]{2,3})?(?:/\[[^\]]*\]|/\d+)?)"
)


def main() -> int:
    roles: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)

    for path in sorted(SRC.rglob("*")):
        if path.suffix not in {".ts", ".tsx"} or not path.is_file():
            continue
        for utility, colour in CLASS.findall(path.read_text(encoding="utf-8", errors="replace")):
            roles[colour][utility] += 1

    total = sum(sum(c.values()) for c in roles.values())
    single = [c for c, u in roles.items() if len(u) == 1]
    multi = [(c, dict(u)) for c, u in roles.items() if len(u) > 1]

    print(f"{total} class occurrences, {len(roles)} distinct colour+alpha values")
    print(f"  used in exactly ONE utility role : {len(single)}")
    print(f"  used in SEVERAL roles           : {len(multi)}\n")

    print("Top 18 colours by volume, with their utilities:")
    for colour, counter in sorted(roles.items(), key=lambda kv: -sum(kv[1].values()))[:18]:
        n = sum(counter.values())
        role_str = ", ".join(f"{k}:{v}" for k, v in counter.most_common())
        flag = "" if len(counter) == 1 else "  <-- MULTI-ROLE"
        print(f"  {n:>4}  {colour:<22} {role_str}{flag}")

    print("\nMulti-role colours in full (each needs a per-role decision, not one override):")
    for colour, utilities in sorted(multi, key=lambda kv: -sum(kv[1].values()))[:20]:
        n = sum(utilities.values())
        print(f"  {n:>4}  {colour:<22} {', '.join(f'{k}:{v}' for k, v in sorted(utilities.items(), key=lambda kv: -kv[1]))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
