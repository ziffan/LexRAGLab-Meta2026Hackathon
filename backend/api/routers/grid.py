"""W1 `POST /api/families/{family}/grid/run` (docs/API.md §3). Tanpa Model API; hasil dikunci per hash."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.api.errors import ApiError
from backend.api.routers.corpus import check_family

router = APIRouter()


class GridRunBody(BaseModel):
    budget_tokens: int | None = None


@router.post("/api/families/{family}/grid/run")
def run_grid(request: Request, family: str, body: GridRunBody | None = None) -> dict[str, Any]:
    """Jalankan grid keluarga (atau baca cache). Respons: `RunRecord`; kunci sama -> `status = "cached"`.

    Satu run selalu mencakup semua anggaran di `config/grid`; `budget_tokens` hanya divalidasi terhadap daftar itu."""
    svc = request.app.state.service
    check_family(family)
    if body is not None and body.budget_tokens is not None:
        b = svc.cfg("grid")["budget"]
        allowed = [b["default_tokens"], *b.get("comparison_tokens", [])]
        if body.budget_tokens not in allowed:
            raise ApiError(400, "invalid_request", f"budget_tokens must be one of {allowed} or null.")
    return svc.run_grid(family, replay=request.app.state.replay).record
