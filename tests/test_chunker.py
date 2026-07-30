"""Chunking rules. Section boundaries are the invariant that matters most."""

from __future__ import annotations

import pytest

from aidoctor.extractors.base import extract
from aidoctor.models.document import Document, Section, SourceType
from aidoctor.services.chunker import ChunkConfig, chunk_document


def _doc(*sections: tuple[str, str]) -> Document:
    return Document(
        doc_id="d",
        filename="f.md",
        source_type=SourceType.TEXT,
        sections=[Section(text=t, label=label, ordinal=i) for i, (label, t) in enumerate(sections)],
    )


def test_chunks_never_span_two_sections():
    """A chunk covering the end of Billing and the start of Support cannot be
    cited honestly, and dilutes both topics in the embedding."""
    document = _doc(("Billing", "Invoices monthly. " * 40), ("Support", "Email support. " * 40))
    chunks = chunk_document(document, ChunkConfig(max_chars=200, overlap_chars=20))
    assert len(chunks) > 2
    for chunk in chunks:
        assert chunk.section_label in {"Billing", "Support"}
        other = "Support" if chunk.section_label == "Billing" else "Billing"
        assert other not in chunk.text


def test_every_chunk_respects_max_chars_plus_overlap():
    document = _doc(("Long", "word " * 800))
    config = ChunkConfig(max_chars=300, overlap_chars=50)
    for chunk in chunk_document(document, config):
        assert len(chunk.text) <= config.max_chars + config.overlap_chars + 1


def test_overlap_carries_context_from_the_previous_chunk():
    document = _doc(("S", "First sentence here. " * 30))
    chunks = chunk_document(document, ChunkConfig(max_chars=120, overlap_chars=40, min_chars=10))
    assert len(chunks) > 1
    tail = chunks[0].text[-40:].strip()
    assert tail and tail[:20] in chunks[1].text


def test_zero_overlap_is_supported():
    document = _doc(("S", "Sentence one. Sentence two. Sentence three. " * 10))
    chunks = chunk_document(document, ChunkConfig(max_chars=100, overlap_chars=0, min_chars=10))
    assert len(chunks) > 1


def test_short_section_survives_even_below_min_chars():
    """Dropping it would lose the only content that section has."""
    document = _doc(("Tiny", "No OCR."))
    chunks = chunk_document(document, ChunkConfig(min_chars=500, overlap_chars=20))
    assert len(chunks) == 1
    assert chunks[0].text == "No OCR."


def test_chunk_ids_are_deterministic_across_runs(docx_file):
    first = chunk_document(extract(docx_file))
    second = chunk_document(extract(docx_file))
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_chunk_ids_are_unique_within_a_document():
    document = _doc(("A", "alpha " * 100), ("B", "beta " * 100))
    ids = [c.chunk_id for c in chunk_document(document, ChunkConfig(max_chars=100, overlap_chars=20))]
    assert len(ids) == len(set(ids))


def test_citation_names_file_and_place(docx_file):
    chunk = chunk_document(extract(docx_file))[0]
    assert "handbook.docx" in chunk.citation
    assert chunk.section_label in chunk.citation


def test_overlap_must_be_smaller_than_max():
    with pytest.raises(ValueError, match="overlap_chars"):
        ChunkConfig(max_chars=100, overlap_chars=100)


def test_max_chars_must_be_positive():
    with pytest.raises(ValueError, match="max_chars"):
        ChunkConfig(max_chars=0)


def test_hard_split_is_the_last_resort_not_the_default():
    """A paragraph that fits must survive whole, not be windowed."""
    document = _doc(("S", "A tidy paragraph that fits comfortably inside the limit."))
    chunks = chunk_document(document, ChunkConfig(max_chars=200, overlap_chars=20))
    assert len(chunks) == 1
    assert chunks[0].text.endswith("limit.")


def test_empty_document_yields_no_chunks():
    assert chunk_document(_doc()) == []
