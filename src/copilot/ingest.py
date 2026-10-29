"""Ingestion: parse -> attach access rights -> chunk -> embed -> Qdrant +
Postgres. Re-ingesting the same file is a no-op (sha256), a new revision of
an existing document becomes the current one if its effective date is newer
and it is not marked superseded."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .access import AccessPolicy
from .chunking import chunk_document
from .db import ChunkRow, Database, Document
from .embeddings import Embedder
from .parsing import ParsedDocument, parse_any
from .sparse import BM25Encoder
from .store import VectorStore
from .text import codes

log = logging.getLogger(__name__)
INACTIVE = {"superseded", "withdrawn", "obsolete", "draft"}


@dataclass
class IngestResult:
    file: str
    doc_no: str
    revision: str
    chunks: int
    skipped: bool = False


class Ingestor:
    def __init__(self, store: VectorStore, db: Database | None, embedder: Embedder, bm25: BM25Encoder,
                 policy: AccessPolicy, max_chars: int = 1100, overlap: int = 150):
        self.store, self.db, self.emb, self.bm25, self.policy = store, db, embedder, bm25, policy
        self.max_chars, self.overlap = max_chars, overlap

    def ingest_file(self, path: str | Path, meta: dict | None = None, roles: list[str] | None = None,
                    force: bool = False) -> IngestResult:
        path = Path(path)
        doc = parse_any(path, meta)
        if self.db and not force:
            existing = self.db.find_by_hash(doc.sha256)
            if existing:
                return IngestResult(path.name, existing.doc_no, existing.revision, existing.n_chunks, skipped=True)
        return self.ingest_parsed(doc, roles)

    def ingest_parsed(self, doc: ParsedDocument, roles: list[str] | None = None) -> IngestResult:
        m = doc.meta
        doc_no, rev = m.get("doc_no", doc.source), str(m.get("revision", "-"))
        classification = m.get("classification", "internal")
        doc_roles = sorted(set(roles) | self.policy.superuser_roles) if roles else \
            self.policy.roles_for_document(doc_no, rev, classification)
        # codes mentioned anywhere in the document (RS-40, MC-504, ...): a chunk
        # from a table does not repeat the part number given in the scope
        doc_codes = sorted(codes(doc.full_text) | codes(m.get("title", "")) | {doc_no.upper()})
        chunks = chunk_document(doc, self.max_chars, self.overlap,
                                extra_meta={"roles": doc_roles, "is_current": m.get("status", "") not in INACTIVE,
                                            "doc_codes": doc_codes})
        texts = [c.index_text for c in chunks]
        dense = self.emb.embed(texts)
        sparse = [self.bm25.encode_doc(t) for t in texts]
        self.store.delete_document(doc_no, rev)
        self.store.upsert([c.payload() for c in chunks], dense, sparse)
        if self.db:
            self.db.add_document(
                Document(doc_no=doc_no, revision=rev, title=m.get("title", doc_no)[:300],
                         doc_type=m.get("doc_type", ""), status=m.get("status", ""),
                         effective=m.get("effective", ""), owner=m.get("owner", ""),
                         classification=classification, roles=doc_roles, source_file=doc.source,
                         sha256=doc.sha256, n_pages=doc.n_pages),
                [ChunkRow(chunk_id=c.chunk_id, section=c.section[:300], page=c.page, text=c.text) for c in chunks])
        self._update_current(doc_no)
        log.info("ingested %s rev %s: %d chunks", doc_no, rev, len(chunks))
        return IngestResult(doc.source, doc_no, rev, len(chunks))

    def _update_current(self, doc_no: str) -> None:
        """Newest effective, non-superseded revision is current."""
        revs = []
        if self.db:
            revs = [(d.effective, d.revision, d.status) for d in self.db.revisions(doc_no)]
        else:
            seen = {(p["effective"], p["revision"], p["status"]) for p in self.store.scroll_all()
                    if p["doc_no"] == doc_no}
            revs = list(seen)
        active = [r for r in revs if r[2] not in INACTIVE] or revs
        if not active:
            return
        current = max(active)[1]
        self.store.set_current(doc_no, current)
        if self.db:
            self.db.set_current(doc_no, current)

    def ingest_dir(self, folder: str | Path) -> list[IngestResult]:
        out = []
        for f in sorted(Path(folder).iterdir()):
            if f.suffix.lower() in (".pdf", ".md", ".txt"):
                out.append(self.ingest_file(f))
        return out
