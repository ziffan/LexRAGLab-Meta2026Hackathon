"""Verifikasi offset potongan terhadap teks sumber. Ketidakcocokan = galat (UI-SPEC U1), bukan peringatan."""

from __future__ import annotations

from typing import Any

from .model import Chunk, ChunkOffsetError, make_chunk_id


def verify_chunks(doc: Any, chunks: list[Chunk], scope: set[str] | None = None) -> None:
    """Tiap potongan: doc_id dan clean_sha256 sama dengan dokumen, chunk_id cocok dengan offsetnya, 0 <= start < end <= len(teks), teks tidak kosong
    dan tanpa spasi di tepi, dan awalnya di dalam rentang section bernama `chunk.section`. Seluruhnya harus di dalam deret section yang
    bersambung dari section itu (H-062: fixed_size melintasi section); dengan `scope`, hanya section dalam cakupan yang
    boleh dilintasi, dan bukan celah di luar cakupan."""
    n = len(doc.text)
    spans: dict[str, list[tuple[int, int]]] = {}
    merged: list[list[int]] = []  # deret bersambung (akhir = awal berikutnya), hanya section dalam cakupan bila `scope`
    for s in sorted(doc.sections, key=lambda x: (x["start"], x["end"])):
        if scope is None or s["section"] in scope:
            if merged and merged[-1][1] == s["start"]:
                merged[-1][1] = s["end"]
            else:
                merged.append([s["start"], s["end"]])
    for s in doc.sections:
        spans.setdefault(s["section"], []).append((s["start"], s["end"]))
    for c in chunks:
        if c.doc_id != doc.doc_id:
            raise ChunkOffsetError(f"chunk {c.chunk_id[:12]} belongs to doc {c.doc_id!r}, not {doc.doc_id!r}")
        if c.clean_sha256 != doc.clean_sha256:
            raise ChunkOffsetError(f"chunk {c.chunk_id[:12]} has clean_sha256 {c.clean_sha256[:12]} but the document is {doc.clean_sha256[:12]}")
        if c.chunk_id != make_chunk_id(c.doc_id, c.start, c.end, c.chunker_key):
            raise ChunkOffsetError(f"chunk {c.chunk_id[:12]} id does not match its (doc_id, start, end, chunker_key); offsets were altered")
        if not (0 <= c.start < c.end <= n):
            raise ChunkOffsetError(f"chunk {c.chunk_id[:12]} offsets [{c.start},{c.end}) are outside the text (length {n})")
        t = doc.text[c.start:c.end]
        if not t.strip() or t != t.strip():
            raise ChunkOffsetError(f"chunk {c.chunk_id[:12]} [{c.start},{c.end}) is empty or has edge whitespace")
        if not any(s <= c.start < e for s, e in spans.get(c.section, [])):
            raise ChunkOffsetError(f"chunk {c.chunk_id[:12]} [{c.start},{c.end}) does not start inside a {c.section!r} section range")
        if not any(s <= c.start and c.end <= e for s, e in merged):
            raise ChunkOffsetError(f"chunk {c.chunk_id[:12]} [{c.start},{c.end}) is not inside one contiguous run of sections")
