"""W6 `POST /api/families/{family}/answers` [Spark] (docs/API.md 3, 5), bagian M2.2: peran C untuk dua kolom.

`verifier` kosong sampai M2.3. `tolak` dan `bukti_tidak_cukup` adalah respons 200. `live=false` (atau mode replay tanpa
butir `scene_checked`) hanya membaca run tersimpan; tanpa run -> 409 `replay_no_stored_run`. Hanya profil Contributor
(`meta`) dan `openrouter_dev` untuk dev; profil berbatas peran (Spark Open, M2.5) ditolak di sini."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend import config
from backend.answer.caller import run_answers
from backend.answer.context import build_context, check_same_budget
from backend.answer.prompt import load_prompt
from backend.api.errors import ApiError
from backend.api.routers.corpus import check_family
from backend.grid.types import Setting
from backend.pipeline.grid_run import baseline_for, to_grid_items
from backend.pipeline.pipeline import SettingNotAvailable
from backend.spark import BudgetExceeded, ConfigInvalid, SparkClient

router = APIRouter()

_ERR_STATUS = {"replay_no_stored_run": (409, "replay_no_stored_run"), "schema_invalid": (422, "schema_invalid"),
               "semantic_invalid": (422, "schema_invalid"), "model_unavailable": (503, "model_unavailable"),
               "timeout": (503, "model_unavailable"), "rate_limited": (503, "model_unavailable")}


class AnswersBody(BaseModel):
    item_id: str
    best_setting_id: str
    baseline_setting_id: str
    model_profile: str | None = None
    live: bool = False


def _profile(request: Request, name: str | None) -> str:
    mc = request.app.state.model_config
    name = name or mc.get("default_profile")
    prof = mc.get("profiles", {}).get(name) if isinstance(name, str) else None
    if prof is None:
        raise ApiError(400, "invalid_request", f"Unknown model_profile {str(name)[:40]!r}.")
    if prof.get("roles"):
        raise ApiError(422, "validation_failed", "This model_profile is not available for W6 until M2.5.")
    return name


@router.post("/api/families/{family}/answers")
def post_answers(request: Request, family: str, body: AnswersBody) -> dict[str, Any]:
    st = request.app.state
    svc = st.service
    check_family(family)
    if family != "uupt":
        raise ApiError(422, "validation_failed", f"Answers for family {family!r} are not available yet.")
    profile = _profile(request, body.model_profile)
    raw = next((i for i in svc.items(family) if i.get("id") == body.item_id), None)
    if raw is None:
        raise ApiError(404, "not_found", f"Unknown item_id {body.item_id[:60]!r}.")
    best = svc.find_setting(family, body.best_setting_id)
    base = svc.find_setting(family, body.baseline_setting_id)
    msg = check_same_budget(best, base)
    if msg:
        raise ApiError(422, "validation_failed", msg)
    expected: Setting | None = baseline_for(svc.grid_settings(family), best, svc.cfg("grid")["baseline"])
    if expected is None or expected.setting_id != base.setting_id:
        raise ApiError(422, "validation_failed", "baseline_setting_id must be the [baseline] setting (H-036) "
                       "with the same retrieval mode and budget as best_setting_id.")

    # live=false, atau mode replay tanpa butir scene_checked: hanya baca (API.md 1).
    allow_live = body.live and (not st.replay or bool(raw.get("scene_checked")))
    replay = not allow_live
    prompt = load_prompt()
    item = to_grid_items([raw])[0]
    doc = svc.doc("uupt-40-2007")
    tok = svc.tok()
    meta = {"corpus_hash": config.config_hash({"docs": [doc.sha256]}), "clean_sha256": doc.clean_sha256,
            "loader_rules_version": doc.loader_rules_version,
            "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
    with svc.compute_lock:
        try:
            pipe = svc.pipeline()
            slots = [("best", build_context(pipe, best, item, prompt)), ("baseline", build_context(pipe, base, item, prompt))]
        except SettingNotAvailable as exc:
            raise ApiError(422, "validation_failed", str(exc)) from None
    try:
        client = SparkClient(profile, model_config=st.model_config, budget_config=st.budget_config, env=st.env,
                             runs_dir=svc.runs_dir, transport=st.spark_transport, replay=replay)
        outcomes, _batch = run_answers(client, prompt, slots, item_id=body.item_id, model_profile=profile, meta=meta,
                                       answers_dir=svc.runs_dir / "answers")
    except BudgetExceeded as exc:
        raise ApiError(402, "budget_exceeded", str(exc)[:300]) from None
    except ConfigInvalid as exc:
        raise ApiError(503, "model_unavailable", str(exc)[:300]) from None
    for o in outcomes:
        if o.error is not None:
            status, code = _ERR_STATUS.get(o.error["code"], (502, "model_error"))
            raise ApiError(status, code, f"{o.slot}: {o.error['message']}"[:300])
    by_slot = {o.slot: o for o in outcomes}
    return {"best": by_slot["best"].answer, "baseline": by_slot["baseline"].answer, "verifier": [],
            "runs": [o.run.to_dict() for o in outcomes]}
