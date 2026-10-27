"""Unit permintaan B: satu panggilan Spark per unit. Sumber potongan:
- `ayat`: satu unit per potongan `structure_handwritten` (header per `chunk_id`).
- `pasal`: satu unit per Pasal (per section); header dibagi ke semua potongan Pasal itu.
- `fixed_size`: satu unit per potongan `fixed_size` (H-069), header per `chunk_id`.
`HeaderB.granularity` memakai nama sumber (`fixed_size` memperluas enum DATA-CONTRACTS 7; temuan spec)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.chunking import chunk_document

SEP = " › "
SOURCES = ("pasal", "ayat", "fixed_size")
SCHEMA_SOURCE = "structure_schema"  # H-080: potongan skema A aktif; butuh `schema_record`
ALL_SOURCES = (*SOURCES, SCHEMA_SOURCE)


@dataclass(frozen=True)
class Unit:
    key: str  # chunk_id yang diminta ke B
    address: str
    text: str
    tokens: int  # token teks sumber (tokenizer lokal)
    chunk_ids: tuple[str, ...]  # chunk penerima header (ayat/fixed: key saja; pasal: semua potongan Pasal)
    start: int | None = None  # rentang [start,end) di doc.text; dipakai pencocokan reuse H-080
    end: int | None = None


def chunker_setting(source: str, fixed: dict[str, Any] | None = None) -> dict[str, Any]:
    if source == "fixed_size":
        f = fixed or {}
        return {"chunker": "fixed_size", "chunk_size_tokens": f["chunk_size_tokens"], "overlap_tokens": f["overlap_tokens"]}
    return {"chunker": "structure_handwritten"}


def _pasal_label(c: Any) -> str | None:
    for lv in c.address_levels:
        if lv["level"] == "pasal":
            return lv["label"]
    return None


def _pasal_address(c: Any, label: str | None) -> str:
    if label is None:
        return c.address
    parts = c.address.split(SEP)
    return SEP.join(parts[: parts.index(label) + 1]) if label in parts else c.address


def build_units(doc: Any, source: str, *, tokenizer: Any, retrieval_cfg: dict[str, Any], grid_cfg: dict[str, Any],
                schema_record: Any = None) -> list[Unit]:
    if source not in ALL_SOURCES:
        raise ValueError(f"unknown source {source!r}")
    if source == SCHEMA_SOURCE:
        if schema_record is None:
            raise ValueError("source structure_schema needs a schema_record (active SchemaRecord of schema A)")
        setting = {"chunker": "structure_schema"}
    else:
        setting = chunker_setting(source, grid_cfg.get("fixed_size"))
    chunks = sorted(chunk_document(doc, setting, tokenizer=tokenizer, retrieval_cfg=retrieval_cfg, grid_cfg=grid_cfg,
                                   schema_record=schema_record), key=lambda c: (c.start, c.end))
    if source in ("ayat", "fixed_size", SCHEMA_SOURCE):
        return [Unit(c.chunk_id, c.address, doc.text[c.start:c.end], c.tokens_local, (c.chunk_id,), c.start, c.end)
                for c in chunks]
    groups: dict[tuple[str, str], list[Any]] = {}
    for c in chunks:
        lab = _pasal_label(c)
        groups.setdefault((c.section, lab if lab is not None else c.chunk_id), []).append(c)
    out: list[Unit] = []
    for members in groups.values():
        first = members[0]
        s, e = min(m.start for m in members), max(m.end for m in members)
        text = doc.text[s:e]
        out.append(Unit(first.chunk_id, _pasal_address(first, _pasal_label(first)), text,
                        tokenizer.count(text), tuple(m.chunk_id for m in members), s, e))
    return out
