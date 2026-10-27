"""Run grid nyata (M1.4 + M1.5): ekspansi G6a ke setting yang tersedia, split, pipeline, frontier, pilihan profil, mutu.

CLI: `uv run python -m backend.pipeline.grid_run [--family uupt]`. Hasil di `runs/grid/<kunci>.json`
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

from backend import config
from backend.grid.expand import expand_grid
from backend.grid.headers import SCOPES, DirHeaderStore, HeaderBinding
from backend.grid.runner import GridError, grid_cache_key, run_grid
from backend.grid.split import SplitError, ensure_split, load_latest_split_record, make_split
from backend.grid.types import GridItem, Setting, SplitRecord, canonical_json, item_set_hash, metrics_to_cache
from backend.metrics.run_record import run_record_parts
from backend.pipeline.pipeline import Pipeline, unavailable_reason
from backend.quality.aggregate import quality_metrics
from backend.quality.types import ChunkSpan, QualityDoc
from backend.retrieval.dense import CACHE_DIR, Encoder, embedder_info, encoder_from_config
from backend.spark.runrecord import RunRecord

RECALL_ITEM_SCOPES = ("all", "tune", "held_out")
CONFIGS = ("grid", "retrieval", "tokenizer", "corpus")
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
                out.append(json.loads(line))
            except json.JSONDecodeError:
                raise GridRunError(f"item file {files[-1][1].name} line {ln} is not valid JSON") from None
    return out, files[-1][1].name


def to_grid_items(items: list[dict[str, Any]]) -> list[GridItem]:
    return [GridItem(id=i["id"], family=i["family"], origin=i["origin"], mode=i["mode"], clean_sha256=i["clean_sha256"],
                     gold_spans=tuple(sorted((int(g["start"]), int(g["end"])) for g in i.get("gold_spans", []))),
                     query=i["query"]) for i in items]


# ---------- rencana ----------
@dataclass
class Plan:
    family: str
    cfgs: dict[str, dict[str, Any]]
    config_hash: str
    headers: HeaderBinding | None
    settings: list[Setting]  # semua hasil ekspansi
    runnable: list[Setting]
    skipped: list[dict[str, Any]]
    items: list[GridItem]
    item_file: str | None
    split: SplitRecord | None
    key: str | None


def pipeline_config_hash(cfgs: dict[str, dict[str, Any]], tok_info: Any, headers: HeaderBinding | None = None) -> str:
    """Hash konfigurasi run. Dengan header B (A10): hash isi store header, granularitas, `prompt_hash` B, model, dan
    `header_b.scope` ikut; `run_id` B tidak. Tanpa binding hash sama seperti sebelum M3.2."""
    parts: dict[str, Any] = {**cfgs, "_tokenizer_info": {"name": tok_info.name, "version": tok_info.version}}
    if headers is not None:
        parts["_header_b"] = headers.identity()
    return config.config_hash(parts)


def load_header_binding(*, runs_dir: Path, config_dir: Path | None = None, headers_dir: Path | None = None) -> HeaderBinding:
    """Binding dari `config/header_b` (granularity, scope, max_header_tokens) + `prompts/b` + `config/model` + `runs/`."""
    from backend.header_b.prompt import load_prompt

    hc = config.load("header_b", config_dir)
    scope = hc.get("scope", "frontier_only")
    if scope not in SCOPES:
        raise GridRunError(f"config/header_b: scope must be one of {list(SCOPES)}, got {scope!r}")
    if hc.get("granularity") not in ("pasal", "ayat"):
        raise GridRunError("config/header_b: granularity must be 'pasal' or 'ayat'")
    prompt = load_prompt(int(hc["max_header_tokens"]))
    mc = config.load("model", config_dir)
    store = DirHeaderStore(headers_dir or Path(runs_dir) / "headers", prompt.prompt_hash, runs_dir)
    return HeaderBinding(store, hc["granularity"], scope, prompt.prompt_hash, mc["profiles"][mc["default_profile"]]["model"])


def make_plan(family: str, *, doc: Any, tokenizer: Any, butir_dir: Path, runs_dir: Path, config_dir: Path | None = None,
              create_split: bool, headers: HeaderBinding | None = None) -> Plan:
    """Rencana run. `create_split=False` (R3): split dihitung murni dari record tersimpan, tanpa menulis; tanpa record -> split None."""
    cfgs = {n: config.load(n, config_dir) for n in CONFIGS}
    settings = expand_grid(cfgs["grid"], family)
    hb = headers is not None
    runnable = [s for s in settings if unavailable_reason(s, headers=hb) is None]
    skipped = [{"setting_id": s.setting_id, "chunker": s.chunker, "retrieval_mode": s.retrieval_mode, "header_b": s.header_b,
                "budget_tokens": s.budget_tokens, "reason": unavailable_reason(s, headers=hb)}
               for s in settings if unavailable_reason(s, headers=hb)]
    raw, fname = load_items(family, butir_dir)
    for it in raw:
        if it.get("clean_sha256") != doc.clean_sha256:
            raise GridRunError(f"item {it.get('id')!r} was written against a different clean text than the loaded corpus")
    items = to_grid_items(raw)
    g = cfgs["grid"]["split"]
    split: SplitRecord | None = None
    if items:
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
    chash = pipeline_config_hash(cfgs, tokenizer.info, headers)
    key = grid_cache_key(doc.clean_sha256, chash, item_set_hash(items), split.split_version) if split else None
    return Plan(family, cfgs, chash, headers, settings, runnable, skipped, items, fname, split, key)


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
def quality_for(pipe: Pipeline, s: Setting, metrics: list[Any]) -> dict[str, Any]:
    """QualityMetrics satu setting: potongan seluruh korpus + Recall@K per butir dari ItemMetrics (fungsi produksi M1.2)."""
    cs = pipe.chunk_set(s)
    q = pipe.rcfg["quality"]
    scope = set(pipe.rcfg["scope_sections"])
    units = cs.amap.in_sections(scope)
    bounds = frozenset({0, len(pipe.doc.text)} | {u.start for u in units} | {u.end for u in units})
    qdoc = QualityDoc(pipe.doc.text, tuple(ChunkSpan(c.start, c.end) for c in cs.chunks), bounds)
    scope = q.get("recall_items", "all")
    if scope not in RECALL_ITEM_SCOPES:
        raise GridRunError(f"[quality].recall_items must be one of {list(RECALL_ITEM_SCOPES)}, got {scope!r}")
    used = [x for x in metrics if scope == "all" or x.split == scope]
    m = quality_metrics(s.setting_id, [qdoc], pipe.k, [x.recall_at_k for x in used], q["entity_patterns"], q["abbreviations"])
    d = asdict(m)
    d["items_scope"] = scope  # label cakupan butir Recall@K (I-39)
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


def run_family_grid(family: str, *, doc: Any, tokenizer: Any, runs_dir: Path, butir_dir: Path, config_dir: Path | None = None,
                    encoder: Encoder | None = None, encoder_factory: Callable[[], Encoder] | None = None,
                    embed_cache_dir: Path | None = None, pipeline_out: list | None = None,
                    log: Callable[[str], None] = lambda _m: None, headers: HeaderBinding | None = None) -> GridResult:
    """Jalankan (atau baca dari cache) grid satu keluarga. Tanpa Model API."""
    t0 = time.perf_counter()
    if family != "uupt":
        raise GridRunError(f"grid for family {family!r} is not available in M1")
    plan = make_plan(family, doc=doc, tokenizer=tokenizer, butir_dir=butir_dir, runs_dir=runs_dir, config_dir=config_dir, create_split=True,
                     headers=headers)
    if not plan.items:
        raise GridRunError(f"no items for family {family!r}")
    assert plan.split is not None and plan.key is not None
    store = RunFileStore(Path(runs_dir) / "grid")
    existing = store.read(plan.key)
    if existing and existing.get("record"):
        rec = dict(existing["record"])
        rec["status"] = "cached"
        log(f"cache hit {plan.key[:16]}")
        return GridResult(plan.key, True, rec, existing, store.path(plan.key))

    g, r = plan.cfgs["grid"], plan.cfgs["retrieval"]
    pipe = Pipeline(doc, tokenizer=tokenizer, retrieval_cfg=r, grid_cfg=g, encoder=encoder, cache_dir=embed_cache_dir,
                    encoder_factory=encoder_factory or (lambda: encoder_from_config(r)), headers=headers)
    if pipeline_out is not None:
        pipeline_out.append(pipe)
    log(f"run {len(plan.runnable)} settings, skipped {len(plan.skipped)}, items {len(plan.items)}")
    if headers is not None:
        log(f"header B: scope={headers.scope} granularity={headers.granularity}")
    res = run_grid(settings=plan.runnable, items=plan.items, pipeline=pipe, cache=store, clean_sha256=doc.clean_sha256,
                   config_hash=plan.config_hash, split_record=plan.split, simplicity=g["simplicity"], family=family,
                   header_scope=headers.scope if headers is not None else "all")
    assert res.grid_run_id == plan.key
    by_id = {s.setting_id: s for s in plan.runnable}
    per_setting: dict[str, list[Any]] = {}
    for m in res.metrics:
        per_setting.setdefault(m.setting_id, []).append(m)
    executed = [s for s in plan.runnable if s.setting_id in per_setting]  # tanpa kembaran di luar scope dan setting gagal
    quality = [quality_for(pipe, s, per_setting[s.setting_id]) for s in executed]
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
    record = RunRecord(
        run_id=f"grid-{plan.key[:16]}", kind="grid", created_at=utc_now(), cache_key=plan.key,
        corpus_hash=config.config_hash({"docs": [doc.sha256]}), config_hash=plan.config_hash,
        clean_sha256=doc.clean_sha256, loader_rules_version=doc.loader_rules_version, prompt_version=None, prompt_hash=None,
        model=None, effort=None, tokenizer=parts["tokenizer"], embedder=emb, packing=parts["packing"],
        usage_input_tokens=None, usage_cached_tokens=None, usage_output_tokens=None, cost_usd_micros=0,
        projected_cost_usd_micros=None, latency_ms=int((time.perf_counter() - t0) * 1000), host=host, device=device,
        provider=None, quantization=None, status="ok", error=None,
        failed_settings=[f.to_dict() for f in res.failed_settings]).to_dict()  # DATA-CONTRACTS §12, H-069
    envelope = {
        "key": plan.key, "family": family, "record": record,
        "item_file": plan.item_file, "n_items": len(plan.items),
        "split": plan.split.to_dict(),
        "settings_run": [asdict(s) for s in executed], "skipped": plan.skipped,
        "n_truncated_by_chunker": trunc,
        "metrics": [metrics_to_cache(m) for m in res.metrics],
        "points": [{**point_dict(p), "header_b": by_id[p.setting_id].header_b} for p in res.points],  # deret on/off (U2)
        "frontiers": [{"family": f.family, "split": f.split, "budget_tokens": f.budget_tokens, "point_ids": list(f.point_ids),
                       "grid_run_id": f.grid_run_id} for f in res.frontiers],
        "selections": {str(b): selection_dict(s) for b, s in sorted(res.selections.items())},
        "quality": quality, "quality_comparison": comparison,
    }
    store.write(plan.key, envelope)
    return GridResult(plan.key, False, record, envelope, store.path(plan.key))


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
    tune = sum(1 for a in sp["assignments"] if a["split"] == "tune")
    out.append(f"split v{sp['split_version']} seed={sp['seed']} ratio={sp['held_out_ratio']}: tune={tune} held_out={len(sp['assignments']) - tune} "
               f"control_in_held_out={sp['control_in_held_out']}")
    by_id = {s["setting_id"]: s for s in env["settings_run"]}
    for f in env["frontiers"]:
        if f["split"] != "tune":
            continue
        out.append(f"frontier tune budget={f['budget_tokens']}:")
        pts = {p["setting_id"]: p for p in env["points"] if p["split"] == "tune" and p["budget_tokens"] == f["budget_tokens"]}
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
    args = ap.parse_args(argv)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from backend.corpus import load_corpus
    from backend.tokenizer import get_tokenizer

    t0 = time.perf_counter()
    try:
        res = run_family_grid(args.family, doc=load_corpus(), tokenizer=get_tokenizer(), runs_dir=args.runs_dir,
                              butir_dir=args.butir_dir, embed_cache_dir=CACHE_DIR, log=lambda m: print(m, flush=True),
                              headers=load_header_binding(runs_dir=args.runs_dir) if args.with_headers else None)
    except (GridRunError, GridError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in summarize(res):
        print(line)
    print(f"wall_seconds={time.perf_counter() - t0:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
