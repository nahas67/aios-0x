"""Repair a broken hash-chain linkage in the SQLite event log WITHOUT touching content.

Incident class this fixes: a concurrent-writer race left seq N chained from the
WRONG predecessor while an interleaved row was written between them (real
incident: seq 4507 chained from 4505 while 4506 was appended between them).
Every row's *content* (ts|kind|ref_id|payload, hashed with its original
prev_hash) still verifies — only the linkage is discontinuous.

Safety model:
  1. Refuses to run unless a byte-exact backup of the database exists next to it
     (created automatically as <db>.pre-repair-<ts> if missing).
  2. Proves content integrity for every relinked row before rewriting anything:
     recompute the row hash from its ORIGINAL prev_hash — a match proves the
     content was never altered; only prev_hash fields are then rewritten.
  3. Relinks from the first bad seq onward: prev_hash := previous row's hash,
     hash := recomputed. Cascades are handled by walking rows in seq order.
  4. Verifies the FULL chain afterwards and writes a JSON manifest recording
     the diagnosis, method, and before/after verification results.

Usage:
    python scripts/repair_chain.py --db data/command_center.db [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS = "0000000000000000000000000000000000000000000000000000000000000000"


def recompute(ts: str, kind: str, ref: str | None, payload: str, prev: str) -> str:
    return hashlib.sha256(
        f"{ts}|{kind}|{ref}|{payload}|{prev}".encode()
    ).hexdigest()


def load_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT seq, ts, kind, ref_id, payload_json, prev_hash, hash "
        "FROM event_log ORDER BY seq ASC"
    ).fetchall()


def diagnose(rows: list[sqlite3.Row]) -> dict[str, Any]:
    """Find linkage breaks; also detect content tampering (hash recompute mismatch)."""
    breaks: list[dict[str, Any]] = []
    tampered: list[int] = []
    expected_prev = GENESIS
    for row in rows:
        recomputed = recompute(
            row["ts"], row["kind"], row["ref_id"], row["payload_json"], row["prev_hash"]
        )
        content_ok = row["hash"] == recomputed
        if row["hash"] != recomputed:
            tampered.append(row["seq"])
        if row["prev_hash"] != expected_prev:
            breaks.append(
                {
                    "seq": row["seq"],
                    "stored_prev": row["prev_hash"],
                    "expected_prev": expected_prev,
                    "content_intact": content_ok,
                }
            )
        # Track the stored hash as the next expected prev: a relink will
        # deterministically fix downstream rows from the first break onward.
        expected_prev = row["hash"]
    return {"breaks": breaks, "tampered": tampered, "total": len(rows)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--dry-run", action="store_true", help="diagnose only, no writes")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[X] database not found: {db}")
        return 2

    # ---- safety: byte-exact backup -------------------------------------
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup = db.with_name(f"{db.name}.pre-repair-{stamp}")
    if not backup.exists():
        shutil.copy2(db, backup)
        print(f"[backup] byte-exact copy -> {backup}")
    else:
        print(f"[backup] existing backup found: {backup}")

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    rows = load_rows(conn)
    report = diagnose(rows)
    breaks = report["breaks"]
    if report["tampered"]:
        print(f"[X] CONTENT TAMPERING detected at seq {report['tampered'][:5]} — aborting. "
              "Relink would forge a chain over altered content. Preserve the backup and investigate.")
        return 3
    if not breaks:
        print("[OK] chain is fully linked — nothing to repair.")
        return 0

    first_bad = breaks[0]["seq"]
    print(f"[diagnose] {len(breaks)} linkage break(s); first bad seq = {first_bad}")
    print(f"[diagnose] row {first_bad} chained from {breaks[0]['stored_prev'][:12]}… "
          f"but expected {breaks[0]['expected_prev'][:12]}… (content verified intact)")

    if args.dry_run:
        print("[dry-run] no changes made.")
        return 0

    # ---- repair: relink from first_bad onward ---------------------------
    # Build the corrected tail: walk rows in order; the row BEFORE first_bad keeps
    # its stored hash (it is valid); every row from first_bad gets prev = previous
    # row's corrected hash and a recomputed hash.
    corrected: dict[int, tuple[str, str]] = {}
    prev_row = next((r for r in rows if r["seq"] == first_bad - 1), None)
    prev_hash = prev_row["hash"] if prev_row else GENESIS
    with conn:  # single transaction
        for row in rows:
            if row["seq"] < first_bad:
                continue
            new_prev = prev_hash
            new_hash = recompute(
                row["ts"], row["kind"], row["ref_id"], row["payload_json"], new_prev
            )
            conn.execute(
                "UPDATE event_log SET prev_hash = ?, hash = ? WHERE seq = ?",
                (new_prev, new_hash, row["seq"]),
            )
            corrected[row["seq"]] = (new_prev, new_hash)
            prev_hash = new_hash

    # ---- verify ----------------------------------------------------------
    rows2 = load_rows(conn)
    expected_prev = GENESIS
    ok = True
    for row in rows2:
        rec = recompute(row["ts"], row["kind"], row["ref_id"], row["payload_json"], row["prev_hash"])
        if row["prev_hash"] != expected_prev or row["hash"] != rec:
            ok = False
            print(f"[X] verification FAILED at seq {row['seq']}")
            break
        expected_prev = row["hash"]

    manifest = {
        "tool": "scripts/repair_chain.py",
        "run_at": datetime.now(UTC).isoformat(),
        "database": str(db),
        "backup": str(backup),
        "diagnosis": report,
        "action": "content-preserving relink from first bad seq onward",
        "rows_relalinked": sorted(corrected.keys())[:3] + ["…", f"total {len(corrected)}"],
        "verified_after": ok,
        "note": (
            "No event content (ts/kind/ref/payload) was modified. Only prev_hash/hash "
            "linkage fields were recomputed to restore continuity after a concurrent-append "
            "race. Root cause fixed in core/persistence.py append_event (BEGIN IMMEDIATE)."
        ),
    }
    manifest_path = db.with_name(f"{db.name}.chain-repair-manifest-{stamp}.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[manifest] {manifest_path}")
    print("[OK] chain verified" if ok else "[X] chain still broken — restore backup and investigate")
    conn.close()
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
