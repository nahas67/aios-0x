"""Generate the (utility, colour) -> design-token map, and print it for review.

WHY (UTILITY, COLOUR) AND NOT COLOUR ALONE.

Measured with `audit_palette_roles.py`: 3,449 class occurrences, 244 distinct values, 38 of
which are used in more than one utility role. A single override per colour therefore cannot
be right — `slate-400` is text 428 times out of 430, but also `fill` once and `to` once.
Repainting it as a text token would theme those two outliers wrongly.

Keying on the pair handles this correctly, because `text-slate-400` and `border-slate-400`
resolve through different entries and can legitimately land on different tokens.

THE DOMINANCE FALLBACK. Where a colour is used in several roles, each entry maps
independently from that utility's own rule set rather than from the colour's overall
majority. That means a `bg-cyan-500` and a `text-cyan-500` can become different tokens,
which is the point.

NOTHING IS APPLIED HERE. This prints a map and writes a JSON proposal. Applying it is a
separate step, so the map can be read before it rewrites 3,449 sites.

Run:  python build_palette_map.py
"""

from __future__ import annotations

import collections
import json
import pathlib
import re

SRC = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X\frontend\src")
# Written OUTSIDE src/. This is build-time provenance for the migration, not runtime code:
# a JSON file under src/ is reachable by the bundler and would ship in the console bundle
# for no benefit. The rule tables above are the source of truth; this is a snapshot.
OUT = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X\scripts\token-map\paletteMigration.json")

CLASS = re.compile(
    r"\b(text|bg|border|ring|from|to|via|fill|stroke|shadow|divide|outline|decoration|placeholder|caret|accent)"
    r"-((?:white|black|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal"
    r"|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)(?:-[0-9]{2,3})?(?:/\[[^\]]*\]|/\d+)?)"
)

NEUTRALS = {"white", "black", "slate", "gray", "zinc", "neutral", "stone"}

#: text-utility rule for the neutral ramp: (family, shade) -> token.
NEUTRAL_TEXT = {
    ("white", None): "text-strong",
    ("slate", "100"): "text-strong",
    ("slate", "200"): "text-strong",
    ("slate", "300"): "text",
    ("slate", "400"): "text-muted",
    ("slate", "500"): "text-subtle",
    ("slate", "600"): "text-subtle",
    ("slate", "700"): "text-dim",
    ("slate", "800"): "text-dim",
    ("slate", "900"): "text-dim",
    ("zinc", "400"): "text-muted",
    ("zinc", "500"): "text-subtle",
    ("neutral", "400"): "text-muted",
    ("stone", "400"): "text-muted",
    ("black", None): "text-strong",
}

#: colour-family rule for text-utility sites.
FAMILY_TEXT = {
    "cyan": "accent",
    "teal": "accent-soft",
    "sky": "accent-info",
    "blue": "accent-info",
    "emerald": "positive",
    "green": "positive",
    "lime": "positive",
    "teal-soft": "positive",
    "amber": "warning",
    "yellow": "warning",
    "orange": "warning",
    "rose": "destructive",
    "red": "destructive",
    "violet": "violet",
    "indigo": "violet",
    "purple": "violet",
    "fuchsia": "magenta",
    "pink": "magenta",
}

#: border-utility: white-alpha maps to the border ramp, families to their own colour.
WHITE_ALPHA_BORDER = {
    "0.02": "border-faint",
    "0.03": "border-faint",
    "0.04": "border-subtle",
    "0.05": "border-subtle",
    "0.06": "border-subtle",
    "0.08": "border-strong",
    "0.1": "border-strong",
    "0.12": "border-strong",
    "10": "border-subtle",
    "20": "border-strong",
}

WHITE_ALPHA_SURFACE = {
    "0.02": "surface-veil",
    "0.03": "surface-veil",
    "0.04": "surface-veil",
    "0.05": "surface-raised",
    "0.06": "surface-raised",
    "0.08": "surface-raised",
    "0.1": "surface-overlay",
    "10": "surface-raised",
    "20": "surface-overlay",
}

DARK_ALPHA_SURFACE = {
    "30": "surface-sunken",
    "40": "surface-sunken",
    "50": "surface-deep",
    "60": "surface-deep",
    "70": "surface-deep",
}


