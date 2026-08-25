"""AutoResearch: the UPDATE-HYPOTHESIS-SPACE step of the core loop.

The prototype's learning loop ended at "persist knowledge". This engine
closes it: after every replay it reads the durable research store and
deterministically proposes NEW hypotheses for future runs:

- INVERSION: a symbol whose hypotheses keep getting REJECTED (and never
  supported) yields a counter-thesis (momentum entries fail there -> test
  mean-reversion entry instead). Parents = the rejected hypotheses.
- CONTINUATION: a symbol with repeated SUPPORTED outcomes yields a
  trend-continuation thesis. Parents = the supported hypotheses.

Every proposal is:
- DURABLE: a first-class Hypothesis row (UNTESTED) with parent lineage,
- TRACKED: registered into the kernel state machine via the bridge,
- AUDITABLE: a HypothesisCreated platform event names the auto researcher,
- STAGED: a challenger trial is proposed for human-gated evaluation.

Nothing here promotes anything. Rejection stays the default; AutoResearch
only widens the hypothesis space honestly.
"""

import logging
from collections import defaultdict

from core.research_store import BaseResearchStore
from schemas.contracts import (
    CandidateHypothesis,
    Hypothesis,
    HypothesisStatus,
)

logger = logging.getLogger(__name__)

_AUTO_SOURCE = "auto_research"
_MIN_OUTCOMES_PER_SIDE = 2


class AutoResearchEngine:
    """Deterministic hypothesis-space expander over durable knowledge."""

    def __init__(self, research_store: BaseResearchStore) -> None:
        self.store = research_store

    # ------------------------------------------------------------- analysis

    def _settled_by_symbol(self) -> dict[str, dict[str, list[Hypothesis]]]:
        """supported/rejected hypothesis lists grouped by symbol."""
        buckets: dict[str, dict[str, list[Hypothesis]]] = defaultdict(
            lambda: {"SUPPORTED": [], "REJECTED": []}
        )
        for h in self.store.list_hypotheses(limit=5000):
            if h.symbol is None:
                continue
            if h.status is HypothesisStatus.SUPPORTED:
                buckets[h.symbol]["SUPPORTED"].append(h)
            elif h.status is HypothesisStatus.REJECTED:
                buckets[h.symbol]["REJECTED"].append(h)
        return buckets

    def _signature_exists(self, signature: str) -> bool:
        """Dedupe: one auto-proposal per rule+symbol across sessions."""
        for h in self.store.list_hypotheses(limit=5000):
            if h.applicable_regime.startswith(f"{_AUTO_SOURCE}:"):
                if h.expected_outcome == signature:
                    return True
        return False

    # ------------------------------------------------------------- synthesis

    def synthesize(self, max_proposals: int = 4) -> list[Hypothesis]:
        """Produce new UNTESTED hypotheses from settled knowledge (idempotent)."""
        proposals: list[Hypothesis] = []
        for symbol, sides in sorted(self._settled_by_symbol().items()):
            rejected = sides["REJECTED"]
            supported = sides["SUPPORTED"]

            if len(rejected) >= _MIN_OUTCOMES_PER_SIDE and not supported:
                signature = f"invert:{symbol}"
                if self._signature_exists(signature):
                    continue
                parents = [h.hypothesis_id for h in rejected[:5]]
                proposals.append(
                    self._make(
                        symbol=symbol,
                        statement=(
                            f"Momentum entries on {symbol} repeatedly failed "
                            f"({len(rejected)} rejections); a mean-reversion "
                            f"entry near band-low should satisfy the same R:R."
                        ),
                        rationale=(
                            f"auto-research inversion: {len(rejected)} REJECTED, "
                            f"0 SUPPORTED for this symbol"
                        ),
                        expected_outcome=signature,
                        parents=parents,
                    )
                )
            elif len(supported) >= _MIN_OUTCOMES_PER_SIDE:
                signature = f"continue:{symbol}"
                if self._signature_exists(signature):
                    continue
                parents = [h.hypothesis_id for h in supported[:5]]
                proposals.append(
                    self._make(
                        symbol=symbol,
                        statement=(
                            f"Trend continuation on {symbol}: {len(supported)} "
                            f"supported outcomes suggest persistence survives "
                            f"wider targets at equal R:R."
                        ),
                        rationale=(
                            f"auto-research continuation: {len(supported)} "
                            f"SUPPORTED outcomes"
                        ),
                        expected_outcome=signature,
                        parents=parents,
                    )
                )
            if len(proposals) >= max_proposals:
                break
        return proposals

    def _make(
        self,
        symbol: str,
        statement: str,
        rationale: str,
        expected_outcome: str,
        parents: list[str],
    ) -> Hypothesis:
        return Hypothesis(
            statement=statement,
            rationale=f"{_AUTO_SOURCE}: {rationale}",
            expected_outcome=expected_outcome,
            applicable_regime=f"{_AUTO_SOURCE}:{expected_outcome}",
            assumptions=[
                "derived deterministically from settled postmortem outcomes",
                "requires verification before any strategy may reference it",
            ],
            symbol=symbol,
            timeframe="1d",
            status=HypothesisStatus.UNTESTED,
            parent_hypotheses=parents,
        )

    # -------------------------------------------------------------- persistence

    def register(self, proposal: Hypothesis) -> Hypothesis:
        """Persist the proposal (idempotent by signature)."""
        try:
            existing = self.store.get_hypothesis(proposal.hypothesis_id)
            return existing
        except KeyError:
            pass
        self.store.save_hypothesis(proposal)
        logger.info("auto-research proposed %s (%s)", proposal.hypothesis_id[:8], proposal.symbol)
        return proposal


def as_candidate(h: Hypothesis) -> CandidateHypothesis:
    """Bridge-compatible transient payload carrying the SAME hypothesis_id."""
    return CandidateHypothesis(
        hypothesis_id=h.hypothesis_id,
        symbol=h.symbol or "?",
        thesis=h.statement,
        supporting_arguments=list(h.assumptions),
        counter_arguments=["auto-generated proposal; unverified"],
        timeframe=h.timeframe or "1d",
        expected_risk_reward_ratio=h.expected_risk_reward_ratio or 2.0,
    )


def outcome_evidence_summary(store: BaseResearchStore, hypothesis_id: str) -> dict[str, float]:
    """Aggregate realized pnl across outcome evidence (observability helper)."""
    total = 0.0
    count = 0
    for ev, rel in store.evidence_for_hypothesis(hypothesis_id):
        if rel != "outcome":
            continue
        count += 1
        for claim in ev.claims:
            if claim.startswith("realized_pnl="):
                try:
                    total += float(claim.split("=", 1)[1].replace("+", ""))
                except ValueError:
                    pass
    return {"outcomes": float(count), "realized_pnl_total": round(total, 2)}
