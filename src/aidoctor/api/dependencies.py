"""Process-wide wiring, built once.

Everything is constructed from :mod:`aidoctor.config.settings`, so switching from
embedded Qdrant to a Qdrant server, or from the offline extractive generator to
OpenAI, is an environment change rather than a code change. ``build_container``
is exposed so tests can construct an isolated stack instead of monkeypatching
module globals.
"""

from __future__ import annotations

from dataclasses import dataclass

from aidoctor.agents.router import Router
from aidoctor.config.settings import Settings
from aidoctor.config.settings import settings as default_settings
from aidoctor.database.store import MetadataStore
from aidoctor.embeddings.base import build_embedder
from aidoctor.llms.base import build_llm
from aidoctor.reranker.base import build_reranker
from aidoctor.retrieval.hybrid import HybridRetriever, RetrievalConfig
from aidoctor.services.answerer import Answerer
from aidoctor.services.chunker import ChunkConfig
from aidoctor.services.ingest import IngestService
from aidoctor.vectorstore.qdrant_store import build_vector_store


@dataclass
class Container:
    settings: Settings
    store: MetadataStore
    retriever: HybridRetriever
    ingest: IngestService
    answerer: Answerer
    router: Router

    @property
    def stats(self) -> dict[str, int]:
        base = self.store.stats()
        base["indexed_chunks"] = self.retriever.size
        return base


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or default_settings
    embedder = build_embedder(settings.embedder, settings.embedding_dimensions)

    kwargs = {"collection": settings.qdrant_collection} if settings.vector_backend == "qdrant" else {}
    if settings.vector_backend == "qdrant" and settings.qdrant_url:
        kwargs["url"] = settings.qdrant_url
    vector_store = build_vector_store(settings.vector_backend, dimensions=embedder.dimensions, **kwargs)

    retriever = HybridRetriever(
        vector_store,
        embedder,
        RetrievalConfig(final_k=settings.candidate_k),
    )
    store = MetadataStore(settings.database_url)
    ingest = IngestService(
        retriever,
        store,
        ChunkConfig(max_chars=settings.chunk_max_chars, overlap_chars=settings.chunk_overlap_chars),
    )
    answerer = Answerer(
        retriever,
        build_reranker(settings.reranker),
        build_llm(settings.llm),
        candidate_k=settings.candidate_k,
        context_k=settings.context_k,
        min_score=settings.min_relevance,
    )
    router = Router(answerer, inventory=lambda: [d.filename for d in store.list_documents()])
    return Container(
        settings=settings,
        store=store,
        retriever=retriever,
        ingest=ingest,
        answerer=answerer,
        router=router,
    )
