from __future__ import annotations

import numpy as np
import pytest

from aidoctor.embeddings.base import build_embedder, tokenize


def test_vectors_are_unit_length(embedder):
    vector = embedder.embed_one("reset the password")
    assert np.isclose(np.linalg.norm(vector), 1.0)


def test_related_text_scores_higher_than_unrelated(embedder):
    query = embedder.embed_one("reset my password")
    related = embedder.embed_one("password reset instructions")
    unrelated = embedder.embed_one("quarterly revenue growth in EMEA")
    assert float(query @ related) > float(query @ unrelated)


def test_empty_string_does_not_produce_nan(embedder):
    """An all-stopword or empty chunk must not poison the index."""
    vector = embedder.embed_one("")
    assert not np.isnan(vector).any()
    assert float(np.linalg.norm(vector)) == 0.0


def test_embedding_is_deterministic(embedder):
    assert np.array_equal(embedder.embed_one("stable"), embedder.embed_one("stable"))


def test_embed_many_matches_embed_one(embedder):
    texts = ["alpha", "beta"]
    batched = embedder.embed_many(texts)
    assert all(np.array_equal(b, embedder.embed_one(t)) for b, t in zip(batched, texts, strict=True))


def test_dimensions_are_respected():
    assert build_embedder("hashing", 64).embed_one("x").shape == (64,)


def test_subtoken_hashing_gives_unseen_words_some_signal(embedder):
    """Without character n-grams an unknown word contributes nothing at all."""
    known = embedder.embed_one("authentication")
    similar = embedder.embed_one("authentications")
    assert float(known @ similar) > 0.5


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError, match="Unknown embedder"):
        build_embedder("magic")


def test_zero_dimensions_is_rejected():
    with pytest.raises(ValueError, match="dimensions"):
        build_embedder("hashing", 0)


def test_every_factory_rejects_an_unknown_name():
    """All four factories should fail loudly and name the valid options.

    build_embedder and build_vector_store were already guarded; build_llm and
    build_reranker were not, which a coverage report surfaced as an unreached
    raise rather than as a missing test.
    """
    from aidoctor.llms.base import build_llm
    from aidoctor.reranker.base import build_reranker
    from aidoctor.vectorstore.qdrant_store import build_vector_store

    with pytest.raises(ValueError, match="Unknown embedder"):
        build_embedder("magic")
    with pytest.raises(ValueError, match="Unknown reranker"):
        build_reranker("telepathy")
    with pytest.raises(ValueError, match="Unknown LLM"):
        build_llm("oracle")
    with pytest.raises(ValueError, match="Unknown vector backend"):
        build_vector_store("pinecone", dimensions=8)


def test_factory_errors_list_the_valid_options():
    """An error that does not say what IS valid makes the caller go read code."""
    from aidoctor.llms.base import build_llm

    with pytest.raises(ValueError) as exc:
        build_llm("oracle")
    assert "extractive" in str(exc.value) and "openai" in str(exc.value)


def test_tokenize_lowercases_and_keeps_error_codes():
    assert tokenize("Reset ERR_LOCK_TIMEOUT now!") == ["reset", "err", "lock", "timeout", "now"]
