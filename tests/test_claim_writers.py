"""Producers write through the ledger now (goal G040).

A ledger nobody writes to is a schema. These tests prove the two producer
shapes land as claims with their confidence intact and their failures
attached — and the properties that keep the conversion honest: confidence
never upgraded at the boundary, deterministic ids making replays no-ops,
and the artefact stored before the claim that resolves to it.
"""

from __future__ import annotations

import pytest

from core.claim_ledger import ClaimLedgerError, ClaimVerdict, build_sqlite_claim_ledger
from core.claim_writers import (
    evidence_package_claim,
    record_evidence_package,
    record_verification_report,
    verification_report_claim,
)
from schemas.contracts import EvidencePackage, VerificationReport


def _report(**overrides) -> VerificationReport:
    fields: dict[str, object] = {
        "report_id": "rep-1",
        "hypothesis_id": "hyp-1",
        "confidence_score": 85.0,
        "is_verified": True,
        "verified_claims": ["revenue grew 12%", "margins held"],
        "flagged_hallucinations": [],
        "verification_notes": "clean pass",
        "fact_score": 40.0,
        "balance_score": 30.0,
        "math_score": 15.0,
    }
    fields.update(overrides)
    return VerificationReport(**fields)  # type: ignore[arg-type]


def _package(**overrides) -> EvidencePackage:
    fields: dict[str, object] = {
        "evidence_id": "ev-1",
        "source": "c3_verification",
        "claims": ["volatility regime stable", "spread within bounds"],
        "counter_claims": ["single-venue sample"],
        "confidence": 75.0,
        "linked_hypotheses": ["hyp-1"],
    }
    fields.update(overrides)
    return EvidencePackage(**fields)  # type: ignore[arg-type]


# ══════════════════════════════════════════════════════════════════════════
# Verification reports
# ══════════════════════════════════════════════════════════════════════════


def test_a_verified_report_lands_as_a_sufficient_claim(tmp_path) -> None:
    """The happy path: verdict, confidence, and evidence refs all survive
    the conversion."""
    ledger = build_sqlite_claim_ledger(tmp_path / "claims.db")
    recorded = record_verification_report(ledger, _report())
    assert recorded.subject_id == "hyp-1"
    assert recorded.predicate == "verification-verdict"
    assert recorded.verdict is ClaimVerdict.SUFFICIENT
    assert recorded.confidence == pytest.approx(0.85)
    assert recorded.evidence_refs == ["revenue grew 12%", "margins held"]
    chain = ledger.verify_chain(recorded.claim_id)
    assert chain["hash_verified"] is True
    assert chain["evidence_count"] == 2


def test_hallucinations_travel_as_contraindications(tmp_path) -> None:
    """What failed the report rides with what passed it. A claim carrying
    only its successes is a summary, and a summary cannot be audited."""
    ledger = build_sqlite_claim_ledger(tmp_path / "claims.db")
    recorded = record_verification_report(
        ledger,
        _report(
            confidence_score=45.0,
            is_verified=False,
            verified_claims=["revenue grew 12%"],
            flagged_hallucinations=["invented guidance number"],
        ),
    )
    assert recorded.verdict is ClaimVerdict.PARTIAL
    assert recorded.contraindications == ["invented guidance number"]


def test_confidence_is_never_upgraded_at_the_boundary() -> None:
    """A perfect score with one evidence string is 0.99, not 1.0: certainty
    from a single source is trust, and the ledger refuses to record trust as
    measurement. The downgrade happens here, loudly, rather than as a
    validation error three layers down."""
    _, claim = verification_report_claim(
        _report(confidence_score=100.0, verified_claims=["one strong claim"])
    )
    assert claim.confidence == pytest.approx(0.99)


def test_two_refs_keep_full_confidence() -> None:
    _, claim = verification_report_claim(_report(confidence_score=100.0))
    assert claim.confidence == pytest.approx(1.0)


