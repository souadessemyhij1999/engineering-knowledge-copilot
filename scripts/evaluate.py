"""Offline evaluation of retrieval and answers.

    python scripts/evaluate.py --calibrate     # pick the abstention threshold on the dev set
    python scripts/evaluate.py                 # full evaluation on the test set

Writes reports/metrics.json, reports/retrieval_results.csv,
reports/answers_test.csv and reports/calibration.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot.config import load_settings  # noqa: E402
from copilot.evaluation import fact_present, gold_docs, is_relevant, load_questions, mean, percentile, retrieval_metrics  # noqa: E402
from copilot.pipeline import Copilot  # noqa: E402

REPORTS = ROOT / "reports"

CONFIGS = {
    "dense": dict(mode="dense", rerank=False),
    "bm25": dict(mode="sparse", rerank=False),
    "hybrid (RRF)": dict(mode="hybrid", rerank=False),
    "hybrid + rerank": dict(mode="hybrid", rerank=True),
}


def build(min_score: float | None = None) -> Copilot:
    over = {"qdrant": {"url": "", "path": ":memory:"}, "database": {"url": "sqlite://"}}
    if min_score is not None:
        over["answer"] = {"min_score": min_score}
    cp = Copilot(load_settings(overrides=over), use_db=False)
    cp.ingestor.ingest_dir(ROOT / "data" / "corpus")
    return cp


def roles_for(cp: Copilot, role: str):
    return None if role in cp.policy.superuser_roles else [role]


def leaks(chunks, role: str, cp: Copilot) -> int:
    if role in cp.policy.superuser_roles:
        return 0
    return sum(role not in c.payload["roles"] for c in chunks)


def calibrate(cp: Copilot) -> float:
    qs = load_questions(ROOT / "data" / "eval" / "dev.jsonl")
    rows = []
    for q in qs:
        r = cp.retriever.retrieve(q.question, roles_for(cp, q.role), top_k=5)
        rows.append((r.chunks[0].answerability if r.chunks else 0.0, q.answerable, q.id))
    best, grid = None, [round(0.3 + 0.01 * i, 2) for i in range(91)]
    out = []
    for t in grid:
        tp = sum(s >= t and a for s, a, _ in rows)
        tn = sum(s < t and not a for s, a, _ in rows)
        pos = sum(a for _, a, _ in rows) or 1
        neg = sum(not a for _, a, _ in rows) or 1
        bal = 0.5 * (tp / pos + tn / neg)
        out.append({"threshold": t, "answer_recall": tp / pos, "abstain_recall": tn / neg, "balanced_acc": bal})
    top = max(o["balanced_acc"] for o in out)
    ok = [o["threshold"] for o in out if o["balanced_acc"] == top]
    best = round((ok[0] + ok[-1]) / 2, 2)
    with open(REPORTS / "calibration.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    with open(REPORTS / "calibration_scores.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "answerable", "top_score"])
        for s, a, i in rows:
            w.writerow([i, a, round(s, 4)])
    print(f"dev: best balanced accuracy {top:.3f} for thresholds {ok[0]}..{ok[-1]} -> using {best}")
    return best


def eval_retrieval(cp: Copilot, qs) -> tuple[dict, list[dict], int]:
    per_cfg, rows, total_leaks = {}, [], 0
    answerable = [q for q in qs if q.answerable]
    for name, kw in CONFIGS.items():
        ms, lat = [], []
        for q in qs:
            t = time.perf_counter()
            r = cp.retriever.retrieve(q.question, roles_for(cp, q.role), top_k=10, **kw)
            lat.append((time.perf_counter() - t) * 1e3)
            total_leaks += leaks(r.chunks, q.role, cp)
            if not q.answerable:
                continue
            rels = [is_relevant(c.payload, q.gold) for c in r.chunks]
            m = retrieval_metrics(rels)
            ms.append(m)
            rows.append({"config": name, "id": q.id, "type": q.type, **{k: round(v, 4) for k, v in m.items()}})
        per_cfg[name] = {k: round(mean(m[k] for m in ms), 4) for k in ms[0]}
        per_cfg[name]["latency_ms_p50"] = round(percentile(lat, 50), 1)
    # ablation: no current-revision filter (what happens on version-trap questions)
    trap = [q for q in answerable if q.forbidden or q.type == "version"]
    wrong_rev = {"filter on": 0, "filter off": 0}
    for label, cur in (("filter on", None), ("filter off", False)):
        for q in trap:
            r = cp.retriever.retrieve(q.question, roles_for(cp, q.role), top_k=1, current_only=cur)
            top = r.chunks[0].payload if r.chunks else None
            if top and not is_relevant(top, q.gold):
                wrong_rev[label] += 1
    per_cfg["_version_trap_top1_wrong"] = {**wrong_rev, "n": len(trap)}
    per_cfg["_by_type_hybrid_rerank"] = {}
    by_type = defaultdict(list)
    for row in rows:
        if row["config"] == "hybrid + rerank":
            by_type[row["type"]].append(row)
    for t, rs in sorted(by_type.items()):
        per_cfg["_by_type_hybrid_rerank"][t] = {"n": len(rs), "hit@1": round(mean(r["hit@1"] for r in rs), 3),
                                                "hit@5": round(mean(r["hit@5"] for r in rs), 3)}
    return per_cfg, rows, total_leaks


def eval_answers(cp: Copilot, qs, mode: str = "extractive") -> tuple[dict, list[dict]]:
    rows = []
    for q in qs:
        user = next(u for u in cp.policy.users.values() if u.role == q.role)
        a = cp.ask(q.question, user, mode=mode, log_query=False)
        cited = [s for s in a.sources if s["cited"]]
        g_docs = gold_docs(q.gold)
        row = {
            "id": q.id, "type": q.type, "role": q.role, "answerable": q.answerable, "abstained": a.abstained,
            "facts_ok": all(fact_present(a.answer, f) for f in q.facts) if q.answerable and not a.abstained else None,
            # superseded value given *instead of* the current one
            "forbidden_hit": bool(q.forbidden) and not a.abstained and any(fact_present(a.answer, f) for f in q.forbidden)
            and not all(fact_present(a.answer, f) for f in q.facts),
            "cit_precision": (sum(s["doc_no"] in g_docs for s in cited) / len(cited)) if cited and q.answerable else None,
            "guard_passed": a.guard.get("passed"), "top_score": a.top_score, "mode_used": a.mode,
            "leaked_sources": sum(q.role not in cp.policy.superuser_roles and
                                  s["doc_no"] in g_docs for s in a.sources) if not q.answerable and q.type == "restricted" else 0,
            "latency_ms": a.timings["total_ms"], "question": q.question,
            "answer": a.answer.replace("\n", " "),
        }
        rows.append(row)
    ans = [r for r in rows if r["answerable"]]
    neg = [r for r in rows if not r["answerable"]]
    answered = [r for r in ans if not r["abstained"]]
    m = {
        "n_questions": len(rows), "n_answerable": len(ans), "n_unanswerable": len(neg),
        "answer_rate (answerable)": round(len(answered) / len(ans), 4),
        "key_fact_accuracy (answered)": round(mean(r["facts_ok"] for r in answered), 4),
        "key_fact_accuracy (all answerable)": round(sum(bool(r["facts_ok"]) for r in ans) / len(ans), 4),
        "citation_precision": round(mean(r["cit_precision"] for r in answered if r["cit_precision"] is not None), 4),
        "guard_pass_rate": round(mean(bool(r["guard_passed"]) for r in answered), 4),
        "superseded_value_in_answer": sum(r["forbidden_hit"] for r in rows),
        "abstention_rate (restricted)": round(mean(r["abstained"] for r in neg if r["type"] == "restricted"), 4),
        "abstention_rate (unanswerable)": round(mean(r["abstained"] for r in neg if r["type"] == "unanswerable"), 4),
        "restricted_doc_in_sources": sum(r["leaked_sources"] for r in rows),
        "llm_answers_rejected_by_guard": sum(r["mode_used"] == "llm->extractive" for r in rows),
        "latency_ms_p50": round(percentile([r["latency_ms"] for r in rows], 50), 1),
        "latency_ms_p95": round(percentile([r["latency_ms"] for r in rows], 95), 1),
    }
    by_type = {}
    for t in sorted({r["type"] for r in rows}):
        rs = [r for r in rows if r["type"] == t]
        if rs[0]["answerable"]:
            by_type[t] = {"n": len(rs), "fact_accuracy": round(sum(bool(r["facts_ok"]) for r in rs) / len(rs), 3),
                          "abstained": sum(r["abstained"] for r in rs)}
        else:
            by_type[t] = {"n": len(rs), "abstention_rate": round(mean(r["abstained"] for r in rs), 3)}
    m["by_type"] = by_type
    return m, rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    ap.add_argument("--mode", default="extractive", choices=["extractive", "llm"],
                    help="llm needs ANTHROPIC_API_KEY; only the answer part is re-run")
    args = ap.parse_args()
    REPORTS.mkdir(exist_ok=True)
    cp = build()
    if args.calibrate:
        calibrate(cp)
        return
    qs = load_questions(ROOT / "data" / "eval" / f"{args.split}.jsonl")
    t0 = time.time()
    if args.mode == "llm":
        ans, arows = eval_answers(cp, qs, mode="llm")
        (REPORTS / "metrics_llm.json").write_text(json.dumps(ans, indent=2), encoding="utf-8")
        with open(REPORTS / "answers_test_llm.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(arows[0]))
            w.writeheader()
            w.writerows(arows)
        print(json.dumps(ans, indent=2))
        return
    retr, rrows, n_leaks = eval_retrieval(cp, qs)
    ans, arows = eval_answers(cp, qs)
    metrics = {"retrieval": retr, "access_leaks_in_retrieval": n_leaks, "answers_extractive": ans,
               "corpus": {"documents": len({(p["doc_no"], p["revision"]) for p in cp.store.scroll_all()}),
                          "chunks": cp.store.count()},
               "settings": {"min_score": cp.cfg["answer"]["min_score"], "top_k": cp.cfg["retrieval"]["top_k"]},
               "runtime_s": round(time.time() - t0, 1)}
    if args.split == "dev":
        (REPORTS / "metrics_dev.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(json.dumps(metrics["answers_extractive"], indent=2))
        return
    (REPORTS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    for name, rows in (("retrieval_results.csv", rrows), ("answers_test.csv", arows)):
        with open(REPORTS / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
