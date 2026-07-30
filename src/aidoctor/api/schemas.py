"""Request and response models. Pydantic lives at the HTTP boundary only."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class PassageOut(BaseModel):
    text: str
    citation: str
    section_label: str
    filename: str
    score: float
    method: str


class AnswerOut(BaseModel):
    question: str
    answer: str
    grounded: bool
    escalated: bool
    confidence: float
    citations: list[str] = []
    passages: list[PassageOut] = []
    intent: str | None = None
    handler: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=6, ge=1, le=50)
    mode: str = Field(default="hybrid", pattern="^(hybrid|dense|lexical)$")


class SearchOut(BaseModel):
    query: str
    mode: str
    results: list[PassageOut] = []


class IngestOut(BaseModel):
    doc_id: str
    filename: str
    source_type: str
    sections: int
    chunks: int
    replaced_chunks: int


class DocumentOut(BaseModel):
    doc_id: str
    filename: str
    source_type: str
    section_count: int
    chunk_count: int


class HealthOut(BaseModel):
    status: str
    version: str
    vector_backend: str
    embedder: str
    reranker: str
    llm: str
    documents: int
    chunks: int


class MetricsOut(BaseModel):
    documents: int
    indexed_chunks: int
    vector_backend: str
    embedding_dimensions: int
    supported_extensions: list[str]
