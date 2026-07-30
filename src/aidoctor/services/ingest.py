"""Ingestion: extract, chunk, embed, index, record.

The ordering here is deliberate. Chunks are deleted from both indexes *before*
the new ones are written, so re-ingesting an edited file cannot leave orphaned
chunks from the previous version answering questions. Chunk ids are
content-derived, so unchanged chunks land on the same ids and the operation is
idempotent — ingesting the same file twice is a no-op, not a doubling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aidoctor.database.store import MetadataStore
from aidoctor.extractors.base import extract
from aidoctor.models.document import Document
from aidoctor.retrieval.hybrid import HybridRetriever
from aidoctor.services.chunker import ChunkConfig, chunk_document


@dataclass(frozen=True)
class IngestResult:
    doc_id: str
    filename: str
    source_type: str
    sections: int
    chunks: int
    replaced: int

    def as_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "filename": self.filename,
            "source_type": self.source_type,
            "sections": self.sections,
            "chunks": self.chunks,
            "replaced_chunks": self.replaced,
        }


class IngestService:
    def __init__(
        self, retriever: HybridRetriever, store: MetadataStore, chunk_config: ChunkConfig | None = None
    ) -> None:
        self.retriever = retriever
        self.store = store
        self.chunk_config = chunk_config or ChunkConfig()

    def ingest_path(self, path: Path | str) -> IngestResult:
        return self.ingest_document(extract(path))

    def ingest_document(self, document: Document) -> IngestResult:
        chunks = chunk_document(document, self.chunk_config)
        # Delete first: an edited file must not leave stale chunks behind.
        replaced = self.retriever.delete_document(document.doc_id)
        self.retriever.index(chunks)
        self.store.upsert_document(
            doc_id=document.doc_id,
            filename=document.filename,
            source_type=document.source_type.value,
            section_count=document.section_count,
            chunk_count=len(chunks),
        )
        return IngestResult(
            doc_id=document.doc_id,
            filename=document.filename,
            source_type=document.source_type.value,
            sections=document.section_count,
            chunks=len(chunks),
            replaced=replaced,
        )

    def delete(self, doc_id: str) -> int:
        removed = self.retriever.delete_document(doc_id)
        self.store.delete(doc_id)
        return removed
