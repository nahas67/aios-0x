"""Writers that carry producer outputs into the claim ledger (goal G040).

The ledger exists and is tested, but nothing writes to it — a ledger nobody
writes to is a schema, not a record. These writers convert the two producer
shapes (verification reports from community 3, evidence packages from
research) into claims with content-addressed sources. Two disciplines keep
the conversion honest rather than lossy:

*Confidence is never upgraded by the writer.* The verification score maps to
claim confidence by division, capped below certainty unless the report
carries two independent evidence references — the ledger's own rule, applied
at the boundary rather than discovered later. A writer that rounded 0.99 up
to 1.0 would manufacture the certainty the gate exists to refuse.

*Claim ids are deterministic.* ``verification-report:{report_id}`` and
``research-evidence:{evidence_id}`` make re-recording a primary-key no-op
instead of a duplicate. A pipeline that replays its outputs (and every
pipeline replays eventually) must not manufacture twin claims.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.claim_ledger import (
    Claim,
    ClaimClass,
    ClaimVerdict,
    PostgresClaimLedger,
    ProvenanceTag,
    SourceArtifact,
    SqliteClaimLedger,
)
from schemas.contracts import EvidencePackage, VerificationReport

#: Either durable tier. Both hold the same claims or the parity suite has
#: found a defect.
ClaimLedger = SqliteClaimLedger | PostgresClaimLedger

__all__ = [
    "evidence_package_claim",
    "record_evidence_package",
    "record_verification_report",
    "verification_report_claim",
]

#: Mirrors the verification rubric scale (Doc 04): 70 verifies. Below 40 the
#: evidence weighs against more than for. Stated here rather than inferred,
#: because a threshold nobody wrote down is a threshold nobody can audit.
_SUFFICIENT_SCORE = 70.0
_PARTIAL_SCORE = 40.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


def verification_report_claim(
    report: VerificationReport, *, retrieved_at: datetime | None = None
) -> tuple[SourceArtifact, Claim]:
    """Convert a verification report into a source artifact plus one claim.

    One claim per report rather than per verified string: the report is the
    unit the agent produced and the rubric scored, and splitting it would
    manufacture N claims from one judgment. The verified strings travel as
    evidence refs (capped at eight by the ledger); the hallucinations travel
    as contraindications, so the claim carries what failed it alongside what
    passed it.
    """
    moment = retrieved_at or _utc_now()
    content = report.model_dump_json()
    artifact = SourceArtifact.create(
        content,
        kind="verification-report",
        source="c3-verification",
        retrieved_at=moment,
        metadata={"report_id": report.report_id, "hypothesis_id": report.hypothesis_id},
    )
    refs = list(dict.fromkeys(report.verified_claims))[:8]
    if report.is_verified and report.confidence_score >= _SUFFICIENT_SCORE:
        verdict = ClaimVerdict.SUFFICIENT
    elif report.confidence_score >= _PARTIAL_SCORE:
        verdict = ClaimVerdict.PARTIAL
    else:
        verdict = ClaimVerdict.WRONG
    raw_confidence = report.confidence_score / 100.0
    confidence = (
        raw_confidence
        if len(set(refs)) >= 2 or raw_confidence < 1.0
        else 0.99
    )
    return artifact, Claim(
        claim_id=f"verification-report:{report.report_id}",
        subject_id=report.hypothesis_id,
        predicate="verification-verdict",
        claim_object={
            "is_verified": report.is_verified,
            "confidence_score": report.confidence_score,
            "fact_score": report.fact_score,
            "balance_score": report.balance_score,
            "math_score": report.math_score,
        },
        claim_class=ClaimClass.INFERRED,
        provenance=ProvenanceTag.INFERRED,
        evidence_refs=refs,
        source_artifact_id=artifact.artifact_id,
        source_hash=artifact.source_hash,
        available_at=moment,
        confidence=confidence,
        verdict=verdict,
        contraindications=list(report.flagged_hallucinations),
    )


def evidence_package_claim(
    package: EvidencePackage, *, retrieved_at: datetime | None = None
) -> tuple[SourceArtifact, Claim]:
    """Convert a research evidence package into a source artifact plus one claim.

    The package's own content hash does not become the artifact id: the
    artifact hashes the full serialised package (retrieval time included), so
    two retrievals of identical findings are distinguishable by when they
    were held. The findings hash remains in the claim object for the reader
    who wants content identity rather than retrieval identity.
    """
    moment = retrieved_at or _utc_now()
    content = package.model_dump_json()
    artifact = SourceArtifact.create(
        content,
        kind="research-evidence",
        source=package.source,
        retrieved_at=moment,
        metadata={"evidence_id": package.evidence_id},
    )
    refs = list(dict.fromkeys(package.claims))[:8]
    if package.confidence >= _SUFFICIENT_SCORE:
        verdict = ClaimVerdict.SUFFICIENT
    elif package.confidence >= _PARTIAL_SCORE:
        verdict = ClaimVerdict.PARTIAL
    else:
        verdict = ClaimVerdict.WRONG
    raw_confidence = package.confidence / 100.0
    confidence = raw_confidence if len(set(refs)) >= 2 or raw_confidence < 1.0 else 0.99
    subject = package.linked_hypotheses[0] if package.linked_hypotheses else package.source
    return artifact, Claim(
        claim_id=f"research-evidence:{package.evidence_id}",
        subject_id=subject,
        predicate="research-evidence",
        claim_object={
            "findings_hash": package.content_hash(),
            "source_version": package.source_version,
            "payload": package.payload,
        },
        claim_class=ClaimClass.DOCUMENTED,
        provenance=ProvenanceTag.EXTRACTED,
        evidence_refs=refs,
        source_artifact_id=artifact.artifact_id,
        source_hash=artifact.source_hash,
        available_at=moment,
        confidence=confidence,
        verdict=verdict,
        contraindications=list(package.counter_claims),
    )


def record_verification_report(
    ledger: ClaimLedger, report: VerificationReport, *, retrieved_at: datetime | None = None
) -> Claim:
    """Store a report's artifact, then its claim. Artifact first: a claim
    without a resolvable source is refused, so the order is load-bearing."""
    artifact, claim = verification_report_claim(report, retrieved_at=retrieved_at)
    ledger.store_artifact(artifact)
    return ledger.record_claim(claim)


def record_evidence_package(
    ledger: ClaimLedger, package: EvidencePackage, *, retrieved_at: datetime | None = None
) -> Claim:
    """Store a package's artifact, then its claim."""
    artifact, claim = evidence_package_claim(package, retrieved_at=retrieved_at)
    ledger.store_artifact(artifact)
    return ledger.record_claim(claim)
