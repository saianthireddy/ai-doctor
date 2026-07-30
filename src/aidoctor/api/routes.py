"""REST endpoints.

Upload handling enforces two limits before anything touches disk: the extension
must be supported, and the body must be under ``max_upload_mb``. Rejecting early
is the difference between a 413 and an out-of-memory kill.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from aidoctor import __version__
from aidoctor.api.schemas import (
    AnswerOut,
    AskRequest,
    DocumentOut,
    HealthOut,
    IngestOut,
    MetricsOut,
    PassageOut,
    SearchOut,
    SearchRequest,
)
from aidoctor.extractors.base import (
    ExtractionError,
    UnsupportedSourceError,
    supported_extensions,
)
from aidoctor.models.document import ScoredChunk

router = APIRouter()


def _container(request: Request):
    return request.app.state.container


def _passage(scored: ScoredChunk) -> PassageOut:
    return PassageOut(
        text=scored.chunk.text,
        citation=scored.chunk.citation,
        section_label=scored.chunk.section_label,
        filename=scored.chunk.filename,
        score=round(scored.score, 4),
        method=scored.method,
    )


@router.get("/health", response_model=HealthOut, tags=["system"])
def health(request: Request) -> HealthOut:
    container = _container(request)
    stats = container.stats
    settings = container.settings
    return HealthOut(
        status="ok",
        version=__version__,
        vector_backend=settings.vector_backend,
        embedder=settings.embedder,
        reranker=settings.reranker,
        llm=settings.llm,
        documents=stats["documents"],
        chunks=stats["indexed_chunks"],
    )


@router.get("/metrics", response_model=MetricsOut, tags=["system"])
def metrics(request: Request) -> MetricsOut:
    container = _container(request)
    return MetricsOut(
        documents=container.stats["documents"],
        indexed_chunks=container.retriever.size,
        vector_backend=container.settings.vector_backend,
        embedding_dimensions=container.retriever.embedder.dimensions,
        supported_extensions=list(supported_extensions()),
    )


@router.post("/ingest", response_model=IngestOut, status_code=201, tags=["ingest"])
async def ingest(request: Request, file: UploadFile = File(...)) -> IngestOut:
    container = _container(request)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in supported_extensions():
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type {suffix or '(none)'}. "
            f"Supported: {', '.join(supported_extensions())}",
        )

    payload = await file.read()
    limit = container.settings.max_upload_mb * 1024 * 1024
    if len(payload) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {container.settings.max_upload_mb} MB limit",
        )
    if not payload:
        raise HTTPException(status_code=400, detail="Empty file")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(file.filename or "upload").name
        path.write_bytes(payload)
        try:
            result = container.ingest.ingest_path(path)
        except UnsupportedSourceError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        except ExtractionError as exc:
            # 422: the type is supported but this particular file is unreadable
            # (e.g. a scanned PDF with no text layer).
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return IngestOut(**result.as_dict())


@router.get("/documents", response_model=list[DocumentOut], tags=["ingest"])
def list_documents(request: Request) -> list[DocumentOut]:
    return [
        DocumentOut(
            doc_id=d.doc_id,
            filename=d.filename,
            source_type=d.source_type,
            section_count=d.section_count,
            chunk_count=d.chunk_count,
        )
        for d in _container(request).store.list_documents()
    ]


@router.delete("/documents/{doc_id}", tags=["ingest"])
def delete_document(request: Request, doc_id: str) -> dict:
    container = _container(request)
    if container.store.get(doc_id) is None:
        raise HTTPException(status_code=404, detail=f"No document {doc_id}")
    removed = container.ingest.delete(doc_id)
    return {"doc_id": doc_id, "removed_chunks": removed}


@router.post("/ask", response_model=AnswerOut, tags=["query"])
def ask(request: Request, payload: AskRequest) -> AnswerOut:
    result = _container(request).router.route(payload.question)
    return AnswerOut(
        question=payload.question,
        answer=result.text,
        grounded=not result.escalated,
        escalated=result.escalated,
        confidence=result.confidence,
        citations=result.citations,
        passages=[_passage(p) for p in result.passages],
        intent=result.intent,
        handler=result.handler,
    )


@router.post("/search", response_model=SearchOut, tags=["query"])
def search(request: Request, payload: SearchRequest) -> SearchOut:
    retriever = _container(request).retriever
    if payload.mode == "dense":
        results = retriever.search_dense(payload.query, limit=payload.limit)
    elif payload.mode == "lexical":
        results = retriever.search_lexical(payload.query, limit=payload.limit)
    else:
        results = retriever.search(payload.query, limit=payload.limit)
    return SearchOut(query=payload.query, mode=payload.mode, results=[_passage(r) for r in results])
