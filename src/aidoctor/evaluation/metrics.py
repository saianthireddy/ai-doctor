"""Retrieval metrics, defined so a reader can check them by hand.

Every function takes ``ranked`` — the retrieved section keys, best first — and
``relevant`` — the labelled set. No library is used, because the point of this
module is that the arithmetic is inspectable.

A note on what these numbers can and cannot show. If the index holds fewer
chunks than the retriever returns, every query returns everything and Recall@k
is 1.0 for reasons that have nothing to do with retrieval quality. That is not a
hypothetical: this project's own corpus had 8 chunks against ``candidate_k`` of
12 before the corpus was expanded. ``runner.guard_index_size`` refuses to report
under those conditions rather than printing a flattering number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the top k that are relevant.

    Divided by ``k``, not by ``len(top)``. Dividing by the number actually
    returned would score a retriever that returns one lucky hit as 1.0.
    """
    if k <= 0:
        return 0.0
    top = ranked[:k]
    return sum(1 for key in top if key in relevant) / k


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the relevant set found in the top k."""
    if not relevant:
        return 0.0
    return sum(1 for key in ranked[:k] if key in relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    """1/rank of the first relevant hit, 0 if none."""
    for index, key in enumerate(ranked, start=1):
        if key in relevant:
            return 1.0 / index
    return 0.0


def dcg(gains: list[float]) -> float:
    return sum(gain / math.log2(index + 1) for index, gain in enumerate(gains, start=1))


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Binary-gain nDCG.

    Included because MRR only sees the first hit. When a question has three
    relevant sections, MRR cannot tell "all three in the top three" from "one at
    rank one and the others at rank forty"; nDCG can.
    """
    if not relevant:
        return 0.0
    gains = [1.0 if key in relevant else 0.0 for key in ranked[:k]]
    ideal = [1.0] * min(len(relevant), k)
    best = dcg(ideal)
    return dcg(gains) / best if best else 0.0


@dataclass(frozen=True)
class RetrievalScores:
    """Averages over the answerable questions only."""

    questions: int
    precision_at_1: float
    precision_at_5: float
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float

    def as_row(self, label: str) -> str:
        return (
            f"| {label} | {self.precision_at_1:.3f} | {self.precision_at_5:.3f} | "
            f"{self.recall_at_5:.3f} | {self.recall_at_10:.3f} | "
            f"{self.mrr:.3f} | {self.ndcg_at_10:.3f} |"
        )


@dataclass(frozen=True)
class RefusalScores:
    """How the system behaves on questions the corpus cannot answer.

    ``false_answer_rate`` is the number this project should be judged on: the
    share of unanswerable questions that got a confident answer anyway.
    """

    answerable: int
    unanswerable: int
    false_answer_rate: float
    wrongly_refused_rate: float

    def as_row(self, label: str) -> str:
        return f"| {label} | {self.false_answer_rate:.3f} | {self.wrongly_refused_rate:.3f} |"


def score_retrieval(results: list[tuple[list[str], set[str]]]) -> RetrievalScores:
    """Aggregate per-question rankings into averages.

    ``results`` is one (ranked, relevant) pair per *answerable* question.
    """
    if not results:
        return RetrievalScores(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def mean(values: list[float]) -> float:
        return sum(values) / len(values)

    return RetrievalScores(
        questions=len(results),
        precision_at_1=mean([precision_at_k(r, rel, 1) for r, rel in results]),
        precision_at_5=mean([precision_at_k(r, rel, 5) for r, rel in results]),
        recall_at_5=mean([recall_at_k(r, rel, 5) for r, rel in results]),
        recall_at_10=mean([recall_at_k(r, rel, 10) for r, rel in results]),
        mrr=mean([reciprocal_rank(r, rel) for r, rel in results]),
        ndcg_at_10=mean([ndcg_at_k(r, rel, 10) for r, rel in results]),
    )
