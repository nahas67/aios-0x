"""Counterfactual retention: every ABSTAIN / REJECT / NO_NEW_RISK decision is kept.

Each retained decision records the foregone outcome — what would have happened
had the action been taken. The outcome is ``None`` (``UNRESOLVED``) until it is
actually known; ``resolve`` attaches it later.

Retention is append-only in spirit: records are frozen (immutable) and are
added, never edited. Resolving an outcome that confirms — or contradicts — the
earlier record creates a NEW superseding record linked via ``supersedes``; the
original is never mutated, so audit can always replay what was known when.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, model_validator


class RestrainedDecision(StrEnum):
    ABSTAIN = "ABSTAIN"
    REJECT = "REJECT"
    NO_NEW_RISK = "NO_NEW_RISK"


class OutcomeState(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"


class CounterfactualRecord(BaseModel, frozen=True):
    """One retained counterfactual. Immutable by construction (frozen)."""

    record_id: str
    decision: RestrainedDecision
    rationale: str
    context_ref: str = ""
    foregone_outcome: str | None = None
    status: OutcomeState = OutcomeState.UNRESOLVED
    supersedes: str = ""
    created_at: float = 0.0

    @model_validator(mode="after")
    def _status_matches_outcome(self) -> CounterfactualRecord:
        resolved = self.foregone_outcome is not None
        if resolved and self.status is not OutcomeState.RESOLVED:
            raise ValueError("record with a foregone outcome must be RESOLVED")
        if not resolved and self.status is not OutcomeState.UNRESOLVED:
            raise ValueError("record without a foregone outcome must be UNRESOLVED")
        return self


class CounterfactualStore:
    """Append-only store: ``retain`` adds UNRESOLVED records, ``resolve``
    supersedes them with new RESOLVED records. No method mutates a record."""

    def __init__(self) -> None:
        self._records: dict[str, CounterfactualRecord] = {}
        self._superseded: set[str] = set()
        self._sequence: int = 0

    def __len__(self) -> int:
        return len(self._records)

    def _next_id(self) -> str:
        self._sequence += 1
        return f"cf-{self._sequence:06d}"

    def retain(
        self,
        *,
        decision: RestrainedDecision,
        rationale: str,
        context_ref: str = "",
        now: float,
    ) -> CounterfactualRecord:
        """Retain a restrained decision with its outcome UNRESOLVED."""
        if not rationale.strip():
            raise ValueError("rationale is required: a counterfactual without reason is hearsay")
        record = CounterfactualRecord(
            record_id=self._next_id(),
            decision=decision,
            rationale=rationale,
            context_ref=context_ref,
            foregone_outcome=None,
            status=OutcomeState.UNRESOLVED,
            created_at=now,
        )
        self._records[record.record_id] = record
        return record

    def resolve(
        self, record_id: str, foregone_outcome: str, now: float
    ) -> CounterfactualRecord:
        """Attach a known outcome via a NEW superseding record (no mutation).

        Raises:
            KeyError: unknown ``record_id``.
            ValueError: target already RESOLVED, or outcome empty.
        """
        original = self._records.get(record_id)
        if original is None:
            raise KeyError(f"counterfactual not found: {record_id!r}")
        if original.status is not OutcomeState.UNRESOLVED:
            raise ValueError(
                f"record {record_id!r} is already RESOLVED; "
                "a contradicting outcome needs a new retained decision, not a re-resolve"
            )
        if not foregone_outcome.strip():
            raise ValueError("foregone outcome must be a non-empty record of what happened")
        successor = CounterfactualRecord(
            record_id=self._next_id(),
            decision=original.decision,
            rationale=original.rationale,
            context_ref=original.context_ref,
            foregone_outcome=foregone_outcome,
            status=OutcomeState.RESOLVED,
            supersedes=original.record_id,
            created_at=now,
        )
        self._records[successor.record_id] = successor
        self._superseded.add(original.record_id)
        return successor

    def get(self, record_id: str) -> CounterfactualRecord:
        """Fetch one record by id (KeyError when unknown)."""
        record = self._records.get(record_id)
        if record is None:
            raise KeyError(f"counterfactual not found: {record_id!r}")
        return record

    def open_items(self) -> list[CounterfactualRecord]:
        """All still-UNRESOLVED records with no successor, oldest first."""
        unresolved = [
            r
            for r in self._records.values()
            if r.status is OutcomeState.UNRESOLVED and r.record_id not in self._superseded
        ]
        unresolved.sort(key=lambda r: r.created_at)
        return unresolved

    def history(self, record_id: str) -> list[CounterfactualRecord]:
        """The full supersede chain ending at ``record_id``, oldest first."""
        chain: list[CounterfactualRecord] = [self.get(record_id)]
        while chain[0].supersedes:
            chain.insert(0, self.get(chain[0].supersedes))
        return chain

    def all_records(self) -> list[CounterfactualRecord]:
        """Every retained record, in retention order."""
        ordered = sorted(self._records.values(), key=lambda r: r.record_id)
        return list(ordered)
