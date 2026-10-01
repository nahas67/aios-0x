"""Append-only claim ledger with content-addressed sources (vNext goal G040).

A research output that cannot name its source is not research, it is a rumour
with formatting. A citation that cannot be rechecked is not evidence, it is a
footnote. This module makes both executable: every claim resolves to a source
artifact whose sha256 verifies on read, and the log itself is append-only, so a
correction supersedes rather than rewrites.

Three distinctions carry the design:

claim_class (what kind of assertion is this?)
    OBSERVED (a market fact) is not INFERRED (a model output) is not REVISED
    (a correction). Collapsing them loses the ability to ask "which of our
    beliefs are facts and which are guesses", which is the question a
    verification pass exists to answer.

provenance (how was it extracted?)
    EXTRACTED (verbatim from the source) is not INFERRED (derived) is not
    AMBIGUOUS (uncertain). Borrowed from graphify, whose per-edge tag is the
    single most copyable idea in the 28-repo sweep.

verdict (what did verification conclude?)
    SUFFICIENT, PARTIAL, or WRONG, with at most eight evidence references. The
    bound is deliberate: a claim needing nine sources to stand is not standing.

Two properties are enforced by tests rather than assumed:

* a confidence of 1.0 requires at least two independent sources. Certainty
  from a single source is not certainty, it is trust, and the ledger refuses
  to record it as the former.
* supersession inserts. An UPDATE against the claims table is a defect, and
  ``tests/test_authority_chain.py`` greps for it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "Claim",
    "ClaimClass",
    "ClaimLedgerError",
    "ClaimVerdict",
    "PostgresClaimLedger",
    "ProvenanceTag",
    "SourceArtifact",
    "SqliteClaimLedger",
    "build_postgres_claim_ledger",
    "build_sqlite_claim_ledger",
]

#: Maximum evidence references per claim. A claim needing more sources than
#: this to stand is not standing; split it into smaller claims.
MAX_EVIDENCE_REFS = 8


class ClaimClass(StrEnum):
    """What kind of assertion a claim is."""

    OBSERVED = "OBSERVED"
    DOCUMENTED = "DOCUMENTED"
    STRUCTURAL = "STRUCTURAL"
    INFERRED = "INFERRED"
    REVISED = "REVISED"
    DISPUTED = "DISPUTED"


class ProvenanceTag(StrEnum):
    """How the claim was extracted from its source."""

    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


class ClaimVerdict(StrEnum):
    """What verification concluded about the claim."""

    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    WRONG = "WRONG"


class ClaimLedgerError(RuntimeError):
    """A claim-ledger write was refused."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class SourceArtifact(BaseModel):
    """Immutable content-addressed source: the thing a claim points at.

    The artifact_id is the sha256 of the content, so identity and integrity
    are the same property. Two sources with the same bytes are the same
    artifact, which is exactly the deduplication a ledger wants.
    """

    model_config = {"frozen": True}

    artifact_id: str = Field(..., min_length=64, max_length=64)
    kind: str = Field(..., min_length=1, description="run-log | filing | feed-bar | paper | quote ...")
    source: str = Field(..., min_length=1)
    retrieved_at: datetime = Field(default_factory=_utc_now)
    content: str = Field(..., description="The bytes the hash covers, stored as text")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        content: str,
        *,
        kind: str,
        source: str,
        retrieved_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SourceArtifact:
        digest = _sha256_hex(content.encode())
        return cls(
            artifact_id=digest,
            kind=kind,
            source=source,
            retrieved_at=retrieved_at or _utc_now(),
            content=content,
            metadata=metadata or {},
        )

    @property
    def source_hash(self) -> str:
        """Alias: the artifact id IS the content hash."""
        return self.artifact_id

    def verify(self) -> bool:
        """Recompute the hash and compare. False means tampered or corrupted."""
        return _sha256_hex(self.content.encode()) == self.artifact_id


