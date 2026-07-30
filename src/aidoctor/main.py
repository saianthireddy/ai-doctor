"""ASGI entrypoint: ``uvicorn aidoctor.main:app``."""

from __future__ import annotations

from fastapi import FastAPI

from aidoctor import __version__
from aidoctor.api.dependencies import build_container
from aidoctor.api.routes import router
from aidoctor.config.settings import Settings

DESCRIPTION = """
Document intelligence over your own files: extract, chunk, embed, hybrid-search,
rerank, and answer **with citations** — or refuse when the corpus does not
contain the answer.

**Not medical software.** Despite the name, AI Doctor diagnoses documents, not
people. It provides no medical advice of any kind.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="AI Doctor",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=[
            {"name": "system", "description": "Health and metrics"},
            {"name": "ingest", "description": "Add and manage documents"},
            {"name": "query", "description": "Ask questions and search"},
        ],
    )
    app.state.container = build_container(settings)
    app.include_router(router, prefix="/api/v1")

    @app.get("/", tags=["system"])
    def root() -> dict:
        return {
            "name": "AI Doctor",
            "version": __version__,
            "docs": "/docs",
            "disclaimer": "Not medical software. Diagnoses documents, not people.",
        }

    return app


app = create_app()
