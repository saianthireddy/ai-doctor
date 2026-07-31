"""The metadata store, held to one contract across SQLite and Postgres.

Until this file existed the store was only ever exercised *through* the API,
which is why the README could say no more than "covered via API tests" — and why
the Postgres row said "Declared". An ORM hides real differences between engines
(identifier quoting, integer types, transaction behaviour, how ``SUM`` over an
empty table comes back), so "SQLAlchemy supports Postgres" is not evidence that
this schema does.

Postgres is skipped unless ``POSTGRES_URL`` is set. Local runs stay offline; CI
starts a real Postgres service container, which is what makes the claim real.
"""

from __future__ import annotations

import os

import pytest

from aidoctor.database.store import MetadataStore


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "postgres":
        url = os.environ.get("POSTGRES_URL")
        if not url:
            pytest.skip("POSTGRES_URL not set; Postgres is exercised in CI")
        store = MetadataStore(url)
        # A real database persists between tests. Start from empty so counts
        # mean what the assertions below think they mean.
        for record in store.list_documents():
            store.delete(record.doc_id)
        return store
    return MetadataStore(f"sqlite:///{tmp_path / 'meta.db'}")


def _add(store, doc_id="d1", filename="handbook.docx", sections=3, chunks=8):
    return store.upsert_document(
        doc_id=doc_id,
        filename=filename,
        source_type="docx",
        section_count=sections,
        chunk_count=chunks,
    )


def test_upsert_then_get_round_trips_every_field(store):
    _add(store)
    record = store.get("d1")
    assert record is not None
    assert record.filename == "handbook.docx"
    assert record.source_type == "docx"
    assert record.section_count == 3
    assert record.chunk_count == 8


def test_get_unknown_document_returns_none(store):
    assert store.get("nope") is None


def test_upsert_replaces_rather_than_duplicating(store):
    """Re-ingesting a document must not leave two rows behind.

    This is the failure that silently doubles a corpus: the second ingest looks
    fine, and only the counts give it away.
    """
    _add(store, chunks=8)
    _add(store, chunks=11)
    assert len(store.list_documents()) == 1
    assert store.get("d1").chunk_count == 11


def test_list_documents_is_ordered_by_filename(store):
    _add(store, doc_id="d1", filename="zebra.md")
    _add(store, doc_id="d2", filename="alpha.md")
    assert [r.filename for r in store.list_documents()] == ["alpha.md", "zebra.md"]


def test_delete_returns_whether_it_removed_anything(store):
    _add(store)
    assert store.delete("d1") is True
    assert store.delete("d1") is False
    assert store.get("d1") is None


def test_stats_sum_chunk_counts_across_documents(store):
    _add(store, doc_id="d1", filename="a.md", chunks=4)
    _add(store, doc_id="d2", filename="b.md", chunks=6)
    assert store.stats() == {"documents": 2, "chunks": 10}


def test_stats_on_an_empty_store_are_zero_not_null(store):
    """``SUM`` over no rows returns NULL, not 0, on both engines.

    The store coalesces it. Without that this returns ``{"chunks": None}`` and
    the /stats endpoint serialises a null where an integer is documented.
    """
    assert store.stats() == {"documents": 0, "chunks": 0}


def test_ingested_at_is_timezone_aware_and_advances_on_reingest(store):
    first = _add(store).ingested_at
    second = _add(store).ingested_at
    assert second >= first
