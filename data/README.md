# Data

## Why the documents are made up

The documents a copilot like this is built for (work instructions, 8D reports, supplier audits, management minutes) are confidential at every manufacturer I know. Public "sample" PDFs don't help much either, because they don't have what makes the problem hard: several revisions of the same instruction, access levels, tables with tolerances, and cross-references between documents.

So I wrote a small but realistic document set for a fictional company, **Nordwerk Drive Systems GmbH**, that builds e-drive units (gearbox + motor) for cars. The plant, the people, the supplier "Kessler Gusstechnik" and every number in the documents are invented. Nothing comes from a real company.

The regulatory register (REG-SUM-001) and the noise policy (HSE-POL-007) refer to real EU regulations. I kept those references to what I could check: the Machinery Regulation (EU) 2023/1230 applying from 20 January 2027, the 80 / 85 / 87 dB(A) values of Directive 2003/10/EC, the 0.1 % SVHC threshold of REACH. They are written as short internal summaries, not as quotes of legal text, and they are not legal advice.

## Folders

| Folder | Content |
|---|---|
| `source/` | 23 documents as markdown with a YAML header. This is what I write and edit. |
| `corpus/` | The same documents rendered to PDF by `scripts/build_corpus.py`, plus `manifest.json`. **This is what the copilot ingests.** |
| `eval/dev.jsonl` | 48 questions used to tune the abstention threshold and the answer settings. |
| `eval/test.jsonl` | 140 questions used only for the reported numbers. |

The PDFs are made to look like controlled documents from a DMS: company header, document number and revision on every page, *Page x of y* footer, a "printed copies are uncontrolled" note, a title block table, wrapped table cells, and a big diagonal SUPERSEDED / CONFIDENTIAL stamp where it applies. The parser has to deal with all of that; the YAML header is **not** printed into the PDF, so metadata has to be recovered from the title block.

`manifest.json` stands in for the access-control export of a document management system: which roles may read which document revision.

## The documents

| Type | Documents |
|---|---|
| Work instructions | WI-ASM-014 Rev B (superseded) and Rev C, WI-MCH-022, WI-PNT-005, WI-ESD-001, WI-LOG-009 |
| Maintenance | MM-CNC-003, MP-LOTO-002, MM-CMP-011, TS-ROB-004 |
| Quality | QR-8D-2026-017 (confidential), QR-8D-2026-021, QR-AUD-2026-03 (confidential), QP-INS-007, QM-NCR-001, QR-MON-2026-09 |
| Engineering | ES-TOR-001, ECN-2026-044, TS-EOL-012 |
| HSE / regulatory | HSE-POL-003, HSE-POL-007, REG-SUM-001 |
| Management | MGT-REV-2026-Q3 (restricted, admin only) |

They link to each other on purpose. The oil leakage complaint (8D-2026-017) led to the engineering change ECN-2026-044, which raised the M10 flange torque from 40 to 45 Nm and produced WI-ASM-014 Rev C. Rev B with the old 40 Nm value is still in the corpus. This is the "superseded revision trap" that the evaluation checks.

## Roles

| Role | Sees |
|---|---|
| operator | work instructions, LOTO, HSE, nonconforming product, regulatory register |
| maintenance | + maintenance manuals, troubleshooting, EOL test spec, ECN, open 8D on machining |
| quality | + all quality reports, audits, inspection plans (not maintenance manuals) |
| engineering | + engineering standards, maintenance manuals, 8D reports, monthly quality report (not the supplier audit) |
| admin | everything, including management review minutes |

## Evaluation questions

Every question was written by hand against the source documents. Each one has:

- `role`: who asks
- `type`: factual, numeric, table, procedural, cross_doc, version, restricted or unanswerable
- `gold`: the relevant document and section, e.g. `WI-ASM-014:4`. `WI-ASM-014@B:3` means a specific old revision; without `@` only the current revision counts.
- `facts`: strings that must appear in a correct answer (`|` separates accepted alternatives)
- `forbidden`: the superseded value that must not be given as the answer
- `answerable: false` for questions the user must not get an answer to, either because the document exists but is not visible to that role (restricted) or because the corpus does not contain the answer at all (unanswerable).

## Licence

The documents and questions are my own work and are under the same MIT licence as the code.
