"""Tier-aware recall: decay actually demotes (goal G180).

The tier modules defined decay, expiry, and safety floors; this suite proves
the recall the system uses consults them. The properties that matter: expired
records are excluded (not merely down-ranked — a down-ranked secret is still
returned at k+1), SAFETY records survive past every horizon, legacy documents
without tier metadata are unaffected, and every blended match records how it
was ranked so the ordering is auditable without re-running the search.
"""

from __future__ import annotations

import pytest

from core.vector_memory import (
    BLEND_SIMILARITY_WEIGHT,
    InMemoryVectorMemory,
    VectorMatch,
    blend_with_salience,
)
from kernel.memory_tiers import salience_for

NOW = 1_700_000_000.0
DAY = 86_400.0


def _meta(
    tier: str | None = "M2",
    criticality: str = "ROUTINE",
    age_days: float = 1.0,
    access_count: int = 0,
) -> dict[str, object]:
    meta: dict[str, object] = {"access_count": access_count}
    if tier is not None:
        meta["tier"] = tier
    meta["criticality"] = criticality
    meta["created_at"] = NOW - age_days * DAY
    return meta


@pytest.fixture()
def memory() -> InMemoryVectorMemory:
    store = InMemoryVectorMemory()
    store.upsert("c", "fresh", "fresh momentum signal", _meta(age_days=1.0))
    store.upsert("c", "stale", "stale momentum signal", _meta(age_days=6.0))
    store.upsert("c", "ancient", "ancient momentum signal", _meta(age_days=60.0))
    store.upsert(
        "c", "risk-breach", "risk breach ledger entry", _meta(tier="M7", criticality="SAFETY", age_days=900.0)
    )
    store.upsert("c", "legacy", "legacy note with no tier metadata", {"access_count": 0})
    return store


def _salience(metadata: dict[str, object]) -> float | None:
    return salience_for(metadata, NOW)


# ══════════════════════════════════════════════════════════════════════════
# Exclusion and survival
# ══════════════════════════════════════════════════════════════════════════


def test_expired_records_are_excluded_not_downranked(memory: InMemoryVectorMemory) -> None:
    """M2 retains 7 days; the 60-day routine record must be absent, not
    last. Down-ranking would still return it at a generous k, which is
    retention by another name."""
    results = memory.search("c", "momentum signal", k=10, now=NOW, salience=_salience)
    assert "ancient" not in {m.doc_id for m in results}
    assert {"fresh", "stale"} <= {m.doc_id for m in results}


def test_safety_records_survive_every_horizon(memory: InMemoryVectorMemory) -> None:
    """900 days old on a 730-day tier: present anyway. The safety floor is
    enforced inside the salience function, not by callers remembering it."""
    results = memory.search("c", "risk breach ledger", k=10, now=NOW, salience=_salience)
    assert results
    assert results[0].doc_id == "risk-breach"


def test_decay_reorders_the_survivors(memory: InMemoryVectorMemory) -> None:
    """Same text family, different ages: the fresher record ranks first once
    salience blends in. Without the blend their order is similarity-only."""
    blended = memory.search("c", "momentum signal", k=10, now=NOW, salience=_salience)
    assert blended[0].doc_id == "fresh"
    assert "salience" in blended[0].metadata
    assert blended[0].metadata["blend_weight"] == BLEND_SIMILARITY_WEIGHT


def test_legacy_documents_without_tier_metadata_are_unaffected(
    memory: InMemoryVectorMemory,
) -> None:
    """Everything stored before tiering existed scores neutral and stays
    visible. Recall degrades open on metadata faults: hiding legacy
    documents would make tiering a deletion engine."""
    results = memory.search("c", "legacy note", k=10, now=NOW, salience=_salience)
    assert any(m.doc_id == "legacy" for m in results)


def test_no_salience_fn_means_legacy_ranking(memory: InMemoryVectorMemory) -> None:
    """Omitting the callable changes nothing: byte-identical ranking to the
    pre-blend path, so existing callers are unaffected until they opt in."""
    assert memory.search("c", "momentum signal", k=10) == memory.search(
        "c", "momentum signal", k=10, salience=None
    )


def test_unparseable_tier_metadata_falls_back_to_neutral() -> None:
    """One bad document must not fail the whole recall: garbage tier names
    score neutral rather than raising inside the search."""
    assert salience_for({"tier": "M99", "created_at": NOW - DAY}, NOW) == 1.0
    assert salience_for({"tier": "M2", "created_at": "not-a-time"}, NOW) == 1.0
    assert salience_for({}, NOW) == 1.0


# ══════════════════════════════════════════════════════════════════════════
# The blend itself
# ══════════════════════════════════════════════════════════════════════════


def test_blend_records_how_it_ranked() -> None:
    """Every blended match carries similarity, salience, and weight: the
    ordering is auditable from the match alone, without re-running."""
    matches = [
        VectorMatch(doc_id="a", score=0.9, text="a", metadata={}),
        VectorMatch(doc_id="b", score=0.5, text="b", metadata={}),
    ]
    (first, second) = blend_with_salience(matches, [0.1, 0.9])
    assert first.doc_id == "b"
    assert first.metadata["similarity"] == 0.5
    assert first.metadata["salience"] == 0.9
    assert first.metadata["blend_weight"] == BLEND_SIMILARITY_WEIGHT
    assert second.doc_id == "a"


def test_blend_scores_stay_in_bounds() -> None:
    """The convex combination of in-range inputs stays in [-1, 1]: the score
    bound the model promises still holds after blending."""
    matches = [VectorMatch(doc_id="a", score=-0.8, text="a", metadata={})]
    (only,) = blend_with_salience(matches, [0.0])
    assert -1.0 <= only.score <= 1.0


def test_all_excluded_yields_empty_not_an_error() -> None:
    """A recall with nothing surviving is an empty result, not a failure:
    the caller asked what is salient, and the answer was nothing."""
    matches = [VectorMatch(doc_id="a", score=0.9, text="a", metadata={})]
    assert blend_with_salience(matches, [None]) == []


def test_misaligned_blend_inputs_are_refused() -> None:
    """A blend over a misaligned pairing ranks documents by someone else's
    score. Refused, not zipped short."""
    matches = [VectorMatch(doc_id="a", score=0.9, text="a", metadata={})]
    with pytest.raises(ValueError, match="misaligned pairing"):
        blend_with_salience(matches, [0.5, 0.6])


def test_salience_fn_receives_match_metadata(memory: InMemoryVectorMemory) -> None:
    """The store passes each match's own metadata to the callable: per-doc
    tiers, not a global one. A blend over one shared score would not be
    tier-aware at all."""
    seen: list[dict[str, object]] = []

    def spy(metadata: dict[str, object]) -> float | None:
        seen.append(metadata)
        return 1.0

    memory.search("c", "momentum signal", k=10, now=NOW, salience=spy)
    assert len(seen) >= 3
    assert all("access_count" in meta for meta in seen)
