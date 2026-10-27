"""BM25 + Sastrawi (A14, Tier 2). Korpus mainan sintetis."""

from backend.retrieval.bm25 import Bm25Retriever, tokenize

PARAMS = dict(k1=1.5, b=0.75, stemming=True, stopwords=True)

DOCS = [
    ("d1", "Pemberhentian anggota direksi dilakukan oleh RUPS dengan menyebut alasannya."),
    ("d2", "Komisaris mengawasi jalannya perseroan dan memberi nasihat kepada direksi."),
    ("d3", "Pembubaran perseroan ditetapkan oleh RUPS."),
    ("d4", "Modal dasar perseroan terdiri atas saham."),
    ("d5", "Laporan tahunan disampaikan setiap akhir tahun buku."),
]


def test_sastrawi_unifies_pemberhentian_and_diberhentikan():
    a = tokenize("pemberhentian", stemming=True, stopwords=False)
    b = tokenize("diberhentikan", stemming=True, stopwords=False)
    assert a == b == ["henti"]
    assert tokenize("diberhentikan", stemming=False, stopwords=False) == ["diberhentikan"]


def test_stemming_matches_inflected_query_to_document():
    r = Bm25Retriever(DOCS, **PARAMS)
    assert r.rank("diberhentikan")[0][0] == "d1"
    off = Bm25Retriever(DOCS, **{**PARAMS, "stemming": False})
    assert off.rank("diberhentikan") == []  # tanpa stemming tidak ada kecocokan literal


def test_stopword_toggle():
    assert tokenize("yang untuk direksi", stemming=False, stopwords=True) == ["direksi"]
    assert tokenize("yang untuk direksi", stemming=False, stopwords=False) == ["yang", "untuk", "direksi"]


def test_ranking_orders_by_relevance_and_only_matching_docs():
    r = Bm25Retriever(DOCS, **PARAMS)
    out = r.rank("pembubaran perseroan")
    ids = [c for c, _ in out]
    assert ids[0] == "d3"
    assert "d5" not in ids
    scores = [s for _, s in out]
    assert scores == sorted(scores, reverse=True)
    assert [c for c, _ in r.rank("pembubaran perseroan", top_n=2)] == ids[:2]


def test_deterministic_and_tie_break_by_chunk_id():
    docs = [("z", "saham biasa"), ("a", "saham biasa"), ("m", "saham biasa"), ("x", "laporan tahunan"), ("y", "direksi")]
    r1 = Bm25Retriever(docs, **PARAMS).rank("saham")
    r2 = Bm25Retriever(list(reversed(docs)), **PARAMS).rank("saham")
    assert r1 == r2
    assert [c for c, _ in r1] == ["a", "m", "z"]


def test_empty_query_and_empty_corpus_give_empty_ranking():
    r = Bm25Retriever(DOCS, **PARAMS)
    assert r.rank("") == [] and r.rank("   ") == [] and r.rank("yang dan") == []
    assert Bm25Retriever([], **PARAMS).rank("direksi") == []
    assert Bm25Retriever([("a", "")], **PARAMS).rank("direksi") == []


def test_unknown_term_returns_empty():
    assert Bm25Retriever(DOCS, **PARAMS).rank("xylophone") == []


def test_duplicate_chunk_id_rejected():
    import pytest

    with pytest.raises(ValueError):
        Bm25Retriever([("a", "x"), ("a", "y")], **PARAMS)


def test_query_and_document_case_insensitive():
    r = Bm25Retriever(DOCS, **PARAMS)
    assert r.rank("PEMBUBARAN Perseroan") == r.rank("pembubaran perseroan")
    assert r.rank("DIREKSI")[0][0] in {"d1", "d2"}
    up = Bm25Retriever([(i, t.upper()) for i, t in DOCS], **PARAMS)
    assert [c for c, _ in up.rank("pembubaran perseroan")] == [c for c, _ in r.rank("pembubaran perseroan")]


def test_corpus_with_empty_and_stopword_only_documents():
    docs = DOCS + [("e1", ""), ("e2", "yang dan untuk")]
    r = Bm25Retriever(docs, **PARAMS)
    ids = [c for c, _ in r.rank("pembubaran perseroan")]
    assert ids[0] == "d3" and "e1" not in ids and "e2" not in ids
    assert r.rank("direksi") == Bm25Retriever(docs, **PARAMS).rank("direksi")
