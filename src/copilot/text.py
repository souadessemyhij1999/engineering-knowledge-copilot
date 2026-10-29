"""Small text helpers shared by keyword search, reranking and the guard."""
from __future__ import annotations

import re

STOPWORDS = set("""
a an the and or of to in on at for from by with without is are was were be been being this that these those
it its as if then than what which who whom when where why how do does did can could should would may might must
shall will i we you he she they them our your their my me us not no yes there here any all each every some such
into over under after before about between per via also only up down out so very just has have had
""".split())

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,/-][a-z0-9]+)*", re.I)
CODE_RE = re.compile(r"\b(?:[A-Z]{1,4}\d*-)+[A-Z0-9]+(?:-\d+)*\b|\b[A-Z]{1,3}\d+(?:x\d+(?:\.\d+)?)?\b|\bO\d{4}\b")
NUM_RE = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)*(?![\w])")


def tokens(text: str) -> list[str]:
    """Lower-cased tokens. Compound codes like 'wi-asm-014' or 'm14x1.5' are
    kept whole and also split into their parts, so 'E-205' matches '205'."""
    out = []
    for t in TOKEN_RE.findall(text.lower()):
        if t in STOPWORDS:
            continue
        out.append(t)
        if re.search(r"[.,/-]", t):
            out.extend(p for p in re.split(r"[.,/-]", t) if p and p not in STOPWORDS and len(p) > 1)
    return out


def content_words(text: str) -> list[str]:
    text = text.lower().replace("%", " percent ")
    return [t for t in re.findall(r"[a-z][a-z0-9]+", text) if t not in STOPWORDS and len(t) > 2]


def bigrams(words: list[str]) -> set[tuple[str, str]]:
    """Adjacent word pairs, lightly stemmed so 'tested' still pairs with 'test'."""
    st = [re.sub(r"(ing|ed|es|s)$", "", w) if len(w) > 4 else w for w in words]
    return set(zip(st, st[1:]))


def phrase_overlap(q_words: list[str], *texts_words: list[str]) -> float:
    qb = bigrams(q_words)
    if not qb:
        return 0.0
    have = set()
    for w in texts_words:
        have |= bigrams(w)
    return len(qb & have) / len(qb)


def codes(text: str) -> set[str]:
    return {c.upper() for c in CODE_RE.findall(text)}


def numbers(text: str) -> set[str]:
    """Numbers normalised: '0,5' -> '0.5', '1,412' -> '1412', '45.0' -> '45'."""
    out = set()
    for n in NUM_RE.findall(text):
        n = n.lstrip("+")
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", n):
            n = n.replace(",", "")
        n = n.replace(",", ".")
        try:
            f = float(n)
            out.add(str(int(f)) if f.is_integer() else str(f))
        except ValueError:
            continue
    return out


def exact_items(text: str) -> tuple[set[str], set[str]]:
    """Codes and numbers used for exact matching. Bare years are left out,
    "2026" appears in half of the documents and says little."""
    nums = {n for n in numbers(text) if not (n.isdigit() and len(n) == 4 and 1990 <= int(n) <= 2100)}
    return codes(text), nums


def split_sentences(text: str, keep_whole: int = 260) -> list[str]:
    """Answer units: table rows and short list items stay whole, longer
    paragraphs are split into sentences."""
    parts = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if (";" in line and ":" in line) or len(line) <= keep_whole:
            parts.append(line)
            continue
        parts.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line) if s.strip())
    return parts
