"""Filter butir per asal/mode/split, `items_summary`, dan laporan per asal (scenarios/M2.1 S19-S22, A18, A29).

Fungsi murni. Butir = dict `Item` (DATA-CONTRACTS 4) ditambah kunci `split` ("tune" / "held_out" / None); metrik = `ItemMetrics`
(objek atau dict) dengan bilangan bulat mentah. Rata-rata per butir (bukan gabungan karakter); butir tanpa gold dan butir
tanpa baris metrik dikeluarkan dari rata-rata."""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from typing import Any, Iterable, Mapping

from backend.api.errors import ApiError

ORIGINS = ("operator", "spark_disetujui")
MODES = ("literal", "parafrase")
SPLITS = ("tune", "held_out")


class ReportError(ValueError):
    """Masukan laporan tidak konsisten (galat keras, A18)."""


def filter_items(items: Iterable[Mapping[str, Any]], *, origin: str | None = None, mode: str | None = None,
                 split: str | None = None) -> list[Mapping[str, Any]]:
    """Irisan (AND) semua filter yang diberikan, urutan masukan dipertahankan. Nilai di luar enum -> 400 invalid_request."""
    for name, val, allowed in (("origin", origin, ORIGINS), ("mode", mode, MODES), ("split", split, SPLITS)):
        if val is not None and val not in allowed:
            raise ApiError(400, "invalid_request", f"{name} must be one of {list(allowed)}.")
    return [i for i in items if (origin is None or i.get("origin") == origin) and (mode is None or i.get("mode") == mode)
            and (split is None or i.get("split") == split)]


def items_summary(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """`items_summary` API 4: lima kunci. Hanya `Item` (bukan usulan) yang dihitung."""
    rows = list(items)
    return {"n_items": len(rows), "by_origin": dict(Counter(i.get("origin") for i in rows)),
            "by_mode": dict(Counter(i.get("mode") for i in rows)),
            "by_split": dict(Counter(i["split"] for i in rows if i.get("split") is not None)),
            "control_in_held_out": sum(1 for i in rows if i.get("origin") == "operator" and i.get("split") == "held_out")}


def pending_count(proposals: Iterable[Mapping[str, Any]]) -> int:
    return sum(1 for p in proposals if p.get("review_status") == "usulan")


def _get(m: Any, name: str) -> int:
    v = m.get(name) if isinstance(m, Mapping) else getattr(m, name)
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise ReportError(f"metric field {name} must be a non-negative integer")
    return v


def _mean(xs: list[Fraction]) -> float | None:
    return float(sum(xs) / len(xs)) if xs else None


def origin_report(items: Iterable[Mapping[str, Any]], metrics: Iterable[Any], *, split: str = "held_out") -> dict[str, dict[str, Any]]:
    """Laporan per asal untuk satu split. Kedua asal selalu ada (baris kosong tetap muncul)."""
    if split not in SPLITS:
        raise ApiError(400, "invalid_request", f"split must be one of {list(SPLITS)}.")
    all_items = list(items)
    by_id = {i["id"]: i for i in all_items}
    rows: dict[str, Any] = {}
    for m in metrics:
        iid = m.get("item_id") if isinstance(m, Mapping) else getattr(m, "item_id")
        if iid not in by_id:
            raise ReportError(f"metrics row refers to unknown item_id {str(iid)[:40]!r}")
        if iid in rows:
            raise ReportError(f"duplicate metrics row for item_id {str(iid)[:40]!r}")
        rows[iid] = m
    out: dict[str, dict[str, Any]] = {}
    for origin in ORIGINS:
        sel = [i for i in all_items if i.get("origin") == origin and i.get("split") == split]
        recalls: list[Fraction] = []
        precisions: list[Fraction] = []
        n_gold = n_no_gold = n_missing = covered = total = 0
        for it in sel:
            m = rows.get(it["id"])
            if m is None:
                n_missing += 1
                continue
            gold = _get(m, "gold_chars")
            if gold == 0:
                n_no_gold += 1
                continue
            n_gold += 1
            cov = _get(m, "covered_gold_chars")
            recalls.append(Fraction(cov, gold))
            ret = _get(m, "retrieved_tokens")
            if ret > 0:
                precisions.append(Fraction(_get(m, "gold_tokens_retrieved"), ret))
            total += 1
            covered += 1 if cov == gold else 0
        out[origin] = {"n_items": len(sel), "n_with_gold": n_gold, "n_no_gold": n_no_gold, "n_missing_metrics": n_missing,
                       "mean_span_recall": _mean(recalls), "mean_token_precision": _mean(precisions),
                       "fully_covered": {"covered": covered, "total": total}}
    return out
