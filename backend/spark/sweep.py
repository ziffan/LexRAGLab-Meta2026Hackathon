"""Profil sapuan effort (H-102, H-103; skenario M3.2-effort-sweep S1, S5, P1, P2, P16).

`config/sweep.toml` dibaca HANYA oleh runner sapuan dan `SparkClient` yang diberi nama profil sapuan (jalur utama tidak
membacanya sama sekali, ARCHITECTURE §7). Profil sapuan hanya memuat kunci `sweep_of`, `reasoning_effort`,
`max_output_tokens`, `roles`, `label`, `rate_group`; `model`, `provider`, `quantization`, `api`, `base_url*`, `api_key_env`,
`pricing` diturunkan dari profil induk di `config/model` oleh `merge_sweep` (Model ID tidak punya salinan kedua).
`merge_sweep` menyuntikkan `for_reported_numbers = false` dan `sweep = true`. Uang integer micro-USD."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend import config as cfg

from .errors import ConfigInvalid

SWEEP_VERSION = 1
EFFORTS = ("low", "medium", "high", "xhigh")
SWEEP_ROLES = ("a", "b", "c")
ALLOWED_KEYS = ("sweep_of", "reasoning_effort", "max_output_tokens", "roles", "label", "rate_group")
IDENTITY_KEYS = ("model", "provider", "quantization", "api", "base_url", "base_url_env", "api_key_env", "pricing",
                 "for_reported_numbers", "sweep")
P17_KEYS = ("max_header_tokens", "schema_max_length_chars")
TUPLE_ROLES = ("a", "b", "c", "d", "measure")
SWEEP_BASETEN_FACTOR_BP_MIN = 19312  # faktor terukur H-101 (P7); dipakai pemeriksa `factor_bp_for` runner B


class SweepConfigMissing(ConfigInvalid):
    code = "sweep_config_missing"


class SweepPoolMissing(ConfigInvalid):
    code = "sweep_pool_missing"


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def load_sweep(config_dir: Path | None = None) -> dict[str, Any]:
    """Muat `config/sweep.toml`. Hilang -> `sweep_config_missing`; rusak -> `config_invalid`."""
    path = (config_dir or cfg.CONFIG_DIR) / "sweep.toml"
    if not path.exists():
        raise SweepConfigMissing("sweep_config_missing: config/sweep.toml is not present")
    try:
        data = cfg.load("sweep", config_dir)
    except cfg.ConfigError as exc:
        raise ConfigInvalid(str(exc)) from None
    return data


def sweep_config_hash(model_cfg: Mapping[str, Any], budget_cfg: Mapping[str, Any], sweep_cfg: Mapping[str, Any]) -> str:
    """Hash gabungan `config_hash({"model", "budget", "sweep"})` atas isi tiga berkas ASLI (P16)."""
    return cfg.config_hash({"model": dict(model_cfg), "budget": dict(budget_cfg), "sweep": dict(sweep_cfg)})


def sweep_profile_names(sweep_cfg: Mapping[str, Any]) -> list[str]:
    p = sweep_cfg.get("profiles") if isinstance(sweep_cfg, Mapping) else None
    return list(p) if isinstance(p, Mapping) else []


def has_sweep_profile(sweep_cfg: Mapping[str, Any] | None, name: str) -> bool:
    return isinstance(sweep_cfg, Mapping) and name in sweep_profile_names(sweep_cfg)


def _main_efforts(model_cfg: Mapping[str, Any], p: Mapping[str, Any]) -> dict[str, str]:
    """effort jalur utama profil non-`sweep`: pin -> {"pin": e}; selain itu [effort].<k> untuk k di TUPLE_ROLES."""
    pin = p.get("reasoning_effort")
    if isinstance(pin, str) and pin:
        return {"pin": pin}
    tbl = model_cfg.get("effort")
    out: dict[str, str] = {}
    if isinstance(tbl, Mapping):
        for k in TUPLE_ROLES:
            v = tbl.get(k)
            if isinstance(v, str) and v:
                out[k] = v
    return out


def _opt_quant(p: Mapping[str, Any]) -> str | None:
    q = p.get("quantization")
    return q if isinstance(q, str) else None


def validate_sweep(model_cfg: Mapping[str, Any], sweep_cfg: Mapping[str, Any]) -> None:
    """P1/P2/S5: `config_invalid` (atau `sweep_pool_missing`) sebelum jaringan; pesan menyebut profil dan kunci."""
    if not isinstance(sweep_cfg, Mapping):
        raise ConfigInvalid("config/sweep: must be a table")
    v = sweep_cfg.get("version")
    if not _is_int(v) or v != SWEEP_VERSION:
        raise ConfigInvalid(f"config/sweep: version must be the integer {SWEEP_VERSION}")
    profiles = sweep_cfg.get("profiles", {})
    if not isinstance(profiles, Mapping):
        raise ConfigInvalid("config/sweep: profiles must be a table")
    model_profiles = model_cfg.get("profiles") if isinstance(model_cfg, Mapping) else None
    if not isinstance(model_profiles, Mapping):
        model_profiles = {}
    tuples: dict[tuple[Any, ...], str] = {}
    for name, p in profiles.items():
        if name in model_profiles:
            raise ConfigInvalid(f"config/sweep: profile '{name}' collides with a profile in config/model")
        if not isinstance(p, Mapping):
            raise ConfigInvalid(f"config/sweep: profile '{name}' must be a table")
        for k in IDENTITY_KEYS + P17_KEYS:
            if k in p:
                raise ConfigInvalid(f"config/sweep: profile '{name}' must not set '{k}' "
                                    f"(model identity is derived from the parent profile in config/model)")
        parent_name = p.get("sweep_of")
        if not isinstance(parent_name, str) or not parent_name:
            raise ConfigInvalid(f"config/sweep: profile '{name}' has no valid 'sweep_of'")
        parent = model_profiles.get(parent_name)
        if not isinstance(parent, Mapping) or parent.get("sweep") is True:
            raise ConfigInvalid(f"config/sweep: profile '{name}' sweep_of '{parent_name}' is not a non-sweep profile "
                                f"in config/model")
        eff = p.get("reasoning_effort")
        if not isinstance(eff, str) or eff not in EFFORTS:
            raise ConfigInvalid(f"config/sweep: profile '{name}' reasoning_effort must be one of {list(EFFORTS)}")
        mot = p.get("max_output_tokens")
        if mot is not None and (not _is_int(mot) or mot < 1):
            raise ConfigInvalid(f"config/sweep: profile '{name}' max_output_tokens must be a positive integer")
        roles = p.get("roles")
        if "roles" not in p:
            raise ConfigInvalid(f"config/sweep: profile '{name}' has no 'roles'")
        if (not isinstance(roles, list) or not roles
                or any((not isinstance(r, str)) or r not in SWEEP_ROLES for r in roles)):
            raise ConfigInvalid(f"config/sweep: profile '{name}' roles must be a non-empty subset of {list(SWEEP_ROLES)}")
        for k in ("label", "rate_group"):
            if k in p and (not isinstance(p[k], str) or not p[k]):
                raise ConfigInvalid(f"config/sweep: profile '{name}' {k} must be a non-empty string")
        tup = (parent.get("provider"), parent.get("model"), _opt_quant(parent), eff)
        if tup in tuples:
            raise ConfigInvalid(f"config/sweep: profiles '{tuples[tup]}' and '{name}' have the same "
                                f"(provider, model, quantization, effort) tuple")
        tuples[tup] = name
        for qname, q in model_profiles.items():
            if not isinstance(q, Mapping) or q.get("sweep") is True:
                continue
            if (q.get("provider"), q.get("model"), _opt_quant(q)) != tup[:3]:
                continue
            for role, e in _main_efforts(model_cfg, q).items():
                if e == eff:
                    where = "its pin" if role == "pin" else f"[effort].{role}"
                    raise ConfigInvalid(f"config/sweep: profile '{name}' duplicates the main-path tuple of profile "
                                        f"'{qname}' ({where} = '{e}'); revise explicitly")
    _validate_pool(model_profiles, sweep_cfg, profiles)


def _validate_pool(model_profiles: Mapping[str, Any], sweep_cfg: Mapping[str, Any], profiles: Mapping[str, Any]) -> None:
    if "sweep_pool" not in sweep_cfg:
        if profiles:
            raise SweepPoolMissing("sweep_pool_missing: config/sweep has sweep profiles but no [sweep_pool]")
        return
    pool = sweep_cfg["sweep_pool"]
    if not isinstance(pool, Mapping):
        raise ConfigInvalid("config/sweep: sweep_pool must be a table")
    for k in ("cap_micros", "profiles"):
        if k not in pool:
            raise ConfigInvalid(f"config/sweep: sweep_pool.{k} is missing")
    cap = pool["cap_micros"]
    if not _is_int(cap) or cap < 0:
        raise ConfigInvalid("config/sweep: sweep_pool.cap_micros must be a non-negative integer")
    if "cumulative_pct" in pool:
        pct = pool["cumulative_pct"]
        if not _is_int(pct) or not 1 <= pct <= 100:
            raise ConfigInvalid("config/sweep: sweep_pool.cumulative_pct must be an integer between 1 and 100")
    names = pool["profiles"]
    if not isinstance(names, list) or not names:
        raise ConfigInvalid("config/sweep: sweep_pool.profiles must be a non-empty list")
    seen: set[str] = set()
    for n in names:
        if not isinstance(n, str) or not n.strip():
            raise ConfigInvalid("config/sweep: sweep_pool.profiles has an empty or non-string name")
        if n in seen:
            raise ConfigInvalid(f"config/sweep: sweep_pool.profiles lists '{n}' twice")
        seen.add(n)
        if n in model_profiles:
            raise ConfigInvalid(f"config/sweep: sweep_pool.profiles lists '{n}', a non-sweep profile in config/model")
        if n not in profiles:
            raise ConfigInvalid(f"config/sweep: sweep_pool.profiles lists '{n}', which is not a profile in config/sweep")
    for n in profiles:
        if n not in seen:
            raise ConfigInvalid(f"config/sweep: sweep profile '{n}' is not listed in sweep_pool.profiles")


def sweep_pool_cap(sweep_cfg: Mapping[str, Any]) -> int:
    """`[sweep_pool].cap_micros` (integer micro-USD >= 0; 0 sah = nol)."""
    pool = sweep_cfg.get("sweep_pool") if isinstance(sweep_cfg, Mapping) else None
    if not isinstance(pool, Mapping) or not _is_int(pool.get("cap_micros")) or pool["cap_micros"] < 0:
        raise ConfigInvalid("config/sweep: sweep_pool.cap_micros is missing or invalid")
    return pool["cap_micros"]


def sweep_pool_cumulative_pct(sweep_cfg: Mapping[str, Any]) -> int | None:
    """`[sweep_pool].cumulative_pct` (H-105): integer 1..100, atau None bila kunci hilang (pakai `[batch_gate]`)."""
    pool = sweep_cfg.get("sweep_pool") if isinstance(sweep_cfg, Mapping) else None
    if not isinstance(pool, Mapping) or "cumulative_pct" not in pool:
        return None
    pct = pool["cumulative_pct"]
    if not _is_int(pct) or not 1 <= pct <= 100:
        raise ConfigInvalid("config/sweep: sweep_pool.cumulative_pct must be an integer between 1 and 100")
    return pct


def merge_sweep(model_cfg: Mapping[str, Any], sweep_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Gabungan di memori: semua profil `config/model` apa adanya + profil sapuan turunan induk (P16). Memvalidasi dulu.
    `default_profile`, `[effort]`, `[pricing]`, `[limits]`, `host` dari `config/model`."""
    validate_sweep(model_cfg, sweep_cfg)
    merged = copy.deepcopy(dict(model_cfg))
    mp = merged.setdefault("profiles", {})
    for name, p in (sweep_cfg.get("profiles") or {}).items():
        parent_name = p["sweep_of"]
        parent = model_cfg["profiles"][parent_name]
        d = copy.deepcopy(dict(parent))
        d["pricing"] = parent.get("pricing", parent_name)
        d["reasoning_effort"] = p["reasoning_effort"]
        d["roles"] = list(p["roles"])
        if "max_output_tokens" in p:
            d["max_output_tokens"] = p["max_output_tokens"]
        d["label"] = p.get("label") or name
        if "rate_group" in p:
            d["rate_group"] = p["rate_group"]
        d["for_reported_numbers"] = False
        d["sweep"] = True
        d["sweep_of"] = parent_name
        mp[name] = d
    return merged
