"""Filter butir per asal/mode/split, `items_summary`, dan laporan per asal (scenarios/M2.1 S19-S22, A18, A29).

Fungsi murni. Butir = dict `Item` (DATA-CONTRACTS 4) ditambah kunci `split` ("tune" / "held_out" / None); metrik = `ItemMetrics`
(objek atau dict) dengan bilangan bulat mentah. Rata-rata per butir (bukan gabungan karakter); butir tanpa gold dan butir
tanpa baris metrik dikeluarkan dari rata-rata."""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from typing import Any, Iterable, Mapping

from backend.api.errors import ApiError

from .item import ITEM_MODES, MODE_TOLAK

ORIGINS = ("operator", "spark_disetujui")
MODES = ITEM_MODES  # H-092: literal, parafrase, tolak (enum Item.mode)
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
            "by_mode": {**dict.fromkeys(ITEM_MODES, 0), **Counter(i.get("mode") for i in rows)},  # tiga kunci selalu ada (H-092)
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


def origin_report(items: Iterable[Mapping[str, Any]], metrics: Iterable[Any], *, split: str | None = "held_out") -> dict[str, dict[str, Any]]:
    """Laporan per asal untuk satu split. Kedua asal selalu ada (baris kosong tetap muncul). `split=None` = keluarga tanpa split
    (akta, H-054): semua butir, tanpa filter split."""
    return _group_report(items, metrics, split, "origin", ORIGINS)


def mode_report(items: Iterable[Mapping[str, Any]], metrics: Iterable[Any], *, split: str | None = "held_out") -> dict[str, dict[str, Any]]:
    """Laporan per mode `Item` (bentuk baris sama dengan `origin_report`); `literal`, `parafrase`, `tolak` selalu ada.
    Butir wajib tolak (`tolak`) tidak bergold: `n_with_gold = 0`, rata-rata `null` (P7)."""
    return _group_report(items, metrics, split, "mode", ITEM_MODES)


def _group_report(items: Iterable[Mapping[str, Any]], metrics: Iterable[Any], split: str | None, key: str,
                  groups: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    if split is not None and split not in SPLITS:
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
    for origin in groups:
        sel = [i for i in all_items if i.get(key) == origin and (split is None or i.get("split") == split)]
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


def must_abstain_summary(items: Iterable[Mapping[str, Any]], answers: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Baris laporan "no gold (must abstain)" (P8, EVAL-SPEC §10): atas `AnswerRecord` satu kombinasi (setting, slot, profil),
    hanya jawaban untuk butir `tolak`. `abstained_correct` = C berstatus `tolak`/`bukti_tidak_cukup`; `n` = jumlah jawaban butir
    wajib tolak. Bukan jumlah sel "Abstained, correctly" (yang bisa memuat butir bergold yang golnya tak ada di konteks)."""
    must = {i["id"] for i in items if i.get("mode") == MODE_TOLAK}
    n = ok = 0
    for a in answers:
        if a.get("item_id") not in must:
            continue
        n += 1
        ok += 1 if (a.get("output") or {}).get("status") in ("tolak", "bukti_tidak_cukup") else 0
    return {"n": n, "abstained_correct": ok}
