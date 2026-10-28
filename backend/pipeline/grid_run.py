"""Run grid nyata (M1.4 + M1.5): ekspansi G6a ke setting yang tersedia, split, pipeline, frontier, pilihan profil, mutu.

CLI: `uv run python -m backend.pipeline.grid_run [--family uupt|akta]`. Keluarga akta (H-086): retrieval per akta butir,
agregasi rata-rata per butir lintas akta, tanpa split dan tanpa pemilihan profil (H-054). Hasil di `runs/grid/<kunci>.json`
(amplop: RunRecord §12 + metrik per butir + titik + frontier + pilihan + mutu). Kunci sama = nol hitung.
Tanpa Model API; `cost_usd_micros = 0`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from backend import config, gpulock
from backend.chunking import boundary_diff, chunk_document, schema_identity
from backend.grid.expand import expand_grid
from backend.grid.headers import SCOPES, DirHeaderStore, HeaderBinding, header_store_dir
from backend.grid.runner import GridError, grid_cache_key, run_grid
from backend.grid.schemas import SchemaBinding, bind_schema_versions, is_approved
from backend.grid.split import SplitError, ensure_split, load_latest_split_record, make_split
from backend.grid.types import (MULTI_DOC_FAMILIES, NO_SPLIT_FAMILY, GridItem, Setting, SplitRecord, canonical_json,
                                family_corpus_hash, item_set_hash, metrics_to_cache)
from backend.metrics.run_record import run_record_parts
from backend.pipeline.multi import MultiDocPipeline
from backend.proposal.item import item_mode_problem
from backend.pipeline.pipeline import Pipeline, unavailable_reason
from backend.quality.aggregate import quality_metrics
from backend.quality.types import ChunkSpan, QualityDoc
from backend.retrieval.dense import CACHE_DIR, Encoder, embedder_info, encoder_from_config
from backend.spark.runrecord import RunRecord

RECALL_ITEM_SCOPES = ("all", "tune", "held_out")
CONFIGS = ("grid", "retrieval", "tokenizer", "corpus")
UNIT_MAP_CONFIG = "akta_unitmap"  # H-090: unit_map_version + aturan Recall@K akta; berkas terpisah agar hash UU PT tidak bergeser
UNIT_MAP_FAMILY = "akta"
FAMILY_CONFIGS = {"akta": ("corpus_akta", UNIT_MAP_CONFIG)}  # config tambahan yang ikut config_hash keluarga itu saja (UU PT tetap)
GRID_FAMILIES = ("uupt", *MULTI_DOC_FAMILIES)
_ITEM_FILE = re.compile(r"^(\w+)\.v(\d+)\.jsonl$")


class GridRunError(Exception):
    """Prasyarat run grid tidak terpenuhi (butir, split)."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- butir ----------
