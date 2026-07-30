"""Grounded answering: retrieve, rerank, generate, cite — or refuse.

The refusal path is the point. A knowledge assistant that always answers is worse
than one that sometimes says "not in the corpus", because a confident wrong answer
costs more than a gap the user can route around. So two gates run before
generation:

* **A relevance floor.** If the best reranked passage scores below
  ``min_score``, the corpus does not contain the answer and we say so.
* **A grounding check.** If the generator produced nothing traceable to a
  passage, the result is reported ungrounded rather than surfaced as an answer.

Citations are attached from the passages actually used, not appended as a
bibliography of everything retrieved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aidoctor.llms.base import LLM
from aidoctor.models.document import ScoredChunk
from aidoctor.reranker.base import Reranker
from aidoctor.retrieval.hybrid import HybridRetriever

REFUSAL = (
    "I could not find this in the indexed documents. Rather than guess, here is "
    "what is missing: no passage matched this question above the relevance "
    "threshold. Try rephrasing, or ingest the source that should contain it."
)


@dataclass
class Answer:
    question: str
    text: str
    grounded: bool
    citations: list[str] = field(default_factory=list)
    passages: list[ScoredChunk] = field(default_factory=list)
    escalated: bool = False
    model: str = ""

    @property
    def confidence(self) -> float:
        """Top reranked score, exposed so callers can set their own thresholds."""
        return round(self.passages[0].score, 4) if self.passages else 0.0


class Answerer:
    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: Reranker,
        llm: LLM,
        candidate_k: int = 12,
        context_k: int = 4,
        min_score: float = 0.12,
    ) -> None:
        self.retriever = retriever
        self.reranker = reranker
        self.llm = llm
        self.candidate_k = candidate_k
        self.context_k = context_k
        self.min_score = min_score

    def answer(self, question: str) -> Answer:
        question = question.strip()
        if not question:
            return Answer(question=question, text=REFUSAL, grounded=False, escalated=True)

        candidates = self.retriever.search(question, limit=self.candidate_k)
        if not candidates:
            return Answer(question=question, text=REFUSAL, grounded=False, escalated=True)

        passages = self.reranker.rerank(question, candidates, limit=self.context_k)
        if not passages or passages[0].score < self.min_score:
            return Answer(
                question=question,
                text=REFUSAL,
                grounded=False,
                passages=passages,
                escalated=True,
            )

        completion = self.llm.complete(question, passages)
        if not completion.text.strip():
            return Answer(
                question=question,
                text=REFUSAL,
                grounded=False,
                passages=passages,
                escalated=True,
                model=completion.model,
            )

        # Cite only the passages whose text actually contributed.
        used = [
            p
            for p in passages
            if any(part and part in completion.text for part in p.chunk.text.split(". ")[:4])
        ] or passages[:1]
        citations: list[str] = []
        for passage in used:
            if passage.chunk.citation not in citations:
                citations.append(passage.chunk.citation)

        return Answer(
            question=question,
            text=completion.text,
            grounded=completion.grounded,
            citations=citations,
            passages=passages,
            escalated=False,
            model=completion.model,
        )
