"""Pin the ratified constitution: print the SHA-256 to embed in core/constitution.py.

Usage: python scripts/pin_constitution.py
"""

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSTITUTION = ROOT / "CONSTITUTION.md"


def main() -> None:
    if not CONSTITUTION.exists():
        print("CONSTITUTION.md not found at repo root")
        sys.exit(1)
    digest = hashlib.sha256(CONSTITUTION.read_bytes()).hexdigest()
    print(f'_PINNED_SHA256 = "{digest}"')
    print("Paste the line above into core/constitution.py, replacing the empty pin.")


if __name__ == "__main__":
    main()
