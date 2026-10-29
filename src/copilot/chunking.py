"""Structure-aware chunking.

One chunk per document section where possible. Sections that are too long
are split on paragraph boundaries with LangChain's recursive splitter;
tables are split by rows and keep their header in every piece. Each chunk
carries a short context line (doc number, revision, title, section) that is
prepended for embedding and keyword search, so a chunk like "M10 45 Nm" still
knows it belongs to the gearbox flange work instruction.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .parsing import Block, ParsedDocument, linearise_table


@dataclass
class Chunk:
    chunk_id: str
    doc_no: str
    revision: str
    title: str
    section: str
    page: int
    text: str                      # the section content
    meta: dict = field(default_factory=dict)

    @property
    def context(self) -> str:
        return f"{self.doc_no} Rev {self.revision} - {self.title} > {self.section}"

    @property
    def index_text(self) -> str:
        """What gets embedded and keyword indexed."""
        return f"{self.context}\n{self.text}"

    def payload(self) -> dict:
        d = asdict(self)
        d.update(self.meta)
        d.pop("meta")
        return d


def _split_table(block: Block, max_chars: int) -> list[str]:
    if not block.rows or len(block.text) <= max_chars:
        return [block.text]
    header, *body = block.rows
    pieces, cur = [], []
    for row in body:
        cur.append(row)
        if len(linearise_table([header] + cur)) > max_chars and len(cur) > 1:
            pieces.append(linearise_table([header] + cur[:-1]))
            cur = [row]
    if cur:
        pieces.append(linearise_table([header] + cur))
    return pieces


def chunk_document(doc: ParsedDocument, max_chars: int = 1100, overlap: int = 150,
                   extra_meta: dict | None = None) -> list[Chunk]:
    m = doc.meta
    doc_no, rev = m.get("doc_no", doc.source), str(m.get("revision", "-"))
    title = m.get("title", doc_no)
    splitter = RecursiveCharacterTextSplitter(chunk_size=max_chars, chunk_overlap=overlap,
                                              separators=["\n\n", "\n", ". ", " "])
    chunks: list[Chunk] = []
    for sec in doc.sections:
        # build groups of blocks that fit into max_chars
        groups: list[tuple[int, str]] = []
        buf, buf_page = [], sec.page
        for b in sec.blocks:
            parts = _split_table(b, max_chars) if b.kind == "table" else [b.text]
            for part in parts:
                if len(part) > max_chars:
                    if buf:
                        groups.append((buf_page, "\n".join(buf)))
                        buf = []
                    groups.extend((b.page, p) for p in splitter.split_text(part))
                    continue
                if buf and sum(len(x) + 1 for x in buf) + len(part) > max_chars:
                    groups.append((buf_page, "\n".join(buf)))
                    buf = []
                if not buf:
                    buf_page = b.page
                buf.append(part)
        if buf:
            groups.append((buf_page, "\n".join(buf)))
        for page, text in groups:
            idx = len(chunks)
            chunks.append(Chunk(
                chunk_id=f"{doc_no}:{rev}:{idx:03d}", doc_no=doc_no, revision=rev, title=title,
                section=sec.heading, page=page, text=text,
                meta={
                    "doc_type": m.get("doc_type", ""), "status": m.get("status", ""),
                    "effective": m.get("effective", ""), "owner": m.get("owner", ""),
                    "classification": m.get("classification", "internal"),
                    "source": doc.source, **(extra_meta or {}),
                },
            ))
    return chunks
