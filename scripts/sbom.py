#!/usr/bin/env python3
"""Generate a CycloneDX SBOM from requirements.lock (goal G230).

The lock file is the resolved dependency closure; the SBOM is the same
closure in a machine-readable interchange format (CycloneDX 1.5 JSON) that
scanners and auditors consume. Generated, never hand-edited: running this
script is part of the release path, and tests pin that the SBOM covers
exactly the lock — every pinned distribution present once, nothing else.

Deliberately offline: no registry lookups, no hash downloads. Hashes and
vulnerability data arrive from the scanner that consumes the SBOM, not from
its generator — a generator that phoned a registry would make the bill of
materials depend on the registry's answer that day.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock"

SPEC_VERSION = "1.5"
BOM_FORMAT = "CycloneDX"
TOOL_NAME = "aios-sbom"


def parse_lock(lock_path: Path = LOCK) -> list[tuple[str, str]]:
    """Parse ``name==version`` lines, skipping comments and blanks.

    Refuses unpinned lines rather than guessing: a lock file with a bare
    package name is not locked, and an SBOM built from it would certify
    versions nobody resolved.
    """
    entries: list[tuple[str, str]] = []
    for lineno, line in enumerate(lock_path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "==" not in stripped:
            raise ValueError(
                f"{lock_path}:{lineno}: unpinned entry {stripped!r}. "
                "The lock must pin every distribution or it is not a lock."
            )
        name, _, version = stripped.partition("==")
        name, version = name.strip(), version.strip()
        if not name or not version:
            raise ValueError(f"{lock_path}:{lineno}: malformed entry {stripped!r}")
        entries.append((name, version))
    seen = [name for name, _ in entries]
    duplicates = sorted({name for name in seen if seen.count(name) > 1})
    if duplicates:
        raise ValueError(f"{lock_path}: duplicate entries for {duplicates}")
    return entries


def build_sbom(entries: list[tuple[str, str]]) -> dict:
    """CycloneDX document for the closure. Sorted by name so output is
    byte-stable: a diff between two SBOMs means the closure changed."""
    return {
        "bomFormat": BOM_FORMAT,
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": {
            "tools": [{"name": TOOL_NAME}],
        },
        "components": [
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name}@{version}",
            }
            for name, version in sorted(entries)
        ],
    }


def write_sbom(out_path: Path, sbom: dict) -> Path:
    out_path.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate CycloneDX SBOM from requirements.lock")
    parser.add_argument("--out", default="sbom.json", help="Output path (default: sbom.json)")
    args = parser.parse_args(argv)
    entries = parse_lock()
    out = write_sbom(Path(args.out), build_sbom(entries))
    print(f"SBOM: {len(entries)} components -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
