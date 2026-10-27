"""R5 `GET /api/families/{family}/retrieval` (docs/API.md §2): ranking dan potongan terambil satu (setting, butir)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from backend.api.routers.corpus import check_family

router = APIRouter()


@router.get("/api/families/{family}/retrieval")
def get_retrieval(request: Request, family: str, setting_id: str, item_id: str) -> dict[str, Any]:
    """`{retrieved_chunk_ids, ranks, scores, packed_tokens}`: `ranks` = posisi di ranking C, `scores` skor retriever,
    `packed_tokens` = token lokal yang dipakai (termasuk header). Menghitung satu butir; tanpa Model API."""
    check_family(family)
    return request.app.state.service.retrieval(family, setting_id, item_id)
