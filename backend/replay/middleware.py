"""Middleware mode putar ulang (docs/API.md §1): header `X-Replay: true|false` di SEMUA respons (termasuk galat) dan
penolakan endpoint tulis yang tidak punya cabang replay sendiri.

Endpoint [Spark] dan W1/W7/W9 sudah menangani `replay` di router/servisnya (baca run tersimpan atau 409
`replay_no_stored_run`; W6 live hanya `scene_checked`). Yang belum: W5 (`POST /api/proposals/{id}/decision`) menulis
usulan dan butir, jadi ditolak di sini. Kode `replay_mode` belum ada di API §1, maka `400 invalid_request` (sama dengan W9).
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

HEADER = "X-Replay"
# Tulis tanpa cabang replay di routernya. (metode, pola jalur)
REPLAY_BLOCKED: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"^/api/proposals/[^/]+/decision/?$")),
)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


class ReplayMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        replay = bool(getattr(request.app.state, "replay", False))
        resp: Response
        if replay and any(request.method == m and p.match(request.url.path) for m, p in REPLAY_BLOCKED):
            resp = _error(400, "invalid_request", "Replay mode is read-only; this action is not available.")
        else:
            try:
                resp = await call_next(request)
            except Exception:  # handler Exception milik FastAPI berada di luar middleware; bentuk galat tetap sama
                resp = _error(500, "internal_error", "Unexpected server error.")
        resp.headers[HEADER] = "true" if replay else "false"
        return resp


def install_replay(app: FastAPI) -> None:
    app.add_middleware(ReplayMiddleware)


__all__: list[Any] = ["HEADER", "REPLAY_BLOCKED", "ReplayMiddleware", "install_replay"]
