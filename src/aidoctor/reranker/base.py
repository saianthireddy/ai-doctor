"""Reranking, with an offline default that is honest about what it is.

Retrieval optimises for recall; reranking trades compute for precision on the
handful of candidates that survived. A real cross-encoder scores the (query,
passage) pair jointly, which is why it beats bi-encoder cosine — it can see
interaction between the two rather than comparing two independent summaries.

``LexicalOverlapReranker`` is **not** a cross-encoder. It is a deterministic
signal-combining reranker used so the pipeline has a working reranking stage with
no model download, and so its effect is measurable in tests. It is named for what
it does rather than what it stands in for. ``CrossEncoderReranker`` is the real
one, lazily imported.
"""

from __future__ import annotations

from typing import Protocol

from aidoctor.embeddings.base import tokenize
from aidoctor.models.document import ScoredChunk

# Coverage must measure *content* overlap. Counting stopwords made an
# out-of-corpus question ("what is the airspeed of an unladen swallow") score
# 0.25 and clear the answerer's relevance floor, because "what/is/the/of/an"
# overlap with every passage. That defeats the refusal path entirely, so the
# terms that carry no topical signal are removed before coverage is computed.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "my",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
        "me",
        "our",
        "us",
        "they",
        "them",
        "he",
        "she",
    }
)


def content_terms(text: str) -> set[str]:
    return {t for t in tokenize(text) if t not in _STOPWORDS and len(t) > 1}


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, candidates: list[ScoredChunk], limit: int) -> list[ScoredChunk]: ...


class NoOpReranker:
    """Passes candidates through. Exists so 'no reranking' is a real, testable
    configuration rather than a None check scattered through the service."""

    name = "none"

    def rerank(self, query: str, candidates: list[ScoredChunk], limit: int) -> list[ScoredChunk]:
        return candidates[:limit]


class LexicalOverlapReranker:
    """Combines term coverage, phrase adjacency and rank prior.

    Coverage answers "does this passage address all of the question, or only one
    word of it?" — the failure hybrid fusion cannot see, because a chunk matching
    one rare term can outrank a chunk matching every term.
    """

    name = "lexical-overlap"

    def __init__(
        self, coverage_weight: float = 0.6, phrase_weight: float = 0.3, prior_weight: float = 0.1
    ) -> None:
        self.coverage_weight = coverage_weight
        self.phrase_weight = phrase_weight
        self.prior_weight = prior_weight

    def rerank(self, query: str, candidates: list[ScoredChunk], limit: int) -> list[ScoredChunk]:
        if not candidates:
            return []
        query_terms = content_terms(query)
        if not query_terms:
            # Nothing but stopwords: there is no signal to rerank on, so preserve
            # the retriever's order rather than inventing one.
            return candidates[:limit]
        bigrams = {f"{a} {b}" for a, b in zip(tokenize(query), tokenize(query)[1:], strict=False)}

        rescored: list[ScoredChunk] = []
        for rank, candidate in enumerate(candidates, start=1):
            present = query_terms & content_terms(candidate.chunk.text)
            coverage = len(present) / len(query_terms)

            lowered = candidate.chunk.text.lower()
            phrase = sum(1 for bg in bigrams if bg in lowered) / len(bigrams) if bigrams else 0.0
            prior = 1.0 / rank
            score = self.coverage_weight * coverage + self.phrase_weight * phrase + self.prior_weight * prior
            # The rank prior must not, on its own, carry a wholly irrelevant
            # passage over a downstream relevance threshold. No content term in
            # common means no score.
            if not present:
                score = 0.0
            rescored.append(ScoredChunk(chunk=candidate.chunk, score=score, method="reranked"))

        rescored.sort(key=lambda s: -s.score)
        return rescored[:limit]


class RerankerUnavailable(RuntimeError):
    """The selected reranker cannot run in this environment."""


class CrossEncoderReranker:
    """Real cross-encoder. Needs sentence-transformers and a model on disk.

    The import is deliberately lazy so the package stays installable without a
    ~2GB torch dependency. The cost of laziness is that a missing dependency
    would otherwise surface on the first *query* rather than at startup, as a
    bare ``ModuleNotFoundError`` from inside a reranking call — which is a
    confusing place to learn that an extra was never installed. So the check is
    hoisted into ``__init__``: choosing this backend fails immediately, with the
    command that fixes it.
    """

    name = "cross-encoder"

    def __init__(self, model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError as exc:
            raise RerankerUnavailable(
                "The cross-encoder reranker requires sentence-transformers. "
                'Install it with: pip install "ai-doctor[rerank]" '
                "(the model itself downloads on first use)."
            ) from exc
        self.model_name = model
        self._model = None

    def _load(self):  # pragma: no cover - requires model download
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, candidates: list[ScoredChunk], limit: int) -> list[ScoredChunk]:
        if not candidates:
            return []
        model = self._load()
        scores = model.predict([(query, c.chunk.text) for c in candidates])
        rescored = [
            ScoredChunk(chunk=c.chunk, score=float(s), method="reranked")
            for c, s in zip(candidates, scores, strict=True)
        ]
        rescored.sort(key=lambda s: -s.score)
        return rescored[:limit]


def build_reranker(name: str = "lexical-overlap") -> Reranker:
    if name in {"none", "noop"}:
        return NoOpReranker()
    if name == "lexical-overlap":
        return LexicalOverlapReranker()
    if name == "cross-encoder":
        return CrossEncoderReranker()
    raise ValueError(f"Unknown reranker {name!r}. Available: none, lexical-overlap, cross-encoder")
