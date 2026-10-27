"""W2 `POST /api/families/{family}/schemas/induce` [Spark] dan W9 `POST /api/families/{family}/schemas/{version}/correct`
(docs/API.md 3, 5), M3.3. W2 menyimpan versi Spark; W9 tidak memanggil Spark, memvalidasi seperti keluaran A, dan selalu
membuat versi baru. Isi koreksi berasal dari operator (H-037); route ini tidak mengisinya."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from backend.api.errors import ApiError
from backend.api.routers.corpus import check_family
from backend.schema_a import (ParentNotFound, SampleDoc, SampleHashMismatch, SchemaInvalid, SchemaStore, SchemaStoreError,
                              correct, induce, load_prompt, parent_samples)
from backend.spark import BudgetExceeded, ConfigInvalid, SparkClient
from backend.spark.store import canonical_json, sha256_hex

router = APIRouter()

MAX_SAMPLE_DOCS = 20
MAX_NOTE_CHARS = 2000
_ERR_STATUS = {"replay_no_stored_run": (409, "replay_no_stored_run"), "schema_invalid": (422, "schema_invalid"),
               "semantic_invalid": (422, "schema_invalid"), "model_unavailable": (503, "model_unavailable"),
               "timeout": (503, "model_unavailable"), "rate_limited": (503, "model_unavailable")}


def _profile(request: Request) -> str:
    mc = request.app.state.model_config
    name = mc.get("default_profile")
    prof = mc.get("profiles", {}).get(name) if isinstance(name, str) else None
    if prof is None:
        raise ApiError(503, "model_unavailable", "Default model profile is not configured.")
    if prof.get("roles") and "a" not in prof["roles"]:
        raise ApiError(422, "validation_failed", "The default model profile is not available for role A.")
    return name


def _store(request: Request) -> SchemaStore:
    return SchemaStore(request.app.state.service.runs_dir)


@router.post("/api/families/{family}/schemas/induce")
def post_induce(request: Request, family: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    st = request.app.state
    svc = st.service
    check_family(family)
    ids = body.get("sample_doc_ids")
    if set(body) - {"sample_doc_ids"} or not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ApiError(400, "invalid_request", "Body must be {\"sample_doc_ids\": [string, ...]}.")
    if not ids or len(ids) > MAX_SAMPLE_DOCS or len(set(ids)) != len(ids):
        raise ApiError(422, "validation_failed", f"sample_doc_ids must hold 1 to {MAX_SAMPLE_DOCS} distinct doc_ids.")
    docs = [svc.doc(i) for i in ids]
    for d in docs:
        if d.family != family:
            raise ApiError(422, "validation_failed", f"Document {d.doc_id!r} does not belong to family {family!r}.")
    samples = [SampleDoc(d.doc_id, d.text, d.clean_sha256) for d in docs]
    profile = _profile(request)
    tok = svc.tok()
    clean = docs[0].clean_sha256 if len(docs) == 1 else sha256_hex(canonical_json(sorted(d.clean_sha256 for d in docs)))
    meta = {"corpus_hash": sha256_hex(canonical_json(sorted(d.sha256 for d in docs))), "clean_sha256": clean,
            "loader_rules_version": docs[0].loader_rules_version,
            "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
    try:
        client = SparkClient(profile, model_config=st.model_config, budget_config=st.budget_config, env=st.env,
                             runs_dir=svc.runs_dir, transport=st.spark_transport, replay=st.replay)
        out = induce(client, load_prompt(), family=family, samples=samples, count_tokens=tok.count, meta=meta,
                     store=_store(request), replay=st.replay)
    except BudgetExceeded as exc:
        raise ApiError(402, "budget_exceeded", str(exc)[:300]) from None
    except ConfigInvalid as exc:
        raise ApiError(503, "model_unavailable", str(exc)[:300]) from None
    except SchemaStoreError:
        raise ApiError(500, "storage_error", "Schema storage failed.") from None
    if out.error is not None:
        status, code = _ERR_STATUS.get(out.error["code"], (502, "model_error"))
        raise ApiError(status, code, str(out.error["message"])[:300])
    return {"schema_record": out.record, "run": out.run.to_dict()}


@router.post("/api/families/{family}/schemas/{version}/correct")
def post_correct(request: Request, family: str, version: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    st = request.app.state
    svc = st.service
    check_family(family)
    if set(body) - {"schema", "operator_note"} or "schema" not in body:
        raise ApiError(400, "invalid_request", "Body must be {\"schema\": SchemaA, \"operator_note\": string | null}.")
    note = body.get("operator_note")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE_CHARS):
        raise ApiError(400, "invalid_request", f"operator_note must be a string of at most {MAX_NOTE_CHARS} characters or null.")
    if st.replay:
        raise ApiError(400, "invalid_request", "Replay mode is read-only; schema corrections are not available.")
    store = _store(request)
    try:
        parent = store.get(family, version)
        if parent is None:
            raise ApiError(404, "not_found", f"No schema version {version} for family {family!r}.")
        rec = correct(store, family=family, parent_version=version, schema=body["schema"], operator_note=note,
                      samples=parent_samples(parent, svc.doc))
    except SchemaInvalid as exc:
        raise ApiError(422, "schema_invalid", "; ".join(exc.errors[:5])[:600]) from None
    except SampleHashMismatch as exc:  # disengaja (H-046): offset/contoh hanya sah terhadap teks bersih yang sama
        raise ApiError(409, "hash_mismatch", f"Sample document {str(exc)[:60]!r} has a different clean text than the one the schema was induced from.") from None
    except ParentNotFound:
        raise ApiError(404, "not_found", f"No schema version {version} for family {family!r}.") from None
    except SchemaStoreError:
        raise ApiError(500, "storage_error", "Schema storage failed.") from None
    return rec
