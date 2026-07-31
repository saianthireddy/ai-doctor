"""The refusal path is the feature; most of these tests are about not answering."""

from __future__ import annotations

import pytest

from aidoctor.agents.router import ANSWER, INVENTORY, LOOKUP, SUMMARISE, Router, classify
from aidoctor.llms.base import ExtractiveLLM, build_llm
from aidoctor.models.document import Chunk, ScoredChunk
from aidoctor.reranker.base import RerankerUnavailable, build_reranker
from aidoctor.retrieval.hybrid import HybridRetriever
from aidoctor.services.answerer import REFUSAL, Answerer
from aidoctor.services.chunker import chunk_document
from aidoctor.vectorstore.qdrant_store import build_vector_store


def _stack(embedder, handbook, **kwargs):
    retriever = HybridRetriever(
        build_vector_store("qdrant", dimensions=embedder.dimensions, collection="ans"), embedder
    )
    retriever.index(chunk_document(handbook))
    answerer = Answerer(retriever, build_reranker("lexical-overlap"), build_llm("extractive"), **kwargs)
    return retriever, answerer


# --------------------------------------------------------------- answering


def test_in_corpus_question_is_answered_with_a_citation(embedder, handbook):
    _, answerer = _stack(embedder, handbook)
    answer = answerer.answer("how do I reset my password")
    assert not answer.escalated
    assert answer.grounded
    assert answer.citations
    assert "handbook.md" in answer.citations[0]
    assert "Reset Password" in answer.text


def test_answer_text_comes_only_from_retrieved_passages(embedder, handbook):
    """The extractive generator cannot hallucinate: every sentence it emits must
    appear in a retrieved chunk."""
    _, answerer = _stack(embedder, handbook)
    answer = answerer.answer("what does ERR_LOCK_TIMEOUT mean")

    # The generator collapses whitespace (a section is "Heading\nBody"), so compare
    # whitespace-normalised forms. The claim under test is that no *content* is
    # invented, not that newlines survive.
    def norm(text: str) -> str:
        return " ".join(text.split())

    corpus = norm(" ".join(p.chunk.text for p in answer.passages))
    for sentence in answer.text.split(". "):
        stripped = norm(sentence).strip(" .")
        if len(stripped) > 20:
            assert stripped in corpus, f"not traceable to a passage: {stripped!r}"


def test_out_of_corpus_question_is_refused(embedder, handbook):
    """Regression: stopword overlap ("what is the ... of an ...") used to clear
    the relevance floor and produce a confident, irrelevant answer."""
    _, answerer = _stack(embedder, handbook)
    for question in [
        "what is the airspeed velocity of an unladen swallow",
        "who won the 1998 world cup",
        "what is the capital of Peru",
    ]:
        answer = answerer.answer(question)
        assert answer.escalated, f"should have refused: {question}"
        assert answer.text == REFUSAL
        assert not answer.citations


def test_blank_question_is_refused(embedder, handbook):
    _, answerer = _stack(embedder, handbook)
    assert answerer.answer("   ").escalated


def test_empty_index_refuses_everything(embedder, handbook):
    retriever = HybridRetriever(build_vector_store("memory", dimensions=embedder.dimensions), embedder)
    answerer = Answerer(retriever, build_reranker("lexical-overlap"), build_llm("extractive"))
    assert answerer.answer("anything at all").escalated


def test_raising_the_floor_refuses_more(embedder, handbook):
    _, strict = _stack(embedder, handbook, min_score=0.95)
    assert strict.answer("how do I reset my password").escalated


def test_confidence_is_reported_and_ordered(embedder, handbook):
    _, answerer = _stack(embedder, handbook)
    good = answerer.answer("how do I reset my password")
    bad = answerer.answer("who won the world cup")
    assert good.confidence > bad.confidence


# ----------------------------------------------------------------- reranker


def test_reranker_promotes_full_coverage_over_a_single_rare_term():
    candidates = [
        ScoredChunk(Chunk("a", "d", "Queue depth affects latency.", 0, "Perf", "f.md"), 0.9, "hybrid"),
        ScoredChunk(
            Chunk("b", "d", "Password reset emails go to the registered address.", 0, "Reset", "f.md"),
            0.5,
            "hybrid",
        ),
    ]
    reranked = build_reranker("lexical-overlap").rerank("how do I reset my password", candidates, 2)
    assert reranked[0].chunk.chunk_id == "b"
    assert reranked[0].method == "reranked"


