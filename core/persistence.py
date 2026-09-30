"""Persistent institutional memory: hash-chained append-only event log + typed ledgers.

Implements the local tier of the AIOS-0X Memory Model (docs/master/AIOS-0X_MEMORY_MODEL.md):
- RAW events are immutable, hash-chained (tamper-evident), never overwritten.
- Typed tables (predictions, observations, postmortems) reference the log.
- Prediction ledger entries are written BEFORE outcomes and scored after.

SQLite is the Phase 1 local store; the BaseMemoryStore ABC keeps later swaps
(PostgreSQL/Qdrant) adapter-only per Doc 16's zero-lock-in rule. The connection
is shared across threads (event loop + HTTP server) under a re-entrant lock.
"""

import hashlib
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from schemas.contracts import (
    ObservationReport,
    PostmortemRecord,
    PredictionRecord,
)

_GENESIS_HASH = "0" * 64


def _canonical(payload: dict[str, Any]) -> str:
    """Stable JSON serialization for hashing and storage."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class BaseMemoryStore(ABC):
    """Abstract persistence boundary for the AIOS memory fabric."""

    @abstractmethod
    def append_event(self, kind: str, ref_id: str | None, payload: dict[str, Any]) -> int:
        """Append a payload to the tamper-evident log; returns the sequence number."""

    @abstractmethod
    def verify_chain(self) -> tuple[bool, int | None]:
        """Verify the full hash chain; returns (ok, first_bad_seq or None)."""

    @abstractmethod
    def save_prediction(self, record: PredictionRecord) -> None:
        """Insert or replace a prediction-ledger row."""

    @abstractmethod
    def save_observation(self, report: ObservationReport) -> None:
        """Insert an observation row."""

    @abstractmethod
    def save_postmortem(self, record: PostmortemRecord) -> None:
        """Insert a postmortem row."""

    @abstractmethod
    def pnl_series(self) -> list[tuple[str, float]]:
        """Return (execution_id, realized_pnl) pairs in insertion order."""

    @abstractmethod
    def counts(self) -> dict[str, int]:
        """Row counts per table for run summaries."""

    @abstractmethod
    def iter_event_payloads(self, kind: str) -> list[dict[str, Any]]:
        """All payloads of one event kind in sequence order."""

    @abstractmethod
    def read_events(
        self, after_seq: int = 0, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Events STRICTLY AFTER a sequence number, ascending order.

        The durability contract behind crash recovery and service restarts:
        a consumer checkpoints {seq}, and read_events(after_seq) returns
        exactly what it missed — nothing twice, nothing skipped.
        Each row: {seq, ts, kind, ref_id, payload}.
        """


