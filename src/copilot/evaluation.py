"""Evaluation helpers: gold matching, retrieval metrics, answer metrics."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Question:
    id: str
    role: str
    type: str
    question: str
    gold: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    answerable: bool = True


def load_questions(path: str | Path) -> list[Question]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append(Question(**d))
    return out


def _parse_gold(g: str) -> tuple[str, str | None, str | None]:
    """'WI-ASM-014@B:3' -> (doc, rev, section prefix). No @ = current revision."""
    doc, _, sec = g.partition(":")
    doc, _, rev = doc.partition("@")
    return doc, rev or None, sec or None


def is_relevant(payload: dict, gold: list[str]) -> bool:
    for g in gold:
        doc, rev, sec = _parse_gold(g)
        if payload["doc_no"] != doc:
            continue
        if rev is not None and payload["revision"] != rev:
            continue
        if rev is None and not payload.get("is_current", True):
            continue
        if sec is not None and payload["section"].split()[0] != sec:
            continue
        return True
    return False


def gold_docs(gold: list[str]) -> set[str]:
    return {_parse_gold(g)[0] for g in gold}


def retrieval_metrics(rels: list[bool], ks=(1, 3, 5, 10)) -> dict:
    out = {f"hit@{k}": float(any(rels[:k])) for k in ks}
    rr = next((1 / (i + 1) for i, r in enumerate(rels) if r), 0.0)
    out["mrr"] = rr
    dcg = sum(1 / math.log2(i + 2) for i, r in enumerate(rels[:10]) if r)
    n_rel = max(1, min(10, sum(rels)))
    idcg = sum(1 / math.log2(i + 2) for i in range(n_rel))
    out["ndcg@10"] = dcg / idcg if any(rels[:10]) else 0.0
    return out


def _norm(s: str) -> str:
    s = s.lower().replace(" ", " ")
    s = re.sub(r"(\d),(\d{3})\b", r"\1\2", s)          # 86,400 -> 86400
    s = re.sub(r"(\d)\s*(%|nm|mm|kn|bar|mbar|db)", r"\1 \2", s)
    return re.sub(r"\s+", " ", s)


def fact_present(answer: str, fact: str) -> bool:
    a = _norm(answer)
    return any(_norm(alt) in a for alt in fact.split("|"))


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def percentile(xs, p: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100
    f, c = math.floor(k), math.ceil(k)
    return xs[f] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f)
