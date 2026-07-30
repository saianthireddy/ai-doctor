"""One interface for every source type.

An extractor turns a file into a :class:`Document` with labelled sections.
Keeping the contract this narrow is what lets the rest of the pipeline stay
ignorant of file formats: chunker, embedder and retriever only ever see sections.

Registration is explicit rather than magic, so an unsupported file fails with an
error naming what *is* supported instead of silently producing an empty document.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from aidoctor.models.document import Document, SourceType


class UnsupportedSourceError(ValueError):
    """The file extension has no registered extractor."""


class ExtractionError(RuntimeError):
    """The file is a supported type but could not be read."""


@runtime_checkable
class Extractor(Protocol):
    source_type: SourceType
    extensions: tuple[str, ...]

    def extract(self, path: Path, doc_id: str) -> Document: ...


def _registry() -> dict[str, Extractor]:
    # Imported inside the function so a missing optional dependency breaks only
    # the format that needs it, not importing the package at all.
    from aidoctor.extractors.docx_extractor import DocxExtractor
    from aidoctor.extractors.html_extractor import HtmlExtractor, TextExtractor
    from aidoctor.extractors.pdf_extractor import PdfExtractor
    from aidoctor.extractors.pptx_extractor import PptxExtractor
    from aidoctor.extractors.xlsx_extractor import XlsxExtractor

    mapping: dict[str, Extractor] = {}
    for extractor in (
        PdfExtractor(),
        DocxExtractor(),
        PptxExtractor(),
        XlsxExtractor(),
        HtmlExtractor(),
        TextExtractor(),
    ):
        for ext in extractor.extensions:
            mapping[ext] = extractor
    return mapping


def supported_extensions() -> tuple[str, ...]:
    return tuple(sorted(_registry()))


def extractor_for(path: Path) -> Extractor:
    suffix = path.suffix.lower()
    try:
        return _registry()[suffix]
    except KeyError:
        raise UnsupportedSourceError(
            f"No extractor for {suffix or path.name!r}. Supported: {', '.join(supported_extensions())}"
        ) from None


def extract(path: Path | str, doc_id: str | None = None) -> Document:
    """Extract *path* using whichever extractor claims its extension."""
    from aidoctor.models.document import content_id

    path = Path(path)
    # Extension first, then existence: if the caller passed a .zip, the useful
    # error names the unsupported format rather than complaining about the path.
    extractor = extractor_for(path)
    if not path.exists():
        raise ExtractionError(f"{path} does not exist")
    return extractor.extract(path, doc_id or content_id(path.name, str(path.stat().st_size)))
