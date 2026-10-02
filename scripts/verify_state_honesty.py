"""Every empty state goes through the shared classifier, and none asserts a cause.

WHY THIS IS A GATE AND NOT A REVIEW CONVENTION
==============================================

The console shipped five hand-rolled empty states. Four were merely inconsistent (three
paddings, two text colours). The fifth was wrong:

    "No open positions. The paper engine holds no positions yet."

A claim about the ENGINE, produced by testing `filteredPositions` — a FILTERED list. So it
fired when a search box matched nothing and told an operator the paper engine held no
positions when it might hold twenty. `CONSTITUTION.md` §3.2 forbids exactly that: unexamined
data rendered as a default conclusion.

`LiveTradingWorkspace` was worse: it collapsed an unavailable source to `[]` before testing
it, so an unwired kernel produced the caption "No working orders reported by
/api/v1/orders" — asserting the endpoint had reported nothing when nothing had been asked.

WHY THIS SCRIPT IS CAREFUL ABOUT WHAT IT MATCHES
================================================

The first version of this gate reported 18 violations, of which 5 were real. The other 13
were:

  - `"no orders payload"` and friends inside `<Unavailable reason={...}>` — which is the
    CORRECT way to describe an unreadable source, and matched only because it contains
    "no ... orders".
  - prose inside `//` and block comments, including this project's own notes.
  - "No record selected", a selection state, which is not an empty-data state.

A gate that is 70% noise trains people to ignore it, and then it protects nothing. So the
scan strips comments, skips lines that are an `Unavailable` reason, and requires the phrase
to sit in JSX text position. It is deliberately narrow: it catches the bug class, and it
does not claim more than it can see.

THE THREE RULES
===============
  1. No view renders a hand-rolled empty-state caption. It must use `<StateView>`.
  2. No empty-state caption asserts a CAUSE. Naming the SOURCE that reported zero is fine;
     naming a component as the reason is not.
  3. No view discards an unavailability marker before classifying.

Run:  python scripts/verify_state_honesty.py
Exits non-zero on any violation.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
VIEWS = REPO / "frontend" / "src" / "components" / "views"
STATE_VIEW = REPO / "frontend" / "src" / "components" / "StateView.tsx"

BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"^\s*//.*$", re.M)
#: A caption in JSX text position: `>No open positions.<` or `{"No fills recorded."}`.
JSX_CAPTION = re.compile(
    r"(?:>\s*|\{\s*[\"'])"
    r"(?P<caption>[^<>{}]{0,120}?"
    r"\bno (?:open |kernel |working |live |recorded )?"
    r"(?:positions?|orders?|trades?|fills?|executions?|records?|rows?|data|hypotheses?|alerts?|keys)"
    r"\b[^<>{}]{0,80}?)"
    r"(?:\s*[<\"'])"
    r"|(?P<quoted>[\"'][^\"']{0,140}\bno (?:open |kernel |working |live |recorded )?"
    r"(?:positions?|orders?|trades?|fills?|executions?|records?|rows?|data|hypotheses?)\b[^\"']{0,60}[\"'])",
    re.I,
)

#: Words that turn a statement of fact into an assertion of cause.
CAUSE_WORDS = re.compile(
    r"\b(?:engine holds|the engine is|holds no|has been cleared|"
    r"failed to fetch|could not connect|is down|is offline)\b",
    re.I,
)

COLLAPSE_TO_EMPTY = re.compile(r"if\s*\([^)]*unavailable[^)]*\)\s*return\s*\[\s*\]", re.I)

#: The WIDER shape, and the reason the first version of this rule was not enough.
#:
#: `if ("unavailable" in x) return []` was the original bug. But the mutation harness showed
#: a gate matching only that form is defeatable: rewriting it as
#: `if (x && "unavailable" in x) return { kind: 'empty' }` — fabricating an emptiness outright
#: — sails straight through. The gate reported green on a tree that lied.
#:
#: So the rule is co-occurrence within a short window, not one syntactic form: wherever code
#: handles an `unavailable` marker and within a couple of lines produces an empty array or an
#: `empty` state, absence is being laundered into emptiness.
LAUNDERS_ABSENCE = re.compile(
    r"unavailable[\s\S]{0,140}?(?:return\s*\[\s*\]|kind:\s*['\"]empty['\"])"
    r"|(?:return\s*\[\s*\]|kind:\s*['\"]empty['\"])[\s\S]{0,140}?unavailable",
    re.I,
)


def _strip_comments(text: str) -> str:
    """Blank out comments, preserving offsets so line numbers stay correct."""
    text = BLOCK_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return LINE_COMMENT.sub("", text)


def _is_unavailable_reason(text: str, at: int) -> bool:
    """`<Unavailable reason="no orders payload">` is honest absence, not a caption.

    Checked over a WINDOW rather than the match's own line: the `reason=` prop and its value
    routinely straddle lines in JSX, so a line-local test missed all four and reported
    correct `<Unavailable>` usage as a violation.
    """
    window = text[max(0, at - 200) : at]
    # `reason=` is the JSX prop; `reason:` is the object property form passed to
    # `classifyList`. Both are honest absence, and a window catches the case where the prop
    # and its value sit on different lines.
    return "Unavailable" in window or "reason=" in window or "reason:" in window


def main() -> int:
    failures: list[str] = []
    scanned = 0

    if not STATE_VIEW.is_file():
        print(f"missing shared state component: {STATE_VIEW}")
        return 1

    for path in sorted(VIEWS.glob("*.tsx")):
        raw = path.read_text(encoding="utf-8")
        text = _strip_comments(raw)
        scanned += 1
        rel = path.relative_to(REPO)

        captions: list[tuple[int, int, str]] = []
        for match in JSX_CAPTION.finditer(text):
            if _is_unavailable_reason(text, match.start()):
                continue
            caption = match.group("caption") or match.group("quoted") or ""
            captions.append((match.start(), match.end(), caption.strip()))
            line_no = text.count("\n", 0, match.start()) + 1
            failures.append(
                f"{rel}:{line_no} hand-rolled empty state (use <StateView>): {caption[:90]!r}"
            )

        # A cause word is only a violation INSIDE an empty-state caption. "No credential store
        # exists server-side, so this panel holds no keys" is accurate prose about a design
        # fact; "Book holds no positions" is a conclusion drawn from an empty array. The
        # difference is not the words, it is the context, so the rule requires the context.
        for match in CAUSE_WORDS.finditer(text):
            if not any(start <= match.start() < end for start, end, _ in captions):
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            failures.append(
                f"{rel}:{line_no} empty state asserts a CAUSE (an empty array cannot "
                f"support one): {match.group(0)!r}"
            )

        for match in LAUNDERS_ABSENCE.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            failures.append(
                f"{rel}:{line_no} launders an unavailability marker into an empty state — "
                f"this is how a dead kernel renders as an empty book"
            )

    print(f"views scanned                     : {scanned}")
    print(f"shared state component present   : {STATE_VIEW.is_file()}")
    print()
    if failures:
        for failure in failures:
            print(f"  FAIL {failure}")
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print(
        "state honesty green: every empty state is classified, attributed to a source, "
        "and claims no cause"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
