"""Embedding backends behind a two-method interface.

``HashingEmbedder`` is the default so the whole platform runs, tests and demos
with no API key and no network. It is **not** a semantic model — it is a
bag-of-hashed-tokens projection, and token overlap is all it can see. That
limitation is stated here because a reader who assumes otherwise will
misinterpret every retrieval number this project reports.

``OpenAIEmbedder`` is the production drop-in, lazily imported so the ``openai``
package is only needed when actually selected.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

_TOKEN = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class Embedder(Protocol):
    dimensions: int
    name: str

    def embed_one(self, text: str) -> np.ndarray: ...

    def embed_many(self, texts: list[str]) -> list[np.ndarray]: ...


class HashingEmbedder:
    """Deterministic, offline, L2-normalised bag-of-hashed-tokens.

    Sub-token hashing (3-grams alongside whole tokens) is included so an unseen
    word still shares signal with a known one — without it, any vocabulary the
    corpus did not contain contributes nothing at all.
    """

    name = "hashing"

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def _bucket(self, token: str) -> int:
        return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dimensions

    def embed_one(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimensions, dtype=np.float32)
        tokens = tokenize(text)
        for token in tokens:
            vector[self._bucket(token)] += 1.0
            for i in range(len(token) - 2):
                vector[self._bucket(token[i : i + 3])] += 0.35
        norm = float(np.linalg.norm(vector))
        # An empty or all-stopword string must not produce NaN downstream.
        return vector / norm if norm else vector

    def embed_many(self, texts: list[str]) -> list[np.ndarray]:
        return [self.embed_one(t) for t in texts]


class OpenAIEmbedder:
    """Production embedder. Batches, because per-text calls are the slow path."""

    name = "openai"

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        batch_size: int = 128,
        api_key: str | None = None,
        client=None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self._api_key = api_key
        # Injectable so the request we build and the response we parse can be
        # tested without a key. The network call is not the risky part; the
        # batching, ordering and dimension handling around it are.
        self._injected = client

    def _client(self):
        if self._injected is not None:
            return self._injected
        from openai import OpenAI  # pragma: no cover - requires the openai extra

        return OpenAI(api_key=self._api_key) if self._api_key else OpenAI()  # pragma: no cover

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[np.ndarray]:
        client = self._client()
        out: list[np.ndarray] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            # `dimensions` must be sent. text-embedding-3-* defaults to the
            # model's full width (1536 for -small), so omitting it while the
            # vector store was sized from `self.dimensions` produced a store
            # expecting 384 and vectors arriving at 1536 — a mismatch that only
            # surfaced at upsert, far from its cause.
            response = client.embeddings.create(model=self.model, input=batch, dimensions=self.dimensions)
            out.extend(np.asarray(item.embedding, dtype=np.float32) for item in response.data)

        wrong = [v.shape[0] for v in out if v.shape[0] != self.dimensions]
        if wrong:
            raise ValueError(
                f"{self.model} returned {wrong[0]}-dimensional vectors but this "
                f"embedder is configured for {self.dimensions}. The vector store "
                "is sized from the latter, so indexing would fail later and "
                "further from the cause."
            )
        return out


def build_embedder(name: str = "hashing", dimensions: int | None = None) -> Embedder:
    # `dimensions or 384` would silently turn an explicit 0 into 384 and hide the
    # caller's mistake; only None means "use the default".
    if name == "hashing":
        return HashingEmbedder(384 if dimensions is None else dimensions)
    if name == "openai":
        return OpenAIEmbedder(dimensions=1536 if dimensions is None else dimensions)
    raise ValueError(f"Unknown embedder {name!r}. Available: hashing, openai")
