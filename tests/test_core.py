import datetime as dt
import json
import math
import os
import tempfile

import pytest

from src import db
from src.document_tool import DocumentError, extract_pdf_text
from src.llm import DemoClient, evaluate_supplier, parse_json_response
from src.orchestrator import run_evaluation, validate_inputs
from src.ranking import compute_run, effective_weights
from src.validation import normalize_evaluation

CRIT = [
    {"criterion_id": 1, "name": "Tech", "description": "", "weight": 60, "max_score": 10, "is_active": True},
    {"criterion_id": 2, "name": "Price", "description": "", "weight": 40, "max_score": 10, "is_active": True},
]


def sup(name, s1, s2, date="2026-01-10", exp=5.0, valid=True):
    return {"supplier_name": name, "submission_date": date, "experience_rating": exp,
            "scores": {1: {"score": s1, "valid": valid, "status": "ok", "justification": "", "evidence": ""},
                       2: {"score": s2, "valid": valid, "status": "ok", "justification": "", "evidence": ""}}}


# ---------------------------------------------------------------- formulas
def test_formulas_by_hand():
    r = compute_run([sup("A", 8, 5), sup("B", 4, 10)], CRIT)
    a = next(s for s in r["suppliers"] if s["supplier_name"] == "A")
    b = next(s for s in r["suppliers"] if s["supplier_name"] == "B")
    assert r["benchmarks"] == {1: 8, 2: 10}
    assert a["absolute_score"] == pytest.approx(8 / 10 * 60 + 5 / 10 * 40)       # 68
    assert b["absolute_score"] == pytest.approx(4 / 10 * 60 + 10 / 10 * 40)      # 64
    assert a["ppi"] == pytest.approx(100 * 0.6 + 50 * 0.4)                        # 80
    assert b["ppi"] == pytest.approx(50 * 0.6 + 100 * 0.4)                        # 70
    assert [c["gap"] for c in a["criteria"]] == [0, -5]
    assert a["final_rank"] == 1 and b["final_rank"] == 2


def test_zero_benchmark_is_safe():
    r = compute_run([sup("A", 0, 5), sup("B", 0, 5)], CRIT)
    for s in r["suppliers"]:
        assert s["criteria"][0]["relative_pct"] == 100.0
        assert not math.isnan(s["ppi"])


def test_weights_renormalised_with_warning():
    w, warn = effective_weights([{**CRIT[0], "weight": 30}, {**CRIT[1], "weight": 20}])
    assert sum(w.values()) == pytest.approx(100) and warn


# --------------------------------------------------------------- tie-breaks
def test_tiebreak_order():
    same = dict(s1=5, s2=5)
    r = compute_run([
        sup("Zeta", **same, date="2026-01-12", exp=9),
        sup("Alpha", **same, date="2026-01-10", exp=5),   # earlier date wins over experience
        sup("Beta", **same, date="2026-01-10", exp=7),    # same date, higher exp beats Alpha
        sup("Aaron", **same, date="2026-01-10", exp=7),   # same date+exp, name asc beats Beta
    ], CRIT)
    assert [s["supplier_name"] for s in r["suppliers"]] == ["Aaron", "Beta", "Alpha", "Zeta"]
    assert [s["final_rank"] for s in r["suppliers"]] == [1, 2, 3, 4]
    assert len(r["tie_break_explanations"]) == 3


def test_ranking_is_deterministic_regardless_of_input_order():
    data = [sup("A", 7, 7), sup("B", 7, 7, date="2026-01-09"), sup("C", 9, 1)]
    r1 = compute_run(list(data), CRIT)
    r2 = compute_run(list(reversed(data)), CRIT)
    assert [s["supplier_name"] for s in r1["suppliers"]] == [s["supplier_name"] for s in r2["suppliers"]]


