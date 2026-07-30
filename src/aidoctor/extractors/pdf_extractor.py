"""PDF text extraction, one section per page.

Page-level sections mean a citation can say "page 7", which is the locator a
reader can actually act on.

**No OCR.** A scanned PDF has no text layer, so extraction yields nothing. Rather
than return an empty document that looks like a successful ingest, this raises
:class:`ExtractionError` naming the likely cause — a silent empty ingest is the
worse failure, because it surfaces later as "the assistant can't find anything"
with no clue why.
"""

from __future__ import annotations

from pathlib import Path

from aidoctor.extractors.base import ExtractionError
from aidoctor.models.document import Document, Section, SourceType


class PdfExtractor:
    source_type = SourceType.PDF
    extensions = (".pdf",)

    def extract(self, path: Path, doc_id: str) -> Document:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ExtractionError("pypdf is required to read PDFs") from exc

        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise ExtractionError(f"Could not open {path.name}: {exc}") from exc

        sections: list[Section] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception:
                # One unreadable page should not abort a 200-page manual.
                text = ""
            if text:
                sections.append(Section(text=text, label=f"page {index}", ordinal=len(sections)))

        if not sections:
            raise ExtractionError(
                f"{path.name} yielded no text. If it is a scanned document it needs OCR, "
                "which this extractor deliberately does not attempt."
            )
        return Document(
            doc_id=doc_id,
            filename=path.name,
            source_type=self.source_type,
            sections=sections,
            metadata={"pages": str(len(reader.pages))},
        )
