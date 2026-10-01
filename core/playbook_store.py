"""Durable playbook policies (vNext goal G120).

The router's memory dies with the process; its policies must not. Playbooks
are immutable once registered — no transitions, so no event log: one row per
playbook version with its content hash, append-only triggers refusing UPDATE
and DELETE. Resume reloads every row and re-registers; certification is
re-asked live at selection time, so a playbook whose verdict was revoked
while the process was down loads but never selects.

The seal signs ``(count, set_hash)`` — the row count plus the digest of the
sorted content hashes — rather than a chain head, because there is no chain.
Truncation changes the count, substitution changes the set hash, and either
invalidates the seal. Same truncation argument as every sibling ledger, same
answer: a record over the entries present verifies perfectly over a
shortened one, so only the external signature exposes the cut.

Payloads are shape-agnostic strings. The router in ``kernel/`` validates on
read; this module stores and orders, keeping the dependency direction
one-way.
"""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.decision_sink import AppendOnlyViolation, ts_str
from core.migrations import apply_sqlite_migrations

__all__ = [
    "PlaybookLedger",
    "PlaybookSeal",
    "PlaybookSealAudit",
    "PostgresPlaybookStore",
    "SqlitePlaybookStore",
    "audit_playbook_log",
    "build_playbook_ledger",
    "build_postgres_playbook_store",
    "build_sqlite_playbook_store",
    "set_hash_of",
]


@dataclass(frozen=True)
class PlaybookSeal:
    """An HMAC over ``(count, set_hash)``, made at a moment in time.

    ``set_hash`` is the sha256 of the sorted content hashes: substitution of
    any row changes the set even when the count is preserved, which is the
    tamper a count-only seal would miss. Recomputed from stored fields on
    verify, so editing a seal in place invalidates it.
    """

    event_count: int
    set_hash: str
    sealed_at: str
    signature: str

    @staticmethod
    def sign(event_count: int, set_hash: str, sealed_at: str, secret: bytes) -> PlaybookSeal:
        blob = f"{event_count}|{set_hash}|{sealed_at}".encode()
        return PlaybookSeal(
            event_count=event_count,
            set_hash=set_hash,
            sealed_at=sealed_at,
            signature=hmac.new(secret, blob, hashlib.sha256).hexdigest(),
        )

    def verify(self, secret: bytes) -> bool:
        blob = f"{self.event_count}|{self.set_hash}|{self.sealed_at}".encode()
        expected = hmac.new(secret, blob, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)


def set_hash_of(hashes: list[str]) -> str:
    """Digest of the sorted content hashes. Order-independent: the set is
    what matters, and registration order must not affect the seal."""
    return hashlib.sha256("|".join(sorted(hashes)).encode()).hexdigest()


@dataclass(frozen=True)
class PlaybookSealAudit:
    """The result of auditing a playbook store the auditor did not write."""

    rows: int
    chain_intact: bool = True
    sealed_through: int | None = None
    seal_signature_valid: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return (
            self.chain_intact
            and not self.truncated
            and self.seal_signature_valid
            and self.sealed_through is not None
            and self.sealed_through == self.rows
        )

    def describe(self) -> str:
        if self.truncated:
            return (
                f"a seal covers {self.sealed_through} row(s) but the store holds "
                f"fewer: policies were removed, and with them the coverage"
            )
        if self.sealed_through is None:
            return (
                f"{self.rows} row(s) with no seal: truncation cannot be detected. "
                "The store is unanchored, not clean."
            )
        if not self.seal_signature_valid:
            return (
                f"seal at row {self.sealed_through} does not verify: forged or "
                "key changed. Treat the store as compromised."
            )
        if self.sealed_through != self.rows:
            return (
                f"sealed through row {self.sealed_through} with "
                f"{self.rows - (self.sealed_through or 0)} row(s) added after: "
                "the tail is unanchored"
            )
        return f"{self.rows} polic(ies|y) verified against their seal."


