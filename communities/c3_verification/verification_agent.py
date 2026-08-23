"""Community 3: Verification Agent for auditing and validating research hypotheses."""

import logging

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import CandidateHypothesis, VerificationReport

logger = logging.getLogger(__name__)


class VerificationAgent:
    """Verification Agent that audits candidate hypotheses and generates verification reports."""

    def __init__(self, event_bus: BaseEventBus, min_confidence_threshold: float = 70.0) -> None:
        """Initialize VerificationAgent.

        Args:
            event_bus: Event bus instance for inter-community messaging.
            min_confidence_threshold: Minimum confidence score required for hypothesis verification (0-100).
        """
        self.event_bus = event_bus
        self.min_confidence_threshold = min_confidence_threshold

    async def verify_hypothesis(self, hypothesis: CandidateHypothesis) -> VerificationReport:
        """Audit candidate hypothesis, compute confidence score, and issue report.

        Args:
            hypothesis: CandidateHypothesis instance to audit.

        Returns:
            VerificationReport instance.
        """
        confidence_score = 0.0
        verified_claims: list[str] = []
        flagged_hallucinations: list[str] = []

        # Audit 1: Supporting arguments verification (+40 points)
        if hypothesis.supporting_arguments and len(hypothesis.supporting_arguments) > 0:
            confidence_score += 40.0
            verified_claims.extend(hypothesis.supporting_arguments)
        else:
            flagged_hallucinations.append("Missing supporting arguments")

        # Audit 2: Counter-arguments evaluation for balanced reasoning (+30 points)
        if hypothesis.counter_arguments and len(hypothesis.counter_arguments) > 0:
            confidence_score += 30.0
        else:
            flagged_hallucinations.append(
                "Missing counter-arguments (lacks balanced risk evaluation)"
            )

        # Audit 3: Risk/reward ratio adequacy (+30 points)
        if hypothesis.expected_risk_reward_ratio >= 1.5:
            confidence_score += 30.0
            verified_claims.append(
                f"Adequate risk/reward ratio ({hypothesis.expected_risk_reward_ratio:.2f} >= 1.5)"
            )
        else:
            flagged_hallucinations.append(
                f"Risk/reward ratio ({hypothesis.expected_risk_reward_ratio:.2f}) is below standard minimum threshold of 1.5"
            )

        confidence_score = min(100.0, max(0.0, confidence_score))
        is_verified = confidence_score >= self.min_confidence_threshold

        report = VerificationReport(
            hypothesis_id=hypothesis.hypothesis_id,
            confidence_score=confidence_score,
            verified_claims=verified_claims,
            flagged_hallucinations=flagged_hallucinations,
            verification_notes=(
                f"Verification audit completed for hypothesis {hypothesis.hypothesis_id}. "
                f"Confidence score: {confidence_score:.1f}. Verified: {is_verified}."
            ),
        )

        if report.is_verified:
            await self.event_bus.publish(EventTopic.VERIFICATION_COMPLETED, report)
            logger.info(
                "Published VerificationReport %s (is_verified=True) to %s",
                report.report_id,
                EventTopic.VERIFICATION_COMPLETED,
            )
        else:
            logger.info(
                "Verification failed for hypothesis %s (confidence=%.1f < threshold=%.1f). Report not published to VERIFICATION_COMPLETED.",
                hypothesis.hypothesis_id,
                confidence_score,
                self.min_confidence_threshold,
            )

        return report

    async def on_hypothesis_generated(self, hypothesis: CandidateHypothesis) -> None:
        """Event handler callback triggered when a candidate hypothesis is generated.

        Args:
            hypothesis: Received CandidateHypothesis event.
        """
        logger.info(
            "VerificationAgent received HYPOTHESIS_GENERATED event for hypothesis %s",
            hypothesis.hypothesis_id,
        )
        await self.verify_hypothesis(hypothesis)
