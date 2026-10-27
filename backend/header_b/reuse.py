"""H-080: header B untuk potongan `structure_schema`. Header Pasal (prompt yang sama) dipakai ulang tanpa panggilan HANYA bila
rentang `[start,end)` dan teks potongan identik byte per byte (UTF-8) dengan unit Pasal sumbernya (teks input B identik;
`chunk_id` dan label ALAMAT memang berbeda dan bukan syarat; selisih alamat dihitung di `address_differs`). Selainnya potongan masuk daftar panggilan B (prompt aktif). Tanpa jaringan.

Reuse hanya membaca store `pasal/<prompt_hash[:12]>` milik prompt yang sedang dipakai; header prompt lain (mis. v1) tidak
pernah disalin. Hasil ditulis ke store `structure_schema/<prompt_hash[:12]>` dengan `reused_from` = `chunk_id` unit Pasal sumber
(field itu masuk hash isi store, `grid/headers.py`)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .caller import _save, load_header, store_dir
from .prompt import PromptB
from .run import Prepared, project
from .units import Unit, build_units

PASAL = "pasal"
SCHEMA = "structure_schema"


@dataclass(frozen=True)
class Reuse:
    unit: Unit  # potongan skema
    source: Unit  # unit Pasal sumber
    record: dict[str, Any]  # record header Pasal sumber


@dataclass
class SchemaPlan:
    reuse: list[Reuse] = field(default_factory=list)
    call: list[Unit] = field(default_factory=list)  # perlu panggilan B
    stored: list[Unit] = field(default_factory=list)  # sudah ada di store structure_schema (tidak diulang)
    near_miss: list[dict[str, str]] = field(default_factory=list)  # rentang+teks sama tetapi header sumber tak ada/tak sah
    address_differs: int = 0  # info: potongan reuse yang label ALAMAT-nya beda dari unit Pasal sumber

    @property
    def total(self) -> int:
        return len(self.reuse) + len(self.call) + len(self.stored)


def _same_text(a: str, b: str) -> bool:
    return a.encode("utf-8") == b.encode("utf-8")


def _usable(rec: Any, src: Unit, prompt: PromptB) -> bool:
    return (isinstance(rec, dict) and isinstance(rec.get("header"), str) and bool(rec["header"].strip())
            and rec.get("chunk_id") == src.key and isinstance(rec.get("run_id"), str)
            and rec.get("prompt_version") == prompt.version)


def plan_schema(p: Prepared, *, headers_dir: Path, tokenizer: Any, retrieval_cfg: dict[str, Any], grid_cfg: dict[str, Any],
                limit: int | None = None) -> SchemaPlan:
    """Pisahkan potongan skema (`p.units`, atau `limit` pertama) menjadi: dipakai ulang, perlu panggilan, sudah tersimpan."""
    pasal = build_units(p.doc, PASAL, tokenizer=tokenizer, retrieval_cfg=retrieval_cfg, grid_cfg=grid_cfg)
    by_span = {(u.start, u.end): u for u in pasal}
    plan = SchemaPlan()
    for u in (p.units if limit is None else p.units[:limit]):
        if load_header(headers_dir, SCHEMA, p.prompt, u.key) is not None:
            plan.stored.append(u)
            continue
        src = by_span.get((u.start, u.end))
        if src is None or not _same_text(src.text, u.text):
            plan.call.append(u)
            continue
        if src.address != u.address:  # hanya info: H-080 mensyaratkan rentang+teks, bukan label ALAMAT (alamat ayat vs Pasal)
            plan.address_differs += 1
        rec = load_header(headers_dir, PASAL, p.prompt, src.key)
        if not _usable(rec, src, p.prompt):
            plan.near_miss.append({"chunk_id": u.key, "reason": "source_header_missing", "source": src.key})
            plan.call.append(u)
            continue
        plan.reuse.append(Reuse(u, src, rec))
    return plan


def write_reuse(plan: SchemaPlan, *, headers_dir: Path, prompt: PromptB) -> int:
    """Tulis record reuse ke store `structure_schema`; tidak menimpa. `run_id` dan `tokens_local` dari sumber (validitas A5 dan
    akuntansi token M3.2 berjalan seperti header lain). Mengembalikan jumlah record."""
    d = store_dir(headers_dir, SCHEMA, prompt)
    for r in plan.reuse:
        rec = {"chunk_id": r.unit.key, "header": r.record["header"], "granularity": SCHEMA, "prompt_version": prompt.version,
               "tokens_local": r.record.get("tokens_local"), "run_id": r.record["run_id"], "reused_from": r.source.key}
        _save(d / f"{r.unit.key}.json", rec)
    return len(plan.reuse)


def project_schema(p: Prepared, plan: SchemaPlan, tokenizer: Any, header_cfg: dict[str, Any], model_cfg: dict[str, Any], *,
                   profile: str | None = None, rpm: int | None = None) -> dict[str, Any]:
    """Jumlah potongan/reuse/panggilan; proyeksi biaya HANYA untuk potongan yang perlu panggilan (nol bila tak ada)."""
    out: dict[str, Any] = {"chunks": plan.total, "reused": len(plan.reuse), "already_stored": len(plan.stored),
                           "to_call": len(plan.call), "near_miss": list(plan.near_miss),
                           "address_differs": plan.address_differs}
    if plan.call:
        out["projection"] = project(replace(p, units=list(plan.call)), tokenizer, header_cfg, model_cfg, profile=profile, rpm=rpm)
    else:
        out["projection"] = {"units": 0, "calls": 0, "cost_usd_micros": {"expected": 0, "upper_cached": 0, "upper_no_cache": 0},
                             "source": SCHEMA, "prompt_version": p.prompt.version, "prompt_hash": p.prompt.prompt_hash}
    return out
