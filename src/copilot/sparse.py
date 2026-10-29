"""BM25 as Qdrant sparse vectors.

The document side stores the BM25 term-frequency part; Qdrant multiplies it
with IDF at query time (collection created with Modifier.IDF), so adding
documents never requires re-indexing the others. The query side is a plain
1.0 per unique term.
"""
from __future__ import annotations

import zlib
from collections import Counter

from .text import tokens


def term_id(term: str) -> int:
    return zlib.crc32(term.encode("utf-8")) & 0x7FFFFFFF


class BM25Encoder:
    def __init__(self, k1: float = 1.2, b: float = 0.75, avg_doc_len: float = 110):
        self.k1, self.b, self.avg = k1, b, avg_doc_len

    def encode_doc(self, text: str) -> tuple[list[int], list[float]]:
        toks = tokens(text)
        dl = max(len(toks), 1)
        tf = Counter(toks)
        idx, val = [], []
        for t, f in tf.items():
            idx.append(term_id(t))
            val.append(f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg)))
        return idx, val

    def encode_query(self, text: str) -> tuple[list[int], list[float]]:
        uniq = list(dict.fromkeys(tokens(text)))
        return [term_id(t) for t in uniq], [1.0] * len(uniq)
