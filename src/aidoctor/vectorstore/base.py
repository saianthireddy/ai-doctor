"""Vector store interface plus a dependency-free in-memory implementation.

The interface is deliberately five methods. Anything wider and swapping backends
stops being a config change; anything narrower and the retriever has to reach
around it.

``upsert`` rather than ``add`` is load-bearing: re-ingesting a document must
replace its chunks, not stack a second copy beside them. Chunk ids are derived
from content, so upsert semantics make re-ingest idempotent by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from aidoctor.models.document import Chunk, ScoredChunk


@dataclass(frozen=True)
class VectorRecord:
    chunk: Chunk
    vector: np.ndarray


class VectorStore(Protocol):
    name: str

    def upsert(self, records: list[VectorRecord]) -> None: ...

    def search(self, vector: np.ndarray, limit: int = 8) -> list[ScoredChunk]: ...

    def delete_document(self, doc_id: str) -> int: ...

    def count(self) -> int: ...

    def all_chunks(self) -> list[Chunk]: ...


class InMemoryVectorStore:
    """Exact cosine search over a dict. The reference implementation.

    Brute force is the right choice at this scale and, more usefully, it is
    *exact* — so it doubles as the oracle that the Qdrant backend is tested
    against. An approximate index that silently disagreed with this would be a
    bug worth catching.
    """

    name = "memory"

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        for record in records:
            self._records[record.chunk.chunk_id] = record

    def search(self, vector: np.ndarray, limit: int = 8) -> list[ScoredChunk]:
        if not self._records:
            return []
        norm = float(np.linalg.norm(vector))
        if not norm:
            return []
        query = vector / norm
        scored: list[ScoredChunk] = []
        for record in self._records.values():
            candidate_norm = float(np.linalg.norm(record.vector))
            score = float(query @ (record.vector / candidate_norm)) if candidate_norm else 0.0
            scored.append(ScoredChunk(chunk=record.chunk, score=score, method="dense"))
        scored.sort(key=lambda s: -s.score)
        return scored[:limit]

    def delete_document(self, doc_id: str) -> int:
        stale = [cid for cid, rec in self._records.items() if rec.chunk.doc_id == doc_id]
        for cid in stale:
            del self._records[cid]
        return len(stale)

    def count(self) -> int:
        return len(self._records)

    def all_chunks(self) -> list[Chunk]:
        return [r.chunk for r in self._records.values()]
