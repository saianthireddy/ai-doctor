"""Qdrant backend.

Uses ``QdrantClient(location=":memory:")`` by default, which is Qdrant's genuine
embedded mode — the same client and query path as a server, with no service to
run. That is what makes this backend testable in CI rather than mocked, and it is
why the tests can assert that Qdrant and the in-memory reference store return the
same ranking.

Point ids: Qdrant requires an unsigned integer or a UUID, but our chunk ids are
32-char content hashes. They are converted to UUIDs deterministically, so the
same chunk always lands on the same point and upsert stays idempotent. The
original id is kept in the payload, because that is what the rest of the system
uses.
"""

from __future__ import annotations

import uuid

import numpy as np

from aidoctor.models.document import Chunk, ScoredChunk
from aidoctor.vectorstore.base import VectorRecord

_NAMESPACE = uuid.UUID("6f1a9d1e-6d5e-4f4a-9a9a-2f0b8c7d4e11")


def point_id(chunk_id: str) -> str:
    """Stable UUID for a content-hash chunk id."""
    return str(uuid.uuid5(_NAMESPACE, chunk_id))


class QdrantVectorStore:
    name = "qdrant"

    def __init__(
        self,
        dimensions: int,
        collection: str = "aidoctor",
        location: str = ":memory:",
        url: str | None = None,
    ) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("qdrant-client is required for the Qdrant backend") from exc

        self.dimensions = dimensions
        self.collection = collection
        self._client = QdrantClient(url=url) if url else QdrantClient(location=location)
        existing = {c.name for c in self._client.get_collections().collections}
        if collection not in existing:
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
            )

    def upsert(self, records: list[VectorRecord]) -> None:
        from qdrant_client.models import PointStruct

        if not records:
            return
        points = [
            PointStruct(
                id=point_id(r.chunk.chunk_id),
                vector=[float(x) for x in r.vector],
                payload={
                    "chunk_id": r.chunk.chunk_id,
                    "doc_id": r.chunk.doc_id,
                    "text": r.chunk.text,
                    "ordinal": r.chunk.ordinal,
                    "section_label": r.chunk.section_label,
                    "filename": r.chunk.filename,
                },
            )
            for r in records
        ]
        self._client.upsert(collection_name=self.collection, points=points)

    @staticmethod
    def _to_chunk(payload: dict) -> Chunk:
        return Chunk(
            chunk_id=payload["chunk_id"],
            doc_id=payload["doc_id"],
            text=payload["text"],
            ordinal=int(payload.get("ordinal", 0)),
            section_label=payload.get("section_label", ""),
            filename=payload.get("filename", ""),
        )

    def search(self, vector: np.ndarray, limit: int = 8) -> list[ScoredChunk]:
        if self.count() == 0:
            return []
        # A zero query vector carries no signal, and cosine against it is
        # undefined. Qdrant will still return *something*; the in-memory
        # reference store returns nothing. Both backends must honour the same
        # contract or the interface is a fiction, so refuse here too.
        if not float(np.linalg.norm(vector)):
            return []
        result = self._client.query_points(
            collection_name=self.collection,
            query=[float(x) for x in vector],
            limit=limit,
            with_payload=True,
        )
        return [
            ScoredChunk(chunk=self._to_chunk(p.payload), score=float(p.score), method="dense")
            for p in result.points
        ]

    def delete_document(self, doc_id: str) -> int:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        condition = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
        before = self.count()
        self._client.delete(collection_name=self.collection, points_selector=FilterSelector(filter=condition))
        return before - self.count()

    def count(self) -> int:
        return int(self._client.count(collection_name=self.collection).count)

    def all_chunks(self) -> list[Chunk]:
        points, _ = self._client.scroll(collection_name=self.collection, limit=10_000, with_payload=True)
        return [self._to_chunk(p.payload) for p in points]


def build_vector_store(backend: str, dimensions: int, **kwargs):
    from aidoctor.vectorstore.base import InMemoryVectorStore

    if backend == "memory":
        return InMemoryVectorStore()
    if backend == "qdrant":
        return QdrantVectorStore(dimensions=dimensions, **kwargs)
    raise ValueError(f"Unknown vector backend {backend!r}. Available: memory, qdrant")
