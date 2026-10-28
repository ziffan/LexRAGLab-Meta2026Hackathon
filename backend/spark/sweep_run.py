"""Bantu runner sapuan (H-102/H-103 bagian B): S5(m)(o), S7, S11(g), S15, S17, S20. Fungsi murni, integer micro-USD.

`config/sweep.toml` dibaca HANYA lewat `resolve_profile` dan hanya bila nama profil tidak ada di `config/model`
(profil non-sapuan tidak pernah membacanya, strict persis H-101)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import ConfigInvalid
from .sweep import (SWEEP_BASETEN_FACTOR_BP_MIN, has_sweep_profile, load_sweep, merge_sweep, sweep_profile_names,
                    validate_sweep)

COVERAGE_POLICIES = ("strict", "mask_threshold", "mask_ref")
EFFORT_RANK = {"low": -1, "medium": 0, "high": 1, "xhigh": 2}
DEFAULT_COVERAGE = ("strict", 100)
PROJECTION_KEYS = ("prefill_tokens_per_s", "base_ms", "output_tokens_per_10s")
FAMILY_ORDER = {"meta": 0, "baseten_open": 1, "glimmer_local": 2}


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def resolve_profile(model_cfg: Mapping[str, Any], name: str, sweep_cfg: Mapping[str, Any] | None = None,
                    loader: Any = None) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
    """(config efektif, config sweep | None). Nama profil ada di `config/model` -> TIDAK membaca `config/sweep.toml`.
    Selain itu muat `config/sweep.toml` (`sweep_config` suntikan atau `loader`); hilang -> `sweep_config_missing`, rusak ->
    `config_invalid`. Nama yang tak ada di berkas mengembalikan config asli (pemanggil menolak: profil tak dikenal)."""
    profiles = model_cfg.get("profiles") if isinstance(model_cfg, Mapping) else None
    if isinstance(profiles, Mapping) and name in profiles:
        return model_cfg, None
    sw = sweep_cfg if sweep_cfg is not None else (loader or load_sweep)()
    if has_sweep_profile(sw, name):
        return merge_sweep(model_cfg, sw), sw
    validate_sweep(model_cfg, sw)
    return model_cfg, None


def parent_of(sweep_cfg: Mapping[str, Any], name: str) -> str:
    return sweep_cfg["profiles"][name]["sweep_of"]


def validate_runner_cfg(sweep_cfg: Mapping[str, Any]) -> None:
    """S7(e), S11(g): `[max_attempts]`, `[factor_bp]`, `[projection.*]`, `[compare]` di `config/sweep.toml` -> `config_invalid`."""
    names = set(sweep_profile_names(sweep_cfg))
    for table, minimum in (("max_attempts", 1), ("factor_bp", 10000)):
        t = sweep_cfg.get(table)
        if t is None:
            continue
        if not isinstance(t, Mapping):
            raise ConfigInvalid(f"config/sweep: {table} must be a table")
        for k, v in t.items():
            if k not in names:
                raise ConfigInvalid(f"config/sweep: {table}.{k} is not a profile in config/sweep")
            if not _is_int(v) or v < minimum:
                raise ConfigInvalid(f"config/sweep: {table}.{k} must be an integer >= {minimum}")
    for name in names:
        if parent_of(sweep_cfg, name) == "baseten_open":
            v = (sweep_cfg.get("factor_bp") or {}).get(name)
            if v is None:
                raise ConfigInvalid(f"config/sweep: factor_bp.{name} is required (pinned >= {SWEEP_BASETEN_FACTOR_BP_MIN})")
            if v < SWEEP_BASETEN_FACTOR_BP_MIN:
                raise ConfigInvalid(f"config/sweep: factor_bp.{name} must be >= {SWEEP_BASETEN_FACTOR_BP_MIN} "
                                    f"(the measured H-101 factor)")
    pr = sweep_cfg.get("projection")
    if pr is not None:
        if not isinstance(pr, Mapping):
            raise ConfigInvalid("config/sweep: projection must be a table")
        for k, v in pr.items():
            if k not in names:
                raise ConfigInvalid(f"config/sweep: projection.{k} is not a profile in config/sweep")
            if not isinstance(v, Mapping):
                raise ConfigInvalid(f"config/sweep: projection.{k} must be a table")
            for key in (*PROJECTION_KEYS, "out_tokens"):
                if key in v and (not _is_int(v[key]) or v[key] < 1):
                    raise ConfigInvalid(f"config/sweep: projection.{k}.{key} must be an integer >= 1")
    coverage_policy(sweep_cfg)


def coverage_policy(sweep_cfg: Mapping[str, Any] | None) -> tuple[str, int]:
    """(policy, threshold_pct) dari `[compare]`; tanpa `config/sweep.toml` (profil non-sapuan) atau tanpa tabel = strict."""
    if sweep_cfg is None or "compare" not in sweep_cfg:
        return DEFAULT_COVERAGE
    t = sweep_cfg["compare"]
    if not isinstance(t, Mapping):
        raise ConfigInvalid("config/sweep: compare must be a table")
    pol = t.get("coverage_policy", "strict")
    if not isinstance(pol, str) or pol not in COVERAGE_POLICIES:
        raise ConfigInvalid(f"config/sweep: compare.coverage_policy must be one of {list(COVERAGE_POLICIES)}")
    pct = t.get("coverage_threshold_pct", 100)
    if not _is_int(pct) or not 1 <= pct <= 100:
        raise ConfigInvalid("config/sweep: compare.coverage_threshold_pct must be an integer between 1 and 100")
    return pol, pct


def covered(headered: int, chunks: int, pct: int) -> bool:
    """S11(a): `headered x 100 >= pct x chunks` (inklusif, tanpa float)."""
    return headered * 100 >= pct * chunks


def coverage_bp(headered: int, chunks: int) -> int:
    return headered * 10000 // chunks if chunks else 0


def max_attempts(hc: Mapping[str, Any], sweep_cfg: Mapping[str, Any], name: str, default: int = 8) -> int:
    """S7(e): entri sendiri di `[max_attempts]` sweep menang; selain itu diwarisi dari induk di `config/header_b`."""
    own = (sweep_cfg.get("max_attempts") or {}).get(name)
    if own is not None:
        return int(own)
    t = hc.get("max_attempts")
    v = t.get(parent_of(sweep_cfg, name)) if isinstance(t, Mapping) else None
    return default if v is None else int(v)


def factor_bp(hc: Mapping[str, Any], sweep_cfg: Mapping[str, Any], name: str, gate_bp: int) -> int:
    """S7(e)/S15: `max(gate, entri induk, entri sendiri)`; `sweep_of = baseten_open` tanpa entri atau < 19.312 = `config_invalid`."""
    parent = parent_of(sweep_cfg, name)
    own = (sweep_cfg.get("factor_bp") or {}).get(name)
    if parent == "baseten_open":
        if own is None:
            raise ConfigInvalid(f"config/sweep: factor_bp.{name} is required (pinned >= {SWEEP_BASETEN_FACTOR_BP_MIN})")
        if not _is_int(own) or own < SWEEP_BASETEN_FACTOR_BP_MIN:
            raise ConfigInvalid(f"config/sweep: factor_bp.{name} must be >= {SWEEP_BASETEN_FACTOR_BP_MIN}")
    t = hc.get("factor_bp")
    inherited = t.get(parent) if isinstance(t, Mapping) else None
    return effective_factor_bp(gate_bp, inherited, own)


def time_params(hc: Mapping[str, Any], sweep_cfg: Mapping[str, Any], name: str) -> dict[str, int] | None:
    """S7(e): tiga parameter waktu Glimmer: induk (`[projection.<induk>]` di header_b) ditimpa entri sendiri."""
    pr = hc.get("projection")
    base = pr.get(parent_of(sweep_cfg, name)) if isinstance(pr, Mapping) else None
    own = (sweep_cfg.get("projection") or {}).get(name)
    merged: dict[str, int] = {}
    for src in (base, own):
        if isinstance(src, Mapping):
            merged.update({k: int(src[k]) for k in PROJECTION_KEYS if k in src})
    return merged if len(merged) == len(PROJECTION_KEYS) else None


def out_tokens_for(hc: Mapping[str, Any], sweep_cfg: Mapping[str, Any] | None, name: str) -> int:
    """S16: `out_tokens` di `[projection.<profil>]` sweep; default = `max_output_tokens` header_b (perilaku lama)."""
    own = ((sweep_cfg or {}).get("projection") or {}).get(name) if sweep_cfg else None
    if isinstance(own, Mapping) and "out_tokens" in own:
        return int(own["out_tokens"])
    return int(hc["max_output_tokens"])


def ceil_factor_bp(actual: int, expected: int) -> int:
    """S15: `factor_bp_ukur = ceil(actual x 10.000 / expected)` integer; `expected <= 0` -> `config_invalid`."""
    if not _is_int(actual) or actual < 0 or not _is_int(expected):
        raise ConfigInvalid("factor measurement needs integer actual >= 0 and expected")
    if expected <= 0:
        raise ConfigInvalid("factor measurement: the expected projection is 0 (no division by zero)")
    return -(-actual * 10000 // expected)


def effective_factor_bp(gate_bp: int, *others: int | None) -> int:
    """S15: `max([batch_gate].factor_bp, nilai terpin, ukur pilot)`; tidak pernah turun di bawah gerbang."""
    return max([int(gate_bp), *(int(x) for x in others if x is not None)])


def sweep_order(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """S17(a): DI DALAM satu model naik menurut `total`; seri -> peringkat effort lalu nama profil. Antar model (D3):
    Contributor (`meta`), Spark Open (`baseten_open`), Glimmer (`glimmer_local`) lewat `family` = profil induk."""
    return sorted(items, key=lambda i: (FAMILY_ORDER.get(i.get("family"), 9), i["total"], EFFORT_RANK.get(i.get("effort"), 9),
                                        i["profile"]))


def sweep_status(done: int, total: int, *, pool_rejected: bool = False) -> str:
    """S17(d): `complete` | `partial (n/m unit)` | `not_run (pool)`."""
    if total > 0 and done >= total:
        return "complete"
    if done == 0 and pool_rejected:
        return "not_run (pool)"
    return f"partial ({done}/{total} unit)"


def reuse_confirmed_relative(latencies_ms: Sequence[int], saving_ms: int) -> bool | None:
    """S16(d): `X = L1 - ceil(S/2)`; terkonfirmasi bila dua nilai tengah (urut) panggilan 2..5 `a + b <= 2 X` (tanpa `//`).
    None bila < 5 panggilan."""
    if len(latencies_ms) < 5:
        return None
    x = latencies_ms[0] - (-(-saving_ms // 2))
    rest = sorted(latencies_ms[1:5])
    return rest[1] + rest[2] <= 2 * x


def go_required(prof: Mapping[str, Any], *, project_only: bool, confirm_go: bool) -> bool:
    """P15/S20(d): B Spark Open sapuan (`sweep_of = baseten_open`) tanpa `--confirm-go` hanya boleh `--project-only`."""
    return prof.get("sweep") is True and prof.get("sweep_of") == "baseten_open" and not project_only and not confirm_go


def uses_model_api_lock(prof: Mapping[str, Any]) -> bool:
    """P9: runner sapuan Contributor (`sweep_of = meta`) mengambil `model_api_meta.lock`."""
    return prof.get("sweep") is True and prof.get("sweep_of") == "meta"
