"""The experiment ledger, durable (vNext goal G070).

``ExperimentRegistry`` keeps every run — including every failure and its
reason — in memory. That is the one thing a ledger must not do. A research
programme that cannot say what it tried last quarter will try it again next
quarter, and a programme that cannot count its trials cannot defend any win
rate it claims. This module makes the ledger survive the process.

Same enforcement shape as :mod:`core.decision_sink`, adapted to a different
write pattern. Governance decisions are immutable events with a global chain;
experiments are stateful rows (CREATED → RUNNING → COMPLETED/FAILED), so this
ledger stores one event per transition carrying the full run snapshot, and
current state is the latest event per experiment. Two consequences follow.

First, there is no global chain hash — ordering only matters *within* an
experiment. Each event carries ``supersedes``, the seq of its experiment's
previous event (0 at creation), and the schema refuses an insert that does not
link to its experiment's head. A forged event rewriting a FAILED run as
COMPLETED cannot link to the head without *becoming* the head, and as the head
it is visible rather than hidden: the rewrite is an event, not an edit.

Second, the seal signs ``(max_seq, event_count)`` rather than a chain head.
The truncation argument is identical to the governance ledger's: a record over
the entries present verifies perfectly over a shortened log, so only an HMAC
with a key the log cannot reach turns "internally consistent" into "this is
the log we had". For experiments the specific prize of a cut tail is
manufacturing a track record — 10,000 failures disappear and the one lucky
result remains. The seal is what makes the denominator auditable.

The payloads are shape-agnostic strings. This module stores and orders; the
registry in ``kernel/`` validates and interprets. That keeps the dependency
direction one-way — ``core/`` never imports ``kernel/`` — and it means the
sink cannot corrupt what it cannot parse.
"""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.decision_sink import AppendOnlyViolation, ts_str
from core.migrations import apply_sqlite_migrations

__all__ = [
    "ExperimentEvent",
    "ExperimentLedger",
    "ExperimentLedgerAudit",
    "ExperimentSeal",
    "PostgresExperimentSink",
    "SqliteExperimentSink",
    "audit_experiment_log",
    "build_experiment_ledger",
    "build_postgres_experiment_sink",
    "build_sqlite_experiment_sink",
]


# ══════════════════════════════════════════════════════════════════════════
# Events and seals
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ExperimentEvent:
    """One transition of one experiment, with the full snapshot after it.

    ``supersedes`` is the seq of this experiment's previous event, 0 when this
    event creates it. The payload is the run's serialised form — opaque here,
    validated by the registry on read.
    """

    seq: int
    experiment_id: str
    event_type: str
    supersedes: int
    recorded_at: str
    payload: str


@dataclass(frozen=True)
class ExperimentSeal:
    """An HMAC over ``(event_count, max_seq)``, made at a moment in time.

    Same discipline as the governance seal: recomputed from the stored fields
    on verify, so editing a seal in place invalidates it instead of becoming
    the new thing to check. Signs the count *and* the head because either
    alone is forgeable by truncation — a log cut to an earlier prefix has a
    self-consistent (count, head) pair that only an external signature exposes.
    """

    event_count: int
    max_seq: int
    sealed_at: str
    signature: str

    @staticmethod
    def sign(event_count: int, max_seq: int, sealed_at: str, secret: bytes) -> ExperimentSeal:
        blob = f"{event_count}|{max_seq}|{sealed_at}".encode()
        return ExperimentSeal(
            event_count=event_count,
            max_seq=max_seq,
            sealed_at=sealed_at,
            signature=hmac.new(secret, blob, hashlib.sha256).hexdigest(),
        )

    def verify(self, secret: bytes) -> bool:
        blob = f"{self.event_count}|{self.max_seq}|{self.sealed_at}".encode()
        expected = hmac.new(secret, blob, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)


