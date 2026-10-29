"""Penghitung golden S19 (docs/scenarios/M3.2-effort-sweep.md): keluaran jalur bersama untuk profil yang ada.

Cara membuat `fixtures/s19_golden.json` (H-103 S3 bagian A): fungsi `compute()` dijalankan pada pohon basis bf769cf
(SEBELUM kode slice diubah) lewat `python -m backend.tests.s19_golden > backend/tests/fixtures/s19_golden.json`.
Test `test_s19_golden_main_path.py` menghitung ulang dengan kode sesudah slice dan membandingkan dengan berkas itu.
Pemanggilan Ledger memakai penyesuai `_pool` (kata kunci `model_cfg` bila API sesudah slice, tanpa itu pada basis).
Semua data sintetis, transport palsu, tanpa jaringan."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from backend import config as cfgmod
from backend.proposal.gate import GateConfig, cumulative_threshold_for, evaluate_gate, load_gate_config
from backend.spark import Ledger, effective_caps, pool_limits, store
from backend.spark import ratelimit
from backend.spark.gate import require_reportable
from backend.spark.settings import load_configs

from .m25_fakes import chat_body, env_m25
from .spark_fakes import OUT_OK, Resp, Rig, body_ok, call_args, synth

ROLES = ("a", "b", "c", "d", "measure")
UNIT = {"input_per_mtok_micros": 1_000_000, "cached_per_mtok_micros": 0, "output_per_mtok_micros": 0}


def canon(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(x: Any) -> str:
    return hashlib.sha256(canon(x).encode("utf-8")).hexdigest()


def real_configs() -> tuple[dict, dict]:
    return load_configs()


def unit_model() -> dict:
    m, _ = real_configs()
    m["pricing"]["unit"] = dict(UNIT)
    m["profiles"]["meta_unit"] = {"provider": "meta", "model": "muse-spark-1.3-contributor", "base_url_env": "MUSE_BASE_URL",
                                  "pricing": "unit", "api_key_env": "MUSE_API_KEY", "for_reported_numbers": True}
    m["profiles"]["bt_unit"] = {"provider": "baseten", "model": "meta-models/muse-spark-open-1026",
                                "base_url_env": "BASETEN_BASE_URL", "pricing": "unit", "api_key_env": "BASETEN_API_KEY",
                                "for_reported_numbers": False}
    return m


def _pool(fn, *a, model_cfg, **kw):
    try:
        return fn(*a, model_cfg=model_cfg, **kw)
    except TypeError:
        return fn(*a, **kw)


def f4(runs: Path) -> None:
    for role, prov, cost in (("a", "meta", 8_170), ("b", "meta", 526_265), ("c", "meta", 5_964), ("d", "meta", 21_342),
                             ("c", "baseten", 53_267), ("b", "baseten", 15_460_483), ("c", "lmstudio_local", 0)):
        synth(runs, role, prov, cost)


def _norm_record(rec_dict: dict) -> dict:
    d = dict(rec_dict)
    d["run_id"] = "RID"
    return d


def _call(tmp: Path, profile: str, role: str, model: dict, budget: dict) -> dict:
    chat = profile == "glimmer_local"
    dflt = Resp(200, chat_body(OUT_OK)) if chat else Resp(200, body_ok())
    r = Rig(tmp, profile=profile, model=model, budget=budget, env=env_m25(), default=dflt)
    res = r.client.call(**call_args(0, role=role, prompt_hash="P1", schema_hash="S1", input="input-x"))
    req = r.tr.requests[0]
    return {"body_sha256": sha(req["body"]), "body": req["body"], "path": req["path"],
            "record": _norm_record(res.record.to_dict()),
            "cache_key": res.record.cache_key, "config_hash": r.client.config_hash}


def compute() -> dict:
    model, budget = real_configs()
    out: dict[str, Any] = {}
    out["config_hash_main"] = cfgmod.config_hash({"model": dict(model), "budget": dict(budget)})
    # (i) body request/RunRecord/cache key per profil dan peran
    calls: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as td:
        n = 0
        for prof, roles in (("meta", ROLES), ("openrouter_dev", ("b",)), ("baseten_open", ("b", "c")),
                            ("glimmer_local", ("b", "c"))):
            for role in roles:
                n += 1
                calls[f"{prof}/{role}"] = _call(Path(td) / str(n), prof, role, model, budget)
    out["calls"] = calls
    # (b) Projection dan pool_limits atas F4
    um = unit_model()
    caps = effective_caps(budget, {}, model)
    proj: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as td:
        f4(Path(td) / "runs")
        for prof, role, micros in (("meta_unit", "b", 473_735), ("meta_unit", "b", 473_736),
                                   ("bt_unit", "c", 4_486_250), ("bt_unit", "c", 4_486_251)):
            r = Rig(Path(td), profile=prof, model=um, budget=budget, env=env_m25(), default=Resp(200, body_ok()))
            p = r.client.project_batch([call_args(1, role=role, est_input=micros, max_output_tokens=1)])
            proj[f"{prof}/{role}/{micros}"] = {k: v for k, v in p.__dict__.items()}
        led = Ledger(Path(td) / "runs")
        pl = {}
        for prov in ("meta", "baseten", "lmstudio_local", "openrouter"):
            pl[prov] = list(_pool(pool_limits, led, caps, prov, "b", model_cfg=model))
        out["pool_limits"] = pl
        out["spent_pool"] = {prov: _pool(led.spent_pool, prov, caps.provider_micros, model_cfg=model)
                             for prov in ("meta", "baseten", "lmstudio_local")}
        out["spent_total_display"] = led.spent()
    out["projection"] = proj
    # (c) ambang kumulatif
    out["thresholds"] = {p: cumulative_threshold_for(p, budget, caps.provider_micros)
                         for p in ("meta", "baseten", "openrouter", "lmstudio_local")}
    # (d) gerbang
    gcfg = load_gate_config(budget)
    gate: dict[str, Any] = {}
    for key, (exp_upper, spent) in {"a": (2_000_000, 561_741), "b": (2_000_001, 561_741),
                                    "c": (2_000_000, 14_000_000), "d": (2_000_000, 14_000_001)}.items():
        # expected sedemikian rupa sehingga batas atas = exp_upper memakai upper_floor
        v = evaluate_gate([0], spent, gcfg, upper_floor=exp_upper, threshold_micros=cumulative_threshold_for("meta", budget, {}))
        gate[key] = v.to_dict()
    out["gate"] = gate
    # (e) kunci registri limiter
    ratelimit.reset_registry()
    for prof in ("meta", "openrouter_dev", "baseten_open", "glimmer_local"):
        ratelimit.get_limiter(prof, "synthetic-key-123456")
    out["limiter_keys"] = sorted([k[0], k[1]] for k in ratelimit._registry)
    ratelimit.reset_registry()
    # (h) require_reportable tanpa model_config
    rep: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as td:
        runs = Path(td) / "runs"
        for prov in ("meta", "baseten", "lmstudio_local", "openrouter"):
            synth(runs, "b", prov, 10, run_id=f"rep-{prov}")
        for r_ in store.load_records(runs):
            try:
                require_reportable([r_])
                rep[r_.provider] = "ok"
            except Exception as exc:  # noqa: BLE001
                rep[r_.provider] = type(exc).__name__ + ":" + str(exc)
    out["reportable"] = rep
    return out


if __name__ == "__main__":
    print(json.dumps(compute(), indent=1, sort_keys=True, ensure_ascii=False))
