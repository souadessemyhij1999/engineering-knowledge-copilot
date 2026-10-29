"""The Copilot object wires everything together. The API, the scripts and
the tests all go through it."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .access import AccessPolicy, User
from .config import load_settings, resolve
from .db import Database
from .embeddings import Embedder
from .generation import NOT_FOUND, ExtractiveAnswerer, LLMAnswerer, source_label
from .guard import check_answer
from .ingest import Ingestor
from .rerank import MaxSimReranker
from .retrieval import Retriever
from .sparse import BM25Encoder
from .store import VectorStore

log = logging.getLogger(__name__)


@dataclass
class Answer:
    question: str
    answer: str
    abstained: bool
    mode: str
    sources: list[dict]
    guard: dict
    top_score: float
    answerability: float
    current_only: bool
    timings: dict = field(default_factory=dict)
    fallback: bool = False
    query_id: int | None = None


class Copilot:
    def __init__(self, settings: dict | None = None, use_db: bool = True):
        self.cfg = cfg = settings or load_settings()
        a = cfg["app"]
        self.policy = AccessPolicy(resolve(a["access_file"]), resolve(a["users_file"]), resolve(a["manifest"]))
        self.embedder = Embedder()
        q = cfg["qdrant"]
        path = q["path"] if q["path"] == ":memory:" else str(resolve(q["path"]))
        self.store = VectorStore(url=q["url"], path=path, collection=q["collection"], dim=self.embedder.dim)
        self.db = Database(cfg["database"]["url"]) if use_db else None
        b = cfg["bm25"]
        self.bm25 = BM25Encoder(b["k1"], b["b"], b["avg_doc_len"])
        r = cfg["rerank"]
        self.reranker = MaxSimReranker(self.embedder, r["w_maxsim"], r["w_exact"], r["w_fusion"], r["w_title"])
        rt = cfg["retrieval"]
        self.retriever = Retriever(self.store, self.embedder, self.bm25, self.reranker if r["enabled"] else None,
                                   rt["candidates"], rt["rerank_top_n"], rt["current_only"])
        ans = cfg["answer"]
        self.extractive = ExtractiveAnswerer(self.reranker, ans["min_score"], ans["max_sentences"], ans["margin"])
        self._llm = None
        c = cfg["chunking"]
        self.ingestor = Ingestor(self.store, self.db, self.embedder, self.bm25, self.policy,
                                 c["max_chars"], c["overlap_chars"])

    @property
    def llm(self) -> LLMAnswerer:
        if self._llm is None:
            a = self.cfg["answer"]
            self._llm = LLMAnswerer(a["llm_model"], a["llm_temperature"], a["llm_max_tokens"])
        return self._llm

    def roles_filter(self, user: User) -> list[str] | None:
        return None if user.role in self.policy.superuser_roles else self.policy.search_roles(user)

    def ask(self, question: str, user: User, mode: str | None = None, top_k: int | None = None,
            log_query: bool = True) -> Answer:
        t0 = time.perf_counter()
        mode = mode or self.cfg["answer"]["mode"]
        top_k = top_k or self.cfg["retrieval"]["top_k"]
        ret = self.retriever.retrieve(question, self.roles_filter(user), top_k=top_k)
        chunks = ret.chunks
        t1 = time.perf_counter()
        fallback = False
        draft = None
        used_llm = False
        if mode == "llm" and self.extractive.answerable(chunks, self.cfg["answer"]["llm_min_score"]):
            try:
                draft = self.llm.answer(question, chunks)
                used_llm = True
            except Exception as e:  # no key, network, rate limit -> extractive
                log.warning("LLM answer failed (%s), using extractive answer", e)
                fallback = True
        if draft is None:
            draft = self.extractive.answer(question, chunks)
        texts = [c.payload["text"] for c in chunks]
        guard = check_answer(draft.text, texts) if not draft.abstained else None
        if guard is not None and not guard.passed and used_llm and self.cfg["answer"]["fallback_on_guard_fail"]:
            log.info("guard rejected LLM answer: %s", guard.as_dict())
            draft = self.extractive.answer(question, chunks)
            guard = check_answer(draft.text, texts) if not draft.abstained else None
            fallback = True
        t2 = time.perf_counter()

        sources = []
        if not draft.abstained:
            for i, c in enumerate(chunks, start=1):
                p = c.payload
                sources.append({"n": i, "cited": i in draft.used, "label": source_label(p), "doc_no": p["doc_no"],
                                "revision": p["revision"], "title": p["title"], "section": p["section"],
                                "page": p["page"], "status": p.get("status", ""), "chunk_id": p["chunk_id"],
                                "text": p["text"], "score": round(c.score, 4), "parts": c.parts})
        timings = {**{k: round(v, 1) for k, v in ret.timings.items()},
                   "answer_ms": round((t2 - t1) * 1e3, 1), "total_ms": round((t2 - t0) * 1e3, 1)}
        ans = Answer(question=question, answer=draft.text if not draft.abstained else NOT_FOUND,
                     abstained=draft.abstained,
                     mode="llm" if used_llm and not fallback else ("llm->extractive" if fallback else "extractive"),
                     sources=sources, guard=guard.as_dict() if guard else {"passed": True, "abstained": True},
                     top_score=round(chunks[0].score, 4) if chunks else 0.0,
                     answerability=round(chunks[0].answerability or 0.0, 4) if chunks else 0.0,
                     current_only=ret.current_only,
                     timings=timings, fallback=fallback)
        if log_query and self.db:
            ans.query_id = self.db.log_query(
                username=user.username, role=user.role, question=question, answer=ans.answer, mode=ans.mode,
                abstained=ans.abstained, guard_passed=bool(ans.guard.get("passed")), top_score=ans.top_score,
                latency_ms=timings["total_ms"], sources=[s["chunk_id"] for s in sources if s["cited"]])
        return ans

    def visible_documents(self, user: User) -> list[dict]:
        docs = {}
        for p in self.store.scroll_all(self.roles_filter(user)):
            key = (p["doc_no"], p["revision"])
            if key not in docs:
                docs[key] = {"doc_no": p["doc_no"], "revision": p["revision"], "title": p["title"],
                             "doc_type": p.get("doc_type", ""), "status": p.get("status", ""),
                             "effective": p.get("effective", ""), "is_current": p.get("is_current", True),
                             "classification": p.get("classification", ""), "chunks": 0}
            docs[key]["chunks"] += 1
        return sorted(docs.values(), key=lambda d: (d["doc_no"], d["revision"]))
