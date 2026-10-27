"""R3 `GET /api/families/{family}/snapshot` (docs/API.md §2, §4): bagian M1.

Dibangun dari berkas dan cache; tidak pernah menjalankan grid, chunker, atau Spark (API.md §5). Hasil grid dibaca dari
`runs/grid/<kunci>.json` untuk kunci yang dihitung dari masukan saat ini; bila belum ada, `grid` bernilai null.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Request

from backend import config
from backend.api.errors import ApiError
from backend.api.routers.corpus import check_family
from backend.api.routers.proposals import get_proposals
from backend.grid.types import metrics_from_cache
from backend.schema_a import SchemaStore, SchemaStoreError, snapshot_view

router = APIRouter()

CORPUS_FIELDS = ("doc_id", "family", "title", "path", "sha256", "clean_sha256", "loader_rules_version", "char_count",
                 "tokens_local", "tokens_endpoint", "calibration_ratio", "sections", "annotations")


def grid_view(env: dict[str, Any], budget: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """(grid, metrics, quality) untuk satu anggaran; grid None bila anggaran itu tidak ada di run tersimpan."""
    ids = {s["setting_id"] for s in env["settings_run"] if s["budget_tokens"] == budget}
    if not ids:
        return None, [], []
    grid: dict[str, Any] = {}
    for split in ("tune", "held_out"):
        grid[split] = {
            "points": [p for p in env["points"] if p["split"] == split and p["budget_tokens"] == budget],
            "frontier": next((f for f in env["frontiers"] if f["split"] == split and f["budget_tokens"] == budget), None),
        }
    grid["selected"] = env["selections"].get(str(budget))
    grid["quality_comparison"] = next((c for c in env["quality_comparison"] if c["budget_tokens"] == budget), None)
    grid["skipped"] = [s for s in env["skipped"] if s["budget_tokens"] == budget]
    grid["grid_run_id"] = env["key"]
    metrics = [metrics_from_cache(m).to_dict() for m in env["metrics"] if m["setting_id"] in ids]
    quality = [q for q in env["quality"] if q["setting_id"] in ids]
    return grid, metrics, quality


@router.get("/api/families/{family}/snapshot")
def get_snapshot(request: Request, family: str, budget_tokens: int | None = None) -> dict[str, Any]:
    svc = request.app.state.service
    check_family(family)
    grid_cfg = svc.cfg("grid")
    budget = budget_tokens if budget_tokens is not None else grid_cfg["budget"]["default_tokens"]
    corpus: list[dict[str, Any]] = []
    if family == "uupt":
        d = svc.doc("uupt-40-2007")
        corpus = [{k: getattr(d, k) for k in CORPUS_FIELDS}]
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
    grid, metrics, quality = grid_view(env, budget) if env is not None else (None, [], [])
    by_split = dict(Counter(split_of.values())) if split is not None else None
    try:
        schemas, schema_diff = snapshot_view(SchemaStore(svc.runs_dir).list(family))
    except SchemaStoreError:
        raise ApiError(500, "storage_error", "Schema storage failed.") from None
    return {
        "family": family, "budget_tokens": budget, "replay": request.app.state.replay, "config_hash": config.config_hash(cfgs),
        "corpus": corpus, "items": items, "split": split.to_dict() if split is not None else None,
        "items_summary": {"n_items": len(items), "by_origin": dict(Counter(i.get("origin") for i in items)),
                          "by_mode": dict(Counter(i.get("mode") for i in items)), "by_split": by_split,
                          "control_in_held_out": split.control_in_held_out if split is not None else None},
        "settings": svc.settings(family),
        "grid": grid, "metrics": metrics, "quality": quality, "schemas": schemas, "schema_diff": schema_diff,
        "proposals": get_proposals(request).list_proposals(family), "answers": [], "answers_summary": [], "runs_summary": None,
    }
