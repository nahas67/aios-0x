"""Durable dataset-version records (vNext goal G030).

``DatasetRegistry`` keeps every version in memory: the exact data a backtest
ran on, pinned by content hash, gone on restart. A version that dies with the
process makes its backtest unreproducible months later — nobody re-registers
a dataset daily, so the loss surfaces as archaeology rather than as an error.

Same event-log shape as the experiment ledger (migration v7): one event per
lifecycle transition (REGISTERED / VALIDATED / ACTIVATED) carrying the full
version snapshot, current state as the latest event per dataset key,
per-key ``supersedes`` linkage refused by name on mismatch, and an HMAC seal
over (count, head) catching the truncation linkage cannot see. The seal and
audit machinery is shared with :mod:`core.experiment_sink` rather than
duplicated: the event shape is identical, only the table names differ, and
two implementations of one audit would be two places for it to be wrong.
Payloads are shape-agnostic strings; the registry validates on read, keeping
the dependency direction one-way.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.decision_sink import AppendOnlyViolation, ts_str
from core.experiment_sink import (
    ExperimentEvent,
    ExperimentLedgerAudit,
    ExperimentSeal,
    audit_experiment_log,
)
from core.migrations import apply_postgres_migrations, apply_sqlite_migrations

__all__ = [
    "DatasetVersionLedger",
    "PostgresDatasetVersionSink",
    "SqliteDatasetVersionSink",
    "build_dataset_version_ledger",
    "build_postgres_dataset_version_sink",
    "build_sqlite_dataset_version_sink",
]

_EVENT_COLUMNS = (
    "seq",
    "dataset_key",
    "event_type",
    "supersedes",
    "recorded_at",
    "payload",
)


def _to_event(row: dict[str, Any]) -> ExperimentEvent:
    """View a dataset event row through the shared event shape.

    The audit operates on linkage, not table names: mapping
    ``dataset_key`` onto ``experiment_id`` is honest because the linkage
    discipline is identical — each event supersedes its key's head.
    """
    return ExperimentEvent(
        seq=int(row["seq"]),
        experiment_id=str(row["dataset_key"]),
        event_type=str(row["event_type"]),
        supersedes=int(row["supersedes"]),
        recorded_at=ts_str(row["recorded_at"]),
        payload=str(row["payload"]),
    )


class SqliteDatasetVersionSink:
    """Durable, append-only dataset-version log on SQLite. Stdlib only."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.RLock()
        apply_sqlite_migrations(connection)

    def append(
        self, dataset_key: str, event_type: str, payload: str, recorded_at: str
    ) -> ExperimentEvent:
        """Append one lifecycle event carrying the version's full snapshot.

        Sequence and predecessor link derive from the log; the schema
        re-checks both. A caller cannot open a gap or fork a version's
        history by supplying its own numbers.
        """
        if not dataset_key:
            raise AppendOnlyViolation("append refused: dataset_key must not be empty")
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT seq FROM dataset_version_events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            seq = 1 if row is None else int(row["seq"]) + 1
            head = self._connection.execute(
                "SELECT seq FROM dataset_version_events WHERE dataset_key = ? "
                "ORDER BY seq DESC LIMIT 1",
                (dataset_key,),
            ).fetchone()
            supersedes = 0 if head is None else int(head["seq"])
            try:
                self._connection.execute(
                    "INSERT INTO dataset_version_events (seq, dataset_key, event_type, "
                    "supersedes, recorded_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
                    (seq, dataset_key, event_type, supersedes, recorded_at, payload),
                )
            except sqlite3.IntegrityError as exc:
                raise AppendOnlyViolation(
                    f"append refused by the ledger schema: {exc}"
                ) from exc
        return ExperimentEvent(
            seq=seq,
            experiment_id=dataset_key,
            event_type=event_type,
            supersedes=supersedes,
            recorded_at=recorded_at,
            payload=payload,
        )

    def seal(self, secret: bytes) -> ExperimentSeal | None:
        """Anchor the current (count, head). ``None`` on an empty log."""
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n, COALESCE(MAX(seq), 0) AS head FROM dataset_version_events"
            ).fetchone()
            count = int(row["n"])
            if count == 0:
                return None
            head = int(row["head"])
            seal = ExperimentSeal.sign(count, head, _now(), secret)
            self._connection.execute(
                "INSERT INTO dataset_version_seals (seal_id, event_count, max_seq, sealed_at, signature) "
                "VALUES (?, ?, ?, ?, ?)",
                (head, seal.event_count, seal.max_seq, seal.sealed_at, seal.signature),
            )
            return seal

    def seals(self) -> list[ExperimentSeal]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT event_count, max_seq, sealed_at, signature FROM dataset_version_seals "
                "ORDER BY seal_id"
            ).fetchall()
        return [
            ExperimentSeal(
                event_count=int(r["event_count"]),
                max_seq=int(r["max_seq"]),
                sealed_at=ts_str(r["sealed_at"]),
                signature=str(r["signature"]),
            )
            for r in rows
        ]

    def read_events(self) -> list[ExperimentEvent]:
        with self._lock:
            rows = self._connection.execute(
                f"SELECT {', '.join(_EVENT_COLUMNS)} FROM dataset_version_events ORDER BY seq"
            ).fetchall()
        return [_to_event(dict(r)) for r in rows]

    def read_snapshots(self) -> dict[str, str]:
        """Latest payload per dataset key, in first-seen order."""
        snapshots: dict[str, str] = {}
        for event in self.read_events():
            snapshots[event.experiment_id] = event.payload
        return snapshots

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n FROM dataset_version_events"
            ).fetchone()
        return 0 if row is None else int(row["n"])

    def audit(self, secret: bytes | None = None) -> ExperimentLedgerAudit:
        """Verify the stored log from scratch, without the writer's help."""
        return audit_experiment_log(self.read_events(), self.seals(), secret)

    def close(self) -> None:
        self._connection.close()


