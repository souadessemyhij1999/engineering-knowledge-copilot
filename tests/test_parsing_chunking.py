from conftest import CORPUS
from copilot.chunking import chunk_document
from copilot.parsing import linearise_table, parse_pdf, parse_text


def test_metadata_from_title_block():
    d = parse_pdf(CORPUS / "WI-ASM-014_RevC.pdf")
    assert d.meta["doc_no"] == "WI-ASM-014"
    assert d.meta["revision"] == "C"
    assert d.meta["status"] == "current"
    assert d.meta["effective"] == "2026-06-01"
    assert d.meta["title"].startswith("Gearbox Housing Assembly")
    assert d.n_pages == 2


def test_wrapped_title_is_joined():
    d = parse_pdf(CORPUS / "QR-8D-2026-017_RevA.pdf")
    assert d.meta["title"].endswith("(Customer Complaint)")


def test_headers_footers_and_watermarks_removed():
    for name in ("WI-ASM-014_RevB.pdf", "QR-AUD-2026-03_RevA.pdf", "WI-ASM-014_RevC.pdf"):
        text = parse_pdf(CORPUS / name).full_text
        assert "Printed copies are uncontrolled" not in text
        assert "Page 1 of" not in text
        assert "Nordwerk Drive Systems GmbH" not in text
        assert "SUPERSEDED" not in text and "CONFIDENTIAL" not in text


def test_sections_and_tables():
    d = parse_pdf(CORPUS / "WI-ASM-014_RevC.pdf")
    heads = [s.heading for s in d.sections]
    assert heads[0] == "1 Purpose" and "4 Tightening torques" in heads
    torque = next(s for s in d.sections if s.heading.startswith("4 "))
    table = next(b for b in torque.blocks if b.kind == "table")
    # wrapped cell "Flange bolts to motor / housing" comes back as one value
    assert "Joint: Flange bolts to motor housing; Thread: M10; Torque: 45 Nm" in table.text


def test_linearise_table():
    rows = [["Code", "Meaning"], ["E-101", "Pressure low"], ["E-102", ""]]
    assert linearise_table(rows) == "Code: E-101; Meaning: Pressure low\nCode: E-102"


def test_markdown_upload(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# Scope\n\nApplies to line L9.\n\n## Rule\n\nTorque is 12 Nm.\n")
    d = parse_text(f, {"doc_no": "NOTE-1"})
    assert [s.heading for s in d.sections] == ["Scope", "Rule"]


def test_chunks_have_context_and_limits():
    d = parse_pdf(CORPUS / "REG-SUM-001_RevE.pdf")
    chunks = chunk_document(d, max_chars=400, overlap=50)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all(len(c.text) <= 400 for c in chunks)
    assert all(c.index_text.startswith("REG-SUM-001 Rev E") for c in chunks)
    # split tables keep their header labels in every piece
    reg = [c for c in chunks if c.section.startswith("2 ")]
    assert len(reg) > 1 and all("Regulation:" in c.text for c in reg)
