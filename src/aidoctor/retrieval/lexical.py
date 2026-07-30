"""BM25 over the indexed chunks, implemented rather than imported.

Dense retrieval alone fails on exactly the queries enterprise users care about:
error codes, product SKUs, licence identifiers. An embedding smears
``ERR_LOCK_TIMEOUT`` into "something about errors"; BM25 matches the literal
token. That is why hybrid exists here rather than as a roadmap item.

Written directly because it is ~40 lines and the constants matter: k1 controls
how fast term frequency saturates, b how strongly long documents are penalised.
Both are exposed rather than buried.
"""

from __future__ import annotations

import math
from collections import Counter

from aidoctor.embeddings.base import tokenize
from aidoctor.models.document import Chunk, ScoredChunk

# Conservative suffix stripping, applied to BM25 terms only.
#
# Without it "seats" misses "seat" and "charged" misses "charges", so a perfectly
# reasonable question returns zero lexical hits — observed on this project's own
# fixture corpus before this was added. A full Porter stemmer is overkill and
# over-stems domain tokens; these four suffixes cover the plural/verb-form cases
# that actually cost recall.
#
# Applied to the *embedder* it would be wrong: dense vectors benefit from the
# surface form, and stemming there discards signal the model can use.
_SUFFIXES = ("ing", "ed", "es", "s")


def stem(token: str) -> str:
    if len(token) < 5:
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def lexical_tokens(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text)]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._chunks: dict[str, Chunk] = {}
        self._tokens: dict[str, Counter] = {}
        self._lengths: dict[str, int] = {}
        self._df: Counter = Counter()

    def index(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            if chunk.chunk_id in self._chunks:
                # Re-indexing the same chunk must not double its document
                # frequency contribution.
                self._remove(chunk.chunk_id)
            tokens = lexical_tokens(chunk.text)
            counts = Counter(tokens)
            self._chunks[chunk.chunk_id] = chunk
            self._tokens[chunk.chunk_id] = counts
            self._lengths[chunk.chunk_id] = len(tokens)
            for term in counts:
                self._df[term] += 1

    def _remove(self, chunk_id: str) -> None:
        for term in self._tokens.get(chunk_id, {}):
            self._df[term] -= 1
            if self._df[term] <= 0:
                del self._df[term]
        self._chunks.pop(chunk_id, None)
        self._tokens.pop(chunk_id, None)
        self._lengths.pop(chunk_id, None)

    def delete_document(self, doc_id: str) -> int:
        stale = [cid for cid, c in self._chunks.items() if c.doc_id == doc_id]
        for cid in stale:
            self._remove(cid)
        return len(stale)

    @property
    def size(self) -> int:
        return len(self._chunks)

    def search(self, query: str, limit: int = 8) -> list[ScoredChunk]:
        if not self._chunks:
            return []
        terms = lexical_tokens(query)
        if not terms:
            return []
        n = len(self._chunks)
        avg_len = sum(self._lengths.values()) / n

        scored: list[ScoredChunk] = []
        for chunk_id, counts in self._tokens.items():
            length = self._lengths[chunk_id] or 1
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                df = self._df.get(term, 0)
                # +0.5/+1 smoothing keeps idf positive for terms in every doc,
                # which would otherwise go negative and invert the ranking.
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                denom = tf + self.k1 * (1 - self.b + self.b * length / avg_len)
                score += idf * (tf * (self.k1 + 1)) / denom
            if score > 0:
                scored.append(ScoredChunk(chunk=self._chunks[chunk_id], score=score, method="lexical"))
        scored.sort(key=lambda s: -s.score)
        return scored[:limit]
