"""Lexical, dense and hybrid retrieval, plus the fusion itself."""

from __future__ import annotations

from aidoctor.models.document import Chunk, ScoredChunk
from aidoctor.retrieval.hybrid import HybridRetriever, RetrievalConfig, reciprocal_rank_fusion
from aidoctor.retrieval.lexical import BM25Index, stem
from aidoctor.services.chunker import chunk_document
from aidoctor.vectorstore.qdrant_store import build_vector_store


def _chunk(cid: str, text: str, label: str = "s", doc: str = "d") -> Chunk:
    return Chunk(chunk_id=cid, doc_id=doc, text=text, ordinal=0, section_label=label, filename="f.md")


# ------------------------------------------------------------------- BM25


def test_bm25_finds_an_exact_token_a_dense_model_would_smear():
    index = BM25Index()
    index.index(
        [
            _chunk("1", "ERR_LOCK_TIMEOUT indicates the queue is saturated", "Troubleshooting"),
            _chunk("2", "Invoices are issued monthly", "Billing"),
        ]
    )
    results = index.search("ERR_LOCK_TIMEOUT")
    assert results and results[0].chunk.chunk_id == "1"
    assert results[0].method == "lexical"


def test_stemming_matches_plural_and_verb_forms():
    """Observed failure before stemming: "charged for seats" returned nothing
    against text saying "per-seat licence charges"."""
    index = BM25Index()
    index.index([_chunk("1", "Invoices include per-seat licence charges.", "Billing")])
    assert index.search("how am I charged for seats")


def test_stemmer_leaves_short_tokens_and_codes_alone():
    assert stem("seat") == "seat"
    assert stem("err_lock_timeout") == "err_lock_timeout"
    assert stem("seats") == "seat"


def test_reindexing_a_chunk_does_not_double_document_frequency():
    index = BM25Index()
    chunk = _chunk("1", "licence charges apply")
    index.index([chunk])
    index.index([chunk])
    assert index.size == 1


def test_bm25_delete_document():
    index = BM25Index()
    index.index([_chunk("1", "alpha", doc="d1"), _chunk("2", "beta", doc="d2")])
    assert index.delete_document("d1") == 1
    assert index.size == 1


def test_bm25_empty_query_and_empty_index():
    index = BM25Index()
    assert index.search("anything") == []
    index.index([_chunk("1", "content")])
    assert index.search("") == []


# --------------------------------------------------------------------- RRF


def test_rrf_rewards_agreement_between_the_two_retrievers():
    shared = _chunk("shared", "in both lists")
    dense = [ScoredChunk(shared, 0.9, "dense"), ScoredChunk(_chunk("d2", "dense only"), 0.8, "dense")]
    lexical = [ScoredChunk(_chunk("l1", "lexical only"), 5.0, "lexical"), ScoredChunk(shared, 4.0, "lexical")]
    fused = reciprocal_rank_fusion([dense, lexical], [1.0, 1.0], k=60, limit=3)
    assert fused[0].chunk.chunk_id == "shared"
    assert fused[0].method == "hybrid"


def test_rrf_ignores_raw_score_magnitude():
    """BM25 scores are unbounded and cosine is in [-1,1]; fusing ranks avoids
    inventing a weighting that shifts as the corpus grows."""
    a = _chunk("a", "a")
    b = _chunk("b", "b")
    huge = [ScoredChunk(a, 999.0, "lexical"), ScoredChunk(b, 998.0, "lexical")]
    tiny = [ScoredChunk(a, 0.002, "dense"), ScoredChunk(b, 0.001, "dense")]
    assert [c.chunk.chunk_id for c in reciprocal_rank_fusion([huge], [1.0], limit=2)] == [
        c.chunk.chunk_id for c in reciprocal_rank_fusion([tiny], [1.0], limit=2)
    ]


def test_rrf_handles_one_empty_list():
    only = [ScoredChunk(_chunk("a", "a"), 1.0, "dense")]
    assert len(reciprocal_rank_fusion([only, []], [1.0, 1.0], limit=5)) == 1


def test_rrf_weights_shift_the_balance():
    a, b = _chunk("a", "a"), _chunk("b", "b")
    dense = [ScoredChunk(a, 1.0, "dense")]
    lexical = [ScoredChunk(b, 1.0, "lexical")]
    dense_first = reciprocal_rank_fusion([dense, lexical], [5.0, 1.0], limit=2)
    lexical_first = reciprocal_rank_fusion([dense, lexical], [1.0, 5.0], limit=2)
    assert dense_first[0].chunk.chunk_id == "a"
    assert lexical_first[0].chunk.chunk_id == "b"


# ---------------------------------------------------------------- retriever


def _retriever(embedder, handbook):
    retriever = HybridRetriever(
        build_vector_store("qdrant", dimensions=embedder.dimensions, collection="retr"),
        embedder,
        RetrievalConfig(final_k=3),
    )
    retriever.index(chunk_document(handbook))
    return retriever


def test_indexing_populates_both_indexes(embedder, handbook):
    retriever = _retriever(embedder, handbook)
    assert retriever.size == 3
    assert retriever.lexical.size == 3


def test_hybrid_beats_neither_on_a_natural_question(embedder, handbook):
    retriever = _retriever(embedder, handbook)
    results = retriever.search("how do I reset my password")
    assert results
    assert results[0].chunk.section_label == "Password reset"


def test_exact_code_is_found(embedder, handbook):
    retriever = _retriever(embedder, handbook)
    assert retriever.search("ERR_LOCK_TIMEOUT")[0].chunk.section_label == "Troubleshooting"


def test_dense_and_lexical_modes_are_separately_reachable(embedder, handbook):
    retriever = _retriever(embedder, handbook)
    assert retriever.search_dense("password", limit=2)[0].method == "dense"
    assert retriever.search_lexical("password", limit=2)[0].method == "lexical"


def test_delete_document_clears_both_indexes(embedder, handbook):
    retriever = _retriever(embedder, handbook)
    retriever.delete_document("handbook")
    assert retriever.size == 0
    assert retriever.lexical.search("password") == []


def test_indexing_nothing_is_safe(embedder, handbook):
    retriever = _retriever(embedder, handbook)
    assert retriever.index([]) == 0