class PostgresDatasetVersionSink:
    """Production PostgreSQL tier. Identical behaviour; the parity suite
    holds both tiers to the same assertions. Migrations run only when asked."""

    def __init__(self, dsn: str, *, auto_migrate: bool = False) -> None:
        try:
            import psycopg  # noqa: PLC0415 - lazy so PG-less installs stay clean
        except ImportError as exc:
            raise ImportError(
                "PostgresDatasetVersionSink requires psycopg >= 3. "
                "Install with: pip install 'psycopg[binary]'"
            ) from exc
        self._psycopg = psycopg
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn)
        self._conn.autocommit = False
        if auto_migrate:
            apply_postgres_migrations(self._conn)
            self._conn.commit()

    def append(
        self, dataset_key: str, event_type: str, payload: str, recorded_at: str
    ) -> ExperimentEvent:
        if not dataset_key:
            raise AppendOnlyViolation("append refused: dataset_key must not be empty")
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT seq FROM dataset_version_events ORDER BY seq DESC LIMIT 1")
                row = cur.fetchone()
                seq = 1 if row is None else int(row[0]) + 1
                cur.execute(
                    "SELECT seq FROM dataset_version_events WHERE dataset_key = %s "
                    "ORDER BY seq DESC LIMIT 1",
                    (dataset_key,),
                )
                head = cur.fetchone()
                supersedes = 0 if head is None else int(head[0])
                try:
                    with self._conn.transaction():
                        with self._conn.cursor() as cur2:
                            cur2.execute(
                                "INSERT INTO dataset_version_events (seq, dataset_key, event_type, "
                                "supersedes, recorded_at, payload) VALUES (%s, %s, %s, %s, %s, %s)",
                                (seq, dataset_key, event_type, supersedes, recorded_at, payload),
                            )
                except self._psycopg.errors.Error as exc:
                    raise AppendOnlyViolation(
                        f"append refused by the ledger schema: {exc}"
                    ) from exc
        return ExperimentEvent(
            seq=seq,
            experiment_id=dataset_key,
            event_type=event_type,
            supersedes=supersedes,
            recorded_at=recorded_at,
            payload=payload,
        )

    def seal(self, secret: bytes) -> ExperimentSeal | None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n, COALESCE(MAX(seq), 0) AS head FROM dataset_version_events"
                )
                row = cur.fetchone()
                if row is None:  # COUNT()/MAX() always yield a row; absence is a defect
                    raise RuntimeError("expected exactly one row from the seal query")
                count = int(row[0])
                if count == 0:
                    return None
                head = int(row[1])
                seal = ExperimentSeal.sign(count, head, _now(), secret)
                with self._conn.transaction():
                    with self._conn.cursor() as cur2:
                        cur2.execute(
                            "INSERT INTO dataset_version_seals (seal_id, event_count, max_seq, sealed_at, signature) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (head, seal.event_count, seal.max_seq, seal.sealed_at, seal.signature),
                        )
                return seal

    def seals(self) -> list[ExperimentSeal]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT event_count, max_seq, sealed_at, signature FROM dataset_version_seals "
                "ORDER BY seal_id"
            )
            rows = cur.fetchall()
        return [
            ExperimentSeal(
                event_count=int(r[0]),
                max_seq=int(r[1]),
                sealed_at=ts_str(r[2]),
                signature=str(r[3]),
            )
            for r in rows
        ]

    def read_events(self) -> list[ExperimentEvent]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_EVENT_COLUMNS)} FROM dataset_version_events ORDER BY seq"
            )
            rows = cur.fetchall()
        return [
            ExperimentEvent(
                seq=int(r[0]),
                experiment_id=str(r[1]),
                event_type=str(r[2]),
                supersedes=int(r[3]),
                recorded_at=ts_str(r[4]),
                payload=str(r[5]),
            )
            for r in rows
        ]

    def read_snapshots(self) -> dict[str, str]:
        snapshots: dict[str, str] = {}
        for event in self.read_events():
            snapshots[event.experiment_id] = event.payload
        return snapshots

    def count(self) -> int:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM dataset_version_events")
            row = cur.fetchone()
        return 0 if row is None else int(row[0])

    def audit(self, secret: bytes | None = None) -> ExperimentLedgerAudit:
        return audit_experiment_log(self.read_events(), self.seals(), secret)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def build_sqlite_dataset_version_sink(path: str | Path) -> SqliteDatasetVersionSink:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target), check_same_thread=False, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return SqliteDatasetVersionSink(connection)


