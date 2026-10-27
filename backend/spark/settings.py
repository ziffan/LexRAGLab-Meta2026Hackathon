"""Setelan klien dari `config/model` + env. Gagal tertutup (`config_invalid`) sebelum jaringan.

Key dan base URL hanya hidup di `Settings` (field repr=False, repr kustom); tidak pernah masuk
record, log, atau pesan galat (T1, T7). Pesan galat hanya menyebut NAMA variabel env."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend import config as cfg

from .errors import ConfigInvalid
from .money import validate_pricing
from .ratelimit import MAX_RPM_EXCLUSIVE

REQUIRED_LIMITS_NUM = ("timeout_s", "backoff_base_s", "backoff_factor", "max_wait_s")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_configs(config_dir: Path | None = None) -> tuple[dict, dict]:
    """(model, budget) dari `config/`. Berkas hilang/rusak -> ConfigInvalid."""
    try:
        return cfg.load("model", config_dir), cfg.load("budget", config_dir)
    except cfg.ConfigError as exc:
        raise ConfigInvalid(str(exc)) from None


@dataclass(frozen=True)
class Limits:
    max_rpm: int
    timeout_s: float
    max_retries: int
    backoff_base_s: float
    backoff_factor: float
    max_429_retries: int
    max_wait_s: float


def parse_limits(model_cfg: Mapping[str, Any]) -> Limits:
    lim = model_cfg.get("limits")
    if not isinstance(lim, Mapping):
        raise ConfigInvalid("config/model: [limits] is missing")
    for k in ("max_rpm", "max_retries", "max_429_retries"):
        if not _is_int(lim.get(k)) or lim[k] < 0:
            raise ConfigInvalid(f"config/model limits.{k} must be a non-negative integer")
    for k in REQUIRED_LIMITS_NUM:
        if not _is_num(lim.get(k)) or lim[k] < 0:
            raise ConfigInvalid(f"config/model limits.{k} must be a non-negative number")
    if lim["max_rpm"] < 1 or lim["max_rpm"] >= MAX_RPM_EXCLUSIVE:
        raise ConfigInvalid(f"config/model limits.max_rpm must be between 1 and {MAX_RPM_EXCLUSIVE - 1} (G-19)")
    if lim["timeout_s"] <= 0 or lim["max_wait_s"] <= 0 or lim["backoff_factor"] < 1:
        raise ConfigInvalid("config/model limits: timeout_s and max_wait_s must be > 0, backoff_factor >= 1")
    return Limits(max_rpm=lim["max_rpm"], timeout_s=lim["timeout_s"], max_retries=lim["max_retries"],
                  backoff_base_s=lim["backoff_base_s"], backoff_factor=lim["backoff_factor"],
                  max_429_retries=lim["max_429_retries"], max_wait_s=lim["max_wait_s"])


def clean_env_value(raw: Any) -> str:
    """Buang spasi dan sisa CR/LF dari `.env` Windows (G-16)."""
    return raw.strip() if isinstance(raw, str) else ""


def profile_cfg(model_cfg: Mapping[str, Any], profile: str) -> Mapping[str, Any]:
    profiles = model_cfg.get("profiles")
    p = profiles.get(profile) if isinstance(profiles, Mapping) else None
    if not isinstance(p, Mapping):
        raise ConfigInvalid(f"config/model: unknown profile '{profile}'")
    for k in ("provider", "model", "api_key_env"):
        if not isinstance(p.get(k), str) or not p[k]:
            raise ConfigInvalid(f"config/model: profile '{profile}' has no valid '{k}'")
    return p


def effort_for(model_cfg: Mapping[str, Any], role: str) -> str:
    eff = model_cfg.get("effort")
    v = eff.get(role) if isinstance(eff, Mapping) and isinstance(role, str) else None
    if not isinstance(v, str) or not v:
        raise ConfigInvalid(f"config/model: no effort configured for role '{role}'")
    return v


@dataclass
class Settings:
    profile: str
    provider: str
    model: str
    quantization: str | None
    host_label: str
    device: str
    pricing: dict[str, int]
    limits: Limits
    api_key: str = field(repr=False)
    base_url: str = field(repr=False)
    api_key_env: str
    for_reported_numbers: bool
    all_secrets: tuple[str, ...] = field(repr=False, default=())

    def __repr__(self) -> str:  # tanpa key dan base URL (S10)
        return f"Settings(profile={self.profile!r}, provider={self.provider!r}, model={self.model!r})"

    __str__ = __repr__


def build_settings(profile: str, model_cfg: Mapping[str, Any], env: Mapping[str, str], *,
                   need_credentials: bool = True) -> Settings:
    p = profile_cfg(model_cfg, profile)
    limits = parse_limits(model_cfg)
    host = model_cfg.get("host")
    if not isinstance(host, str) or not host:
        raise ConfigInvalid("config/model: 'host' label is missing (e.g. authoritative / secondary)")
    pricing_name = p.get("pricing", profile)
    pricing_tbl = model_cfg.get("pricing", {})
    block = pricing_tbl.get(pricing_name) if isinstance(pricing_tbl, Mapping) else None
    if not isinstance(block, Mapping):
        raise ConfigInvalid(f"config/model: no [pricing.{pricing_name}] block for profile '{profile}'")
    try:
        pricing = validate_pricing({
            "input": block.get("input_per_mtok_micros"),
            "cached": block.get("cached_per_mtok_micros"),
            "output": block.get("output_per_mtok_micros"),
        })
    except ValueError as exc:
        raise ConfigInvalid(f"config/model [pricing.{pricing_name}]: {exc}") from None

    key_env = p["api_key_env"]
    api_key = clean_env_value(env.get(key_env))
    base_url = ""
    if need_credentials:
        if not api_key:
            raise ConfigInvalid(f"environment variable {key_env} is not set or empty")
        if re.search(r"[\x00-\x1f\x7f\s]", api_key):
            raise ConfigInvalid(f"environment variable {key_env} contains invalid characters")
        if isinstance(p.get("base_url"), str) and p["base_url"]:
            base_url = p["base_url"].strip()
        else:
            be = p.get("base_url_env")
            if not isinstance(be, str) or not be:
                raise ConfigInvalid(f"config/model: profile '{profile}' has no base URL source")
            base_url = clean_env_value(env.get(be))
            if not base_url:
                raise ConfigInvalid(f"environment variable {be} is not set or empty")
        if not base_url.startswith("https://"):
            raise ConfigInvalid("base URL must use https")
    secrets = tuple(s for s in (api_key, base_url) if s)
    quant = p.get("quantization")
    return Settings(
        profile=profile, provider=p["provider"], model=p["model"],
        quantization=quant if isinstance(quant, str) else None,
        host_label=host, device="remote", pricing=pricing, limits=limits,
        api_key=api_key, base_url=base_url, api_key_env=key_env,
        for_reported_numbers=bool(p.get("for_reported_numbers", False)), all_secrets=secrets,
    )
