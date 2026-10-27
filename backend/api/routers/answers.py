"""W6 `POST /api/families/{family}/answers` [Spark] (docs/API.md 3, 5), bagian M2.2 + M2.3: peran C untuk dua kolom.

M2.3: `verifier` = `VerifierResult` per kutipan (best lalu baseline, urutan `citation_index`), dihitung SAAT RESPONS dari
`AnswerRecord` yang tak diubah (verifier murni; hasilnya tidak ditulis ulang ke `runs/answers/`), dan `summary` =
`RejectionSummary` per (setting_id, slot, model_profile) untuk butir ini. Mode replay yang tak menemukan run tersimpan
untuk prompt `current` mencoba versi prompt lebih lama (hasil v1 tetap dapat dibaca). `tolak` dan `bukti_tidak_cukup` adalah respons 200. `live=false` (atau mode replay tanpa
butir `scene_checked`) hanya membaca run tersimpan; tanpa run -> 409 `replay_no_stored_run`. Hanya profil Contributor
(`meta`) dan `openrouter_dev` untuk dev; profil berbatas peran diterima hanya bila `roles` memuat `c` (M2.5: Spark Open
Baseten, Glimmer lokal); profil tanpa `c` -> 422. Jawaban tersimpan per `model_profile` (ada di `answer_id`), tak pernah
digabung lintas profil (H-028)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend import config
from backend.answer.caller import run_answers
from backend.answer.context import build_context, check_same_budget
from backend.answer.prompt import load_prompt, prompt_versions
from backend.api.errors import ApiError
from backend.api.routers.corpus import check_family
from backend.api.routers.system import profile_status
from backend.spark.settings import API_CHAT, profile_api
from backend.grid.types import Setting
from backend.pipeline.grid_run import baseline_for, to_grid_items
from backend.pipeline.pipeline import SettingNotAvailable
from backend.spark import BudgetExceeded, ConfigInvalid, SparkClient
from backend.verifier import (ChunkSpan, VerifierConfigError, grade_answer, parse_verifier_config, summarize,
                              units_from_address_map)

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
    roles = prof.get("roles")
    if roles and "c" not in roles:  # profil berbatas peran: hanya yang memuat C boleh di W6 (H-053, H-060)
        raise ApiError(422, "validation_failed", "This model_profile is not available for the answer role (C).")
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
    prof_cfg = st.model_config["profiles"][profile]
    if allow_live and prof_cfg.get("live_via_cli"):
        # G-26: W6 live menjalankan retrieval/embedding di proses ini; profil ini dijalankan lewat CLI. Hasil tersimpan tetap terbaca.
        raise ApiError(409, "live_unavailable", "This model runs offline via the CLI to avoid GPU contention with embeddings; stored results are shown.")
    if allow_live and profile_api(prof_cfg) == API_CHAT:
        ok, why = profile_status(request, prof_cfg)  # server lokal mati -> 503 jelas, tanpa konteks/embedding
        if not ok:
            raise ApiError(503, "model_unavailable", why or "Local model server is not available.")
    item = to_grid_items([raw])[0]
    doc = svc.doc("uupt-40-2007")
    tok = svc.tok()
    meta = {"corpus_hash": config.config_hash({"docs": [doc.sha256]}), "clean_sha256": doc.clean_sha256,
            "loader_rules_version": doc.loader_rules_version,
            "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
    try:
        vcfg = parse_verifier_config(svc.cfg("verifier"))
    except (VerifierConfigError, config.ConfigError) as exc:
        raise ApiError(500, "internal_error", f"Verifier configuration is invalid: {str(exc)[:200]}") from None
    versions = prompt_versions() if replay else prompt_versions()[:1]  # replay boleh jatuh ke versi lebih lama
    outcomes: list = []
    slots: list = []
    for n, ver in enumerate(versions):
        prompt = load_prompt(ver)
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
                                           answers_dir=svc.runs_dir / "answers", persist=not replay)
        except BudgetExceeded as exc:
            raise ApiError(402, "budget_exceeded", str(exc)[:300]) from None
        except ConfigInvalid as exc:
            raise ApiError(503, "model_unavailable", str(exc)[:300]) from None
        missing = any(o.error is not None and o.error["code"] == "replay_no_stored_run" for o in outcomes)
        if not (replay and missing and n + 1 < len(versions)):
            break
    for o in outcomes:
        if o.error is not None:
            status, code = _ERR_STATUS.get(o.error["code"], (502, "model_error"))
            raise ApiError(status, code, f"{o.slot}: {o.error['message']}"[:300])
    by_slot = {o.slot: o for o in outcomes}
    verifier: list[dict[str, Any]] = []
    cells: list[tuple[str, str, str, str]] = []
    with svc.compute_lock:
        for slot, setting in (("best", best), ("baseline", base)):
            ans = by_slot[slot].answer
            cs = svc.pipeline().chunk_set(setting)
            units = units_from_address_map(cs.amap, doc.text)
            spans = [ChunkSpan(cid, cs.by_id[cid].start, cs.by_id[cid].end) for cid in ans["context_chunk_ids"]]
            verdicts, cell = grade_answer(ans["answer_id"], ans["output"], units, spans, item.gold_spans, vcfg)
            verifier += [v.result.to_dict() for v in verdicts]
            cells.append((ans["setting_id"], slot, ans["model_profile"], cell))
    return {"best": by_slot["best"].answer, "baseline": by_slot["baseline"].answer, "verifier": verifier,
            "summary": [x.to_dict() for x in summarize(cells)], "runs": [o.run.to_dict() for o in outcomes]}