def audit_playbook_log(
    rows: list[tuple[str, str]],
    seals: list[PlaybookSeal] | None = None,
    secret: bytes | None = None,
) -> PlaybookSealAudit:
    """Verify a playbook store from the outside.

    ``rows`` are ``(playbook_ref, content_hash)`` pairs. PK uniqueness is the
    store's job (same id+version with different content is refused at write);
    the audit checks the set against the newest seal.
    """
    seals = list(seals or [])
    current = set_hash_of([content for _, content in rows])
    if not seals:
        return PlaybookSealAudit(rows=len(rows))
    newest = max(seals, key=lambda s: s.event_count)
    if newest.event_count > len(rows):
        return PlaybookSealAudit(
            rows=len(rows),
            sealed_through=newest.event_count,
            seal_signature_valid=False,
            truncated=True,
        )
    signature_valid = newest.verify(secret) if secret is not None else False
    if newest.event_count == len(rows) and signature_valid:
        # The seal must also cover THIS set, not just this size: a same-count
        # substitution keeps the count while changing the policies.
        if newest.set_hash != current:
            return PlaybookSealAudit(
                rows=len(rows),
                sealed_through=newest.event_count,
                seal_signature_valid=False,
            )
    return PlaybookSealAudit(
        rows=len(rows),
        sealed_through=newest.event_count,
        seal_signature_valid=signature_valid,
    )


