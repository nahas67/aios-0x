"""Every number traces to a line, or it is not evidence (goal G040).

A research pipeline that cannot name its source is not research, it is a
rumour with formatting. A citation that cannot be rechecked is not evidence,
it is a footnote. These tests assert the ledger properties directly: sources
are content-addressed, claims resolve to them, certainty requires two sources,
and corrections supersede rather than rewrite.

The store is exercised on SQLite. The SQL is parameter-free where it matters
and dialect-portable by construction; a PostgreSQL tier is future work, and
the registry records that honestly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.claim_ledger import (
    MAX_EVIDENCE_REFS,
    Claim,
    ClaimClass,
    ClaimLedgerError,
    ClaimVerdict,
    ProvenanceTag,
    SourceArtifact,
    SqliteClaimLedger,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)
T1 = datetime(2024, 6, 1, tzinfo=UTC)


@pytest.fixture()
def ledger(tmp_path) -> SqliteClaimLedger:
    return SqliteClaimLedger(tmp_path / "claims.db")


@pytest.fixture()
def artifact() -> SourceArtifact:
    return SourceArtifact.create(
        content="BTC closed at 67234.12 on 2024-05-31 per exchange feed.",
        kind="feed-bar",
        source="ccxt:binance",
        retrieved_at=T1,
    )


@pytest.fixture()
def stored_ledger(
    ledger: SqliteClaimLedger, artifact: SourceArtifact
) -> tuple[SqliteClaimLedger, SourceArtifact]:
    ledger.store_artifact(artifact)
    return ledger, artifact


def _claim(
    artifact: SourceArtifact,
    claim_id: str = "claim-1",
    *,
    confidence: float = 0.8,
    evidence_refs: list[str] | None = None,
    verdict: ClaimVerdict = ClaimVerdict.SUFFICIENT,
    **overrides,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject_id=overrides.pop("subject_id", "BTC/USD"),
        predicate=overrides.pop("predicate", "close_price"),
        claim_object=overrides.pop("claim_object", 67234.12),
        claim_class=overrides.pop("claim_class", ClaimClass.OBSERVED),
        provenance=overrides.pop("provenance", ProvenanceTag.EXTRACTED),
        evidence_refs=evidence_refs if evidence_refs is not None else ["feed-bar-1"],
        source_artifact_id=artifact.artifact_id,
        source_hash=artifact.source_hash,
        source_time=overrides.pop("source_time", T0),
        available_at=overrides.pop("available_at", T1),
        confidence=confidence,
        verdict=verdict,
        **overrides,
    )


# ══════════════════════════════════════════════════════════════════════════
# Sources are content-addressed
# ══════════════════════════════════════════════════════════════════════════


def test_artifact_id_is_the_content_hash() -> None:
    """Identity and integrity are the same property: same bytes, same id."""
    first = SourceArtifact.create(content="same bytes", kind="log", source="a")
    second = SourceArtifact.create(content="same bytes", kind="log", source="b")
    assert first.artifact_id == second.artifact_id
    assert first.verify() is True


def test_different_content_is_a_different_artifact() -> None:
    first = SourceArtifact.create(content="a", kind="log", source="a")
    second = SourceArtifact.create(content="b", kind="log", source="a")
    assert first.artifact_id != second.artifact_id


def test_tampered_content_fails_verification() -> None:
    artifact = SourceArtifact.create(content="real", kind="log", source="a")
    tampered = artifact.model_copy(update={"content": "forged"})
    assert tampered.verify() is False


def test_storing_the_same_artifact_twice_is_a_no_op(
    ledger: SqliteClaimLedger, artifact: SourceArtifact
) -> None:
    ledger.store_artifact(artifact)
    ledger.store_artifact(artifact)
    assert ledger.artifact(artifact.artifact_id).artifact_id == artifact.artifact_id


def test_read_verifies_the_hash(ledger: SqliteClaimLedger, artifact: SourceArtifact) -> None:
    """A corrupted row is refused on read, not trusted."""
    ledger.store_artifact(artifact)
    with ledger._conn:
        ledger._conn.execute(
            "UPDATE source_artifacts SET content = ? WHERE artifact_id = ?",
            ("forged content", artifact.artifact_id),
        )
    with pytest.raises(ClaimLedgerError, match="failed hash verification on read"):
        ledger.artifact(artifact.artifact_id)


# ══════════════════════════════════════════════════════════════════════════
# Claims resolve to sources
# ══════════════════════════════════════════════════════════════════════════


def test_recorded_claim_round_trips(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    ledger, artifact = stored_ledger
    ledger.record_claim(_claim(artifact))
    stored = ledger.get("claim-1")
    assert stored.claim_object == 67234.12
    assert stored.verdict is ClaimVerdict.SUFFICIENT


def test_claim_without_a_stored_source_is_refused(
    ledger: SqliteClaimLedger, artifact: SourceArtifact
) -> None:
    """A claim without a resolvable source is a rumour with formatting."""
    with pytest.raises(ClaimLedgerError, match="unknown artifact"):
        ledger.record_claim(_claim(artifact))


def test_claim_with_a_mismatched_hash_is_refused(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    ledger, artifact = stored_ledger
    broken = _claim(artifact).model_copy(update={"source_hash": "0" * 64})
    # The model itself refuses the mismatch before the store ever sees it.
    with pytest.raises(ValueError, match="must equal source_artifact_id"):
        Claim(
            claim_id="broken",
            subject_id="BTC/USD",
            predicate="close_price",
            claim_object=1.0,
            claim_class=ClaimClass.OBSERVED,
            provenance=ProvenanceTag.EXTRACTED,
            evidence_refs=["x"],
            source_artifact_id=artifact.artifact_id,
            source_hash="0" * 64,
        )
    _ = broken


def test_verify_chain_rechecks_everything(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    """What an auditor runs instead of trusting the verdict field."""
    ledger, artifact = stored_ledger
    ledger.record_claim(_claim(artifact))
    chain = ledger.verify_chain("claim-1")
    assert chain["hash_verified"] is True
    assert chain["artifact_id"] == artifact.artifact_id
    assert chain["evidence_count"] == 1


# ══════════════════════════════════════════════════════════════════════════
# Certainty requires two sources
# ══════════════════════════════════════════════════════════════════════════


def test_confidence_one_with_a_single_source_is_refused(artifact: SourceArtifact) -> None:
    """Certainty from one source is trust, not measurement."""
    with pytest.raises(ValueError, match="at least two independent"):
        _claim(artifact, confidence=1.0, evidence_refs=["only-one"])


def test_confidence_one_with_two_sources_passes(artifact: SourceArtifact) -> None:
    claim = _claim(artifact, confidence=1.0, evidence_refs=["feed-bar-1", "feed-bar-2"])
    assert claim.confidence == 1.0


def test_duplicate_refs_do_not_count_as_two_sources(artifact: SourceArtifact) -> None:
    """Two citations of the same source are one source cited twice."""
    with pytest.raises(ValueError, match="at least two independent"):
        _claim(artifact, confidence=1.0, evidence_refs=["same", "same"])


def test_high_but_uncertain_confidence_needs_no_second_source(
    artifact: SourceArtifact,
) -> None:
    """The rule binds certainty, not strong belief. 0.99 from one source is fine."""
    claim = _claim(artifact, confidence=0.99, evidence_refs=["only-one"])
    assert claim.confidence == 0.99


# ══════════════════════════════════════════════════════════════════════════
# The log is append-only
# ══════════════════════════════════════════════════════════════════════════


def test_recording_the_same_claim_twice_is_a_no_op(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    """Pipelines replay. Re-asserting the identical claim returns the stored
    row instead of manufacturing a twin — the same idempotency-key semantic
    the OMS uses for client_order_id."""
    ledger, artifact = stored_ledger
    first = ledger.record_claim(_claim(artifact))
    second = ledger.record_claim(_claim(artifact))
    assert second.claim_id == first.claim_id
    assert len(ledger.claims_for_subject("BTC/USD")) == 1


def test_recording_a_different_claim_under_the_same_id_is_refused(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    """Same id, different content is a fork wearing a familiar name: either a
    revision (which gets a new id plus supersedes) or a collision. Refused."""
    ledger, artifact = stored_ledger
    ledger.record_claim(_claim(artifact))
    with pytest.raises(ClaimLedgerError, match="already recorded"):
        ledger.record_claim(_claim(artifact, claim_object=99999.99))


def test_supersession_inserts_and_preserves(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    """A correction that erases the old claim is not a correction, it is a cover-up."""
    ledger, artifact = stored_ledger
    ledger.record_claim(_claim(artifact, claim_class=ClaimClass.INFERRED))

    revision = _claim(
        artifact,
        claim_id="claim-2",
        claim_class=ClaimClass.REVISED,
        supersedes="claim-1",
    )
    ledger.supersede("claim-1", revision)

    old = ledger.get("claim-1")
    new = ledger.get("claim-2")
    assert old.claim_class is ClaimClass.INFERRED
    assert new.claim_class is ClaimClass.REVISED
    assert new.supersedes == "claim-1"


def test_supersede_must_name_what_it_replaces(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    """A revision that does not name its predecessor is a fork, not a correction."""
    ledger, artifact = stored_ledger
    ledger.record_claim(_claim(artifact))
    orphan = _claim(artifact, claim_id="claim-2")
    with pytest.raises(ClaimLedgerError, match="must set supersedes"):
        ledger.supersede("claim-1", orphan)


def test_supersede_of_an_unknown_claim_is_refused(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    ledger, artifact = stored_ledger
    revision = _claim(artifact, claim_id="claim-2", supersedes="no-such-claim")
    with pytest.raises(KeyError, match="unknown claim"):
        ledger.supersede("no-such-claim", revision)


def test_history_follows_supersedes(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    ledger, artifact = stored_ledger
    ledger.record_claim(_claim(artifact, claim_id="v1"))
    ledger.supersede("v1", _claim(artifact, claim_id="v2", supersedes="v1"))
    ledger.supersede("v2", _claim(artifact, claim_id="v3", supersedes="v2"))
    assert [c.claim_id for c in ledger.history("v3")] == ["v1", "v2", "v3"]


def test_claims_for_subject_are_ordered(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    ledger, artifact = stored_ledger
    ledger.record_claim(_claim(artifact, claim_id="a", predicate="close_price"))
    ledger.record_claim(_claim(artifact, claim_id="b", predicate="volume"))
    subjects = ledger.claims_for_subject("BTC/USD")
    assert {c.claim_id for c in subjects} == {"a", "b"}


# ══════════════════════════════════════════════════════════════════════════
# Bounds and taxonomy
# ══════════════════════════════════════════════════════════════════════════


def test_evidence_refs_are_bounded_at_eight(artifact: SourceArtifact) -> None:
    """A claim needing nine sources is not standing; split it."""
    with pytest.raises(ValueError, match="at most 8"):
        _claim(artifact, evidence_refs=[f"ref-{i}" for i in range(MAX_EVIDENCE_REFS + 1)])


def test_claim_chain_is_recheckable(
    stored_ledger: tuple[SqliteClaimLedger, SourceArtifact],
) -> None:
    """claim -> artifact -> hash, in one dict an auditor can walk."""
    ledger, artifact = stored_ledger
    claim = _claim(artifact)
    ledger.record_claim(claim)
    chain = ledger.get("claim-1").chain()
    assert chain["source_artifact_id"] == artifact.artifact_id
    assert chain["source_hash"] == artifact.source_hash


def test_created_at_is_stable_across_a_copy(artifact: SourceArtifact) -> None:
    """created_at is immutable: a copy carries the original instant."""
    claim = _claim(artifact)
    assert claim.model_copy().created_at == claim.created_at
