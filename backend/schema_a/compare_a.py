"""CLI H-100: peran A untuk profil pembanding open-weight (Spark Open Baseten, Glimmer lokal).

Masukan sama persis dengan induksi Contributor tersimpan (prompt A saat ini, sampel = `sample` versi Spark pertama
keluarga itu, `clean_sha256` dicek). Hasil disimpan di store pembanding `runs/schemas/<family>/compare/<profile>/`,
tidak pernah aktif dan tidak menyentuh store utama, grid, atau profil (G-38). Diff dibandingkan dengan versi Spark
Contributor dan versi operator terbaru.

    uv run python -m backend.schema_a.compare_a --model-profile baseten_open --project-only
    uv run python -m backend.schema_a.compare_a --model-profile baseten_open [--family uupt akta]
    uv run python -m backend.schema_a.compare_a --model-profile glimmer_local --diff

Proyeksi + gerbang `[batch_gate]` (G-36) atas batas atas `MAX_ATTEMPTS` upaya sebelum panggilan apa pun; profil lokal
(Glimmer) berbiaya 0 dan diperiksa ketersediaannya dulu. Keluaran gagal validasi tidak di-cache; diulang paling banyak
`MAX_ATTEMPTS` kali, lalu gagal jujur. `--project-only` dan `--diff` tidak memanggil apa pun dan tidak menulis."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend import config
from backend.spark import BudgetExceeded, ConfigInvalid, Ledger, SparkClient, format_usd_micros
from backend.spark.settings import API_CHAT, profile_api
from backend.spark.store import canonical_json, sha256_hex

from .ops import ParentNotFound, SampleDoc, SampleHashMismatch, diff_bodies, induce, latest, make_call
from .prompt import load_prompt
from .schema import FAMILIES
from .store import SchemaStore, SchemaStoreError

ROLE = "a"
MAX_ATTEMPTS = 2  # usulan agen (O1): keluaran tak sah tidak di-cache, upaya ulang membayar penuh
RETRY_CODES = ("semantic_invalid", "schema_invalid", "incomplete")


@dataclass
class FamilyPlan:
    family: str
    samples: list[SampleDoc]
    meta: dict[str, Any]
    call: dict[str, Any]
    source_version: int


def source_record(store: SchemaStore, family: str) -> dict[str, Any]:
    """Versi Spark pertama store utama (induksi Contributor) = sumber sampel pembanding."""
    rec = next((r for r in store.list(family) if r.get("source") == "spark"), None)
    if rec is None or not rec.get("sample"):
        raise ParentNotFound(f"no Contributor (source spark) schema with a sample for family {family!r}")
    return rec


def load_samples(rec: Mapping[str, Any], load_doc: Callable[[str], Any]) -> list[Any]:
    docs = []
    for m in rec["sample"]:
        doc = load_doc(m["doc_id"])
        if doc.clean_sha256 != m["clean_sha256"]:
            raise SampleHashMismatch(m["doc_id"])
        docs.append(doc)
    return docs


def build_meta(docs: list[Any], tok: Any) -> dict[str, Any]:
    """Sama dengan route W2 (`backend/api/routers/schemas.py`)."""
    clean = docs[0].clean_sha256 if len(docs) == 1 else sha256_hex(canonical_json(sorted(d.clean_sha256 for d in docs)))
    return {"corpus_hash": sha256_hex(canonical_json(sorted(d.sha256 for d in docs))), "clean_sha256": clean,
            "loader_rules_version": docs[0].loader_rules_version,
            "tokenizer": {"name": tok.info.name, "version": tok.info.version}}


def diff_report(main: SchemaStore, cmp: SchemaStore, family: str) -> dict[str, Any]:
    """Diff tiap versi pembanding vs Spark Contributor (versi Spark pertama) dan operator terbaru store utama."""
    records = main.list(family)
    src = next((r for r in records if r.get("source") == "spark"), None)
    op = latest(records, "operator")
    rows = []
    for r in cmp.list(family):
        row: dict[str, Any] = {"compare_version": r["schema_version"], "model_profile": r.get("model_profile"),
                               "run_id": r.get("run_id"), "levels": len(r["body"].get("levels", [])),
                               "default_chunk_level": r["body"].get("default_chunk_level")}
        if src is not None:
            row["vs_contributor"] = {"version": src["schema_version"], "changed": diff_bodies(src["body"], r["body"])}
        if op is not None:
            row["vs_operator"] = {"version": op["schema_version"], "changed": diff_bodies(op["body"], r["body"])}
        rows.append(row)
    return {"family": family, "compare_profile": cmp.compare_profile, "records": rows,
            "rejected": [{"run_id": x.get("run_id"), "errors": x.get("errors", [])[:5]} for x in cmp.list_rejected(family)]}


def _gate(budget_cfg: Mapping[str, Any], expected: list[int], spent: int) -> Any:
    from backend.proposal.gate import evaluate_gate, load_gate_config
    return evaluate_gate(expected, spent, load_gate_config(budget_cfg))


def main(argv: list[str] | None = None, *, env: Mapping[str, str] | None = None,
         model_config: Mapping[str, Any] | None = None, budget_config: Mapping[str, Any] | None = None,
         runs_dir: Path | None = None, transport: Any = None, out: Callable[[str], None] = print,
         probe: Callable[[str, str], tuple[bool, str]] | None = None, load_doc: Callable[[str], Any] | None = None,
         tokenizer: Any = None, pid_alive: Callable[[int], bool] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="backend.schema_a.compare_a", description=__doc__.split("\n\n")[0])
    ap.add_argument("--model-profile", required=True, help="profil pembanding di config/model dengan roles memuat 'a'")
    ap.add_argument("--family", nargs="+", choices=FAMILIES, default=list(FAMILIES))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--project-only", action="store_true", help="proyeksi + gerbang; tanpa panggilan, tanpa tulis")
    g.add_argument("--diff", action="store_true", help="diff skema pembanding tersimpan (JSON); tanpa panggilan")
    ap.add_argument("--break-stale-lock", action="store_true", help="profil lokal: hapus kunci GPU kedaluwarsa (pid tak hidup) lalu lanjut")
    a = ap.parse_args(argv)

    runs = Path(runs_dir) if runs_dir is not None else config.REPO_ROOT / "runs"
    if model_config is None or budget_config is None:
        from backend.spark.settings import load_configs
        m, b = load_configs()
        model_config, budget_config = model_config or m, budget_config or b
    prof = model_config.get("profiles", {}).get(a.model_profile)
    if prof is None or ROLE not in (prof.get("roles") or []):
        print(f"error: profile {a.model_profile!r} is unknown or has no role 'a'", file=sys.stderr)
        return 2
    if a.model_profile == model_config.get("default_profile") or prof.get("for_reported_numbers"):
        print("error: the comparison profile must not be the default profile or a reported-numbers profile", file=sys.stderr)
        return 2
    main_store = SchemaStore(runs)
    cmp_store = SchemaStore(runs, compare_profile=a.model_profile)
    try:
        if a.diff:
            out(json.dumps([diff_report(main_store, cmp_store, f) for f in a.family], ensure_ascii=False, indent=1))
            return 0
        if load_doc is None:
            from backend.corpus import load_corpus as load_doc  # type: ignore[no-redef]
        if tokenizer is None:
            from backend.tokenizer import get_tokenizer
            tokenizer = get_tokenizer()
        prompt = load_prompt()
        plans: list[FamilyPlan] = []
        for fam in a.family:
            src = source_record(main_store, fam)
            docs = load_samples(src, load_doc)
            samples = [SampleDoc(d.doc_id, d.text, d.clean_sha256) for d in docs]
            meta = build_meta(docs, tokenizer)
            plans.append(FamilyPlan(fam, samples, meta, make_call(prompt, fam, samples, tokenizer.count, meta),
                                    src["schema_version"]))
    except (ParentNotFound, SampleHashMismatch, SchemaStoreError) as exc:
        print(f"error: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
        return 1

    if env is None:
        from dotenv import dotenv_values
        env = {k: v for k, v in dotenv_values(config.REPO_ROOT / ".env").items() if v}
    try:
        client = SparkClient(a.model_profile, model_config=model_config, budget_config=budget_config, env=env,
                             runs_dir=runs, transport=transport)
        local = profile_api(prof) == API_CHAT
        per_attempt: list[int] = []
        for p in plans:
            proj = client.project_batch([p.call])
            per_attempt.append(proj.total_micros)
            out(f"{p.family}: est_input={p.call['est_input']} projected micro-USD per attempt={proj.total_micros} "
                f"({format_usd_micros(proj.total_micros)})" + (" [local, cost 0]" if local else "")
                + f" source=v{p.source_version} samples={[s.doc_id for s in p.samples]} client_verdict={proj.verdict}")
        verdict = _gate(budget_config, per_attempt * MAX_ATTEMPTS, Ledger(runs).spent())
    except ConfigInvalid as exc:
        print(f"error: {str(exc)[:200]}", file=sys.stderr)
        return 2
    out(f"gate [batch_gate] over {MAX_ATTEMPTS} attempts: expected={verdict.expected} upper_bound={verdict.batas_atas} "
        f"spent={verdict.spent} ok={verdict.ok} reasons={list(verdict.reasons)} profile={a.model_profile} "
        f"model={prof.get('model')} quantization={prof.get('quantization')} "
        f"effort={prof.get('reasoning_effort') or model_config['effort'][ROLE]}")
    if a.project_only:
        return 0
    if not verdict.ok:
        print("error: projection rejected by [batch_gate]; nothing was sent", file=sys.stderr)
        return 3
    lock = None
    if local:  # H-101 S16: kunci GPU eksklusif (Glimmer vs embedding), diambil SEBELUM request apa pun ke 127.0.0.1
        from backend import gpulock
        try:
            lock = gpulock.acquire(runs, "glimmer-a", break_stale=a.break_stale_lock,
                                   **({"pid_alive": pid_alive} if pid_alive is not None else {}))
        except gpulock.GpuLockError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
    try:
        if local:
            from backend.spark import local_server
            ok, why = (probe or local_server.probe_models)(prof.get("base_url", ""), prof.get("model", ""))
            if not ok:
                print(f"error: {why}", file=sys.stderr)
                return 3
        rc = 0
        for p in plans:
            res = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    res = induce(client, prompt, family=p.family, samples=p.samples, count_tokens=tokenizer.count,
                                 meta=p.meta, store=cmp_store, extra={"model_profile": a.model_profile})
                except BudgetExceeded as exc:
                    print(f"error: budget_exceeded: {str(exc)[:200]}", file=sys.stderr)
                    return 3
                except SchemaStoreError as exc:
                    print(f"error: SchemaStoreError: {str(exc)[:200]}", file=sys.stderr)
                    return 1
                r = res.run
                out(f"{p.family} attempt {attempt}: run_status={r.status} cost_micro_usd={r.cost_usd_micros} "
                    f"run_id={r.run_id} " + (f"saved compare v{res.record['schema_version']}" if res.record
                                             else f"ERROR {res.error['code']}"))
                if res.record is not None or (res.error or {}).get("code") not in RETRY_CODES:
                    break
            if res is None or res.record is None:
                rc = 4
        return rc

    finally:
        if lock is not None:
            lock.release()

if __name__ == "__main__":
    raise SystemExit(main())
