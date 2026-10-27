"""R1 `GET /api/health` dan R6 `GET /api/runs` (docs/API.md §2). Respons tidak pernah memuat key atau base URL."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from backend.api.errors import ApiError
from backend.spark import store
from backend.spark.runrecord import KINDS, RunRecord
from backend.spark.settings import clean_env_value

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

router = APIRouter()


def _available(profile: Mapping[str, Any], env_map: Mapping[str, str]) -> bool:
    if not clean_env_value(env_map.get(profile.get("api_key_env", ""))):
        return False
    if isinstance(profile.get("base_url"), str) and profile["base_url"]:
        return True
    return bool(clean_env_value(env_map.get(profile.get("base_url_env", ""))))


def grid_records(runs_dir: Path) -> list[RunRecord]:
    """RunRecord run grid dari amplop `runs/grid/<kunci>.json`; amplop tanpa record (belum selesai) atau rusak dilewati."""
    out: list[RunRecord] = []
    d = Path(runs_dir) / "grid"
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            rec = json.loads(p.read_bytes().decode("utf-8")).get("record")
            if rec:
                out.append(RunRecord.from_dict(rec))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return out


@router.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    st = request.app.state
    profiles = st.model_config.get("profiles", {})
    default = st.model_config.get("default_profile")
    return {
        "status": "ok",
        "replay": st.replay,
        "model": profiles.get(default, {}).get("model"),
        "config_hash": st.config_hash,
        "model_profiles": [
            {"model_profile": name, "model": p.get("model"), "available": _available(p, st.env)}
            for name, p in profiles.items()
        ],
    }


@router.get("/api/runs")
def runs_list(request: Request, kind: str | None = None, limit: str | None = None):
    if kind is not None and kind not in KINDS:
        raise ApiError(400, "invalid_request", "kind must be one of: " + ", ".join(KINDS))
    n = DEFAULT_LIMIT
    if limit is not None:
        if not limit.isascii() or not limit.isdigit() or not (1 <= int(limit) <= MAX_LIMIT):
            raise ApiError(400, "invalid_request", f"limit must be an integer between 1 and {MAX_LIMIT}")
        n = int(limit)
    runs = request.app.state.service.runs_dir
    try:
        records = store.load_records(runs)
    except ValueError:
        raise ApiError(500, "model_error", "stored run records are unreadable") from None
    records += grid_records(runs)
    if kind is not None:
        records = [r for r in records if r.kind == kind]
    records.sort(key=lambda r: (r.created_at, r.run_id), reverse=True)
    return [r.to_dict() for r in records[:n]]
