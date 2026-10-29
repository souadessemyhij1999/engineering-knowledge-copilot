"""Dense embeddings with WordLlama (MIT licence, 256-dim, weights ship inside
the pip package so nothing is downloaded at runtime and it runs on CPU in
milliseconds).

The class also exposes word vectors for the late-interaction reranker.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np


@lru_cache(maxsize=1)
def _load_wordllama():
    import wordllama
    from wordllama import WordLlama
    pkg = Path(wordllama.__file__).parent
    return WordLlama.load(cache_dir=pkg, disable_download=True)


class Embedder:
    dim = 256
    name = "wordllama-l2_supercat-256"

    def __init__(self):
        self.wl = _load_wordllama()
        self._word_cache: dict[str, np.ndarray] = {}

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.asarray(self.wl.embed(texts, norm=True), dtype=np.float32)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    def word_vectors(self, words: list[str]) -> np.ndarray:
        """Unit vectors for single words (cached)."""
        missing = [w for w in dict.fromkeys(words) if w not in self._word_cache]
        if missing:
            for w, v in zip(missing, self.embed(missing)):
                self._word_cache[w] = v
        if not words:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self._word_cache[w] for w in words])

