"""Answer generation.

Two answerers with the same interface:

* ExtractiveAnswerer - no LLM. Picks the sentences / table rows from the
  retrieved chunks that best match the question and cites them. Cannot make
  things up, which is why it is the default and what the offline
  evaluation measures.
* LLMAnswerer - LangChain + Claude. Writes a fluent answer from the numbered
  sources only, with [n] citations. Its output always goes through the guard;
  if the guard fails, the copilot falls back to the extractive answer.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .rerank import CAUSE_SECTION_RE, PROCEDURE_RE, WHY_RE, MaxSimReranker, Scored
from .text import content_words, exact_items, numbers, phrase_overlap, split_sentences

NOT_FOUND = "I could not find this in the documents you have access to."

# questions that expect a value as the answer (classic answer-type detection)
VALUE_RE = re.compile(r"\b(how (much|many|long|often|wide|tight|loud|quickly|high|low)|what (is|was|are) the|which .*"
                      r"(value|limit|range|size|voltage|pressure)|torque|pressure|concentration|tolerance|interval|"
                      r"limit|rate|voltage|width|temperature|resistance|force)\b", re.I)
STEP_RE = re.compile(r"^\d+\s+[A-Z]")



@dataclass
class Draft:
    text: str
    abstained: bool
    used: list[int]          # 1-based source numbers used


def source_label(p: dict) -> str:
    return f"{p['doc_no']} Rev {p['revision']}, {p['section']}, p. {p['page']}"


class ExtractiveAnswerer:
    def __init__(self, reranker: MaxSimReranker, min_score: float = 0.8, max_sentences: int = 3,
                 margin: float = 0.4):
        self.rr, self.min_score, self.max_sentences, self.margin = reranker, min_score, max_sentences, margin

    def answerable(self, chunks: list[Scored], min_score: float | None = None) -> bool:
        if not chunks:
            return False
        a = chunks[0].answerability
        return (a if a is not None else chunks[0].score) >= (self.min_score if min_score is None else min_score)

    def answer(self, question: str, chunks: list[Scored]) -> Draft:
        if not self.answerable(chunks):
            return Draft(NOT_FOUND, True, [])
        q_words = list(dict.fromkeys(content_words(question)))
        q_codes, q_nums = exact_items(question)
        q_exact = q_codes | q_nums
        wants_value = VALUE_RE.search(question) is not None
        wants_steps = PROCEDURE_RE.search(question) is not None
        wants_why = WHY_RE.search(question) is not None
        cands = []
        for rank, c in enumerate(chunks[:5]):
            sents = split_sentences(c.payload["text"])
            ctx_words = content_words(f"{c.payload.get('title', '')} {c.payload.get('section', '')}")
            why = 0.15 if wants_why and CAUSE_SECTION_RE.search(c.payload.get("section", "")) else 0.0
            for pos, s in enumerate(sents):
                s = re.sub(r"^[-\u2022]\s+", "", s)
                s_words = content_words(s)
                ms, _ = self.rr.maxsim(q_words, s_words + ctx_words)
                phrase = phrase_overlap(q_words, s_words, ctx_words)
                s_codes, s_nums = exact_items(s)
                ex = len(q_exact & (s_codes | s_nums)) / len(q_exact) if q_exact else 0.0
                # a question asking for a value wants a sentence that has one
                has_num = (0.15 if wants_value else 0.05) if numbers(s) else 0.0
                score = ms + 0.5 * ex + 0.3 * phrase + has_num + why + 0.1 * c.score - 0.04 * rank
                cands.append((score, rank, pos, s))
        if not cands:
            return Draft(NOT_FOUND, True, [])
        cands.sort(key=lambda x: x[0], reverse=True)
        best = cands[0][0]
        top_rank = cands[0][1]
        if wants_steps:
            steps = [x for x in cands if x[1] == top_rank and STEP_RE.match(x[3])]
            if len(steps) >= 3:
                # a procedure question gets the whole step list, in order
                steps.sort(key=lambda x: x[2])
                lines = [f"- {s.rstrip()} [{top_rank + 1}]" for _, _, _, s in steps[:12]]
                return Draft("\n".join(lines), False, [top_rank + 1])
        n_max = self.max_sentences
        picked = [cands[0]]
        for cand in cands[1:]:
            if len(picked) >= n_max:
                break
            if cand[0] >= best - self.margin and cand[3] not in {p[3] for p in picked}:
                picked.append(cand)
        # keep document order inside a source so procedures read naturally
        picked.sort(key=lambda x: (x[1], x[2]))
        lines = [f"- {s.rstrip()} [{rank + 1}]" for _, rank, _, s in picked]
        return Draft("\n".join(lines), False, sorted({r + 1 for _, r, _, _ in picked}))


SYSTEM_PROMPT = """You are the engineering knowledge assistant of a manufacturing plant.
Answer the question using ONLY the numbered sources below.
Rules:
- Cite every sentence with the source number in square brackets, e.g. [2].
- Copy numbers, limits and units exactly as written in the sources.
- If the sources do not contain the answer, reply exactly: NOT_FOUND
- If sources disagree, prefer the current revision and say so.
- Be short and practical. Use a list for steps."""


class LLMAnswerer:
    def __init__(self, model: str = "claude-haiku-5-5", temperature: float = 0.0, max_tokens: int = 500):
        from langchain_anthropic import ChatAnthropic
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.llm = ChatAnthropic(model=model, temperature=temperature, max_tokens=max_tokens)

    @staticmethod
    def build_messages(question: str, chunks: list[Scored]):
        from langchain_core.messages import HumanMessage, SystemMessage
        src = "\n\n".join(
            f"[{i}] {source_label(c.payload)} (status: {c.payload.get('status', '')})\n{c.payload['text']}"
            for i, c in enumerate(chunks, start=1))
        return [SystemMessage(SYSTEM_PROMPT), HumanMessage(f"Sources:\n{src}\n\nQuestion: {question}")]

    def answer(self, question: str, chunks: list[Scored]) -> Draft:
        if not chunks:
            return Draft(NOT_FOUND, True, [])
        out = self.llm.invoke(self.build_messages(question, chunks))
        text = out.content if isinstance(out.content, str) else "".join(
            b.get("text", "") for b in out.content if isinstance(b, dict))
        text = text.strip()
        if text.startswith("NOT_FOUND") or not text:
            return Draft(NOT_FOUND, True, [])
        used = sorted({int(x) for x in re.findall(r"\[(\d+)\]", text) if 1 <= int(x) <= len(chunks)})
        return Draft(text, False, used)
