"""Cross-dialect parity for the claim ledger (goal G040).

An audit that passes on SQLite while production runs PostgreSQL is an audit
of the wrong system. Every behavioural test here runs against *both* tiers:
the PostgreSQL leg runs when ``AIOS_TEST_PG_DSN`` is set and skips otherwise,
per the repo's integration contract. The v6 DDL cross-checks need no database:
the migration texts are the artifact under test.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from core.claim_ledger import (
    Claim,
    ClaimClass,
    ClaimLedgerError,
    ClaimVerdict,
    ProvenanceTag,
    SourceArtifact,
    build_postgres_claim_ledger,
    build_sqlite_claim_ledger,
)
from core.migrations import MIGRATIONS, _statements

DSN = os.environ.get("AIOS_TEST_PG_DSN", "")


def _artifact(content: str = "close 67234.12 at 2024-05-01T00:00:00Z") -> SourceArtifact:
    return SourceArtifact.create(content, kind="feed-bar", source="test-feed")


def _claim(artifact: SourceArtifact, claim_id: str = "claim-1", **overrides) -> Claim:
    fields: dict[str, object] = {
        "claim_id": claim_id,
        "subject_id": "BTC/USD",
        "predicate": "close_price",
        "claim_object": 67234.12,
        "claim_class": ClaimClass.OBSERVED,
        "provenance": ProvenanceTag.EXTRACTED,
        "evidence_refs": ["feed-bar-1", "feed-bar-2"],
        "source_artifact_id": artifact.artifact_id,
        "source_hash": artifact.source_hash,
        "confidence": 0.8,
        "verdict": ClaimVerdict.SUFFICIENT,
    }
    fields.update(overrides)
    return Claim(**fields)  # type: ignore[arg-type]


@pytest.fixture(params=["sqlite"] + (["postgres"] if DSN else []))
def ledger(request, tmp_path: Path):
    """One claim ledger per tier. Same behaviour asserted on both."""
    if request.param == "sqlite":
        yield build_sqlite_claim_ledger(tmp_path / "claims.db")
    else:
        import psycopg

        with psycopg.connect(DSN, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE source_artifacts, claims")
        store = build_postgres_claim_ledger(DSN, auto_migrate=True)
        try:
            yield store
        finally:
            store.close()


# ══════════════════════════════════════════════════════════════════════════
# Behavioural parity
# ══════════════════════════════════════════════════════════════════════════


def test_artifact_round_trip_verifies_on_read(ledger) -> None:
    """Content-addressed means verified on read, on both tiers: the hash is
    recomputed from stored bytes, so tampering surfaces at read time."""
    artifact = _artifact()
    ledger.store_artifact(artifact)
    assert ledger.artifact(artifact.artifact_id).verify() is True


def test_claim_requires_a_stored_source(ledger) -> None:
    """A claim without a resolvable source is refused before anything is
    written — a rumour with formatting stays out on both tiers."""
    artifact = _artifact()
    with pytest.raises(ClaimLedgerError, match="unknown artifact"):
        ledger.record_claim(_claim(artifact))
    with pytest.raises(KeyError):
        ledger.get("claim-1")


def test_claim_round_trip_preserves_every_field(ledger) -> None:
    """The fields an audit reads — confidence, verdict, refs, hashes — must
    survive both tiers identically. A lossy tier is a lossy audit."""
    artifact = _artifact()
    ledger.store_artifact(artifact)
    recorded = ledger.record_claim(_claim(artifact))
    reread = ledger.get("claim-1")
    assert reread == recorded
    chain = ledger.verify_chain("claim-1")
    assert chain["hash_verified"] is True
    assert chain["evidence_count"] == 2
    assert chain["verdict"] == "SUFFICIENT"


def test_identical_rerecord_is_a_no_op(ledger) -> None:
    artifact = _artifact()
    ledger.store_artifact(artifact)
    first = ledger.record_claim(_claim(artifact))
    second = ledger.record_claim(_claim(artifact))
    assert second.claim_id == first.claim_id
    assert len(ledger.claims_for_subject("BTC/USD")) == 1


def test_divergent_rerecord_is_refused(ledger) -> None:
    artifact = _artifact()
    ledger.store_artifact(artifact)
    ledger.record_claim(_claim(artifact))
    with pytest.raises(ClaimLedgerError, match="already recorded"):
        ledger.record_claim(_claim(artifact, claim_object=1.0))


def test_supersession_inserts_and_preserves(ledger) -> None:
    artifact = _artifact()
    ledger.store_artifact(artifact)
    ledger.record_claim(_claim(artifact, claim_id="claim-1"))
    revision = _claim(artifact, claim_id="claim-2", supersedes="claim-1")
    ledger.supersede("claim-1", revision)
    assert [c.claim_id for c in ledger.history("claim-2")] == ["claim-1", "claim-2"]
    assert ledger.get("claim-1").claim_object == 67234.12


def test_supersession_must_name_what_it_replaces(ledger) -> None:
    """A revision that does not name its predecessor is a fork, not a
    correction — refused identically on both tiers."""
    artifact = _artifact()
    ledger.store_artifact(artifact)
    ledger.record_claim(_claim(artifact, claim_id="claim-1"))
    with pytest.raises(ClaimLedgerError, match="must set supersedes"):
        ledger.supersede("claim-1", _claim(artifact, claim_id="claim-2"))


def test_certainty_still_needs_two_sources(ledger) -> None:
    """The model-level rule holds regardless of tier: certainty from one
    source is refused at construction, before any tier is touched."""
    artifact = _artifact()
    ledger.store_artifact(artifact)
    with pytest.raises(ValueError, match="at least two independent"):
        _claim(artifact, confidence=1.0, evidence_refs=["only-one"])


# ══════════════════════════════════════════════════════════════════════════
# Hermetic: v6 DDL parity without a database
# ══════════════════════════════════════════════════════════════════════════


def _ddl_names(statements: list[str], kind: str) -> set[str]:
    pattern = re.compile(
        rf"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP\s+)?{kind}\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
        re.IGNORECASE,
    )
    return {
        match.group(1).lower()
        for statement in statements
        if (match := pattern.search(statement))
    }


def _columns(statements: list[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for statement in statements:
        match = re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*)\)",
            statement, re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue
        table, body = match.group(1).lower(), match.group(2)
        cols = set()
        for line in body.splitlines():
            token = line.strip().split()
            if token and token[0].upper() not in {
                "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT",
            }:
                cols.add(token[0].strip('", ').lower())
        found[table] = cols
    return found


def test_claim_ddl_matches_across_dialects() -> None:
    """Same tables, indexes, and columns under the same names. The claim
    ledger carries no triggers (append-only by construction: no UPDATE
    exists in either tier), so there is nothing else to compare."""
    v6 = next(m for m in MIGRATIONS if m.version == 6)
    sqlite_stmts = _statements(v6.sqlite)
    pg_stmts = _statements(v6.postgres)
    for kind in ("TABLE", "INDEX"):
        assert _ddl_names(sqlite_stmts, kind) == _ddl_names(pg_stmts, kind), (
            f"v6 {kind} mismatch"
        )
    sqlite_cols = _columns(sqlite_stmts)
    pg_cols = _columns(pg_stmts)
    assert set(sqlite_cols) == set(pg_cols)
    for table in sqlite_cols:
        assert sqlite_cols[table] == pg_cols[table], f"v6 column mismatch on {table}"


def test_neither_claim_tier_updates_in_place() -> None:
    """Structural backstop for the append-only guarantee: no UPDATE against
    either claim table in either tier's code. A future UPDATE would have to
    remove this test to land, which is the point."""
    import pathlib

    source = pathlib.Path("core/claim_ledger.py").read_text(encoding="utf-8")
    updates = [
        line.strip()
        for line in source.splitlines()
        if re.match(r"\s*['\"]UPDATE\s", line, re.IGNORECASE)
    ]
    assert updates == [], f"UPDATE statements found in the claim ledger: {updates}"
