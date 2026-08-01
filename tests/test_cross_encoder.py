"""The real cross-encoder, with the real model.

Skipped unless ``sentence-transformers`` is installed, so the default offline
run stays fast and dependency-light. CI installs the ``[rerank]`` extra and
downloads the model, which is what lets this row claim ✅ rather than 🟡.

The assertions are behavioural, not "it imported". A cross-encoder that loads
and then ranks an irrelevant passage first is broken, and a test that only
checks the object exists would not notice.
"""

from __future__ import annotations

import pytest

from aidoctor.models.document import Chunk, ScoredChunk

pytest.importorskip(
    "sentence_transformers",
    reason="the [rerank] extra is not installed; CI installs it and runs this",
)

from aidoctor.reranker.base import CrossEncoderReranker  # noqa: E402


def _candidate(chunk_id: str, text: str, score: float = 0.5) -> ScoredChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
        doc_id="d",
        text=text,
        ordinal=0,
        section_label="s",
        filename="f.md",
    )
    return ScoredChunk(chunk=chunk, score=score, method="hybrid")


@pytest.fixture(scope="module")
def reranker():
    """One model load for the module; the download is the slow part."""
    return CrossEncoderReranker()


def test_it_promotes_the_passage_that_actually_answers_the_question(reranker):
    """The point of a cross-encoder: judge the pair, not two summaries.

    Retrieval hands these over in the wrong order on purpose — the irrelevant
    passage arrives with the higher upstream score.
    """
    candidates = [
        _candidate("wrong", "Annual leave is twenty five days plus public holidays.", 0.9),
        _candidate("right", "To reset your password open Settings and choose Reset Password.", 0.4),
    ]
    ranked = reranker.rerank("how do I reset my password", candidates, limit=2)
    assert ranked[0].chunk.chunk_id == "right"
    assert ranked[0].score > ranked[1].score


def test_it_separates_a_near_miss_from_the_real_answer(reranker):
    """The case the lexical floor cannot handle.

    Both passages are about leave and share vocabulary. Only one answers the
    question asked. This is the failure documented in docs/evaluation.md, and
    it is the reason to want a cross-encoder at all.
    """
    candidates = [
        _candidate("annual", "Annual leave is twenty five days plus public holidays."),
        _candidate("parental", "Parental leave is twenty six weeks at full pay."),
    ]
    ranked = reranker.rerank("what is the parental leave policy", candidates, limit=2)
    assert ranked[0].chunk.chunk_id == "parental"


def test_reranking_marks_its_output_and_respects_the_limit(reranker):
    candidates = [_candidate(str(i), f"passage number {i} about billing") for i in range(5)]
    ranked = reranker.rerank("billing", candidates, limit=2)
    assert len(ranked) == 2
    assert all(r.method == "reranked" for r in ranked)


def test_no_candidates_returns_nothing_without_loading_anything(reranker):
    assert reranker.rerank("anything", [], limit=3) == []


def test_scores_are_ordered_descending(reranker):
    candidates = [
        _candidate("a", "invoices include per-seat licence charges"),
        _candidate("b", "restart the worker pool to clear the queue"),
        _candidate("c", "annual leave is twenty five days"),
    ]
    ranked = reranker.rerank("how am I billed for seats", candidates, limit=3)
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ranked[0].chunk.chunk_id == "a"
