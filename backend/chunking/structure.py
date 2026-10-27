"""Chunker struktur tulisan tangan (`structure_handwritten`): satu potongan per unit peta alamat."""

from __future__ import annotations

from typing import Any

from backend import config
from backend.tokenizer import get_tokenizer

from .address_map import AddressMap, build_address_map, levels_to_dicts
from .model import NO_MARKER_WARNING, Chunk, make_chunk_id, make_chunker_key


def context_for(doc: Any, retrieval_cfg: dict[str, Any] | None) -> tuple[dict[str, Any], set[str], str, dict[str, str]]:
    cfg = retrieval_cfg if retrieval_cfg is not None else config.load("retrieval")
    scope = set(cfg["scope_sections"])
    prefix = doc.metadata.get("address_prefix") or doc.doc_id
    return cfg, scope, prefix, dict(cfg.get("chunking", {}).get("section_labels", {}))


def structure_key(cfg: dict[str, Any], tok: Any) -> str:
    """Tokenizer (nama + versi) ikut kunci: `tokens_local` bergantung padanya, jadi ganti tokenizer = `chunk_id` baru."""
    return make_chunker_key("structure_handwritten", {
        "version": cfg["chunking"]["structure_version"],
        "scope_sections": list(cfg["scope_sections"]),
        "tokenizer": tok.info.name, "tokenizer_version": tok.info.version,
    })


def chunk_structure(doc: Any, *, amap: AddressMap | None = None, retrieval_cfg: dict[str, Any] | None = None, tokenizer: Any = None) -> list[Chunk]:
    """Satu potongan per unit di section dalam cakupan retrieval. Section tanpa penanda struktur:
    satu potongan per section dengan peringatan `no structural marker, fallback per section`.

    H-064: potongan unit pertama tiap Pasal (ayat (1), atau "Ayat (1)" Penjelasan tanpa isi pembuka) mulai di heading
    Pasal (`Unit.lead`); alamat dan unit Recall@K (`Unit.start/end`, M1.2 A4) tidak berubah."""
    cfg, scope, prefix, labels = context_for(doc, retrieval_cfg)
    tok = tokenizer or get_tokenizer()
    amap = amap or build_address_map(doc.text, doc.sections, prefix, scope, labels)
    key = structure_key(cfg, tok)
    out: list[Chunk] = []
    for u in amap.in_sections(scope):
        out.append(Chunk(
            chunk_id=make_chunk_id(doc.doc_id, u.lead, u.end, key), doc_id=doc.doc_id, chunker_key=key,
            start=u.lead, end=u.end, clean_sha256=doc.clean_sha256, section=u.section, address=u.address,
            address_levels=levels_to_dicts(u.levels), tokens_local=tok.count(doc.text[u.lead:u.end]),
            warnings=[NO_MARKER_WARNING] if u.fallback else [],
        ))
    return out
