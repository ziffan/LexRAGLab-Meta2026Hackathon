"""W7 `GET /api/families/{family}/profiles/export` dan W8 `POST /api/profiles/import` (docs/API.md §3, M4.3).

Tanpa Model API. W7 menulis `profiles/{family}/{setting_id}.json` (tidak di replay); W8 tidak menulis apa pun (A7, A8).
Test dapat menyuntikkan `app.state.profile_deps` (ProfileDeps) dan `app.state.profiles_dir`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse, Response

from backend.api.errors import ApiError
from backend.grid.expand import expand_grid
from backend.grid.types import metrics_from_cache, setting_content
from backend.pipeline.grid_run import CONFIGS, pipeline_config_hash
from backend.profile import ProfileDeps, ProfileError, export_profile, import_profile, make_default_chunker
from backend.schema_a import SchemaStore, SchemaStoreError

router = APIRouter()

_STATUS = {"validation_failed": 422, "not_found": 404, "invalid_request": 400, "hash_mismatch": 409}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_deps(request: Request) -> ProfileDeps:
    st = request.app.state
    svc = st.service
    tok = svc.tok()
    retrieval, grid = svc.cfg("retrieval"), svc.cfg("grid")

    def docs(family: str) -> list[Any]:
        return [svc.doc(d["doc_id"]) for d in svc.cfg("corpus")["documents"] if d["family"] == family]

    def settings(family: str) -> list[dict[str, Any]]:
        return [{"setting_id": s.setting_id, **setting_content(s)} for s in expand_grid(grid, family)]

    def grid_metrics(family: str):
        _plan, env = svc.stored_grid(family)  # hanya membaca runs/grid
        if env is None:
            return None
        return svc.items(family), [metrics_from_cache(m) for m in env["metrics"]]

    def schema(family: str, version: int):
        try:
            return SchemaStore(svc.runs_dir).get(family, version)
        except SchemaStoreError:
            return None

    dense = retrieval["dense"]
    embedder = {"name": dense["model"], "revision": dense["revision"], "max_seq_length": int(dense["max_seq_length"])}
    profiles_dir = getattr(st, "profiles_dir", None) or Path(svc.runs_dir).parent / "profiles"
    return ProfileDeps(
        docs=docs, settings=settings, chunker=make_default_chunker(retrieval, grid), tokenizer=tok,
        config_hash=pipeline_config_hash({n: svc.cfg(n) for n in CONFIGS}, tok.info), packing=grid["packing"]["rule"],
        embedder=embedder, grid_metrics=grid_metrics, schema=schema, clock=_utc_now, profiles_dir=Path(profiles_dir))


def _deps(request: Request) -> ProfileDeps:
    return getattr(request.app.state, "profile_deps", None) or build_deps(request)


def _api_error(exc: ProfileError) -> ApiError:
    return ApiError(_STATUS[exc.kind], exc.kind, exc.message)


@router.get("/api/families/{family}/profiles/export")
def get_export(request: Request, family: str, setting_id: str | None = None) -> Response:
    replay = bool(request.app.state.replay)
    try:
        res = export_profile(_deps(request), family, setting_id, replay=replay)
    except ProfileError as exc:
        raise _api_error(exc) from None
    name = f"profile-{family}-{(setting_id or '')[:12]}.json"
    return Response(content=res.body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Replay": "true" if replay else "false"})


@router.post("/api/profiles/import")
def post_import(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        out = import_profile(_deps(request), body)
    except ProfileError as exc:
        raise _api_error(exc) from None
    return JSONResponse(out, headers={"X-Replay": "true" if request.app.state.replay else "false"})
