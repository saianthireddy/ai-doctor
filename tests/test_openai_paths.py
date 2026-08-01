"""The OpenAI paths, against a stub client — *not* against the API.

Be precise about what this proves. It does **not** verify that OpenAI accepts
these requests or that the response shape is current; that needs a key and a
live call, and the status table keeps these rows 🟡 for exactly that reason.

What it does verify is the code around the call, which is where the bugs
actually were: batching, ordering, dimension handling, and not calling the API
at all when there is nothing to send. All of that was `# pragma: no cover`
before, so a typo in the parsing loop would have shipped silently.

The stub mimics the shape this code consumes (`response.data[i].embedding`,
`response.choices[0].message.content`) rather than the whole SDK surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from aidoctor.embeddings.base import OpenAIEmbedder
from aidoctor.llms.base import OpenAIChatLLM
from aidoctor.models.document import Chunk, ScoredChunk

# --------------------------------------------------------------------- stubs


@dataclass
class _Embeddings:
    dimensions: int
    calls: list[dict] = field(default_factory=list)
    override: int | None = None

    def create(self, model, input, dimensions=None, **kwargs):  # noqa: A002
        self.calls.append({"model": model, "input": list(input), "dimensions": dimensions})
        width = self.override or dimensions or self.dimensions
        # Deterministic and distinguishable per text, so ordering is checkable.
        data = [type("Item", (), {"embedding": [float(len(text))] * width})() for text in input]
        return type("Response", (), {"data": data})()


@dataclass
class _EmbeddingClient:
    dimensions: int = 8
    override: int | None = None

    def __post_init__(self):
        self.embeddings = _Embeddings(self.dimensions, override=self.override)


@dataclass
class _Completions:
    reply: str = "The handbook says to open Settings."
    calls: list[dict] = field(default_factory=list)

    def create(self, model, messages, temperature=None, **kwargs):
        self.calls.append({"model": model, "messages": messages, "temperature": temperature})
        message = type("Msg", (), {"content": self.reply})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class _ChatClient:
    def __init__(self, reply: str = "The handbook says to open Settings."):
        self.chat = type("Chat", (), {"completions": _Completions(reply)})()


def _passage(text: str = "Open Settings and choose Reset Password.") -> ScoredChunk:
    chunk = Chunk(
        chunk_id="c1",
        doc_id="d1",
        text=text,
        ordinal=0,
        section_label="Password reset",
        filename="handbook.docx",
    )
    return ScoredChunk(chunk=chunk, score=0.9, method="hybrid")


# ----------------------------------------------------------------- embedder


def test_configured_dimensions_are_sent_to_the_api():
    """The bug this test exists for.

    `text-embedding-3-*` returns the model's full width unless `dimensions` is
    passed. The vector store is sized from `embedder.dimensions`, so omitting it
    built a store expecting 384 while vectors arrived at 1536 — a mismatch that
    only surfaced at upsert, far from its cause.
    """
    client = _EmbeddingClient(dimensions=384)
    embedder = OpenAIEmbedder(dimensions=384, client=client)
    embedder.embed_many(["hello"])
    assert client.embeddings.calls[0]["dimensions"] == 384


def test_texts_are_batched_and_every_text_is_sent_exactly_once():
    client = _EmbeddingClient(dimensions=4)
    embedder = OpenAIEmbedder(dimensions=4, batch_size=10, client=client)
    texts = [f"text-{i}" for i in range(25)]
    embedder.embed_many(texts)

    sizes = [len(call["input"]) for call in client.embeddings.calls]
    assert sizes == [10, 10, 5]
    sent = [t for call in client.embeddings.calls for t in call["input"]]
    assert sent == texts


def test_results_come_back_in_the_order_they_were_requested():
    """Across batch boundaries, not just within one call."""
    client = _EmbeddingClient(dimensions=4)
    embedder = OpenAIEmbedder(dimensions=4, batch_size=2, client=client)
    vectors = embedder.embed_many(["a", "bb", "ccc", "dddd", "eeeee"])
    # The stub encodes len(text) into every component.
    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_vectors_are_float32_arrays_not_python_lists():
    client = _EmbeddingClient(dimensions=4)
    vectors = OpenAIEmbedder(dimensions=4, client=client).embed_many(["x"])
    assert isinstance(vectors[0], np.ndarray)
    assert vectors[0].dtype == np.float32


def test_embed_one_returns_a_single_vector_not_a_list():
    client = _EmbeddingClient(dimensions=4)
    vector = OpenAIEmbedder(dimensions=4, client=client).embed_one("x")
    assert isinstance(vector, np.ndarray)
    assert vector.shape == (4,)


def test_a_width_mismatch_is_caught_here_rather_than_at_upsert():
    """If the API ignores `dimensions`, fail loudly and immediately.

    Otherwise the vectors reach the store and the error arrives as a confusing
    complaint from Qdrant about a collection that was configured correctly.
    """
    client = _EmbeddingClient(dimensions=384, override=1536)
    embedder = OpenAIEmbedder(dimensions=384, client=client)
    with pytest.raises(ValueError, match="1536-dimensional"):
        embedder.embed_many(["x"])


def test_embedding_no_texts_makes_no_api_call():
    client = _EmbeddingClient(dimensions=4)
    assert OpenAIEmbedder(dimensions=4, client=client).embed_many([]) == []
    assert client.embeddings.calls == []


# ---------------------------------------------------------------------- llm


def test_no_passages_means_no_api_call_and_an_ungrounded_answer():
    """Refusal must not cost a paid request."""
    client = _ChatClient()
    completion = OpenAIChatLLM(client=client).complete("anything", [])
    assert completion.text == ""
    assert completion.grounded is False
    assert client.chat.completions.calls == []


def test_the_system_prompt_instructs_refusal_over_invention():
    client = _ChatClient()
    OpenAIChatLLM(client=client).complete("how do I reset my password", [_passage()])
    system = client.chat.completions.calls[0]["messages"][0]
    assert system["role"] == "system"
    assert "do not speculate" in system["content"]


def test_the_context_carries_citation_labels_the_model_can_quote():
    client = _ChatClient()
    OpenAIChatLLM(client=client).complete("q", [_passage()])
    user = client.chat.completions.calls[0]["messages"][1]["content"]
    assert "handbook.docx" in user
    assert "Password reset" in user
    assert "Open Settings" in user


def test_temperature_and_model_are_passed_through():
    client = _ChatClient()
    OpenAIChatLLM(model="gpt-4o-mini", temperature=0.0, client=client).complete("q", [_passage()])
    call = client.chat.completions.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert call["temperature"] == 0.0


def test_an_empty_reply_does_not_become_the_string_none():
    """`message.content` is nullable; `str(None)` would be published as an answer."""
    client = _ChatClient(reply=None)
    completion = OpenAIChatLLM(client=client).complete("q", [_passage()])
    assert completion.text == ""
