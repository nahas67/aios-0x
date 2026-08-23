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
from typing import Any

from pydantic import BaseModel, Field


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


class BaseVectorMemory(ABC):
    """Abstract semantic-memory boundary (Memory Model section 6)."""

    @abstractmethod
    def upsert(
        self, collection: str, doc_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Insert or replace one document."""

    @abstractmethod
    def search(self, collection: str, query_text: str, k: int = 5) -> list[VectorMatch]:
        """Top-k most similar documents (empty when collection unknown)."""


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

    def search(self, collection: str, query_text: str, k: int = 5) -> list[VectorMatch]:
        if not self._client.collection_exists(collection):
            return []
        hits = self._client.query_points(
            collection, query=self.embedder.embed(query_text), limit=k
        ).points
        return [
            VectorMatch(
                doc_id=str((hit.payload or {}).get("doc_id", hit.id)),
                score=round(float(hit.score or 0.0), 4),
                text=str((hit.payload or {}).get("text", "")),
                metadata=dict((hit.payload or {}).get("metadata", {})),
            )
            for hit in hits
        ]


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

    def search(self, collection: str, query_text: str, k: int = 5) -> list[VectorMatch]:
        store = self._collections.get(collection, {})
        if not store:
            return []
        qvec = self.embedder.embed(query_text)
        scored = [
            (doc_id, cosine(qvec, vec), text, meta) for doc_id, (vec, text, meta) in store.items()
        ]
        scored.sort(key=lambda t: t[1], reverse=True)
        return [
            VectorMatch(doc_id=d, score=round(s, 4), text=t, metadata=m)
            for d, s, t, m in scored[:k]
        ]
