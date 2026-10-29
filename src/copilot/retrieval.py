"""Hybrid retrieval: dense + BM25 in Qdrant with reciprocal rank fusion,
role and revision filters, then reranking."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from .embeddings import Embedder
from .rerank import MaxSimReranker, Scored
from .sparse import BM25Encoder
from .store import VectorStore

REVISION_INTENT = re.compile(
    r"\brev(?:ision)?\.?\s+[A-Z]\b|\b(previous|earlier|old|older|superseded|former)\s+(rev|revision|version|value|torque|instruction)"
    r"|\bbefore\s+(the\s+)?(change|ecn|update)|\bused to be\b|\bwas it\b", re.I)

REV_TARGET = re.compile(r"\brev(?:ision)?\.?\s+([A-Z])\b")


@dataclass
class Retrieved:
    chunks: list[Scored]
    current_only: bool
    timings: dict


class Retriever:
    def __init__(self, store: VectorStore, embedder: Embedder, bm25: BM25Encoder,
                 reranker: MaxSimReranker | None, candidates: int = 30, rerank_top_n: int = 30,
                 current_only: bool = True):
        self.store, self.emb, self.bm25, self.reranker = store, embedder, bm25, reranker
        self.candidates, self.rerank_top_n, self.current_only = candidates, rerank_top_n, current_only

    def wants_history(self, question: str) -> bool:
        return REVISION_INTENT.search(question) is not None

    def retrieve(self, question: str, roles: list[str] | None, *, top_k: int = 5, mode: str = "hybrid",
                 rerank: bool = True, current_only: bool | None = None) -> Retrieved:
        t0 = time.perf_counter()
        if current_only is None:
            current_only = self.current_only and not self.wants_history(question)
        dense_q = self.emb.embed_one(question)
        sparse_q = self.bm25.encode_query(question)
        t1 = time.perf_counter()
        hits = self.store.search(dense_q, sparse_q, roles=roles, current_only=current_only, mode=mode,
                                 candidates=self.candidates, limit=self.rerank_top_n)
        t2 = time.perf_counter()
        cands = [Scored(payload=h.payload, fusion_rank=i, fusion_score=h.score) for i, h in enumerate(hits)]
        if rerank and self.reranker is not None and cands:
            cands = self.reranker.score(question, cands)
            target = REV_TARGET.search(question)
            if target and not current_only:
                # "what was it in revision B" -> prefer chunks of that revision
                for c in cands:
                    if c.payload.get("revision") == target.group(1):
                        c.score += 0.5
                        c.parts["revision"] = 0.5
                cands.sort(key=lambda c: c.score, reverse=True)
        else:
            for c in cands:
                c.score = c.fusion_score
        t3 = time.perf_counter()
        return Retrieved(chunks=cands[:top_k], current_only=current_only,
                         timings={"embed_ms": (t1 - t0) * 1e3, "search_ms": (t2 - t1) * 1e3,
                                  "rerank_ms": (t3 - t2) * 1e3})
