"""Agregasi held-out (EVAL-SPEC 9, H-015, H-054, M4.3 A9/A10) dan laporan per butir (A15, A16, A18, A19).

Fungsi murni: masukan butir (`id`, `origin`, `mode`) dan `ItemMetrics` (backend/metrics/types.py) satu setting; angka
dihitung eksak (Fraction) dan baru dikonversi ke float di batas keluaran. Rata-rata per butir, bukan rasio gabungan.
Penyebut nol -> None (dua kondisi null terpisah: recall dan precision, A10, H-061).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Iterable, Mapping, Sequence

from backend.metrics.types import ItemMetrics

ORIGINS = ("operator", "spark_disetujui")
NO_GOLD_NOTE = "no gold (must abstain)"
TITLE_UUPT = "Held-out results"
TITLE_AKTA = "Transfer results"  # A19; label laporan, bukan nilai data (H-054, H-059)
SPLIT_LABEL_AKTA = "Transfer"


def _f(x: Fraction | None) -> float | None:
    return None if x is None else float(x)


def _mean(values: Sequence[Fraction]) -> Fraction | None:
    return sum(values, Fraction(0)) / len(values) if values else None


def _origin_of(items_by_id: Mapping[str, Mapping[str, Any]], m: ItemMetrics) -> Mapping[str, Any]:
    it = items_by_id.get(m.item_id)
    if it is None:
        raise KeyError(m.item_id)
    return it


def summarize(rows: Sequence[ItemMetrics]) -> dict[str, Any]:
    """Rata-rata per butir bergold. recall: atas butir bergold; precision: atas nilai non-null; `fully_covered`
    `{covered, total}` atas butir bergold. Kelompok tanpa nilai untuk suatu metrik -> None untuk metrik itu saja."""
    gold = [m for m in rows if m.has_gold]
    rec = _mean([m.span_recall for m in gold if m.span_recall is not None])
    prec = _mean([m.token_precision for m in gold if m.token_precision is not None])
    return {"n_items": len(rows), "n_gold": len(gold), "mean_span_recall": _f(rec), "mean_token_precision": _f(prec),
            "fully_covered": {"covered": sum(1 for m in gold if m.fully_covered), "total": len(gold)}}


def held_out_block(items: Iterable[Mapping[str, Any]], metrics: Iterable[ItemMetrics]) -> dict[str, Any]:
    """`Profile.held_out` (DATA-CONTRACTS 11): hanya butir `split == "held_out"` pada setting itu. `n_items` = semua butir
    held-out (termasuk tanpa gold); `by_origin` kedua kunci selalu ada."""
    by_id = {i["id"]: i for i in items}
    held = [m for m in metrics if m.split == "held_out"]
    by_origin: dict[str, int] = {o: 0 for o in ORIGINS}
    for m in held:
        o = _origin_of(by_id, m)["origin"]
        by_origin[o] = by_origin.get(o, 0) + 1
    s = summarize(held)
    return {"n_items": s["n_items"], "by_origin": by_origin, "mean_span_recall": s["mean_span_recall"],
            "mean_token_precision": s["mean_token_precision"], "fully_covered": s["fully_covered"]}


# ---------- laporan ----------
def _count(num: int, den: int) -> dict[str, Any]:
    """Hitungan mentah `x of y` tanpa persen (A16)."""
    return {"numerator": num, "denominator": den, "text": f"{num} of {den}"}


def _row(it: Mapping[str, Any], m: ItemMetrics, split_label: str) -> dict[str, Any]:
    gold = m.has_gold
    prec_ok = gold and m.token_precision is not None
    return {
        "item_id": m.item_id, "split": split_label, "origin": it["origin"], "mode": it["mode"],
        "span_recall": _count(m.covered_gold_chars, m.gold_chars) if gold else None,
        "token_precision": _count(m.gold_tokens_retrieved, m.retrieved_tokens) if prec_ok else None,
        "reciprocal_rank": _f(m.reciprocal_rank), "recall_at_k": _f(m.recall_at_k),
        "fully_covered": m.fully_covered, "note": None if gold else NO_GOLD_NOTE,
    }


def _groups(by_id: Mapping[str, Mapping[str, Any]], rows: Sequence[ItemMetrics], key: str) -> dict[str, dict[str, Any]]:
    keys = sorted({_origin_of(by_id, m)[key] for m in rows})
    out: dict[str, dict[str, Any]] = {}
    for k in keys:
        s = summarize([m for m in rows if by_id[m.item_id][key] == k])
        out[k] = {"n_items": s["n_items"], "n_gold": s["n_gold"], "mean_span_recall": s["mean_span_recall"],
                  "mean_token_precision": s["mean_token_precision"]}
    return out


def build_report(family: str, items: Iterable[Mapping[str, Any]], metrics: Iterable[ItemMetrics]) -> dict[str, Any]:
    """Laporan per butir. UU PT: hanya butir held-out, judul `Held-out results`. Akta: semua butir (tanpa split),
    judul `Transfer results`, kolom split `Transfer`, tanpa kata held-out dan tanpa penanda profil terpilih (A15, H-054)."""
    by_id = {i["id"]: i for i in items}
    ms = list(metrics)
    if family == "uupt":
        used, title, label = [m for m in ms if m.split == "held_out"], TITLE_UUPT, "held_out"
    elif family == "akta":
        used, title, label = ms, TITLE_AKTA, SPLIT_LABEL_AKTA
    else:
        raise ValueError(f"unknown family {family!r}")
    used.sort(key=lambda m: m.item_id)
    s = summarize(used)
    return {
        "family": family, "title": title,
        "rows": [_row(_origin_of(by_id, m), m, label) for m in used],
        "summary": {"n_items": s["n_items"], "mean_span_recall": s["mean_span_recall"],
                    "mean_token_precision": s["mean_token_precision"],
                    "fully_covered": _count(s["fully_covered"]["covered"], s["fully_covered"]["total"])},
        "by_origin": _groups(by_id, used, "origin"), "by_mode": _groups(by_id, used, "mode"),
    }
