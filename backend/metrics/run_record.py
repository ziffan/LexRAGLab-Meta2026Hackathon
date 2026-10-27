"""Bagian `RunRecord` untuk tokenizer dan packing (DATA-CONTRACTS §12; M1.2 S16). Tidak menulis berkas."""

from __future__ import annotations

from typing import Any, Iterable

from backend.metrics.types import PACKING_RULES


def run_record_parts(tokenizer_info: Any, packing: str | None = None) -> dict[str, Any]:
    """`tokenizer_info` punya `.name` dan `.version`. Tanpa packing -> "stop" (A11)."""
    rule = "stop" if packing is None else packing
    if rule not in PACKING_RULES:
        raise ValueError(f"unknown packing rule: {rule!r}")
    return {"tokenizer": {"name": tokenizer_info.name, "version": tokenizer_info.version}, "packing": rule}


def ensure_single_tokenizer(infos: Iterable[Any]) -> None:
    """Semua setting dalam satu perbandingan harus memakai tokenizer (nama + versi) yang sama."""
    seen = {(i.name, i.version) for i in infos}
    if len(seen) > 1:
        raise ValueError(f"settings use different tokenizers: {sorted(seen)}")