def split_colour(colour: str) -> tuple[str, str | None, str | None]:
    """'white/[0.06]' -> ('white', None, '0.06');  'cyan-400' -> ('cyan', '400', None)."""
    alpha = None
    base = colour
    if "/" in colour:
        base, _, alpha_s = colour.partition("/")
        alpha = alpha_s.strip("[]")
    if "-" in base:
        family, _, shade = base.partition("-")
        return family, shade, alpha
    return base, None, alpha


def token_for(utility: str, colour: str) -> str | None:
    family, shade, alpha = split_colour(colour)

    # --- surfaces ---------------------------------------------------------
    if utility in {"bg", "divide"}:
        if family == "white" and alpha:
            return WHITE_ALPHA_SURFACE.get(alpha, "surface-raised")
        if family == "black" and alpha:
            return DARK_ALPHA_SURFACE.get(alpha, "surface-sunken")
        if family == "slate" and shade in {"900", "950"}:
            return "surface-deep"
        if family == "slate" and shade in {"800"}:
            return "surface-2"
        if family in {"cyan", "sky"} and shade in {"900", "950"}:
            return "info-bg"
        if family == "emerald" and shade in {"900", "950"}:
            return "positive-bg"
        if family == "rose" and shade in {"900", "950"}:
            return "destructive-bg"
        if family == "amber" and shade in {"900", "950"}:
            return "warning-bg"
        if family in NEUTRALS:
            return "surface-raised"
        return FAMILY_TEXT.get(family, "surface-raised")

    # --- borders ----------------------------------------------------------
    if utility in {"border", "outline", "ring", "divide"}:
        if family == "white" and alpha:
            return WHITE_ALPHA_BORDER.get(alpha, "border-subtle")
        if family in NEUTRALS:
            return "border-subtle"
        return FAMILY_TEXT.get(family, "border-subtle")

    # --- foreground -------------------------------------------------------
    if utility in {"text", "placeholder", "fill", "stroke", "accent", "caret", "from", "to", "via"}:
        if family in NEUTRALS:
            return NEUTRAL_TEXT.get((family, shade), "text")
        return FAMILY_TEXT.get(family, "text")

    return None


def main() -> int:
    usage: collections.Counter[tuple[str, str]] = collections.Counter()
    for path in sorted(SRC.rglob("*")):
        if path.suffix not in {".ts", ".tsx"} or not path.is_file():
            continue
        for utility, colour in CLASS.findall(path.read_text(encoding="utf-8", errors="replace")):
            usage[(utility, colour)] += 1

    mapping: dict[str, str] = {}
    unmapped: list[tuple[str, str, int]] = []
    for (utility, colour), n in usage.items():
        token = token_for(utility, colour)
        if token is None:
            unmapped.append((utility, colour, n))
            continue
        mapping[f"{utility}-{colour}"] = token

    by_token: collections.Counter[str] = collections.Counter(mapping.values())
    print(f"{len(usage)} distinct (utility, colour) pairs -> {len(mapping)} mapped")
    print(f"{len(unmapped)} unmapped\n")

    # A token whose name starts with a UTILITY name collides when that utility is the one
    # being applied. `accent-violet` as a token turned `accent-violet-400` (the CSS
    # accent-color utility) into `accent-accent-violet`, and `var(--color-accent-accent-
    # violet)` resolves to nothing — 58 sites silently unstyled, which is how the first
    # migration shipped a broken value while every other check passed. Violet and magenta
    # are therefore named `violet`/`magenta`, with no utility prefix.
    collisions = sorted(
        {
            f"{key}-{token}"
            for key, token in mapping.items()
            if token.split("-")[0] == key.split("-", 1)[0]
        }
    )
    if collisions:
        print(f"TOKEN/UTILITY COLLISIONS ({len(collisions)}) — these emit a doubled name:")
        for name in collisions[:12]:
            print(f"  {name}")
        print("\nRename the token so it does not begin with a utility name.")
        return 1
    if unmapped:
        print("UNMAPPED (refusing to generate):")
        for utility, colour, n in sorted(unmapped, key=lambda x: -x[2]):
            print(f"  {n:>4}  {utility}-{colour}")
        return 1

    print("token distribution:")
    for token, n in by_token.most_common():
        print(f"  {n:>4} sites -> {token}")

    OUT.write_text(
        json.dumps(
            {
                "source": "generated by scripts/build_palette_map.py — review before applying",
                "pairs": mapping,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