@dataclass(frozen=True)
class ExperimentLedgerAudit:
    """The result of auditing an experiment log the auditor did not write."""

    events: int
    max_seq: int
    chain_intact: bool
    sealed_through: int | None = None
    seal_signature_valid: bool = False
    unsealed_events: int = 0
    truncated: bool = False

    @property
    def ok(self) -> bool:
        """Fully accounted for: linked, sealed to the head, signature valid.

        A log with no seal is not ``ok`` — nothing external vouches for it, so
        a truncation is undetectable. The honest reading of an unsealed log is
        "unverifiable", reported rather than passed.
        """
        return (
            self.chain_intact
            and not self.truncated
            and self.seal_signature_valid
            and self.sealed_through is not None
            and self.unsealed_events == 0
        )

    def describe(self) -> str:
        if not self.chain_intact:
            return (
                f"event linkage broken at {self.events} event(s): an event was "
                "inserted without linking to its experiment's head"
            )
        if self.truncated:
            return (
                f"a seal covers {self.sealed_through} event(s) but the log holds "
                f"fewer: the tail was cut, and with it the trials nobody wants "
                "counted"
            )
        if self.sealed_through is None:
            return (
                f"events link cleanly over {self.events} entr(y/ies) but the log "
                "carries no seal, so truncation cannot be detected. The log is "
                "unanchored, not clean."
            )
        if not self.seal_signature_valid:
            return (
                f"seal at event {self.sealed_through} does not verify: it was forged "
                "or the key changed. Treat the log as compromised."
            )
        if self.unsealed_events:
            return (
                f"events link cleanly and are sealed through event {self.sealed_through}, "
                f"with {self.unsealed_events} event(s) recorded after the last seal. "
                "The tail is unanchored: a truncation within it would not be detected."
            )
        return (
            f"{self.events} event(s) verified; linkage intact and sealed through "
            f"event {self.sealed_through}."
        )


def audit_experiment_log(
    events: Sequence[ExperimentEvent],
    seals: Sequence[ExperimentSeal] = (),
    secret: bytes | None = None,
) -> ExperimentLedgerAudit:
    """Verify an experiment log from the outside.

    Takes the entries rather than a sink, because an audit that reads the
    writer's own memory is not an audit. Checks global contiguity (1..N, since
    a gap is a removed event the triggers should have refused) and
    per-experiment linkage (each event supersedes its experiment's head).
    """
    ordered = sorted(events, key=lambda e: e.seq)
    heads: dict[str, int] = {}
    intact = True
    for index, event in enumerate(ordered, start=1):
        if event.seq != index:
            intact = False
            break
        expected = heads.get(event.experiment_id, 0)
        if event.supersedes != expected:
            intact = False
            break
        heads[event.experiment_id] = event.seq
    max_seq = ordered[-1].seq if ordered else 0

    if not intact:
        return ExperimentLedgerAudit(events=len(ordered), max_seq=max_seq, chain_intact=False)
    if not seals:
        return ExperimentLedgerAudit(events=len(ordered), max_seq=max_seq, chain_intact=True)

    # The newest seal is the claim about where the log ended. A seal ahead of
    # the stored log is the signature of a cut tail; a seal behind it is a
    # checkpoint the log has grown past.
    newest = max(seals, key=lambda s: (s.max_seq, s.event_count))
    if newest.max_seq > max_seq or newest.event_count > len(ordered):
        return ExperimentLedgerAudit(
            events=len(ordered),
            max_seq=max_seq,
            chain_intact=True,
            sealed_through=newest.max_seq,
            seal_signature_valid=False,
            truncated=True,
        )
    signature_valid = newest.verify(secret) if secret is not None else False
    return ExperimentLedgerAudit(
        events=len(ordered),
        max_seq=max_seq,
        chain_intact=True,
        sealed_through=newest.max_seq,
        seal_signature_valid=signature_valid,
        unsealed_events=len(ordered) - newest.event_count,
    )


# ══════════════════════════════════════════════════════════════════════════
# SQLite sink
# ══════════════════════════════════════════════════════════════════════════


_EVENT_COLUMNS = (
    "seq",
    "experiment_id",
    "event_type",
    "supersedes",
    "recorded_at",
    "payload",
)


