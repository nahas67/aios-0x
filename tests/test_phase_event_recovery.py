"""Event recovery tests (§26): durable replay, exactly-once cursor semantics.

Simulated crash: a consumer checkpoints mid-log, "dies", restarts, and must
receive EXACTLY the events it missed — nothing twice, nothing skipped — on
both SQLite and PostgreSQL.
"""

from pathlib import Path

import pytest

from core.event_recovery import EventReplay, checkpoint
from core.persistence import BaseMemoryStore, SqliteMemoryStore
from core.pg_store import PostgresMemoryStore

PG_DSN = pytest.importorskip("os").environ.get("AIOS_TEST_PG_DSN", "")


def _seed(store: BaseMemoryStore) -> None:
    for i in range(20):
        kind = "aios.platform.hypothesis_created" if i % 2 == 0 else "aios.c5.order_filled"
        store.append_event(kind, f"ref-{i}", {"i": i})


# ------------------------------------------------------------------ cursors


def test_checkpoint_and_exact_once_resume(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "r.db")
    _seed(store)

    assert checkpoint(store) == 20

    # ---- consumer A processes the first 8 events then "crashes"
    consumer = EventReplay(store, after_seq=0)
    first_batch = consumer.next(limit=8)
    assert [e["i"] for e in (b["payload"] for b in first_batch)] == list(range(8))
    crash_cursor = consumer.after_seq

    # ---- restarted consumer resumes from the persisted cursor
    resumed = EventReplay(store, after_seq=crash_cursor)
    tail = resumed.drain()
    assert [e["payload"]["i"] for e in tail] == list(range(8, 20)), (
        "recovery must deliver exactly the missed events"
    )
    seqs = [e["seq"] for e in tail]
    assert seqs == sorted(seqs), "replay must be strictly ascending"
    all_seen = [e["payload"]["i"] for e in first_batch] + [e["payload"]["i"] for e in tail]
    assert len(all_seen) == len(set(all_seen)) == 20  # nothing twice


def test_kind_prefix_filter_and_empty_drain(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "r.db")
    _seed(store)
    replay = EventReplay(store)
    platform_only = replay.drain(kind_prefix="aios.platform.")
    assert platform_only
    assert all(e["kind"] == "aios.platform.hypothesis_created" for e in platform_only)

    exhausted = EventReplay(store, after_seq=checkpoint(store))
    assert exhausted.drain() == []


def test_pagination_across_many_batches(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "r.db")
    for i in range(57):
        store.append_event("K", str(i), {"i": i})
    replay = EventReplay(store)
    drained = replay.drain()
    assert [e["payload"]["i"] for e in drained] == list(range(57))


def test_read_events_respects_after_seq_strictness(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "r.db")
    _seed(store)
    strict = store.read_events(after_seq=10, limit=100)
    assert strict[0]["seq"] > 10 and strict[-1]["seq"] == 20
    none_after_end = store.read_events(after_seq=9999)
    assert none_after_end == []


# -------------------------------------------------------- postgres parity


@pytest.mark.skipif(not PG_DSN, reason="set AIOS_TEST_PG_DSN for live parity")
def test_pg_recovery_matches_sqlite_semantics() -> None:
    store = PostgresMemoryStore(PG_DSN)
    marker = __import__("uuid").uuid4().hex[:8]
    seqs = [
        store.append_event(f"RECOVERY_{marker}", str(i), {"i": i}) for i in range(12)
    ]
    replay = EventReplay(store, after_seq=seqs[3])
    batch = replay.next(limit=4)
    assert [e["payload"]["i"] for e in batch] == [4, 5, 6, 7]
    tail = replay.drain()
    assert [e["payload"]["i"] for e in tail] == list(range(8, 12))
