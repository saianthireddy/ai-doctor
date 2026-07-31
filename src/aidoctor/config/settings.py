"""Environment-driven settings.

Every value has a default that works offline with no services, so ``uvicorn
aidoctor.main:app`` runs on a clean machine. Production swaps backends by
environment variable only — no code change, which is the whole point of the
interfaces in the layers below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "AI Doctor"
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))

    # Metadata store. SQLite by default; a postgresql:// URL is honoured as-is.
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./data/aidoctor.db")
    )

    # Vector store: memory | qdrant. Qdrant defaults to embedded mode.
    vector_backend: str = field(default_factory=lambda: os.getenv("VECTOR_BACKEND", "qdrant"))
    qdrant_url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", ""))
    qdrant_collection: str = field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "aidoctor"))

    embedder: str = field(default_factory=lambda: os.getenv("EMBEDDER", "hashing"))
    embedding_dimensions: int = field(default_factory=lambda: _int("EMBEDDING_DIMENSIONS", 384))
    reranker: str = field(default_factory=lambda: os.getenv("RERANKER", "lexical-overlap"))
    llm: str = field(default_factory=lambda: os.getenv("LLM", "extractive"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    chunk_max_chars: int = field(default_factory=lambda: _int("CHUNK_MAX_CHARS", 1200))
    chunk_overlap_chars: int = field(default_factory=lambda: _int("CHUNK_OVERLAP_CHARS", 150))
    candidate_k: int = field(default_factory=lambda: _int("CANDIDATE_K", 12))
    context_k: int = field(default_factory=lambda: _int("CONTEXT_K", 4))
    # 0.15 rather than the original 0.12, chosen from the threshold sweep in
    # docs/evaluation.md. On the labelled set 0.12 answered 50% of unanswerable
    # questions; 0.15 answers 33% and wrongly refuses *nothing* that 0.12
    # answered, so the change costs no recall. Going further does cost: 0.25
    # reaches 17% false answers but wrongly refuses 20% of answerable ones.
    min_relevance: float = field(default_factory=lambda: _float("MIN_RELEVANCE", 0.15))

    max_upload_mb: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 25))
    enable_metrics: bool = field(default_factory=lambda: _bool("ENABLE_METRICS", True))

    @property
    def uses_openai(self) -> bool:
        return "openai" in {self.embedder, self.llm}


settings = Settings()
