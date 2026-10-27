"""W57: header B untuk keluarga multi-dokumen (akta; H-088 G-6, H-089, H-091). Tanpa jaringan kecuali `run_family`.

Satu `Prepared` per (dokumen, sumber). Proyeksi per akta dan total memakai batas atas dengan faktor ulang G-36
(`ceil(expected * factor_bp / 10000)`) lalu gerbang belanja. Hanya unit yang BELUM tersimpan di store header yang
diproyeksikan dan dipanggil (cache per `chunk_id`, tidak diulang). UU PT tidak lewat modul ini."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from .caller import HeaderRun, load_header, run_headers
from .run import HeaderConfigError, Prepared, prepare, project
from .units import Unit

MAX_ATTEMPTS = 8  # H-081, H-082: sampai 8 upaya total; tetap gagal = gagal jujur, tanpa fallback


def batch_gate_cfg(budget_cfg: Mapping[str, Any] | None) -> dict[str, int]:
    """Baca `[batch_gate]` config/budget (H-092 P10 / G-36): factor_bp, batch_cap_micros, cumulative_cap_micros, cumulative_pct."""
    g = (budget_cfg or {}).get("batch_gate")
    if not isinstance(g, Mapping):
        raise HeaderConfigError("config/budget: [batch_gate] is missing")
    out = {}
    for k in ("factor_bp", "batch_cap_micros", "cumulative_cap_micros", "cumulative_pct"):
        v = g.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise HeaderConfigError(f"config/budget: batch_gate.{k} must be a positive integer")
        out[k] = v
    if out["factor_bp"] < 10000:
        raise HeaderConfigError("config/budget: batch_gate.factor_bp must be >= 10000")
    return out


def upper_bound(expected_micros: int, bp: int) -> int:
    return -(-expected_micros * bp // 10000)


def _stored(headers_dir: Path, p: Prepared, u: Unit) -> bool:
    return all(load_header(headers_dir, p.source, p.prompt, cid) is not None for cid in u.chunk_ids)


@dataclass
class FamilyPlan:
    call: list[Unit] = field(default_factory=list)
    stored: list[Unit] = field(default_factory=list)


def plan_prepared(p: Prepared, headers_dir: Path, limit: int | None = None) -> FamilyPlan:
    plan = FamilyPlan()
    for u in (p.units if limit is None else p.units[:limit]):
        (plan.stored if _stored(headers_dir, p, u) else plan.call).append(u)
    return plan


def project_prepared(p: Prepared, plan: FamilyPlan, tokenizer: Any, header_cfg: dict, model_cfg: dict, bp: int, *,
                     profile: str | None = None, rpm: int | None = None) -> dict[str, Any]:
    """Proyeksi satu (dokumen, sumber) atas unit yang perlu panggilan, plus batas atas G-36 dan statistik unit."""
    stats = {"doc_id": p.doc.doc_id, "source": p.source, "units": len(p.units), "already_stored": len(plan.stored),
             "to_call": len(plan.call), "max_unit_tokens": max((u.tokens for u in p.units), default=0),
             "prefix_tokens": p.prefix.tokens}
    if plan.call:
        proj = project(replace(p, units=list(plan.call)), tokenizer, header_cfg, model_cfg, profile=profile, rpm=rpm)
        exp = proj["cost_usd_micros"]["expected"]
        return {**stats, "projection": proj, "expected": exp, "upper_g36": upper_bound(exp, bp),
                "upper_no_cache": proj["cost_usd_micros"]["upper_no_cache"],
                "calls": proj["calls"], "estimated_seconds": proj["time"]["estimated_seconds"]}
    return {**stats, "projection": None, "expected": 0, "upper_g36": 0, "upper_no_cache": 0, "calls": 0, "estimated_seconds": 0}


def gate(total_upper: int, spent_cumulative: int, budget_cfg: Mapping[str, Any]) -> dict[str, Any]:
    c = batch_gate_cfg(budget_cfg)
    threshold = c["cumulative_cap_micros"] * c["cumulative_pct"] // 100
    reasons = []
    if total_upper > c["batch_cap_micros"]:
        reasons.append(f"upper_bound {total_upper} > batch_cap {c['batch_cap_micros']}")
    if spent_cumulative + total_upper > threshold:
        reasons.append(f"cumulative {spent_cumulative} + upper_bound {total_upper} > {threshold}")
    return {"verdict": "reject" if reasons else "allow", "reasons": reasons, "upper_bound": total_upper,
            "spent_cumulative": spent_cumulative, "single_limit": c["batch_cap_micros"], "cumulative_limit": threshold}


def precheck(res: Mapping[str, Any], *, spent_b: int, spent_total: int, per_role_b_cap: int, total_cap: int) -> str | None:
    """Pemeriksaan sebelum run live: gerbang batch lalu cap config/budget (expected + terpakai). None = lolos."""
    g = res["gate"]
    if g["verdict"] != "allow":
        return "gate_rejected (" + "; ".join(g["reasons"]) + ")"
    exp = res["total"]["expected"]
    if spent_b + exp > per_role_b_cap or spent_total + exp > total_cap:
        return "budget_exceeded (projection over config/budget)"
    return None


def prepare_family(doc_ids: list[str], sources: list[str], *, tokenizer: Any, header_cfg: dict, retrieval_cfg: dict,
                   grid_cfg: dict, schema_record: Any = None, config_dir: Path | None = None,
                   loader: Callable[..., Any] | None = None) -> dict[str, dict[str, Prepared]]:
    """doc_id -> sumber -> Prepared. Dokumen dan prompt dimuat sekali per dokumen / sekali total."""
    out: dict[str, dict[str, Prepared]] = {}
    prompt = None
    for d in doc_ids:
        doc = None
        out[d] = {}
        for s in sources:
            kw: dict[str, Any] = dict(tokenizer=tokenizer, header_cfg=header_cfg, retrieval_cfg=retrieval_cfg,
                                      grid_cfg=grid_cfg, config_dir=config_dir, doc_id=d, prompt=prompt, doc=doc)
            if s == "structure_schema":
                kw["schema_record"] = schema_record
            p = prepare(s, **kw)
            doc, prompt = p.doc, p.prompt
            out[d][s] = p
    return out


def project_family(prepared: dict[str, dict[str, Prepared]], headers_dir: Path, tokenizer: Any, header_cfg: dict,
                   model_cfg: dict, budget_cfg: dict, *, spent: int, profile: str | None = None, rpm: int | None = None,
                   limit: int | None = None) -> dict[str, Any]:
    bp, bp_src = batch_gate_cfg(budget_cfg)["factor_bp"], "config/budget [batch_gate]"
    per_doc: dict[str, Any] = {}
    total = {"expected": 0, "upper_g36": 0, "upper_no_cache": 0, "calls": 0, "estimated_seconds": 0, "to_call": 0}
    for d, srcs in prepared.items():
        rows = {}
        for s, p in srcs.items():
            row = project_prepared(p, plan_prepared(p, headers_dir, limit), tokenizer, header_cfg, model_cfg, bp,
                                   profile=profile, rpm=rpm)
            rows[s] = row
            for k in total:
                total[k] += row[k]
        per_doc[d] = {"sources": rows, "expected": sum(r["expected"] for r in rows.values()),
                      "upper_g36": sum(r["upper_g36"] for r in rows.values()),
                      "gate": gate(sum(r["upper_g36"] for r in rows.values()), spent, budget_cfg)}
    return {"factor_bp": bp, "factor_source": bp_src, "per_doc": per_doc, "total": total,
            "gate": gate(total["upper_g36"], spent, budget_cfg)}


def run_family(client: Any, prepared: dict[str, dict[str, Prepared]], *, tokenizer: Any, headers_dir: Path,
               header_cfg: dict, meta_for: Callable[[Prepared], dict], limit: int | None = None,
               max_attempts: int = MAX_ATTEMPTS, log: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    """Jalankan unit yang belum tersimpan, per (dokumen, sumber), sampai `max_attempts` putaran (H-081). Berhenti seluruhnya
    bila `run_headers` berhenti (budget_exceeded, too_many_errors, warm_failed, cache_ratio_low). Unit yang tetap gagal
    setelah semua upaya dilaporkan di `failed` (gagal jujur)."""
    summary: dict[str, Any] = {"stopped": None, "failed": {}, "attempts": {}, "stored": 0}
    for d, srcs in prepared.items():
        for s, p in srcs.items():
            key = f"{d}/{s}"
            for attempt in range(1, max_attempts + 1):
                plan = plan_prepared(p, headers_dir, limit)
                if not plan.call:
                    break
                summary["attempts"][key] = attempt
                res: HeaderRun = run_headers(
                    client, p.prompt, p.prefix, plan.call, granularity=s, tokenizer=tokenizer, headers_dir=headers_dir,
                    max_header_tokens=header_cfg["max_header_tokens"], max_output_tokens=header_cfg["max_output_tokens"],
                    max_consecutive_errors=header_cfg["max_consecutive_errors"],
                    warm_max_output_tokens=header_cfg["warm_max_output_tokens"],
                    cache_guard_calls=header_cfg["cache_guard_calls"], cache_guard_min_ratio=header_cfg["cache_guard_min_ratio"],
                    meta=meta_for(p), max_length_chars=header_cfg.get("schema_max_length_chars"))
                ok = sum(1 for o in res.outcomes if o.headers)
                summary["stored"] += ok
                log(f"{key} attempt {attempt}: called={len(res.outcomes)} ok={ok} stopped={res.stopped_reason}")
                if res.stopped_reason:
                    summary["stopped"] = f"{key}: {res.stopped_reason}"
                    return summary
            left = plan_prepared(p, headers_dir, limit).call
            if left:
                summary["failed"][key] = [u.key for u in left]
    return summary
