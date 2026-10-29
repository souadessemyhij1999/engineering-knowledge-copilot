"""Render the markdown sources in data/source into PDFs that look like real
controlled documents: company header, title block, page x of y footers,
tables, watermarks on superseded or confidential files.

The PDFs are what the copilot ingests. The frontmatter is NOT copied into the
PDF as-is; the parser has to recover document number, revision, dates etc.
from the printed title block, the same way it would with a real DMS export.
Access rights come from a separate manifest (data/corpus/manifest.json),
which stands in for the ACL export of a document management system.

    python scripts/build_corpus.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "source"
OUT = ROOT / "data" / "corpus"

COMPANY = "Nordwerk Drive Systems GmbH"

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=12.5, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4)
TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=6)
CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10.5)
CELL_B = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")


def read_source(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm), body.strip()


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_to_flowables(body: str) -> list:
    flow, table_rows, list_items, list_kind = [], [], [], None

    def flush_table():
        nonlocal table_rows
        if not table_rows:
            return
        rows = [r for r in table_rows if not re.fullmatch(r"\|?\s*-+\s*(\|\s*-+\s*)*\|?", r)]
        data = []
        for i, r in enumerate(rows):
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            data.append([Paragraph(esc(c), CELL_B if i == 0 else CELL) for c in cells])
        t = Table(data, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6e9ee")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        flow.extend([t, Spacer(1, 5)])
        table_rows = []

    def flush_list():
        nonlocal list_items, list_kind
        if not list_items:
            return
        items = [ListItem(Paragraph(esc(x), BODY), leftIndent=12) for x in list_items]
        if list_kind == "ol":
            flow.append(ListFlowable(items, bulletType="1", bulletFontSize=9.5, leftIndent=14))
        else:
            flow.append(ListFlowable(items, bulletType="bullet", start="-", leftIndent=14))
        list_items, list_kind = [], None

    for line in body.splitlines():
        s = line.strip()
        if s.startswith("|"):
            flush_list()
            table_rows.append(s)
            continue
        flush_table()
        m_ol = re.match(r"^\d+\.\s+(.*)", s)
        if m_ol or s.startswith("- "):
            kind = "ol" if m_ol else "ul"
            if list_kind and list_kind != kind:
                flush_list()
            list_kind = kind
            list_items.append(m_ol.group(1) if m_ol else s[2:])
            continue
        flush_list()
        if not s:
            continue
        if s.startswith("## "):
            flow.append(Paragraph(esc(s[3:]), H2))
        else:
            flow.append(Paragraph(esc(s), BODY))
    flush_table()
    flush_list()
    return flow


def title_block(meta: dict) -> list:
    rows = [
        ["Document no.", meta["doc_no"], "Revision", str(meta["revision"])],
        ["Document type", meta["type"].title(), "Status", meta["status"].title()],
        ["Effective date", str(meta["effective"]), "Owner", meta["owner"]],
        ["Classification", meta["classification"].title(), "", ""],
    ]
    data = [[Paragraph(esc(str(c)), CELL_B if j % 2 == 0 else CELL) for j, c in enumerate(r)] for r in rows]
    t = Table(data, colWidths=[30 * mm, 55 * mm, 25 * mm, 55 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f2f2")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f2f2f2")),
    ]))
    return [Paragraph(esc(meta["title"]), TITLE), t, Spacer(1, 8)]


def make_canvas(meta: dict):
    """Canvas class that knows the total page count (two-pass) and draws
    header, footer and watermark on every page."""

    class DocCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total):
            w, h = A4
            self.setFont("Helvetica-Bold", 8.5)
            self.drawString(18 * mm, h - 12 * mm, COMPANY)
            self.setFont("Helvetica", 8.5)
            self.drawRightString(w - 18 * mm, h - 12 * mm, f"{meta['doc_no']}  Rev. {meta['revision']}")
            self.line(18 * mm, h - 14 * mm, w - 18 * mm, h - 14 * mm)
            self.line(18 * mm, 16 * mm, w - 18 * mm, 16 * mm)
            self.setFont("Helvetica", 7.5)
            self.drawString(18 * mm, 11 * mm, "Printed copies are uncontrolled. Check the DMS for the current revision.")
            self.drawRightString(w - 18 * mm, 11 * mm, f"Page {self._pageNumber} of {total}")
            mark = None
            if meta["status"] == "superseded":
                mark = "SUPERSEDED"
            elif meta["classification"] in ("confidential", "restricted"):
                mark = meta["classification"].upper()
            if mark:
                self.saveState()
                self.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.12))
                self.setFont("Helvetica-Bold", 70)
                self.translate(w / 2, h / 2)
                self.rotate(40)
                self.drawCentredString(0, 0, mark)
                self.restoreState()

    return DocCanvas


def render(meta: dict, body: str, out: Path) -> None:
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=20 * mm, bottomMargin=22 * mm,
                            title=meta["title"], author=COMPANY)
    doc.build(title_block(meta) + md_to_flowables(body), canvasmaker=make_canvas(meta))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.pdf"):
        old.unlink()
    manifest = []
    for src in sorted(SRC.glob("*.md")):
        meta, body = read_source(src)
        fname = f"{meta['doc_no']}_Rev{meta['revision']}.pdf"
        render(meta, body, OUT / fname)
        manifest.append({"file": fname, "doc_no": meta["doc_no"], "revision": str(meta["revision"]),
                         "roles": meta["roles"], "classification": meta["classification"]})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"rendered {len(manifest)} PDFs to {OUT}")


if __name__ == "__main__":
    main()
