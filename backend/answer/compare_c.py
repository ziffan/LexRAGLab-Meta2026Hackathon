"""CLI M2.5: jalankan peran C untuk satu `model_profile` pembanding (Glimmer lokal atau Spark Open Baseten) dengan
MEMAKAI ULANG konteks persis jawaban Contributor yang tersimpan (`runs/answers/`, profil sumber `meta`).

Tidak ada retrieval/embedding: konteks dibangun ulang dari `context_chunk_ids` + prompt versi yang tercatat di
RunRecord sumber, lalu dicocokkan dengan `cache_key` Contributor (hash masukan identik). Cocok = masukan byte-identik,
jadi perbandingan adil dan Glimmer tidak berbarengan dengan bge-m3 (G-26). Tidak cocok = butir dilewati dengan alasan.

    uv run python -m backend.answer.compare_c --model-profile glimmer_local --project-only
    uv run python -m backend.answer.compare_c --model-profile glimmer_local
    uv run python -m backend.answer.compare_c --model-profile baseten_open [--items kontrol-K-09 ...]

Tanpa `--items`: butir `scene_checked` yang punya jawaban Contributor tersimpan untuk kedua kolom. Hasil di-cache per
hash (run ulang tidak memanggil). `--project-only` tidak memanggil apa pun dan tidak menulis.

Profil sapuan effort (H-102, `config/sweep.toml`): gerbang G-36 per butir (dua slot) atas pool sapuan SEBELUM jaringan
(ditolak -> butir `not_run`, bukan kegagalan model), kunci `model_api_meta.lock` untuk Contributor sapuan, dan
`--grade`: sel 2x2 OFFLINE (tanpa model) atas jawaban tersimpan profil itu -> `runs/compare_report/c/<profil>.json` + `.md`.

Penyimpangan dari skenario S20 (a), dinyatakan: batas atas gerbang butir = jumlah `Projection.per_call_micros` (batas atas sadar-floor
TANPA cache, sudah konservatif) sebagai `upper_floor`, tanpa faktor ulang ganda; token cached tidak dihitung. Angka skenario
(55.000 per panggilan, 110.000 per butir) diuji di fungsi gerbang."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend import config
from backend.answer.caller import ROLE, SLOTS, load_answer, make_call, run_answers
from backend.answer.context import ContextBundle, ContextEntry, entry_labels, render
from backend.answer.prompt import PromptC, load_prompt, schema_hash
from backend.pipeline.grid_run import to_grid_items
from backend.spark import BudgetExceeded, ConfigInvalid, SparkClient, format_usd_micros, store, sweep_run
from backend.spark.settings import API_CHAT, profile_api

SOURCE_PROFILE = "meta"


@dataclass
class Plan:
    item_id: str
    slot: str
    setting_id: str
    bundle: ContextBundle | None
    prompt: PromptC | None
    skip_reason: str | None = None


def stored_answers(answers_dir: Path, source_profile: str) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """(item_id, slot) -> jawaban tersimpan profil sumber, urut answer_id (deterministik)."""
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    d = Path(answers_dir)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        rec = load_answer(d, p.stem)
        if isinstance(rec, dict) and rec.get("model_profile") == source_profile and rec.get("slot") in SLOTS:
            out.setdefault((rec["item_id"], rec["slot"]), []).append(rec)
    return out


def rebuild_plan(svc: Any, rec: dict[str, Any], records_by_run: Mapping[str, Any], item: Any) -> Plan:
    """Bangun ulang masukan C dari jawaban Contributor tersimpan; verifikasi hash masukan = cache_key sumber."""
    base = dict(item_id=rec["item_id"], slot=rec["slot"], setting_id=rec["setting_id"])
    sr = records_by_run.get(rec.get("run_id"))
    if sr is None:
        return Plan(**base, bundle=None, prompt=None, skip_reason="source RunRecord not found")
    try:
        prompt = load_prompt(sr.prompt_version)
    except (OSError, KeyError, ValueError):
        return Plan(**base, bundle=None, prompt=None, skip_reason=f"prompt version {sr.prompt_version!r} not found")
    if prompt.prompt_hash != sr.prompt_hash:
        return Plan(**base, bundle=None, prompt=prompt, skip_reason="prompt file changed since the source run")
    setting = svc.find_setting("uupt", rec["setting_id"])
    cs = svc.pipeline().chunk_set(setting)  # hanya chunking; tanpa embedding/retrieval
    doc = svc.pipeline().doc
    entries: list[ContextEntry] = []
    for rank, cid in enumerate(rec["context_chunk_ids"], start=1):
        ch = cs.by_id.get(cid)
        if ch is None:
            return Plan(**base, bundle=None, prompt=prompt, skip_reason=f"chunk {cid[:12]} not in the current chunk set")
        labels = entry_labels(cs.amap, ch.start, ch.end) if prompt.unit_labels else ()
        text = doc.text[ch.start:ch.end]
        entries.append(ContextEntry(cid, ch.address, text, int(svc.tok().count(text)), rank, labels))
    text, nonce = render(prompt, item.query, entries)
    key = store.cache_key_for(sr.provider, sr.model, sr.quantization, sr.effort, sr.prompt_hash, schema_hash(),
                              store.sha256_hex(text))
    if key != sr.cache_key:
        return Plan(**base, bundle=None, prompt=prompt, skip_reason="rebuilt input does not match the source run hash")
    bundle = ContextBundle(item_id=item.id, setting_id=setting.setting_id, budget_tokens=rec["budget_tokens"],
                           entries=entries, input_text=text, est_input=int(svc.tok().count(text)), nonce=nonce,
                           packed_tokens=sum(e.tokens for e in entries), chunk_ids=list(rec["context_chunk_ids"]))
    return Plan(**base, bundle=bundle, prompt=prompt)


def build_plans(svc: Any, runs_dir: Path, item_ids: list[str] | None, source_profile: str) -> tuple[list[Plan], list[str]]:
    """(rencana per jawaban sumber, pesan peringatan)."""
    warnings: list[str] = []
    stored = stored_answers(Path(runs_dir) / "answers", source_profile)
    raw_items = {i.get("id"): i for i in svc.items("uupt")}
    explicit = item_ids is not None
    if item_ids is None:
        item_ids = [iid for iid, r in raw_items.items() if r.get("scene_checked")]
    records = {r.run_id: r for r in store.load_records(runs_dir)}
    plans: list[Plan] = []
    for iid in item_ids:
        raw = raw_items.get(iid)
        if raw is None:
            warnings.append(f"{iid}: unknown item")
            continue
        if not all((iid, s) in stored for s in SLOTS):
            if explicit and any((iid, s) in stored for s in SLOTS):
                warnings.append(f"{iid}: stored {source_profile} answers exist for only one slot; skipped")
            continue
        item = to_grid_items([raw])[0]
        for slot in SLOTS:
            for rec in stored[(iid, slot)]:
                plans.append(rebuild_plan(svc, rec, records, item))
    return plans, warnings


COMPARE_REPORT_DIR = "compare_report"


def grade_cells(svc: Any, answers_dir: Path, profile: str, vcfg: Any, item_ids: list[str] | None = None) -> list[tuple[str, str, str, str]]:
    """P11/S14 (c): sel 2x2 per jawaban tersimpan profil `profile`: `(setting_id, slot, profil, sel)`. Murni offline."""
    from backend.verifier import ChunkSpan, grade_answer, units_from_address_map
    raw_items = {i.get("id"): i for i in svc.items("uupt")}
    doc = svc.doc("uupt-40-2007")
    cells: list[tuple[str, str, str, str]] = []
    for (iid, slot), recs in sorted(stored_answers(answers_dir, profile).items()):
        if item_ids is not None and iid not in item_ids:
            continue
        raw = raw_items.get(iid)
        if raw is None:
            continue
        item = to_grid_items([raw])[0]
        for ans in recs:
            cs = svc.pipeline().chunk_set(svc.find_setting("uupt", ans["setting_id"]))
            units = units_from_address_map(cs.amap, doc.text)
            spans = [ChunkSpan(cid, cs.by_id[cid].start, cs.by_id[cid].end) for cid in ans["context_chunk_ids"]]
            _, cell = grade_answer(ans["answer_id"], ans["output"], units, spans, item.gold_spans, vcfg)
            cells.append((ans["setting_id"], slot, profile, cell))
    return cells


def write_grade_report(runs_dir: Path, profile: str, label: str, cells: list[tuple[str, str, str, str]]) -> tuple[Path, Path]:
    """`runs/compare_report/c/<profil>.json` (+ `.md`) byte-sama pada run ulang: kunci terurut, tanpa waktu."""
    import json

    from backend.verifier import summarize
    rows = [x.to_dict() for x in summarize(cells)]
    d = Path(runs_dir) / COMPARE_REPORT_DIR / "c"
    d.mkdir(parents=True, exist_ok=True)
    js, md = d / f"{profile}.json", d / f"{profile}.md"
    js.write_text(json.dumps({"profile": profile, "label": label, "summary": rows}, sort_keys=True, ensure_ascii=False, indent=1) + "\n",
                  encoding="utf-8", newline="\n")
    lines = [f"# {label} - answer 2x2 (offline, comparison only)", "",
             "| Setting | Slot | answered_supported | answered_unsupported | abstained_correct | abstained_should_answer | n_items |",
             "|---|---|---|---|---|---|---|"]
    lines += [f"| `{r['setting_id'][:12]}` | {r['slot']} | {r['answered_supported']} | {r['answered_unsupported']} | "
              f"{r['abstained_correct']} | {r['abstained_should_answer']} | {r['n_items']} |" for r in rows]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return js, md


def _meta(svc: Any) -> dict[str, Any]:
    doc = svc.doc("uupt-40-2007")
    tok = svc.tok()
    return {"corpus_hash": config.config_hash({"docs": [doc.sha256]}), "clean_sha256": doc.clean_sha256,
            "loader_rules_version": doc.loader_rules_version,
            "tokenizer": {"name": tok.info.name, "version": tok.info.version}}


def main(argv: list[str] | None = None, *, service: Any = None, env: Mapping[str, str] | None = None,
         model_config: Mapping[str, Any] | None = None, budget_config: Mapping[str, Any] | None = None,
         runs_dir: Path | None = None, transport: Any = None, out: Callable[[str], None] = print,
         probe: Callable[[str, str], tuple[bool, str]] | None = None, pid_alive: Callable[[int], bool] | None = None,
         sweep_config: Mapping[str, Any] | None = None, pid_alive_rpm: Callable[[int], bool] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="backend.answer.compare_c", description=__doc__.split("\n\n")[0])
    ap.add_argument("--model-profile", required=True, help="profil di config/model dengan roles memuat 'c'")
    ap.add_argument("--items", nargs="*", default=None, help="item_id; bawaan: butir scene_checked bersumber tersimpan")
    ap.add_argument("--source-profile", default=SOURCE_PROFILE)
    ap.add_argument("--project-only", action="store_true", help="cetak proyeksi biaya; tanpa panggilan")
    ap.add_argument("--grade", action="store_true", help="sel 2x2 offline atas jawaban tersimpan profil ini (tanpa model)")
    ap.add_argument("--break-stale-lock", action="store_true", help="profil lokal: hapus kunci GPU kedaluwarsa (pid tak hidup) lalu lanjut")
    a = ap.parse_args(argv)

    from backend.api.service import Service
    from backend.spark.settings import load_configs
    svc = service or Service()
    if runs_dir is not None:
        svc.runs_dir = Path(runs_dir)
    if model_config is None or budget_config is None:
        m, b = load_configs()
        model_config, budget_config = model_config or m, budget_config or b
    try:
        eff_model, sweep_cfg = sweep_run.resolve_profile(model_config, a.model_profile, sweep_config)  # non-sapuan: tak membaca
        if sweep_cfg is not None:
            sweep_run.validate_runner_cfg(sweep_cfg)
    except ConfigInvalid as exc:
        print(f"error: {str(exc)[:200]}", file=sys.stderr)
        return 2
    prof = eff_model.get("profiles", {}).get(a.model_profile)
    if prof is None or "c" not in (prof.get("roles") or []):
        print(f"error: profile {a.model_profile!r} is unknown or has no role 'c'", file=sys.stderr)
        return 2
    if a.model_profile == a.source_profile:
        print("error: the comparison profile must differ from the source profile", file=sys.stderr)
        return 2
    if sweep_cfg is not None and (a.source_profile in sweep_run.sweep_profile_names(sweep_cfg)):
        print("error: the source profile must be a non-sweep profile (Contributor answers)", file=sys.stderr)
        return 2
    if a.grade:  # S14 (c)(d): offline, tanpa Model API, tanpa ledger
        from backend.verifier import VerifierConfigError, parse_verifier_config
        try:
            vcfg = parse_verifier_config(svc.cfg("verifier"))
        except (VerifierConfigError, config.ConfigError) as exc:
            print(f"error: verifier configuration is invalid: {str(exc)[:200]}", file=sys.stderr)
            return 2
        cells = grade_cells(svc, svc.runs_dir / "answers", a.model_profile, vcfg, a.items)
        if not cells:
            print(f"error: no stored answers for profile {a.model_profile!r}", file=sys.stderr)
            return 2
        js, md = write_grade_report(svc.runs_dir, a.model_profile, str(prof.get("label") or a.model_profile), cells)
        out(f"graded {len(cells)} answers offline; report={js}")
        return 0
    if env is None:
        from dotenv import dotenv_values
        env = {k: v for k, v in dotenv_values(config.REPO_ROOT / ".env").items() if v}

    plans, warnings = build_plans(svc, svc.runs_dir, a.items, a.source_profile)
    for w in warnings:
        out(f"warning: {w}")
    ok_plans = [p for p in plans if p.bundle is not None]
    for p in plans:
        if p.bundle is None:
            out(f"skip {p.item_id} {p.slot}: {p.skip_reason}")
    if not ok_plans:
        print("error: nothing to run (no reproducible stored Contributor answers)", file=sys.stderr)
        return 2

    client = SparkClient(a.model_profile, model_config=model_config, budget_config=budget_config, env=env,
                         runs_dir=svc.runs_dir, transport=transport, **({"sweep_config": sweep_cfg} if sweep_cfg is not None else {}))
    local = profile_api(prof) == API_CHAT
    gate = None
    if sweep_cfg is not None and not local:  # D13/P14/S20 (a): gerbang G-36 per butir atas pool sapuan, SEBELUM jaringan.
        # `per_call_micros` sudah batas atas sadar-floor (tanpa cache): batas atas butir = jumlahnya (`upper_floor`), tanpa faktor ganda
        from backend.header_b.compare import make_gate
        gate = make_gate(prof["provider"], budget_config, model_config, env, svc.runs_dir, sweep_cfg=sweep_cfg)
    # Satu batch per (item): dua kolom, supaya proyeksi dan cap diperiksa sebelum jaringan.
    by_item: dict[str, list[Plan]] = {}
    for p in ok_plans:
        by_item.setdefault(p.item_id, []).append(p)
    meta = _meta(svc)
    total = 0
    for iid, ps in by_item.items():
        calls = [make_call(p.prompt, p.bundle, meta) for p in ps]  # type: ignore[arg-type]
        try:
            proj = client.project_batch(calls)
        except ConfigInvalid as exc:
            print(f"error: {str(exc)[:200]}", file=sys.stderr)
            return 2
        total += proj.total_micros
        if gate is not None:
            v = gate([0], sum(proj.per_call_micros))
            out(f"{iid}: gate upper_bound={v.batas_atas} spent_sweep_pool={v.spent} ok={v.ok} reasons={list(v.reasons)}")
        n_cached = sum(1 for c in proj.per_call_micros if c == 0 and not local)
        out(f"{iid}: calls={len(calls)} projected micro-USD={proj.total_micros} ({format_usd_micros(proj.total_micros)})"
            + (" [local, cost 0]" if local else f" cached={n_cached}") + f" verdict={proj.verdict}")
    out(f"total projected micro-USD={total} ({format_usd_micros(total)}) profile={a.model_profile} "
        f"model={prof.get('model')} quantization={prof.get('quantization')} effort={prof.get('reasoning_effort') or model_config['effort']['c']}")
    if a.project_only:
        return 0
    lock = None
    rpm = None
    if sweep_run.uses_model_api_lock(prof):  # P9/S18 (d): runner sapuan Contributor serial, SEBELUM request apa pun
        from backend.spark import rpmlock
        try:
            rpm = rpmlock.acquire(svc.runs_dir, "sweep-c", break_stale=a.break_stale_lock,
                                  **({"pid_alive": pid_alive_rpm} if pid_alive_rpm is not None else {}))
        except rpmlock.RpmLockError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
    if local:  # H-101 S16: kunci GPU eksklusif (Glimmer vs embedding), diambil SEBELUM request apa pun ke 127.0.0.1
        from backend import gpulock
        try:
            lock = gpulock.acquire(svc.runs_dir, "glimmer-c", break_stale=a.break_stale_lock,
                                   **({"pid_alive": pid_alive} if pid_alive is not None else {}))
        except gpulock.GpuLockError as exc:
            print(f"error: {exc}", file=sys.stderr)
            if rpm is not None:
                rpm.release()
            return 3
    try:
        if local:
            from backend.spark import local_server
            ok, why = (probe or local_server.probe_models)(prof.get("base_url", ""), prof.get("model", ""))
            if not ok:
                print(f"error: {why}", file=sys.stderr)
                return 3
        rc = 0
        for iid, ps in by_item.items():
            slots = [(p.slot, p.bundle) for p in ps]
            prompt = ps[0].prompt
            if gate is not None:  # S20 (a): butir ditolak gerbang -> `not_run` (bukan gagal model), 0 request
                calls = [make_call(p.prompt, p.bundle, meta) for p in ps]  # type: ignore[arg-type]
                proj = client.project_batch(calls)
                v = gate([0], sum(proj.per_call_micros))
                if not v.ok:
                    rc = 3
                    out(f"{iid}: not_run (gate rejected: {','.join(v.reasons)}; upper_bound={v.batas_atas} spent={v.spent})")
                    continue
            try:
                outcomes, _ = run_answers(client, prompt, slots, item_id=iid, model_profile=a.model_profile, meta=meta,  # type: ignore[arg-type]
                                          answers_dir=svc.runs_dir / "answers")
            except BudgetExceeded as exc:
                print(f"error: budget_exceeded: {str(exc)[:200]}", file=sys.stderr)
                return 3
            for o in outcomes:
                if o.error is not None:
                    rc = 4
                    out(f"{iid} {o.slot}: ERROR {o.error['code']} run_id={o.run.run_id}")
                else:
                    out(f"{iid} {o.slot}: {o.answer['output']['status']} run_status={o.run.status} "
                        f"cost_micro_usd={o.run.cost_usd_micros} answer_id={o.answer['answer_id'][:12]}")
        return rc
    finally:
        if lock is not None:
            lock.release()
        if rpm is not None:
            rpm.release()

if __name__ == "__main__":
    raise SystemExit(main())
