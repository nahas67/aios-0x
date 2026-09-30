"""Decay + retrieval-contract tests for institutional memory (G180)."""

import pytest

from kernel.memory_tiers import (
    SAFETY_SALIENCE_FLOOR,
    TIER_TABLE,
    Criticality,
    MemoryRecord,
    MemoryTier,
    is_expired,
    rank_by_salience,
    record_salience,
)
from kernel.retrieval_contract import (
    CONTRACT_VERSION,
    ContractVersionMismatch,
    RetrievalQuery,
    RetrievalVerdict,
    evaluate_retrieval,
)

TEN_YEARS: float = 10.0 * 365.0 * 24.0 * 3600.0


def test_safety_records_never_decay_past_every_half_life() -> None:
    """Prevents silent loss of safety-critical memory: SAFETY salience must hold its floor."""
    t0 = 1_700_000_000.0
    far_future = t0 + TEN_YEARS
    for tier in MemoryTier:
        record = MemoryRecord(
            record_id=f"safety-{tier.value}",
            tier=tier,
            criticality=Criticality.SAFETY,
            created_at=t0,
        )
        assert record_salience(record, far_future) >= SAFETY_SALIENCE_FLOOR
        assert record_salience(record, far_future) == pytest.approx(record.base_score)
        assert is_expired(record, far_future) is False


def test_decay_reduces_ordinary_recall_and_reorders_with_age() -> None:
    """Prevents ageless recall: ordinary records decay and fresher ones outrank stale ones."""
    t0 = 1_700_000_000.0
    stale = MemoryRecord(
        record_id="old", tier=MemoryTier.M2, criticality=Criticality.ROUTINE, created_at=t0
    )
    fresh = MemoryRecord(
        record_id="new",
        tier=MemoryTier.M2,
        criticality=Criticality.ROUTINE,
        created_at=t0 + 30.0 * 24.0 * 3600.0,
    )
    now = t0 + 30.0 * 24.0 * 3600.0
    assert record_salience(stale, now) < stale.base_score
    assert record_salience(fresh, now) == pytest.approx(fresh.base_score)
    ranked = rank_by_salience([stale, fresh], now)
    assert [r.record_id for r in ranked] == ["new", "old"]


def test_constitutional_tiers_hold_without_half_life() -> None:
    """Prevents accidental expiry of constitutional memory: M8/M9 configs carry no decay."""
    assert TIER_TABLE[MemoryTier.M8].half_life_seconds is None
    assert TIER_TABLE[MemoryTier.M9].half_life_seconds is None
    assert TIER_TABLE[MemoryTier.M8].retention_horizon_seconds is None
    assert TIER_TABLE[MemoryTier.M9].retention_horizon_seconds is None


def test_retrieval_contract_version_mismatch_refused() -> None:
    """Prevents silent cross-version certification: a stale contract version is refused."""
    query = RetrievalQuery(contract_version=CONTRACT_VERSION + 1, min_evidence=1)
    with pytest.raises(ContractVersionMismatch):
        evaluate_retrieval(query, ["e1"], ["e1"])


def test_sufficient_with_stale_evidence_rejected() -> None:
    """Prevents stale evidence certifying sufficiency: out-of-batch refs force REJECTED."""
    query = RetrievalQuery(contract_version=CONTRACT_VERSION, min_evidence=2)
    rejected = evaluate_retrieval(query, ["e1", "stale-9"], ["e1", "e2"])
    assert rejected.verdict is RetrievalVerdict.REJECTED

    sufficient = evaluate_retrieval(query, ["e1", "e2"], ["e1", "e2", "e3"])
    assert sufficient.verdict is RetrievalVerdict.SUFFICIENT

    short = evaluate_retrieval(query, ["e1"], ["e1", "e2"])
    assert short.verdict is RetrievalVerdict.INSUFFICIENT
