"""Perlengkapan uji runner sapuan bagian B (H-103 S3): config uji (`model_b`) + `config/sweep.toml` nyata, klien sapuan, rig. Tanpa jaringan."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.spark import SparkClient
from backend.spark.sweep import load_sweep

from .h101_helpers import budget_b, hc_b, make_prepared, model_b, rig_for  # noqa: F401
from .spark_fakes import Rig


def sweep_cfg() -> dict:
    return copy.deepcopy(load_sweep())


def sweep_rig(tmp: Path, profile: str, behaviours: dict[str, list[Any]] | None = None, *, sweep: dict | None = None,
              usage: Any = None, model: dict | None = None, budget: dict | None = None, log: list[str] | None = None) -> tuple[Rig, dict]:
    """Rig dengan `rig.client` = SparkClient profil sapuan (model_config ASLI + sweep_config terpisah)."""
    from .h101_helpers import USAGE_BT
    rig = rig_for(tmp, "meta", behaviours, usage=usage or USAGE_BT, log=log, model=model, budget=budget)
    sw = sweep if sweep is not None else sweep_cfg()
    inner = rig.tr.default

    def reflect(tr: Any, request: Any) -> Any:  # server Responses memantulkan effort yang dikirim (P5)
        import json
        r = inner(tr, request) if callable(inner) else inner
        if isinstance(getattr(r, "json", None), dict) and "output" in r.json and "reasoning" not in r.json:
            e = ((json.loads(request.content.decode("utf-8")).get("reasoning")) or {}).get("effort")
            if e:
                r.json["reasoning"] = {"effort": e}
        return r

    rig.tr.default = reflect
    rig.client = SparkClient(profile, model_config=rig.model, budget_config=rig.budget, env=rig.env, runs_dir=rig.runs,
                             transport=rig.tr.transport, now=rig.clock.now, sleep=rig.clock.sleep, sweep_config=sw)
    return rig, sw


def run_main(rig: Rig, argv: list[str], *, sweep: dict | None, out: list[str] | None = None, model: dict | None = None,
             prepared: Any = None, hc: dict | None = None, **kw: Any) -> int:
    from backend.header_b import compare as cmp
    from .h101_helpers import Tok
    fake = lambda ids, sources, **k: {"uupt-x": {"pasal": prepared or make_prepared(3)}}  # noqa: E731
    return cmp.main(argv, env=rig.env, model_config=model or rig.model, budget_config=rig.budget, header_config=hc or hc_b(),
                    runs_dir=rig.runs, transport=rig.tr.transport, out=(out.append if out is not None else (lambda s: None)),
                    tokenizer=Tok(), prepare_fn=fake, probe=lambda u, m: (True, "ok"), sweep_config=sweep, **kw)


def args(profile: str, *extra: str) -> list[str]:
    return ["--model-profile", profile, "--family", "uupt", "--sources", "pasal", *extra]


def go_sweep(rig: Rig, sw: dict, prepared: Any, store_dir: Path, *, profile: str, max_attempts: int = 8, gate: Any = "auto",
             gate_cfg: dict | None = None, hc: dict | None = None, **kw: Any) -> dict:
    """`run_compare` atas profil sapuan (model efektif = `merge_sweep`); `gate="auto"` = gerbang pool sapuan nyata."""
    from backend.header_b.compare import make_gate, run_compare, select_pairs
    from backend.spark.sweep import merge_sweep
    from .h101_helpers import GATE, Tok
    from .h101_run import meta_for
    eff = merge_sweep(rig.model, sw)
    ps = prepared if isinstance(prepared, list) else [prepared]
    pm: dict[str, dict[str, Any]] = {}
    for p in ps:
        pm.setdefault(p.doc.doc_id, {})[p.source] = p
    pairs = select_pairs(pm, store_dir, **kw)
    prof = eff["profiles"][profile]
    g = {"factor_bp": GATE["factor_bp"], "batch_cap_micros": GATE["batch_cap_micros"], **(gate_cfg or {})}
    if gate == "auto":
        gate = None if prof.get("api") == "chat_completions" else make_gate(prof["provider"], rig.budget, rig.model, rig.env, rig.runs,
                                                                           sweep_cfg=sw)
    return run_compare(rig.client, pairs, profile=profile, prof=prof, model_cfg=eff, hc=hc or hc_b(), gate_cfg=g, tokenizer=Tok(),
                       store_dir=store_dir, meta_for=meta_for, max_attempts=max_attempts, gate=gate)