# --------------------------------------------------------------- validation
def test_validation_handles_bad_llm_output():
    raw = {"criteria": [
        {"criterion_id": 1, "score": "12", "justification": "ok", "evidence": "q"},   # out of range -> clipped
        {"criterion_id": 99, "score": 5},                                              # unknown
    ]}
    norm, warns = normalize_evaluation(raw, CRIT)
    assert norm["scores"][1]["score"] == 10 and norm["scores"][1]["status"] == "clipped"
    assert norm["scores"][2]["score"] == 0 and norm["scores"][2]["status"] == "missing"
    assert any("unknown criterion" in w for w in warns)


@pytest.mark.parametrize("bad", [None, "text", [], {"criteria": "nope"}, {"criteria": [1, "x"]}])
def test_validation_never_raises(bad):
    norm, warns = normalize_evaluation(bad, CRIT)
    assert set(norm["scores"]) == {1, 2} and warns


def test_validation_score_coercion():
    raw = {"criteria": [{"criterion_id": "1", "score": "7/10", "evidence": "e"},
                        {"criterion_id": 2, "score": "n/a"}]}
    norm, _ = normalize_evaluation(raw, CRIT)
    assert norm["scores"][1]["score"] == 7.0
    assert norm["scores"][2]["valid"] is False


def test_parse_json_variants():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_response('Sure! {"a": 2} hope this helps') == {"a": 2}
    with pytest.raises(ValueError):
        parse_json_response("no json here")


# ----------------------------------------------------------------- documents
def test_blank_pdf_rejected():
    with open("sample_rfps/EDGE_blank_scanned_RFP.pdf", "rb") as f:
        with pytest.raises(DocumentError):
            extract_pdf_text(f.read())
    with pytest.raises(DocumentError):
        extract_pdf_text(b"not a pdf")


def test_input_validation():
    docs = [{"filename": "a.pdf", "supplier_name": "X", "submission_date": dt.date.today(), "experience_rating": 5},
            {"filename": "b.pdf", "supplier_name": "x", "submission_date": dt.date.today(), "experience_rating": 11}]
    errs = validate_inputs(docs, CRIT)
    assert any("Duplicate" in e for e in errs) and any("between 0 and 10" in e for e in errs)


# --------------------------------------------------------- end-to-end + DB
def test_end_to_end_and_persistence():
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    db.init_db(path)
    names = {"Apex_Systems_RFP": "Apex Systems", "BrightPath_Tech_RFP": "BrightPath Tech"}
    docs = [{"filename": f"{k}.pdf", "data": open(f"sample_rfps/{k}.pdf", "rb").read(), "supplier_name": v,
             "submission_date": dt.date(2026, 3, 1), "experience_rating": 7} for k, v in names.items()]
    docs.append({"filename": "blank.pdf", "data": open("sample_rfps/EDGE_blank_scanned_RFP.pdf", "rb").read(),
                 "supplier_name": "Blank Co", "submission_date": dt.date(2026, 3, 1), "experience_rating": 7})
    result = run_evaluation(docs, DemoClient(), "Demo", "x", path)
    assert [s["final_rank"] for s in result["suppliers"]] == [1, 2, 3]
    assert result["suppliers"][-1]["supplier_name"] == "Blank Co"                  # failed extraction -> zeros
    assert any("extraction failed" in w for w in result["warnings"])
    stored = db.get_run(result["rfp_run_id"], path)
    assert stored["leaderboard"] == json.loads(json.dumps(result["leaderboard"]))
    assert db.list_runs(path)[0]["status"] == "COMPLETED"
    # same validated scorecards -> same ranking, every time
    again = run_evaluation(docs, DemoClient(), "Demo", "x", path)
    assert again["leaderboard"] == result["leaderboard"]


def test_llm_garbage_then_recovery():
    class Flaky:
        n = 0
        def complete(self, s, u, ctx=None):
            Flaky.n += 1
            return "garbage" if Flaky.n == 1 else '{"criteria": []}'
    raw, w = evaluate_supplier(Flaky(), CRIT, "X", "text")
    assert raw == {"criteria": []} and len(w) == 1
