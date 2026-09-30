"""Audit-chain integrity regression tests.

Covers the two failure modes behind the real seq-4507 incident:
  1. Concurrent appenders (separate store instances) interleaving reads and
     writes must not gap the hash chain — append_event is transactional
     (BEGIN IMMEDIATE) since the fix.
  2. A chain that IS gapped must be repairable without touching event content
     (scripts/repair_chain.py relinks and re-verifies).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from core.persistence import SqliteMemoryStore
from scripts.repair_chain import diagnose, recompute


def test_concurrent_appenders_keep_chain_valid(tmp_path: Path) -> None:
    """Two independent store instances appending simultaneously must leave a
    fully valid chain — the race that broke seq 4507 must stay impossible."""
    db = tmp_path / "race.db"
    a = SqliteMemoryStore(db)
    b = SqliteMemoryStore(db)

    errors: list[BaseException] = []

    def worker(store: SqliteMemoryStore, tag: str) -> None:
        try:
            for i in range(40):
                store.append_event(f"race.{tag}", f"{tag}-{i}", {"i": i, "tag": tag})
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(a, "a")),
        threading.Thread(target=worker, args=(b, "b")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, f"appenders raised: {errors!r}"
    assert a.verify_chain() == (True, None)
    assert b.verify_chain() == (True, None)


def test_repair_tool_relinks_gapped_chain_without_touching_content(tmp_path: Path) -> None:
    """Simulate the seq-4507 race gap: row n+1 chains from n-1's hash while row
    n sits between them. The repair tool must relink, preserve every payload,
    and re-verify the full chain."""
    db = tmp_path / "gap.db"
    store = SqliteMemoryStore(db)
    payloads = []
    for i in range(8):
        payload = {"i": i, "data": f"payload-{i}"}
        payloads.append(payload)
        store.append_event("test.kind", f"ref-{i}", payload)

    # Forge the race gap exactly like the real incident: two writers both read
    # the tail (seq 4's predecessor = seq 3's hash); the later row (seq 5) was
    # INSERTED with prev=seq3.hash and its hash computed from that same prev —
    # internally consistent, but skipping seq 4's hash in the linkage.
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    row5 = conn.execute("SELECT * FROM event_log WHERE seq = 5").fetchone()
    row3 = conn.execute("SELECT * FROM event_log WHERE seq = 3").fetchone()
    forged_hash = recompute(
        row5["ts"], row5["kind"], row5["ref_id"], row5["payload_json"], row3["hash"]
    )
    conn.execute(
        "UPDATE event_log SET prev_hash = ?, hash = ? WHERE seq = 5",
        (row3["hash"], forged_hash),
    )
    conn.commit()
    conn.close()

    rows = sqlite3.connect(str(db)).execute(
        "SELECT seq, ts, kind, ref_id, payload_json, prev_hash, hash "
        "FROM event_log ORDER BY seq ASC"
    ).fetchall()
    rows_as_dict = [
        {
            "seq": r[0], "ts": r[1], "kind": r[2], "ref_id": r[3],
            "payload_json": r[4], "prev_hash": r[5], "hash": r[6],
        }
        for r in rows
    ]
    report = diagnose(rows_as_dict)
    assert report["tampered"] == []
    assert report["breaks"], "gap must be detected"
    assert report["breaks"][0]["seq"] == 5
    assert report["breaks"][0]["content_intact"], "content must still verify"

    # Run the repair tool end-to-end (it makes its own byte-exact backup).
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/repair_chain.py", "--db", str(db)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[OK] chain verified" in result.stdout

    # Full chain valid again…
    assert store.verify_chain() == (True, None)

    # …and every payload byte-identical to what was originally written.
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    got = [
        (r["kind"], r["ref_id"], r["payload_json"])
        for r in conn.execute("SELECT * FROM event_log ORDER BY seq ASC")
    ]
    want = [
        ("test.kind", f"ref-{i}", __import__("json").dumps(p, sort_keys=True, separators=(",", ":")))
        for i, p in enumerate(payloads)
    ]
    assert got == want


def test_repair_refuses_when_content_tampered(tmp_path: Path) -> None:
    """If a row's hash no longer verifies against its own content, the tool must
    abort instead of laundering tampered content into a valid chain."""
    db = tmp_path / "tamper.db"
    store = SqliteMemoryStore(db)
    for i in range(5):
        store.append_event("test.kind", f"ref-{i}", {"i": i})
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE event_log SET payload_json = ? WHERE seq = 3",
        ('{"i": 3, "evil": true}',),
    )
    conn.commit()
    conn.close()
    rows = [
        {
            "seq": r[0], "ts": r[1], "kind": r[2], "ref_id": r[3],
            "payload_json": r[4], "prev_hash": r[5], "hash": r[6],
        }
        for r in sqlite3.connect(str(db)).execute(
            "SELECT seq, ts, kind, ref_id, payload_json, prev_hash, hash "
            "FROM event_log ORDER BY seq ASC"
        )
    ]
    report = diagnose(rows)
    assert report["tampered"], "tampering must be flagged"
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/repair_chain.py", "--db", str(db), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 3, result.stdout + result.stderr
