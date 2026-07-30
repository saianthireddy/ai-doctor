"""Extraction across every supported format, against real files."""

from __future__ import annotations

import pytest

from aidoctor.extractors.base import (
    ExtractionError,
    UnsupportedSourceError,
    extract,
    extractor_for,
    supported_extensions,
)
from aidoctor.models.document import SourceType


def test_every_supported_format_extracts(all_files):
    for path in all_files:
        document = extract(path)
        assert document.sections, f"{path.name} produced no sections"
        assert document.text.strip()
        assert document.filename == path.name


def test_pdf_produces_one_section_per_page(pdf_file):
    document = extract(pdf_file)
    assert document.source_type is SourceType.PDF
    assert [s.label for s in document.sections] == ["page 1", "page 2"]
    assert "non transferable" in document.sections[0].text


def test_docx_uses_headings_as_labels_and_reads_tables(docx_file):
    document = extract(docx_file)
    labels = [s.label for s in document.sections]
    assert "Password reset" in labels
    assert "Billing" in labels
    assert any(label.startswith("table") for label in labels), "tables must not be silently skipped"
    table_text = next(s.text for s in document.sections if s.label.startswith("table"))
    assert "Enterprise" in table_text and "500" in table_text


def test_pptx_includes_speaker_notes(pptx_file):
    document = extract(pptx_file)
    assert document.sections[0].label == "slide 1"
    assert "Speaker notes" in document.sections[0].text
    assert "three large renewals" in document.sections[0].text


def test_xlsx_repeats_headers_onto_every_row(xlsx_file):
    """A bare "EMEA | 1200" chunk is unanswerable; the header is what gives it meaning."""
    document = extract(xlsx_file)
    text = document.sections[0].text
    assert "Region: EMEA" in text
    assert "Amount: 1200" in text
    assert "Region: APAC" in text
    assert text.count("\n") == 1, "the blank row should have been dropped"


def test_html_drops_script_and_style_and_separates_headings(html_file):
    document = extract(html_file)
    joined = document.text
    assert "bad()" not in joined and "b{}" not in joined
    # Regression: the heading used to run into the body -> "SetupInstall the agent"
    assert "Setup\nInstall the agent on each host." in joined
    assert [s.label for s in document.sections] == ["Setup", "Limits"]


def test_markdown_headings_become_sections(text_file):
    document = extract(text_file)
    assert [s.label for s in document.sections] == ["Overview", "Caveats"]


def test_unsupported_extension_names_what_is_supported(tmp_path):
    path = tmp_path / "archive.zip"
    path.write_bytes(b"PK\x03\x04")
    with pytest.raises(UnsupportedSourceError) as exc:
        extract(path)
    assert ".pdf" in str(exc.value) and ".docx" in str(exc.value)


def test_unsupported_extension_is_reported_even_when_the_file_is_missing(tmp_path):
    """The caller's mistake is the format, not the path — say so."""
    with pytest.raises(UnsupportedSourceError):
        extract(tmp_path / "nope.zip")


def test_missing_supported_file_raises_extraction_error(tmp_path):
    with pytest.raises(ExtractionError):
        extract(tmp_path / "missing.pdf")


def test_empty_pdf_is_refused_rather_than_silently_empty(tmp_path):
    """A scanned PDF has no text layer. Returning an empty document would look
    like a successful ingest and fail confusingly much later."""
    from reportlab.pdfgen import canvas

    path = tmp_path / "blank.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.showPage()
    pdf.save()
    with pytest.raises(ExtractionError, match="OCR"):
        extract(path)


def test_registry_is_case_insensitive(tmp_path, docx_file):
    upper = tmp_path / "SHOUTING.DOCX"
    upper.write_bytes(docx_file.read_bytes())
    assert extract(upper).sections


def test_supported_extensions_is_sorted_and_non_empty():
    extensions = supported_extensions()
    assert extensions == tuple(sorted(extensions))
    assert ".pdf" in extensions


def test_extractor_for_returns_the_matching_extractor(pdf_file):
    assert extractor_for(pdf_file).source_type is SourceType.PDF
