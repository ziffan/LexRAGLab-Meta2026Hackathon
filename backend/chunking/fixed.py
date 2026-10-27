"""Chunker ukuran tetap (`fixed_size`): jendela token dengan overlap, per section dalam cakupan retrieval."""

from __future__ import annotations

from typing import Any

from backend import config
from backend.tokenizer import get_tokenizer

from .address_map import AddressMap, build_address_map
from .model import Chunk, make_chunk_id, make_chunker_key
from .structure import context_for


def fixed_key(cfg: dict[str, Any], size: int, overlap: int, tok: Any) -> str:
    return make_chunker_key("fixed_size", {
        "version": cfg["chunking"]["fixed_size_version"],
        "chunk_size_tokens": size, "overlap_tokens": overlap,
        "scope_sections": list(cfg["scope_sections"]),
        "tokenizer": tok.info.name, "tokenizer_version": tok.info.version,
    })


def chunk_fixed(doc: Any, *, size: int | None = None, overlap: int | None = None, amap: AddressMap | None = None,
                retrieval_cfg: dict[str, Any] | None = None, tokenizer: Any = None, grid_cfg: dict[str, Any] | None = None) -> list[Chunk]:
    """Jendela `size` token, langkah `size - overlap`, per section (tidak melintasi section, karena `Chunk.section`
    tunggal). Batas jendela di batas token tokenizer lokal; spasi tepi dipangkas (offset code point, setengah terbuka)."""
    cfg, scope, prefix, labels = context_for(doc, retrieval_cfg)
    if size is None or overlap is None:
        fx = (grid_cfg or config.load("grid"))["fixed_size"]
        size = fx["chunk_size_tokens"] if size is None else size
        overlap = fx["overlap_tokens"] if overlap is None else overlap
    if size <= 0 or not (0 <= overlap < size):
        raise ValueError(f"invalid fixed_size parameters: chunk_size_tokens={size}, overlap_tokens={overlap}")
    tok = tokenizer or get_tokenizer()
    amap = amap or build_address_map(doc.text, doc.sections, prefix, scope, labels)
    key = fixed_key(cfg, size, overlap, tok)
    default_labels = {"batang_tubuh": "Batang Tubuh", "penjelasan_pasal": "Penjelasan", "penjelasan_umum": "Penjelasan Umum"}
    out: list[Chunk] = []
    for sec in doc.sections:
        name = sec["section"]
        if name not in scope:
            continue
        s, e = sec["start"], sec["end"]
        sec_text = doc.text[s:e]
        offs = tok.offsets(sec_text)
        n = len(offs)
        i = 0
        while i < n:
            j = min(i + size, n)
            a, b = offs[i][0], offs[j - 1][1]
            piece = sec_text[a:b]
            lead = len(piece) - len(piece.lstrip())
            trail = len(piece) - len(piece.rstrip())
            if lead < len(piece):  # bukan jendela kosong-spasi
                st, en = s + a + lead, s + b - trail
                text = doc.text[st:en]
                address, levels, warns = amap.address_for_range(st, en, name, prefix, labels.get(name) or default_labels.get(name, name))
                out.append(Chunk(
                    chunk_id=make_chunk_id(doc.doc_id, st, en, key), doc_id=doc.doc_id, chunker_key=key, start=st, end=en,
                    clean_sha256=doc.clean_sha256, section=name, address=address, address_levels=levels,
                    tokens_local=tok.count(text), warnings=warns,
                ))
            if j == n:
                break
            i += size - overlap
    return out
