"""CLI M3.1: `uv run python -m backend.header_b --granularity {pasal,ayat} [--chunker fixed_size] --sample N [--project-only]`.

`--project-only`: proyeksi biaya dan waktu seluruh korpus (semua sumber), tanpa panggilan, ditulis ke
`runs/headers/projection/`. Tanpa flag itu: panggilan live berurutan untuk N unit pertama (urutan dokumen) setelah
proyeksi sampel dan pemeriksaan cap `config/budget`."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from backend import config
from backend.grid.headers import header_store_dir
from backend.spark import (BudgetExceeded, Ledger, SparkClient, effective_caps, format_usd_micros, pool_limits,
                           profile_provider)
from backend.proposal.gate import cumulative_threshold_for
from backend.tokenizer import get_tokenizer

from .caller import run_headers
from .family import precheck, prepare_family, project_family, run_family
from .project import write_projection
from .schema import plan_schema, project_schema
from .run import (DEFAULT_DOC, HeaderConfigError, find_unit, load_all_configs, prepare, project, run_smoke,
                  smoke_projection)
from .units import SOURCES


def _fmt(p: dict) -> str:
    c, t = p["cost_usd_micros"], p["time"]
    return (f"  {p['source']:<10} units={p['units']:>5} calls={p['calls']:>5} prefix_tokens={p['prefix_tokens']} "
            f"src_tokens={p['source_tokens_total']}\n"
            f"             cost micro-USD expected={c['expected']} ({format_usd_micros(c['expected'])}) "
            f"upper_cached={c['upper_cached']} ({format_usd_micros(c['upper_cached'])}) "
            f"upper_no_cache={c['upper_no_cache']} ({format_usd_micros(c['upper_no_cache'])})\n"
            f"             time @ {p['rpm']} RPM, latency {p['assumed_latency_ms']} ms (assumed): "
            f"rpm_floor={t['rpm_floor_seconds']}s sequential={t['sequential_seconds']}s estimated={t['estimated_seconds']}s")


def _schema_record(a):
    from backend.grid.schemas import SchemaBinding
    rec = SchemaBinding.from_store(config.REPO_ROOT / "runs", a.family).active()  # H-075: versi operator tertinggi, bila tak ada Spark
    if rec is None:
        print(f"error: no schema A record for family {a.family!r} in runs/schemas", file=sys.stderr)
    return rec


def _fmt_schema(r: dict) -> str:
    head = f"  structure_schema chunks={r['chunks']} already_stored={r['already_stored']} to_call={r['to_call']}"
    if not r["to_call"]:
        return head + "\n  cost micro-USD (to_call only): 0"
    return head + "\n" + _fmt({**r["projection"], "source": "schema/call"})


def _client(a, model_cfg, budget_cfg):
    from dotenv import dotenv_values
    env = {k: v for k, v in dotenv_values(config.REPO_ROOT / ".env").items() if v}
    return SparkClient(a.profile or model_cfg["default_profile"], model_config=model_cfg, budget_config=budget_cfg,
                       env=env, runs_dir=config.REPO_ROOT / "runs")


def _smoke(a, hc, model_cfg, budget_cfg, tok, source, kw) -> int:
    if not a.unit:
        print("error: --smoke requires --unit <address|chunk_id>", file=sys.stderr)
        return 2
    p = prepare(source, **kw)
    try:
        unit = find_unit(p, a.unit)
    except HeaderConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sm = smoke_projection(p, unit, tok, hc, model_cfg, profile=a.profile, rpm=a.rpm)
    print(_fmt(sm))
    print(f"  smoke: 1 call, no warm-up request (cost above includes one warm-up that is NOT sent), "
          f"prompt {p.prompt.version} {p.prompt.prompt_hash[:12]}, schema maxLength={hc.get('schema_max_length_chars')}")
    caps = effective_caps(budget_cfg, None)
    prov = profile_provider(model_cfg, a.profile)
    ledger = Ledger(config.REPO_ROOT / "runs")
    cost = sm["cost_usd_micros"]["upper_no_cache"]
    sr, rc, st, tc = pool_limits(ledger, caps, prov, "b")
    if sr + cost > rc or st + cost > tc:
        print("error: budget_exceeded (projection over config/budget); nothing was sent", file=sys.stderr)
        return 3
    client = _client(a, model_cfg, budget_cfg)
    meta = {"corpus_hash": config.config_hash({"docs": [p.doc.sha256]}), "clean_sha256": p.doc.clean_sha256,
            "loader_rules_version": p.doc.loader_rules_version, "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
    out = run_smoke(client, p, unit, tokenizer=tok, header_cfg=hc, headers_dir=config.REPO_ROOT / "runs" / "headers", meta=meta)
    print(f"{out['status']} error_code={out['error_code']} unit={out['unit']} run_id={out['run_id']}")
    if out["header"]:
        print(f"header: {out['header']}")
    return {"accepted": 0, "rejected_by_api": 1}.get(out["status"], 4)


def _schema_main(a, hc, model_cfg, budget_cfg, tok, kw) -> int:
    p = prepare("structure_schema", **kw)
    hdir = config.REPO_ROOT / "runs" / "headers"
    plan = plan_schema(p, headers_dir=hdir, limit=a.sample or None)
    res = project_schema(p, plan, tok, hc, model_cfg, profile=a.profile, rpm=a.rpm)
    print(_fmt_schema(res))
    if a.project_only:
        path = (config.REPO_ROOT / "runs" / "headers" / "projection"
                / f"{DEFAULT_DOC}-{p.doc.clean_sha256[:12]}-{p.prompt.prompt_hash[:12]}-structure_schema.json")
        write_projection(path, {"created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "structure_schema": res})
        print(f"written: {path.relative_to(config.REPO_ROOT)}")
        return 0
    if a.sample < 1:
        print("error: --sample N (N >= 1) is required for a live run", file=sys.stderr)
        return 2
    caps = effective_caps(budget_cfg, None)
    prov = profile_provider(model_cfg, a.profile)
    ledger = Ledger(config.REPO_ROOT / "runs")
    cost = res["projection"]["cost_usd_micros"]["upper_cached"]
    sr, rc, st, tc = pool_limits(ledger, caps, prov, "b")
    if sr + cost > rc or st + cost > tc:
        print("error: budget_exceeded (projection over config/budget); nothing was sent", file=sys.stderr)
        return 3
    if not plan.call:
        return 0
    client = _client(a, model_cfg, budget_cfg)
    meta = {"corpus_hash": config.config_hash({"docs": [p.doc.sha256]}), "clean_sha256": p.doc.clean_sha256,
            "loader_rules_version": p.doc.loader_rules_version, "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
    try:
        run = run_headers(client, p.prompt, p.prefix, plan.call, granularity="structure_schema", tokenizer=tok, headers_dir=hdir,
                          max_header_tokens=hc["max_header_tokens"], max_output_tokens=hc["max_output_tokens"],
                          max_consecutive_errors=hc["max_consecutive_errors"], warm_max_output_tokens=hc["warm_max_output_tokens"],
                          cache_guard_calls=hc["cache_guard_calls"], cache_guard_min_ratio=hc["cache_guard_min_ratio"],
                          meta=meta, max_length_chars=hc.get("schema_max_length_chars"))
    except BudgetExceeded as exc:
        print(f"error: budget_exceeded: {exc}", file=sys.stderr)
        return 3
    for o in run.outcomes:
        print(f"[{o.unit.address}] " + (o.headers[0]["header"] if o.headers else f"ERROR {o.error}"))
    print(f"outcomes={len(run.outcomes)} stopped={run.stopped_reason}")
    return 0 if run.stopped_reason is None else 1


def _fmt_family(res: dict) -> str:
    lines = [f"factor_bp={res['factor_bp']} ({res['factor_source']}); upper_g36 = ceil(expected * factor_bp / 10000)"]
    for d, row in res["per_doc"].items():
        for s, r in row["sources"].items():
            lines.append(f"  {d} {s:<21} units={r['units']:>3} stored={r['already_stored']:>3} to_call={r['to_call']:>3} "
                         f"max_unit_tokens={r['max_unit_tokens']:>5} calls={r['calls']:>3} expected={r['expected']:>7} "
                         f"upper_g36={r['upper_g36']:>7} upper_no_cache={r['upper_no_cache']:>7}")
        lines.append(f"  {d} SUBTOTAL expected={row['expected']} upper_g36={row['upper_g36']} gate={row['gate']['verdict']}")
    t, g = res["total"], res["gate"]
    lines.append(f"TOTAL calls={t['calls']} expected={t['expected']} ({format_usd_micros(t['expected'])}) "
                 f"upper_g36={t['upper_g36']} ({format_usd_micros(t['upper_g36'])}) est_seconds={t['estimated_seconds']}")
    lines.append(f"GATE {g['verdict']}: upper_bound={g['upper_bound']} spent_cumulative={g['spent_cumulative']} "
                 f"limits single={g['single_limit']} cumulative={g['cumulative_limit']}"
                 + ("; " + "; ".join(g["reasons"]) if g["reasons"] else ""))
    return "\n".join(lines)


def _family_main(a, hc, model_cfg, budget_cfg, tok, rcfg, gcfg, gran) -> int:
    """W57: `--family akta` mengiterasi semua akta config/corpus_akta untuk sumber yang diminta (`--chunker all` = ketiganya)."""
    from backend.corpus import akta_entries
    from backend.grid.schemas import SchemaBinding
    if a.smoke:
        print("error: --smoke is single-document; not supported with --family akta", file=sys.stderr)
        return 2
    chunkers = ["structure_handwritten", "fixed_size", "structure_schema"] if a.chunker == "all" else [a.chunker]
    sources = [gran if c == "structure_handwritten" else c for c in chunkers]
    rec = None
    if "structure_schema" in sources:
        rec = SchemaBinding.from_store(config.REPO_ROOT / "runs", a.family).active()
        if rec is None:
            print(f"error: no schema A record for family {a.family!r} in runs/schemas", file=sys.stderr)
            return 2
    ids = list(akta_entries())
    if a.doc:
        ids = [d for d in ids if d == a.doc]
        if not ids:
            print(f"error: unknown akta {a.doc!r}", file=sys.stderr)
            return 2
    prepared = prepare_family(ids, sources, tokenizer=tok, header_cfg=hc, retrieval_cfg=rcfg, grid_cfg=gcfg, schema_record=rec)
    hbase = config.REPO_ROOT / "runs" / "headers"
    hdir = header_store_dir(config.REPO_ROOT / "runs", a.family)  # W63: store per keluarga; proyeksi tetap di hbase
    ledger = Ledger(config.REPO_ROOT / "runs")
    limit = a.sample or None
    prov = profile_provider(model_cfg, a.profile)
    pcaps = effective_caps(budget_cfg, None).provider_micros
    res = project_family(prepared, hdir, tok, hc, model_cfg, budget_cfg, spent=ledger.spent_pool(prov, pcaps),
                         profile=a.profile, rpm=a.rpm, limit=limit,
                         threshold=cumulative_threshold_for(prov, budget_cfg, pcaps))
    print(_fmt_family(res))
    if a.project_only:
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        for d, row in res["per_doc"].items():
            for s, r in row["sources"].items():
                p = prepared[d][s]
                write_projection(hbase / "projection" / f"{d}-{p.doc.clean_sha256[:12]}-{p.prompt.prompt_hash[:12]}-{s}.json",
                                 {"created_at": stamp, "factor_bp": res["factor_bp"], "row": r})
        first = next(iter(next(iter(prepared.values())).values()))
        path = (hbase / "projection" / f"{a.family}-{a.doc or 'all'}-{first.prompt.prompt_hash[:12]}-{'+'.join(sources)}.json")
        write_projection(path, {"created_at": stamp, **res})
        print(f"written: {path.relative_to(config.REPO_ROOT)} (+ one file per akta per source)")
        return 0
    if not a.full and not a.sample:
        print("error: live run needs --sample N (units per akta per source) or --full", file=sys.stderr)
        return 2
    caps = effective_caps(budget_cfg, None)
    sr, rc, st, tc = pool_limits(ledger, caps, prov, "b")
    err = precheck(res, spent_b=sr, spent_total=st, per_role_b_cap=rc, total_cap=tc)
    if err:
        print(f"error: {err}; nothing was sent", file=sys.stderr)
        return 3
    client = _client(a, model_cfg, budget_cfg)

    def meta_for(p):
        return {"corpus_hash": config.config_hash({"docs": [p.doc.sha256]}), "clean_sha256": p.doc.clean_sha256,
                "loader_rules_version": p.doc.loader_rules_version,
                "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
    try:
        out = run_family(client, prepared, tokenizer=tok, headers_dir=hdir, header_cfg=hc, meta_for=meta_for, limit=limit,
                         max_attempts=a.attempts, log=print)
    except BudgetExceeded as exc:
        print(f"error: budget_exceeded: {exc}", file=sys.stderr)
        return 3
    print(f"stored={out['stored']} stopped={out['stopped']} failed={ {k: len(v) for k, v in out['failed'].items()} }")
    return 0 if out["stopped"] is None and not out["failed"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.header_b")
    ap.add_argument("--granularity", choices=("pasal", "ayat"))
    ap.add_argument("--chunker", choices=("structure_handwritten", "fixed_size", "structure_schema", "all"), default="structure_handwritten",
                    help="fixed_size (H-069): satu header per potongan fixed_size; structure_schema (H-082): potongan skema A aktif, "
                         "B dipanggil untuk semua potongan (tanpa reuse header Pasal); granularity diabaikan; "
                         "all (hanya --family akta, W57): ketiga sumber sekaligus")
    ap.add_argument("--family", default="uupt", help="keluarga skema A untuk --chunker structure_schema")
    ap.add_argument("--doc", default=None, help="--family akta: satu akta saja (default: semua akta config/corpus_akta)")
    ap.add_argument("--full", action="store_true", help="--family akta, run live: semua unit (tanpa --sample)")
    ap.add_argument("--attempts", type=int, default=8, help="--family akta, run live: upaya maksimal per sumber (H-081)")
    ap.add_argument("--sample", type=int, default=0, help="N unit pertama (urutan dokumen)")
    ap.add_argument("--project-only", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="H-079: tepat SATU panggilan untuk --unit, tanpa pemanas; cetak accepted|rejected_by_api + kode galat; "
                         "header sukses tidak disimpan ke store")
    ap.add_argument("--unit", default=None, help="alamat atau chunk_id unit (dengan --smoke)")
    ap.add_argument("--rpm", type=int, default=None, help="default [limits].max_rpm di config/model")
    ap.add_argument("--profile", default=None)
    a = ap.parse_args(argv)

    hc, model_cfg, budget_cfg, rcfg, gcfg = load_all_configs()
    tok = get_tokenizer()
    gran = a.granularity or hc["granularity"]
    source = a.chunker if a.chunker in ("fixed_size", "structure_schema") else gran
    if a.family == "akta":
        return _family_main(a, hc, model_cfg, budget_cfg, tok, rcfg, gcfg, gran)
    if a.chunker == "all":
        print("error: --chunker all is only supported with --family akta", file=sys.stderr)
        return 2
    kw = dict(tokenizer=tok, header_cfg=hc, retrieval_cfg=rcfg, grid_cfg=gcfg)
    if source == "structure_schema":
        rec = _schema_record(a)
        if rec is None:
            return 2
        kw["schema_record"] = rec
        if not a.smoke:
            return _schema_main(a, hc, model_cfg, budget_cfg, tok, kw)

    if a.project_only:
        first = prepare(SOURCES[0], **kw)
        payload = {"created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "projections": {}}
        for s in SOURCES:
            p = first if s == SOURCES[0] else prepare(s, doc=first.doc, prompt=first.prompt, **kw)
            full = project(p, tok, hc, model_cfg, profile=a.profile, rpm=a.rpm)
            payload["projections"][s] = full
            print(_fmt(full))
            if a.sample:
                sm = project(p, tok, hc, model_cfg, profile=a.profile, rpm=a.rpm, limit=a.sample)
                payload["projections"][s + ":sample"] = sm
                print("  sample:\n" + _fmt(sm))
        path = config.REPO_ROOT / "runs" / "headers" / "projection" / f"{DEFAULT_DOC}-{first.doc.clean_sha256[:12]}-{first.prompt.prompt_hash[:12]}.json"
        write_projection(path, payload)
        print(f"written: {path.relative_to(config.REPO_ROOT)}")
        return 0

    if a.smoke:
        return _smoke(a, hc, model_cfg, budget_cfg, tok, source, kw)

    if a.sample < 1:
        print("error: --sample N (N >= 1) is required for a live run", file=sys.stderr)
        return 2
    p = prepare(source, **kw)
    sm = project(p, tok, hc, model_cfg, profile=a.profile, rpm=a.rpm, limit=a.sample)
    print(_fmt(sm))
    caps = effective_caps(budget_cfg, None)
    prov = profile_provider(model_cfg, a.profile)
    ledger = Ledger(config.REPO_ROOT / "runs")
    cost = sm["cost_usd_micros"]["upper_cached"]
    sr, rc, st, tc = pool_limits(ledger, caps, prov, "b")
    if sr + cost > rc or st + cost > tc:
        print("error: budget_exceeded (projection over config/budget); nothing was sent", file=sys.stderr)
        return 3
    client = _client(a, model_cfg, budget_cfg)
    meta = {"corpus_hash": config.config_hash({"docs": [p.doc.sha256]}), "clean_sha256": p.doc.clean_sha256,
            "loader_rules_version": p.doc.loader_rules_version, "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
    try:
        res = run_headers(client, p.prompt, p.prefix, p.units[:a.sample], granularity=source, tokenizer=tok,
                          headers_dir=config.REPO_ROOT / "runs" / "headers", max_header_tokens=hc["max_header_tokens"],
                          max_output_tokens=hc["max_output_tokens"], max_consecutive_errors=hc["max_consecutive_errors"],
                          warm_max_output_tokens=hc["warm_max_output_tokens"],
                          cache_guard_calls=hc["cache_guard_calls"], cache_guard_min_ratio=hc["cache_guard_min_ratio"],
                          meta=meta, max_length_chars=hc.get("schema_max_length_chars"))
    except BudgetExceeded as exc:
        print(f"error: budget_exceeded: {exc}", file=sys.stderr)
        return 3
    for o in res.outcomes:
        print(f"[{o.unit.address}] " + (o.headers[0]["header"] if o.headers else f"ERROR {o.error}"))
    print(f"outcomes={len(res.outcomes)} stopped={res.stopped_reason}")
    return 0 if res.stopped_reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
