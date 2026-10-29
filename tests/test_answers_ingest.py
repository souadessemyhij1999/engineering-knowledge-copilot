from copilot.generation import NOT_FOUND, Draft


def test_extractive_answer_is_cited_and_grounded(copilot, users):
    a = copilot.ask("What is the reject limit of the gearbox leak test?", users["olga.operator"], log_query=False)
    assert not a.abstained
    assert "2.0 cm3/min" in a.answer and "[" in a.answer
    assert a.guard["passed"]
    assert any(s["cited"] and s["doc_no"] == "WI-PNT-005" for s in a.sources)


def test_off_topic_question_abstains(copilot, users):
    a = copilot.ask("What is on the canteen menu on Friday?", users["olga.operator"], log_query=False)
    assert a.abstained and a.answer == NOT_FOUND


def test_procedure_returns_all_steps(copilot, users):
    a = copilot.ask("What are the steps of lockout tagout?", users["olga.operator"], log_query=False)
    assert a.answer.count("\n") >= 5 and "Verify zero energy" in a.answer


def test_llm_mode_without_key_falls_back(copilot, users, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    copilot._llm = None
    a = copilot.ask("What torque for the M10 flange bolts?", users["olga.operator"], mode="llm", log_query=False)
    assert a.mode == "llm->extractive" and "45 Nm" in a.answer


class FakeLLM:
    def __init__(self, text):
        self.text = text

    def answer(self, question, chunks):
        return Draft(self.text, False, [1])


def test_guard_rejects_hallucinated_llm_answer(copilot, users):
    copilot._llm = FakeLLM("Use 50 Nm for the M10 flange bolts [1].")
    try:
        a = copilot.ask("What torque for the M10 flange bolts?", users["olga.operator"], mode="llm", log_query=False)
    finally:
        copilot._llm = None
    assert a.mode == "llm->extractive"
    assert "50 Nm" not in a.answer and "45 Nm" in a.answer


def test_grounded_llm_answer_is_kept(copilot, users):
    copilot._llm = FakeLLM("Tighten the M10 flange bolts to 45 Nm +/- 4.5 Nm [1].")
    try:
        a = copilot.ask("What torque for the M10 flange bolts?", users["olga.operator"], mode="llm", log_query=False)
    finally:
        copilot._llm = None
    assert a.mode == "llm" and a.guard["passed"]


def test_llm_prompt_contains_numbered_sources(copilot):
    from copilot.generation import LLMAnswerer
    r = copilot.retriever.retrieve("leak test pressure", ["operator"], top_k=3)
    msgs = LLMAnswerer.build_messages("leak test pressure", r.chunks)
    assert "NOT_FOUND" in msgs[0].content
    assert "[1] WI-PNT-005 Rev D" in msgs[1].content and "[3]" in msgs[1].content


def test_reingest_same_file_is_skipped(fresh_copilot):
    from conftest import CORPUS
    res = fresh_copilot.ingestor.ingest_file(CORPUS / "WI-ESD-001_RevB.pdf")
    assert res.skipped


def test_new_revision_becomes_current(fresh_copilot, tmp_path, users):
    f = tmp_path / "WI-ASM-014_RevD.md"
    f.write_text("# 4 Tightening torques\n\nFlange bolts to motor housing M10: 48 Nm +/- 4.8 Nm.\n")
    fresh_copilot.ingestor.ingest_file(f, meta={"doc_no": "WI-ASM-014", "revision": "D", "status": "current",
                                                "effective": "2026-12-01", "title": "Gearbox Housing Assembly"})
    revs = {d.revision: d.is_current for d in fresh_copilot.db.revisions("WI-ASM-014")}
    assert revs == {"B": False, "C": False, "D": True}
    a = fresh_copilot.ask("What torque for the M10 flange bolts?", users["olga.operator"], log_query=False)
    assert "48 Nm" in a.answer and "45 Nm" not in a.answer


def test_query_log_and_feedback(fresh_copilot, users):
    a = fresh_copilot.ask("What is the speed limit for forklifts?", users["olga.operator"])
    assert a.query_id
    assert fresh_copilot.db.add_feedback(a.query_id, True, "spot on")
    assert not fresh_copilot.db.add_feedback(99999, True)
    st = fresh_copilot.db.stats()
    assert st["queries"] == 1 and st["helpful"] == 1
