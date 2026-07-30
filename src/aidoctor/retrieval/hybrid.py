"""Hybrid retrieval via Reciprocal Rank Fusion.

The naive approach is to normalise the two score distributions and add them.
That is fragile: BM25 scores are unbounded and corpus-dependent while cosine sits
in [-1, 1], so any normalisation is really a hidden weighting that shifts as the
corpus grows.

RRF sidesteps it by discarding magnitudes and fusing *ranks*:
``score = sum(1 / (k + rank))``. A chunk both retrievers rank highly wins; one
that only appears in a single list still places if it ranks near the top there.
``k`` damps the influence of the very top position — the standard 60 is used, and
exposed rather than hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass

from aidoctor.embeddings.base import Embedder
from aidoctor.models.document import Chunk, ScoredChunk
from aidoctor.retrieval.lexical import BM25Index
from aidoctor.vectorstore.base import VectorRecord, VectorStore


@dataclass(frozen=True)
class RetrievalConfig:
    dense_k: int = 12
    lexical_k: int = 12
    final_k: int = 6
    rrf_k: int = 60
    dense_weight: float = 1.0
    lexical_weight: float = 1.0


def reciprocal_rank_fusion(
    ranked_lists: list[list[ScoredChunk]], weights: list[float], k: int = 60, limit: int = 6
) -> list[ScoredChunk]:
    fused: dict[str, float] = {}
    seen: dict[str, Chunk] = {}
    for results, weight in zip(ranked_lists, weights, strict=True):
        for rank, scored in enumerate(results, start=1):
            cid = scored.chunk.chunk_id
            fused[cid] = fused.get(cid, 0.0) + weight * (1.0 / (k + rank))
            seen.setdefault(cid, scored.chunk)
    ordered = sorted(fused.items(), key=lambda kv: -kv[1])
    return [ScoredChunk(chunk=seen[cid], score=score, method="hybrid") for cid, score in ordered[:limit]]


class HybridRetriever:
    """Owns both indexes so they cannot drift out of sync.

    Keeping the vector store and the BM25 index behind one ``index`` call is
    deliberate: two separate entry points is how a corpus ends up half-indexed,
    with lexical hits for chunks dense search cannot see.
    """

    def __init__(self, store: VectorStore, embedder: Embedder, config: RetrievalConfig | None = None) -> None:
        self.store = store
        self.embedder = embedder
        self.config = config or RetrievalConfig()
        self.lexical = BM25Index()

    def index(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        vectors = self.embedder.embed_many([c.text for c in chunks])
        self.store.upsert([VectorRecord(chunk=c, vector=v) for c, v in zip(chunks, vectors, strict=True)])
        self.lexical.index(chunks)
        return len(chunks)

    def delete_document(self, doc_id: str) -> int:
        removed = self.store.delete_document(doc_id)
        self.lexical.delete_document(doc_id)
        return removed

    def search(self, query: str, limit: int | None = None) -> list[ScoredChunk]:
        limit = limit or self.config.final_k
        dense = self.store.search(self.embedder.embed_one(query), limit=self.config.dense_k)
        lexical = self.lexical.search(query, limit=self.config.lexical_k)
        if not dense and not lexical:
            return []
        return reciprocal_rank_fusion(
            [dense, lexical],
            [self.config.dense_weight, self.config.lexical_weight],
            k=self.config.rrf_k,
            limit=limit,
        )

    def search_dense(self, query: str, limit: int = 6) -> list[ScoredChunk]:
        return self.store.search(self.embedder.embed_one(query), limit=limit)

    def search_lexical(self, query: str, limit: int = 6) -> list[ScoredChunk]:
        return self.lexical.search(query, limit=limit)

    @property
    def size(self) -> int:
        return self.store.count()