def test_reranker_scores_zero_when_no_content_term_matches():
    """The rank prior alone must not carry an irrelevant passage over a threshold."""
    candidates = [
        ScoredChunk(Chunk("a", "d", "Queue depth affects latency.", 0, "Perf", "f.md"), 0.9, "hybrid")
    ]
    assert build_reranker("lexical-overlap").rerank("capital of Peru", candidates, 1)[0].score == 0.0


def test_noop_reranker_preserves_order():
    candidates = [
        ScoredChunk(Chunk("a", "d", "x", 0, "A", "f"), 0.9, "hybrid"),
        ScoredChunk(Chunk("b", "d", "y", 0, "B", "f"), 0.1, "hybrid"),
    ]
    assert [c.chunk.chunk_id for c in build_reranker("none").rerank("q", candidates, 2)] == ["a", "b"]


def test_reranker_handles_empty_candidates():
    assert build_reranker("lexical-overlap").rerank("q", [], 3) == []


def test_stopword_only_query_preserves_retriever_order():
    candidates = [ScoredChunk(Chunk("a", "d", "x", 0, "A", "f"), 0.9, "hybrid")]
    assert build_reranker("lexical-overlap").rerank("the of and", candidates, 1)[0].chunk.chunk_id == "a"


# ------------------------------------------------------------------- router


def test_classification_is_most_specific_first():
    assert classify("what documents do you have") == INVENTORY
    assert classify("summarise the billing policy") == SUMMARISE
    assert classify("ERR_LOCK_TIMEOUT") == LOOKUP
    assert classify("how do I reset my password") == ANSWER


def test_router_reports_which_handler_ran(embedder, handbook):
    _, answerer = _stack(embedder, handbook)
    router = Router(answerer, inventory=lambda: ["handbook.md"])
    assert router.route("how do I reset my password").handler == "grounded-answer"
    assert router.route("ERR_LOCK_TIMEOUT").handler == "exact-lookup"
    assert router.route("summarise billing").handler == "summariser"
    assert router.route("what documents do you have").handler == "inventory"


def test_inventory_handler_lists_documents(embedder, handbook):
    _, answerer = _stack(embedder, handbook)
    router = Router(answerer, inventory=lambda: ["a.pdf", "b.docx"])
    result = router.route("which documents do you have")
    assert "a.pdf" in result.text and "b.docx" in result.text
    assert not result.escalated


def test_inventory_handler_says_so_when_empty(embedder, handbook):
    _, answerer = _stack(embedder, handbook)
    result = Router(answerer, inventory=lambda: []).route("what files do you have")
    assert result.escalated
    assert "No documents" in result.text


def test_router_restores_context_k_after_widening(embedder, handbook):
    """The summariser temporarily widens the context window; leaking that would
    silently change every later answer."""
    _, answerer = _stack(embedder, handbook)
    before = answerer.context_k
    Router(answerer).route("summarise everything")
    assert answerer.context_k == before


# --------------------------------------------------------------------- llm


def test_extractive_llm_returns_nothing_without_passages():
    assert not ExtractiveLLM().complete("q", []).grounded


def test_extractive_llm_caps_sentence_count():
    chunk = Chunk("a", "d", " ".join(f"Sentence number {i} about passwords." for i in range(10)), 0, "S", "f")
    completion = ExtractiveLLM(max_sentences=2).complete("passwords", [ScoredChunk(chunk, 1.0, "hybrid")])
    assert completion.text.count("Sentence number") <= 2


# ----------------------------------------------------------- optional extras


def test_choosing_the_cross_encoder_without_its_extra_fails_immediately():
    """Fail at construction, not on the first user query.

    The import is lazy so the package stays installable without torch. Without
    this check a missing dependency surfaced as a bare ModuleNotFoundError from
    inside a reranking call — after startup had already reported healthy. Every
    other optional dependency here fails loudly at its boundary; this one now
    does too.
    """
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        pass
    else:  # pragma: no cover - only when the extra is installed
        pytest.skip("sentence-transformers is installed; nothing to guard")

    with pytest.raises(RerankerUnavailable) as exc:
        build_reranker("cross-encoder")
    assert "ai-doctor[rerank]" in str(exc.value)


def test_an_unknown_reranker_name_is_rejected():
    with pytest.raises(ValueError, match="Unknown reranker"):
        build_reranker("magic")
