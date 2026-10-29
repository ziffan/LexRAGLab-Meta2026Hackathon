"""H-101 bagian 4: grid ulang per model pembanding untuk header B (kembaran header-on saja) dan laporan berkas.

    uv run python -m backend.pipeline.grid_compare --family uupt --model-profile baseten_open
    uv run python -m backend.pipeline.grid_compare --family akta --model-profile glimmer_local   # run ulang = cache hit + laporan

Hasil di `runs/grid_compare/<profile>/<kunci>.json` (DI LUAR `runs/grid/`; pembaca R3/snapshot hanya membaca `runs/grid/*.json`).
Himpunan setting = kembaran header-on dari frontier tune deret off di amplop UTAMA (D3, `scope` config/header_b); header-off
tidak dijalankan ulang (P4: amplop utama dirujuk lewat `off_ref`, tidak disalin, tidak ditulis); model tidak memilih setting
(`selections` kosong). Header yang hilang/basi/kosong/salah granularitas = galat per setting di `failed_settings` (D4) tanpa
GridPoint. Kunci = kunci grid yang sama (korpus, `config_hash`, butir, split) dengan `config_hash` memuat blok `compare`
(profile, provider, model, quantization, effort) dan isi store pembanding; identitas utama tidak berubah (G-38).
Laporan berkas (Q-B5, tanpa UI): `runs/grid_compare/<profile>/report-<kunci>.md` (+ `.json`), label `Header B: <label>`.

Profil sapuan (H-102, `config/sweep.toml`, S11): kebijakan cakupan sebagian `mask_threshold`/`mask_ref` (ambang `>=` integer); blok
`coverage` amplop memuat kunci lama (`sources_run`, `sources_not_run`) DIGABUNG dengan `policy`, `threshold_pct`, `settings`
(penyimpangan dinyatakan dari S11 (b): satu kunci `coverage`; setting di bawah ambang diberi `below_threshold`). Profil non-sapuan
tidak membaca `config/sweep.toml` dan tetap `strict` persis H-101.

H-104 Q-S14: flag CLI eksplisit `--coverage-policy {strict,mask_threshold,mask_ref}` + `--coverage-threshold-pct N` (1..100, wajib untuk
mask_*, dilarang untuk strict) berlaku untuk profil mana pun (`coverage_override` di `run_compare_grid`) dan menggantikan `[compare]`.
Tanpa flag perilaku tidak berubah (non-sapuan strict tanpa membaca sweep.toml). Dengan flag non-strict, blok compare memuat
`policy`/`threshold_pct` sehingga kunci beda dan amplop strict H-101 lama tidak ditimpa. Nilai tidak sah = rc 2 sebelum kerja."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from backend import config, gpulock
from backend.grid.frontier import aggregate_points, compute_frontiers
from backend.grid.headers import GRANULARITY_DIRS, DirHeaderStore, HeaderBinding, HeaderError, HeaderStore
from backend.grid.runner import GridError, _frontier_twins, run_grid
from backend.grid.schemas import SchemaBinding
from backend.grid.types import (MULTI_DOC_FAMILIES, GridPoint, Setting, canonical_json, metrics_from_cache, metrics_to_cache)
from backend.header_b.compare_store import (CompareError, build_identity, check_forbidden_profile_keys, check_identity,
                                            compare_profile_root, compare_store_dir, comparison_profile, read_identity)
from backend.metrics.run_record import run_record_parts
from backend.pipeline.grid_run import (GridRunError, RunFileStore, load_header_binding, make_plan, point_dict, utc_now)
from backend.pipeline.multi import MultiDocPipeline
from backend.pipeline.pipeline import Pipeline
from backend.spark import ConfigInvalid, sweep_run
from backend.retrieval.dense import Encoder, embedder_info, encoder_from_config
from backend.spark.runrecord import RunRecord

COMPARE_GRID_DIR = "grid_compare"
LABEL_PREFIX = "Header B: "


class OffSeriesMissing(CompareError):
    def __init__(self, key: str | None) -> None:
        super().__init__("off_series_missing", f"the main grid envelope (key {key}) is missing; run the main grid with headers first")


@dataclass
class CompareGridResult:
    key: str
    cache_hit: bool
    envelope: dict[str, Any]
    path: Path
    ref_path: Path | None = None  # S11 (c): titik rujukan Contributor ber-mask (hanya mask_ref profil sapuan)


class RefFileStore(RunFileStore):
    """`runs/grid_compare/<profil>/ref-<kunci>.json`: titik rujukan Contributor ber-mask (S11 c)."""

    def path(self, key: str) -> Path:
        return self.dir / f"ref-{key}.json"


def coverage_label(bp: int) -> str:
    return f"{bp // 100},{bp % 100:02d}%"


def compare_grid_dir(runs_dir: Path, profile: str) -> Path:
    return Path(runs_dir) / COMPARE_GRID_DIR / profile


def label_for(prof: Mapping[str, Any], profile: str) -> str:
    """P13: `Header B: <label profil di config/model>`."""
    return LABEL_PREFIX + str(prof.get("label") or profile)


def compare_block(identity: Mapping[str, Any]) -> dict[str, Any]:
    return {k: identity.get(k) for k in ("profile", "provider", "model", "quantization", "effort")}


def comparison_frontier(off_points: Sequence[GridPoint], on_points: Sequence[GridPoint], key: str) -> tuple[list[GridPoint], list[Any]]:
    """Frontier pembanding (S13 (h)): dominasi atas {titik off amplop utama} + {titik on pembanding}. Frontier utama tidak berubah."""
    return compute_frontiers([*off_points, *on_points], key)


def store_has_source(store: Any, gran: str) -> bool:
    """Ada minimal satu header tersimpan untuk sumber `gran` (dibaca dari isi store, bukan dari hasil titik grid)."""
    if isinstance(store, DirHeaderStore):
        return next((store.headers_dir / gran / store.prompt12).glob("*.json"), None) is not None
    recs = getattr(store, "records", None)
    return isinstance(recs, Mapping) and any(r.get("granularity") == gran for r in recs.values())


def coverage_of(twins: Sequence[Setting], binding: HeaderBinding) -> dict[str, list[str]]:
    """Cakupan per sumber header diturunkan dari ISI store pembanding: `sources_run` = sumber yang dibutuhkan kembaran dan punya
    header tersimpan; `sources_not_run` = dibutuhkan tetapi store kosong (S17 (d)). Setting yang gagal sebagian tetap tercatat di
    `failed_settings`, bukan sebagai sumber tak dijalankan."""
    need = {binding.expected_granularity(s.chunker) for s in twins}
    ran = {g for g in need if store_has_source(binding.store, g)}
    order = {g: i for i, g in enumerate(GRANULARITY_DIRS)}
    return {"sources_run": sorted(ran, key=order.get), "sources_not_run": sorted(need - ran, key=order.get)}  # type: ignore[arg-type]


def validate_coverage_override(policy: str, pct: int) -> tuple[str, int]:
    """H-104 Q-S14: kebijakan eksplisit dari CLI. `strict` -> (strict, 100); mask_* butuh integer 1..100 (bool ditolak)."""
    if policy not in sweep_run.COVERAGE_POLICIES:
        raise ConfigInvalid(f"coverage policy must be one of {list(sweep_run.COVERAGE_POLICIES)}")
    if isinstance(pct, bool) or not isinstance(pct, int) or not 1 <= pct <= 100:
        raise ConfigInvalid("coverage threshold must be an integer between 1 and 100")
    return policy, pct


def run_compare_grid(family: str, *, profile: str, model_cfg: Mapping[str, Any], doc: Any = None, docs: Any = None, tokenizer: Any,
                     runs_dir: Path, butir_dir: Path, config_dir: Path | None = None, encoder: Encoder | None = None,
                     encoder_factory: Callable[[], Encoder] | None = None, embed_cache_dir: Path | None = None,
                     log: Callable[[str], None] = lambda _m: None, main_headers: HeaderBinding | None = None,
                     compare_store: HeaderStore | None = None, identity: Mapping[str, Any] | None = None,
                     schemas: SchemaBinding | None | str = "auto",
                     gpu_lock: bool = False, gpu_pid_alive: Callable[[int], bool] | None = None,
                     sweep_cfg: Mapping[str, Any] | None = None,
                     coverage_override: tuple[str, int] | None = None) -> CompareGridResult:
    """Jalankan (atau baca dari cache) grid pembanding satu keluarga. Tanpa Model API.

    `main_headers`/`compare_store`/`identity` disuntikkan oleh test; bawaan: binding utama dari `runs/headers`, store
    `runs/headers_compare/<profile>[/akta]`, dan `identity.json` profil itu."""
    t0 = time.perf_counter()
    check_forbidden_profile_keys(model_cfg)
    # S5 (m)(o): profil non-sapuan (ada di config/model) TIDAK membaca config/sweep.toml dan tetap strict persis H-101
    eff_model, sw = sweep_run.resolve_profile(model_cfg, profile, sweep_cfg)
    if sw is not None:
        sweep_run.validate_runner_cfg(sw)
    pol, pct = validate_coverage_override(*coverage_override) if coverage_override is not None else sweep_run.coverage_policy(sw)
    prof = comparison_profile(eff_model, profile)
    multi = family in MULTI_DOC_FAMILIES
    runs = Path(runs_dir)
    base = main_headers or load_header_binding(runs_dir=runs, config_dir=config_dir, family=family)
    ident = dict(identity) if identity is not None else read_identity(compare_profile_root(runs, profile))
    if ident is None:
        raise CompareError("compare_store_missing", f"no comparison store for profile '{profile}' (run backend.header_b.compare first)")
    cur = build_identity(profile, prof, eff_model, prompt_hash=base.prompt_hash,
                         max_header_tokens=ident.get("max_header_tokens"), schema_max_length_chars=ident.get("schema_max_length_chars"))
    if identity is None:
        check_identity(compare_profile_root(runs, profile), cur)  # config berubah sejak store dibuat -> mismatch, bukan kunci baru diam-diam
    store = compare_store if compare_store is not None else DirHeaderStore(compare_store_dir(runs, profile, family), base.prompt_hash, runs)
    block = compare_block(ident)
    if pol != "strict":  # S11 (e): kebijakan ikut kunci (blok compare memuat policy dan threshold_pct); strict = kunci H-101
        block = {**block, "policy": pol, "threshold_pct": pct}
    cbind = HeaderBinding(store, base.granularity, base.scope, base.prompt_hash, str(prof.get("model")), compare=block,
                          coverage=(pol, pct) if pol != "strict" else None)

    if schemas == "auto":  # sama dengan `Service.schema_binding`: skema A keluarga bila store punya rekaman (kunci K0 memuat identitasnya)
        sb = SchemaBinding.from_store(runs, family)
        schemas = sb if sb.records else None
    common: dict[str, Any] = dict(doc=doc, docs=docs, tokenizer=tokenizer, butir_dir=butir_dir, runs_dir=runs, config_dir=config_dir,
                                  create_split=False, schemas=schemas)
    main_plan = make_plan(family, headers=base, **common)
    if main_plan.key is None:
        raise GridRunError("no grid key for the main plan (no items or no split record)")
    main_store = RunFileStore(runs / "grid")
    main_env = main_store.read(main_plan.key)
    if not main_env or not main_env.get("record"):
        raise OffSeriesMissing(main_plan.key)
    plan = make_plan(family, headers=cbind, **common)
    assert plan.key is not None
    cstore = RunFileStore(compare_grid_dir(runs, profile))
    existing = cstore.read(plan.key)
    if existing and existing.get("record"):
        log(f"cache hit {plan.key[:16]}")
        return CompareGridResult(plan.key, True, existing, cstore.path(plan.key))

    off = [s for s in plan.runnable if not s.header_b]
    on = [s for s in plan.runnable if s.header_b]
    by_id_all = {s.setting_id: s for s in plan.runnable}
    off_ids = {s.setting_id for s in off}
    off_metrics = [metrics_from_cache(d) for d in main_env.get("metrics", []) if d.get("setting_id") in off_ids]
    twins = on if base.scope == "all" else _frontier_twins(off, on, off_metrics, main_plan.key, family)
    log(f"compare grid {profile}: {len(twins)} header-on twins, {len(off_metrics)} main off metrics, main key {main_plan.key[:16]}")

    lock = None
    if gpu_lock and any(s.retrieval_mode != "bm25" for s in twins):  # S16 (g): encoder dimuat -> kunci GPU eksklusif
        lock = gpulock.acquire(runs, "embedding", **({"pid_alive": gpu_pid_alive} if gpu_pid_alive is not None else {}))
    try:
        g, r = plan.cfgs["grid"], plan.cfgs["retrieval"]
        pkw = dict(tokenizer=tokenizer, retrieval_cfg=r, grid_cfg=g, encoder=encoder, cache_dir=embed_cache_dir,
                   encoder_factory=encoder_factory or (lambda r=r: encoder_from_config(r)), headers=cbind, schemas=plan.schemas)
        pipe: Any = MultiDocPipeline(docs, **pkw) if multi else Pipeline(doc, **pkw)
        res = run_grid(settings=twins, items=plan.items, pipeline=pipe, cache=cstore, clean_sha256=plan.corpus_key,
                       config_hash=plan.config_hash, split_record=plan.split, simplicity=g["simplicity"], family=family,
                       header_scope="all")
        assert res.grid_run_id == plan.key
        executed_ids = {m.setting_id for m in res.metrics}
        executed = [s for s in twins if s.setting_id in executed_ids]
        on_metrics = list(res.metrics)
        all_points = aggregate_points([*off_metrics, *on_metrics], by_id_all)
        pts, fronts = comparison_frontier([p for p in all_points if p.setting_id in off_ids],
                                          [p for p in all_points if p.setting_id in executed_ids], plan.key)
        on_pts = [p for p in pts if p.setting_id in executed_ids]
        cov = coverage_of(twins, cbind)
        ref_path = None
        if pol != "strict":  # S11 (b): cakupan per setting (juga setting di bawah ambang) di amplop
            sub = list(pipe.pipes.values()) if multi else [pipe]
            reports: dict[str, Any] = {}
            for pp in sub:  # deterministik: setting yang metriknya diambil dari cache tidak pernah diindeks -> hitung dari chunk set + store
                for st in twins:
                    if st.setting_id not in pp.coverage_report:
                        try:
                            pp.headers_for(st)
                        except HeaderError:
                            pass  # laporan tetap terisi (finally di headers_for); galat dicatat run_grid pada jalur indeks
            for pp in sub:
                for sid, r in pp.coverage_report.items():
                    if sid in reports:
                        reports[sid] = {"chunks": reports[sid]["chunks"] + r["chunks"], "headered": reports[sid]["headered"] + r["headered"],
                                        "coverage_bp": (reports[sid]["headered"] + r["headered"]) * 10000 //
                                        (reports[sid]["chunks"] + r["chunks"]), "missing": reports[sid]["missing"] + r["missing"]}
                    else:
                        reports[sid] = dict(r)
            failed_ids = {f.setting_id for f in res.failed_settings}
            cov = {**cov, "policy": pol, "threshold_pct": pct,
                   "settings": {sid: ({**r, "below_threshold": True} if sid in failed_ids else r) for sid, r in sorted(reports.items())}}
        enc = pipe.encoder if pipe.encoder_used else None
        trunc = pipe.n_truncated()
        emb = embedder_info(enc, sum(trunc.values())) if enc is not None else None
        host = config.load("model", config_dir)["host"]
        device = ("cuda:0" if enc.device == "cuda" else enc.device) if enc is not None else "cpu"
        parts = run_record_parts(tokenizer.info, g["packing"]["rule"])
        if multi:
            corpus_hash, clean, rules = plan.corpus_key, plan.corpus_key, ",".join(sorted({d.loader_rules_version for d in docs}))
        else:
            corpus_hash, clean, rules = config.config_hash({"docs": [doc.sha256]}), doc.clean_sha256, doc.loader_rules_version
        record = RunRecord(
            run_id=f"gridcmp-{plan.key[:16]}", kind="grid", created_at=utc_now(), cache_key=plan.key, corpus_hash=corpus_hash,
            config_hash=plan.config_hash, clean_sha256=clean, loader_rules_version=rules, prompt_version=None, prompt_hash=None,
            model=block["model"], effort=block["effort"], tokenizer=parts["tokenizer"], embedder=emb, packing=parts["packing"],
            usage_input_tokens=None, usage_cached_tokens=None, usage_output_tokens=None, cost_usd_micros=0,
            projected_cost_usd_micros=None, latency_ms=int((time.perf_counter() - t0) * 1000), host=host, device=device,
            provider=block["provider"], quantization=block["quantization"], status="ok", error=None,
            failed_settings=[f.to_dict() for f in res.failed_settings]).to_dict()
        by_pt = {p.setting_id: p for p in on_pts}
        envelope = {
            "key": plan.key, "kind": "grid_compare", "family": family, "label": label_for(prof, profile),
            "compare": {**block, "profile_label": prof.get("label")},
            "off_ref": {"key": main_plan.key, "path": f"runs/grid/{main_plan.key}.json"},
            "record": record, "item_file": plan.item_file, "n_items": len(plan.items),
            "split": plan.split.to_dict() if plan.split is not None else None,
            "settings_requested": [s.setting_id for s in twins],
            "settings_run": [asdict(s) for s in executed], "skipped": [],
            "metrics": [metrics_to_cache(m) for m in on_metrics],
            "points": [{**point_dict(p), "header_b": True} for p in on_pts],
            "frontiers": [{"family": f.family, "split": f.split, "budget_tokens": f.budget_tokens, "point_ids": list(f.point_ids),
                           "grid_run_id": f.grid_run_id,
                           "dominated_ids": sorted(p.setting_id for p in pts if (p.family, p.split, p.budget_tokens) ==
                                                   (f.family, f.split, f.budget_tokens) and p.dominated)} for f in fronts],
            "selections": {},  # model pembanding tidak memilih profil (D3)
            "failed_settings": [f.to_dict() for f in res.failed_settings],
            "coverage": cov,
            "n_truncated_by_chunker": trunc,
        }
        assert set(by_pt) <= executed_ids
        if pol == "mask_ref":  # S11 (c): rujukan Contributor ber-mask SAMA (tanpa panggilan model; hanya retrieval)
            masked = sorted({cid for sid, r in cov["settings"].items() if not r.get("below_threshold") for cid in r["missing"]})
            if masked:
                ref_path = _run_reference(base, masked, profile, pol, pct, eff_model, executed, by_id_all, common, plan, pkw, multi, docs,
                                          doc, family, g, off_metrics, runs)
        # Amplop ditulis SESUDAH rujukan: rujukan yang gagal tidak meninggalkan amplop yang kelak cache-hit tanpa rujukan.
        cstore.write(plan.key, envelope)
        return CompareGridResult(plan.key, False, envelope, cstore.path(plan.key), ref_path)
    finally:
        if lock is not None:
            lock.release()


def _run_reference(base: HeaderBinding, masked: Sequence[str], profile: str, pol: str, pct: int, model_cfg: Mapping[str, Any],
                   executed: Sequence[Setting], by_id_all: Mapping[str, Setting], common: Mapping[str, Any], plan: Any,
                   pkw: Mapping[str, Any], multi: bool, docs: Any, doc: Any, family: str, g: Mapping[str, Any],
                   off_metrics: Sequence[Any], runs: Path) -> Path:
    """Titik rujukan (iv): store header Contributor UTAMA dengan potongan `masked` diperlakukan tanpa header (teks header-off)."""
    import hashlib
    effort = (model_cfg.get("effort") or {}).get("b", "low")
    label = f"{LABEL_PREFIX}Contributor ({effort}), masked as {profile}"
    mdigest = hashlib.sha256(canonical_json(list(masked)).encode("utf-8")).hexdigest()
    block = {"profile": f"main_masked_as_{profile}", "provider": "meta", "model": base.model, "quantization": None, "effort": effort,
             "policy": pol, "threshold_pct": pct, "mask_sha256": mdigest}
    rbind = HeaderBinding(base.store, base.granularity, base.scope, base.prompt_hash, base.model, compare=block,
                          mask=frozenset(masked))
    rplan = make_plan(family, headers=rbind, **common)
    assert rplan.key is not None
    rstore = RefFileStore(compare_grid_dir(runs, profile))
    p = rstore.path(rplan.key)
    if rstore.read(rplan.key):
        return p
    rpkw = {**pkw, "headers": rbind}
    pipe: Any = MultiDocPipeline(docs, **rpkw) if multi else Pipeline(doc, **rpkw)
    res = run_grid(settings=list(executed), items=rplan.items, pipeline=pipe, cache=rstore, clean_sha256=rplan.corpus_key,
                   config_hash=rplan.config_hash, split_record=rplan.split, simplicity=g["simplicity"], family=family, header_scope="all")
    pts = aggregate_points(list(res.metrics), by_id_all)
    rstore.write(rplan.key, {
        "key": rplan.key, "kind": "grid_compare_ref", "family": family, "label": label, "compare": block, "masked": list(masked),
        "settings_run": [asdict(s) for s in executed], "metrics": [metrics_to_cache(m) for m in res.metrics],
        "points": [{**point_dict(pt), "header_b": True} for pt in pts], "failed_settings": [f.to_dict() for f in res.failed_settings]})
    return p


# ---------------------------------------------------------------- laporan berkas (Q-B5)
def _dec(exact: str | None, v: Any) -> str:
    return "n/a" if exact is None else f"{exact} = {v:.6f}" if isinstance(v, (int, float)) else str(exact)


def _partial(env: Mapping[str, Any], setting_id: str) -> str:
    """S11 (b): baris titik dengan potongan tanpa header ditandai 'partial header coverage 95,00%'."""
    r = ((env.get("coverage") or {}).get("settings") or {}).get(setting_id)
    return f" (partial header coverage {coverage_label(r['coverage_bp'])})" if r and r.get("missing") else ""


def render_report(env: Mapping[str, Any]) -> str:
    """Markdown laporan pembanding. Membaca HANYA amplop pembanding; tiap baris berlabel `Header B: <label>`; tidak menghitung
    ulang frontier utama (frontier pembanding diambil apa adanya dari amplop)."""
    label = env["label"]
    c = env["compare"]
    cov = env.get("coverage") or {"sources_run": [], "sources_not_run": []}
    partial = bool(cov["sources_not_run"])
    out = [f"# {label} ({env['family']})", "",
           f"- key: `{env['key']}`; main off series: `{env['off_ref']['path']}` (key `{env['off_ref']['key']}`)",
           f"- provider `{c['provider']}`, model `{c['model']}`, quantization `{c['quantization']}`, effort `{c['effort']}`",
           f"- sources run: {', '.join(cov['sources_run']) or '(none)'}; sources not run: {', '.join(cov['sources_not_run']) or '(none)'}"
           + ("; **partial coverage**" if partial else ""),
           "- Not a reported number: comparison only (H-028); the main grid, frontier and selected profile stay Contributor.", ""]
    by_id = {s["setting_id"]: s for s in env.get("settings_run", [])}
    out += ["## Points (header-on twins)", "", "| Series | Setting | Chunker | Mode | Budget | Split | Span recall | Mean retrieved tokens | Dominated |",
            "|---|---|---|---|---|---|---|---|---|"]
    for p in env.get("points", []):
        s = by_id.get(p["setting_id"], {})
        ex = p.get("exact", {})
        out.append(f"| {label}{' (partial coverage)' if partial else ''}{_partial(env, p['setting_id'])} | `{p['setting_id'][:12]}` | {s.get('chunker')} | {s.get('retrieval_mode')} | "
                   f"{p['budget_tokens']} | {p['split']} | {_dec(ex.get('mean_span_recall'), p.get('mean_span_recall'))} | "
                   f"{_dec(ex.get('mean_retrieved_tokens'), p.get('mean_retrieved_tokens'))} | {p.get('dominated')} |")
    out += ["", "## Frontier (main off series + this comparison's header-on points)", ""]
    for f in env.get("frontiers", []):
        ids = ", ".join(f"`{i[:12]}`{' (' + label + ')' if i in by_id else ' (main, header off)'}" for i in f["point_ids"])
        out.append(f"- split {f['split']} budget {f['budget_tokens']}: {ids or '(empty)'}")
    out += ["", "## Failed settings", ""]
    fs = env.get("failed_settings") or []
    out += (["| Setting | Reason | Chunk |", "|---|---|---|", *[f"| `{x['setting_id'][:12]}` | {x['reason']} | {x.get('chunk_id')} |" for x in fs]]
            if fs else ["(none)"])
    return "\n".join(out) + "\n"


def write_report(runs_dir: Path, profile: str, env: Mapping[str, Any]) -> tuple[Path, Path]:
    d = compare_grid_dir(runs_dir, profile)
    d.mkdir(parents=True, exist_ok=True)
    md, js = d / f"report-{env['key']}.md", d / f"report-{env['key']}.json"
    for p, body in ((md, render_report(env)), (js, canonical_json({k: env[k] for k in ("key", "label", "family", "compare", "off_ref", "coverage",
                                                                                      "failed_settings", "points", "frontiers")}) + "\n")):
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(body, encoding="utf-8", newline="\n")
        os.replace(tmp, p)
    return md, js


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    import argparse

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="backend.pipeline.grid_compare")
    ap.add_argument("--family", default="uupt")
    ap.add_argument("--model-profile", required=True)
    ap.add_argument("--runs-dir", type=Path, default=config.REPO_ROOT / "runs")
    ap.add_argument("--butir-dir", type=Path, default=config.REPO_ROOT / "data" / "butir")
    ap.add_argument("--coverage-policy", choices=list(sweep_run.COVERAGE_POLICIES), default=None)
    ap.add_argument("--coverage-threshold-pct", type=int, default=None)
    args = ap.parse_args(argv)
    override: tuple[str, int] | None = None
    if args.coverage_policy is not None or args.coverage_threshold_pct is not None:  # divalidasi sebelum kerja apa pun
        try:
            if args.coverage_policy is None:
                raise ConfigInvalid("--coverage-threshold-pct requires --coverage-policy")
            if args.coverage_policy == "strict":
                if args.coverage_threshold_pct is not None:
                    raise ConfigInvalid("--coverage-threshold-pct is not allowed with --coverage-policy strict")
                override = ("strict", 100)
            else:
                if args.coverage_threshold_pct is None:
                    raise ConfigInvalid(f"--coverage-policy {args.coverage_policy} requires --coverage-threshold-pct")
                override = validate_coverage_override(args.coverage_policy, args.coverage_threshold_pct)
        except ConfigInvalid as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from backend.corpus import akta_entries, load_corpus
    from backend.retrieval.dense import CACHE_DIR
    from backend.tokenizer import get_tokenizer

    model_cfg = config.load("model")
    try:
        if args.family in MULTI_DOC_FAMILIES:
            ids = [i for i, e in akta_entries().items() if e.get("family", args.family) == args.family]
            dkw: dict[str, Any] = {"docs": [load_corpus(i) for i in ids]}
        else:
            dkw = {"doc": load_corpus()}
        res = run_compare_grid(args.family, profile=args.model_profile, model_cfg=model_cfg, **dkw, tokenizer=get_tokenizer(),
                               runs_dir=args.runs_dir, butir_dir=args.butir_dir, embed_cache_dir=CACHE_DIR,
                               log=lambda m: print(m, flush=True), gpu_lock=True, coverage_override=override)
    except (GridRunError, GridError, CompareError, gpulock.GpuLockError, ConfigInvalid) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    md, js = write_report(args.runs_dir, args.model_profile, res.envelope)
    print(f"{res.envelope['label']}: key={res.key} cache_hit={res.cache_hit} failed_settings={len(res.envelope['failed_settings'])} "
          f"coverage={json.dumps(res.envelope['coverage'])}")
    print(f"path={res.path}\nreport={md}\nreport_json={js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
