"""Chunker `structure_schema` (M3.4): potongan digerakkan `SchemaRecord` peran A, bukan parser tulisan tangan.

Fungsi murni `(dokumen, rekaman skema) -> Chunk[]`. Tafsir yang dipakai (dicatat untuk review):

- Unit potong = level `default_chunk_level`. Per section, bila level itu tidak punya penanda di section tersebut, dipakai
  level lain ber-`is_chunk_unit = true` (urutan terkecil dulu); bila tidak ada sama sekali, satu potongan per section dengan
  peringatan `NO_MARKER_WARNING` (sama dengan fallback struktur tulisan tangan). Skema yang hanya menandai satu level
  potong (mis. UU PT v1) berperilaku persis "unit = default_chunk_level".
- Potongan = dari awal penanda unit sampai sebelum penanda unit berikutnya ATAU penanda level lain yang bukan turunan
  unit (turunan = rantai `parent_order`), ATAU akhir section; spasi tepi dipangkas. Teks sebelum penanda pertama di
  section tidak masuk potongan mana pun. Potongan tidak melintasi section.
- H-064 (heading Pasal masuk potongan pertama) hanya untuk `structure_handwritten`; di sini batas mengikuti skema:
  bila skema memberi penanda Pasal, heading ikut potongan itu karena penandanya adalah heading.
- Pola dijalankan `re` (`MULTILINE`, `finditer` per section); pola sudah divalidasi aman saat disimpan (H-072) dan
  dikompilasi ulang lewat `compile_marker`.
- Alamat: dari peta alamat tulisan tangan (prinsip keadilan, DATA-CONTRACTS §3), rentang `<awal> – <akhir>` bila
  potongan beririsan beberapa unit. Antarmuka `AddressFn` memungkinkan akta (M4.1) menyuplai peta alamat dari skema.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Sequence

from backend.schema_a.schema import compile_marker
from backend.tokenizer import get_tokenizer

from .address_map import build_address_map
from .model import NO_MARKER_WARNING, Chunk, make_chunk_id, make_chunker_key, sha256_hex
from .structure import context_for

SCHEMA_CHUNKER_VERSION = 1  # naikkan bila aturan batas/alamat berubah; dapat ditimpa `config/retrieval [chunking].schema_chunker_version`

# (start, end, section) -> (address, address_levels, warnings)
AddressFn = Callable[[int, int, str], "tuple[str, list[dict[str, str]], list[str]]"]


class SchemaChunkerError(ValueError):
    """Skema tidak bisa dipakai untuk memotong (pola rusak, level potong tidak ada)."""


def body_hash(body: Mapping[str, Any]) -> str:
    """Hash isi skema (tubuh saja, bukan catatan/versi/waktu): skema sama = hash sama."""
    return sha256_hex(body)


def schema_identity(record: Mapping[str, Any]) -> dict[str, Any]:
    return {"family": record["family"], "schema_version": record["schema_version"], "schema_hash": body_hash(record["body"])}


def schema_key(cfg: dict[str, Any], record: Mapping[str, Any], tok: Any) -> str:
    """`chunker_key` memuat versi implementasi, versi skema, hash isi skema, cakupan, dan tokenizer."""
    return make_chunker_key("structure_schema", {
        "version": cfg.get("chunking", {}).get("schema_chunker_version", SCHEMA_CHUNKER_VERSION),
        "schema_version": record["schema_version"], "schema_hash": body_hash(record["body"]),
        "scope_sections": list(cfg["scope_sections"]),
        "tokenizer": tok.info.name, "tokenizer_version": tok.info.version,
    })


def handwritten_address_fn(doc: Any, retrieval_cfg: dict[str, Any] | None = None, amap: Any = None) -> AddressFn:
    """Alamat dari peta alamat tulisan tangan UU PT (satu peta untuk semua chunker)."""
    cfg, scope, prefix, labels = context_for(doc, retrieval_cfg)
    amap = amap or build_address_map(doc.text, doc.sections, prefix, scope, labels)
    default_labels = {"batang_tubuh": "Batang Tubuh", "penjelasan_pasal": "Penjelasan", "penjelasan_umum": "Penjelasan Umum"}

    def fn(start: int, end: int, section: str) -> tuple[str, list[dict[str, str]], list[str]]:
        return amap.address_for_range(start, end, section, prefix, labels.get(section) or default_labels.get(section, section))
    return fn


def _descendants(levels: Sequence[Mapping[str, Any]], order: int) -> set[int]:
    out = {order}
    for lv in sorted(levels, key=lambda x: x["order"]):  # parent_order selalu lebih kecil dari order (validasi skema)
        if lv["parent_order"] in out:
            out.add(lv["order"])
    return out


def _compiled(levels: Sequence[Mapping[str, Any]]) -> dict[int, re.Pattern[str]]:
    out: dict[int, re.Pattern[str]] = {}
    for lv in levels:
        rx, why = compile_marker(lv["marker_pattern"])
        if rx is None:
            raise SchemaChunkerError(f"level {lv['order']} ({lv['name']}): {why}")
        out[lv["order"]] = rx
    return out


def _unit_candidates(body: Mapping[str, Any]) -> list[int]:
    d = body["default_chunk_level"]
    levels = body["levels"]
    if not any(lv["order"] == d for lv in levels):
        raise SchemaChunkerError(f"default_chunk_level {d} is not an existing order")
    return [d] + sorted(lv["order"] for lv in levels if lv["is_chunk_unit"] and lv["order"] != d)


def _first_nonspace(text: str, pos: int, end: int) -> int:
    while pos < end and text[pos].isspace():
        pos += 1
    return pos


def _trim_end(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def chunk_schema(doc: Any, record: Mapping[str, Any], *, address_fn: AddressFn | None = None, amap: Any = None,
                 retrieval_cfg: dict[str, Any] | None = None, tokenizer: Any = None) -> list[Chunk]:
    """Potongan `doc` menurut `record["body"]` (SchemaRecord, DATA-CONTRACTS §6). Hanya section dalam cakupan retrieval."""
    cfg, scope, _prefix, _labels = context_for(doc, retrieval_cfg)
    tok = tokenizer or get_tokenizer()
    body = record["body"]
    levels = body["levels"]
    rx = _compiled(levels)
    cands = _unit_candidates(body)
    key = schema_key(cfg, record, tok)
    addr = address_fn or handwritten_address_fn(doc, cfg, amap)
    text = doc.text
    out: list[Chunk] = []

    def emit(st: int, en: int, name: str, warns: list[str]) -> None:
        a, lv, aw = addr(st, en, name)
        out.append(Chunk(
            chunk_id=make_chunk_id(doc.doc_id, st, en, key), doc_id=doc.doc_id, chunker_key=key, start=st, end=en,
            clean_sha256=doc.clean_sha256, section=name, address=a, address_levels=lv,
            tokens_local=tok.count(text[st:en]), warnings=[*warns, *aw],
        ))

    for sec in sorted((x for x in doc.sections if x["section"] in scope), key=lambda x: (x["start"], x["end"])):
        s, e, name = sec["start"], sec["end"], sec["section"]
        marks = {o: sorted({m.start() for m in r.finditer(text, s, e)}) for o, r in rx.items()}
        unit = next((o for o in cands if marks.get(o)), None)
        if unit is None:
            st = _first_nonspace(text, s, e)
            en = _trim_end(text, st, e)
            if st < en:
                emit(st, en, name, [NO_MARKER_WARNING])
            continue
        own = _descendants(levels, unit)
        stops = sorted({p for o, ps in marks.items() if o not in own for p in ps})
        starts = sorted({_first_nonspace(text, p, e) for p in marks[unit]})
        starts = [p for p in starts if p < e]
        for i, st in enumerate(starts):
            limit = starts[i + 1] if i + 1 < len(starts) else e
            nxt = next((p for p in stops if p > st), None)
            if nxt is not None and nxt < limit:
                limit = nxt
            en = _trim_end(text, st, limit)
            if st < en:
                emit(st, en, name, [])
    return out


# ---------- selisih batas terhadap parser tangan ----------
def _edges(chunks: Sequence[Chunk], section: str) -> set[tuple[str, int]]:
    out: set[tuple[str, int]] = set()
    for c in chunks:
        if c.section == section:
            out.add(("start", c.start))
            out.add(("end", c.end))
    return out


def _example(doc: Any, chunks: Sequence[Chunk], section: str, edge: str, pos: int, width: int = 40) -> dict[str, Any]:
    owner = next((c for c in chunks if c.section == section and (c.start if edge == "start" else c.end) == pos), None)
    snip = doc.text[pos:pos + width] if edge == "start" else doc.text[max(0, pos - width):pos]
    return {"edge": edge, "offset": pos, "address": owner.address if owner else None, "snippet": snip}


def boundary_diff(doc: Any, hand: Sequence[Chunk], schema: Sequence[Chunk], *, sections: Sequence[str] | None = None,
                  n_examples: int = 5) -> dict[str, Any]:
    """Selisih batas potongan `structure_schema` terhadap `structure_handwritten`, per section dan total.

    Batas = awal dan akhir tiap potongan (offset code point teks bersih), dihitung per section pemilik potongan.
    Per section: `same` (batas sama), `hand_only`, `schema_only`, jumlah potongan kedua sisi, dan `examples`
    (n_examples pertama menurut offset untuk hand_only dan schema_only)."""
    names = list(sections) if sections is not None else sorted({c.section for c in hand} | {c.section for c in schema})
    out: dict[str, Any] = {}
    tot = {"same": 0, "hand_only": 0, "schema_only": 0, "n_chunks_hand": 0, "n_chunks_schema": 0}
    for name in names:
        h, s = _edges(hand, name), _edges(schema, name)
        only_h, only_s = sorted(h - s, key=lambda t: (t[1], t[0])), sorted(s - h, key=lambda t: (t[1], t[0]))
        row = {
            "same": len(h & s), "hand_only": len(only_h), "schema_only": len(only_s),
            "n_chunks_hand": sum(1 for c in hand if c.section == name), "n_chunks_schema": sum(1 for c in schema if c.section == name),
            "examples": {
                "hand_only": [_example(doc, hand, name, k, p) for k, p in only_h[:n_examples]],
                "schema_only": [_example(doc, schema, name, k, p) for k, p in only_s[:n_examples]],
            },
        }
        out[name] = row
        for k in tot:
            tot[k] += row[k]
    return {"sections": out, "total": tot, "boundary": "start and end offsets of each chunk, per section"}

