"""SQLAlchemy metadata store.

The vector store holds chunks and embeddings; this holds the *record* of what was
ingested — filename, type, section and chunk counts, timestamps. Separating them
matters because they have different lifecycles: you re-embed when the model
changes without losing ingest history, and you can answer "what do we have?"
without touching the vector index.

SQLite by default, Postgres by URL. The models are plain enough that the switch
is genuinely just ``DATABASE_URL`` — no dialect-specific types are used.
"""

from __future__ import annotations

from datetime import datetime, timezone  # noqa: UP017
from pathlib import Path

from sqlalchemy import String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class DocumentRecord(Base):
    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(16))
    section_count: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
    ingested_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)  # noqa: UP017
    )


class MetadataStore:
    def __init__(self, database_url: str) -> None:
        if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
            path = Path(database_url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread: FastAPI serves on a thread pool and SQLite objects to
        # cross-thread use by default.
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        kwargs: dict = {"future": True, "connect_args": connect_args}
        if ":memory:" in database_url:
            # An in-memory SQLite database lives inside a single connection, so the
            # default pool hands out a *different, empty* database per checkout —
            # create_all runs on one connection and the first query fails on
            # another with "no such table". StaticPool reuses one connection so
            # the schema and the data are visible to every session.
            kwargs["poolclass"] = StaticPool
        self.engine = create_engine(database_url, **kwargs)
        Base.metadata.create_all(self.engine)

    def upsert_document(
        self, doc_id: str, filename: str, source_type: str, section_count: int, chunk_count: int
    ) -> DocumentRecord:
        with Session(self.engine) as session:
            record = session.get(DocumentRecord, doc_id)
            if record is None:
                record = DocumentRecord(doc_id=doc_id)
                session.add(record)
            record.filename = filename
            record.source_type = source_type
            record.section_count = section_count
            record.chunk_count = chunk_count
            record.ingested_at = datetime.now(timezone.utc)  # noqa: UP017
            session.commit()
            session.refresh(record)
            session.expunge(record)
            return record

    def get(self, doc_id: str) -> DocumentRecord | None:
        with Session(self.engine) as session:
            record = session.get(DocumentRecord, doc_id)
            if record is not None:
                session.expunge(record)
            return record

    def list_documents(self) -> list[DocumentRecord]:
        with Session(self.engine) as session:
            records = list(session.scalars(select(DocumentRecord).order_by(DocumentRecord.filename)))
            for record in records:
                session.expunge(record)
            return records

    def delete(self, doc_id: str) -> bool:
        with Session(self.engine) as session:
            record = session.get(DocumentRecord, doc_id)
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    def stats(self) -> dict[str, int]:
        with Session(self.engine) as session:
            return {
                "documents": int(session.scalar(select(func.count(DocumentRecord.doc_id))) or 0),
                "chunks": int(session.scalar(select(func.sum(DocumentRecord.chunk_count))) or 0),
            }
