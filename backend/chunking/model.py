"""Bentuk `Chunk` (DATA-CONTRACTS §3), `Setting` (§10), dan hash kanonik (§1)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

SEP = " › "  # U+203A, pemisah alamat kanonik (docs/CONVENTIONS.md)
NO_MARKER_WARNING = "no structural marker, fallback per section"


class ChunkOffsetError(Exception):
    """Offset potongan tidak cocok dengan teks sumber. Galat, bukan peringatan (UI-SPEC U1)."""


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def make_chunker_key(chunker: str, params: dict[str, Any]) -> str:
    """Hash chunker + parameter + versi (§3). `params` memuat versi implementasi."""
    return sha256_hex({"chunker": chunker, "params": params})


def make_chunk_id(doc_id: str, start: int, end: int, chunker_key: str) -> str:
    return sha256_hex([doc_id, start, end, chunker_key])


@dataclass(frozen=True)
class Chunk:
    """Field persis DATA-CONTRACTS §3. Teks tidak disimpan; ia `doc.text[start:end]`."""

    chunk_id: str
    doc_id: str
    chunker_key: str
    start: int
    end: int
    clean_sha256: str
    section: str
    address: str
    address_levels: list[dict[str, str]]
    tokens_local: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_setting_id(setting: dict[str, Any]) -> str:
    """`setting_id` = hash isi kanonik field Setting (§10), tanpa `setting_id` itu sendiri."""
    body = {k: v for k, v in setting.items() if k != "setting_id"}
    return sha256_hex(body)
