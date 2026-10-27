"""API FastAPI minimal M1.1 (docs/API.md §2 R3 sebagian, R4). Listen di 127.0.0.1 saja (lihat `__main__`).

Tanpa Model API, tanpa penulisan data. Galat selalu `{"error": {"code", "message"}}` tanpa stack trace.
"""

from __future__ import annotations

import json
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend import config
from backend.chunking import ChunkOffsetError, chunk_document, make_setting_id
from backend.corpus import CorpusDoc, CorpusError, load_corpus

FAMILIES = ("uupt", "akta")
_ITEM_FILE = re.compile(r"^uupt\.v(\d+)\.jsonl$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def build_settings(family: str, retrieval_cfg: dict[str, Any], grid_cfg: dict[str, Any], budget_tokens: int | None = None) -> list[dict[str, Any]]:
    """Dua setting chunker yang ada di M1.1 (struktur tulisan tangan, ukuran tetap).

    Bentuk `Setting` (DATA-CONTRACTS §10): `setting_id` = SHA-256 atas JSON kanonik (sort_keys, tanpa spasi)
    dari delapan field lain. `retrieval_mode` dan `header_b` dari `config/retrieval` `[setting_defaults]`
    (placeholder sampai M1.2), `budget_tokens` dari `config/grid` `[budget] default_tokens`."""
    d = retrieval_cfg["setting_defaults"]
    budget = budget_tokens if budget_tokens is not None else grid_cfg["budget"]["default_tokens"]
    fx = grid_cfg["fixed_size"]
    common = {"family": family, "schema_version": None, "retrieval_mode": d["retrieval_mode"], "header_b": d["header_b"], "budget_tokens": budget}
    rows = [
        {**common, "chunker": "structure_handwritten", "chunk_size_tokens": None, "overlap_tokens": None},
        {**common, "chunker": "fixed_size", "chunk_size_tokens": fx["chunk_size_tokens"], "overlap_tokens": fx["overlap_tokens"]},
    ]
    return [{"setting_id": make_setting_id(r), **r} for r in rows]


class Service:
    def __init__(self, config_dir: Path | None = None, butir_dir: Path | None = None, tokenizer: Any = None):
        self.config_dir = config_dir
        self.butir_dir = butir_dir or (config.REPO_ROOT / "data" / "butir")
        self.tokenizer = tokenizer
        self._lock = threading.Lock()
        self._docs: dict[str, CorpusDoc] = {}
        self._chunks: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def cfg(self, name: str) -> dict[str, Any]:
        return config.load(name, self.config_dir)

    def doc(self, doc_id: str) -> CorpusDoc:
        with self._lock:
            if doc_id not in self._docs:
                try:
                    self._docs[doc_id] = load_corpus(doc_id, config_dir=self.config_dir)
                except CorpusError as exc:
                    if "not listed" in str(exc):
                        raise ApiError(404, "not_found", f"Unknown doc_id {doc_id!r}.") from None
                    raise ApiError(422, "validation_failed", f"Corpus could not be loaded: {exc}") from None
            return self._docs[doc_id]

    def settings(self, family: str, budget_tokens: int | None = None) -> list[dict[str, Any]]:
        return build_settings(family, self.cfg("retrieval"), self.cfg("grid"), budget_tokens)

    def items(self, family: str) -> list[dict[str, Any]]:
        if family != "uupt":
            return []
        files = sorted(((int(m.group(1)), p) for p in self.butir_dir.glob("uupt.v*.jsonl") if (m := _ITEM_FILE.match(p.name))))
        if not files:
            return []
        out: list[dict[str, Any]] = []
        for ln, line in enumerate(files[-1][1].read_bytes().decode("utf-8").split("\n"), 1):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    raise ApiError(422, "validation_failed", f"Item file {files[-1][1].name} line {ln} is not valid JSON.") from None
        return out

    def chunks(self, doc: CorpusDoc, setting: dict[str, Any]) -> list[dict[str, Any]]:
        key = (doc.doc_id, setting["setting_id"])
        with self._lock:
            hit = self._chunks.get(key)
        if hit is not None:
            return hit
        try:
            res = [c.to_dict() for c in chunk_document(doc, setting, tokenizer=self.tokenizer, retrieval_cfg=self.cfg("retrieval"), grid_cfg=self.cfg("grid"))]
        except ChunkOffsetError as exc:
            raise ApiError(422, "validation_failed", f"Chunk offsets do not match source text: {exc}") from None
        with self._lock:
            self._chunks[key] = res
        return res


def _check_family(family: str) -> None:
    if family not in FAMILIES:
        raise ApiError(400, "invalid_request", f"family must be one of {list(FAMILIES)}.")


def create_app(service: Service | None = None) -> FastAPI:
    svc = service or Service()
    app = FastAPI(title="LexRAGLab", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "invalid_request"}.get(exc.status_code, "invalid_request")
        return JSONResponse({"error": {"code": code, "message": "Not found." if exc.status_code == 404 else "Request not allowed."}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": {"code": "invalid_request", "message": "Invalid request parameters."}}, status_code=400)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"error": {"code": "internal_error", "message": "Unexpected server error."}}, status_code=500)

    @app.get("/api/families/{family}/docs/{doc_id}")
    def get_doc(family: str, doc_id: str, setting_id: str | None = None) -> dict[str, Any]:
        """R4: teks bersih dan potongan untuk satu setting. Tanpa `setting_id`: `chunks = null`."""
        _check_family(family)
        if family != "uupt":
            raise ApiError(404, "not_found", f"Unknown doc_id {doc_id!r} for family {family!r}.")
        doc = svc.doc(doc_id)
        chunks = None
        if setting_id is not None:
            setting = next((s for s in svc.settings(family) if s["setting_id"] == setting_id), None)
            if setting is None:
                raise ApiError(404, "not_found", f"Unknown setting_id {setting_id[:16]!r}.")
            chunks = svc.chunks(doc, setting)
        return {"doc_id": doc.doc_id, "text": doc.text, "chunks": chunks, "headers": None}

    @app.get("/api/families/{family}/snapshot")
    def get_snapshot(family: str, budget_tokens: int | None = None) -> dict[str, Any]:
        """R3 (bagian M1.1): corpus, items, settings. Bidang lain null atau kosong (API.md §4)."""
        _check_family(family)
        retrieval_cfg, grid_cfg = svc.cfg("retrieval"), svc.cfg("grid")
        budget = budget_tokens if budget_tokens is not None else grid_cfg["budget"]["default_tokens"]
        corpus: list[dict[str, Any]] = []
        if family == "uupt":
            d = svc.doc("uupt-40-2007")
            corpus = [{k: getattr(d, k) for k in ("doc_id", "family", "title", "path", "sha256", "clean_sha256", "loader_rules_version",
                                                   "char_count", "tokens_local", "tokens_endpoint", "calibration_ratio", "sections", "annotations")}]
        items = svc.items(family)
        clean = {c["doc_id"]: c["clean_sha256"] for c in corpus}
        for it in items:
            if clean.get(it.get("doc_id")) != it.get("clean_sha256"):
                raise ApiError(409, "hash_mismatch", f"Item {it.get('id')!r} was written against a different clean text than the loaded corpus.")
        cfgs = {n: svc.cfg(n) for n in ("grid", "retrieval", "corpus", "tokenizer")}
        return {
            "family": family, "budget_tokens": budget, "replay": False, "config_hash": config.config_hash(cfgs),
            "corpus": corpus, "items": items, "split": None,
            "items_summary": {"n_items": len(items), "by_origin": dict(Counter(i.get("origin") for i in items)),
                              "by_mode": dict(Counter(i.get("mode") for i in items)), "by_split": None, "control_in_held_out": None},
            "settings": svc.settings(family, budget) if family == "uupt" else [],
            "grid": None, "metrics": [], "quality": [], "schemas": [], "schema_diff": None,
            "proposals": [], "answers": [], "answers_summary": [], "runs_summary": None,
        }

    return app
