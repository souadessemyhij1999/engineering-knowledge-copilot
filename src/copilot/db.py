"""Relational side: document registry, chunk texts, query log and user
feedback. PostgreSQL in Docker, SQLite locally and in tests."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_no: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="")
    effective: Mapped[str] = mapped_column(String(10), default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    classification: Mapped[str] = mapped_column(String(32), default="internal")
    roles: Mapped[list] = mapped_column(JSON, default=list)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    source_file: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    n_pages: Mapped[int] = mapped_column(Integer, default=1)
    n_chunks: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    chunks: Mapped[list["ChunkRow"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class ChunkRow(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(100), unique=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    section: Mapped[str] = mapped_column(String(300))
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    document: Mapped[Document] = relationship(back_populates="chunks")


class QueryLog(Base):
    __tablename__ = "query_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    username: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16))
    abstained: Mapped[bool] = mapped_column(Boolean)
    guard_passed: Mapped[bool] = mapped_column(Boolean)
    top_score: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float)
    sources: Mapped[list] = mapped_column(JSON, default=list)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("query_log.id", ondelete="CASCADE"))
    helpful: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class Database:
    def __init__(self, url: str):
        if url.startswith("sqlite"):
            kw = {"connect_args": {"check_same_thread": False}}
            if url in ("sqlite://", "sqlite:///:memory:"):
                kw["poolclass"] = StaticPool      # one shared in-memory DB across threads
        else:
            kw = {"pool_pre_ping": True}
        self.engine = create_engine(url, **kw)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.Session()

    def find_by_hash(self, sha: str) -> Document | None:
        with self.session() as s:
            return s.scalar(select(Document).where(Document.sha256 == sha))

    def add_document(self, doc: Document, chunks: list[ChunkRow]) -> Document:
        with self.session() as s, s.begin():
            # same doc_no + revision re-ingested: replace
            for old in s.scalars(select(Document).where(Document.doc_no == doc.doc_no,
                                                        Document.revision == doc.revision)):
                s.delete(old)
            s.flush()
            doc.chunks = chunks
            doc.n_chunks = len(chunks)
            s.add(doc)
        return doc

    def revisions(self, doc_no: str) -> list[Document]:
        with self.session() as s:
            return list(s.scalars(select(Document).where(Document.doc_no == doc_no)))

    def set_current(self, doc_no: str, revision: str) -> None:
        with self.session() as s, s.begin():
            for d in s.scalars(select(Document).where(Document.doc_no == doc_no)):
                d.is_current = d.revision == revision

    def list_documents(self) -> list[Document]:
        with self.session() as s:
            return list(s.scalars(select(Document).order_by(Document.doc_no, Document.revision)))

    def log_query(self, **fields) -> int:
        with self.session() as s, s.begin():
            row = QueryLog(**fields)
            s.add(row)
            s.flush()
            return row.id

    def add_feedback(self, query_id: int, helpful: bool, comment: str = "") -> bool:
        with self.session() as s, s.begin():
            if s.get(QueryLog, query_id) is None:
                return False
            s.add(Feedback(query_id=query_id, helpful=helpful, comment=comment))
            return True

    def stats(self) -> dict:
        with self.session() as s:
            n_q = s.scalar(select(func.count(QueryLog.id))) or 0
            n_abs = s.scalar(select(func.count(QueryLog.id)).where(QueryLog.abstained.is_(True))) or 0
            n_fb = s.scalar(select(func.count(Feedback.id))) or 0
            n_up = s.scalar(select(func.count(Feedback.id)).where(Feedback.helpful.is_(True))) or 0
            lat = s.scalar(select(func.avg(QueryLog.latency_ms))) or 0.0
        return {"queries": n_q, "abstained": n_abs, "feedback": n_fb, "helpful": n_up, "avg_latency_ms": round(lat, 1)}
