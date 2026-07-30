"""Both backends, held to the same contract.

The in-memory store does exact cosine, so it doubles as the oracle: if Qdrant's
ranking ever diverges from it on this corpus, that is a bug worth knowing about.
Parametrising over both backends is what makes the interface claim real rather
than aspirational.
"""

from __future__ import annotations

import numpy as np
import pytest

from aidoctor.models.document import Chunk
from aidoctor.vectorstore.base import InMemoryVectorStore, VectorRecord
from aidoctor.vectorstore.qdrant_store import QdrantVectorStore, build_vector_store, point_id

DIMS = 32


def _chunk(cid: str, doc_id: str, text: str) -> Chunk:
    return Chunk(chunk_id=cid, doc_id=doc_id, text=text, ordinal=0, section_label="s", filename="f.md")


def _records(embedder) -> list[VectorRecord]:
    data = [
        ("c1", "d1", "password reset instructions for the console"),
        ("c2", "d1", "invoices include per-seat licence charges"),
        ("c3", "d2", "ERR_LOCK_TIMEOUT means the queue is saturated"),
    ]
    return [
        VectorRecord(chunk=_chunk(cid, doc, text), vector=embedder.embed_one(text)) for cid, doc, text in data
    ]


@pytest.fixture(params=["memory", "qdrant"])
def store(request):
    return build_vector_store(request.param, dimensions=DIMS, collection="contract")


@pytest.fixture()
def small_embedder():
    from aidoctor.embeddings.base import build_embedder

    return build_embedder("hashing", DIMS)


def test_upsert_then_count(store, small_embedder):
    store.upsert(_records(small_embedder))
    assert store.count() == 3


def test_upsert_is_idempotent(store, small_embedder):
    """Re-ingesting the same content must replace, not stack a second copy."""
    records = _records(small_embedder)
    store.upsert(records)
    store.upsert(records)
    assert store.count() == 3


def test_search_returns_the_relevant_chunk_first(store, small_embedder):
    store.upsert(_records(small_embedder))
    results = store.search(small_embedder.embed_one("how do I reset a password"), limit=3)
    assert results
    assert results[0].chunk.chunk_id == "c1"
    assert results[0].method == "dense"


def test_search_on_empty_store_returns_nothing(store, small_embedder):
    assert store.search(small_embedder.embed_one("anything"), limit=5) == []


def test_search_with_zero_vector_returns_nothing(store, small_embedder):
    store.upsert(_records(small_embedder))
    assert store.search(np.zeros(DIMS, dtype=np.float32), limit=3) == []


def test_delete_document_removes_only_that_document(store, small_embedder):
    store.upsert(_records(small_embedder))
    removed = store.delete_document("d1")
    assert removed == 2
    assert store.count() == 1
    assert {c.doc_id for c in store.all_chunks()} == {"d2"}


def test_delete_unknown_document_is_a_noop(store, small_embedder):
    store.upsert(_records(small_embedder))
    assert store.delete_document("nope") == 0
    assert store.count() == 3


def test_payload_round_trips_all_chunk_fields(store, small_embedder):
    store.upsert(_records(small_embedder))
    by_id = {c.chunk_id: c for c in store.all_chunks()}
    assert by_id["c2"].doc_id == "d1"
    assert by_id["c2"].section_label == "s"
    assert by_id["c2"].filename == "f.md"
    assert "licence" in by_id["c2"].text


def test_qdrant_and_memory_agree_on_ranking(small_embedder):
    """The exact store is the oracle for the approximate one."""
    records = _records(small_embedder)
    memory = InMemoryVectorStore()
    qdrant = QdrantVectorStore(dimensions=DIMS, collection="agree")
    memory.upsert(records)
    qdrant.upsert(records)
    query = small_embedder.embed_one("licence charges on the invoice")
    assert [r.chunk.chunk_id for r in memory.search(query, 3)] == [
        r.chunk.chunk_id for r in qdrant.search(query, 3)
    ]


def test_qdrant_point_ids_are_stable_uuids():
    """Chunk ids are 32-char hashes; Qdrant needs int or UUID. The mapping must be
    deterministic or upsert stops being idempotent."""
    first = point_id("abc123")
    assert first == point_id("abc123")
    assert first != point_id("abc124")
    assert len(first) == 36


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError, match="Unknown vector backend"):
        build_vector_store("pinecone", dimensions=DIMS)
