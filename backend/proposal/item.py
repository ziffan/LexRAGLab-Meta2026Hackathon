"""Enum `Item.mode` dan invarian butir wajib tolak (H-092 P4 (c); docs/DATA-CONTRACTS.md §4). Tanpa impor: dipakai
layanan usulan, laporan, dan pemuat butir."""

from __future__ import annotations

from typing import Any, Mapping

MODE_TOLAK = "tolak"  # butir wajib tolak (akta, uupt; H-092, H-099 V4): gold_spans = []
ITEM_MODES = ("literal", "parafrase", MODE_TOLAK)


def item_mode_problem(item: Mapping[str, Any]) -> str | None:
    """Alasan satu baris bila `mode` di luar enum atau `mode = tolak` tetapi `gold_spans` tidak kosong; selain itu None.
    Arah sebaliknya (gold kosong tetapi mode lain) tidak dipaksa: `kontrol-K-08` lama tetap sah."""
    mode = item.get("mode")
    if mode not in ITEM_MODES:
        return f"mode must be one of {list(ITEM_MODES)}"
    if mode == MODE_TOLAK and item.get("gold_spans") != []:
        return "mode 'tolak' requires gold_spans = []"
    return None
