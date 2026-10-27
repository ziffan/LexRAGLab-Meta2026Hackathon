"""Aplikasi FastAPI tunggal (docs/API.md): satu `create_app`, router per modul, satu handler galat.

Pakai: `uv run python -m backend.api` (listen 127.0.0.1 saja). Tanpa Model API di route mana pun pada M1.
Router: system (R1, R6), corpus (R4), snapshot (R3), retrieval (R5), grid (W1), answers (W6, M2.2).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from backend import config as cfg
from backend.api.errors import ApiError, install_error_handlers
from backend.api.routers import answers, corpus, grid, proposals, retrieval, schemas, snapshot, system
from backend.api.service import FAMILIES, Service
from backend.spark.settings import load_configs

__all__ = ["ApiError", "FAMILIES", "Service", "create_app"]


def create_app(service: Service | None = None, *, env: Mapping[str, str] | None = None, runs_dir: Path | None = None,
               model_config: Mapping[str, Any] | None = None, budget_config: Mapping[str, Any] | None = None,
               replay: bool = False, spark_transport: Any = None) -> FastAPI:
    """`service` memegang korpus/butir/runs; `runs_dir` (bila diberikan) menggantikan `service.runs_dir`.
    `env`, `model_config`, `budget_config` untuk R1 (ketersediaan profil; nilai key tidak pernah dikembalikan)."""
    svc = service or Service()
    if runs_dir is not None:
        svc.runs_dir = Path(runs_dir)
    if model_config is None or budget_config is None:
        m, b = load_configs()
        model_config, budget_config = model_config or m, budget_config or b
    app = FastAPI(title="LexRAGLab", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = svc
    app.state.env = dict(os.environ if env is None else env)
    app.state.model_config = model_config
    app.state.budget_config = budget_config
    app.state.spark_transport = spark_transport  # hanya untuk test (transport palsu)
    app.state.replay = replay
    app.state.config_hash = cfg.config_hash({"model": dict(model_config), "budget": dict(budget_config)})
    install_error_handlers(app)
    for module in (system, corpus, snapshot, retrieval, grid, answers, proposals, schemas):
        app.include_router(module.router)
    return app
