"""R3 `GET /api/families/{family}/snapshot` (docs/API.md §2, §4): bagian M1.

Dibangun dari berkas dan cache; tidak pernah menjalankan grid, chunker, atau Spark (API.md §5). Hasil grid dibaca dari
`runs/grid/<kunci>.json` untuk kunci yang dihitung dari masukan saat ini; bila belum ada, `grid` bernilai null.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from backend import config
from backend.api.errors import ApiError
from backend.api.routers.corpus import check_family
from backend.api.routers.proposals import get_proposals
from backend.proposal.report import items_summary, origin_report
from backend.grid.types import metrics_from_cache
from backend.schema_a import SchemaStore, SchemaStoreError, snapshot_view

router = APIRouter()

CORPUS_FIELDS = ("doc_id", "family", "title", "path", "sha256", "clean_sha256", "loader_rules_version", "char_count",
                 "tokens_local", "tokens_endpoint", "calibration_ratio", "sections", "annotations")


def grid_view(env: dict[str, Any], budget: int, settings: list[dict[str, Any]] | None = None, header_scope: str | None = None
              ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """(grid, metrics, quality) untuk satu anggaran; grid None bila anggaran itu tidak ada di run tersimpan.

    U2 dua deret (M3.2): tiap titik membawa `header_b` (dari envelope; titik lama tanpa label dilengkapi dari `settings_run`).
    `failed_settings` = setting header-on yang gagal pada run tersimpan (`record.failed_settings`: setting_id, reason, chunk_id),
    disaring ke anggaran ini lewat `settings` bila diberikan. `header_scope` = scope header B bila run memuat titik header-on."""
    ids = {s["setting_id"] for s in env["settings_run"] if s["budget_tokens"] == budget}
    if not ids:
        return None, [], []
    hdr = {s["setting_id"]: bool(s.get("header_b")) for s in env["settings_run"]}
    budget_of = {s["setting_id"]: s["budget_tokens"] for s in (settings or [])}
    grid: dict[str, Any] = {}
    for split in ("tune", "held_out"):
        grid[split] = {
            "points": [{**p, "header_b": bool(p["header_b"]) if "header_b" in p else hdr.get(p["setting_id"], False)}
                       for p in env["points"] if p["split"] == split and p["budget_tokens"] == budget],
            "frontier": next((f for f in env["frontiers"] if f["split"] == split and f["budget_tokens"] == budget), None),
        }
    grid["selected"] = env["selections"].get(str(budget))
    grid["quality_comparison"] = next((c for c in env["quality_comparison"] if c["budget_tokens"] == budget), None)
    grid["skipped"] = [s for s in env["skipped"] if s["budget_tokens"] == budget]
    grid["grid_run_id"] = env["key"]
    failed = [f for f in (env.get("record") or {}).get("failed_settings") or []
              if isinstance(f, dict) and (not budget_of or budget_of.get(f.get("setting_id")) == budget)]
    grid["failed_settings"] = [{"setting_id": f.get("setting_id"), "reason": f.get("reason"), "chunk_id": f.get("chunk_id")} for f in failed]
    grid["header_scope"] = header_scope if any(hdr.values()) or failed else None
    metrics = [metrics_from_cache(m).to_dict() for m in env["metrics"] if m["setting_id"] in ids]
    quality = [q for q in env["quality"] if q["setting_id"] in ids]
    return grid, metrics, quality


HEADER_SAMPLE_PER_GRANULARITY = 10
HEADER_GRANULARITIES = ("pasal", "ayat", "fixed_size")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def header_b_view(runs_dir: Path) -> dict[str, Any]:
    """Kunci baca-saja `header_b` (U8, M3.1): proyeksi biaya terbaru dari `runs/headers/projection/` dan sampel header
    tersimpan per granularitas (`runs/headers/<granularitas>/<prompt_hash12>/<chunk_id>.json`). Hanya membaca berkas;
    berkas rusak dilewati. Alamat tidak disertakan (butuh chunker); frontend mencocokkan `chunk_id` dengan R4."""
    root = Path(runs_dir) / "headers"
    projection = None
    best = ""
    for p in sorted((root / "projection").glob("*.json")) if (root / "projection").is_dir() else []:
        d = _read_json(p)
        if isinstance(d, dict) and isinstance(d.get("projections"), dict) and str(d.get("created_at", "")) >= best:
            best, projection = str(d.get("created_at", "")), d
    if projection is not None:
        keep = ("source", "units", "calls", "cost_usd_micros", "time", "prompt_hash")
        projection = {"created_at": projection.get("created_at"),
                      "projections": {k: {f: v[f] for f in keep if f in v} for k, v in projection["projections"].items() if isinstance(v, dict)}}
    prompt12 = None
    if projection is not None:
        for v in projection["projections"].values():
            if isinstance(v, dict) and isinstance(v.get("prompt_hash"), str):
                prompt12 = v["prompt_hash"][:12]
                break
    samples: list[dict[str, Any]] = []
    stored: dict[str, int] = {}
    for g in HEADER_GRANULARITIES:
        gdir = root / g
        dirs = [gdir / prompt12] if prompt12 else (sorted(x for x in gdir.iterdir() if x.is_dir()) if gdir.is_dir() else [])
        files = sorted(f for d in dirs if d.is_dir() for f in d.glob("*.json"))
        stored[g] = len(files)
        for f in files[:HEADER_SAMPLE_PER_GRANULARITY]:
            d = _read_json(f)
            if isinstance(d, dict) and isinstance(d.get("chunk_id"), str):
                samples.append({k: d.get(k) for k in ("chunk_id", "granularity", "header", "tokens_local", "prompt_version", "run_id")})
    return {"projection": projection, "samples": samples, "stored_counts": stored}


@router.get("/api/families/{family}/snapshot")
def get_snapshot(request: Request, family: str, budget_tokens: int | None = None) -> dict[str, Any]:
    svc = request.app.state.service
    check_family(family)
    grid_cfg = svc.cfg("grid")
    budget = budget_tokens if budget_tokens is not None else grid_cfg["budget"]["default_tokens"]
    corpus = [{k: getattr(d, k) for k in CORPUS_FIELDS} for d in svc.family_docs(family)]
    items = svc.items(family)
    clean = {c["doc_id"]: c["clean_sha256"] for c in corpus}
    for it in items:
        if clean.get(it.get("doc_id")) != it.get("clean_sha256"):
            raise ApiError(409, "hash_mismatch", f"Item {it.get('id')!r} was written against a different clean text than the loaded corpus.")
    cfgs = {n: svc.cfg(n) for n in ("grid", "retrieval", "corpus", "tokenizer")}

    plan, env = svc.stored_grid(family) if items else (None, None)
    split = plan.split if plan is not None else None
    split_of = split.split_of() if split is not None else {}
    if split is not None:
        items = [{**i, "split": split_of.get(i["id"])} for i in items]
    hb = svc.header_binding() if env is not None else None
    grid, metrics, quality = (grid_view(env, budget, svc.settings(family), hb.scope if hb is not None else None)
                              if env is not None else (None, [], []))
    by_split = dict(Counter(split_of.values())) if split is not None else None
    try:
        _ss = SchemaStore(svc.runs_dir)
        schemas, schema_diff = snapshot_view(_ss.list(family))
        schemas_rejected = _ss.list_rejected(family)
    except SchemaStoreError:
        raise ApiError(500, "storage_error", "Schema storage failed.") from None
    summary = items_summary(items)
    if split is None:
        summary["by_split"], summary["control_in_held_out"] = None, None
    by_origin_report = None
    sel = (grid or {}).get("selected") if grid else None
    if split is not None and sel:
        rows = [m for m in metrics if m.get("setting_id") == sel.get("setting_id")]
        by_origin_report = origin_report(items, rows, split="held_out")
    return {
        "family": family, "budget_tokens": budget, "replay": request.app.state.replay, "config_hash": config.config_hash(cfgs),
        "corpus": corpus, "items": items, "split": split.to_dict() if split is not None else None,
        "items_summary": summary, "origin_report": by_origin_report,
        "settings": svc.settings(family),
        "grid": grid, "metrics": metrics, "quality": quality, "schemas": schemas, "schemas_rejected": schemas_rejected, "schema_diff": schema_diff,
        "proposals": get_proposals(request).list_proposals(family), "answers": [], "answers_summary": [], "runs_summary": None,
        "header_b": header_b_view(svc.runs_dir) if family == "uupt" else {"projection": None, "samples": [], "stored_counts": {}},
    }
