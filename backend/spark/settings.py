"""Setelan klien dari `config/model` + env. Gagal tertutup (`config_invalid`) sebelum jaringan.

Key dan base URL hanya hidup di `Settings` (field repr=False, repr kustom); tidak pernah masuk
record, log, atau pesan galat (T1, T7). Pesan galat hanya menyebut NAMA variabel env."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from backend import config as cfg

from .errors import ConfigInvalid
from .money import validate_pricing
from .ratelimit import MAX_RPM_EXCLUSIVE

API_RESPONSES = "responses"
API_CHAT = "chat_completions"  # hanya klien lokal Glimmer (H-047), endpoint loopback
LOCAL_PLACEHOLDER_KEY = "local-no-key"  # konstanta non-rahasia; SDK mewajibkan string, server lokal tidak memeriksanya
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
REQUIRED_LIMITS_NUM = ("timeout_s", "backoff_base_s", "backoff_factor", "max_wait_s")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


FORBIDDEN_PROFILE_KEYS = ("max_header_tokens", "schema_max_length_chars")


def check_forbidden_profile_keys(model_cfg: Mapping[str, Any]) -> None:
    """H-101 P17: validator header sama untuk semua model; kunci ini di `[profiles.*]` = config_invalid.
    Kunci tak dikenal lain tetap diabaikan."""
    profiles = model_cfg.get("profiles") if isinstance(model_cfg, Mapping) else None
    if not isinstance(profiles, Mapping):
        return
    for name, p in profiles.items():
        if isinstance(p, Mapping):
            for k in FORBIDDEN_PROFILE_KEYS:
                if k in p:
                    raise ConfigInvalid(f"config/model: profile '{name}' must not set '{k}' (the header validator is the "
                                        f"same for every model; set it in config/header_b)")


def load_configs(config_dir: Path | None = None) -> tuple[dict, dict]:
    """(model, budget) dari `config/`. Berkas hilang/rusak -> ConfigInvalid."""
    try:
        model, budget = cfg.load("model", config_dir), cfg.load("budget", config_dir)
    except cfg.ConfigError as exc:
        raise ConfigInvalid(str(exc)) from None
    check_forbidden_profile_keys(model)
    return model, budget


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


def is_loopback_url(url: Any) -> bool:
    """http(s) ke 127.0.0.1 / localhost / ::1 saja (H-047: Glimmer lokal, backend tidak keluar mesin)."""
    if not isinstance(url, str):
        return False
    try:
        u = urlsplit(url.strip())
        return u.scheme in ("http", "https") and (u.hostname or "").lower() in LOOPBACK_HOSTS
    except ValueError:
        return False


def profile_api(p: Mapping[str, Any]) -> str:
    return API_CHAT if p.get("api") == API_CHAT else API_RESPONSES


def profile_cfg(model_cfg: Mapping[str, Any], profile: str) -> Mapping[str, Any]:
    profiles = model_cfg.get("profiles")
    p = profiles.get(profile) if isinstance(profiles, Mapping) else None
    if not isinstance(p, Mapping):
        raise ConfigInvalid(f"config/model: unknown profile '{profile}'")
    if p.get("api") not in (None, API_RESPONSES, API_CHAT):
        # H-113: profil `asr_transcribe` (pemeriksa VO) dan nilai `api` lain tidak bisa dipakai SparkClient.
        raise ConfigInvalid(f"config/model: profile '{profile}' uses api '{p.get('api')}', which the Spark client does not support")
    required = ("provider", "model") if profile_api(p) == API_CHAT else ("provider", "model", "api_key_env")
    for k in required:
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
    api: str = API_RESPONSES
    effort_override: str | None = None  # profil Glimmer: reasoning_effort dipin di profil (H-047)
    max_output_tokens_floor: int | None = None  # profil reasoning-berat: batas keluaran minimal (G-26)
    sweep: bool = False  # profil sapuan effort (H-102): hasil gabungan `merge_sweep`, bukan dari `config/model`
    rate_group: str | None = None  # kelompok pembatas laju bersama (P9); None = kunci per profil

    def __repr__(self) -> str:  # tanpa key dan base URL (S10)
        return f"Settings(profile={self.profile!r}, provider={self.provider!r}, model={self.model!r})"

    __str__ = __repr__


def _opt_str(profile: str, p: Mapping[str, Any], k: str) -> str | None:
    v = p.get(k)
    if v is None:
        return None
    if not isinstance(v, str) or not v:
        raise ConfigInvalid(f"config/model: profile '{profile}' {k} must be a non-empty string")
    return v


def _opt_int(profile: str, p: Mapping[str, Any], k: str) -> int | None:
    v = p.get(k)
    if v is None:
        return None
    if not _is_int(v) or v < 1:
        raise ConfigInvalid(f"config/model: profile '{profile}' {k} must be a positive integer")
    return v


def _profile_limits(profile: str, p: Mapping[str, Any], base: Limits) -> Limits:
    """Override per profil untuk `timeout_s` dan `max_retries` (reasoning panjang, G-26)."""
    t = p.get("timeout_s")
    r = p.get("max_retries")
    if t is not None and (not _is_num(t) or t <= 0):
        raise ConfigInvalid(f"config/model: profile '{profile}' timeout_s must be > 0")
    if r is not None and (not _is_int(r) or r < 0):
        raise ConfigInvalid(f"config/model: profile '{profile}' max_retries must be a non-negative integer")
    return replace(base, timeout_s=base.timeout_s if t is None else t, max_retries=base.max_retries if r is None else r)


def build_settings(profile: str, model_cfg: Mapping[str, Any], env: Mapping[str, str], *,
                   need_credentials: bool = True) -> Settings:
    check_forbidden_profile_keys(model_cfg)
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

    api = profile_api(p)
    if api == API_CHAT:
        # Glimmer lokal: loopback saja, tanpa key (placeholder konstan), validasi dilakukan selalu (juga replay).
        bu = p.get("base_url")
        if not is_loopback_url(bu):
            raise ConfigInvalid(f"config/model: profile '{profile}' must use a loopback base_url (127.0.0.1, localhost or ::1)")
        limits = _profile_limits(profile, p, limits)
        return Settings(
            profile=profile, provider=p["provider"], model=p["model"],
            quantization=p["quantization"] if isinstance(p.get("quantization"), str) else None,
            host_label=host, device="local", pricing=pricing, limits=limits,
            api_key=LOCAL_PLACEHOLDER_KEY, base_url=bu.strip(), api_key_env="",
            for_reported_numbers=bool(p.get("for_reported_numbers", False)), all_secrets=(), api=API_CHAT,
            effort_override=_opt_str(profile, p, "reasoning_effort"),
            max_output_tokens_floor=_opt_int(profile, p, "max_output_tokens"),
            sweep=p.get("sweep") is True, rate_group=_opt_str(profile, p, "rate_group"),
        )
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
        max_output_tokens_floor=_opt_int(profile, p, "max_output_tokens"),
        # S2 (H-102): profil Responses yang memin `reasoning_effort` (profil sapuan) benar-benar mengirim pin itu.
        # Profil tanpa kunci (meta, openrouter_dev, baseten_open) tetap None: byte-identik (S19).
        effort_override=_opt_str(profile, p, "reasoning_effort"),
        sweep=p.get("sweep") is True, rate_group=_opt_str(profile, p, "rate_group"),
    )