class Claim(BaseModel):
    """One assertion, resolved to a source, graded by verification."""

    model_config = {"frozen": True}

    claim_id: str = Field(..., min_length=1)
    subject_id: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    claim_object: Any = Field(..., description="The asserted value")
    claim_class: ClaimClass
    provenance: ProvenanceTag
    evidence_refs: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_REFS)
    source_artifact_id: str = Field(..., min_length=64, max_length=64)
    source_hash: str = Field(..., min_length=64, max_length=64)
    source_time: datetime | None = Field(
        default=None, description="When the source event happened in the world"
    )
    available_at: datetime | None = Field(
        default=None, description="When the source became knowable; the PIT join key",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verdict: ClaimVerdict = ClaimVerdict.PARTIAL
    contraindications: list[str] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=_utc_now,
        description="IMMUTABLE: when the claim was recorded, never touched by decay",
    )
    updated_at: datetime = Field(
        default_factory=_utc_now, description="Content revisions only; decay must not touch this",
    )
    supersedes: str | None = Field(
        default=None, description="claim_id this revision replaces; the old row stays",
    )
    contradicted_by: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_certainty_requires_two_sources(self) -> Claim:
        if self.confidence >= 1.0 and len(set(self.evidence_refs)) < 2:
            raise ValueError(
                "confidence 1.0 requires at least two independent evidence references. "
                "Certainty from a single source is trust, not measurement."
            )
        return self

    @model_validator(mode="after")
    def _check_hash_matches_artifact(self) -> Claim:
        if self.source_hash != self.source_artifact_id:
            raise ValueError(
                "source_hash must equal source_artifact_id: the claim resolves to its "
                "artifact by content hash, and a mismatch means the reference is broken."
            )
        return self

    def chain(self) -> dict[str, Any]:
        """The recheckable reference: claim -> artifact -> hash."""
        return {
            "claim_id": self.claim_id,
            "source_artifact_id": self.source_artifact_id,
            "source_hash": self.source_hash,
            "evidence_refs": list(self.evidence_refs),
            "supersedes": self.supersedes,
        }


_CLAIM_COLUMNS = (
    "claim_id",
    "subject_id",
    "predicate",
    "object_json",
    "claim_class",
    "provenance",
    "evidence_refs_json",
    "source_artifact_id",
    "source_hash",
    "source_time",
    "available_at",
    "confidence",
    "verdict",
    "contraindications_json",
    "created_at",
    "updated_at",
    "supersedes",
    "contradicted_by_json",
)

_ARTIFACT_COLUMNS = (
    "artifact_id",
    "kind",
    "source",
    "retrieved_at",
    "content",
    "metadata_json",
)


def _claim_params(claim: Claim) -> tuple[Any, ...]:
    return (
        claim.claim_id,
        claim.subject_id,
        claim.predicate,
        json.dumps(claim.claim_object, sort_keys=True, default=str),
        str(claim.claim_class),
        str(claim.provenance),
        json.dumps(claim.evidence_refs),
        claim.source_artifact_id,
        claim.source_hash,
        claim.source_time.isoformat() if claim.source_time else None,
        claim.available_at.isoformat() if claim.available_at else None,
        claim.confidence,
        str(claim.verdict),
        json.dumps(claim.contraindications),
        claim.created_at.isoformat(),
        claim.updated_at.isoformat(),
        claim.supersedes,
        json.dumps(claim.contradicted_by),
    )


def _row_to_claim(row: dict[str, Any]) -> Claim:
    return Claim(
        claim_id=str(row["claim_id"]),
        subject_id=str(row["subject_id"]),
        predicate=str(row["predicate"]),
        claim_object=json.loads(str(row["object_json"])),
        claim_class=ClaimClass(str(row["claim_class"])),
        provenance=ProvenanceTag(str(row["provenance"])),
        evidence_refs=json.loads(str(row["evidence_refs_json"] or "[]")),
        source_artifact_id=str(row["source_artifact_id"]),
        source_hash=str(row["source_hash"]),
        source_time=_parse_dt(row["source_time"]),
        available_at=_parse_dt(row["available_at"]),
        confidence=float(row["confidence"]),
        verdict=ClaimVerdict(str(row["verdict"])),
        contraindications=json.loads(str(row["contraindications_json"] or "[]")),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        updated_at=_parse_dt(row["updated_at"]) or _utc_now(),
        supersedes=row["supersedes"],
        contradicted_by=json.loads(str(row["contradicted_by_json"] or "[]")),
    )


