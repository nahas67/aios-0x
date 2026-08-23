"""Vector memory contract tests: Qdrant local mode + in-memory fallback parity."""

import pytest

from core.vector_memory import (
    BaseVectorMemory,
    HashingEmbedder,
    InMemoryVectorMemory,
    QdrantLocalMemory,
)

IMPLEMENTATIONS = [QdrantLocalMemory, InMemoryVectorMemory]


def test_embedder_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder(dims=128)
    v1 = embedder.embed("bullish momentum breakout on BTC")
    v2 = embedder.embed("bullish momentum breakout on BTC")
    assert v1 == v2
    norm = sum(x * x for x in v1) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("impl", IMPLEMENTATIONS)
def test_upsert_search_semantic_retrieval_order(impl) -> None:
    memory: BaseVectorMemory = impl()

    docs = {
        "d1": "Bitcoin momentum thesis: bullish breakout with rising volume",
        "d2": "Apple earnings review: margin pressure from supply chain",
        "d3": "Ethereum gas fees spike concerns for defi users",
        "d4": "Fed rate decision impact on treasury yields",
    }
    for doc_id, text in docs.items():
        memory.upsert("research_theses", doc_id, text, {"source": "test"})

    hits = memory.search("research_theses", "BTC breakout volume momentum", k=3)
    assert len(hits) == 3
    assert hits[0].doc_id == "d1", f"expected crypto-momentum doc first, got {hits[0].doc_id}"
    assert all(-1.0 <= h.score <= 1.0 for h in hits)


@pytest.mark.parametrize("impl", IMPLEMENTATIONS)
def test_unknown_collection_returns_empty_and_overwrite_works(impl) -> None:
    memory: BaseVectorMemory = impl()
    assert memory.search("missing", "anything") == []

    memory.upsert("c", "same-id", "first version")
    memory.upsert("c", "same-id", "second version")
    hits = memory.search("c", "second version", k=5)
    assert len(hits) == 1
    assert hits[0].text == "second version"
