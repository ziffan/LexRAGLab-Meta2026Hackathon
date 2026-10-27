"""Chunker ukuran tetap (`fixed_size`): jendela token dengan overlap, berurutan atas teks dalam cakupan retrieval (H-062)."""

from __future__ import annotations

from bisect import bisect_right
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


def scope_runs(doc: Any, scope: set[str]) -> list[list[dict[str, Any]]]:
    """Rentang section dalam cakupan, berurutan menurut offset, dikelompokkan jadi deret yang bersambung
    (akhir section = awal section berikutnya). Section di luar cakupan di antaranya = celah: jendela tidak melintasinya
    (kontrak `start/end` tunggal, H-062)."""
    runs: list[list[dict[str, Any]]] = []
    for sec in sorted((x for x in doc.sections if x["section"] in scope), key=lambda x: (x["start"], x["end"])):
        if runs and runs[-1][-1]["end"] == sec["start"]:
            runs[-1].append(sec)
        else:
            runs.append([sec])
    return runs


def chunk_fixed(doc: Any, *, size: int | None = None, overlap: int | None = None, amap: AddressMap | None = None,
                retrieval_cfg: dict[str, Any] | None = None, tokenizer: Any = None, grid_cfg: dict[str, Any] | None = None) -> list[Chunk]:
    """Jendela `size` token, langkah `size - overlap`, berurutan atas teks dalam cakupan retrieval; melintasi batas Pasal
    dan section selama rentangnya bersambung (H-062). `Chunk.section` = section di posisi awal potongan; alamat = rentang
    `<awal> – <akhir>` bila beririsan beberapa unit. Batas jendela di batas token tokenizer lokal; spasi tepi dipangkas
    (offset code point, setengah terbuka)."""
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
    for run in scope_runs(doc, scope):
        s, e = run[0]["start"], run[-1]["end"]
        starts = [x["start"] for x in run]
        run_text = doc.text[s:e]
        offs = tok.offsets(run_text)
        n = len(offs)
        i = 0
        while i < n:
            j = min(i + size, n)
            a, b = offs[i][0], offs[j - 1][1]
            piece = run_text[a:b]
            lead = len(piece) - len(piece.lstrip())
            trail = len(piece) - len(piece.rstrip())
            if lead < len(piece):  # bukan jendela kosong-spasi
                st, en = s + a + lead, s + b - trail
                name = run[bisect_right(starts, st) - 1]["section"]  # section di posisi awal
                text = doc.text[st:en]
                address, levels, warns = amap.address_for_range(st, en, name, prefix, labels.get(name) or default_labels.get(name, name),
                                                                across_sections=True)
                out.append(Chunk(
                    chunk_id=make_chunk_id(doc.doc_id, st, en, key), doc_id=doc.doc_id, chunker_key=key, start=st, end=en,
                    clean_sha256=doc.clean_sha256, section=name, address=address, address_levels=levels,
                    tokens_local=tok.count(text), warnings=warns,
                ))
            if j == n:
                break
            i += size - overlap
    return out
