"""CLI M3.1: `uv run python -m backend.header_b --granularity {pasal,ayat} [--chunker fixed_size] --sample N [--project-only]`.

`--project-only`: proyeksi biaya dan waktu seluruh korpus (semua sumber), tanpa panggilan, ditulis ke
`runs/headers/projection/`. Tanpa flag itu: panggilan live berurutan untuk N unit pertama (urutan dokumen) setelah
proyeksi sampel dan pemeriksaan cap `config/budget`."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from backend import config
from backend.spark import BudgetExceeded, Ledger, SparkClient, effective_caps, format_usd_micros
from backend.tokenizer import get_tokenizer

from .caller import run_headers
from .project import write_projection
from .run import DEFAULT_DOC, load_all_configs, prepare, project
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.header_b")
    ap.add_argument("--granularity", choices=("pasal", "ayat"))
    ap.add_argument("--chunker", choices=("structure_handwritten", "fixed_size"), default="structure_handwritten",
                    help="fixed_size (H-069): satu header per potongan fixed_size; granularity diabaikan")
    ap.add_argument("--sample", type=int, default=0, help="N unit pertama (urutan dokumen)")
    ap.add_argument("--project-only", action="store_true")
    ap.add_argument("--rpm", type=int, default=None, help="default [limits].max_rpm di config/model")
    ap.add_argument("--profile", default=None)
    a = ap.parse_args(argv)

    hc, model_cfg, budget_cfg, rcfg, gcfg = load_all_configs()
    tok = get_tokenizer()
    gran = a.granularity or hc["granularity"]
    source = "fixed_size" if a.chunker == "fixed_size" else gran
    kw = dict(tokenizer=tok, header_cfg=hc, retrieval_cfg=rcfg, grid_cfg=gcfg)

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

    if a.sample < 1:
        print("error: --sample N (N >= 1) is required for a live run", file=sys.stderr)
        return 2
    p = prepare(source, **kw)
    sm = project(p, tok, hc, model_cfg, profile=a.profile, rpm=a.rpm, limit=a.sample)
    print(_fmt(sm))
    caps = effective_caps(budget_cfg, None)
    ledger = Ledger(config.REPO_ROOT / "runs")
    cost = sm["cost_usd_micros"]["upper_cached"]
    if ledger.spent(role="b") + cost > caps.per_role_micros["b"] or ledger.spent() + cost > caps.total_micros:
        print("error: budget_exceeded (projection over config/budget); nothing was sent", file=sys.stderr)
        return 3
    from dotenv import dotenv_values
    env = {k: v for k, v in dotenv_values(config.REPO_ROOT / ".env").items() if v}
    client = SparkClient(a.profile or model_cfg["default_profile"], model_config=model_cfg, budget_config=budget_cfg,
                         env=env, runs_dir=config.REPO_ROOT / "runs")
    meta = {"corpus_hash": config.config_hash({"docs": [p.doc.sha256]}), "clean_sha256": p.doc.clean_sha256,
            "loader_rules_version": p.doc.loader_rules_version, "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
    try:
        res = run_headers(client, p.prompt, p.prefix, p.units[:a.sample], granularity=source, tokenizer=tok,
                          headers_dir=config.REPO_ROOT / "runs" / "headers", max_header_tokens=hc["max_header_tokens"],
                          max_output_tokens=hc["max_output_tokens"], max_consecutive_errors=hc["max_consecutive_errors"],
                          warm_max_output_tokens=hc["warm_max_output_tokens"],
                          meta=meta)
    except BudgetExceeded as exc:
        print(f"error: budget_exceeded: {exc}", file=sys.stderr)
        return 3
    for o in res.outcomes:
        print(f"[{o.unit.address}] " + (o.headers[0]["header"] if o.headers else f"ERROR {o.error}"))
    print(f"outcomes={len(res.outcomes)} stopped={res.stopped_reason}")
    return 0 if res.stopped_reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
