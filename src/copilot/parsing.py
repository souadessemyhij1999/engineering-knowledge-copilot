"""PDF parsing: text + tables in reading order, cleaned of headers, footers
and watermarks, split into sections, with metadata recovered from the
printed title block.

Plain text and markdown files are supported too (for uploads), they skip the
layout part.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

WATERMARK_MIN_SIZE = 30.0       # anything printed this big is a stamp, not content
HEADING_MIN_SIZE = 11.0
TITLE_MIN_SIZE = 14.0
REPEAT_SHARE = 0.6               # a line on >=60 % of pages is header/footer
MARGIN_BAND = 0.055              # top/bottom 5.5 % of the page height = running header/footer

PAGE_RE = re.compile(r"^page\s+\d+\s+(of|/)\s+\d+$", re.I)
HEADING_NUM_RE = re.compile(r"^(?:\d+(?:\.\d+)*|D\d)\s+\S")

META_PATTERNS = {
    "doc_no": r"Document no\.\s+(\S+)",
    "revision": r"Revision\s+([A-Z0-9]+)\b",
    "doc_type": r"Document type\s+(.+?)\s+Status\b",
    "status": r"Status\s+(\w+)",
    "effective": r"Effective date\s+(\d{4}-\d{2}-\d{2})",
    "owner": r"Owner\s+(.+)$",
    "classification": r"Classification\s+(\w+)",
}


@dataclass
class Block:
    kind: str                 # "text" | "table"
    text: str                 # text used for retrieval (tables are linearised)
    page: int
    rows: list[list[str]] | None = None


@dataclass
class Section:
    heading: str
    page: int
    blocks: list[Block] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


@dataclass
class ParsedDocument:
    source: str
    sha256: str
    n_pages: int
    meta: dict
    sections: list[Section]

    @property
    def full_text(self) -> str:
        return "\n\n".join(f"{s.heading}\n{s.text}" for s in self.sections)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _norm_line(s: str) -> str:
    return re.sub(r"\d+", "#", s.strip().lower())


def clean_cell(c: str | None) -> str:
    if c is None:
        return ""
    return re.sub(r"\s+", " ", c).strip()


def linearise_table(rows: list[list[str]]) -> str:
    """One line per row, every value prefixed with its column header, so a
    row still makes sense when it lands in a chunk on its own."""
    if not rows:
        return ""
    header, *body = rows
    if not body:
        return " | ".join(header)
    lines = []
    for r in body:
        parts = []
        for h, v in zip(header, r):
            if v:
                parts.append(f"{h}: {v}" if h else v)
        lines.append("; ".join(parts))
    return "\n".join(lines)


def _page_items(page, page_no: int) -> list[tuple[float, str, object]]:
    """Return (top, kind, payload) items of one page in reading order."""
    page = page.filter(lambda o: o.get("object_type") != "char" or o.get("size", 0) < WATERMARK_MIN_SIZE)
    tables = page.find_tables()
    bboxes = [t.bbox for t in tables]

    def outside(obj):
        if obj.get("object_type") != "char":
            return True
        x, y = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return not any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in bboxes)

    h = page.height
    items: list[tuple[float, str, object]] = []
    for t in tables:
        rows = [[clean_cell(c) for c in r] for r in t.extract()]
        rows = [r for r in rows if any(r)]
        if rows:
            items.append((t.bbox[1], "table", rows))
    for line in page.filter(outside).extract_text_lines(return_chars=True):
        chars = [c for c in line["chars"] if c["text"].strip()]
        if not chars or line["top"] < h * MARGIN_BAND or line["bottom"] > h * (1 - MARGIN_BAND):
            continue
        size = max(c["size"] for c in chars)
        bold = sum("Bold" in c["fontname"] for c in chars) > len(chars) / 2
        items.append((line["top"], "line", {"text": line["text"].strip(), "size": size, "bold": bold,
                                             "top": line["top"], "bottom": line["bottom"]}))
    items.sort(key=lambda x: x[0])
    return items


def parse_pdf(path: str | Path) -> ParsedDocument:
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        pages = [_page_items(p, i + 1) for i, p in enumerate(pdf.pages)]
        n_pages = len(pdf.pages)

    # 1) header / footer lines: repeated on most pages or "page x of y"
    counts = Counter()
    for items in pages:
        counts.update({_norm_line(p["text"]) for _, k, p in items if k == "line"})
    repeated = {ln for ln, c in counts.items() if n_pages > 1 and c / n_pages >= REPEAT_SHARE}

    def is_noise(text: str) -> bool:
        return PAGE_RE.match(text) is not None or _norm_line(text) in repeated or \
            text.lower().startswith("printed copies are uncontrolled")

    # 2) metadata from the title block (first table on page 1) + title line
    meta: dict = {}
    first_table = next((p for _, k, p in pages[0] if k == "table"), None) if pages else None
    block_text = "\n".join(" ".join(r) for r in first_table) if first_table else ""
    for key, pat in META_PATTERNS.items():
        m = re.search(pat, block_text, re.M)
        if m:
            meta[key] = m.group(1).strip()
    title_parts = [p["text"] for _, k, p in pages[0] if k == "line" and p["size"] >= TITLE_MIN_SIZE] if pages else []
    if title_parts:
        meta["title"] = " ".join(title_parts)
    for k in ("status", "classification", "doc_type"):
        if k in meta:
            meta[k] = meta[k].lower()

    # 3) walk items, build sections; merge wrapped lines into paragraphs
    sections: list[Section] = []
    current = Section(heading="Document header", page=1)
    para: list[str] = []
    para_page, last_bottom = 1, None

    def flush_para():
        nonlocal para
        if para:
            current.blocks.append(Block("text", " ".join(para), para_page))
            para = []

    skipped_title_block = False
    for page_no, items in enumerate(pages, start=1):
        last_bottom = None
        for _, kind, payload in items:
            if kind == "table":
                if page_no == 1 and not skipped_title_block and payload is first_table:
                    skipped_title_block = True
                    continue
                flush_para()
                current.blocks.append(Block("table", linearise_table(payload), page_no, rows=payload))
                last_bottom = None
                continue
            text = payload["text"]
            if is_noise(text) or (page_no == 1 and text in title_parts):
                continue
            if payload["bold"] and payload["size"] >= HEADING_MIN_SIZE and HEADING_NUM_RE.match(text):
                flush_para()
                if current.blocks or current.heading != "Document header":
                    sections.append(current)
                current = Section(heading=text, page=page_no)
                last_bottom = payload["bottom"]
                continue
            new_item = re.match(r"^(\d+|-|•)\s", text) is not None
            gap = (payload["top"] - last_bottom) if last_bottom is not None else 99
            if para and not new_item and gap < payload["size"] * 0.9:
                para.append(text)          # wrapped continuation line
            else:
                flush_para()
                para, para_page = [text], page_no
            last_bottom = payload["bottom"]
    flush_para()
    if current.blocks:
        sections.append(current)

    return ParsedDocument(source=path.name, sha256=file_sha256(path), n_pages=n_pages,
                          meta=meta, sections=sections)


def parse_text(path: str | Path, meta: dict | None = None) -> ParsedDocument:
    """Markdown / plain text: split on markdown headings."""
    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    sections: list[Section] = []
    current = Section(heading="Document header", page=1)
    for para in re.split(r"\n\s*\n", raw):
        para = para.strip()
        if not para:
            continue
        m = re.match(r"^#{1,6}\s+(.*)", para)
        if m:
            if current.blocks:
                sections.append(current)
            first, _, rest = para.partition("\n")
            current = Section(heading=m.group(1).strip(), page=1)
            if rest.strip():
                current.blocks.append(Block("text", rest.strip(), 1))
        else:
            current.blocks.append(Block("text", re.sub(r"\s*\n\s*", " ", para), 1))
    if current.blocks:
        sections.append(current)
    meta = dict(meta or {})
    meta.setdefault("doc_no", path.stem)
    meta.setdefault("title", path.stem.replace("_", " "))
    return ParsedDocument(source=path.name, sha256=file_sha256(path), n_pages=1, meta=meta, sections=sections)


def parse_any(path: str | Path, meta: dict | None = None) -> ParsedDocument:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        doc = parse_pdf(path)
        if meta:
            doc.meta.update({k: v for k, v in meta.items() if v})
        return doc
    return parse_text(path, meta)