def _same_assertion(first: Claim, second: Claim) -> bool:
    """Whether two claims assert the same thing.

    Record metadata is excluded: created_at, updated_at, and available_at say
    when each assertion was recorded and when it became knowable *to the
    recorder*, not what was asserted. This is the same idempotency-key
    semantic the OMS uses — re-submitting the same key returns the existing
    order instead of creating a second one — applied to judgments: a replayed
    pipeline re-asserts the same claims, and the ledger must not manufacture
    twins for them.
    """
    excluded = {"created_at", "updated_at", "available_at"}
    left = first.model_dump(mode="json", exclude=excluded)
    right = second.model_dump(mode="json", exclude=excluded)
    return left == right


def _row_to_artifact(row: dict[str, Any]) -> SourceArtifact:
    artifact = SourceArtifact(
        artifact_id=str(row["artifact_id"]),
        kind=str(row["kind"]),
        source=str(row["source"]),
        retrieved_at=_parse_dt(row["retrieved_at"]) or _utc_now(),
        content=str(row["content"]),
        metadata=json.loads(str(row["metadata_json"] or "{}")),
    )
    if not artifact.verify():
        raise ClaimLedgerError(
            f"source artifact {artifact.artifact_id[:12]} failed hash verification on read. "
            "The content does not match its address: tampered or corrupted."
        )
    return artifact