def build_postgres_dataset_version_sink(
    dsn: str, *, auto_migrate: bool = False
) -> PostgresDatasetVersionSink:
    """Open a durable dataset-version log on PostgreSQL. Migrations run only when asked."""
    return PostgresDatasetVersionSink(dsn, auto_migrate=auto_migrate)


@dataclass(frozen=True)
class DatasetVersionLedger:
    """A durable dataset-version log plus the key that can vouch for it."""

    sink: SqliteDatasetVersionSink | PostgresDatasetVersionSink
    secret: bytes

    def seal(self) -> ExperimentSeal | None:
        return self.sink.seal(self.secret)

    def audit(self) -> ExperimentLedgerAudit:
        return audit_experiment_log(
            self.sink.read_events(), self.sink.seals(), self.secret
        )

    def snapshots(self) -> dict[str, str]:
        return self.sink.read_snapshots()

    def close(self) -> None:
        self.sink.close()


def build_dataset_version_ledger(path: str | Path, secret: bytes) -> DatasetVersionLedger:
    """Open (or create) a durable, sealable dataset-version log at ``path``."""
    if not secret:
        raise ValueError("a sealing secret is required; an unsealable ledger is not a ledger")
    return DatasetVersionLedger(sink=build_sqlite_dataset_version_sink(path), secret=secret)
