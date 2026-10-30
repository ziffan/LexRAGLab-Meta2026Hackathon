"""Titik masuk lama `backend.app:create_app` (R1, R6), kini hanya alias ke aplikasi tunggal `backend.api.app`.

Pakai server: uv run uvicorn backend.app:server_app --factory --host 127.0.0.1  (atau `uv run python -m backend.api`).
`server_app` memanaskan indeks record R1/R6 saat startup (M5.1-N1); alias `create_app` tanpa pemanasan (test).
"""

from fastapi import FastAPI

from backend.api.app import create_app

__all__ = ["create_app", "server_app"]


def server_app() -> FastAPI:
    """Factory server: `create_app(warm_index=True)`."""
    return create_app(warm_index=True)