_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_artifacts (
    artifact_id   TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    source        TEXT NOT NULL,
    retrieved_at  TEXT NOT NULL,
    content       TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id               TEXT PRIMARY KEY,
    subject_id             TEXT NOT NULL,
    predicate              TEXT NOT NULL,
    object_json            TEXT NOT NULL,
    claim_class            TEXT NOT NULL,
    provenance             TEXT NOT NULL,
    evidence_refs_json     TEXT NOT NULL DEFAULT '[]',
    source_artifact_id     TEXT NOT NULL,
    source_hash            TEXT NOT NULL,
    source_time            TEXT,
    available_at           TEXT,
    confidence             REAL NOT NULL,
    verdict                TEXT NOT NULL,
    contraindications_json TEXT NOT NULL DEFAULT '[]',
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    supersedes             TEXT,
    contradicted_by_json   TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (source_artifact_id) REFERENCES source_artifacts(artifact_id)
);
CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_id, predicate);
CREATE INDEX IF NOT EXISTS idx_claims_artifact ON claims(source_artifact_id);
CREATE INDEX IF NOT EXISTS idx_claims_supersedes ON claims(supersedes) WHERE supersedes IS NOT NULL;
"""


class SqliteClaimLedger:
    """SQLite tier of the claim ledger: append-only claims, hashed sources.

    Supersession is an insert, never an update. Recording a revision writes a
    new row whose ``supersedes`` points at the old one; the old row is
    untouched. A mutation in place would be indistinguishable from a cover-up,
    so the write path contains no UPDATE against the claims table by
    construction rather than by convention.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 10000")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = FULL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------ sources

    def store_artifact(self, artifact: SourceArtifact) -> SourceArtifact:
        """Persist a source. Same content twice is a no-op, not a duplicate."""
        if not artifact.verify():
            raise ClaimLedgerError("refusing to store a source artifact that fails its own hash")
        with self._lock:
            self._conn.execute(
                f"INSERT OR IGNORE INTO source_artifacts ({', '.join(_ARTIFACT_COLUMNS)})"
                f" VALUES ({', '.join('?' for _ in _ARTIFACT_COLUMNS)})",
                (
                    artifact.artifact_id,
                    artifact.kind,
                    artifact.source,
                    artifact.retrieved_at.isoformat(),
                    artifact.content,
                    json.dumps(artifact.metadata, sort_keys=True, default=str),
                ),
            )
            self._conn.commit()
        return artifact

    def artifact(self, artifact_id: str) -> SourceArtifact:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM source_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown source artifact {artifact_id[:12]}")
        return _row_to_artifact(dict(row))

    # ------------------------------------------------------------------- claims

    def record_claim(self, claim: Claim) -> Claim:
        """Append one claim. The referenced artifact must already be stored."""
        with self._lock:
            stored = self._conn.execute(
                "SELECT artifact_id, content FROM source_artifacts WHERE artifact_id = ?",
                (claim.source_artifact_id,),
            ).fetchone()
            if stored is None:
                raise ClaimLedgerError(
                    f"claim {claim.claim_id} references unknown artifact "
                    f"{claim.source_artifact_id[:12]}. Store the source first: a claim "
                    "without a resolvable source is a rumour with formatting."
                )
            if _sha256_hex(str(stored["content"]).encode()) != claim.source_hash:
                raise ClaimLedgerError(
                    f"claim {claim.claim_id} source_hash does not match stored content. "
                    "The artifact changed under its address."
                )
            try:
                with self._conn:
                    self._conn.execute(
                        f"INSERT INTO claims ({', '.join(_CLAIM_COLUMNS)})"
                        f" VALUES ({', '.join('?' for _ in _CLAIM_COLUMNS)})",
                        _claim_params(claim),
                    )
            except sqlite3.IntegrityError as exc:
                # Re-recording the identical claim is a no-op, not an update:
                # pipelines replay, and a replay must not manufacture twins.
                # Same id with different content is refused — a claim that
                # changed under its name is either a revision (which gets a
                # new id plus supersedes) or a fork. Record timestamps are
                # excluded from the comparison: they say when each assertion
                # was recorded, not what was asserted.
                stored = self._conn.execute(
                    "SELECT * FROM claims WHERE claim_id = ?", (claim.claim_id,)
                ).fetchone()
                if stored is not None and _same_assertion(_row_to_claim(dict(stored)), claim):
                    # Return what the ledger holds, not what was re-supplied:
                    # the stored row is the assertion of record.
                    return _row_to_claim(dict(stored))
                raise ClaimLedgerError(f"claim {claim.claim_id} already recorded: {exc}") from exc
        return claim

    def supersede(self, old_claim_id: str, revision: Claim) -> Claim:
        """Record a revision. The old row stays; the new row points at it."""
        if revision.supersedes != old_claim_id:
            raise ClaimLedgerError(
                f"revision {revision.claim_id} must set supersedes={old_claim_id!r}. "
                "A revision that does not name what it replaces is a fork, not a correction."
            )
        with self._lock:
            old = self._conn.execute(
                "SELECT claim_id FROM claims WHERE claim_id = ?", (old_claim_id,)
            ).fetchone()
            if old is None:
                raise KeyError(f"cannot supersede unknown claim {old_claim_id!r}")
        return self.record_claim(revision)

    def get(self, claim_id: str) -> Claim:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown claim {claim_id!r}")
        return _row_to_claim(dict(row))

    def verify_chain(self, claim_id: str) -> dict[str, Any]:
        """Recheck the full reference: claim -> artifact -> hash -> evidence bound.

        Returns the chain on success and raises on any break. This is what an
        auditor runs instead of trusting the verdict field.
        """
        claim = self.get(claim_id)
        artifact = self.artifact(claim.source_artifact_id)
        return {
            "claim_id": claim.claim_id,
            "artifact_id": artifact.artifact_id,
            "hash_verified": artifact.verify(),
            "evidence_refs": list(claim.evidence_refs),
            "evidence_count": len(claim.evidence_refs),
            "supersedes": claim.supersedes,
            "verdict": str(claim.verdict),
        }

    def claims_for_subject(self, subject_id: str) -> list[Claim]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM claims WHERE subject_id = ? ORDER BY created_at",
                (subject_id,),
            ).fetchall()
        return [_row_to_claim(dict(row)) for row in rows]

    def history(self, claim_id: str) -> list[Claim]:
        """Every revision of a claim, oldest first, by following supersedes."""
        chain: list[Claim] = []
        current: str | None = claim_id
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            claim = self.get(current)
            chain.append(claim)
            # Walk backwards: find the claim this one supersedes.
            current = claim.supersedes
        chain.reverse()
        return chain