class SqlitePlaybookStore:
    """Durable, append-only playbook policies on SQLite. Stdlib only."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.RLock()
        apply_sqlite_migrations(connection)

    def save(
        self,
        playbook_id: str,
        version: str,
        content_hash: str,
        payload: str,
        registered_at: str,
    ) -> bool:
        """Store one playbook version. Returns True when written, False when
        the identical row already exists. Same id+version with different
        content hits the primary key and is refused: a policy that changes
        under its version is a different policy wearing an old name."""
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT content_hash FROM playbooks WHERE playbook_id = ? AND version = ?",
                (playbook_id, version),
            ).fetchone()
            if existing is not None:
                if str(existing["content_hash"]) != content_hash:
                    raise AppendOnlyViolation(
                        f"playbook {playbook_id}:{version} already stored with a "
                        "different hash. Register a new version instead of "
                        "rewriting a certified policy."
                    )
                return False
            try:
                self._connection.execute(
                    "INSERT INTO playbooks (playbook_id, version, content_hash, "
                    "registered_at, payload) VALUES (?, ?, ?, ?, ?)",
                    (playbook_id, version, content_hash, registered_at, payload),
                )
            except sqlite3.IntegrityError as exc:
                raise AppendOnlyViolation(
                    f"playbook store refused the write: {exc}"
                ) from exc
            return True

    def read_all(self) -> list[tuple[str, str, str]]:
        """(ref, content_hash, payload) in registration order."""
        with self._lock:
            rows = self._connection.execute(
                "SELECT playbook_id, version, content_hash, payload FROM playbooks "
                "ORDER BY rowid"
            ).fetchall()
        return [
            (f"{r['playbook_id']}:{r['version']}", str(r["content_hash"]), str(r["payload"]))
            for r in rows
        ]

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS n FROM playbooks").fetchone()
        return 0 if row is None else int(row["n"])

    def seal(self, secret: bytes) -> PlaybookSeal | None:
        with self._lock, self._connection:
            rows = self.read_all()
            if not rows:
                return None
            digest = set_hash_of([content for _, content, _ in rows])
            seal = PlaybookSeal.sign(len(rows), digest, _now(), secret)
            # seal_id advances independently of the row count: resealing an
            # unchanged store must anchor again, not collide on the count.
            last = self._connection.execute(
                "SELECT COALESCE(MAX(seal_id), 0) AS m FROM playbook_seals"
            ).fetchone()
            self._connection.execute(
                "INSERT INTO playbook_seals (seal_id, event_count, set_hash, sealed_at, signature) "
                "VALUES (?, ?, ?, ?, ?)",
                (int(last["m"]) + 1, seal.event_count, seal.set_hash, seal.sealed_at, seal.signature),
            )
            return seal

    def seals(self) -> list[PlaybookSeal]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT event_count, set_hash, sealed_at, signature FROM playbook_seals "
                "ORDER BY seal_id"
            ).fetchall()
        return [
            PlaybookSeal(
                event_count=int(r["event_count"]),
                set_hash=str(r["set_hash"]),
                sealed_at=ts_str(r["sealed_at"]),
                signature=str(r["signature"]),
            )
            for r in rows
        ]

    def audit(self, secret: bytes | None = None) -> PlaybookSealAudit:
        return audit_playbook_log(
            [(ref, content) for ref, content, _ in self.read_all()],
            self.seals(),
            secret,
        )

    def close(self) -> None:
        self._connection.close()


class PostgresPlaybookStore:
    """Production PostgreSQL tier. Identical behaviour; the parity suite
    holds both tiers to the same assertions. Migrations run only when asked."""

    def __init__(self, dsn: str, *, auto_migrate: bool = False) -> None:
        try:
            import psycopg  # noqa: PLC0415 - lazy so PG-less installs stay clean
        except ImportError as exc:
            raise ImportError(
                "PostgresPlaybookStore requires psycopg >= 3. "
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

    def save(
        self,
        playbook_id: str,
        version: str,
        content_hash: str,
        payload: str,
        registered_at: str,
    ) -> bool:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT content_hash FROM playbooks WHERE playbook_id = %s AND version = %s",
                    (playbook_id, version),
                )
                existing = cur.fetchone()
                if existing is not None:
                    if str(existing[0]) != content_hash:
                        raise AppendOnlyViolation(
                            f"playbook {playbook_id}:{version} already stored with a "
                            "different hash. Register a new version instead of "
                            "rewriting a certified policy."
                        )
                    return False
                try:
                    with self._conn.transaction():
                        with self._conn.cursor() as cur2:
                            cur2.execute(
                                "INSERT INTO playbooks (playbook_id, version, content_hash, "
                                "registered_at, payload) VALUES (%s, %s, %s, %s, %s)",
                                (playbook_id, version, content_hash, registered_at, payload),
                            )
                except self._psycopg.errors.Error as exc:
                    raise AppendOnlyViolation(
                        f"playbook store refused the write: {exc}"
                    ) from exc
                return True

    def read_all(self) -> list[tuple[str, str, str]]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT playbook_id, version, content_hash, payload FROM playbooks "
                "ORDER BY registered_at, playbook_id, version"
            )
            rows = cur.fetchall()
        return [(f"{r[0]}:{r[1]}", str(r[2]), str(r[3])) for r in rows]

    def count(self) -> int:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM playbooks")
            row = cur.fetchone()
        return 0 if row is None else int(row[0])

    def seal(self, secret: bytes) -> PlaybookSeal | None:
        with self._lock:
            rows = self.read_all()
            if not rows:
                return None
            digest = set_hash_of([content for _, content, _ in rows])
            seal = PlaybookSeal.sign(len(rows), digest, _now(), secret)
            with self._conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(seal_id), 0) FROM playbook_seals")
                row = cur.fetchone()
                nxt = int(row[0]) + 1 if row is not None else 1
                with self._conn.transaction():
                    with self._conn.cursor() as cur2:
                        cur2.execute(
                            "INSERT INTO playbook_seals (seal_id, event_count, set_hash, sealed_at, signature) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (nxt, seal.event_count, seal.set_hash, seal.sealed_at, seal.signature),
                        )
            return seal

    def seals(self) -> list[PlaybookSeal]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT event_count, set_hash, sealed_at, signature FROM playbook_seals "
                "ORDER BY seal_id"
            )
            rows = cur.fetchall()
        return [
            PlaybookSeal(
                event_count=int(r[0]),
                set_hash=str(r[1]),
                sealed_at=ts_str(r[2]),
                signature=str(r[3]),
            )
            for r in rows
        ]

    def audit(self, secret: bytes | None = None) -> PlaybookSealAudit:
        return audit_playbook_log(
            [(ref, content) for ref, content, _ in self.read_all()],
            self.seals(),
            secret,
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def build_postgres_playbook_store(
    dsn: str, *, auto_migrate: bool = False
) -> PostgresPlaybookStore:
    """Open a durable playbook store on PostgreSQL. Migrations run only when asked."""
    return PostgresPlaybookStore(dsn, auto_migrate=auto_migrate)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def build_sqlite_playbook_store(path: str | Path) -> SqlitePlaybookStore:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target), check_same_thread=False, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return SqlitePlaybookStore(connection)


@dataclass(frozen=True)
class PlaybookLedger:
    """A durable playbook store plus the key that can vouch for it.

    Bundled because the two must not be separable: a store without its key
    is internally consistent and externally unanchored, and that failure mode
    is invisible by inspection.
    """

    sink: SqlitePlaybookStore | PostgresPlaybookStore
    secret: bytes

    def seal(self) -> PlaybookSeal | None:
        return self.sink.seal(self.secret)

    def audit(self) -> PlaybookSealAudit:
        return audit_playbook_log(
            [(ref, content) for ref, content, _ in self.sink.read_all()],
            self.sink.seals(),
            self.secret,
        )

    def close(self) -> None:
        self.sink.close()


def build_playbook_ledger(path: str | Path, secret: bytes) -> PlaybookLedger:
    """Open (or create) a durable, sealable playbook store at ``path``."""
    if not secret:
        raise ValueError("a sealing secret is required; an unsealable store is not a store")
    return PlaybookLedger(sink=build_sqlite_playbook_store(path), secret=secret)