class SqliteExperimentSink:
    """Durable, append-only experiment log on SQLite. Stdlib only.

    The same reasoning as the governance ledger applies with more force here:
    a tamper that must be defeated by every call site being correct succeeds
    the first time one is not, and the failures this log holds are exactly the
    rows someone under deadline would prefer not to exist.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.RLock()
        apply_sqlite_migrations(connection)

    # ------------------------------------------------------------------ write

    def append(
        self, experiment_id: str, event_type: str, payload: str, recorded_at: str
    ) -> ExperimentEvent:
        """Append one transition event carrying the run's full snapshot.

        The sequence and the predecessor link are derived from the log rather
        than passed in, so a caller cannot open a gap or fork an experiment's
        history by supplying its own numbers. The schema re-checks both, so a
        tampered insert is caught by the database instead of by a code path a
        reviewer has to notice.
        """
        if not experiment_id:
            raise AppendOnlyViolation("append refused: experiment_id must not be empty")
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT seq FROM experiment_events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            seq = 1 if row is None else int(row["seq"]) + 1
            head = self._connection.execute(
                "SELECT seq FROM experiment_events WHERE experiment_id = ? "
                "ORDER BY seq DESC LIMIT 1",
                (experiment_id,),
            ).fetchone()
            supersedes = 0 if head is None else int(head["seq"])
            try:
                self._connection.execute(
                    "INSERT INTO experiment_events (seq, experiment_id, event_type, "
                    "supersedes, recorded_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
                    (seq, experiment_id, event_type, supersedes, recorded_at, payload),
                )
            except sqlite3.IntegrityError as exc:
                raise AppendOnlyViolation(
                    f"append refused by the ledger schema: {exc}"
                ) from exc
        return ExperimentEvent(
            seq=seq,
            experiment_id=experiment_id,
            event_type=event_type,
            supersedes=supersedes,
            recorded_at=recorded_at,
            payload=payload,
        )

    def seal(self, secret: bytes) -> ExperimentSeal | None:
        """Anchor the current (count, head). ``None`` on an empty log."""
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n, COALESCE(MAX(seq), 0) AS head FROM experiment_events"
            ).fetchone()
            count = int(row["n"])
            if count == 0:
                return None
            head = int(row["head"])
            seal = ExperimentSeal.sign(count, head, _now(), secret)
            self._connection.execute(
                "INSERT INTO experiment_seals (seal_id, event_count, max_seq, sealed_at, signature) "
                "VALUES (?, ?, ?, ?, ?)",
                (head, seal.event_count, seal.max_seq, seal.sealed_at, seal.signature),
            )
            return seal

    def seals(self) -> list[ExperimentSeal]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT event_count, max_seq, sealed_at, signature FROM experiment_seals "
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

    # ------------------------------------------------------------------- read

    def read_events(self) -> list[ExperimentEvent]:
        with self._lock:
            rows = self._connection.execute(
                f"SELECT {', '.join(_EVENT_COLUMNS)} FROM experiment_events ORDER BY seq"
            ).fetchall()
        return [
            ExperimentEvent(
                seq=int(r["seq"]),
                experiment_id=str(r["experiment_id"]),
                event_type=str(r["event_type"]),
                supersedes=int(r["supersedes"]),
                recorded_at=ts_str(r["recorded_at"]),
                payload=str(r["payload"]),
            )
            for r in rows
        ]

    def read_snapshots(self) -> dict[str, str]:
        """Latest payload per experiment, in first-seen order.

        Current state is the latest event per experiment. First-seen order
        rather than alphabetical, so a resume replays creation order and
        parent links resolve — a child created before its parent's snapshot
        was read would dangle.
        """
        snapshots: dict[str, str] = {}
        for event in self.read_events():
            snapshots[event.experiment_id] = event.payload
        return snapshots

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n FROM experiment_events"
            ).fetchone()
        return 0 if row is None else int(row["n"])

    def audit(self, secret: bytes | None = None) -> ExperimentLedgerAudit:
        """Verify the stored log from scratch, without the writer's help."""
        return audit_experiment_log(self.read_events(), self.seals(), secret)

    def close(self) -> None:
        self._connection.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ══════════════════════════════════════════════════════════════════════════
# PostgreSQL sink
# ══════════════════════════════════════════════════════════════════════════