class SqliteMemoryStore(BaseMemoryStore):
    """Local SQLite implementation of the memory store (thread-safe)."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        # Wait (instead of failing) when another process holds the write lock,
        # so cross-process appenders serialize rather than interleave.
        self._conn.execute("PRAGMA busy_timeout = 10000")
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS event_log (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    ref_id TEXT,
                    payload_json TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS predictions (
                    prediction_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    strategy_id TEXT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exit_reason TEXT,
                    realized_pnl REAL,
                    direction_correct INTEGER,
                    confidence_score REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS observations (
                    observation_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    actual_pnl REAL NOT NULL,
                    direction_correct INTEGER,
                    exit_reason TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS postmortems (
                    postmortem_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    prediction_id TEXT,
                    hypothesis_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------------ events

    def append_event(self, kind: str, ref_id: str | None, payload: dict[str, Any]) -> int:
        with self._lock:
            cur = self._conn.cursor()
            # BEGIN IMMEDIATE takes the database write lock BEFORE reading the
            # previous hash. Without it, two writers (separate processes or
            # store instances) could both read the same tail hash and interleave
            # their inserts, leaving a gap in the hash chain (a real incident:
            # seq 4507 chained from 4505 while 4506 was written between them).
            cur.execute("BEGIN IMMEDIATE")
            try:
                prev_row = cur.execute(
                    "SELECT hash FROM event_log ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                prev = prev_row["hash"] if prev_row else _GENESIS_HASH
                ts = _utc_now_iso()
                body = _canonical(payload)
                digest = hashlib.sha256(
                    f"{ts}|{kind}|{ref_id}|{body}|{prev}".encode()
                ).hexdigest()
                cur.execute(
                    "INSERT INTO event_log (ts, kind, ref_id, payload_json, prev_hash, hash) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ts, kind, ref_id, body, prev, digest),
                )
                self._conn.commit()
                return int(cur.lastrowid or 0)
            except BaseException:
                self._conn.rollback()
                raise

    def verify_chain(self) -> tuple[bool, int | None]:
        with self._lock:
            expected_prev = _GENESIS_HASH
            for row in self._conn.execute(
                "SELECT seq, ts, kind, ref_id, payload_json, prev_hash, hash "
                "FROM event_log ORDER BY seq ASC"
            ):
                recomputed = hashlib.sha256(
                    f"{row['ts']}|{row['kind']}|{row['ref_id']}|{row['payload_json']}|"
                    f"{row['prev_hash']}".encode()
                ).hexdigest()
                if row["prev_hash"] != expected_prev or row["hash"] != recomputed:
                    return False, int(row["seq"])
                expected_prev = row["hash"]
            return True, None

    # ------------------------------------------------------------- typed views

    def save_prediction(self, record: PredictionRecord) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO predictions "
                "(prediction_id, created_at, hypothesis_id, strategy_id, symbol, direction, "
                " status, exit_reason, realized_pnl, direction_correct, confidence_score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.prediction_id,
                    record.created_at.isoformat(),
                    record.hypothesis_id,
                    record.strategy_id,
                    record.symbol,
                    record.direction,
                    record.status,
                    record.exit_reason,
                    record.realized_pnl,
                    None if record.direction_correct is None else int(record.direction_correct),
                    record.confidence_score,
                ),
            )
            self._conn.commit()

    def save_observation(self, report: ObservationReport) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO observations "
                "(observation_id, execution_id, actual_pnl, direction_correct, exit_reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    report.observation_id,
                    report.execution_id,
                    report.actual_pnl,
                    None if report.direction_correct is None else int(report.direction_correct),
                    report.exit_reason,
                    _utc_now_iso(),
                ),
            )
            self._conn.commit()

    def save_postmortem(self, record: PostmortemRecord) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO postmortems "
                "(postmortem_id, execution_id, prediction_id, hypothesis_id, symbol, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.postmortem_id,
                    record.execution_id,
                    record.prediction_id,
                    record.hypothesis_id,
                    record.symbol,
                    _canonical(record.model_dump(mode="json")),
                    _utc_now_iso(),
                ),
            )
            self._conn.commit()

    def pnl_series(self) -> list[tuple[str, float]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT execution_id, actual_pnl FROM observations ORDER BY rowid ASC"
            ).fetchall()
        return [(str(r["execution_id"]), float(r["actual_pnl"])) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._lock:
            result = {}
            for table in ("event_log", "predictions", "observations", "postmortems"):
                row = self._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
                result[table] = int(row["n"])
            return result

    def iter_event_payloads(self, kind: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM event_log WHERE kind = ? ORDER BY seq ASC",
                (kind,),
            ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def read_events(self, after_seq: int = 0, limit: int = 1000) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, ts, kind, ref_id, payload_json FROM event_log "
                "WHERE seq > ? ORDER BY seq ASC LIMIT ?",
                (after_seq, limit),
            ).fetchall()
        return [
            {
                "seq": int(r["seq"]),
                "ts": r["ts"],
                "kind": r["kind"],
                "ref_id": r["ref_id"],
                "payload": json.loads(r["payload_json"]),
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()
