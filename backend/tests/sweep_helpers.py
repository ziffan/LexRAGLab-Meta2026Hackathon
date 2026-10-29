"""Perlengkapan uji sapuan effort (docs/scenarios/M3.2-effort-sweep.md). Data sintetis, transport palsu, tanpa jaringan."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.spark import RunRecord, SparkClient, store
from backend.spark.money import compute_cost_micros
from backend.spark.runrecord import kind_for_role, utc_iso
from backend.spark.settings import load_configs
from backend.spark.sweep import load_sweep

from .m25_fakes import chat_body, env_m25
from .spark_fakes import Clock, FakeTransport, Resp, body_ok

CONTRIB = "muse-spark-1.3-contributor"
OPEN = "meta-models/muse-spark-open-1026"
GLIM = "meta/muse-glimmer"
USAGE_40K = {"input_tokens": 40300, "input_tokens_details": {"cached_tokens": 40000}, "output_tokens": 700}


def cfgs() -> tuple[dict, dict, dict]:
    """(model, budget, sweep) dari berkas config nyata, salinan dalam."""
    m, b = load_configs()
    return copy.deepcopy(m), copy.deepcopy(b), copy.deepcopy(load_sweep())


def make_client(tmp: Path, profile: str, *, default: Any = None, script: list[Any] | None = None, model: dict | None = None,
                budget: dict | None = None, sweep: dict | None = None, env: dict | None = None,
                clock: Clock | None = None) -> tuple[SparkClient, FakeTransport]:
    m, b, s = cfgs()
    clock = clock or Clock()
    if default is None:
        default = Resp(200, chat_body({"jawaban": "x", "kutipan": [], "status": "tolak"})) if profile.endswith("glimmer_local") \
            or "glimmer" in profile else Resp(200, body_ok())
    tr = FakeTransport(clock, script, default)
    client = SparkClient(profile, model_config=model or m, budget_config=budget or b, env=env or env_m25(), runs_dir=tmp / "runs",
                         transport=tr.transport, now=clock.now, sleep=clock.sleep, sweep_config=sweep if sweep is not None else s)
    return client, tr


def syn(runs: Path, role: str, provider: str | None, model: str | None, effort: str | None, cost: int, *,
        quant: str | None = None, rid: str | None = None, kind: str | None = None, projected: int | None = None) -> RunRecord:
    """RunRecord sintetis lengkap (provider/model/kuantisasi/effort) untuk ledger sapuan."""
    rec = RunRecord(run_id=rid or f"syn-{role}-{provider}-{effort}-{cost}-{kind}", kind=kind or kind_for_role(role),
                    created_at=utc_iso(1000.0), cache_key="k", corpus_hash=None, config_hash="CFG", clean_sha256=None,
                    loader_rules_version=None, prompt_version=None, prompt_hash=None, model=model, effort=effort,
                    tokenizer=None, embedder=None, packing=None, usage_input_tokens=None, usage_cached_tokens=None,
                    usage_output_tokens=None, cost_usd_micros=cost, projected_cost_usd_micros=projected, latency_ms=0,
                    host="authoritative", device="remote", provider=provider, quantization=quant, status="ok", error=None)
    store.save_record(runs, rec)
    return rec


def f3(runs: Path) -> None:
    """Ledger F3 S4: jalur utama (on-pin) + tujuh rekaman S1-smoke + dua rekaman sapuan sintetis (off-pin)."""
    for role, cost in (("a", 8_170), ("b", 526_265), ("c", 5_964), ("d", 21_342)):
        syn(runs, role, "meta", CONTRIB, "low", cost)
    syn(runs, "c", "baseten", OPEN, "low", 53_267)
    syn(runs, "b", "baseten", OPEN, "low", 15_460_483)
    for eff, cost in (("medium", 4_637), ("high", 6_745), ("xhigh", 1_156), ("max", 1_887)):
        syn(runs, "c", "baseten", OPEN, eff, cost)
    for eff, cost in (("medium", 151), ("high", 130), ("xhigh", 103)):
        syn(runs, "c", "meta", CONTRIB, eff, cost)
    syn(runs, "b", "meta", CONTRIB, "high", 11_000_000, rid="sweep-meta-high-b")
    syn(runs, "b", "baseten", OPEN, "xhigh", 26_990_441, rid="sweep-baseten-xhigh-b")


def calls_for_total(target: int, pricing: dict[str, int], out_tokens: int, *, max_calls: int = 3) -> list[int]:
    """`est_input` satu sampai tiga panggilan (tanpa cache) yang proyeksinya berjumlah TEPAT `target` micro-USD
    (`ceil` per panggilan, `compute_cost_micros`). Dipakai untuk uji batas inklusif/+1 pada klien."""
    def c(n: int) -> int:
        return compute_cost_micros({"input": n, "cached": 0, "output": out_tokens}, pricing)

    base = c(0)
    # satu panggilan
    lo, hi = 0, 10**10
    while lo < hi:
        mid = (lo + hi) // 2
        if c(mid) >= target:
            hi = mid
        else:
            lo = mid + 1
    if c(lo) == target:
        return [lo]
    for extra in range(1, 12):  # panggilan kedua kecil: sisa dicari pada panggilan pertama
        rest = target - c(extra)
        if rest < base:
            continue
        lo, hi = 0, 10**10
        while lo < hi:
            mid = (lo + hi) // 2
            if c(mid) >= rest:
                hi = mid
            else:
                lo = mid + 1
        if c(lo) == rest:
            return [lo, extra]
    raise AssertionError(f"no est_input combination reaches {target}")


def project_total(client: SparkClient, role: str, ests: list[int], max_out: int = 1):
    from .spark_fakes import call_args
    return client.project_batch([call_args(i, role=role, est_input=e, max_output_tokens=max_out) for i, e in enumerate(ests)])
