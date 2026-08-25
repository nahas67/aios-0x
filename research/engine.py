"""Hypothesis Engine: the Research Plane's knowledge core (Phase C).

Turns transient pipeline payloads into durable knowledge:

- CandidateHypothesis (debate output)  -> persistent Hypothesis row
- VerificationReport (C3 verdict)      -> EvidencePackage + status transition
- Postmortem outcome (closed trade)    -> outcome evidence + final status

Every piece of knowledge is hash-addressable, linked to the hypotheses it
supports or contradicts, and queryable across sessions. The engine also
restores non-terminal hypotheses into a fresh kernel state machine at boot,
so lifecycle enforcement continues where the previous session left off.

The engine NEVER decides what is true. It records what deterministic
components concluded (verification scores, realized PnL) — AI proposes,
the research plane remembers.
"""

from typing import Any

from core.research_store import BaseResearchStore
from kernel.bootstrap import AIOSKernel
from kernel.state_machine import StateMachineEngine
from schemas.contracts import (
    CandidateHypothesis,
    EvidencePackage,
    Hypothesis,
    HypothesisStatus,
    PostmortemRecord,
    VerificationReport,
)


class HypothesisEngine:
    """Registers, tests and settles first-class hypotheses durably."""

    def __init__(self, store: BaseResearchStore) -> None:
        self.store = store

    # ------------------------------------------------------------- registration

    def register_from_candidate(
        self, candidate: CandidateHypothesis, dataset_ref: dict[str, str] | None = None
    ) -> Hypothesis:
        """Persist a debate payload as a durable UNTESTED hypothesis (idempotent)."""
        try:
            existing = self.store.get_hypothesis(candidate.hypothesis_id)
            return existing  # already registered; bus redelivery is not new knowledge
        except KeyError:
            pass
        hypothesis = Hypothesis(
            hypothesis_id=candidate.hypothesis_id,
            statement=candidate.thesis[:1000],
            rationale="adversarial debate thesis (bull/bear synthesis)",
            expected_outcome=(
                f"{candidate.timeframe} move with target R:R >= "
                f"{candidate.expected_risk_reward_ratio:g}"
            ),
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            expected_risk_reward_ratio=candidate.expected_risk_reward_ratio,
            assumptions=list(candidate.supporting_arguments)
            + [f"counter: {a}" for a in candidate.counter_arguments],
            dataset_ref=dataset_ref or {},
        )
        self.store.save_hypothesis(hypothesis)
        return hypothesis

    def get(self, hypothesis_id: str) -> Hypothesis:
        return self.store.get_hypothesis(hypothesis_id)

    # -------------------------------------------------------------- verification

    def apply_verification(self, report: VerificationReport) -> EvidencePackage | None:
        """Record C3 verdict as evidence; verified hypotheses enter TESTING."""
        try:
            hypothesis = self.store.get_hypothesis(report.hypothesis_id)
        except KeyError:
            return None

        evidence = EvidencePackage(
            source="c3_verification",
            claims=["verified: " + c for c in report.verified_claims],
            counter_claims=["hallucination: " + f for f in report.flagged_hallucinations],
            confidence=report.confidence_score,
            provenance={
                "report_id": report.report_id,
                "is_verified": report.is_verified,
                "fact_score": report.fact_score,
                "balance_score": report.balance_score,
                "math_score": report.math_score,
                "notes": report.verification_notes,
            },
            payload={"report_id": report.report_id},
        )
        self._attach(
            hypothesis,
            evidence,
            relationship="supports" if report.is_verified else "contradicts",
        )

        if report.is_verified and hypothesis.status is HypothesisStatus.UNTESTED:
            hypothesis.status = HypothesisStatus.TESTING
        self.store.save_hypothesis(hypothesis)
        return evidence

    # ------------------------------------------------------------------- outcome

    def apply_outcome(
        self,
        hypothesis_id: str,
        direction_correct: bool,
        realized_pnl: float,
        postmortem: PostmortemRecord | None = None,
        execution_id: str | None = None,
    ) -> HypothesisStatus | None:
        """Close the loop: outcome evidence + terminal-or-persisted status."""
        try:
            hypothesis = self.store.get_hypothesis(hypothesis_id)
        except KeyError:
            return None
        if hypothesis.status in {
            HypothesisStatus.SUPPORTED,
            HypothesisStatus.REJECTED,
            HypothesisStatus.PARTIALLY_SUPPORTED,
        } and any(rel == "outcome" for _, rel in self.store.evidence_for_hypothesis(hypothesis_id)):
            return hypothesis.status  # already settled; one outcome per hypothesis

        evidence = EvidencePackage(
            source="postmortem",
            claims=[
                f"realized_pnl={realized_pnl:+.2f}",
                f"direction_correct={direction_correct}",
            ],
            confidence=hypothesis.confidence,
            provenance={
                "postmortem_id": postmortem.postmortem_id if postmortem else None,
                "execution_id": execution_id,
                "luck_assessment": postmortem.luck_assessment if postmortem else "",
            },
            payload={
                "postmortem_id": postmortem.postmortem_id if postmortem else None,
                "what_we_thought": postmortem.what_we_thought if postmortem else "",
                "should_change": postmortem.should_change if postmortem else [],
            },
        )
        target_status = HypothesisStatus.SUPPORTED if direction_correct else HypothesisStatus.REJECTED
        self._attach_with_status(hypothesis, evidence, "outcome", target_status)
        return target_status

    # ------------------------------------------------------- cross-session boot

    def restore_into_state_machine(self, sm: StateMachineEngine) -> int:
        """Re-register non-terminal hypotheses into a fresh kernel state machine.

        Terminal states stay in storage only: they are history, not active work.
        Returns how many objects were restored.
        """
        restored = 0
        for h in self.store.list_hypotheses(limit=5000):
            if h.status in {HypothesisStatus.UNTESTED, HypothesisStatus.TESTING}:
                key = f"hypothesis:{h.hypothesis_id}"
                if key in sm._objects:  # noqa: SLF001 - restore is composition-root duty
                    continue
                sm._objects[key] = h.status.value  # noqa: SLF001
                restored += 1
        return restored

    def knowledge_summary(self) -> dict[str, Any]:
        """Counts by status for observability/UI."""
        summary: dict[str, int] = {}
        for h in self.store.list_hypotheses(limit=5000):
            summary[h.status.value] = summary.get(h.status.value, 0) + 1
        return {"statuses": summary, **self.store.counts()}

    # ------------------------------------------------------------------ internals

    def _attach(
        self, hypothesis: Hypothesis, evidence: EvidencePackage, relationship: str
    ) -> str:
        evidence.linked_hypotheses.append(hypothesis.hypothesis_id)
        evidence_id = self.store.save_evidence(evidence)
        self.store.link_evidence(hypothesis.hypothesis_id, evidence_id, relationship)
        if evidence_id not in hypothesis.evidence_ids:
            hypothesis.evidence_ids.append(evidence_id)
        return evidence_id

    def _attach_with_status(
        self,
        hypothesis: Hypothesis,
        evidence: EvidencePackage,
        relationship: str,
        status: HypothesisStatus,
    ) -> None:
        self._attach(hypothesis, evidence, relationship)
        hypothesis.status = status
        hypothesis.confidence = max(hypothesis.confidence, evidence.confidence)
        self.store.save_hypothesis(hypothesis)


def wire_kernel_to_engine(kernel: AIOSKernel, engine: HypothesisEngine) -> int:
    """Boot helper: make a fresh kernel aware of durable in-flight hypotheses."""
    return engine.restore_into_state_machine(kernel.state_machine)
