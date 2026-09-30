"""Counterfactual-retention tests for institutional memory (G180)."""

import pytest
from pydantic import ValidationError

from kernel.counterfactuals import (
    CounterfactualStore,
    OutcomeState,
    RestrainedDecision,
)


def test_counterfactual_retained_unresolved_then_resolved() -> None:
    """Prevents losing the foregone alternative: restrained decisions stay UNRESOLVED until known."""
    store = CounterfactualStore()
    record = store.retain(
        decision=RestrainedDecision.ABSTAIN,
        rationale="spread too wide to price the tail",
        context_ref="trade-123",
        now=1_700_000_000.0,
    )
    assert record.status is OutcomeState.UNRESOLVED
    assert record.foregone_outcome is None
    assert store.open_items() == [record]

    resolved = store.resolve(record.record_id, "rally +4.2% missed", now=1_700_010_000.0)
    assert resolved.status is OutcomeState.RESOLVED
    assert resolved.foregone_outcome == "rally +4.2% missed"
    assert resolved.supersedes == record.record_id
    assert store.open_items() == []


def test_resolution_never_mutates_the_original() -> None:
    """Prevents rewriting history: resolving supersedes by new record, original untouched."""
    store = CounterfactualStore()
    original = store.retain(
        decision=RestrainedDecision.NO_NEW_RISK,
        rationale="exposure cap already reached",
        now=1_700_000_000.0,
    )
    snapshot = original.model_dump()

    store.resolve(original.record_id, "drawdown avoided", now=1_700_010_000.0)

    assert store.get(original.record_id).model_dump() == snapshot
    assert store.get(original.record_id).status is OutcomeState.UNRESOLVED
    with pytest.raises(ValidationError):
        original.foregone_outcome = "edited"  # type: ignore[misc]

    chain = store.history(store.all_records()[-1].record_id)
    assert [r.record_id for r in chain] == [original.record_id, chain[-1].record_id]
    assert chain[-1].status is OutcomeState.RESOLVED


def test_double_resolve_and_unknown_id_fail_closed() -> None:
    """Prevents outcome churn: a RESOLVED record cannot be re-resolved, unknown ids raise."""
    store = CounterfactualStore()
    record = store.retain(
        decision=RestrainedDecision.REJECT, rationale="thesis invalidated", now=1_700_000_000.0
    )
    store.resolve(record.record_id, "flat", now=1_700_010_000.0)
    successor_id = store.all_records()[-1].record_id
    with pytest.raises(ValueError, match="already RESOLVED"):
        store.resolve(successor_id, "contradicting rewrite", now=1_700_020_000.0)
    with pytest.raises(KeyError):
        store.resolve("cf-999999", "anything", now=1_700_020_000.0)


def test_all_restrained_decision_kinds_retained() -> None:
    """Prevents selective memory: ABSTAIN, REJECT, and NO_NEW_RISK are all retainable."""
    store = CounterfactualStore()
    for kind in (
        RestrainedDecision.ABSTAIN,
        RestrainedDecision.REJECT,
        RestrainedDecision.NO_NEW_RISK,
    ):
        record = store.retain(decision=kind, rationale=f"reason for {kind.value}", now=1.0)
        assert record.decision is kind
    assert len(store) == 3
