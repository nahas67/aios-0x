"""Community 3: Verification Agent - evidence-grounded hypothesis auditing.

Phase 2 upgrade: when an EvidencePack is cached for the hypothesis symbol,
every numeric claim in supporting/counter arguments is checked against real
market facts. Fabricated numbers are flagged as hallucinations and reduce the
fact score below the verification threshold. Without evidence the structural
rubric applies unchanged (backward compatible).
"""

import logging
import re

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import (
    CandidateHypothesis,
    EvidencePack,
    MarketDataPayload,
    VerificationReport,
)

logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def cited_numbers(text: str) -> list[float]:
    """Extract numeric literals from a claim string."""
    return [float(m) for m in _NUMBER_RE.findall(text)]


def _is_consistent(number: float, references: list[float]) -> bool:
    """A cited number is consistent if it matches any reference within tolerance."""
    for ref in references:
        tol = max(0.02 * abs(ref), 0.011)
        if abs(number - ref) <= tol:
            return True
    return False


class VerificationAgent:
    """Verification Agent that audits hypotheses and issues gatekeeping reports."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        min_confidence_threshold: float = 70.0,
    ) -> None:
        self.event_bus = event_bus
        self.min_confidence_threshold = min_confidence_threshold
        self._evidence: dict[str, EvidencePack] = {}

    async def on_data_acquired(self, payload: MarketDataPayload) -> None:
        """Cache the latest evidence per symbol (runner wires DATA_ACQUIRED here)."""
        self._evidence[payload.symbol] = EvidencePack.from_payload(payload)

    def clear_evidence(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._evidence.clear()
        else:
            self._evidence.pop(symbol, None)

    def check_numeric_claims(
        self, arguments: list[str], evidence: EvidencePack
    ) -> tuple[list[str], list[str]]:
        """Split argument strings into consistent vs fabricated-number offenders."""
        references = evidence.reference_numbers()
        ok: list[str] = []
        flagged: list[str] = []
        for arg in arguments:
            numbers = cited_numbers(arg)
            bad = [n for n in numbers if not _is_consistent(n, references)]
            if bad:
                formatted = ", ".join(f"{n:g}" for n in bad)
                flagged.append(f"Fabricated or inconsistent numbers [{formatted}] in claim: {arg}")
            else:
                ok.append(arg)
        return ok, flagged

    async def verify_hypothesis(self, hypothesis: CandidateHypothesis) -> VerificationReport:
        """Audit candidate hypothesis, compute rubric scores, and issue report.

        Rubric (Doc 04): facts +40, balance +30, math +30; verified at >=70.
        """
        evidence = self._evidence.get(hypothesis.symbol)
        verified_claims: list[str] = []
        flagged_hallucinations: list[str] = []

        # ---- Audit 1: Fact & Data Verification (+40)
        fact_score: float
        if not hypothesis.supporting_arguments:
            fact_score = 0.0
            flagged_hallucinations.append("Missing supporting arguments")
        elif evidence is None:
            # No evidence available: full structural credit (legacy behavior).
            fact_score = 40.0
            verified_claims.extend(hypothesis.supporting_arguments)
        else:
            all_args = list(hypothesis.supporting_arguments) + list(hypothesis.counter_arguments)
            _, fabricated = self.check_numeric_claims(all_args, evidence)
            if fabricated:
                # Fabricated numbers gut the fact score below the pass line:
                # 5 + 30 + 30 = 65 < 70 -> rejected.
                fact_score = 5.0
                flagged_hallucinations.extend(fabricated)
                logger.warning(
                    "Numeric hallucination detected for %s (%d claims)",
                    hypothesis.hypothesis_id,
                    len(fabricated),
                )
            else:
                fact_score = 40.0
                verified_claims.extend(hypothesis.supporting_arguments)
                if cited_numbers(" ".join(hypothesis.supporting_arguments)):
                    verified_claims.append(
                        "All cited numbers consistent with decision-time evidence."
                    )

        # ---- Audit 2: Balanced Reasoning (+30)
        balance_score = 0.0
        if hypothesis.counter_arguments:
            balance_score += 30.0
        else:
            flagged_hallucinations.append(
                "Missing counter-arguments (lacks balanced risk evaluation)"
            )

        # ---- Audit 3: Mathematical & Risk Validity (+30)
        math_score = 0.0
        rr = hypothesis.expected_risk_reward_ratio
        if rr >= 1.5:
            math_score += 30.0
            verified_claims.append(f"Adequate risk/reward ratio ({rr:.2f} >= 1.5)")
        else:
            flagged_hallucinations.append(
                f"Risk/reward ratio ({rr:.2f}) is below standard minimum threshold of 1.5"
            )

        confidence_score = min(100.0, max(0.0, fact_score + balance_score + math_score))
        is_verified = confidence_score >= self.min_confidence_threshold

        report = VerificationReport(
            hypothesis_id=hypothesis.hypothesis_id,
            confidence_score=confidence_score,
            is_verified=is_verified,
            verified_claims=verified_claims,
            flagged_hallucinations=flagged_hallucinations,
            verification_notes=(
                f"Verification audit for {hypothesis.hypothesis_id}: "
                f"facts={fact_score:.0f}/40 balance={balance_score:.0f}/30 "
                f"math={math_score:.0f}/30 total={confidence_score:.1f}. "
                f"Evidence {'used' if evidence else 'unavailable (structural only)'}."
            ),
            fact_score=fact_score,
            balance_score=balance_score,
            math_score=math_score,
        )

        if report.is_verified:
            await self.event_bus.publish(EventTopic.VERIFICATION_COMPLETED, report)
            logger.info(
                "Published VerificationReport %s (score=%.1f) to %s",
                report.report_id,
                confidence_score,
                EventTopic.VERIFICATION_COMPLETED,
            )
        else:
            logger.info(
                "Verification failed for hypothesis %s (score=%.1f < %.1f); not published.",
                hypothesis.hypothesis_id,
                confidence_score,
                self.min_confidence_threshold,
            )
        return report

    async def on_hypothesis_generated(self, hypothesis: CandidateHypothesis) -> None:
        """Event handler callback triggered when a candidate hypothesis is generated."""
        await self.verify_hypothesis(hypothesis)
