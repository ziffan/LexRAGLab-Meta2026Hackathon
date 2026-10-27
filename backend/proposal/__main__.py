"""CLI batch D `unanswerable` (H-092 P10): `uv run python -m backend.proposal unanswerable --family akta [--doc akta-01 ...]
--project-only | --run [--device cpu]`.

`--project-only`: proyeksi per akta, total `expected`, `batas_atas` (faktor ulang G-36) dan putusan gerbang; tidak memanggil Spark dan
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
from backend.spark import BudgetExceeded, ConfigInvalid, Ledger, SparkClient, format_usd_micros, load_configs

from . import prompt as promptmod
from .absence import load_absence_config, service_checker_provider
from .gate import evaluate_gate, expected_cost_micros, load_gate_config
from .prompt import MODE_U
from .service import DocInfo, ProposalService

FAMILY = "akta"


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
    ap.add_argument("--doc", action="append", default=None, help="doc_id akta (boleh berulang); default semua akta korpus")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--project-only", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--device", default=None, help="perangkat encoder dense, mis. cpu (VRAM dipakai Glimmer, H-047)")
    ap.add_argument("--profile", default=None)
    a = ap.parse_args(argv)
    if a.family != FAMILY:
        print("error: mode 'unanswerable' is only available for family 'akta'", file=sys.stderr)
        return 2
    try:
        if model_cfg is None or budget_cfg is None:
            model_cfg, budget_cfg = load_configs()
        gcfg = load_gate_config(budget_cfg)
        acfg = load_absence_config()
    except ConfigInvalid as exc:
        print(f"error: config_invalid: {exc}", file=sys.stderr)
        return 2
    base = base or Service()
    ids = base.doc_ids(FAMILY)
    if a.doc:
        unknown = [d for d in a.doc if d not in ids]
        if unknown:
            print(f"error: unknown doc_id {unknown[0]!r}; known: {', '.join(ids)}", file=sys.stderr)
            return 2
        ids = [d for d in ids if d in a.doc]
    profile = a.profile or model_cfg["default_profile"]
    pricing = _pricing(model_cfg, profile)
    prm = promptmod.load_prompt(mode=MODE_U)
    docs = [base.doc(i) for i in ids]
    expected = []
    for d in docs:
        text = promptmod.render_input(prm, d.doc_id, d.text, MODE_U, acfg.max_per_call, d.clean_sha256)
        n_in = int(base.tok().count(text))
        expected.append(expected_cost_micros(n_in, acfg.projection_expected_output_tokens, pricing))
        print(f"  {d.doc_id:<10} input_tokens={n_in} output_tokens(assumed)={acfg.projection_expected_output_tokens} "
              f"expected micro-USD={expected[-1]} ({format_usd_micros(expected[-1])})")
    used = spent if spent is not None else Ledger(base.runs_dir).spent()
    v = evaluate_gate(expected, used, gcfg)
    print(f"prompt {prm.version} {prm.prompt_hash[:12]} schema {promptmod.SCHEMA_NAME_U} {promptmod.schema_hash(MODE_U)[:12]} "
          f"factor_bp={gcfg.factor_bp} (assumption, not measured for D)")
    print(f"total expected={v.expected} batas_atas={v.batas_atas} ({format_usd_micros(v.batas_atas)}) cumulative_spent={v.spent} "
          f"batch_cap={gcfg.batch_cap_micros} cumulative_threshold={gcfg.cumulative_threshold_micros}")
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
            out = svc.generate(FAMILY, d.doc_id, [MODE_U], profile=profile, model_config=model_cfg, client_factory=make)
        except (ApiError, BudgetExceeded) as exc:
            print(f"error: {d.doc_id}: {getattr(exc, 'message', exc)}", file=sys.stderr)
            return 1
        flagged = sum(1 for p in out["proposals"] if p["absence_check"]["status"] == "doubtful")
        print(f"{d.doc_id}: run={out['runs'][0]['status']} proposals={len(out['proposals'])} doubtful={flagged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
