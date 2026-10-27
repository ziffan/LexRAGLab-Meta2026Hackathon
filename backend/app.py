"""Titik masuk lama `backend.app:create_app` (R1, R6), kini hanya alias ke aplikasi tunggal `backend.api.app`.

Pakai: uv run uvicorn backend.app:create_app --factory --host 127.0.0.1  (atau `uv run python -m backend.api`).
"""

from backend.api.app import create_app

__all__ = ["create_app"]