def load_items(family: str, butir_dir: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Butir versi terbaru `<family>.vN.jsonl` (BACA SAJA). Mengembalikan (butir, nama berkas)."""
    files = sorted(((int(m.group(2)), p) for p in Path(butir_dir).glob(f"{family}.v*.jsonl") if (m := _ITEM_FILE.match(p.name))))
    if not files:
        return [], None
    out = []
    for ln, line in enumerate(files[-1][1].read_bytes().decode("utf-8").split("\n"), 1):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                raise GridRunError(f"item file {files[-1][1].name} line {ln} is not valid JSON") from None
            bad = item_mode_problem(row) if isinstance(row, dict) and "mode" in row else None  # H-092: enum Item.mode, tolak
            if bad:
                raise GridRunError(f"item file {files[-1][1].name} line {ln} is invalid: {bad}")
            out.append(row)
    return out, files[-1][1].name


def to_grid_items(items: list[dict[str, Any]]) -> list[GridItem]:
    """`doc_id` hanya diisi untuk keluarga multi-dokumen (H-086); UU PT tetap "" agar `item_set_hash` tak berubah."""
    return [GridItem(id=i["id"], family=i["family"], origin=i["origin"], mode=i["mode"], clean_sha256=i["clean_sha256"],
                     gold_spans=tuple(sorted((int(g["start"]), int(g["end"])) for g in i.get("gold_spans", []))),
                     query=i["query"], doc_id=str(i.get("doc_id") or "") if i["family"] in MULTI_DOC_FAMILIES else "")
            for i in items]


def check_items_against_docs(family: str, raw: list[dict[str, Any]], *, doc: Any = None, docs: Any = None) -> None:
    """Satu dokumen: semua butir ditulis atas teks bersih `doc`. Multi-dokumen (H-086): tiap butir merujuk `doc_id` yang ada
    di korpus keluarga dan `clean_sha256`-nya sama dengan teks bersih dokumen itu; id butir unik lintas dokumen."""
    if family not in MULTI_DOC_FAMILIES:
        for it in raw:
            if it.get("clean_sha256") != doc.clean_sha256:
                raise GridRunError(f"item {it.get('id')!r} was written against a different clean text than the loaded corpus")
        return
    by_doc = {d.doc_id: d for d in docs}
    seen: set[Any] = set()
    for it in raw:
        iid, did = it.get("id"), it.get("doc_id")
        if iid in seen:
            raise GridRunError(f"duplicate item id {iid!r} in the {family} items")
        seen.add(iid)
        if it.get("family") != family:
            raise GridRunError(f"item {iid!r} has family {it.get('family')!r}, but it is in the {family} items")
        d = by_doc.get(did)
        if d is None:
            raise GridRunError(f"item {iid!r} refers to doc_id {did!r}, which is not in the {family} corpus")
        if it.get("clean_sha256") != d.clean_sha256:
            raise GridRunError(f"item {iid!r} was written against a different clean text than document {did!r}")


# ---------- rencana ----------
@dataclass
class Plan:
    family: str
    cfgs: dict[str, dict[str, Any]]
    config_hash: str
    headers: HeaderBinding | None
    schemas: SchemaBinding | None
    settings: list[Setting]  # semua hasil ekspansi (structure_schema ber-versi aktif konkret bila ada skema)
    runnable: list[Setting]
    skipped: list[dict[str, Any]]
    items: list[GridItem]
    item_file: str | None
    split: SplitRecord | None
    key: str | None
    corpus_key: str = ""  # komponen korpus kunci cache: `clean_sha256` (satu dokumen) atau `family_corpus_hash` (H-086)


def pipeline_config_hash(cfgs: dict[str, dict[str, Any]], tok_info: Any, headers: HeaderBinding | None = None,
                         schema_a: list[dict[str, Any]] | None = None, unit_map: dict[str, Any] | None = None) -> str:
    """Hash konfigurasi run. Dengan header B (A10): hash isi store header, granularitas, `prompt_hash` B, model, dan
    `header_b.scope` ikut; `run_id` B tidak. Dengan skema A (M3.4): versi, hash isi, dan sumber tiap skema yang dipakai
    setting `structure_schema` yang bisa jalan ikut (`schema_a` kosong/None = hash sama seperti sebelum M3.4).
    `unit_map` (H-090, hanya akta): identitas skema AKTIF (peta unit semua setting) + `unit_map_version`; None = tak berubah."""
    parts: dict[str, Any] = {**cfgs, "_tokenizer_info": {"name": tok_info.name, "version": tok_info.version}}
    if headers is not None:
        parts["_header_b"] = headers.identity()
    if schema_a:
        parts["_schema_a"] = schema_a
    if unit_map is not None:
        parts["_unit_map"] = unit_map
    return config.config_hash(parts)


def load_header_binding(*, runs_dir: Path, config_dir: Path | None = None, headers_dir: Path | None = None,
                        family: str = "uupt") -> HeaderBinding:
    """Binding (store per keluarga: `header_store_dir`, W63) dari `config/header_b` (granularity, scope, max_header_tokens) + `prompts/b` + `config/model` + `runs/`."""
    from backend.header_b.prompt import load_prompt

    hc = config.load("header_b", config_dir)
    scope = hc.get("scope", "frontier_only")
    if scope not in SCOPES:
        raise GridRunError(f"config/header_b: scope must be one of {list(SCOPES)}, got {scope!r}")
    if hc.get("granularity") not in ("pasal", "ayat"):
        raise GridRunError("config/header_b: granularity must be 'pasal' or 'ayat'")
    prompt = load_prompt(int(hc["max_header_tokens"]), hc.get("prompt_version"))  # H-079: versi dari config, sama dengan CLI B
    mc = config.load("model", config_dir)
    store = DirHeaderStore(headers_dir or header_store_dir(runs_dir, family), prompt.prompt_hash, runs_dir)
    return HeaderBinding(store, hc["granularity"], scope, prompt.prompt_hash, mc["profiles"][mc["default_profile"]]["model"])


def schema_identities(settings: list[Setting], schemas: SchemaBinding | None) -> list[dict[str, Any]]:
    """Identitas (versi + hash isi + sumber) skema yang dipakai `settings`, urut menurut versi; kosong bila tak ada."""
    if schemas is None:
        return []
    recs: dict[int, Any] = {}
    for s in settings:
        rec = schemas.resolve(s.schema_version) if s.chunker == "structure_schema" else None
        if rec is not None:
            recs[rec["schema_version"]] = rec
    return [{**schema_identity(rec), "source": rec.get("source")} for _, rec in sorted(recs.items())]


def schema_report(pipe: Pipeline, executed: list[Setting], schemas: SchemaBinding | None) -> dict[str, Any]:
    """Bagian amplop skema A (M3.4). `schemas_used`: identitas + `schema_approved` tiap versi yang dijalankan;
    `schema_approved`: semuanya disetujui (None bila tak ada skema dipakai); `boundary_diff`: per versi skema, selisih
    batas terhadap `structure_handwritten` per section. Selisih ada di amplop grid (bukan berkas `runs/` terpisah)
    agar ikut kunci cache dan hash config yang sama."""
    used: dict[int, Setting] = {}
    for s in executed:
        if s.chunker == "structure_schema" and s.schema_version is not None:
            used.setdefault(s.schema_version, s)
    if not used or schemas is None:
        return {"schemas_used": [], "schema_approved": None, "boundary_diff": {}}
    scope = list(pipe.rcfg["scope_sections"])
    multi = isinstance(pipe, MultiDocPipeline)
    pipes = _doc_pipes(pipe)
    hands = {p.doc.doc_id: chunk_document(p.doc, {"chunker": "structure_handwritten"}, tokenizer=p.tok, retrieval_cfg=p.rcfg)
             for p in pipes}
    desc, diffs = [], {}
    for v, s in sorted(used.items()):
        rec = schemas.resolve(v)
        assert rec is not None
        desc.append(schemas.describe(rec))
        per_doc = {p.doc.doc_id: boundary_diff(p.doc, hands[p.doc.doc_id], p.chunk_set(s).chunks, sections=scope) for p in pipes}
        diffs[str(v)] = per_doc if multi else per_doc[pipes[0].doc.doc_id]  # multi-dokumen: per doc_id (H-086)
    return {"schemas_used": desc, "schema_approved": all(d["schema_approved"] for d in desc), "boundary_diff": diffs}


def unit_map_identity(cfgs: dict[str, dict[str, Any]], schemas: SchemaBinding | None) -> dict[str, Any]:
    """Komponen kunci grid akta (H-090 P2): skema A aktif (versi, hash isi, sumber; None bila tak ada) dan `unit_map_version`,
    walau grid tanpa setting `structure_schema` (peta unit berlaku untuk semua setting)."""
    return {"schema": schemas.identity() if schemas is not None else None, "unit_map_version": cfgs[UNIT_MAP_CONFIG]["unit_map_version"]}


def unit_map_kind(pipe: Any) -> tuple[str, list[str]]:
    """("schema" | "fallback", doc_id dokumen akta yang memakai peta cadangan). Satu dokumen cadangan = seluruh keluarga bertanda."""
    fb = sorted(p.doc.doc_id for p in _doc_pipes(pipe) if p.akta_unit_map()[1] == "fallback")
    return ("fallback" if fb else "schema"), fb


def unit_map_report(pipe: Any, schemas: SchemaBinding | None, unit_cfg: dict[str, Any], metrics: list[Any]) -> dict[str, Any]:
    """Blok amplop `unit_map` (H-090 P1, P7, P10; hanya akta): identitas skema aktif + persetujuan, `unit_map_version`, tanda
    peta cadangan, `recall_unit`, dan hitungan butir. `metrics` = ItemMetrics satu setting (peta sama untuk semua setting)."""
    act = schemas.active() if schemas is not None else None
    desc = schemas.describe(act) if act is not None and schemas is not None else None
    kind, fb = unit_map_kind(pipe)
    return {"unit_map_version": unit_cfg["unit_map_version"],
            "schema_version": desc["schema_version"] if desc else None, "schema_hash": desc["schema_hash"] if desc else None,
            "source": desc["source"] if desc else None, "schema_approved": desc["schema_approved"] if desc else None,
            "kind": kind, "fallback_doc_ids": fb, "recall_unit": unit_cfg["recall"]["unit"],
            "n_items_recall_null": sum(1 for m in metrics if m.gold_chars > 0 and m.parts_total == 0),
            "n_items_gold_partly_outside": sum(1 for m in metrics if m.parts_total > 0 and (m.gold_chars_outside_units or 0) > 0)}


def make_plan(family: str, *, doc: Any = None, tokenizer: Any, butir_dir: Path, runs_dir: Path, config_dir: Path | None = None,
              create_split: bool, headers: HeaderBinding | None = None, schemas: SchemaBinding | None = None,
              docs: Any = None) -> Plan:
    """Rencana run. `create_split=False` (R3): split dihitung murni dari record tersimpan, tanpa menulis; tanpa record -> split None.
    Keluarga multi-dokumen (H-086): `docs` = semua dokumen keluarga; tanpa split (H-054), kunci ber-`split_version` None."""
    multi = family in MULTI_DOC_FAMILIES
    if multi and not docs:
        raise GridRunError(f"family {family!r} needs its document list")
    if not multi and doc is None:
        raise GridRunError(f"family {family!r} needs its document")
    cfgs = {n: config.load(n, config_dir) for n in (*CONFIGS, *FAMILY_CONFIGS.get(family, ()))}
    settings = bind_schema_versions(expand_grid(cfgs["grid"], family), schemas)
    hb = headers is not None
    runnable = [s for s in settings if unavailable_reason(s, headers=hb, schemas=schemas) is None]
    skipped = [{"setting_id": s.setting_id, "chunker": s.chunker, "retrieval_mode": s.retrieval_mode, "header_b": s.header_b,
                "budget_tokens": s.budget_tokens, "reason": unavailable_reason(s, headers=hb, schemas=schemas)}
               for s in settings if unavailable_reason(s, headers=hb, schemas=schemas)]
    raw, fname = load_items(family, butir_dir)
    check_items_against_docs(family, raw, doc=doc, docs=docs)
    items = to_grid_items(raw)
    g = cfgs["grid"]["split"]
    split: SplitRecord | None = None
    if items and family != NO_SPLIT_FAMILY:
        kw = dict(family=family, seed=g["seed"], held_out_ratio=g["held_out_ratio"], min_control=g["min_control_in_held_out"],
                  strata=tuple(g["strata"]))
        splits_dir = Path(runs_dir) / "split"
        try:
            if create_split:
                split = ensure_split(items, directory=splits_dir, **kw)
            else:
                prev = load_latest_split_record(splits_dir, family)
                split = make_split(items, previous=prev, **kw) if prev is not None else None
        except SplitError as exc:
            if create_split:
                raise GridRunError(str(exc)) from None
    chash = pipeline_config_hash(cfgs, tokenizer.info, headers, schema_identities(runnable, schemas),
                                 unit_map_identity(cfgs, schemas) if family == UNIT_MAP_FAMILY else None)
    corpus_key = family_corpus_hash(docs) if multi else doc.clean_sha256
    if split:
        key: str | None = grid_cache_key(corpus_key, chash, item_set_hash(items), split.split_version)
    elif family == NO_SPLIT_FAMILY and items:
        key = grid_cache_key(corpus_key, chash, item_set_hash(items), None)
    else:
        key = None
    return Plan(family, cfgs, chash, headers, schemas, settings, runnable, skipped, items, fname, split, key, corpus_key)


# ---------- penyimpanan amplop ----------
class RunFileStore:
    """`runs/grid/<kunci>.json`: amplop. Memenuhi protokol `GridCache` runner (metrik per butir) dan menyimpan sisanya."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def read(self, key: str) -> dict[str, Any] | None:
        p = self.path(key)
        if not p.is_file():
            return None
        try:
            d = json.loads(p.read_bytes().decode("utf-8"))
        except (OSError, ValueError):
            return None
        return d if isinstance(d, dict) else None

    def write(self, key: str, envelope: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        p = self.path(key)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(canonical_json(envelope) + "\n")
        os.replace(tmp, p)

    def get(self, key: str):
        d = self.read(key)
        return d.get("metrics") if d else None

    def put(self, key: str, value) -> None:
        self.write(key, {"metrics": value})


# ---------- serialisasi ----------
def _exact(x: Fraction | None) -> str | None:
    return None if x is None else f"{x.numerator}/{x.denominator}"


def point_dict(p: Any) -> dict[str, Any]:
    d = p.to_dict()
    d["exact"] = {"mean_span_recall": _exact(p.mean_span_recall), "mean_token_precision": _exact(p.mean_token_precision),
                  "mrr": _exact(p.mrr), "mean_retrieved_tokens": _exact(p.mean_retrieved_tokens)}
    d["n_gold"] = p.n_gold
    return d


def selection_dict(sel: Any) -> dict[str, Any]:
    return {"family": sel.family, "budget_tokens": sel.budget_tokens, "setting_id": sel.setting_id,
            "tune_point": point_dict(sel.tune_point),
            "held_out_point": point_dict(sel.held_out_point) if sel.held_out_point is not None else None}


# ---------- mutu (M1.5) ----------
def _doc_pipes(pipe: Any) -> list[Pipeline]:
    """Pipeline satu-dokumen di balik `pipe` (urut `doc_id` untuk multi-dokumen)."""
    return list(pipe.pipes.values()) if isinstance(pipe, MultiDocPipeline) else [pipe]


def _quality_doc(p: Pipeline, s: Setting) -> QualityDoc:
    cs = p.chunk_set(s)
    units = cs.amap.in_sections(set(p.rcfg["scope_sections"]))
    bounds = frozenset({0, len(p.doc.text)} | {u.start for u in units} | {u.end for u in units})
    return QualityDoc(p.doc.text, tuple(ChunkSpan(c.start, c.end) for c in cs.chunks), bounds)


def quality_for(pipe: Pipeline, s: Setting, metrics: list[Any], unit_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """QualityMetrics satu setting: potongan seluruh korpus + Recall@K per butir dari ItemMetrics (fungsi produksi M1.2).
    `unit_cfg` (config akta_unitmap, hanya akta; I-65/H-090): cakupan butir dan label dari `[recall]`, plus `recall_unit` dan
    `unit_map_kind`; None = aturan `[quality].recall_items` (UU PT, tidak berubah)."""
    q = pipe.rcfg["quality"]
    qdocs = [_quality_doc(p, s) for p in _doc_pipes(pipe)]  # multi-dokumen: hitungan entitas/batas digabung lintas dokumen
    scope = q.get("recall_items", "all") if unit_cfg is None else unit_cfg["recall"]["items"]
    if scope not in RECALL_ITEM_SCOPES:
        raise GridRunError(f"[quality].recall_items (akta: {UNIT_MAP_CONFIG} [recall].items) must be one of {list(RECALL_ITEM_SCOPES)}, got {scope!r}")
    used = [x for x in metrics if scope == "all" or x.split == scope]
    m = quality_metrics(s.setting_id, qdocs, pipe.k, [x.recall_at_k for x in used], q["entity_patterns"], q["abbreviations"])
    d = asdict(m)
    d["items_scope"] = scope if unit_cfg is None else unit_cfg["recall"]["label"]  # label cakupan butir Recall@K (I-39; akta: "transfer")
    if unit_cfg is not None:
        d["recall_unit"] = unit_cfg["recall"]["unit"]
        d["unit_map_kind"] = unit_map_kind(pipe)[0]
    d["recall_n_items"] = sum(1 for x in used if x.recall_at_k is not None)
    return d


def baseline_for(settings: list[Setting], selected: Setting, base_cfg: dict[str, Any]) -> Setting | None:
    """Pembanding C (H-036): `fixed_size` dari `[baseline]` dengan mode retrieval dan anggaran profil terpilih."""
    for s in settings:
        if (s.chunker == base_cfg["chunker"] and s.chunk_size_tokens == base_cfg["chunk_size_tokens"]
                and s.overlap_tokens == base_cfg["overlap_tokens"] and s.retrieval_mode == selected.retrieval_mode
                and s.budget_tokens == selected.budget_tokens and not s.header_b):
            return s
    return None


# ---------- run ----------
@dataclass
class GridResult:
    key: str
    cache_hit: bool
    record: dict[str, Any]
    envelope: dict[str, Any]
    path: Path


def run_family_grid(family: str, *, doc: Any = None, tokenizer: Any, runs_dir: Path, butir_dir: Path, config_dir: Path | None = None,
                    encoder: Encoder | None = None, encoder_factory: Callable[[], Encoder] | None = None,
                    embed_cache_dir: Path | None = None, pipeline_out: list | None = None,
                    log: Callable[[str], None] = lambda _m: None, headers: HeaderBinding | None = None,
                    schemas: SchemaBinding | None = None, docs: Any = None,
                    gpu_lock: bool = False, gpu_pid_alive: Callable[[int], bool] | None = None) -> GridResult:
    """Jalankan (atau baca dari cache) grid satu keluarga. Tanpa Model API.
    Keluarga multi-dokumen (akta, H-086): `docs` = semua dokumen keluarga; retrieval per dokumen butir; tanpa split dan tanpa
    pemilihan profil (H-054).
    `gpu_lock=True` (CLI `main`): ambil kunci GPU eksklusif `runs/locks/gpu.lock` (holder `embedding`) bila ada setting dense/hybrid
    yang akan menjalankan encoder (H-101 S16). Proses berumur panjang (backend API) memakai bawaan False dan tidak memegang kunci."""
    t0 = time.perf_counter()
    if family not in GRID_FAMILIES:
        raise GridRunError(f"grid for family {family!r} is not available")
    multi = family in MULTI_DOC_FAMILIES
    plan = make_plan(family, doc=doc, tokenizer=tokenizer, butir_dir=butir_dir, runs_dir=runs_dir, config_dir=config_dir, create_split=True,
                     headers=headers, schemas=schemas, docs=docs)
    if not plan.items:
        if multi:
            raise GridRunError(f"no approved {family} items: no {family}.v*.jsonl item file in the item directory")
        raise GridRunError(f"no items for family {family!r}")
    assert plan.key is not None and (plan.split is not None or family == NO_SPLIT_FAMILY)
    store = RunFileStore(Path(runs_dir) / "grid")
    existing = store.read(plan.key)
    if existing and existing.get("record"):
        rec = dict(existing["record"])
        rec["status"] = "cached"
        log(f"cache hit {plan.key[:16]}")
        return GridResult(plan.key, True, rec, existing, store.path(plan.key))

    lock = None
    if gpu_lock and any(s.retrieval_mode != "bm25" for s in plan.runnable):  # H-101 S16 (g): encoder bge-m3 dimuat -> kunci GPU eksklusif
        lock = gpulock.acquire(runs_dir, "embedding", **({"pid_alive": gpu_pid_alive} if gpu_pid_alive is not None else {}))
    try:
        g, r = plan.cfgs["grid"], plan.cfgs["retrieval"]
        pkw = dict(tokenizer=tokenizer, retrieval_cfg=r, grid_cfg=g, encoder=encoder, cache_dir=embed_cache_dir,
                   encoder_factory=encoder_factory or (lambda: encoder_from_config(r)), headers=headers, schemas=schemas)
        pipe: Any = MultiDocPipeline(docs, **pkw) if multi else Pipeline(doc, **pkw)
        if pipeline_out is not None:
            pipeline_out.append(pipe)
        log(f"run {len(plan.runnable)} settings, skipped {len(plan.skipped)}, items {len(plan.items)}")
        for sid in schema_identities(plan.runnable, schemas):
            log(f"schema A: v{sid['schema_version']} {sid['schema_hash'][:12]} source={sid['source']} "
                f"approved={is_approved(schemas.resolve(sid['schema_version']))}")  # type: ignore[union-attr]
        if headers is not None:
            log(f"header B: scope={headers.scope} granularity={headers.granularity}")
        res = run_grid(settings=plan.runnable, items=plan.items, pipeline=pipe, cache=store, clean_sha256=plan.corpus_key,
                       config_hash=plan.config_hash, split_record=plan.split, simplicity=g["simplicity"], family=family,
                       header_scope=headers.scope if headers is not None else "all")
        assert res.grid_run_id == plan.key
        by_id = {s.setting_id: s for s in plan.runnable}
        per_setting: dict[str, list[Any]] = {}
        for m in res.metrics:
            per_setting.setdefault(m.setting_id, []).append(m)
        executed = [s for s in plan.runnable if s.setting_id in per_setting]  # tanpa kembaran di luar scope dan setting gagal
        ucfg = plan.cfgs.get(UNIT_MAP_CONFIG) if family == UNIT_MAP_FAMILY else None
        quality = [quality_for(pipe, s, per_setting[s.setting_id], ucfg) for s in executed]
        q_by_id = {q["setting_id"]: q for q in quality}
        comparison = []
        for budget, sel in sorted(res.selections.items()):
            chosen = by_id[sel.setting_id]
            base = baseline_for(plan.runnable, chosen, g["baseline"])
            comparison.append({"budget_tokens": budget, "selected_setting_id": chosen.setting_id,
                               "baseline_setting_id": base.setting_id if base else None,
                               "selected": q_by_id[chosen.setting_id], "baseline": q_by_id[base.setting_id] if base else None})

        enc = pipe.encoder if pipe.encoder_used else None
        trunc = pipe.n_truncated()
        emb = embedder_info(enc, sum(trunc.values())) if enc is not None else None
        host = config.load("model", config_dir)["host"]
        device = ("cuda:0" if enc.device == "cuda" else enc.device) if enc is not None else "cpu"
        parts = run_record_parts(tokenizer.info, g["packing"]["rule"])
        if multi:  # H-086: hash korpus keluarga (doc_id + clean_sha256 terurut) menggantikan teks bersih tunggal
            corpus_hash, clean, rules = plan.corpus_key, plan.corpus_key, ",".join(sorted({d.loader_rules_version for d in docs}))
        else:
            corpus_hash, clean, rules = config.config_hash({"docs": [doc.sha256]}), doc.clean_sha256, doc.loader_rules_version
        record = RunRecord(
            run_id=f"grid-{plan.key[:16]}", kind="grid", created_at=utc_now(), cache_key=plan.key,
            corpus_hash=corpus_hash, config_hash=plan.config_hash,
            clean_sha256=clean, loader_rules_version=rules, prompt_version=None, prompt_hash=None,
            model=None, effort=None, tokenizer=parts["tokenizer"], embedder=emb, packing=parts["packing"],
            usage_input_tokens=None, usage_cached_tokens=None, usage_output_tokens=None, cost_usd_micros=0,
            projected_cost_usd_micros=None, latency_ms=int((time.perf_counter() - t0) * 1000), host=host, device=device,
            provider=None, quantization=None, status="ok", error=None,
            failed_settings=[f.to_dict() for f in res.failed_settings]).to_dict()  # DATA-CONTRACTS §12, H-069
        envelope = {
            "key": plan.key, "family": family, "record": record,
            "item_file": plan.item_file, "n_items": len(plan.items),
            "split": plan.split.to_dict() if plan.split is not None else None,  # akta: tanpa split (H-054)
            **({"docs": [{"doc_id": d.doc_id, "clean_sha256": d.clean_sha256, "loader_rules_version": d.loader_rules_version,
                          "n_items": sum(1 for i in plan.items if i.doc_id == d.doc_id)} for d in sorted(docs, key=lambda d: d.doc_id)]}
               if multi else {}),
            "settings_run": [asdict(s) for s in executed], "skipped": plan.skipped,
            "n_truncated_by_chunker": trunc,
            "metrics": [metrics_to_cache(m) for m in res.metrics],
            "points": [{**point_dict(p), "header_b": by_id[p.setting_id].header_b} for p in res.points],  # deret on/off (U2)
            "frontiers": [{"family": f.family, "split": f.split, "budget_tokens": f.budget_tokens, "point_ids": list(f.point_ids),
                           "grid_run_id": f.grid_run_id} for f in res.frontiers],
            "selections": {str(b): selection_dict(s) for b, s in sorted(res.selections.items())},
            "quality": quality, "quality_comparison": comparison,
            **schema_report(pipe, executed, schemas),
            **({"unit_map": unit_map_report(pipe, schemas, ucfg, per_setting[executed[0].setting_id] if executed else []),
                "recall_unit": ucfg["recall"]["unit"]} if ucfg is not None else {}),
        }
        store.write(plan.key, envelope)
        return GridResult(plan.key, False, record, envelope, store.path(plan.key))
    finally:
        if lock is not None:
            lock.release()


# ---------- CLI ----------
def _frac(d: dict[str, Any], f: str) -> str:
    v, e = d[f], d["exact"][f]
    return "n/a" if v is None else f"{e} = {v:.6f}"


def summarize(res: GridResult) -> list[str]:
    env = res.envelope
    out = [f"run {res.record['run_id']} status={res.record['status']} key={res.key}",
           f"path={res.path}", f"latency_ms={res.record['latency_ms']} host={res.record['host']} device={res.record['device']} "
           f"tokenizer={res.record['tokenizer']['name']} packing={res.record['packing']} embedder={res.record['embedder']}",
           f"settings run={len(env['settings_run'])} skipped={len(env['skipped'])} n_truncated_by_chunker={env['n_truncated_by_chunker']}"]
    for sk in sorted({(s['chunker'], s['header_b'], s['reason']) for s in env["skipped"]}, key=str):
        out.append(f"  skipped: chunker={sk[0]} header_b={sk[1]}: {sk[2]}")
    sp = env["split"]
    if sp is not None:
        tune = sum(1 for a in sp["assignments"] if a["split"] == "tune")
        out.append(f"split v{sp['split_version']} seed={sp['seed']} ratio={sp['held_out_ratio']}: tune={tune} held_out={len(sp['assignments']) - tune} "
                   f"control_in_held_out={sp['control_in_held_out']}")
    else:
        out.append("split: none (H-054); docs " + ", ".join(f"{d['doc_id']}={d['n_items']}" for d in env.get("docs", [])))
    want = "tune" if sp is not None else None
    by_id = {s["setting_id"]: s for s in env["settings_run"]}
    for f in env["frontiers"]:
        if f["split"] != want:
            continue
        out.append(f"frontier {want or 'all items'} budget={f['budget_tokens']}:")
        pts = {p["setting_id"]: p for p in env["points"] if p["split"] == want and p["budget_tokens"] == f["budget_tokens"]}
        for sid in f["point_ids"]:
            p, s = pts[sid], by_id[sid]
            out.append(f"  {sid[:12]} {s['chunker']}/{s['retrieval_mode']} header_b={'on' if s['header_b'] else 'off'}: span_recall {_frac(p, 'mean_span_recall')} "
                       f"mean_retrieved_tokens {_frac(p, 'mean_retrieved_tokens')}")
    for b, sel in env["selections"].items():
        s = by_id[sel["setting_id"]]
        out.append(f"selected budget={b}: {sel['setting_id'][:12]} {s['chunker']}/{s['retrieval_mode']} "
                   f"tune {_frac(sel['tune_point'], 'mean_span_recall')}"
                   + (f"; held_out {_frac(sel['held_out_point'], 'mean_span_recall')}" if sel["held_out_point"] else ""))
    for c in env["quality_comparison"]:
        for label in ("selected", "baseline"):
            q = c[label]
            out.append(f"quality budget={c['budget_tokens']} {label} {(c[label + '_setting_id'] or '')[:12]}: "
                       + (f"entity_preservation={q['entity_preservation']} boundary_coherence={q['boundary_coherence']} "
                          f"recall_at_k={q['recall_at_k']} k={q['k']} counts={q['counts']}" if q else "n/a"))
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="backend.pipeline.grid_run")
    ap.add_argument("--family", default="uupt")
    ap.add_argument("--runs-dir", type=Path, default=config.REPO_ROOT / "runs")
    ap.add_argument("--butir-dir", type=Path, default=config.REPO_ROOT / "data" / "butir")
    ap.add_argument("--with-headers", action="store_true",
                    help="sertakan kembaran header-on (store runs/headers, scope dari config/header_b); tanpa Model API")
    ap.add_argument("--with-schema", action="store_true",
                    help="aktifkan structure_schema dari skema A di runs/schemas/<family> (versi aktif; yang belum disetujui "
                         "ditandai di amplop); tanpa Model API")
    args = ap.parse_args(argv)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from backend.corpus import akta_entries, load_corpus
    from backend.tokenizer import get_tokenizer

    t0 = time.perf_counter()
    try:
        if args.family in MULTI_DOC_FAMILIES:
            ids = [i for i, e in akta_entries().items() if e.get("family", args.family) == args.family]
            dkw: dict[str, Any] = {"docs": [load_corpus(i) for i in ids]}
        else:
            dkw = {"doc": load_corpus()}
        res = run_family_grid(args.family, **dkw, tokenizer=get_tokenizer(), runs_dir=args.runs_dir,
                              butir_dir=args.butir_dir, embed_cache_dir=CACHE_DIR, log=lambda m: print(m, flush=True),
                              headers=load_header_binding(runs_dir=args.runs_dir, family=args.family) if args.with_headers else None,
                              schemas=SchemaBinding.from_store(args.runs_dir, args.family) if args.with_schema else None,
                              gpu_lock=True)
    except (GridRunError, GridError, gpulock.GpuLockError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in summarize(res):
        print(line)
    print(f"wall_seconds={time.perf_counter() - t0:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
