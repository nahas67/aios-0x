"""The governance decision log, durable (vNext goal G050).

``ToolGuardian`` keeps its audit log in memory. That is the one thing an audit
log must not be. Every guarded decision — every allow, clamp, escalation, and
denial — vanishes on restart, leaving a system that was governed for six hours
and can prove nothing about any of it. This module makes the log survive the
process.

**Append-only is enforced by the schema, not by convention.** The v4 migration
installs triggers that abort ``UPDATE``, ``DELETE``, out-of-sequence ``INSERT``,
and out-of-chain ``INSERT``. This matters more here than anywhere else in the
schema: a Python guard that promises not to edit a row is a promise, and the
question "who could have edited the record of a denial?" has to be answered by
the database rather than by reading every call site.

**A hash chain does not detect truncation.** This is the property that makes
the seal necessary rather than decorative. The chain is a rolling digest over
the entries present, so an attacker who removes the last *k* decisions leaves a
shorter chain that recomputes perfectly — every remaining link still holds. Any
verification that stops at "the links are consistent" is satisfied by a log
that has been quietly cut short, and a log that has lost its tail is precisely
the one an operator would need to detect.

So the head is anchored externally: :class:`GovernanceSeal` is an HMAC over the
chain hash at a moment in time, signed with a key the log cannot reach. A
truncated log presents a head that no seal covers. The seal is what turns
"internally consistent" into "this is the log we had".

The read side is deliberately independent of the writer.
:meth:`DecisionLedger.audit` verifies a log it did not write, from a log it did
not hold in memory, which is the only way an answer obtained after a restart
means anything.
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

from core.migrations import apply_sqlite_migrations
from schemas.governance import GuardianDecision

__all__ = [
    "AppendOnlyViolation",
    "DecisionLedger",
    "GovernanceSeal",
    "LedgerAudit",
    "PostgresDecisionSink",
    "SqliteDecisionSink",
    "audit_log",
    "build_decision_ledger",
    "build_postgres_decision_sink",
    "build_sqlite_decision_sink",
    "ts_str",
]


class AppendOnlyViolation(RuntimeError):
    """A write to the governance log was refused as a tamper attempt."""


# ══════════════════════════════════════════════════════════════════════════
# Seals
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class GovernanceSeal:
    """An HMAC over the chain head, made at a moment in time.

    Signed rather than merely hashed, and that distinction is the whole
    mechanism. A hash written into the same table as the log can be rewritten
    by whoever rewrote the log. An HMAC keyed by something the log does not
    contain cannot, so a truncated tail has no seal covering its new head and
    the audit fails closed.

    The alternative — publishing the head somewhere else — fails in practice
    for the reason that matters: whoever can edit the log can usually also edit
    wherever else is convenient to edit.
    """

    seq: int
    chain_hash: str
    sealed_at: str
    signature: str

    @staticmethod
    def sign(seq: int, chain_hash: str, sealed_at: str, secret: bytes) -> GovernanceSeal:
        blob = f"{seq}|{chain_hash}|{sealed_at}".encode()
        return GovernanceSeal(
            seq=seq,
            chain_hash=chain_hash,
            sealed_at=sealed_at,
            signature=hmac.new(secret, blob, hashlib.sha256).hexdigest(),
        )

    def verify(self, secret: bytes) -> bool:
        """Whether this seal was made with the given key over its own fields.

        Recomputing from the *stored* fields rather than comparing digests is
        what makes a seal non-forgeable in place: changing ``seq`` or
        ``chain_hash`` invalidates the signature instead of becoming the new
        thing to verify.
        """
        blob = f"{self.seq}|{self.chain_hash}|{self.sealed_at}".encode()
        expected = hmac.new(secret, blob, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)


@dataclass(frozen=True)
class LedgerAudit:
    """The result of auditing a log the auditor did not write.

    Reported as named checks rather than one boolean, because a single
    ``False`` cannot distinguish "someone edited a decision" from "the process
    was restarted and this is a fresh prefix" — and those demand opposite
    responses.
    """

    entries: int
    chain_intact: bool
    head: str
    #: The newest seal that covers the current head, if any.
    sealed_through: int | None = None
    seal_signature_valid: bool = False
    #: Entries the log holds beyond its newest seal. Non-zero after a restart
    #: is normal; non-zero *combined with a lost seal* is truncation.
    unsealed_entries: int = 0

    @property
    def ok(self) -> bool:
        """Whether the log is fully accounted for.

        Requires the links to hold *and* a valid seal covering the head. A log
        with no seal at all is not ``ok``: nothing external vouches for it, so
        a truncation is undetectable. The honest reading of an unsealed log is
        "unverifiable", and this reports that rather than passing it.
        """
        return (
            self.chain_intact
            and self.seal_signature_valid
            and self.sealed_through is not None
            and self.unsealed_entries == 0
        )

    def describe(self) -> str:
        if not self.chain_intact:
            return (
                f"chain broken at {self.entries} entr(y/ies): a decision was edited, "
                "removed, or reordered"
            )
        if self.sealed_through is None:
            return (
                f"chain internally consistent over {self.entries} entr(y/ies) but carries "
                "no seal, so truncation cannot be detected. The log is unanchored, not clean."
            )
        if not self.seal_signature_valid:
            return (
                f"seal at entry {self.sealed_through} does not verify: it was forged or the "
                "key changed. Treat the log as compromised."
            )
        if self.unsealed_entries:
            return (
                f"chain intact and sealed through entry {self.sealed_through}, with "
                f"{self.unsealed_entries} entr(y/ies) made after the last seal. The tail is "
                "unanchored: a truncation within it would not be detected."
            )
        return (
            f"{self.entries} decision(s) verified; chain intact and sealed through entry "
            f"{self.sealed_through}."
        )


def audit_log(
    decisions: Sequence[GuardianDecision],
    seals: Sequence[GovernanceSeal] = (),
    secret: bytes | None = None,
) -> LedgerAudit:
    """Verify a log from the outside.

    Takes the entries rather than a guardian, because an audit that reads the
    writer's own memory is not an audit. Recomputes every link from genesis, so
    a log is judged on its own contents and not on the head the process
    currently believes in.
    """
    entries = list(decisions)
    previous = ""
    for index, decision in enumerate(entries):
        blob = "|".join(
            [
                previous,
                decision.disposition,
                decision.call_digest,
                decision.reasoning,
                str(index + 1),
            ]
        )
        if hashlib.sha256(blob.encode()).hexdigest() != decision.chain_hash:
            return LedgerAudit(entries=len(entries), chain_intact=False, head=previous)
        previous = decision.chain_hash

    head = previous
    if not seals:
        return LedgerAudit(entries=len(entries), chain_intact=True, head=head)

    # The seal must cover the head we actually hold. A seal for an earlier head
    # is the signature of a log that grew past its last checkpoint; a seal whose
    # chain_hash is not in the log at all is the signature of a rewritten one.
    reached: GovernanceSeal | None = None
    by_hash = {seal.chain_hash: seal for seal in seals}
    for decision in entries:
        if decision.chain_hash in by_hash:
            reached = by_hash[decision.chain_hash]

    if reached is None:
        if secret is None:
            return LedgerAudit(entries=len(entries), chain_intact=True, head=head)
        # Every seal exists but none lands on a chain hash we hold. If the
        # newest seal's seq exceeds the log length, the tail was cut.
        newest = max(seals, key=lambda s: s.seq)
        if newest.seq > len(entries):
            return LedgerAudit(
                entries=len(entries),
                chain_intact=True,
                head=head,
                sealed_through=None,
                seal_signature_valid=False,
            )
        return LedgerAudit(entries=len(entries), chain_intact=True, head=head)

    signature_valid = reached.verify(secret) if secret is not None else False
    return LedgerAudit(
        entries=len(entries),
        chain_intact=True,
        head=head,
        sealed_through=reached.seq,
        seal_signature_valid=signature_valid,
        unsealed_entries=len(entries) - reached.seq,
    )


# ══════════════════════════════════════════════════════════════════════════
# SQLite sink
# ══════════════════════════════════════════════════════════════════════════


_DECISION_COLUMNS = (
    "seq",
    "chain_hash",
    "previous_chain_hash",
    "disposition",
    "call_digest",
    "reasoning",
    "evaluator",
    "model_id",
    "decided_at",
    "payload",
)


class SqliteDecisionSink:
    """Durable, append-only governance log on SQLite.

    Uses the stdlib only. A governance ledger is the last component that should
    gain a third-party dependency: the surface area of a numerical library is
    irrelevant here, while a supply-chain compromise in the audit trail would be
    unrecoverable and undetectable by construction.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.RLock()
        apply_sqlite_migrations(connection)

    # ------------------------------------------------------------------ write

    def append(self, decision: GuardianDecision, previous_chain_hash: str) -> None:
        """Append one decision. Never mutates, never overwrites.

        The sequence is derived from the log rather than passed in, so a caller
        cannot open a gap by supplying its own number. Deriving it is also what
        lets the schema refuse out-of-order writes: the value here is always the
        next one, and the trigger fails any *other* value, which means a
        tampered insert is caught by the database instead of by a code path a
        reviewer has to notice.
        """
        payload = decision.model_dump_json()
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT seq, chain_hash FROM governance_decisions ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            expected_previous = "" if row is None else str(row["chain_hash"])
            if previous_chain_hash != expected_previous:
                raise AppendOnlyViolation(
                    f"append refused: previous_chain_hash {previous_chain_hash[:12] or '(genesis)'} "
                    f"does not match the stored head {expected_previous[:12] or '(genesis)'}. "
                    "The log has moved; a decision cannot be written onto a stale head."
                )
            seq = 1 if row is None else int(row["seq"]) + 1
            try:
                self._connection.execute(
                    "INSERT INTO governance_decisions ("
                    "seq, chain_hash, previous_chain_hash, disposition, call_digest, "
                    "reasoning, evaluator, model_id, decided_at, payload"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        seq,
                        decision.chain_hash,
                        previous_chain_hash,
                        str(decision.disposition),
                        decision.call_digest,
                        decision.reasoning,
                        str(decision.evaluator),
                        decision.model_id,
                        decision.decided_at,
                        payload,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                # The triggers fire as IntegrityError. Surfacing the database's
                # own message keeps the tamper class visible to whoever hits it.
                raise AppendOnlyViolation(
                    f"append refused by the ledger schema: {exc}"
                ) from exc

    def seal(self, secret: bytes) -> GovernanceSeal | None:
        """Anchor the current head. ``None`` when the log is empty.

        An empty log has no head to anchor, and inventing one — a seal over
        genesis — would produce a signed artifact attesting to nothing.
        """
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT seq, chain_hash FROM governance_decisions ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            seq = int(row["seq"])
            seal = GovernanceSeal.sign(seq, str(row["chain_hash"]), _now(), secret)
            self._connection.execute(
                "INSERT INTO governance_seals (seal_id, seq, chain_hash, sealed_at, signature) "
                "VALUES (?, ?, ?, ?, ?)",
                (seq, seal.seq, seal.chain_hash, seal.sealed_at, seal.signature),
            )
            return seal

    def seals(self) -> list[GovernanceSeal]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT seq, chain_hash, sealed_at, signature FROM governance_seals "
                "ORDER BY seal_id"
            ).fetchall()
        return [
            GovernanceSeal(
                seq=int(r["seq"]),
                chain_hash=str(r["chain_hash"]),
                sealed_at=ts_str(r["sealed_at"]),
                signature=str(r["signature"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------- read

    def read_all(self) -> list[GuardianDecision]:
        with self._lock:
            rows = self._connection.execute(
                f"SELECT {', '.join(_DECISION_COLUMNS)} FROM governance_decisions ORDER BY seq"
            ).fetchall()
        return [GuardianDecision.model_validate_json(str(r["payload"])) for r in rows]

    def head(self) -> str:
        with self._lock:
            row = self._connection.execute(
                "SELECT chain_hash FROM governance_decisions ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        return "" if row is None else str(row["chain_hash"])

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n FROM governance_decisions"
            ).fetchone()
        return 0 if row is None else int(row["n"])

    def audit(self, secret: bytes | None = None) -> LedgerAudit:
        """Verify the stored log from scratch, without the writer's help."""
        return audit_log(self.read_all(), self.seals(), secret)

    def close(self) -> None:
        self._connection.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def ts_str(value: object) -> str:
    """Render a stored timestamp back to the exact string that was signed.

    Every seal's HMAC is computed over ``f"{seq}|{chain_hash}|{sealed_at}"``
    using the ISO-8601 string produced by :func:`_now`. Reading the column back
    must therefore reproduce that same string, and it does not: SQLite stores
    TEXT and hands it back unchanged, while PostgreSQL stores TIMESTAMPTZ and
    hands back a ``datetime``. ``str(datetime)`` renders a space where
    ``isoformat()`` renders ``T``, so the recomputed HMAC covers different bytes
    and every Postgres seal fails its own verification -- which reads as "the
    log was tampered with" when nothing was tampered with.

    The fix belongs on the read, not on the writer. Re-signing in the dialect's
    own representation would make seals portable but forgeable-by-rewrite in a
    different way: the signature would no longer be a function of the canonical
    fields. Normalising the read keeps one canonical string on both tiers.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


# ══════════════════════════════════════════════════════════════════════════
# PostgreSQL sink
# ══════════════════════════════════════════════════════════════════════════


class PostgresDecisionSink:
    """Production PostgreSQL tier of the governance log.

    Identical behaviour to the SQLite tier: the same trigger-enforced
    append-only shape (v4 DDL, both dialects), the same chain head discipline,
    the same seal table. ``audit_log`` and ``GovernanceSeal`` are
    dialect-agnostic — they operate on models, not rows — which is what makes
    the mirror exact rather than approximate. The parity suite holds both
    tiers to the same assertions.

    Production PostgreSQL never mutates DDL on open — ``auto_migrate`` is
    opt-in for tests and bootstrap tooling.
    """

    def __init__(self, dsn: str, *, auto_migrate: bool = False) -> None:
        try:
            import psycopg  # noqa: PLC0415 - lazy so PG-less installs stay clean
        except ImportError as exc:
            raise ImportError(
                "PostgresDecisionSink requires psycopg >= 3. "
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

    def append(self, decision: GuardianDecision, previous_chain_hash: str) -> None:
        """Append one decision. Never mutates, never overwrites.

        Same contract as the SQLite tier: the sequence derives from the log,
        the store re-checks the head rather than trusting the caller, and a
        trigger violation surfaces as :class:`AppendOnlyViolation` carrying
        the database's own message.
        """
        payload = decision.model_dump_json()
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT seq, chain_hash FROM governance_decisions ORDER BY seq DESC LIMIT 1"
                )
                row = cur.fetchone()
            expected_previous = "" if row is None else str(row[1])
            if previous_chain_hash != expected_previous:
                raise AppendOnlyViolation(
                    f"append refused: previous_chain_hash {previous_chain_hash[:12] or '(genesis)'} "
                    f"does not match the stored head {expected_previous[:12] or '(genesis)'}. "
                    "The log has moved; a decision cannot be written onto a stale head."
                )
            seq = 1 if row is None else int(row[0]) + 1
            try:
                with self._conn.transaction():
                    with self._conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO governance_decisions ("
                            "seq, chain_hash, previous_chain_hash, disposition, call_digest, "
                            "reasoning, evaluator, model_id, decided_at, payload"
                            ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (
                                seq,
                                decision.chain_hash,
                                previous_chain_hash,
                                str(decision.disposition),
                                decision.call_digest,
                                decision.reasoning,
                                str(decision.evaluator),
                                decision.model_id,
                                decision.decided_at,
                                payload,
                            ),
                        )
            except self._psycopg.errors.Error as exc:
                # transaction() already rolled the failed insert back.
                raise AppendOnlyViolation(
                    f"append refused by the ledger schema: {exc}"
                ) from exc
            # Commit: transaction() brackets the statement but does not commit
            # it. Uncommitted, the decision was visible only to this connection
            # and lost when it closed -- on a log whose purpose is a durable
            # record of what was decided and why.
            self._conn.commit()

    def seal(self, secret: bytes) -> GovernanceSeal | None:
        """Anchor the current head. ``None`` when the log is empty."""
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT seq, chain_hash FROM governance_decisions ORDER BY seq DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row is None:
                    return None
                seq = int(row[0])
                seal = GovernanceSeal.sign(seq, str(row[1]), _now(), secret)
                with self._conn.transaction():
                    with self._conn.cursor() as cur2:
                        cur2.execute(
                            "INSERT INTO governance_seals (seal_id, seq, chain_hash, sealed_at, signature) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (seq, seal.seq, seal.chain_hash, seal.sealed_at, seal.signature),
                        )
                # Commit: the seal is the external anchor that makes truncation
                # of this log detectable afterwards. Uncommitted it vanished on
                # close, and a restarted log then reported itself unanchored --
                # the anchoring mechanism causing the doubt it exists to settle.
                self._conn.commit()
                return seal

    def seals(self) -> list[GovernanceSeal]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT seq, chain_hash, sealed_at, signature FROM governance_seals "
                "ORDER BY seal_id"
            )
            rows = cur.fetchall()
        return [
            GovernanceSeal(
                seq=int(r[0]),
                chain_hash=str(r[1]),
                sealed_at=ts_str(r[2]),
                signature=str(r[3]),
            )
            for r in rows
        ]

    def read_all(self) -> list[GuardianDecision]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_DECISION_COLUMNS)} FROM governance_decisions ORDER BY seq"
            )
            rows = cur.fetchall()
        return [GuardianDecision.model_validate_json(str(r[9])) for r in rows]

    def head(self) -> str:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT chain_hash FROM governance_decisions ORDER BY seq DESC LIMIT 1"
            )
            row = cur.fetchone()
        return "" if row is None else str(row[0])

    def count(self) -> int:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM governance_decisions")
            row = cur.fetchone()
        return 0 if row is None else int(row[0])

    def audit(self, secret: bytes | None = None) -> LedgerAudit:
        """Verify the stored log from scratch, without the writer's help."""
        return audit_log(self.read_all(), self.seals(), secret)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def build_postgres_decision_sink(dsn: str, *, auto_migrate: bool = False) -> PostgresDecisionSink:
    """Open a durable governance log on PostgreSQL. Migrations run only when asked."""
    return PostgresDecisionSink(dsn, auto_migrate=auto_migrate)


# ══════════════════════════════════════════════════════════════════════════
# Facade
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class DecisionLedger:
    """A durable log plus the key that can vouch for it.

    Bundled rather than passed as loose arguments because the two must not be
    separable. A sink without its key produces a log that is internally
    consistent and externally unanchored — the truncation case above — and that
    is a failure mode a caller will not notice by inspection, so the type makes
    the pairing the path of least resistance.

    This is the object a composition root holds. It does not judge calls; the
    guardian in ``kernel/`` does that and writes through here.
    """

    sink: SqliteDecisionSink | PostgresDecisionSink
    secret: bytes

    def seal(self) -> GovernanceSeal | None:
        """Anchor the current head. ``None`` on an empty log."""
        return self.sink.seal(self.secret)

    def audit(self) -> LedgerAudit:
        """Verify the stored log end to end, including truncation."""
        return audit_log(self.sink.read_all(), self.sink.seals(), self.secret)

    def decisions(self) -> list[GuardianDecision]:
        return self.sink.read_all()

    def denials(self) -> list[GuardianDecision]:
        """Every decision that was not allowed through, with its reason.

        The query an operator actually runs. Reading a denial list out of a
        table is fine; reading it out of memory is not, because the question
        "what did this system refuse, and why" is asked after the incident
        rather than during it.
        """
        return [d for d in self.sink.read_all() if d.disposition.value == "DENY"]

    def head(self) -> str:
        return self.sink.head()

    def close(self) -> None:
        self.sink.close()


def build_decision_ledger(path: str | Path, secret: bytes) -> DecisionLedger:
    """Open (or create) a durable, sealable governance log at ``path``."""
    if not secret:
        raise ValueError("a sealing secret is required; an unsealable audit is not an audit")
    return DecisionLedger(sink=build_sqlite_decision_sink(path), secret=secret)


def build_sqlite_decision_sink(path: str | Path) -> SqliteDecisionSink:
    """Open (or create) a durable governance log at ``path``."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target), check_same_thread=False, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return SqliteDecisionSink(connection)
