import pytest

from copilot.access import AccessPolicy

QUESTIONS = [
    "What was the root cause of the oil leakage complaint?",
    "What was the result of the supplier audit at Kessler?",
    "What budget was approved for the second source of castings?",
    "What is the drawbar clamping force?",
    "What was the scrap rate in September?",
]


@pytest.mark.parametrize("role", ["operator", "maintenance", "quality", "engineering"])
def test_no_chunk_outside_role_is_ever_returned(copilot, role):
    for q in QUESTIONS:
        for mode in ("dense", "sparse", "hybrid"):
            r = copilot.retriever.retrieve(q, [role], top_k=20, mode=mode, current_only=False)
            assert all(role in c.payload["roles"] for c in r.chunks), (role, q, mode)


def test_visible_documents_differ_by_role(copilot, users):
    op = {d["doc_no"] for d in copilot.visible_documents(users["olga.operator"])}
    qa = {d["doc_no"] for d in copilot.visible_documents(users["quinn.quality"])}
    adm = {d["doc_no"] for d in copilot.visible_documents(users["ada.admin"])}
    assert "QR-8D-2026-017" not in op and "QR-8D-2026-017" in qa
    assert "MGT-REV-2026-Q3" in adm and "MGT-REV-2026-Q3" not in qa
    assert op < adm and qa < adm


def test_restricted_question_abstains_without_hinting(copilot, users):
    a = copilot.ask("What budget was approved for the second source of housing castings?",
                    users["emre.engineer"], log_query=False)
    assert a.abstained and a.sources == []
    b = copilot.ask("What budget was approved for the second source of housing castings?",
                    users["ada.admin"], log_query=False)
    assert not b.abstained and "180,000 EUR" in b.answer


def test_current_revision_wins(copilot):
    r = copilot.retriever.retrieve("What torque for the M10 flange bolts?", ["operator"], top_k=5)
    top = r.chunks[0].payload
    assert (top["doc_no"], top["revision"]) == ("WI-ASM-014", "C")
    assert all(c.payload["is_current"] for c in r.chunks)


def test_history_question_searches_old_revisions(copilot):
    q = "What was the flange bolt torque in revision B of WI-ASM-014?"
    r = copilot.retriever.retrieve(q, ["engineering"], top_k=3)
    assert not r.current_only
    assert r.chunks[0].payload["revision"] == "B"


def test_exact_code_lookup(copilot):
    r = copilot.retriever.retrieve("E-102", ["maintenance"], top_k=1)
    assert r.chunks[0].payload["doc_no"] == "TS-ROB-004"


def test_rerank_beats_plain_fusion_on_table_question(copilot):
    q = "What is the reject limit of the gearbox leak test?"
    rr = copilot.retriever.retrieve(q, ["operator"], top_k=1)
    assert rr.chunks[0].payload["section"].startswith("4 Test parameters")


def test_login_and_tokens(tmp_path):
    from conftest import ROOT
    pol = AccessPolicy(ROOT / "configs/access.yaml", ROOT / "configs/users.yaml", ROOT / "data/corpus/manifest.json")
    u = pol.authenticate("olga.operator", "demo")
    assert u and u.role == "operator"
    assert pol.authenticate("olga.operator", "wrong") is None
    tok = pol.issue_token(u, "a-test-secret-that-is-long-enough-32b")
    assert pol.user_from_token(tok, "a-test-secret-that-is-long-enough-32b") == u
    assert pol.user_from_token(tok, "another-test-secret-long-enough-32b") is None
    # admin is always added, unknown documents fall back to classification defaults
    assert "admin" in pol.roles_for_document("NEW-1", "A", "confidential")
    assert pol.roles_for_document("NEW-1", "A", "restricted") == ["admin"]
