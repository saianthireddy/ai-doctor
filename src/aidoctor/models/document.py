"""Core domain types.

Deliberately plain dataclasses rather than ORM rows or Pydantic models: these
travel between the extractor, chunker, embedder, vector store and answerer, and
none of those layers should have to know about HTTP validation or a database
session. The API and persistence layers convert at their own boundaries.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SourceType(str, Enum):  # noqa: UP042 - StrEnum needs 3.11+; str+Enum keeps 3.10 usable
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    HTML = "html"
    TEXT = "text"


@dataclass(frozen=True)
class Section:
    """A logical unit of a document, before chunking.

    Extractors emit sections rather than one flat string so the chunker can avoid
    splitting across a heading or a slide boundary, and so a citation can say
    *where* in the document an answer came from. ``label`` is the human-facing
    locator: "page 3", "slide 2", "sheet Sales".
    """

    text: str
    label: str
    ordinal: int


@dataclass
class Document:
    doc_id: str
    filename: str
    source_type: SourceType
    sections: list[Section] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # noqa: UP017

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)

    @property
    def section_count(self) -> int:
        return len(self.sections)


@dataclass(frozen=True)
class Chunk:
    """A retrievable span, carrying enough provenance to cite itself."""

    chunk_id: str
    doc_id: str
    text: str
    ordinal: int
    section_label: str
    filename: str = ""

    @property
    def citation(self) -> str:
        where = f", {self.section_label}" if self.section_label else ""
        return f"[{self.filename}{where}]" if self.filename else f"[{self.section_label}]"


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float
    # Which retrieval path produced this: "dense", "lexical", "hybrid" or
    # "reranked". Kept on the result rather than inferred, so the API can explain
    # why a chunk surfaced instead of the caller guessing.
    method: str = "hybrid"


def content_id(*parts: str) -> str:
    """Deterministic id derived from content.

    Ingesting the same file twice must produce the same ids, otherwise a
    re-ingest duplicates the index instead of replacing it. That exact bug cost
    a sibling project a silent 3x index, so it is designed out here rather than
    discovered later.
    """
    digest = hashlib.sha256(" ".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]
