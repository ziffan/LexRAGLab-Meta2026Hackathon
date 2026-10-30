"""Aplikasi FastAPI tunggal (docs/API.md): satu `create_app`, router per modul, satu handler galat.

Pakai: `uv run python -m backend.api` (listen 127.0.0.1 saja). Tanpa Model API di route mana pun pada M1.
Router: system (R1, R6), corpus (R4), snapshot (R3), retrieval (R5), grid (W1), answers (W6, M2.2).
"""

from __future__ import annotations

import os
import threading
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from backend import config as cfg
from backend.api.errors import ApiError, install_error_handlers
from backend.api.routers import answers, corpus, grid, headers, profiles, proposals, retrieval, schemas, snapshot, system
from backend.api.service import FAMILIES, Service
from backend.replay.middleware import install_replay
from backend.spark import local_server
from backend.spark.settings import API_CHAT, load_configs, profile_api

__all__ = ["ApiError", "FAMILIES", "Service", "create_app"]


def create_app(service: Service | None = None, *, env: Mapping[str, str] | None = None, runs_dir: Path | None = None,
               model_config: Mapping[str, Any] | None = None, budget_config: Mapping[str, Any] | None = None,
               replay: bool = False, spark_transport: Any = None, warm_index: bool = False) -> FastAPI:
    """`service` memegang korpus/butir/runs; `runs_dir` (bila diberikan) menggantikan `service.runs_dir`.
    `env`, `model_config`, `budget_config` untuk R1 (ketersediaan profil; nilai key tidak pernah dikembalikan).
    `warm_index` (M5.1-N1): saat startup, thread daemon memanaskan indeks record R1/R6 (hanya server; test default mati)."""
    svc = service or Service()
    if runs_dir is not None:
        svc.runs_dir = Path(runs_dir)
    if model_config is None or budget_config is None:
        m, b = load_configs()
        model_config, budget_config = model_config or m, budget_config or b
    lifespan = _warm_lifespan if warm_index else None
    app = FastAPI(title="LexRAGLab", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service = svc
    app.state.env = dict(os.environ if env is None else env)
    app.state.model_config = model_config
    app.state.budget_config = budget_config
    app.state.spark_transport = spark_transport  # hanya untuk test (transport palsu)
    app.state.replay = replay
    app.state.config_hash = cfg.config_hash({"model": dict(model_config), "budget": dict(budget_config)})
    install_error_handlers(app)
    install_replay(app)  # header X-Replay di semua respons; W5 ditolak di replay (M5.1)
    for module in (system, corpus, snapshot, retrieval, grid, answers, proposals, schemas, headers, profiles):
        app.include_router(module.router)
    return app


@asynccontextmanager
async def _warm_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Mulai pemanasan indeks R1/R6 di thread daemon; tidak menunggu, tidak menulis apa pun. Di luar replay dan tanpa
    probe pengganti test, cache probe server lokal (profil Chat Completions) diperbarui di latar (M5.1-N1)."""
    st = app.state
    idx = system.run_index(st, st.service.runs_dir)
    threading.Thread(target=idx.warm, name="run-index-warm", daemon=True).start()
    stop = threading.Event()
    targets = [(p.get("base_url", ""), p.get("model", "")) for p in st.model_config.get("profiles", {}).values()
               if profile_api(p) == API_CHAT]
    if targets and not st.replay and getattr(st, "local_probe", None) is None:
        for t in dict.fromkeys(targets):  # satu thread per target: siklus < TTL berapa pun jumlah profil lokal
            threading.Thread(target=local_server.refresh_loop, args=([t], stop), name="local-probe-refresh",
                             daemon=True).start()
    try:
        yield
    finally:
        stop.set()