class PostgresExperimentSink:
    """Production PostgreSQL tier of the experiment log.

    Identical behaviour to the SQLite tier: one event per transition, the
    sequence and the predecessor link derived from the log, the schema
    re-checking both (v5 DDL, both dialects). ``audit_experiment_log`` and
    ``ExperimentSeal`` are dialect-agnostic, which is what makes the mirror
    exact. The parity suite holds both tiers to the same assertions.

    Production PostgreSQL never mutates DDL on open — ``auto_migrate`` is
    opt-in for tests and bootstrap tooling.
    """

    def __init__(self, dsn: str, *, auto_migrate: bool = False) -> None:
        try:
            import psycopg  # noqa: PLC0415 - lazy so PG-less installs stay clean
        except ImportError as exc:
            raise ImportError(
                "PostgresExperimentSink requires psycopg >= 3. "
                "Install with: pip install 'psycopg[binary]'"
            ) from exc
        self._psycopg = psycopg
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn)
        self._conn.autocommit = False
        if auto_migrate:
            from core.migrations import apply_postgres_migrations

            apply_postgres_migrations(self._conn)
            self._conn.commit()

    def append(
        self, experiment_id: str, event_type: str, payload: str, recorded_at: str
    ) -> ExperimentEvent:
        """Append one transition event. Sequence and predecessor link derive
        from the log; the schema re-checks both."""
        if not experiment_id:
            raise AppendOnlyViolation("append refused: experiment_id must not be empty")
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute("SELECT seq FROM experiment_events ORDER BY seq DESC LIMIT 1")
                row = cur.fetchone()
                seq = 1 if row is None else int(row[0]) + 1
                cur.execute(
                    "SELECT seq FROM experiment_events WHERE experiment_id = %s "
                    "ORDER BY seq DESC LIMIT 1",
                    (experiment_id,),
                )
                head = cur.fetchone()
                supersedes = 0 if head is None else int(head[0])
                try:
                    with self._conn.transaction():
                        with self._conn.cursor() as cur2:
                            cur2.execute(
                                "INSERT INTO experiment_events (seq, experiment_id, event_type, "
                                "supersedes, recorded_at, payload) VALUES (%s, %s, %s, %s, %s, %s)",
                                (seq, experiment_id, event_type, supersedes, recorded_at, payload),
                            )
                except self._psycopg.errors.Error as exc:
                    raise AppendOnlyViolation(
                        f"append refused by the ledger schema: {exc}"
                    ) from exc
        return ExperimentEvent(
            seq=seq,
            experiment_id=experiment_id,
            event_type=event_type,
            supersedes=supersedes,
            recorded_at=recorded_at,
            payload=payload,
        )

    def seal(self, secret: bytes) -> ExperimentSeal | None:
        """Anchor the current (count, head). ``None`` on an empty log."""
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n, COALESCE(MAX(seq), 0) AS head FROM experiment_events"
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
                            "INSERT INTO experiment_seals (seal_id, event_count, max_seq, sealed_at, signature) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (head, seal.event_count, seal.max_seq, seal.sealed_at, seal.signature),
                        )
                return seal

    def seals(self) -> list[ExperimentSeal]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT event_count, max_seq, sealed_at, signature FROM experiment_seals "
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
                f"SELECT {', '.join(_EVENT_COLUMNS)} FROM experiment_events ORDER BY seq"
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
        """Latest payload per experiment, in first-seen order."""
        snapshots: dict[str, str] = {}
        for event in self.read_events():
            snapshots[event.experiment_id] = event.payload
        return snapshots

    def count(self) -> int:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM experiment_events")
            row = cur.fetchone()
        return 0 if row is None else int(row[0])

    def audit(self, secret: bytes | None = None) -> ExperimentLedgerAudit:
        """Verify the stored log from scratch, without the writer's help."""
        return audit_experiment_log(self.read_events(), self.seals(), secret)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def build_postgres_experiment_sink(
    dsn: str, *, auto_migrate: bool = False
) -> PostgresExperimentSink:
    """Open a durable experiment log on PostgreSQL. Migrations run only when asked."""
    return PostgresExperimentSink(dsn, auto_migrate=auto_migrate)


def build_sqlite_experiment_sink(path: str | Path) -> SqliteExperimentSink:
    """Open (or create) a durable experiment log at ``path``."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target), check_same_thread=False, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return SqliteExperimentSink(connection)


# ══════════════════════════════════════════════════════════════════════════
# Facade
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ExperimentLedger:
    """A durable experiment log plus the key that can vouch for it.

    Bundled because the two must not be separable: a sink without its key
    produces a log that is internally consistent and externally unanchored,
    and that is a failure mode a caller will not notice by inspection.
    """

    sink: SqliteExperimentSink | PostgresExperimentSink
    secret: bytes

    def seal(self) -> ExperimentSeal | None:
        """Anchor the current (count, head). ``None`` on an empty log."""
        return self.sink.seal(self.secret)

    def audit(self) -> ExperimentLedgerAudit:
        """Verify the stored log end to end, including truncation."""
        return audit_experiment_log(
            self.sink.read_events(), self.sink.seals(), self.secret
        )

    def snapshots(self) -> dict[str, str]:
        return self.sink.read_snapshots()

    def close(self) -> None:
        self.sink.close()


def build_experiment_ledger(path: str | Path, secret: bytes) -> ExperimentLedger:
    """Open (or create) a durable, sealable experiment log at ``path``."""
    if not secret:
        raise ValueError("a sealing secret is required; an unsealable ledger is not a ledger")
    return ExperimentLedger(sink=build_sqlite_experiment_sink(path), secret=secret)
