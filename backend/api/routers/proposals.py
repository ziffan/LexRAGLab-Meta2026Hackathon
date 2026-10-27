"""W4 `POST /api/families/{family}/proposals/generate` [Spark] dan W5 `POST /api/proposals/{proposal_id}/decision`
(docs/API.md 3, 5), M2.1.

W4 tidak pernah membuat `Item`. W5 menerima transisi hanya dari `usulan` (H-006, H-035). Respons W4:
`{"proposals": ProposalRecord[], "runs": RunRecord[]}` (satu RunRecord per mode, A23). Respons W5:
`{"proposal": ProposalRecord, "item": Item | null}`."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from backend.api.errors import ApiError
from backend.api.routers.corpus import check_family
from backend.proposal.absence import load_absence_config, service_checker_provider
from backend.proposal.report import pending_count
from backend.proposal.service import DocInfo, ProposalService
from backend.spark import SparkClient

router = APIRouter()


def get_proposals(request: Request) -> ProposalService:
    """Layanan usulan per aplikasi; test boleh menggantinya lewat `app.state.proposals`."""
    st = request.app.state
    svc = getattr(st, "proposals", None)
    if svc is None:
        base = st.service

        def docs(doc_id: str) -> DocInfo | None:
            try:
                d = base.doc(doc_id)
            except ApiError:
                return None
            return DocInfo(d.doc_id, d.family, d.text, d.clean_sha256)

        svc = ProposalService(runs_dir=base.runs_dir, butir_dir=base.butir_dir, doc_provider=docs,
                              count_tokens=lambda t: int(base.tok().count(t)), config_dir=base.config_dir,
                              checker_provider=service_checker_provider(base))
        st.proposals = svc
    return svc


@router.post("/api/families/{family}/proposals/generate")
def post_generate(request: Request, family: str, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    st = request.app.state
    check_family(family)
    if body is None:
        raise ApiError(400, "invalid_request", "Request body must be a JSON object.")
    svc = get_proposals(request)
    profile = st.model_config.get("default_profile")
    if not isinstance(profile, str):
        raise ApiError(503, "model_unavailable", "No default model profile.")

    def make_client() -> SparkClient:
        return SparkClient(profile, model_config=st.model_config, budget_config=st.budget_config, env=st.env,
                           runs_dir=st.service.runs_dir, transport=st.spark_transport, replay=False, now=svc.clock)

    return svc.generate(family, body.get("doc_id"), body.get("modes"), profile=profile, model_config=st.model_config,
                        client_factory=make_client, replay=bool(st.replay))


@router.post("/api/proposals/{proposal_id}/decision")
def post_decision(request: Request, proposal_id: str, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    return get_proposals(request).decide(proposal_id, body)


@router.get("/api/families/{family}/proposals")
def get_queue(request: Request, family: str) -> dict[str, Any]:
    """Antrean layar Review (U6): semua `ProposalRecord` keluarga (klien menyaring `usulan`), jumlah menunggu, dan jumlah
    baris konteks dari `config/proposals` (A19). Hanya baca; tidak memanggil Spark."""
    check_family(family)
    svc = get_proposals(request)
    recs = svc.list_proposals(family)
    return {"proposals": recs, "pending": pending_count(recs), "context_lines": svc.context_lines,
            "check_config_hash": svc.check_config_hash()}
