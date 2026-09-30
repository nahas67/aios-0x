"""Vector memory boundary + Qdrant local-mode adapter (Phase 2.0 completion).

Implements the Doc 16 zero-lock-in rule for vector storage:
- BaseVectorMemory ABC: upsert / search over named collections.
- QdrantLocalMemory: real Qdrant engine running in local in-process mode
  (no server deployment required).

Embeddings use a deterministic hashing embedder (feature hashing, L2-
normalized). This is an honest PLACEHOLDER until a real embedding model is
selected - Doc 09's 384-vs-768 dimension conflict stays unresolved until then,
and semantic quality is correspondingly limited. The interface accepts any
embedder, so swapping in a licensed model is adapter-only.
"""

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

#: Salience function injected into search: metadata in, score or None
#: (exclude) out. Lives here so both store implementations share one type
#: without importing the tier definitions that implement it.
SalienceFunction = Callable[[dict[str, Any]], float | None]


class VectorMatch(BaseModel):
    doc_id: str
    score: float = Field(ge=-1.0, le=1.0)
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Embedder(ABC):
    dims: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Deterministic embedding vector for a text."""


class HashingEmbedder(Embedder):
    """Feature-hashing embedder: deterministic, dependency-free placeholder."""

    _TOKEN_RE = re.compile(r"[a-z0-9]+")

    def __init__(self, dims: int = 256) -> None:
        self.dims = dims

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dims
        for token in self._TOKEN_RE.findall(text.lower()):
            digest = hashlib.md5(token.encode()).digest()
            index = int.from_bytes(digest[:4], "little") % self.dims
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[index] += sign
            # bigram-ish second projection for mild context sensitivity
            index2 = int.from_bytes(digest[5:9], "little") % self.dims
            vec[index2] += sign * 0.5
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


#: Fraction of the blended score coming from similarity; the rest is
#: salience. Recorded on every blended match so the ranking is reproducible
#: from the match alone. Fixed rather than tunable per call because a weight
#: that varies per query is a ranking policy nobody versioned.
BLEND_SIMILARITY_WEIGHT = 0.7


def blend_with_salience(
    matches: list[VectorMatch],
    saliences: list[float | None],
    *,
    weight: float = BLEND_SIMILARITY_WEIGHT,
) -> list[VectorMatch]:
    """Re-rank similarity matches by tier salience. Pure function.

    ``saliences[i]`` is the salience of ``matches[i]`` or ``None`` to exclude
    it (expired). Surviving saliences are min-max normalized over the
    candidate set — salience is meaningful only relative to what it competed
    against — then combined as ``weight * similarity + (1 - weight) *
    norm``. The convex combination stays inside [-1, 1] whenever both inputs
    do, so the score bound the model promises still holds. Each surviving
    match records its similarity, salience, and blend weight in metadata, so
    the ranking is auditable without re-running the search.
    """
    if len(matches) != len(saliences):
        raise ValueError(
            f"{len(matches)} matches but {len(saliences)} saliences: a blend "
            "over a misaligned pairing ranks documents by someone else's score"
        )
    scored = [
        (match, salience)
        for match, salience in zip(matches, saliences, strict=True)
        if salience is not None
    ]
    if not scored:
        return []
    values = [salience for _, salience in scored]
    lo, hi = min(values), max(values)
    blended: list[tuple[float, VectorMatch]] = []
    for match, salience in scored:
        norm = 1.0 if hi <= lo else (salience - lo) / (hi - lo)
        combined = weight * match.score + (1.0 - weight) * norm
        blended.append(
            (
                combined,
                match.model_copy(
                    update={
                        "score": round(combined, 4),
                        "metadata": {
                            **match.metadata,
                            "similarity": match.score,
                            "salience": salience,
                            "blend_weight": weight,
                        },
                    }
                ),
            )
        )
    blended.sort(key=lambda pair: pair[0], reverse=True)
    return [match for _, match in blended]


class BaseVectorMemory(ABC):
    """Abstract semantic-memory boundary (Memory Model section 6)."""

    @abstractmethod
    def upsert(
        self, collection: str, doc_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Insert or replace one document."""

    @abstractmethod
    def search(
        self,
        collection: str,
        query_text: str,
        k: int = 5,
        *,
        now: float | None = None,
        salience: SalienceFunction | None = None,
        blend_pool: int = 5,
    ) -> list[VectorMatch]:
        """Top-k documents, by similarity alone unless ``salience`` is given.

        ``salience`` is a callable over a match's metadata returning a score
        or ``None`` to exclude it (expired). Injected rather than imported so
        this module never depends on the tier definitions: the caller owns
        the policy, the store owns the arithmetic. ``blend_pool`` oversamples
        candidates before blending so expired documents do not eat result
        slots; ``now`` is explicit because a recall timestamp that comes from
        a wall clock inside the store is unrepeatable.
        """


