"""W3 `POST /api/families/{family}/headers/run` [Spark] (docs/API.md 3, 5), M3.1: header B untuk satu dokumen.

Proyeksi dulu (tanpa jaringan), 402 bila melewati `config/budget`; lalu satu request pemanas dan panggilan berurutan.
Mode replay: hanya cache (409 `replay_no_stored_run` bila ada unit tanpa run tersimpan). `sample` membatasi ke N unit
pertama; `chunker: "fixed_size"` meminta header per potongan `fixed_size` (H-069)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend import config
from backend.api.errors import ApiError
from backend.api.routers.corpus import check_family
from backend.header_b.caller import run_headers
from backend.header_b.run import HeaderConfigError, load_header_cfg, prepare, project
from backend.spark import BudgetExceeded, ConfigInvalid, Ledger, SparkClient, effective_caps, pool_limits, profile_provider

router = APIRouter()

_ERR_STATUS = {"replay_no_stored_run": (409, "replay_no_stored_run"), "schema_invalid": (422, "schema_invalid"),
               "semantic_invalid": (502, "model_error"), "model_unavailable": (503, "model_unavailable"),
               "timeout": (503, "model_unavailable"), "rate_limited": (503, "model_unavailable")}


class HeadersBody(BaseModel):
    doc_id: str
    granularity: str
    chunker: str = "structure_handwritten"
    sample: int | None = None


@router.post("/api/families/{family}/headers/run")
def post_headers_run(request: Request, family: str, body: HeadersBody) -> dict[str, Any]:
    st = request.app.state
    svc = st.service
    check_family(family)
    if family != "uupt":
        raise ApiError(422, "validation_failed", f"Headers for family {family!r} are not available yet.")
    if body.granularity not in ("pasal", "ayat"):
        raise ApiError(400, "invalid_request", "granularity must be 'pasal' or 'ayat'.")
    if body.chunker not in ("structure_handwritten", "fixed_size"):
        raise ApiError(400, "invalid_request", "chunker must be 'structure_handwritten' or 'fixed_size'.")
    if body.sample is not None and body.sample < 1:
        raise ApiError(400, "invalid_request", "sample must be a positive integer.")
    source = "fixed_size" if body.chunker == "fixed_size" else body.granularity
    doc = svc.doc(body.doc_id)
    try:
        hc = load_header_cfg(svc.config_dir)
    except (HeaderConfigError, config.ConfigError) as exc:
        raise ApiError(503, "model_unavailable", f"Header config is invalid: {exc}"[:300]) from None
    tok = svc.tok()
    with svc.compute_lock:
        p = prepare(source, doc=doc, tokenizer=tok, header_cfg=hc, retrieval_cfg=svc.cfg("retrieval"),
                    grid_cfg=svc.cfg("grid"))
    proj = project(p, tok, hc, st.model_config, limit=body.sample)
    cost = proj["cost_usd_micros"]["upper_cached"]
    caps = effective_caps(st.budget_config, st.env)
    ledger = Ledger(svc.runs_dir)
    sr, rc, stt, tc = pool_limits(ledger, caps, profile_provider(st.model_config, None), "b")
    if not st.replay and (sr + cost > rc or stt + cost > tc):
        raise ApiError(402, "budget_exceeded", "Projected cost exceeds config/budget; nothing was sent.")
    units = p.units if body.sample is None else p.units[:body.sample]
    meta = {"corpus_hash": config.config_hash({"docs": [doc.sha256]}), "clean_sha256": doc.clean_sha256,
            "loader_rules_version": doc.loader_rules_version, "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
    try:
        client = SparkClient(st.model_config["default_profile"], model_config=st.model_config,
                             budget_config=st.budget_config, env=st.env, runs_dir=svc.runs_dir,
                             transport=st.spark_transport, replay=st.replay)
        res = run_headers(client, p.prompt, p.prefix, units, granularity=source, tokenizer=tok,
                          headers_dir=svc.runs_dir / "headers", max_header_tokens=hc["max_header_tokens"],
                          max_output_tokens=hc["max_output_tokens"], max_consecutive_errors=hc["max_consecutive_errors"],
                          warm_max_output_tokens=hc["warm_max_output_tokens"],
                          cache_guard_calls=hc["cache_guard_calls"], cache_guard_min_ratio=hc["cache_guard_min_ratio"],
                          meta=meta, warm=not st.replay, max_length_chars=hc.get("schema_max_length_chars"))
    except BudgetExceeded as exc:
        raise ApiError(402, "budget_exceeded", str(exc)[:300]) from None
    except ConfigInvalid as exc:
        raise ApiError(503, "model_unavailable", str(exc)[:300]) from None
    for o in res.outcomes:
        if o.error is not None:
            status, code = _ERR_STATUS.get(o.error["code"], (502, "model_error"))
            raise ApiError(status, code, o.error["message"][:300])
    if res.stopped_reason == "budget_exceeded":
        raise ApiError(402, "budget_exceeded", "Budget cap reached during the run.")
    if res.stopped_reason is not None:
        raise ApiError(502, "model_error", f"Run stopped: {res.stopped_reason}.")
    runs = ([res.warm] if res.warm else []) + [o.run for o in res.outcomes]
    return {"headers": [h for o in res.outcomes for h in o.headers], "runs": [r.to_dict() for r in runs],
            "projection_usd_micros": cost}
