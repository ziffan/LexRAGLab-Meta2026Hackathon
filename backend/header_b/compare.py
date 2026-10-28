"""H-101 bagian 2: runner B pembanding open-weight (Spark Open Baseten, Glimmer lokal) ke store TERPISAH.

    uv run python -m backend.header_b.compare --model-profile baseten_open --family uupt --sources pasal --project-only
    uv run python -m backend.header_b.compare --model-profile baseten_open --family uupt --sources pasal --max-units 20
    uv run python -m backend.header_b.compare --model-profile glimmer_local --family akta --sources pasal fixed_size

Header disimpan di `runs/headers_compare/<profile>[/akta]/` (struktur sama dengan `runs/headers`); store utama, grid, dan
profil terpilih tidak disentuh (G-38) dan dibuktikan dengan potret identitas utama sebelum/sesudah (`main_identity_changed`).
Validator 40 token / 190 karakter sama untuk semua model (D6). Batas atas proyeksi sadar-floor profil (P7); run dipecah
jadi batch <= `batch_cap_micros` (P8); tiap batch (dan tiap ronde upaya ulang) dinilai gerbang atas belanja AKTUAL pool
provider (P9) sebelum request. Profil `chat_completions` (Glimmer): tanpa pemanas (P15), guard cache dilewati (P10), kunci
GPU eksklusif (P12), lanjut setelah berhenti (unit tersimpan dilewati). Ringkasan run ditulis di
`runs/headers_compare/<profile>/runs/<UTC>.json` (di luar direktori yang di-hash)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend import config, gpulock
from backend.spark import BudgetExceeded, ConfigInvalid, compute_cost_micros, format_usd_micros
from backend.spark.settings import API_CHAT, profile_api

from .caller import load_header, run_headers
from .compare_store import (CompareError, factor_bp_for, assert_main_identity, build_identity, check_forbidden_profile_keys, check_identity,
                            comparison_profile, compare_profile_root, compare_store_dir, max_attempts_for, snapshot_main,
                            time_params_for, validate_compare_cfg, write_identity)
from .family import upper_bound
from .render import WARM_UNIT, render_suffix
from .run import HeaderConfigError, Prepared
from .units import Unit

ROLE = "b"
ALLOWED_SOURCES = ("pasal", "ayat", "fixed_size", "structure_schema")
REUSE_MEDIAN_MAX_MS = 60_000  # S17 (c): reuse terkonfirmasi bila median latensi panggilan 2..5 <= ini
REUSE_SMOKE_CALLS = 5


# ---------------------------------------------------------------- proyeksi biaya (P7)
def pricing_for(model_cfg: Mapping[str, Any], profile: str) -> dict[str, int]:
    prof = model_cfg["profiles"][profile]
    raw = model_cfg["pricing"][prof.get("pricing", profile)]
    return {k: raw[f"{k}_per_mtok_micros"] for k in ("input", "cached", "output")}


def floor_for(prof: Mapping[str, Any]) -> int | None:
    v = prof.get("max_output_tokens")
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else None


def unit_costs(prefix_tokens: int, suffix_tokens: Sequence[int], warm_suffix_tokens: int, pricing: Mapping[str, int], *,
               expected_output_tokens: int, max_output_tokens: int, warm_max_output_tokens: int, floor: int | None,
               warm: bool) -> dict[str, Any]:
    """Biaya per panggilan (integer micro-USD, `compute_cost_micros`) untuk `suffix_tokens` plus satu pemanas bila `warm`.

    Profil berfloor (klien menaikkan `max_output_tokens` ke floor, `client._projected`): keluaran efektif
    `max(max_output_tokens, floor)` dan pemanas `max(warm_max_output_tokens, floor)` (P7). Tanpa floor: rumus
    `header_b.project` apa adanya (pemanas `min(keluaran, warm_max_output_tokens)`)."""
    p = prefix_tokens
    out_up = max(max_output_tokens, floor) if floor else max_output_tokens
    warm_up = max(warm_max_output_tokens, floor) if floor else min(max_output_tokens, warm_max_output_tokens)
    warm_exp_out = min(expected_output_tokens, warm_max_output_tokens)

    def c(s: int, cached: bool, out: int) -> int:
        return compute_cost_micros({"input": p + s, "cached": p if cached else 0, "output": out}, pricing)

    r: dict[str, Any] = {
        "unit_expected": [c(s, True, expected_output_tokens) for s in suffix_tokens],
        "unit_upper_cached": [c(s, True, out_up) for s in suffix_tokens],
        "unit_upper_no_cache": [c(s, False, out_up) for s in suffix_tokens],
        "warm_expected": c(warm_suffix_tokens, False, warm_exp_out) if warm else 0,
        "warm_upper": c(warm_suffix_tokens, False, warm_up) if warm else 0,
        "floored": bool(floor), "output_effective": out_up, "warm_output_effective": warm_up if warm else 0}
    r["expected"] = sum(r["unit_expected"]) + r["warm_expected"]
    r["upper_cached"] = sum(r["unit_upper_cached"]) + r["warm_upper"]
    r["upper_no_cache"] = sum(r["unit_upper_no_cache"]) + r["warm_upper"]
    return r


def batas_atas(expected: int, upper_cached: int, factor_bp: int, floored: bool) -> int:
    """Batas atas gerbang batch: `ceil(expected * factor_bp / 10000)` (G-36); profil berfloor: `max(itu, upper_cached efektif)`."""
    g = upper_bound(expected, factor_bp)
    return max(g, upper_cached) if floored else g


def split_batches(chunk_ids: Sequence[str], costs: Mapping[str, Any], *, batch_cap: int, factor_bp: int) -> list[list[int]]:
    """Pemecahan serakah menurut urutan (P8): unit berurutan sebanyak mungkin dengan batas atas (termasuk SATU pemanas per
    batch) <= `batch_cap` (inklusif). Satu unit + pemanas > cap -> `unit_over_batch_cap` (menyebut `chunk_id` dan angkanya)."""
    ue, uu, floored = costs["unit_expected"], costs["unit_upper_cached"], costs["floored"]
    we, wu = costs["warm_expected"], costs["warm_upper"]
    out: list[list[int]] = []
    cur: list[int] = []
    e, u = we, wu
    for i, cid in enumerate(chunk_ids):
        ne, nu = e + ue[i], u + uu[i]
        if batas_atas(ne, nu, factor_bp, floored) <= batch_cap:
            cur.append(i)
            e, u = ne, nu
            continue
        if not cur:
            raise CompareError("unit_over_batch_cap",
                               f"unit {cid} alone (with one warm-up) has an upper bound of "
                               f"{batas_atas(ne, nu, factor_bp, floored)} micro-USD, over batch_cap_micros {batch_cap}")
        out.append(cur)
        cur, e, u = [i], we + ue[i], wu + uu[i]
        b = batas_atas(e, u, factor_bp, floored)
        if b > batch_cap:
            raise CompareError("unit_over_batch_cap",
                               f"unit {cid} alone (with one warm-up) has an upper bound of {b} micro-USD, "
                               f"over batch_cap_micros {batch_cap}")
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------- proyeksi waktu Glimmer (S17)
def prefill_ms(tokens: int, params: Mapping[str, int]) -> int:
    return -(-tokens * 1000 // params["prefill_tokens_per_s"])


def output_ms(tokens: int, params: Mapping[str, int]) -> int:
    return -(-tokens * 10_000 // params["output_tokens_per_10s"])


def call_ms(prefill: int, out_tokens: int, params: Mapping[str, int]) -> int:
    return prefill + params["base_ms"] + output_ms(out_tokens, params)


def project_time_ms(n_calls: int, first_call_ms: int, reuse_call_ms: int) -> dict[str, int]:
    """Batas atas ("tanpa reuse": semua panggilan penuh) dan dengan reuse prefiks (panggilan pertama penuh, sisanya reuse)."""
    if n_calls < 1:
        return {"no_reuse_ms": 0, "reuse_ms": 0}
    return {"no_reuse_ms": n_calls * first_call_ms, "reuse_ms": first_call_ms + (n_calls - 1) * reuse_call_ms}


def glimmer_time(prefix_tokens: int, suffix_tokens: Sequence[int], out_tokens: int, params: Mapping[str, int]) -> dict[str, Any]:
    """Proyeksi waktu per (dokumen, sumber) dengan parameter profil (BUKAN `assumed_latency_ms` Contributor); tanpa pemanas."""
    n = len(suffix_tokens)
    no_reuse = sum(call_ms(prefill_ms(prefix_tokens + s, params), out_tokens, params) for s in suffix_tokens)
    reuse = (call_ms(prefill_ms(prefix_tokens + suffix_tokens[0], params), out_tokens, params)
             + sum(call_ms(prefill_ms(s, params), out_tokens, params) for s in suffix_tokens[1:])) if n else 0
    return {"calls": n, "no_reuse_ms": no_reuse, "reuse_ms": reuse, "basis": "no_reuse is the upper bound; reuse is unconfirmed "
                                                                              "until the smoke check (median of calls 2..5) passes"}


def reuse_confirmed(latencies_ms: Sequence[int], threshold_ms: int = REUSE_MEDIAN_MAX_MS) -> bool | None:
    """Smoke reuse (S17 c): lima panggilan; median latensi panggilan 2..5 <= ambang. None bila kurang dari 5 panggilan."""
    if len(latencies_ms) < REUSE_SMOKE_CALLS:
        return None
    rest = sorted(latencies_ms[1:REUSE_SMOKE_CALLS])
    return rest[1] + rest[2] <= 2 * threshold_ms  # median 4 nilai = (tengah1 + tengah2) / 2, tanpa pembagian


# ---------------------------------------------------------------- gerbang per pool
def make_gate(provider: str, budget_cfg: Mapping[str, Any], model_cfg: Mapping[str, Any], env: Mapping[str, str] | None,
              runs_dir: Path, *, sweep_cfg: Mapping[str, Any] | None = None) -> Callable[[Sequence[int], int], Any]:
    """Gerbang per batch atas belanja AKTUAL pool provider (P9): `spent_pool` + `cumulative_threshold_for` + `evaluate_gate`
    dengan lantai batas atas (P7). Dibaca ulang dari buku belanja tiap pemanggilan.

    `sweep_cfg` diberikan (profil sapuan, H-102 P4/D13): `spent` = belanja pool sapuan (`Ledger.spent_off_pin`) dan ambang
    = `[sweep_pool].cap_micros x cumulative_pct // 100` (50.000.000 x 80 // 100 = 40.000.000). `model_cfg` = `config/model`
    ASLI (tanpa profil sapuan)."""
    from backend.proposal.gate import cumulative_threshold_for, evaluate_gate, load_gate_config, sweep_threshold_micros
    from backend.spark.budget import Ledger, effective_caps

    def gate(expected_per_call: Sequence[int], upper_floor: int) -> Any:
        pc = effective_caps(budget_cfg, env, model_cfg).provider_micros
        if sweep_cfg is not None:
            return evaluate_gate(list(expected_per_call), Ledger(runs_dir).spent_off_pin(model_cfg=model_cfg),
                                 load_gate_config(budget_cfg), upper_floor=upper_floor,
                                 threshold_micros=sweep_threshold_micros(budget_cfg, sweep_cfg))
        spent = Ledger(runs_dir).spent_pool(provider, pc, model_cfg=model_cfg)
        return evaluate_gate(list(expected_per_call), spent, load_gate_config(budget_cfg), upper_floor=upper_floor,
                             threshold_micros=cumulative_threshold_for(provider, budget_cfg, pc))

    return gate


def warm_unit_for(nonce: str) -> Unit:
    """Pemanas ber-nonce: awalan dokumen sama (cache prefiks penyedia), tetapi hash masukan beda sehingga klien tidak
    mengembalikan hasil pemanas dari cache lokal: satu pemanas NYATA per batch dan per ronde (G-36, S6)."""
    return Unit(WARM_UNIT.key, WARM_UNIT.address, f"{WARM_UNIT.text} [{nonce}]", 0, ())


WARM_NONCE_LEN = 8


# ---------------------------------------------------------------- rencana unit
def stored(store_dir: Path, p: Prepared, u: Unit) -> bool:
    return all(load_header(store_dir, p.source, p.prompt, cid) is not None for cid in u.chunk_ids)


@dataclass
class Pair:
    key: str  # "<dokumen>/<sumber>"
    p: Prepared
    units: list[Unit] = field(default_factory=list)  # unit terpilih (belum tersimpan saat dipilih, urutan dokumen)
    total: int = 0
    already_stored: int = 0


def select_pairs(prepared: Mapping[str, Mapping[str, Prepared]], store_dir: Path, *, sample: int | None = None,
                 max_units: int | None = None) -> list[Pair]:
    """Per (dokumen, sumber): unit yang BELUM tersimpan, urutan dokumen. `sample` = N pertama per pasangan; `max_units` = N
    pertama di seluruh run (pilot). Keduanya menghitung hanya unit yang belum tersimpan (lanjut setelah berhenti)."""
    pairs: list[Pair] = []
    left = max_units
    for d, srcs in prepared.items():
        for s, p in srcs.items():
            todo = [u for u in p.units if not stored(store_dir, p, u)]
            pair = Pair(f"{d}/{s}", p, total=len(p.units), already_stored=len(p.units) - len(todo))
            if sample is not None:
                todo = todo[:sample]
            if left is not None:
                todo = todo[:max(left, 0)]
                left -= len(todo)
            pair.units = todo
            pairs.append(pair)
    return pairs


class PairCosts:
    """Biaya per unit satu pasangan; token suffix dihitung sekali per unit."""

    def __init__(self, pair: Pair, tokenizer: Any, pricing: Mapping[str, int], hc: Mapping[str, Any], floor: int | None, warm: bool):
        p = pair.p
        self._suffix = {u.key: tokenizer.count(render_suffix(p.prefix, u)) for u in pair.units}
        self._warm_suffix = tokenizer.count(render_suffix(p.prefix, warm_unit_for("0" * WARM_NONCE_LEN)))
        self._args = (p.prefix.tokens, pricing, hc, floor, warm)

    def for_units(self, units: Sequence[Unit]) -> dict[str, Any]:
        prefix_tokens, pricing, hc, floor, warm = self._args
        return unit_costs(prefix_tokens, [self._suffix[u.key] for u in units], self._warm_suffix, pricing,
                          expected_output_tokens=hc["expected_output_tokens"], max_output_tokens=hc["max_output_tokens"],
                          warm_max_output_tokens=hc["warm_max_output_tokens"], floor=floor, warm=warm)

    def suffix_tokens(self, units: Sequence[Unit]) -> list[int]:
        return [self._suffix[u.key] for u in units]


def plan_batches(pair: Pair, remaining: Sequence[Unit], pc: PairCosts, *, batch_cap: int, factor_bp: int) -> list[list[Unit]]:
    if not remaining:
        return []
    costs = pc.for_units(remaining)
    return [[remaining[i] for i in idx] for idx in split_batches([u.key for u in remaining], costs, batch_cap=batch_cap,
                                                                 factor_bp=factor_bp)]


# ---------------------------------------------------------------- run
def run_compare(client: Any, pairs: Sequence[Pair], *, profile: str, prof: Mapping[str, Any], model_cfg: Mapping[str, Any],
                hc: Mapping[str, Any], gate_cfg: Mapping[str, int], tokenizer: Any, store_dir: Path,
                meta_for: Callable[[Prepared], dict], max_attempts: int,
                gate: Callable[[Sequence[int], int], Any] | None, log: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    """Jalankan unit terpilih per (dokumen, sumber): ronde 1..`max_attempts`; tiap ronde dipecah jadi batch <= cap, tiap batch
    dinilai `gate` (None = tanpa gerbang biaya: profil lokal) lalu `run_headers`. Berhenti seluruhnya bila `run_headers`
    berhenti atau gerbang menolak. Unit yang tetap gagal = gagal jujur (tanpa fallback ke header lain)."""
    local = profile_api(prof) == API_CHAT
    warm = not local  # P15: Glimmer tanpa pemanas
    pricing = pricing_for(model_cfg, profile)
    floor = floor_for(prof)
    summary: dict[str, Any] = {"stopped": None, "stopped_at": None, "attempts": {}, "failed": {}, "not_attempted": {}, "stored": 0,
                               "batches": [], "cache_guard": "skipped" if local else "active", "warm": warm,
                               "latency_ms_first_calls": []}
    pcs = {pr.key: PairCosts(pr, tokenizer, pricing, hc, floor, warm) for pr in pairs}
    for pr in pairs:  # seluruh run ditolak lebih awal bila ada unit yang tak muat satu batch (tanpa request)
        plan_batches(pr, pr.units, pcs[pr.key], batch_cap=gate_cfg["batch_cap_micros"], factor_bp=gate_cfg["factor_bp"])
    done = False
    for pr in pairs:
        if done:
            break
        sent: dict[str, int] = {}
        for attempt in range(1, max_attempts + 1):
            remaining = [u for u in pr.units if not stored(store_dir, pr.p, u)]
            if not remaining:
                break
            summary["attempts"][pr.key] = attempt
            for batch in plan_batches(pr, remaining, pcs[pr.key], batch_cap=gate_cfg["batch_cap_micros"],
                                      factor_bp=gate_cfg["factor_bp"]):
                costs = pcs[pr.key].for_units(batch)
                info: dict[str, Any] = {"key": pr.key, "round": attempt, "units": len(batch),
                                        "expected": costs["expected"], "upper_cached": costs["upper_cached"]}
                if gate is not None:
                    v = gate(costs["unit_expected"] + ([costs["warm_expected"]] if warm else []),
                             costs["upper_cached"] if costs["floored"] else 0)
                    info.update({"batas_atas": v.batas_atas, "spent_pool": v.spent, "gate_ok": v.ok, "reasons": list(v.reasons)})
                    if not v.ok:
                        summary["batches"].append(info)
                        summary["stopped"], summary["stopped_at"] = "gate_rejected", pr.key
                        summary["gate_reasons"] = list(v.reasons)
                        done = True
                        break
                else:
                    info["gate_ok"] = "skipped_local"
                summary["batches"].append(info)
                try:
                    res = run_headers(
                        client, pr.p.prompt, pr.p.prefix, batch, granularity=pr.p.source, tokenizer=tokenizer,
                        headers_dir=store_dir, max_header_tokens=hc["max_header_tokens"],
                        max_output_tokens=hc["max_output_tokens"], max_consecutive_errors=hc["max_consecutive_errors"],
                        warm_max_output_tokens=hc["warm_max_output_tokens"], meta=meta_for(pr.p), warm=warm,
                        cache_guard_calls=None if local else hc["cache_guard_calls"],
                        cache_guard_min_ratio=hc["cache_guard_min_ratio"], max_length_chars=hc.get("schema_max_length_chars"),
                        warm_unit=warm_unit_for(uuid.uuid4().hex[:WARM_NONCE_LEN]), count_semantic_errors=False)
                except BudgetExceeded:
                    summary["stopped"], summary["stopped_at"] = "budget_exceeded", pr.key
                    done = True
                    break
                for o in res.outcomes:
                    sent[o.unit.key] = sent.get(o.unit.key, 0) + 1
                    if len(summary["latency_ms_first_calls"]) < REUSE_SMOKE_CALLS and not summary["batches"][:-1]:
                        summary["latency_ms_first_calls"].append(o.run.latency_ms)
                ok = sum(1 for o in res.outcomes if o.headers)
                summary["stored"] += ok
                info.update({"called": len(res.outcomes), "ok": ok, "stopped": res.stopped_reason})
                log(f"{pr.key} round {attempt}: called={len(res.outcomes)} ok={ok} stopped={res.stopped_reason}")
                if res.stopped_reason:
                    summary["stopped"], summary["stopped_at"] = res.stopped_reason, pr.key
                    done = True
                    break
            if done:
                break
        left = [u for u in pr.units if not stored(store_dir, pr.p, u)]
        failed = [u.key for u in left if sent.get(u.key)]
        if failed:
            summary["failed"][pr.key] = failed
        na = [u.key for u in left if not sent.get(u.key)]
        if na:
            summary["not_attempted"][pr.key] = na
    summary["pairs_not_started"] = [pr.key for pr in pairs if pr.key not in summary["attempts"] and pr.units and
                                    pr.key not in summary["not_attempted"] and pr.key not in summary["failed"]]
    return summary


# ---------------------------------------------------------------- laporan
def coverage_of(pairs: Sequence[Pair], store_dir: Path) -> dict[str, dict[str, int]]:
    return {pr.key: {"units": pr.total, "stored": sum(1 for u in pr.p.units if stored(store_dir, pr.p, u))} for pr in pairs}


def write_run_report(profile_root: Path, payload: Mapping[str, Any], now: datetime | None = None) -> Path:
    d = Path(profile_root) / "runs"
    d.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    p = d / f"{stamp}.json"
    n = 1
    while p.exists():
        n += 1
        p = d / f"{stamp}-{n}.json"
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, p)
    return p


# ---------------------------------------------------------------- CLI
def _hm(ms: int) -> str:
    return f"{ms // 3_600_000}h{ms % 3_600_000 // 60_000:02d}m"


def _fmt_pair(pr: Pair, batches: list[list[Unit]], pc: PairCosts, pcosts_all: dict[str, Any], local: bool,
              tparams: Mapping[str, int] | None, hc: Mapping[str, Any]) -> list[str]:
    lines = [f"  {pr.key:<34} units={pr.total} stored={pr.already_stored} to_call={len(pr.units)} batches={len(batches)} "
             f"expected={pcosts_all['expected']} ({format_usd_micros(pcosts_all['expected'])}) "
             f"upper_cached={pcosts_all['upper_cached']} upper_no_cache={pcosts_all['upper_no_cache']}"]
    for i, b in enumerate(batches, 1):
        c = pc.for_units(b)
        lines.append(f"    batch {i}: units={len(b)} first={b[0].key} expected={c['expected']} upper_cached={c['upper_cached']}")
    if local and tparams is not None and pr.units:
        t = glimmer_time(pr.p.prefix.tokens, pc.suffix_tokens(pr.units), hc["max_output_tokens"], tparams)
        lines.append(f"    time (no warm-up, {t['calls']} calls): no_reuse={t['no_reuse_ms']} ms ({_hm(t['no_reuse_ms'])}) "
                     f"reuse={t['reuse_ms']} ms ({_hm(t['reuse_ms'])}); reuse unconfirmed until --smoke-reuse passes")
    return lines


def main(argv: list[str] | None = None, *, env: Mapping[str, str] | None = None, model_config: Mapping[str, Any] | None = None,
         budget_config: Mapping[str, Any] | None = None, header_config: Mapping[str, Any] | None = None,
         runs_dir: Path | None = None, transport: Any = None, out: Callable[[str], None] = print,
         probe: Callable[[str, str], tuple[bool, str]] | None = None, tokenizer: Any = None,
         prepare_fn: Callable[..., Any] | None = None, pid_alive: Callable[[int], bool] | None = None,
         casefold: bool | None = None, main_extras: Mapping[str, Callable[[], Any]] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="backend.header_b.compare", description=__doc__.split("\n\n")[0])
    ap.add_argument("--model-profile", required=True, help="profil pembanding di config/model dengan roles memuat 'b'")
    ap.add_argument("--family", choices=("uupt", "akta"), default="uupt")
    ap.add_argument("--sources", nargs="+", choices=ALLOWED_SOURCES, default=["pasal"])
    ap.add_argument("--doc", default=None, help="--family akta: satu akta saja")
    ap.add_argument("--project-only", action="store_true", help="proyeksi + batch + gerbang; tanpa panggilan, tanpa tulis")
    ap.add_argument("--sample", type=int, default=None, help="N unit pertama yang BELUM tersimpan per (dokumen, sumber)")
    ap.add_argument("--max-units", type=int, default=None, help="N unit pertama yang BELUM tersimpan di seluruh run (pilot)")
    ap.add_argument("--smoke-reuse", action="store_true", help="Glimmer: 5 panggilan lalu cek reuse prefiks (median 2..5 <= 60 dtk)")
    ap.add_argument("--break-stale-lock", action="store_true", help="hapus kunci GPU kedaluwarsa (pid tak hidup) lalu lanjut")
    a = ap.parse_args(argv)
    for name, v in (("--sample", a.sample), ("--max-units", a.max_units)):
        if v is not None and v < 1:
            print(f"error: {name} must be >= 1", file=sys.stderr)
            return 2
    if a.smoke_reuse and a.max_units is None:
        a.max_units = REUSE_SMOKE_CALLS

    runs = Path(runs_dir) if runs_dir is not None else config.REPO_ROOT / "runs"
    try:
        from .run import load_header_cfg
        from backend.spark.settings import load_configs
        if model_config is None or budget_config is None:
            m, b = load_configs()
            model_config, budget_config = model_config or m, budget_config or b
        hc = dict(header_config) if header_config is not None else load_header_cfg()
        check_forbidden_profile_keys(model_config)
        validate_compare_cfg(hc, model_config)
        prof = comparison_profile(model_config, a.model_profile)
        from backend.proposal.gate import load_gate_config
        gcfg = load_gate_config(budget_config)
        gate_cfg = {"factor_bp": factor_bp_for(hc, a.model_profile, gcfg.factor_bp), "batch_cap_micros": gcfg.batch_cap_micros}
        from backend.spark.budget import effective_caps
        effective_caps(budget_config, env, model_config)  # plafon provider tidak sah = config_invalid sebelum jaringan
        store_dir = compare_store_dir(runs, a.model_profile, a.family, casefold=casefold)
    except (ConfigInvalid, CompareError, HeaderConfigError) as exc:
        print(f"error: {str(exc)[:300]}", file=sys.stderr)
        return 2
    root = compare_profile_root(runs, a.model_profile)
    local = profile_api(prof) == API_CHAT

    if tokenizer is None:
        from backend.tokenizer import get_tokenizer
        tokenizer = get_tokenizer()
    try:
        if prepare_fn is None:
            from .family import prepare_family
            prepare_fn = prepare_family
        from backend import config as _c
        from backend.corpus import akta_entries
        from .run import DEFAULT_DOC
        rec = None
        if "structure_schema" in a.sources:
            from backend.grid.schemas import SchemaBinding
            rec = SchemaBinding.from_store(runs, a.family).active()
            if rec is None:
                print(f"error: no schema A record for family {a.family!r} in runs/schemas", file=sys.stderr)
                return 2
        ids = [DEFAULT_DOC]
        if a.family == "akta":
            ids = [d for d in akta_entries() if not a.doc or d == a.doc]
            if not ids:
                print(f"error: unknown akta {a.doc!r}", file=sys.stderr)
                return 2
        prepared = prepare_fn(ids, list(a.sources), tokenizer=tokenizer, header_cfg=hc, retrieval_cfg=_c.load("retrieval"),
                              grid_cfg=_c.load("grid"), schema_record=rec)
        first = next(iter(next(iter(prepared.values())).values()))
        prompt = first.prompt
        identity = build_identity(a.model_profile, prof, model_config, prompt_hash=prompt.prompt_hash,
                                  max_header_tokens=hc["max_header_tokens"], schema_max_length_chars=hc.get("schema_max_length_chars"))
        had_identity = check_identity(root, identity)
        pairs = select_pairs(prepared, store_dir, sample=a.sample, max_units=a.max_units)
        pricing, floor = pricing_for(model_config, a.model_profile), floor_for(prof)
        pcs = {pr.key: PairCosts(pr, tokenizer, pricing, hc, floor, not local) for pr in pairs}
        plans = {pr.key: plan_batches(pr, pr.units, pcs[pr.key], batch_cap=gate_cfg["batch_cap_micros"],
                                      factor_bp=gate_cfg["factor_bp"]) for pr in pairs}
    except (ConfigInvalid, CompareError, HeaderConfigError) as exc:
        print(f"error: {str(exc)[:300]}", file=sys.stderr)
        return 2

    tparams = time_params_for(hc, a.model_profile) if local else None
    out(f"profile={a.model_profile} provider={prof.get('provider')} model={prof.get('model')} "
        f"quantization={prof.get('quantization')} effort={identity['effort']} store={store_dir} "
        f"identity={'ok' if had_identity else 'new'} max_attempts={max_attempts_for(hc, a.model_profile)}")
    for pr in pairs:
        out("\n".join(_fmt_pair(pr, plans[pr.key], pcs[pr.key], pcs[pr.key].for_units(pr.units), local, tparams, hc)))
    if a.project_only:
        return 0
    if not any(pr.units for pr in pairs):
        out("nothing to do: all selected units are already stored")
        return 0

    if env is None:
        from dotenv import dotenv_values
        env = {k: v for k, v in dotenv_values(config.REPO_ROOT / ".env").items() if v}
    from backend.spark import SparkClient
    try:
        client = SparkClient(a.model_profile, model_config=model_config, budget_config=budget_config, env=env, runs_dir=runs,
                             transport=transport)
        gate = None if local else make_gate(prof["provider"], budget_config, model_config, env, runs)
    except ConfigInvalid as exc:
        print(f"error: {str(exc)[:300]}", file=sys.stderr)
        return 2
    lock = None
    try:
        if local:  # S16: kunci GPU diambil SEBELUM request apa pun ke 127.0.0.1 (juga sebelum cek ketersediaan model)
            lock = gpulock.acquire(runs, "glimmer-b", break_stale=a.break_stale_lock,
                                   **({"pid_alive": pid_alive} if pid_alive is not None else {}))
            from backend.spark import local_server
            ok, why = (probe or local_server.probe_models)(prof.get("base_url", ""), prof.get("model", ""))
            if not ok:
                print(f"error: {why}", file=sys.stderr)
                return 3
        before = snapshot_main(runs, prompt.prompt_hash, extras=main_extras)
        write_identity(root, identity)
        tok = tokenizer

        def meta_for(p: Prepared) -> dict:
            return {"corpus_hash": config.config_hash({"docs": [p.doc.sha256]}), "clean_sha256": p.doc.clean_sha256,
                    "loader_rules_version": p.doc.loader_rules_version, "tokenizer": {"name": tok.info.name, "version": tok.info.version}}

        started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary = run_compare(client, pairs, profile=a.model_profile, prof=prof, model_cfg=model_config, hc=hc, gate_cfg=gate_cfg,
                              tokenizer=tokenizer, store_dir=store_dir, meta_for=meta_for,
                              max_attempts=max_attempts_for(hc, a.model_profile), gate=gate, log=out)
        after = snapshot_main(runs, prompt.prompt_hash, extras=main_extras)
        report = {"profile": a.model_profile, "family": a.family, "sources": list(a.sources), "started_at": started,
                  "finished_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "identity": identity,
                  "coverage": coverage_of(pairs, store_dir), "main_identity": "unchanged",
                  "gpu_lock": ({"holder": lock.holder, "broke_stale": lock.broke_stale} if lock else None), **summary}
        if local:
            report["reuse_confirmed"] = reuse_confirmed(summary["latency_ms_first_calls"])
        try:
            assert_main_identity(before, after)
        except CompareError as exc:
            report["main_identity"] = str(exc)
            write_run_report(root, report)
            print(f"error: {exc}", file=sys.stderr)
            return 5
        path = write_run_report(root, report)
    except (gpulock.GpuLockError, ConfigInvalid, CompareError) as exc:
        print(f"error: {str(exc)[:300]}", file=sys.stderr)
        return 3
    finally:
        if lock is not None:
            lock.release()
    out(f"stored={summary['stored']} stopped={summary['stopped']} failed={ {k: len(v) for k, v in summary['failed'].items()} } "
        f"report={path}")
    return 0 if summary["stopped"] is None and not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
