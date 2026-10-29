"""Hallucination guard. Runs on every answer before it is returned.

Checks:
1. every [n] citation points to a source that was actually given,
2. every sentence with real content carries a citation,
3. every number in the answer appears in the cited sources (numbers are
   where a wrong answer hurts most on the shop floor: torques, pressures,
   limits),
4. the words of each sentence are supported by the sources it cites.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import content_words, numbers

CITE_RE = re.compile(r"\[(\d+)\]")


@dataclass
class GuardReport:
    passed: bool
    invalid_citations: list[int] = field(default_factory=list)
    uncited_sentences: list[str] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    weak_sentences: list[str] = field(default_factory=list)
    support: float = 1.0
    cited: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


CLAIM_RE = re.compile(r"(.*?)((?:\s*\[\d+\])+)", re.S)


def _claims(answer: str) -> list[tuple[str, list[int]]]:
    """Split an answer into claims. A claim is the text up to a citation
    group like "[1]" or "[1][3]"; the citation covers every sentence since
    the previous citation on the same line. Text after the last citation of
    a line is an uncited claim."""
    out = []
    for line in answer.splitlines():
        line = line.strip().lstrip("-*• ").strip()
        if not line:
            continue
        pos = 0
        for m in CLAIM_RE.finditer(line):
            text = m.group(1).strip(" ;,")
            cites = [int(x) for x in re.findall(r"\d+", m.group(2))]
            if text:
                out.append((text, cites))
            pos = m.end()
        rest = line[pos:].strip(" .;,")
        if rest:
            out.append((rest, []))
    return out


def check_answer(answer: str, sources: list[str], min_support: float = 0.5) -> GuardReport:
    n_src = len(sources)
    rep = GuardReport(passed=True)
    all_cites = [int(x) for x in CITE_RE.findall(answer)]
    rep.cited = sorted(set(c for c in all_cites if 1 <= c <= n_src))
    rep.invalid_citations = sorted(set(c for c in all_cites if not 1 <= c <= n_src))

    supports = []
    for plain, raw_cites in _claims(answer):
        cites = [c for c in raw_cites if 1 <= c <= n_src]
        words = content_words(plain)
        if len(words) < 3 and not numbers(plain):
            continue
        if not cites:
            rep.uncited_sentences.append(plain.strip())
            ctx = " ".join(sources)
        else:
            ctx = " ".join(sources[c - 1] for c in cites)
        ctx_nums, ctx_words = numbers(ctx), set(content_words(ctx))
        rep.unsupported_numbers.extend(sorted(numbers(plain) - ctx_nums))
        if words:
            s = sum(w in ctx_words for w in words) / len(words)
            supports.append(s)
            if s < min_support:
                rep.weak_sentences.append(plain.strip())
    rep.support = round(min(supports), 3) if supports else 1.0
    rep.unsupported_numbers = sorted(set(rep.unsupported_numbers))
    rep.passed = not (rep.invalid_citations or rep.uncited_sentences or rep.unsupported_numbers or rep.weak_sentences)
    return rep
