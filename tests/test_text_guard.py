from copilot.evaluation import fact_present, is_relevant, retrieval_metrics
from copilot.guard import check_answer
from copilot.sparse import BM25Encoder
from copilot.text import codes, exact_items, numbers, tokens

SRC = ["Joint: Flange bolts to motor housing; Thread: M10; Torque: 45 Nm; Tolerance: +/- 4.5 Nm",
       "Test pressure 500 mbar (0.5 bar). Reject limit 2.0 cm3/min."]


def test_tokens_keep_codes_and_parts():
    t = tokens("Alarm E-205 on WI-ASM-014")
    assert "e-205" in t and "205" in t and "wi-asm-014" in t


def test_numbers_normalised():
    assert numbers("86,400 EUR and 0,5 bar and 45.0 Nm") == {"86400", "0.5", "45"}


def test_codes_and_years():
    assert {"E-205", "M10", "MC-504"} <= codes("E-205 at M10 on MC-504")
    _, nums = exact_items("since 2026, limit 87 dB")
    assert nums == {"87"}


def test_bm25_encoder():
    enc = BM25Encoder()
    idx, val = enc.encode_doc("torque torque bolt")
    assert len(idx) == 2 and max(val) > min(val)
    qi, qv = enc.encode_query("torque torque")
    assert len(qi) == 1 and qv == [1.0]


def test_guard_passes_grounded_answer():
    rep = check_answer("The M10 flange bolts get 45 Nm +/- 4.5 Nm [1].", SRC)
    assert rep.passed, rep


def test_guard_catches_invented_number():
    rep = check_answer("The M10 flange bolts get 40 Nm [1].", SRC)
    assert not rep.passed and rep.unsupported_numbers == ["40"]


def test_guard_number_must_be_in_cited_source():
    rep = check_answer("The test pressure is 500 mbar [1].", SRC)   # it is in [2], not [1]
    assert not rep.passed


def test_guard_catches_bad_and_missing_citations():
    assert check_answer("Torque is 45 Nm [7].", SRC).invalid_citations == [7]
    rep = check_answer("Torque is 45 Nm for the flange bolts.", SRC)
    assert rep.uncited_sentences and not rep.passed


def test_guard_citation_covers_whole_line():
    rep = check_answer("Test pressure is 500 mbar. Reject limit is 2.0 cm3/min. [2]", SRC)
    assert rep.passed, rep


def test_guard_flags_unsupported_wording():
    rep = check_answer("Operators must wear welding helmets and fireproof aprons [1].", SRC)
    assert rep.weak_sentences and not rep.passed


def test_metrics():
    m = retrieval_metrics([False, True, False])
    assert m["hit@1"] == 0 and m["hit@3"] == 1 and m["mrr"] == 0.5
    assert fact_present("Cost 86,400 EUR", "86400 EUR")
    assert fact_present("pressure 0.5 bar", "500 mbar|0.5 bar")


def test_gold_matching():
    p = {"doc_no": "WI-ASM-014", "revision": "B", "section": "3 Tightening torques", "is_current": False}
    assert is_relevant(p, ["WI-ASM-014@B:3"])
    assert not is_relevant(p, ["WI-ASM-014:3"])  # no @ = current revision only
