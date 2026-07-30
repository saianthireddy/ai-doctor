"""Section-aware chunking.

Chunking is where most RAG quality is won or lost, and the failure is quiet: a
chunk split mid-sentence still embeds, still retrieves, and still gets cited —
it just answers badly. Three rules here:

**Never merge across sections.** A chunk that spans the end of "Installation"
and the start of "Billing" cannot be cited honestly, and it dilutes both topics
in the embedding. Sections are hard boundaries even when that leaves a short
chunk.

**Split on paragraph, then sentence, then hard.** Falling straight to a
character window is what produces "…hold the power butt / on for ten seconds".
Hard splitting is the last resort, not the default.

**Overlap carries context backwards, not forwards.** The tail of the previous
chunk is prepended to the next so a definition introduced in one paragraph is
still present when the following one is retrieved alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aidoctor.models.document import Chunk, Document, content_id

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class ChunkConfig:
    max_chars: int = 1200
    overlap_chars: int = 150
    min_chars: int = 80

    def __post_init__(self) -> None:
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")


def _hard_split(text: str, limit: int) -> list[str]:
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _split_to_limit(text: str, limit: int) -> list[str]:
    """Paragraph -> sentence -> hard, stopping as soon as pieces fit."""
    if len(text) <= limit:
        return [text]

    pieces: list[str] = []
    for para in _PARAGRAPH.split(text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= limit:
            pieces.append(para)
            continue
        sentences = _SENTENCE.split(para)
        current = ""
        for sentence in sentences:
            if len(sentence) > limit:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.extend(_hard_split(sentence, limit))
                continue
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= limit:
                current = candidate
            else:
                pieces.append(current)
                current = sentence
        if current:
            pieces.append(current)
    return pieces or [text[:limit]]


def chunk_document(document: Document, config: ChunkConfig | None = None) -> list[Chunk]:
    config = config or ChunkConfig()
    chunks: list[Chunk] = []

    for section in document.sections:
        pieces = _split_to_limit(section.text.strip(), config.max_chars)

        # Merge runs of small pieces so a bulleted section does not become
        # twenty near-useless chunks, while still respecting max_chars.
        merged: list[str] = []
        for piece in pieces:
            if merged and len(merged[-1]) + len(piece) + 1 <= config.max_chars:
                merged[-1] = f"{merged[-1]}\n{piece}"
            else:
                merged.append(piece)

        previous_tail = ""
        for piece in merged:
            body = f"{previous_tail}\n{piece}".strip() if previous_tail else piece
            # Drop fragments that carry no retrievable meaning, unless the whole
            # section is that short — then it is all we have.
            if len(body) < config.min_chars and len(merged) > 1 and chunks:
                previous_tail = piece[-config.overlap_chars :]
                continue
            chunks.append(
                Chunk(
                    chunk_id=content_id(document.doc_id, section.label, str(len(chunks)), body[:64]),
                    doc_id=document.doc_id,
                    text=body,
                    ordinal=len(chunks),
                    section_label=section.label,
                    filename=document.filename,
                )
            )
            previous_tail = piece[-config.overlap_chars :] if config.overlap_chars else ""

    return chunks
