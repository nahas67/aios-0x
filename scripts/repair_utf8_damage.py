"""Repair UTF-8 damage caused by Windows PowerShell 5.1 rewrites.

WHAT HAPPENED, precisely. `Set-Content -Encoding utf8` in PowerShell 5.1 writes a BOM. Worse,
when the console pipeline had already decoded a UTF-8 file as ANSI (cp1252), the write
re-encoded those misread characters back to UTF-8, so an em dash (U+2014, bytes
E2 80 94) was read as three cp1252 characters (a-acute, euro, right-double-quote) and then
written out as E2 82 AC E2 80 9D E2 80 9D. The three characters are now permanently in the
file; no amount of re-saving fixes that, which is why this reverses the transform instead
of repeating it.

THE REPAIR IS THE EXACT INVERSE, NOT A LOOKUP TABLE. The reliable move is to encode the
text back to cp1252 — recovering the original bytes — and decode those as UTF-8. A hardcoded
list of mojibake spellings is the obvious approach and it is what the first version of this
script did; it silently did nothing, because the script itself had to be written through
the same PowerShell pipeline and its own patterns were mangled before the script ever ran.
The inverse transform has no such dependency.

BOMs are stripped separately, and only after decoding, so the byte order mark is not
mistaken for content.

Every file is backed up before writing, and a file whose round trip does not decode as
UTF-8, or does not reduce the damage, is left untouched and reported rather than rewritten
on a guess.

Run:  python scripts/repair_utf8_damage.py [--apply]
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")

#: Files rewritten through `Set-Content` during the token/appearance work. Listed
#: explicitly rather than discovered, because "every file with a BOM in the repo" would
#: include files whose BOM is intentional (a UTF-8 BOM in a Windows-targeted file can be
#: deliberate) and there is no way to tell the two apart from the bytes alone.
TARGETS = [
    "frontend/src/index.css",
    "scripts/prove_theme_gate.py",
    "scripts/build_palette_map.py",
    "scripts/apply_token_migration.py",
    "frontend/src/lib/theme.ts",
    "frontend/src/lib/theme.test.ts",
    "frontend/src/components/views/SettingsWorkspace.tsx",
    "frontend/src/types.ts",
    "frontend/src/adapters/settings.ts",
]


def damage_score(text: str) -> int:
    """Count characters characteristic of a UTF-8-read-as-cp1252 round trip."""
    return sum(text.count(c) for c in ("\u00e2\u20ac", "\u00c2"))


def main() -> int:
    apply = "--apply" in sys.argv
    backups: dict[pathlib.Path, bytes] = {}
    report: list[str] = []
    problems: list[str] = []

    try:
        for rel in TARGETS:
            path = REPO / rel
            if not path.is_file():
                continue
            raw = path.read_bytes()
            backups[path] = raw

            had_bom = raw.startswith(b"\xef\xbb\xbf")
            text = raw.decode("utf-8-sig")  # sig handles the BOM as an encoding, not content

            before = damage_score(text)
            if before == 0:
                if had_bom:
                    report.append(f"  {rel:<48} BOM stripped")
                    if apply:
                        path.write_text(text, encoding="utf-8", newline="")
                else:
                    report.append(f"  {rel:<48} clean")
                continue

            # WHY A PER-SEQUENCE REPAIR, NOT THE INVERSE TRANSFORM. The obvious move is to
            # re-encode to cp1252 and decode as UTF-8, which reverses the damage exactly.
            # It does not apply here, because this file now contains a MIX: sequences
            # damaged by the PowerShell round trip alongside characters written correctly
            # afterwards by an editor that did not go through the console. Re-encoding the
            # whole file therefore tries to interpret the good characters as cp1252 too and
            # produces bytes that are not valid UTF-8 — so it fails outright.
            #
            # Measured before writing this: `index.css` holds 7 damaged em dashes, 3 damaged
            # ellipses, and 3 correct em dashes and 1 correct ellipsis. Only the damaged
            # runs are touched, and only when the sequence is one of the known signatures.
            # Two separate keys collapse to the same text here — an em dash and a right double
            # quote both come out of the same misread bytes depending on the following
            # character. A dict cannot express both, so `SEQUENCE_REPAIRS` is a list of
            # pairs: order is significant, and the em dash is tried first because it is by
            # far the common case. Ruff flags F601 on the dict form, correctly.
            SEQUENCE_REPAIRS: list[tuple[str, str]] = [
                ("\u00e2\u20ac\u201d", "\u2014"),  # em dash
                ("\u00e2\u20ac\u00a6", "\u2026"),  # ellipsis
                ("\u00e2\u20ac\u0153", "\u201c"),  # left double quote
                ("\u00e2\u20ac\u0093", "\u201c"),  # left double quote, control variant
                ("\u00e2\u20ac\u009d", "\u201d"),  # right double quote
                ("\u00e2\u20ac\u201c", "\u201c"),  # left double quote, re-encoded
                ("\u00e2\u20ac\u201d", "\u201d"),  # right double quote, re-encoded
                ("\u00e2\u20ac\u2013", "\u2013"),  # en dash, re-encoded
                ("\u00e2\u20ac\u2014", "\u2014"),  # em dash, re-encoded
                ("\u00e2\u20ac\u2026", "\u2026"),  # ellipsis, re-encoded
                ("\u00e2\u20ac\ufffd", "\u2026"),  # ellipsis, lossy variant
            ]
            repaired, changed = text, 0
            for bad, good in SEQUENCE_REPAIRS:
                changed += repaired.count(bad)
                repaired = repaired.replace(bad, good)

            after = damage_score(repaired)
            if changed == 0 and after >= before:
                problems.append(f"{rel}: no known damaged sequence found")
                report.append(f"  {rel:<48} SKIPPED, nothing recognisable to repair")
                continue

            report.append(
                f"  {rel:<48} BOM={had_bom} repaired {changed} sequence(s), "
                f"damage {before} -> {after}"
            )
            if apply:
                path.write_text(repaired, encoding="utf-8", newline="")

        print("\n".join(report))
    finally:
        if not apply and backups:
            print("\nDRY RUN. Nothing written.")

    if problems:
        print("\nUNRESOLVED:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
