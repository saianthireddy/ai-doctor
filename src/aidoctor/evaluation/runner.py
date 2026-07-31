"""Running the labelled set against retrieval strategies.

Ablations exist so a component has to earn its place. Hybrid retrieval and
reranking are both defensible on paper; whether they help *this* corpus is a
question only a measurement answers, and the answer is allowed to be no.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from aidoctor.evaluation.dataset import EvalQuestion
from aidoctor.evaluation.metrics import (
    RefusalScores,
    RetrievalScores,
    score_retrieval,
)
from aidoctor.models.document import Chunk, ScoredChunk
from aidoctor.reranker.base import LexicalOverlapReranker
from aidoctor.retrieval.hybrid import HybridRetriever


class IndexTooSmall(Exception):
    """The index cannot support a meaningful ranking measurement."""


def section_key(chunk: Chunk) -> str:
    return f"{chunk.filename}#{chunk.section_label}"


def guard_index_size(retriever: HybridRetriever, depth: int) -> None:
    """Refuse to score when every query would return the whole index.

    With ``size <= depth`` the retriever returns everything for every query, so
    Recall@depth is 1.0 by arithmetic and Precision@1 is measuring a coin toss
    over a handful of chunks. Reporting those numbers would be worse than
    reporting nothing, because they look like evidence.
    """
    if retriever.size <= depth:
        raise IndexTooSmall(
            f"index holds {retriever.size} chunks but the harness ranks to depth "
            f"{depth}; every query would return the entire index and the scores "
            "would be arithmetic, not evidence. Expand the corpus first."
        )


Strategy = Callable[[str, int], list[ScoredChunk]]


@dataclass(frozen=True)
class Variant:
    name: str
    strategy: Strategy


def build_variants(retriever: HybridRetriever, rerank_depth: int = 20) -> list[Variant]:
    """The ablation grid: each retrieval mode, and hybrid with reranking."""
    reranker = LexicalOverlapReranker()

    def hybrid_reranked(query: str, limit: int) -> list[ScoredChunk]:
        candidates = retriever.search(query, limit=rerank_depth)
        return reranker.rerank(query, candidates, limit=limit)

    return [
        Variant("dense only", retriever.search_dense),
        Variant("lexical only (BM25)", retriever.search_lexical),
        Variant("hybrid (RRF)", retriever.search),
        Variant("hybrid + rerank", hybrid_reranked),
    ]


def rank_keys(strategy: Strategy, question: str, depth: int) -> list[str]:
    return [section_key(scored.chunk) for scored in strategy(question, depth)]


def evaluate_variant(variant: Variant, questions: list[EvalQuestion], depth: int = 10) -> RetrievalScores:
    answerable = [q for q in questions if q.answerable]
    results = [(rank_keys(variant.strategy, q.question, depth), set(q.relevant)) for q in answerable]
    return score_retrieval(results)


def evaluate_refusal(router_route: Callable[[str], object], questions: list[EvalQuestion]) -> RefusalScores:
    """Measure the refusal path end to end, through the router.

    ``false_answer_rate`` counts unanswerable questions that were answered
    anyway. ``wrongly_refused_rate`` is its opposite and is reported alongside
    on purpose: a system can drive false answers to zero by refusing
    everything, and one number without the other hides that.
    """
    answerable = [q for q in questions if q.answerable]
    unanswerable = [q for q in questions if not q.answerable]

    false_answers = 0
    for question in unanswerable:
        result = router_route(question.question)
        if not getattr(result, "escalated", False):
            false_answers += 1

    wrongly_refused = 0
    for question in answerable:
        result = router_route(question.question)
        if getattr(result, "escalated", False):
            wrongly_refused += 1

    return RefusalScores(
        answerable=len(answerable),
        unanswerable=len(unanswerable),
        false_answer_rate=false_answers / len(unanswerable) if unanswerable else 0.0,
        wrongly_refused_rate=wrongly_refused / len(answerable) if answerable else 0.0,
    )
