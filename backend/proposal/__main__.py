"""CLI batch D `unanswerable` (H-092 P10, H-099 V1/V9): `uv run python -m backend.proposal unanswerable --family akta|uupt
[--doc <doc_id> ...] --project-only | --run [--device cpu]`.

Keluarga sah dari satu sumber (`prompt.FAMILIES_U`); `--family` lain = exit 2 sebelum apa pun. Tanpa `--doc` = semua dokumen
keluarga itu di korpus. Prompt per (keluarga, mode) lewat `prompt.prompt_for` (akta v2, uupt v3).

`--project-only`: proyeksi per dokumen, total `expected`, `batas_atas` (faktor ulang G-36) dan putusan gerbang; tidak memanggil Spark dan
tidak menulis apa pun. `--run`: menolak (exit 3, nol panggilan) bila gerbang gagal; selain itu memanggil `ProposalService.generate`
(jalur yang sama dengan W4: cache, RunRecord). Kumulatif terpakai dari `RunRecord` tersimpan (`Ledger`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from backend import config
from backend.api.errors import ApiError
from backend.api.service import Service
from backend.spark import BudgetExceeded, ConfigInvalid, Ledger, SparkClient, format_usd_micros, load_configs, profile_provider, provider_caps

from . import prompt as promptmod
from .absence import load_absence_config, service_checker_provider
from .gate import cumulative_threshold_for, evaluate_gate, expected_cost_micros, load_gate_config
from .prompt import FAMILIES_U, MODE_U
from .service import DocInfo, ProposalService

FAMILY = "akta"  # default `--family` saja; daftar sah = FAMILIES_U


def _pricing(model_cfg: dict[str, Any], profile: str) -> dict[str, int]:
    prof = model_cfg["profiles"][profile]
    raw = model_cfg["pricing"][prof.get("pricing", profile)]
    return {k: raw[f"{k}_per_mtok_micros"] for k in ("input", "cached", "output")}


def _default_client_factory(profile: str, model_cfg: dict, budget_cfg: dict, runs_dir: Path) -> Callable[[], SparkClient]:
    def make() -> SparkClient:
        from dotenv import dotenv_values
        env = {k: v for k, v in dotenv_values(config.REPO_ROOT / ".env").items() if v}
        return SparkClient(profile, model_config=model_cfg, budget_config=budget_cfg, env=env, runs_dir=runs_dir)
    return make


def main(argv: list[str] | None = None, *, base: Service | None = None, model_cfg: dict | None = None,
         budget_cfg: dict | None = None, spent: int | None = None,
         client_factory: Callable[[], SparkClient] | None = None, checker_provider: Callable | None = None) -> int:
    """Argumen keyword hanya untuk uji (suntikan); produksi memakai default."""
    ap = argparse.ArgumentParser(prog="python -m backend.proposal")
    ap.add_argument("command", choices=("unanswerable",))
    ap.add_argument("--family", default=FAMILY)
    ap.add_argument("--doc", action="append", default=None, help="doc_id (boleh berulang); default semua dokumen keluarga di korpus")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--project-only", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--device", default=None, help="perangkat encoder dense, mis. cpu (VRAM dipakai Glimmer, H-047)")
    ap.add_argument("--profile", default=None)
    a = ap.parse_args(argv)
    family = a.family
    if family not in FAMILIES_U:
        print(f"error: mode 'unanswerable' is only available for families: {', '.join(FAMILIES_U)}", file=sys.stderr)
        return 2
    base = base or Service()
    try:
        if model_cfg is None or budget_cfg is None:
            model_cfg, budget_cfg = load_configs()
        gcfg = load_gate_config(budget_cfg)
        acfg = load_absence_config(base.config_dir)
        prm = promptmod.prompt_for(family, MODE_U)
    except ConfigInvalid as exc:
        print(f"error: config_invalid: {exc}", file=sys.stderr)
        return 2
    cap = acfg.cap_for(family)
    ids = base.doc_ids(family)
    if a.doc:
        unknown = [d for d in a.doc if d not in ids]
        if unknown:
            print(f"error: unknown doc_id {unknown[0]!r}; known: {', '.join(ids)}", file=sys.stderr)
            return 2
        ids = [d for d in ids if d in a.doc]
    profile = a.profile or model_cfg["default_profile"]
    pricing = _pricing(model_cfg, profile)
    docs = [base.doc(i) for i in ids]
    expected = []
    for d in docs:
        text = promptmod.render_input(prm, d.doc_id, d.text, MODE_U, cap, d.clean_sha256)
        n_in = int(base.tok().count(text))
        expected.append(expected_cost_micros(n_in, acfg.projection_expected_output_tokens, pricing))
        print(f"  {d.doc_id:<10} input_tokens={n_in} output_tokens(assumed)={acfg.projection_expected_output_tokens} "
              f"expected micro-USD={expected[-1]} ({format_usd_micros(expected[-1])})")
    try:
        pcaps = provider_caps(budget_cfg, model_cfg)
        prov = profile_provider(model_cfg, profile)
    except ConfigInvalid as exc:
        print(f"error: config_invalid: {exc}", file=sys.stderr)
        return 2
    # S9 (e): pool default = belanja rekaman provider tak berplafon; provider berplafon = pool-nya sendiri (H-101 P6/P9).
    used = spent if spent is not None else Ledger(base.runs_dir).spent_pool(prov, pcaps, model_cfg=model_cfg)
    thr = cumulative_threshold_for(prov, budget_cfg, pcaps)
    v = evaluate_gate(expected, used, gcfg) if prov not in pcaps else evaluate_gate(expected, used, gcfg, threshold_micros=thr)
    print(f"prompt {prm.version} {prm.prompt_hash[:12]} schema {promptmod.SCHEMA_NAME_U} {promptmod.schema_hash(MODE_U)[:12]} "
          f"factor_bp={gcfg.factor_bp} (assumption, not measured for D) family={family} max_per_call={cap}")
    print(f"total expected={v.expected} batas_atas={v.batas_atas} ({format_usd_micros(v.batas_atas)}) cumulative_spent={v.spent} "
          f"batch_cap={gcfg.batch_cap_micros} cumulative_threshold={thr}")
    print("gate: " + ("PASS" if v.ok else "REFUSED (" + ", ".join(v.reasons) + ")"))
    if a.project_only:
        return 0
    if not v.ok:
        print("error: batch gate refused; nothing was sent", file=sys.stderr)
        return 3

    def doc_provider(doc_id: str) -> DocInfo | None:
        try:
            d = base.doc(doc_id)
        except ApiError:
            return None
        return DocInfo(d.doc_id, d.family, d.text, d.clean_sha256)

    svc = ProposalService(runs_dir=base.runs_dir, butir_dir=base.butir_dir, doc_provider=doc_provider, config_dir=base.config_dir,
                          count_tokens=lambda t: int(base.tok().count(t)),
                          checker_provider=checker_provider or service_checker_provider(base, device=a.device))
    make = client_factory or _default_client_factory(profile, model_cfg, budget_cfg, base.runs_dir)
    for d in docs:
        try:
            out = svc.generate(family, d.doc_id, [MODE_U], profile=profile, model_config=model_cfg, client_factory=make)
        except (ApiError, BudgetExceeded) as exc:
            print(f"error: {d.doc_id}: {getattr(exc, 'message', exc)}", file=sys.stderr)
            return 1
        flagged = sum(1 for p in out["proposals"] if p["absence_check"]["status"] == "doubtful")
        print(f"{d.doc_id}: run={out['runs'][0]['status']} proposals={len(out['proposals'])} doubtful={flagged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