def build_sqlite_claim_ledger(db_path: str | Path) -> SqliteClaimLedger:
    """Construct the SQLite tier. Named for symmetry with the other stores."""
    return SqliteClaimLedger(db_path)


class PostgresClaimLedger:
    """Production PostgreSQL tier of the claim ledger.

    Method-for-method mirror of the SQLite tier: content-addressed artifacts
    verified on read, claims appended only against stored artifacts,
    supersession by insert. The row mappers already accept native
    datetime/Decimal objects, which is what makes the mirror exact. The
    parity suite holds both tiers to the same assertions; like the SQLite
    tier, this class contains no UPDATE against either table, by
    construction rather than by convention.

    Production PostgreSQL never mutates DDL on open — ``auto_migrate`` is
    opt-in for tests and bootstrap tooling.
    """

    def __init__(self, dsn: str, *, auto_migrate: bool = False) -> None:
        try:
            import psycopg  # noqa: PLC0415 - lazy so PG-less installs stay clean
        except ImportError as exc:
            raise ImportError(
                "PostgresClaimLedger requires psycopg >= 3. "
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

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ sources

    def store_artifact(self, artifact: SourceArtifact) -> SourceArtifact:
        """Persist a source. Same content twice is a no-op, not a duplicate."""
        if not artifact.verify():
            raise ClaimLedgerError("refusing to store a source artifact that fails its own hash")
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO source_artifacts ({', '.join(_ARTIFACT_COLUMNS)})"
                f" VALUES ({', '.join('%s' for _ in _ARTIFACT_COLUMNS)})"
                " ON CONFLICT (artifact_id) DO NOTHING",
                (
                    artifact.artifact_id,
                    artifact.kind,
                    artifact.source,
                    artifact.retrieved_at.isoformat(),
                    artifact.content,
                    json.dumps(artifact.metadata, sort_keys=True, default=str),
                ),
            )
            self._conn.commit()
        return artifact

    def artifact(self, artifact_id: str) -> SourceArtifact:
        with self._lock, self._conn.cursor(row_factory=self._psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT * FROM source_artifacts WHERE artifact_id = %s", (artifact_id,)
            )
            row = cur.fetchone()
        if row is None:
            raise KeyError(f"unknown source artifact {artifact_id[:12]}")
        return _row_to_artifact(dict(row))

    # ------------------------------------------------------------------- claims

    def record_claim(self, claim: Claim) -> Claim:
        """Append one claim. The referenced artifact must already be stored."""
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "SELECT artifact_id, content FROM source_artifacts WHERE artifact_id = %s",
                (claim.source_artifact_id,),
            )
            stored = cur.fetchone()
            if stored is None:
                raise ClaimLedgerError(
                    f"claim {claim.claim_id} references unknown artifact "
                    f"{claim.source_artifact_id[:12]}. Store the source first: a claim "
                    "without a resolvable source is a rumour with formatting."
                )
            if _sha256_hex(str(stored[1]).encode()) != claim.source_hash:
                raise ClaimLedgerError(
                    f"claim {claim.claim_id} source_hash does not match stored content. "
                    "The artifact changed under its address."
                )
            try:
                with self._conn.transaction():
                    with self._conn.cursor() as cur2:
                        cur2.execute(
                            f"INSERT INTO claims ({', '.join(_CLAIM_COLUMNS)})"
                            f" VALUES ({', '.join('%s' for _ in _CLAIM_COLUMNS)})",
                            _claim_params(claim),
                        )
            except self._psycopg.errors.UniqueViolation as exc:
                # dict_row, because _row_to_claim expects a mapping. A plain
                # cursor yields a positional tuple, and dict(tuple) raises
                # "element #0 has length 7; 2 is required" -- so the idempotent
                # re-record path raised a TypeError-shaped ValueError instead of
                # recognising the identical claim it was written to absorb.
                #
                # No rollback here. The `transaction()` block above has already
                # rolled back the failed INSERT when the exception escaped it.
                # Calling self._conn.rollback() as well rolled back the *outer*
                # transaction too, which is wider than the failed statement: it
                # discarded the first, already-successful insert as well. An
                # idempotent re-record therefore returned the right claim and
                # then deleted it from the ledger. Verified by counting rows on
                # both sides of the call.
                with self._conn.cursor(row_factory=self._psycopg.rows.dict_row) as cur3:
                    cur3.execute(
                        "SELECT * FROM claims WHERE claim_id = %s", (claim.claim_id,)
                    )
                    row = cur3.fetchone()
                if row is not None and _same_assertion(
                    _row_to_claim(dict(row)), claim
                ):
                    return _row_to_claim(dict(row))
                raise ClaimLedgerError(
                    f"claim {claim.claim_id} already recorded: {exc}"
                ) from exc
        return claim

    def supersede(self, old_claim_id: str, revision: Claim) -> Claim:
        """Record a revision. The old row stays; the new row points at it."""
        if revision.supersedes != old_claim_id:
            raise ClaimLedgerError(
                f"revision {revision.claim_id} must set supersedes={old_claim_id!r}. "
                "A revision that does not name what it replaces is a fork, not a correction."
            )
        with self._lock, self._conn.cursor() as cur:
            cur.execute("SELECT claim_id FROM claims WHERE claim_id = %s", (old_claim_id,))
            if cur.fetchone() is None:
                raise KeyError(f"cannot supersede unknown claim {old_claim_id!r}")
        return self.record_claim(revision)

    def get(self, claim_id: str) -> Claim:
        with self._lock, self._conn.cursor(row_factory=self._psycopg.rows.dict_row) as cur:
            cur.execute("SELECT * FROM claims WHERE claim_id = %s", (claim_id,))
            row = cur.fetchone()
        if row is None:
            raise KeyError(f"unknown claim {claim_id!r}")
        return _row_to_claim(dict(row))

    def verify_chain(self, claim_id: str) -> dict[str, Any]:
        """Recheck the full reference: claim -> artifact -> hash -> evidence bound."""
        claim = self.get(claim_id)
        artifact = self.artifact(claim.source_artifact_id)
        return {
            "claim_id": claim.claim_id,
            "artifact_id": artifact.artifact_id,
            "hash_verified": artifact.verify(),
            "evidence_refs": list(claim.evidence_refs),
            "evidence_count": len(claim.evidence_refs),
            "supersedes": claim.supersedes,
            "verdict": str(claim.verdict),
        }

    def claims_for_subject(self, subject_id: str) -> list[Claim]:
        with self._lock, self._conn.cursor(row_factory=self._psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT * FROM claims WHERE subject_id = %s ORDER BY created_at",
                (subject_id,),
            )
            rows = cur.fetchall()
        return [_row_to_claim(dict(row)) for row in rows]

    def history(self, claim_id: str) -> list[Claim]:
        """Every revision of a claim, oldest first, by following supersedes."""
        chain: list[Claim] = []
        current: str | None = claim_id
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            claim = self.get(current)
            chain.append(claim)
            current = claim.supersedes
        chain.reverse()
        return chain


def build_postgres_claim_ledger(dsn: str, *, auto_migrate: bool = False) -> PostgresClaimLedger:
    """Construct the PostgreSQL tier. Migrations run only when asked."""
    return PostgresClaimLedger(dsn, auto_migrate=auto_migrate)
