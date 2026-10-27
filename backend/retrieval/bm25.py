"""Retriever BM25 (rank-bm25 0.2.2) dengan tokenisasi Indonesia dan stemmer Sastrawi (A14).

Parameter (`k1`, `b`, stemming, stopword) disuntik pemanggil dari `config/retrieval.toml` `[bm25]`.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Sequence

from rank_bm25 import BM25Okapi

_WORD = re.compile(r"\w+", re.UNICODE)


@lru_cache(maxsize=1)
def _stemmer():
    from Sastrawi.Stemmer.StemmerFactory import StemmerFactory

    return StemmerFactory().create_stemmer()


@lru_cache(maxsize=1)
def _stopwords() -> frozenset[str]:
    from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory

    return frozenset(StopWordRemoverFactory().get_stop_words())


@lru_cache(maxsize=200_000)
def _stem(word: str) -> str:
    return _stemmer().stem(word)


def tokenize(text: str, *, stemming: bool, stopwords: bool) -> list[str]:
    toks = _WORD.findall(text.lower())
    if stopwords:
        sw = _stopwords()
        toks = [t for t in toks if t not in sw]
    if stemming:
        toks = [_stem(t) for t in toks]
    return toks


class Bm25Retriever:
    def __init__(
        self,
        docs: Sequence[tuple[str, str]],
        *,
        k1: float,
        b: float,
        stemming: bool,
        stopwords: bool,
    ):
        """`docs` = daftar `(chunk_id, text)`. chunk_id harus unik."""
        ids = [d[0] for d in docs]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate chunk_id")
        self._stemming, self._stopwords = stemming, stopwords
        self._ids = ids
        self._toks = [tokenize(t, stemming=stemming, stopwords=stopwords) for _, t in docs]
        self._sets = [set(t) for t in self._toks]
        # rank-bm25 gagal pada korpus kosong atau semua dokumen kosong (pembagian nol)
        usable = bool(self._toks) and any(self._toks)
        self._bm25 = BM25Okapi([t or ["\x00"] for t in self._toks], k1=k1, b=b) if usable else None

    def rank(self, query: str, top_n: int | None = None) -> list[tuple[str, float]]:
        """Ranking `(chunk_id, skor)` menurun; hanya dokumen yang memuat minimal satu istilah query.
        Seri skor dipecah `chunk_id` naik (deterministik). Query kosong -> []."""
        q = tokenize(query, stemming=self._stemming, stopwords=self._stopwords)
        if not q or self._bm25 is None:
            return []
        scores = self._bm25.get_scores(q)
        qs = set(q)
        hits = [(self._ids[i], float(scores[i])) for i in range(len(self._ids)) if self._sets[i] & qs]
        hits.sort(key=lambda x: (-x[1], x[0]))
        return hits if top_n is None else hits[:top_n]
