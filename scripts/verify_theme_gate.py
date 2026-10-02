"""Enforce ADR-008's token gate: colours live in index.css and nowhere else.

The gate exists because a status document or a plan is not a constraint. It turned a
number someone wrote down — "206 hex literals" — into something that fails.

WHAT IT CHECKS, and why each is separate:

  1. No hex literal outside index.css. The literal rule, verbatim from ADR-008.
  2. No hardcoded Tailwind palette class. The FIRST version of the gate checked only hex
     and reported zero — which was true and useless. The palette classes were 3,455
     occurrences across 300 values, 17x the hex count, and none of them theme. A gate that
     passes while the feature it guards does not work is worse than no gate.
  3. Tokens referenced actually exist. The migration emits `var(--color-…)`; a reference
     to an undefined token renders as nothing, silently.
  4. Both themes define the same token set. A theme that sets only `surface-0` leaves
     every panel on the previous theme's background.
  5. `var(--…)` is genuinely used. The pre-migration tree had 0 uses while declaring
     tokens nothing read — a token layer that exists on paper is the exact state ADR-004
     decision 2 produced and ADR-008 exists to end.

Run:  python scripts/verify_theme_gate.py
Exits non-zero on any violation.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
SRC = REPO / "frontend" / "src"
CSS = SRC / "index.css"

HEX = re.compile(r"#[0-9a-fA-F]{6}")
#: Tailwind's built-in colour families. A theme cannot restyle `text-slate-400`, because
#: those resolve to Tailwind's own palette rather than to a design token.
TAILWIND_PALETTE = re.compile(
    r"\b(?:text|bg|border|ring|from|to|via|fill|stroke|shadow|divide|outline|decoration"
    r"|placeholder|caret|accent)-(?:white|black|slate|gray|zinc|neutral|stone|red|orange"
    r"|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia"
    r"|pink|rose)(?:-[0-9]{2,3})?(?:/\[[^\]]*\]|/\d+)?"
)
TOKEN_DEF = re.compile(r"--color-([a-z0-9-]+)\s*:")
TOKEN_USE = re.compile(r"var\(--color-([a-z0-9-]+)\)")


def main() -> int:
    failures: list[str] = []

    sources = [
        p
        for p in sorted(SRC.rglob("*"))
        if p.suffix in {".ts", ".tsx"} and p.is_file()
    ]
    css_text = CSS.read_text(encoding="utf-8")

    # Computed up front: check 2 needs the token names to tell a token from a palette
    # colour, and check 3 needs them to verify references resolve. Defining it inside check
    # 3 — where it originally lived — left check 2 reading an unbound local.
    defined = set(TOKEN_DEF.findall(css_text))

    # 1. no hex outside index.css
    hex_sites = [
        (p.relative_to(REPO), HEX.findall(p.read_text(encoding="utf-8", errors="replace")))
        for p in sources
    ]
    hex_sites = [(rel, hits) for rel, hits in hex_sites if hits]
    total_hex = sum(len(h) for _, h in hex_sites)
    if hex_sites:
        failures.append(
            f"{total_hex} hex literals outside index.css: "
            + ", ".join(f"{rel} ({len(h)})" for rel, h in hex_sites[:6])
        )

    # 2. no hardcoded Tailwind palette classes
    #
    # A token whose name happens to look like a Tailwind colour is NOT a palette class:
    # `accent-violet` is the CSS accent-color utility plus our `violet` token, and
    # `text-text-muted` is `text-` plus the `text-muted` token. Counting those as
    # hardcoded palette usage is a false positive that would force the very classes the
    # migration produces to be flagged forever — and the first version of this gate did
    # exactly that, reporting 54 violations on a tree where every one was correct.
    #
    # So token names are excluded before scanning. A colour segment is a token usage when
    # it begins with a defined token name followed by `-`, `/`, or end of segment.
    token_names = sorted(defined, key=len, reverse=True)

    def is_token(colour: str) -> bool:
        return any(
            colour == name or colour.startswith(name + "-") or colour.startswith(name + "/")
            for name in token_names
        )

    palette_sites: list[tuple[object, list[str]]] = []
    for path in sources:
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [
            m.group(0)
            for m in TAILWIND_PALETTE.finditer(text)
            # m.group(0) is `utility-colour[-shade][-alpha]`; split the colour part off.
            if not is_token(m.group(0).split("-", 1)[1] if "-" in m.group(0) else m.group(0))
        ]
        if hits:
            palette_sites.append((path.relative_to(REPO), hits))
    total_palette = sum(len(h) for _, h in palette_sites)
    if palette_sites:
        failures.append(
            f"{total_palette} hardcoded Tailwind palette classes: "
            + ", ".join(f"{rel} ({len(h)})" for rel, h in palette_sites[:6])
        )

    # 3. every referenced token is defined
    used: set[str] = set()
    for path in sources:
        used |= set(TOKEN_USE.findall(path.read_text(encoding="utf-8", errors="replace")))
    undefined = sorted(used - defined)
    if undefined:
        failures.append(
            f"{len(undefined)} tokens referenced but not defined in index.css: "
            + ", ".join(f"--color-{t}" for t in undefined[:10])
        )

    # 4. both themes define the same tokens
    root_block = re.search(r"(?m)^:root\s*\{(.*?)^\}", css_text, re.S)
    paper_block = re.search(r"(?m)^\[data-theme='paper'\]\s*\{(.*?)^\}", css_text, re.S)
    if not root_block or not paper_block:
        failures.append("index.css is missing a :root block or a [data-theme='paper'] block")
    else:
        root_tokens = set(TOKEN_DEF.findall(root_block.group(1)))
        paper_tokens = set(TOKEN_DEF.findall(paper_block.group(1)))
        only_root = sorted(root_tokens - paper_tokens)
        only_paper = sorted(paper_tokens - root_tokens)
        if only_root:
            failures.append(
                f"{len(only_root)} tokens defined for :root but not for the paper theme: "
                + ", ".join(f"--color-{t}" for t in only_root[:10])
            )
        if only_paper:
            failures.append(
                f"{len(only_paper)} tokens defined for paper but not for :root: "
                + ", ".join(f"--color-{t}" for t in only_paper[:10])
            )

    # 5. the tokens are actually consumed
    if not used:
        failures.append(
            "no var(--color-…) is referenced anywhere: the token layer is declared but "
            "unused, which is the exact state ADR-004 decision 2 produced"
        )

    print(f"hex literals outside index.css : {total_hex}")
    print(f"hardcoded palette classes      : {total_palette}")
    print(f"tokens defined in index.css   : {len(defined)}")
    print(f"tokens referenced in code      : {len(used)}")
    print(f"tokens defined but unused     : {len(defined - used)}")
    print()
    if failures:
        for f in failures:
            print(f"  FAIL {f}")
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("theme gate green: colours are tokens, tokens exist, both themes agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
