"""The harness itself, and the property that makes its numbers worth anything.

The central test here is ``test_the_benchmark_can_fail``. A benchmark that
cannot fail cannot detect a regression either, and the failure mode is quiet:
the numbers look excellent and mean nothing. So a deliberately broken retriever
is scored alongside the real one and must come out materially worse.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aidoctor.evaluation.dataset import (
    DatasetError,
    load_questions,
    validate_against,
)
from aidoctor.evaluation.metrics import score_retrieval
from aidoctor.evaluation.runner import (
    IndexTooSmall,
    Variant,
    evaluate_variant,
    guard_index_size,
    section_key,
)
from aidoctor.models.document import Chunk, ScoredChunk

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "examples" / "corpus"
QUESTIONS = ROOT / "examples" / "evaluation" / "questions.json"
DEPTH = 10


@pytest.fixture(scope="module")
def indexed():
    """Ingest the real sample corpus once for the whole module."""
    from aidoctor.api.dependencies import build_container
    from aidoctor.config.settings import Settings

    container = build_container(
        Settings(
            database_url="sqlite:///:memory:",
            embedding_dimensions=384,
            qdrant_collection="test-eval",
        )
    )
    for path in sorted(CORPUS.iterdir()):
        if path.is_file():
            container.ingest.ingest_path(path)
    return container


def test_corpus_is_larger_than_the_ranking_depth(indexed):
    """The precondition for the whole measurement.

    This is the check that was missing when the corpus held 8 chunks against a
    candidate_k of 12: every query returned the entire index, so Recall@k was
    1.0 as a matter of arithmetic.
    """
    assert indexed.retriever.size > DEPTH * 2


def test_guard_refuses_to_score_a_too_small_index(indexed):
    with pytest.raises(IndexTooSmall):
        guard_index_size(indexed.retriever, depth=indexed.retriever.size)


def test_guard_allows_a_large_enough_index(indexed):
    guard_index_size(indexed.retriever, depth=DEPTH)


def test_every_label_names_a_section_that_exists(indexed):
    """Catches labels left behind when a document is edited."""
    questions = load_questions(QUESTIONS)
    available = {section_key(c) for c in indexed.retriever.store.all_chunks()}
    validate_against(questions, available)


def test_a_label_for_a_missing_section_is_an_error():
    questions = load_questions(QUESTIONS)
    with pytest.raises(DatasetError):
        validate_against(questions, {"nothing.md#Nowhere"})


def test_dataset_has_both_answerable_and_unanswerable_questions():
    questions = load_questions(QUESTIONS)
    answerable = [q for q in questions if q.answerable]
    unanswerable = [q for q in questions if not q.answerable]
    assert len(answerable) >= 40
    # Without unanswerable questions the false-answer rate is undefined, and
    # refusal is the behaviour this project most wants to be judged on.
    assert len(unanswerable) >= 5


def test_duplicate_question_ids_are_rejected(tmp_path):
    path = tmp_path / "dupes.json"
    path.write_text(
        json.dumps(
            {
                "questions": [
                    {"id": "q1", "question": "a", "relevant": []},
                    {"id": "q1", "question": "b", "relevant": []},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DatasetError):
        load_questions(path)


def test_the_benchmark_can_fail(indexed):
    """A saboteur retriever must score materially worse than the real one.

    If the corpus were too small, or the labels wrong, or the metrics broken,
    these two would score the same — and that equality is the signal that the
    benchmark is measuring nothing.
    """
    questions = load_questions(QUESTIONS)
    real = Variant("hybrid", indexed.retriever.search)

    all_chunks = sorted(indexed.retriever.store.all_chunks(), key=lambda c: c.chunk_id)

    def saboteur(query: str, limit: int) -> list[ScoredChunk]:
        # Ignores the query entirely: returns the same arbitrary chunks every
        # time. Any real retriever must beat this.
        return [ScoredChunk(chunk=chunk, score=0.0, method="saboteur") for chunk in all_chunks[:limit]]

    real_scores = evaluate_variant(real, questions, depth=DEPTH)
    broken_scores = evaluate_variant(Variant("saboteur", saboteur), questions, depth=DEPTH)

    assert real_scores.mrr > broken_scores.mrr + 0.3
    assert real_scores.precision_at_1 > broken_scores.precision_at_1 + 0.3


def test_reranking_beats_plain_hybrid_on_this_corpus(indexed):
    """Locks in the measured result so a regression is visible.

    Reranking is the one component the ablation shows clearly earning its
    place: it lifts P@1 from 0.543 to 0.674. If a change erases that, this
    fails rather than the README quietly becoming untrue.
    """
    from aidoctor.evaluation.runner import build_variants

    questions = load_questions(QUESTIONS)
    variants = {v.name: v for v in build_variants(indexed.retriever)}
    hybrid = evaluate_variant(variants["hybrid (RRF)"], questions, depth=DEPTH)
    reranked = evaluate_variant(variants["hybrid + rerank"], questions, depth=DEPTH)
    assert reranked.precision_at_1 > hybrid.precision_at_1
    assert reranked.mrr > hybrid.mrr


def test_ranking_is_deterministic_across_runs(indexed):
    questions = load_questions(QUESTIONS)
    variant = Variant("hybrid", indexed.retriever.search)
    first = evaluate_variant(variant, questions, depth=DEPTH)
    second = evaluate_variant(variant, questions, depth=DEPTH)
    assert first == second


def test_scores_are_bounded(indexed):
    questions = load_questions(QUESTIONS)
    scores = evaluate_variant(Variant("hybrid", indexed.retriever.search), questions, depth=DEPTH)
    for value in (
        scores.precision_at_1,
        scores.precision_at_5,
        scores.recall_at_5,
        scores.recall_at_10,
        scores.mrr,
        scores.ndcg_at_10,
    ):
        assert 0.0 <= value <= 1.0


def test_a_perfect_ranking_scores_one():
    """Sanity anchor: the metrics do reach 1.0 when they should."""
    chunk = Chunk(chunk_id="c", doc_id="d", text="t", ordinal=0, section_label="S", filename="f.md")
    key = section_key(chunk)
    scores = score_retrieval([([key], {key})])
    assert scores.precision_at_1 == 1.0
    assert scores.mrr == 1.0
