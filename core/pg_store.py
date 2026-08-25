"""PostgreSQL implementation of the AIOS memory store (Phase B data layer).

Same contract, same tamper-evident hash chain, same typed tables as
``SqliteMemoryStore`` — but backed by PostgreSQL for the transactional-state
tier described in the original architecture (Data & State Plane).

Chain semantics are byte-identical to SQLite: ``hash = sha256(
ts|kind|ref_id|payload_json|prev_hash)`` with canonical JSON payloads, so an
audit chain started on SQLite stays verifiable after a migration and both
backends can be run side by side.

psycopg (v3) is imported lazily: environments without it keep working as long
as they never select this store. Connection failures raise immediately —
persistence problems are never silently degraded (fail closed).
"""

import hashlib
import json
import threading
from typing import Any

from core.persistence import BaseMemoryStore, _canonical, _utc_now_iso
from schemas.contracts import (
    ObservationReport,
    PostmortemRecord,
    PredictionRecord,
)

_GENESIS_HASH = "0" * 64


class PostgresMemoryStore(BaseMemoryStore):
    """Server-grade memory store: PostgreSQL + identical hash-chain semantics."""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg  # noqa: PLC0415 - lazy so PG-less installs stay clean
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise ImportError(
                "PostgresMemoryStore requires psycopg >= 3. "
                "Install with: pip install 'psycopg[binary]'"
            ) from exc
        self._dsn = dsn
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn)
        self._conn.autocommit = False
        self._ensure_schema()

    # ------------------------------------------------------------------ schema

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS event_log (
                        seq BIGSERIAL PRIMARY KEY,
                        ts TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        ref_id TEXT,
                        payload_json TEXT NOT NULL,
                        prev_hash TEXT NOT NULL,
                        hash TEXT NOT NULL
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_event_log_kind ON event_log (kind)")
                cur.execute(
                    """
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
                        direction_correct BOOLEAN,
                        confidence_score REAL NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS observations (
                        observation_id TEXT PRIMARY KEY,
                        execution_id TEXT NOT NULL,
                        actual_pnl REAL NOT NULL,
                        direction_correct BOOLEAN,
                        exit_reason TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS postmortems (
                        postmortem_id TEXT PRIMARY KEY,
                        execution_id TEXT NOT NULL,
                        prediction_id TEXT,
                        hypothesis_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
            self._conn.commit()

    # ------------------------------------------------------------------ events

    def append_event(self, kind: str, ref_id: str | None, payload: dict[str, Any]) -> int:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT hash FROM event_log ORDER BY seq DESC LIMIT 1")
                row = cur.fetchone()
                prev = row[0] if row else _GENESIS_HASH
                ts = _utc_now_iso()
                body = _canonical(payload)
                digest = hashlib.sha256(
                    f"{ts}|{kind}|{ref_id}|{body}|{prev}".encode()
                ).hexdigest()
                cur.execute(
                    "INSERT INTO event_log (ts, kind, ref_id, payload_json, prev_hash, hash) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING seq",
                    (ts, kind, ref_id, body, prev, digest),
                )
                seq = int(cur.fetchone()[0])
            self._conn.commit()
            return seq

    def verify_chain(self) -> tuple[bool, int | None]:
        with self._lock:
            expected_prev = _GENESIS_HASH
            with self._conn.cursor(name="verify_chain_cursor") as cur:
                cur.itersize = 1000
                cur.execute(
                    "SELECT seq, ts, kind, ref_id, payload_json, prev_hash, hash "
                    "FROM event_log ORDER BY seq ASC"
                )
                for row in cur:
                    seq, ts, kind, ref_id, body, prev_hash, digest = row
                    recomputed = hashlib.sha256(
                        f"{ts}|{kind}|{ref_id}|{body}|{prev_hash}".encode()
                    ).hexdigest()
                    if prev_hash != expected_prev or digest != recomputed:
                        return False, int(seq)
                    expected_prev = digest
            return True, None

    # ------------------------------------------------------------- typed views

    def save_prediction(self, record: PredictionRecord) -> None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO predictions "
                    "(prediction_id, created_at, hypothesis_id, strategy_id, symbol, direction,"
                    " status, exit_reason, realized_pnl, direction_correct, confidence_score) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (prediction_id) DO UPDATE SET "
                    "status = EXCLUDED.status, exit_reason = EXCLUDED.exit_reason, "
                    "realized_pnl = EXCLUDED.realized_pnl, "
                    "direction_correct = EXCLUDED.direction_correct",
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
                        record.direction_correct,
                        record.confidence_score,
                    ),
                )
            self._conn.commit()

    def save_observation(self, report: ObservationReport) -> None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO observations "
                    "(observation_id, execution_id, actual_pnl, direction_correct, exit_reason,"
                    " created_at) VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (observation_id) DO NOTHING",
                    (
                        report.observation_id,
                        report.execution_id,
                        report.actual_pnl,
                        report.direction_correct,
                        report.exit_reason,
                        _utc_now_iso(),
                    ),
                )
            self._conn.commit()

    def save_postmortem(self, record: PostmortemRecord) -> None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO postmortems "
                    "(postmortem_id, execution_id, prediction_id, hypothesis_id, symbol,"
                    " payload_json, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (postmortem_id) DO UPDATE SET payload_json = EXCLUDED.payload_json",
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
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT execution_id, actual_pnl FROM observations "
                    "ORDER BY created_at ASC, observation_id ASC"
                )
                rows = cur.fetchall()
        return [(str(r[0]), float(r[1])) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._lock:
            result: dict[str, int] = {}
            with self._conn.cursor() as cur:
                for table in ("event_log", "predictions", "observations", "postmortems"):
                    cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 - fixed table list
                    result[table] = int(cur.fetchone()[0])
            return result

    def iter_event_payloads(self, kind: str) -> list[dict[str, Any]]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT payload_json FROM event_log WHERE kind = %s ORDER BY seq ASC",
                    (kind,),
                )
                rows = cur.fetchall()
        return [json.loads(r[0]) for r in rows]

    def read_events(self, after_seq: int = 0, limit: int = 1000) -> list[dict[str, Any]]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT seq, ts, kind, ref_id, payload_json FROM event_log "
                    "WHERE seq > %s ORDER BY seq ASC LIMIT %s",
                    (after_seq, limit),
                )
                rows = cur.fetchall()
        return [
            {
                "seq": int(r[0]),
                "ts": r[1],
                "kind": r[2],
                "ref_id": r[3],
                "payload": json.loads(r[4]),
            }
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
