"""H-082: rencana header B untuk potongan `structure_schema`. Semua potongan dipanggil B sendiri (prompt aktif); tidak ada
reuse header Pasal. Potongan yang sudah tersimpan di `structure_schema/<prompt_hash[:12]>` dilewati (tidak diulang, tidak
ditimpa). Tanpa jaringan."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .caller import load_header
from .run import Prepared, project
from .units import Unit

SCHEMA = "structure_schema"


@dataclass
class SchemaPlan:
    call: list[Unit] = field(default_factory=list)  # perlu panggilan B
    stored: list[Unit] = field(default_factory=list)  # sudah ada di store structure_schema

    @property
    def total(self) -> int:
        return len(self.call) + len(self.stored)


def plan_schema(p: Prepared, *, headers_dir: Path, limit: int | None = None) -> SchemaPlan:
    """Pisahkan potongan skema (`p.units`, atau `limit` pertama) menjadi: sudah tersimpan vs perlu panggilan."""
    plan = SchemaPlan()
    for u in (p.units if limit is None else p.units[:limit]):
        (plan.stored if load_header(headers_dir, SCHEMA, p.prompt, u.key) is not None else plan.call).append(u)
    return plan


def project_schema(p: Prepared, plan: SchemaPlan, tokenizer: Any, header_cfg: dict[str, Any], model_cfg: dict[str, Any], *,
                   profile: str | None = None, rpm: int | None = None) -> dict[str, Any]:
    """Jumlah potongan/tersimpan/panggilan; proyeksi biaya HANYA untuk potongan yang perlu panggilan (nol bila tak ada)."""
    out: dict[str, Any] = {"chunks": plan.total, "already_stored": len(plan.stored), "to_call": len(plan.call)}
    if plan.call:
        out["projection"] = project(replace(p, units=list(plan.call)), tokenizer, header_cfg, model_cfg, profile=profile, rpm=rpm)
    else:
        out["projection"] = {"units": 0, "calls": 0, "cost_usd_micros": {"expected": 0, "upper_cached": 0, "upper_no_cache": 0},
                             "source": SCHEMA, "prompt_version": p.prompt.version, "prompt_hash": p.prompt.prompt_hash}
    return out
