"""Lapisan layanan API: korpus, butir, setting, potongan, hasil grid tersimpan, retrieval per butir.

R3/R4 hanya membaca berkas dan cache (docs/API.md §5). Hanya W1 (`run_grid`) dan R5 (retrieval satu butir) menghitung.
Tanpa Model API.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from backend import config
from backend.api.errors import ApiError
from backend.chunking import ChunkOffsetError, chunk_document
from backend.config import ConfigError
from backend.corpus import CorpusDoc, CorpusError, load_corpus
from backend.grid.expand import expand_grid
from backend.grid.headers import GRANULARITY_DIRS, DirHeaderStore, HeaderBinding, HeaderError
from backend.grid.types import Setting, setting_content
from backend.pipeline.grid_run import (GridResult, GridRunError, Plan, RunFileStore, load_header_binding, load_items, make_plan,
                                       run_family_grid, to_grid_items)
from backend.pipeline.pipeline import Pipeline, SettingNotAvailable, unavailable_reason
from backend.retrieval.dense import CACHE_DIR, Encoder, encoder_from_config
from backend.tokenizer import get_tokenizer

FAMILIES = ("uupt", "akta")
log = logging.getLogger(__name__)
# Galat yang berarti config/prompt B tak terbaca atau cacat; selain ini (bug) dibiarkan naik.
_BINDING_UNREADABLE = (GridRunError, ConfigError, OSError, ValueError, KeyError, TypeError)


class Service:
    def __init__(self, config_dir: Path | None = None, butir_dir: Path | None = None, tokenizer: Any = None,
                 runs_dir: Path | None = None, encoder: Encoder | None = None,
                 encoder_factory: Callable[[], Encoder] | None = None, embed_cache_dir: Path | None = None):
        self.config_dir = config_dir
        self.butir_dir = butir_dir or (config.REPO_ROOT / "data" / "butir")
        self.tokenizer = tokenizer
        self.runs_dir = Path(runs_dir) if runs_dir is not None else config.REPO_ROOT / "runs"
        self._encoder, self._encoder_factory = encoder, encoder_factory
        self.embed_cache_dir = embed_cache_dir if embed_cache_dir is not None else CACHE_DIR
        self._lock = threading.RLock()
        self.compute_lock = threading.Lock()  # satu perhitungan berat (W1, R5) sekali jalan
        self._docs: dict[str, CorpusDoc] = {}
        self._chunks: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._pipeline: Pipeline | None = None
        self._pipeline_headers = False

    # --- dasar ---
    def cfg(self, name: str) -> dict[str, Any]:
        return config.load(name, self.config_dir)

    def tok(self) -> Any:
        return self.tokenizer or get_tokenizer()

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

    def items(self, family: str) -> list[dict[str, Any]]:
        if family != "uupt":
            return []
        try:
            return load_items(family, self.butir_dir)[0]
        except GridRunError as exc:
            raise ApiError(422, "validation_failed", str(exc)) from None

    # --- header B (M3.2) ---
    def header_binding(self) -> HeaderBinding | None:
        """Binding ke store header `runs/headers/` bila store itu punya header untuk `prompt_hash` B saat ini; selain itu None
        (perilaku M1: setting header-on tidak tersedia). Hanya membaca berkas; tanpa Spark."""
        if not (self.runs_dir / "headers").is_dir():
            return None
        try:
            hb = load_header_binding(runs_dir=self.runs_dir, config_dir=self.config_dir)
        except _BINDING_UNREADABLE as exc:  # config/prompt B tak terbaca: anggap tak ada store (dicatat, tanpa isi config)
            log.warning("header B binding unavailable: %s", type(exc).__name__)
            return None
        store = hb.store
        if isinstance(store, DirHeaderStore):
            has = any(next((store.headers_dir / g / store.prompt12).glob("*.json"), None) is not None for g in GRANULARITY_DIRS)
            if not has:
                return None
        return hb

    # --- setting ---
    def grid_settings(self, family: str) -> list[Setting]:
        """Semua setting hasil ekspansi `config/grid` (termasuk yang belum tersedia di M1)."""
        return expand_grid(self.cfg("grid"), family) if family == "uupt" else []

    def settings(self, family: str) -> list[dict[str, Any]]:
        return [{"setting_id": s.setting_id, **setting_content(s)} for s in self.grid_settings(family)]

    def find_setting(self, family: str, setting_id: str) -> Setting:
        s = next((x for x in self.grid_settings(family) if x.setting_id == setting_id), None)
        if s is None:
            raise ApiError(404, "not_found", f"Unknown setting_id {setting_id[:16]!r}.")
        reason = unavailable_reason(s, headers=self.header_binding() is not None)
        if reason:
            raise ApiError(422, "validation_failed", f"Setting is not available yet: {reason}.")
        return s

    def chunks(self, doc: CorpusDoc, setting: Setting) -> list[dict[str, Any]]:
        key = (doc.doc_id, setting.setting_id)
        with self._lock:
            hit = self._chunks.get(key)
        if hit is not None:
            return hit
        try:
            res = [c.to_dict() for c in chunk_document(doc, setting_content(setting), tokenizer=self.tokenizer,
                                                       retrieval_cfg=self.cfg("retrieval"), grid_cfg=self.cfg("grid"))]
        except ChunkOffsetError as exc:
            raise ApiError(422, "validation_failed", f"Chunk offsets do not match source text: {exc}") from None
        with self._lock:
            self._chunks[key] = res
        return res

    # --- hasil grid tersimpan (R3) ---
    def plan(self, family: str, *, create_split: bool = False, headers: HeaderBinding | None = None) -> Plan:
        doc = self.doc("uupt-40-2007")
        try:
            return make_plan(family, doc=doc, tokenizer=self.tok(), butir_dir=self.butir_dir, runs_dir=self.runs_dir,
                             config_dir=self.config_dir, create_split=create_split, headers=headers)
        except GridRunError as exc:
            raise ApiError(409, "hash_mismatch", str(exc)) from None

    def stored_grid(self, family: str) -> tuple[Plan | None, dict[str, Any] | None]:
        """(rencana, amplop tersimpan). Tanpa menjalankan apa pun dan tanpa menulis (R3)."""
        if family != "uupt":
            return None, None
        store = RunFileStore(self.runs_dir / "grid")
        hb = self.header_binding()
        if hb is not None:  # run dengan kembaran header-on punya kunci sendiri (config_hash memuat identitas store)
            hplan = self.plan(family, headers=hb)
            henv = store.read(hplan.key) if hplan.key is not None else None
            if henv and henv.get("record"):
                return hplan, henv
        plan = self.plan(family)
        if plan.key is None:
            return plan, None
        env = store.read(plan.key)
        return plan, (env if env and env.get("record") else None)

    # --- hitung (R5, W1) ---
    def _encoder_factory_or_default(self) -> Callable[[], Encoder]:
        if self._encoder is not None:
            return lambda: self._encoder  # type: ignore[return-value]
        return self._encoder_factory or (lambda: encoder_from_config(self.cfg("retrieval")))

    def pipeline(self) -> Pipeline:
        with self._lock:
            hb = self.header_binding()
            if self._pipeline is None or self._pipeline_headers != (hb is not None):
                self._pipeline_headers = hb is not None
                self._pipeline = Pipeline(self.doc("uupt-40-2007"), tokenizer=self.tok(), retrieval_cfg=self.cfg("retrieval"),
                                          grid_cfg=self.cfg("grid"), encoder_factory=self._encoder_factory_or_default(),
                                          cache_dir=self.embed_cache_dir, headers=hb)
            return self._pipeline

    def retrieval(self, family: str, setting_id: str, item_id: str) -> dict[str, Any]:
        if family != "uupt":
            raise ApiError(404, "not_found", f"No items for family {family!r}.")
        s = self.find_setting(family, setting_id)
        raw = next((i for i in self.items(family) if i.get("id") == item_id), None)
        if raw is None:
            raise ApiError(404, "not_found", f"Unknown item_id {item_id!r}.")
        item = to_grid_items([raw])[0]
        with self.compute_lock:
            try:
                r = self.pipeline().retrieve(s, item)
            except (SettingNotAvailable, HeaderError) as exc:
                raise ApiError(422, "validation_failed", str(exc)) from None
        return {"retrieved_chunk_ids": [p.chunk_id for p in r.packed], "ranks": [p.rank_in_c for p in r.packed],
                "scores": [r.scores[p.chunk_id] for p in r.packed], "packed_tokens": sum(p.cost for p in r.packed)}

    def run_grid(self, family: str, *, replay: bool = False) -> GridResult:
        if family != "uupt":
            raise ApiError(422, "validation_failed", f"Grid for family {family!r} is not available in M1.")
        with self.compute_lock:
            if replay:
                _plan, env = self.stored_grid(family)
                if env is None:
                    raise ApiError(409, "replay_no_stored_run", "No stored run for this request. Replay mode does not call the Model API.")
                rec = dict(env["record"])
                rec["status"] = "cached"
                return GridResult(env["key"], True, rec, env, RunFileStore(self.runs_dir / "grid").path(env["key"]))
            try:
                return run_family_grid(family, doc=self.doc("uupt-40-2007"), tokenizer=self.tok(), runs_dir=self.runs_dir,
                                       butir_dir=self.butir_dir, config_dir=self.config_dir, encoder=self._encoder,
                                       encoder_factory=self._encoder_factory, embed_cache_dir=self.embed_cache_dir, headers=self.header_binding())
            except GridRunError as exc:
                raise ApiError(422, "validation_failed", str(exc)) from None
