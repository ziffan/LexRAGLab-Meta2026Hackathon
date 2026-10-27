"""FastAPI app: R1 `GET /api/health`, R6 `GET /api/runs` (docs/API.md). Listen di 127.0.0.1 saja.

Pakai: uv run uvicorn backend.app:create_app --factory --host 127.0.0.1
Respons tidak pernah memuat key atau base URL; `available` hanya benar/salah."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend import config as cfg
from backend.spark import store
from backend.spark.runrecord import KINDS
from backend.spark.settings import clean_env_value, load_configs

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(*, env: Mapping[str, str] | None = None, runs_dir: Path | None = None,
               model_config: Mapping[str, Any] | None = None, budget_config: Mapping[str, Any] | None = None,
               replay: bool = False) -> FastAPI:
    env_map = dict(os.environ if env is None else env)
    if model_config is None or budget_config is None:
        m, b = load_configs()
        model_config, budget_config = model_config or m, budget_config or b
    runs = Path(runs_dir) if runs_dir is not None else cfg.REPO_ROOT / "runs"
    chash = cfg.config_hash({"model": dict(model_config), "budget": dict(budget_config)})
    app = FastAPI(title="LexRAGLab", docs_url=None, redoc_url=None, openapi_url=None)

    def available(profile: Mapping[str, Any]) -> bool:
        if not clean_env_value(env_map.get(profile.get("api_key_env", ""))):
            return False
        if isinstance(profile.get("base_url"), str) and profile["base_url"]:
            return True
        return bool(clean_env_value(env_map.get(profile.get("base_url_env", ""))))

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        profiles = model_config.get("profiles", {})
        default = model_config.get("default_profile")
        return {
            "status": "ok",
            "replay": replay,
            "model": profiles.get(default, {}).get("model"),
            "config_hash": chash,
            "model_profiles": [
                {"model_profile": name, "model": p.get("model"), "available": available(p)}
                for name, p in profiles.items()
            ],
        }

    @app.get("/api/runs")
    def runs_list(kind: str | None = None, limit: str | None = None):
        if kind is not None and kind not in KINDS:
            return _error(400, "invalid_request", "kind must be one of: " + ", ".join(KINDS))
        n = DEFAULT_LIMIT
        if limit is not None:
            if not limit.isascii() or not limit.isdigit() or not (1 <= int(limit) <= MAX_LIMIT):
                return _error(400, "invalid_request", f"limit must be an integer between 1 and {MAX_LIMIT}")
            n = int(limit)
        try:
            records = store.load_records(runs)
        except ValueError:
            return _error(500, "model_error", "stored run records are unreadable")
        if kind is not None:
            records = [r for r in records if r.kind == kind]
        records.sort(key=lambda r: (r.created_at, r.run_id), reverse=True)
        return [r.to_dict() for r in records[:n]]

    return app
