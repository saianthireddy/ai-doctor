"""Metric arithmetic, checked against values worked out by hand.

Testing a metric against the implementation that produced it proves nothing.
Every expected number here is derived in the test name or a comment, so a
reviewer can verify it without running anything.
"""

from __future__ import annotations

import math

import pytest

from aidoctor.evaluation.metrics import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    score_retrieval,
)

RANKED = ["a", "b", "c", "d", "e"]


def test_precision_divides_by_k_not_by_results_returned():
    # One hit in the top 5 is 1/5, not 1/1. Dividing by the number returned
    # would let a retriever that returns a single lucky chunk score 1.0.
    assert precision_at_k(["a"], {"a"}, 5) == pytest.approx(0.2)


def test_precision_at_1_is_a_hit_or_a_miss():
    assert precision_at_k(RANKED, {"a"}, 1) == 1.0
    assert precision_at_k(RANKED, {"b"}, 1) == 0.0


def test_recall_is_over_the_relevant_set_not_the_ranking():
    # Two of three relevant found in the top 3 -> 2/3.
    assert recall_at_k(RANKED, {"a", "c", "zzz"}, 3) == pytest.approx(2 / 3)


def test_recall_of_an_empty_relevant_set_is_zero_not_one():
    # Vacuous truth would say "found all zero of them" = 1.0, which would make
    # unanswerable questions inflate the average. They are excluded instead.
    assert recall_at_k(RANKED, set(), 5) == 0.0


def test_reciprocal_rank_uses_the_first_hit_only():
    assert reciprocal_rank(RANKED, {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(RANKED, {"c", "d"}) == pytest.approx(1 / 3)


def test_reciprocal_rank_is_zero_when_nothing_relevant_is_retrieved():
    assert reciprocal_rank(RANKED, {"zzz"}) == 0.0


def test_ndcg_is_one_when_every_relevant_item_leads():
    assert ndcg_at_k(RANKED, {"a", "b"}, 5) == pytest.approx(1.0)


def test_ndcg_penalises_a_hit_that_ranks_lower():
    # Single relevant item at rank 3: DCG = 1/log2(4) = 0.5, ideal = 1.0.
    assert ndcg_at_k(RANKED, {"c"}, 5) == pytest.approx(0.5)


def test_ndcg_separates_orderings_that_mrr_cannot():
    # Both have their first hit at rank 1, so MRR is 1.0 for both; only nDCG
    # sees that the second ranking buries the other two relevant items.
    good = ["a", "b", "c", "x", "y"]
    bad = ["a", "x", "y", "b", "c"]
    relevant = {"a", "b", "c"}
    assert reciprocal_rank(good, relevant) == reciprocal_rank(bad, relevant)
    assert ndcg_at_k(good, relevant, 5) > ndcg_at_k(bad, relevant, 5)


def test_dcg_discount_matches_the_definition():
    # Hits at ranks 1 and 3 -> 1/log2(2) + 1/log2(4) = 1.0 + 0.5.
    expected_dcg = 1 / math.log2(2) + 1 / math.log2(4)
    ideal_dcg = 1 / math.log2(2) + 1 / math.log2(3)
    assert ndcg_at_k(["a", "x", "c"], {"a", "c"}, 3) == pytest.approx(expected_dcg / ideal_dcg)


def test_scores_average_over_questions_not_over_hits():
    perfect = (["a"], {"a"})
    missed = (["x"], {"a"})
    scores = score_retrieval([perfect, missed])
    assert scores.questions == 2
    assert scores.precision_at_1 == pytest.approx(0.5)
    assert scores.mrr == pytest.approx(0.5)


def test_empty_result_set_scores_zero_rather_than_raising():
    scores = score_retrieval([])
    assert scores.questions == 0
    assert scores.mrr == 0.0
