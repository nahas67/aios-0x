"""Versioned retrieval contract: stale evidence cannot certify sufficiency.

A query pins ``contract_version`` plus its evidence requirements. Evaluation
is fail-closed:

- version mismatch -> ``ContractVersionMismatch`` raised (refused, never
  silently coerced);
- a ``SUFFICIENT`` verdict is returned ONLY when every presented evidence ref
  is a member of the current retrieval batch; otherwise the verdict is
  ``REJECTED`` (stale evidence cannot certify);
- anything short of the required evidence count is ``INSUFFICIENT``.

Migration notes
---------------
- v0 (implicit, pre-contract): callers consumed raw retrieval batches with no
  version pin and no stale-evidence check. Any code written against that
  behaviour must migrate by pinning ``contract_version=1`` and passing the
  batch the evidence was drawn from.
- v1 (current, ``CONTRACT_VERSION``): introduces ``RetrievalQuery`` with a
  mandatory version pin, ``min_evidence`` requirement, and the
  sufficient-implies-subset-of-batch gate. Future versions MUST bump
  ``CONTRACT_VERSION`` and append a note here describing what changed and how
  v(n-1) queries migrate; old versions are refused, never coerced.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field

#: Current retrieval contract version. Bump deliberately with a migration note
#: in this module's docstring; never silently.
CONTRACT_VERSION: Final[int] = 1


class ContractVersionMismatch(ValueError):
    """Raised when a query pins a contract version this code does not serve."""


class RetrievalVerdict(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    REJECTED = "REJECTED"


class RetrievalQuery(BaseModel, frozen=True):
    """A retrieval request pinned to one contract version."""

    contract_version: int
    min_evidence: int = Field(default=1, ge=0)
    query_text: str = ""


class RetrievalAssessment(BaseModel, frozen=True):
    """The evaluated outcome for one query against one batch."""

    verdict: RetrievalVerdict
    reason: str
    presented_refs: tuple[str, ...] = ()
    batch_refs: tuple[str, ...] = ()


def evaluate_retrieval(
    query: RetrievalQuery,
    presented_refs: Sequence[str],
    batch_refs: Collection[str],
) -> RetrievalAssessment:
    """Evaluate a query against the current batch (fail-closed).

    Raises:
        ContractVersionMismatch: when ``query.contract_version`` is not the
            current ``CONTRACT_VERSION``.
    """
    if query.contract_version != CONTRACT_VERSION:
        raise ContractVersionMismatch(
            f"retrieval contract v{query.contract_version} not supported "
            f"(current: v{CONTRACT_VERSION}); migrate the caller"
        )
    presented = tuple(presented_refs)
    batch = set(batch_refs)
    unique_presented = set(presented)
    stale = sorted(unique_presented - batch)
    sufficient_by_count = len(unique_presented) >= query.min_evidence
    batch_snapshot = tuple(sorted(batch))
    if sufficient_by_count:
        if stale:
            return RetrievalAssessment(
                verdict=RetrievalVerdict.REJECTED,
                reason=f"stale evidence cannot certify: {len(stale)} ref(s) outside batch",
                presented_refs=presented,
                batch_refs=batch_snapshot,
            )
        return RetrievalAssessment(
            verdict=RetrievalVerdict.SUFFICIENT,
            reason="evidence meets requirement and is fully within batch",
            presented_refs=presented,
            batch_refs=batch_snapshot,
        )
    detail = (
        f"requires {query.min_evidence}, presented {len(unique_presented)}"
        + (f"; {len(stale)} stale ref(s) ignored" if stale else "")
    )
    return RetrievalAssessment(
        verdict=RetrievalVerdict.INSUFFICIENT,
        reason=f"insufficient evidence: {detail}",
        presented_refs=presented,
        batch_refs=batch_snapshot,
    )
