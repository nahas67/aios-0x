"""Create a verified SQLite backup without mutating the source database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from core.persistence import SqliteMemoryStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"source database does not exist: {args.source}", file=sys.stderr)
        return 2
    store = SqliteMemoryStore(args.source)
    try:
        valid, bad_seq = store.verify_chain()
        if not valid:
            print(f"refusing backup: audit chain invalid at seq {bad_seq}", file=sys.stderr)
            return 1
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        with store._lock:  # noqa: SLF001 - backup is a persistence operation
            destination = store._conn  # noqa: SLF001
            backup_conn = sqlite3.connect(str(args.destination))
            try:
                destination.backup(backup_conn)
                backup_conn.commit()
            finally:
                backup_conn.close()
    finally:
        store.close()

    print(f"backup created: {args.destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
