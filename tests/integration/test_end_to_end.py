"""End-to-end across every format, through the real HTTP surface.

These use genuine files produced by reportlab, python-docx, python-pptx and
openpyxl — the point is that the whole pipeline survives real serialisation, not
a fixture string.
"""

from __future__ import annotations

import pytest

from tests.conftest import as_upload

pytestmark = pytest.mark.integration


def test_every_format_ingests_and_becomes_searchable(client, all_files):
    for path in all_files:
        response = client.post("/api/v1/ingest", files=as_upload(path))
        assert response.status_code == 201, f"{path.name}: {response.text}"
        assert response.json()["chunks"] > 0

    assert len(client.get("/api/v1/documents").json()) == len(all_files)
    assert client.get("/api/v1/health").json()["chunks"] > 0


def test_answers_cite_the_format_they_came_from(client, pdf_file, xlsx_file):
    client.post("/api/v1/ingest", files=as_upload(pdf_file))
    client.post("/api/v1/ingest", files=as_upload(xlsx_file))

    pdf_answer = client.post("/api/v1/ask", json={"question": "are licence keys transferable"}).json()
    assert not pdf_answer["escalated"]
    assert any("manual.pdf" in c for c in pdf_answer["citations"])
    assert any("page" in c for c in pdf_answer["citations"])


def test_spreadsheet_answers_carry_the_header_context(client, xlsx_file):
    """The reason headers are repeated onto every row at extraction time."""
    client.post("/api/v1/ingest", files=as_upload(xlsx_file))
    body = client.post("/api/v1/search", json={"query": "EMEA amount", "mode": "lexical"}).json()
    assert body["results"]
    assert "Region: EMEA" in body["results"][0]["text"]


def test_deleting_one_document_leaves_the_others_answerable(client, pdf_file, docx_file):
    pdf_id = client.post("/api/v1/ingest", files=as_upload(pdf_file)).json()["doc_id"]
    client.post("/api/v1/ingest", files=as_upload(docx_file))

    client.delete(f"/api/v1/documents/{pdf_id}")

    answer = client.post("/api/v1/ask", json={"question": "how do I reset my password"}).json()
    assert not answer["escalated"], "the surviving document must still answer"
    assert all("manual.pdf" not in c for c in answer["citations"])


def test_full_corpus_still_refuses_what_it_does_not_know(client, all_files):
    for path in all_files:
        client.post("/api/v1/ingest", files=as_upload(path))
    answer = client.post("/api/v1/ask", json={"question": "what is the population of Ulaanbaatar"}).json()
    assert answer["escalated"], "a six-document corpus must not start guessing"


def test_pipeline_is_deterministic_across_two_identical_runs(settings, all_files):
    """Same corpus, same question, same answer — no ordering nondeterminism."""
    from fastapi.testclient import TestClient

    from aidoctor.config.settings import Settings
    from aidoctor.main import create_app

    def run() -> dict:
        isolated = Settings(
            database_url="sqlite:///:memory:",
            vector_backend="qdrant",
            embedding_dimensions=256,
            qdrant_collection="determinism",
        )
        client = TestClient(create_app(isolated))
        for path in all_files:
            client.post("/api/v1/ingest", files=as_upload(path))
        return client.post("/api/v1/ask", json={"question": "how do I reset my password"}).json()

    first, second = run(), run()
    assert first["answer"] == second["answer"]
    assert first["citations"] == second["citations"]
