"""Reranking of fused candidates.

No cross-encoder can be downloaded in my build environment and I did not
want a reranker that needs a GPU anyway, so the reranker is a word-level
late-interaction model (ColBERT-style MaxSim) on top of the same WordLlama
vectors, plus exact matching of codes and numbers. In plant documents the
exact tokens matter a lot: "E-205", "M10", "WI-PNT-005", "0.5 bar".

score = w_maxsim * MaxSim(question words, chunk words)
      + w_exact  * share of question codes/numbers found in the chunk
      + w_title  * share of question words found in doc title / section
      + w_fusion * (1 - fused_rank / n)
      + 0.3 * share of question word pairs ("test pressure") found as a phrase
      + 0.3 if the question asks for a procedure and the chunk is a step list
      + 0.3 if the question asks "why" and the section is about causes / reasons
      - 0.4 * share of question codes (E-999, M12 ...) missing in the chunk

A separate "answerability" value is kept for the abstention decision:
MaxSim plus a smaller share of the exact matches, minus missing codes.
Fusion rank and title overlap are useful for ordering but say little about
whether the chunk actually answers the question.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from .embeddings import Embedder
from .text import content_words, exact_items, phrase_overlap

PROCEDURE_RE = re.compile(r"\b(how (do|should|to|can)|steps?|procedure|what (do|should|must) (i|we) do|sequence)\b", re.I)
STEP_LINE_RE = re.compile(r"^\d+\s+[A-Z]", re.M)
WHY_RE = re.compile(r"^\s*why\b|\b(root cause|reason|what caused|cause of)\b", re.I)
CAUSE_SECTION_RE = re.compile(r"\b(cause|reason)", re.I)


@dataclass
class Scored:
    payload: dict
    fusion_rank: int
    fusion_score: float
    score: float = 0.0
    parts: dict = field(default_factory=dict)
    answerability: float | None = None


class MaxSimReranker:
    def __init__(self, embedder: Embedder, w_maxsim=1.0, w_exact=0.6, w_fusion=0.15, w_title=0.25):
        self.emb = embedder
        self.w = dict(maxsim=w_maxsim, exact=w_exact, fusion=w_fusion, title=w_title)

    def maxsim(self, q_words: list[str], doc_words: list[str]) -> tuple[float, float]:
        """Mean over question words of the best cosine with any chunk word,
        and the share of question words that have a near-exact match."""
        if not q_words or not doc_words:
            return 0.0, 0.0
        qv = self.emb.word_vectors(q_words)
        dv = self.emb.word_vectors(list(dict.fromkeys(doc_words)))
        sims = qv @ dv.T
        best = sims.max(axis=1)
        return float(best.mean()), float((best > 0.8).mean())

    def score(self, question: str, cands: list[Scored]) -> list[Scored]:
        q_words = list(dict.fromkeys(content_words(question)))
        q_codes, q_nums = exact_items(question)
        q_exact = q_codes | q_nums
        n = max(len(cands), 1)
        wants_steps = PROCEDURE_RE.search(question) is not None
        wants_why = WHY_RE.search(question) is not None
        for c in cands:
            p = c.payload
            body = f"{p.get('doc_no', '')} {p.get('title', '')} {p.get('section', '')}\n{p.get('text', '')}"
            ms, cov = self.maxsim(q_words, content_words(body))
            exact = missing = 0.0
            if q_exact:
                b_codes, b_nums = exact_items(body)
                doc_codes = set(p.get("doc_codes", []))
                in_chunk = q_exact & (b_codes | b_nums)
                # a code named elsewhere in the same document counts most of the way
                in_doc = (q_codes & doc_codes) - in_chunk
                exact = (len(in_chunk) + 0.75 * len(in_doc)) / len(q_exact)
                if q_codes:
                    missing = len(q_codes - b_codes - doc_codes) / len(q_codes)
            title_words = set(content_words(f"{p.get('title', '')} {p.get('section', '')}"))
            title = len(set(q_words) & title_words) / len(q_words) if q_words else 0.0
            fusion = 1 - c.fusion_rank / n
            steps = 0.3 if wants_steps and len(STEP_LINE_RE.findall(p.get("text", ""))) >= 3 else 0.0
            why = 0.3 if wants_why and CAUSE_SECTION_RE.search(p.get("section", "")) else 0.0
            phrase = phrase_overlap(q_words, content_words(p.get("title", "")), content_words(p.get("section", "")),
                                    content_words(p.get("text", "")))
            c.parts = {"maxsim": round(ms, 4), "coverage": round(cov, 4), "exact": round(exact, 4),
                       "missing_codes": round(missing, 4), "title": round(title, 4), "fusion": round(fusion, 4),
                       "steps": steps, "why": why, "phrase": round(phrase, 4)}
            c.score = (self.w["maxsim"] * ms + self.w["exact"] * exact + self.w["title"] * title
                       + self.w["fusion"] * fusion + steps + why + 0.3 * phrase - 0.4 * missing)
            c.answerability = ms + 0.3 * exact - 0.5 * missing
        return sorted(cands, key=lambda c: c.score, reverse=True)


def normalise(scores: list[float]) -> np.ndarray:
    a = np.asarray(scores, dtype=float)
    if a.size == 0 or np.ptp(a) == 0:
        return np.zeros_like(a)
    return (a - a.min()) / np.ptp(a)