def test_replaying_a_report_is_a_no_op(tmp_path) -> None:
    """Deterministic claim ids make pipeline replays idempotent. Twins would
    double-count the same judgment in every downstream denominator."""
    ledger = build_sqlite_claim_ledger(tmp_path / "claims.db")
    first = record_verification_report(ledger, _report())
    second = record_verification_report(ledger, _report())
    assert second.claim_id == first.claim_id
    assert len(ledger.claims_for_subject("hyp-1")) == 1


# ══════════════════════════════════════════════════════════════════════════
# Evidence packages
# ══════════════════════════════════════════════════════════════════════════


def test_an_evidence_package_lands_documented(tmp_path) -> None:
    ledger = build_sqlite_claim_ledger(tmp_path / "claims.db")
    recorded = record_evidence_package(ledger, _package())
    assert recorded.subject_id == "hyp-1"
    assert recorded.predicate == "research-evidence"
    assert recorded.verdict is ClaimVerdict.SUFFICIENT
    assert recorded.confidence == pytest.approx(0.75)
    assert recorded.contraindications == ["single-venue sample"]
    assert ledger.verify_chain(recorded.claim_id)["hash_verified"] is True


def test_an_unlinked_package_names_its_source_as_subject(tmp_path) -> None:
    """No hypothesis link, no invented subject: the source stands in. A
    writer that defaulted the subject would file orphan findings under a
    name nobody chose."""
    ledger = build_sqlite_claim_ledger(tmp_path / "claims.db")
    recorded = record_evidence_package(ledger, _package(linked_hypotheses=[]))
    assert recorded.subject_id == "c3_verification"


def test_weak_evidence_is_wrong_not_silent(tmp_path) -> None:
    """Low confidence is recorded with its verdict, not dropped. Dropping
    weak evidence is how a ledger becomes a record of successes."""
    ledger = build_sqlite_claim_ledger(tmp_path / "claims.db")
    recorded = record_evidence_package(ledger, _package(confidence=20.0))
    assert recorded.verdict is ClaimVerdict.WRONG
    assert recorded.confidence == pytest.approx(0.20)


def test_evidence_refs_are_capped_at_eight() -> None:
    """The ledger's bound is respected at the boundary, not discovered at
    insert time."""
    _, claim = evidence_package_claim(
        _package(claims=[f"finding {i}" for i in range(20)])
    )
    assert len(claim.evidence_refs) == 8


# ══════════════════════════════════════════════════════════════════════════
# Failure modes
# ══════════════════════════════════════════════════════════════════════════


def test_a_claim_without_a_stored_source_is_refused(tmp_path) -> None:
    """Artifact first, claim second: the writer stores in that order because
    the ledger refuses any other. Tested here rather than trusted to review."""
    from core.claim_ledger import Claim, ClaimClass, ProvenanceTag

    ledger = build_sqlite_claim_ledger(tmp_path / "claims.db")
    artifact, _ = verification_report_claim(_report())
    orphan = Claim(
        claim_id="orphan",
        subject_id="hyp-1",
        predicate="verification-verdict",
        claim_object={},
        claim_class=ClaimClass.INFERRED,
        provenance=ProvenanceTag.INFERRED,
        evidence_refs=["a", "b"],
        source_artifact_id=artifact.artifact_id,
        source_hash=artifact.source_hash,
        confidence=0.5,
    )
    with pytest.raises(ClaimLedgerError, match="unknown artifact"):
        ledger.record_claim(orphan)


def test_available_at_is_the_record_moment() -> None:
    """The PIT join key is when the ledger could know, not when the world
    happened: backtests join on knowability, and anything else is look-ahead."""
    from datetime import UTC, datetime

    moment = datetime(2024, 5, 1, tzinfo=UTC)
    _, claim = verification_report_claim(_report(), retrieved_at=moment)
    assert claim.available_at == moment
