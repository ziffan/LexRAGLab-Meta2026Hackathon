"""Hash profil (DATA-CONTRACTS 11, H-068). Semua hash = SHA-256 heks atas JSON kanonik (sama dengan `backend/chunking/model.py`).

Dua hash potongan berbeda tujuan dan tidak boleh tertukar (I-43):
- `profile_chunk_set_hash` (di sini) = `Profile.chunk_set_hash`: atas pasangan `(chunk_id, teks)`, tanpa data encoder;
- `backend.retrieval.dense.embedding_set_hash` = kunci cache embedding: memuat encoder.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from backend.chunking.model import sha256_hex


def corpus_hash(docs: Iterable[Any]) -> str:
    """A1: pasangan `(doc_id, sha256)` mentah semua dokumen keluarga profil, urut `doc_id`. Urutan muat tak berpengaruh."""
    return sha256_hex([[d.doc_id, d.sha256] for d in sorted(docs, key=lambda d: d.doc_id)])


def clean_text_hash(docs: Iterable[Any]) -> str:
    """A6: pasangan `(doc_id, clean_sha256)` terurut menurut `doc_id`."""
    return sha256_hex([[d.doc_id, d.clean_sha256] for d in sorted(docs, key=lambda d: d.doc_id)])


def loader_rules(docs: Iterable[Any]) -> str:
    """Versi aturan pemuat bersama semua dokumen keluarga; bila beda antar dokumen, gabungan terurut (tak akan cocok)."""
    return ",".join(sorted({d.loader_rules_version for d in docs}))


def profile_chunk_set_hash(rows: Iterable[tuple[str, int, int, str, str]]) -> str:
    """A2-X, A21: hash atas `[[chunk_id, teks], ...]` terurut menurut (`doc_id`, `start`, `end`).
    `rows` = `(doc_id, start, end, chunk_id, teks)` diterima dalam urutan apa pun (urutan keluaran chunker dan urutan
    muat dokumen tidak berpengaruh)."""
    ordered = sorted(rows, key=lambda r: (r[0], r[1], r[2], r[3]))
    return sha256_hex([[r[3], r[4]] for r in ordered])


def chunk_rows(docs: Sequence[Any], chunks_by_doc: dict[str, Sequence[Any]]) -> list[tuple[str, int, int, str, str]]:
    """`(doc_id, start, end, chunk_id, teks)`; teks = `doc.text[start:end]` atas code point teks bersih."""
    out = []
    for d in docs:
        for c in chunks_by_doc.get(d.doc_id, ()):
            out.append((d.doc_id, c.start, c.end, c.chunk_id, d.text[c.start:c.end]))
    return out