class QdrantLocalMemory(BaseVectorMemory):
    """Real Qdrant engine in local in-process mode (no server)."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.embedder = embedder or HashingEmbedder()
        self._client = QdrantClient(":memory:")
        self._distance = Distance.COSINE
        self._vector_params = VectorParams(size=self.embedder.dims, distance=self._distance)

    def _ensure(self, collection: str) -> None:
        if not self._client.collection_exists(collection):
            self._client.create_collection(collection, vectors_config=self._vector_params)

    def upsert(
        self, collection: str, doc_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        import uuid as _uuid

        from qdrant_client.models import PointStruct

        self._ensure(collection)
        # Qdrant requires UUID/int point ids; map deterministically and keep
        # the caller's id in both payload and returned matches.
        point_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"aios:{collection}:{doc_id}"))
        self._client.upsert(
            collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector=self.embedder.embed(text),
                    payload={"doc_id": str(doc_id), "text": text, "metadata": metadata or {}},
                )
            ],
        )

    def search(
        self,
        collection: str,
        query_text: str,
        k: int = 5,
        *,
        now: float | None = None,
        salience: SalienceFunction | None = None,
        blend_pool: int = 5,
    ) -> list[VectorMatch]:
        if not self._client.collection_exists(collection):
            return []
        limit = k if salience is None else max(k, 1) * max(blend_pool, 1)
        hits = self._client.query_points(
            collection, query=self.embedder.embed(query_text), limit=limit
        ).points
        matches = [
            VectorMatch(
                doc_id=str((hit.payload or {}).get("doc_id", hit.id)),
                score=round(float(hit.score or 0.0), 4),
                text=str((hit.payload or {}).get("text", "")),
                metadata=dict((hit.payload or {}).get("metadata", {})),
            )
            for hit in hits
        ]
        if salience is None:
            return matches[:k]
        return blend_with_salience(
            matches, [salience(match.metadata) for match in matches]
        )[:k]


class InMemoryVectorMemory(BaseVectorMemory):
    """Pure-python fallback implementing the identical contract."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or HashingEmbedder()
        self._collections: dict[str, dict[str, tuple[list[float], str, dict[str, Any]]]] = {}

    def upsert(
        self, collection: str, doc_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        store = self._collections.setdefault(collection, {})
        store[str(doc_id)] = (self.embedder.embed(text), text, metadata or {})

    def search(
        self,
        collection: str,
        query_text: str,
        k: int = 5,
        *,
        now: float | None = None,
        salience: SalienceFunction | None = None,
        blend_pool: int = 5,
    ) -> list[VectorMatch]:
        store = self._collections.get(collection, {})
        if not store:
            return []
        # now and blend_pool are accepted for signature parity: this backend
        # scans the whole collection, so there is nothing to oversample, and
        # the salience callable receives what it needs through metadata.
        qvec = self.embedder.embed(query_text)
        scored = [
            (doc_id, cosine(qvec, vec), text, meta) for doc_id, (vec, text, meta) in store.items()
        ]
        scored.sort(key=lambda t: t[1], reverse=True)
        matches = [
            VectorMatch(doc_id=d, score=round(s, 4), text=t, metadata=m)
            for d, s, t, m in scored
        ]
        if salience is None:
            return matches[:k]
        return blend_with_salience(
            matches, [salience(match.metadata) for match in matches]
        )[:k]
