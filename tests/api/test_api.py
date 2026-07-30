"""HTTP surface: status codes carry meaning, so they are asserted explicitly."""

from __future__ import annotations

from aidoctor import __version__


def test_root_carries_the_not_medical_disclaimer(client):
    body = client.get("/").json()
    assert "Not medical software" in body["disclaimer"]
    assert body["version"] == __version__


def test_health_reports_the_active_backends(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["vector_backend"] == "qdrant"
    assert body["embedder"] == "hashing"
    assert body["documents"] == 0


def test_metrics_lists_supported_extensions(client):
    body = client.get("/api/v1/metrics").json()
    assert ".pdf" in body["supported_extensions"]
    assert body["embedding_dimensions"] == 256


def test_openapi_schema_is_served(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "AI Doctor"
    assert "/api/v1/ask" in schema["paths"]


def test_ingest_then_ask_round_trip(client, upload):
    created = upload(client)
    assert created.status_code == 201
    body = created.json()
    assert body["source_type"] == "docx"
    assert body["chunks"] > 0
    assert body["replaced_chunks"] == 0

    answer = client.post("/api/v1/ask", json={"question": "how do I reset my password"}).json()
    assert not answer["escalated"]
    assert answer["citations"]
    assert answer["intent"] == "answer"
    assert answer["handler"] == "grounded-answer"
    assert answer["passages"]


def test_reingest_replaces_rather_than_duplicates(client, upload):
    first = upload(client).json()
    second = upload(client).json()
    assert second["doc_id"] == first["doc_id"]
    assert second["replaced_chunks"] == first["chunks"]
    assert len(client.get("/api/v1/documents").json()) == 1
    assert client.get("/api/v1/health").json()["chunks"] == first["chunks"]


def test_out_of_corpus_question_is_refused_over_http(client, upload):
    upload(client)
    answer = client.post("/api/v1/ask", json={"question": "who won the 1998 world cup"}).json()
    assert answer["escalated"]
    assert answer["citations"] == []
    assert answer["confidence"] == 0.0


def test_search_modes_are_selectable(client, upload):
    upload(client)
    for mode in ("hybrid", "dense", "lexical"):
        body = client.post("/api/v1/search", json={"query": "licence charges", "mode": mode}).json()
        assert body["mode"] == mode
        if body["results"]:
            assert body["results"][0]["method"] in {"hybrid", "dense", "lexical"}


def test_invalid_search_mode_is_rejected(client):
    assert client.post("/api/v1/search", json={"query": "x", "mode": "telepathy"}).status_code == 422


def test_search_limit_is_bounded(client):
    assert client.post("/api/v1/search", json={"query": "x", "limit": 999}).status_code == 422


def test_documents_can_be_listed_and_deleted(client, upload):
    doc_id = upload(client).json()["doc_id"]
    assert [d["doc_id"] for d in client.get("/api/v1/documents").json()] == [doc_id]

    deleted = client.delete(f"/api/v1/documents/{doc_id}")
    assert deleted.status_code == 200
    assert deleted.json()["removed_chunks"] > 0
    assert client.get("/api/v1/documents").json() == []
    assert client.get("/api/v1/health").json()["chunks"] == 0


def test_deleting_an_unknown_document_is_404(client):
    assert client.delete("/api/v1/documents/does-not-exist").status_code == 404


def test_unsupported_file_type_is_415(client, upload):
    assert upload(client, name="archive.zip", payload=b"PK\x03\x04").status_code == 415


def test_empty_upload_is_400(client, upload):
    assert upload(client, name="empty.txt", payload=b"").status_code == 400


def test_unreadable_but_supported_file_is_422(client, upload):
    """A .pdf that is not really a PDF: the type is supported, the file is not
    readable. That is a different failure from an unsupported type."""
    assert upload(client, name="broken.pdf", payload=b"not a pdf at all").status_code == 422


def test_blank_question_is_422(client):
    assert client.post("/api/v1/ask", json={"question": ""}).status_code == 422


def test_missing_question_field_is_422(client):
    assert client.post("/api/v1/ask", json={}).status_code == 422


def test_inventory_intent_routes_without_retrieval(client, upload):
    upload(client)
    answer = client.post("/api/v1/ask", json={"question": "what documents do you have"}).json()
    assert answer["intent"] == "inventory"
    assert "handbook.docx" in answer["answer"]
