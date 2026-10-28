"""Cost guard (SECURITY-COMPLIANCE T6): cap efektif, buku belanja, proyeksi.

Semua uang integer micro-USD. Cap total = min(config, env) (D1); env kosong = tidak diset, env
non-kosong tidak valid = config_invalid (O-12 alt. 2); peran tanpa cap = config_invalid (O-11)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import store
from .errors import ConfigInvalid

ENV_CAP = "DEV_SPEND_CAP_MICRO_USD"
_DIGITS = re.compile(r"[0-9]+")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


@dataclass(frozen=True)
class Caps:
    total_micros: int
    total_source: str  # "config" | "env"
    per_role_micros: dict[str, int]
    provider_micros: dict[str, int] = field(default_factory=dict)  # plafon pool per provider (H-101 P6)


def provider_caps(budget_cfg: Mapping[str, Any], model_cfg: Mapping[str, Any] | None = None) -> dict[str, int]:
    """Tabel `[provider_cap_micros]` (H-101 P6): provider -> plafon pool (integer micro-USD >= 0; 0 sah = nol, bukan
    tanpa batas). Tabel tidak ada -> `{}` (satu pool, perilaku lama). `version` < 2 dengan tabel = config_invalid (P16).
    `model_cfg` diberikan -> kunci harus provider yang ada di `profiles.*.provider` (typo tidak jatuh diam ke pool default)."""
    if not isinstance(budget_cfg, Mapping) or "provider_cap_micros" not in budget_cfg:
        return {}
    table = budget_cfg["provider_cap_micros"]
    if not isinstance(table, Mapping):
        raise ConfigInvalid("config/budget: provider_cap_micros must be a table")
    version = budget_cfg.get("version")
    if not _is_int(version) or version < 2:
        raise ConfigInvalid("config/budget: provider_cap_micros requires version >= 2")
    known: set[str] | None = None
    if model_cfg is not None:
        profiles = model_cfg.get("profiles") if isinstance(model_cfg, Mapping) else None
        known = ({str(p["provider"]) for p in profiles.values()
                  if isinstance(p, Mapping) and isinstance(p.get("provider"), str)}
                 if isinstance(profiles, Mapping) else set())
    out: dict[str, int] = {}
    for k, v in table.items():
        if not isinstance(k, str) or not k.strip():
            raise ConfigInvalid("config/budget: provider_cap_micros has an empty provider key")
        if not _is_int(v) or v < 0:
            raise ConfigInvalid(f"config/budget: provider_cap_micros.{k} must be a non-negative integer")
        if known is not None and k not in known:
            raise ConfigInvalid(f"config/budget: provider_cap_micros.{k} is not a provider in config/model profiles")
        out[k] = v
    return out


def effective_caps(budget_cfg: Mapping[str, Any], env: Mapping[str, str] | None,
                   model_cfg: Mapping[str, Any] | None = None) -> Caps:
    total = budget_cfg.get("dev_total_cap_micros") if isinstance(budget_cfg, Mapping) else None
    if not _is_int(total) or total < 0:
        raise ConfigInvalid("config/budget: dev_total_cap_micros must be a non-negative integer")
    roles = budget_cfg.get("per_role_cap_micros")
    if not isinstance(roles, Mapping):
        raise ConfigInvalid("config/budget: per_role_cap_micros is missing")
    per_role: dict[str, int] = {}
    for k, v in roles.items():
        if not _is_int(v) or v < 0:
            raise ConfigInvalid(f"config/budget: per_role_cap_micros.{k} must be a non-negative integer")
        per_role[str(k)] = v
    raw = (env or {}).get(ENV_CAP)
    cap, source = total, "config"
    if isinstance(raw, str) and raw.strip() != "":
        s = raw.strip()
        if not _DIGITS.fullmatch(s):
            raise ConfigInvalid(f"environment variable {ENV_CAP} must be a non-negative integer (micro-USD) or empty")
        env_cap = int(s)
        if env_cap < total:
            cap, source = env_cap, "env"
    return Caps(total_micros=cap, total_source=source, per_role_micros=per_role,
                provider_micros=provider_caps(budget_cfg, model_cfg))


class Ledger:
    """Buku belanja = jumlah `cost ?? projected` semua RunRecord tersimpan (T6, O-3 cabang A)."""

    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = Path(runs_dir)

    def spent(self, role: str | None = None, provider: str | None = None) -> int:
        try:
            records = store.load_records(self.runs_dir)
        except ValueError as exc:
            raise ConfigInvalid(str(exc)) from None
        total = 0
        for r in records:
            if role is not None and r.role() != role:
                continue
            if provider is not None and r.provider != provider:
                continue
            total += r.spend_micros()
        return total

    def spent_pool(self, provider: str, caps: Mapping[str, int], role: str | None = None) -> int:
        """Belanja pool tempat `provider` berada (H-101 P6). Provider tercantum di `caps` -> belanja provider itu saja
        (semua peran, atau satu peran). Selain itu -> pool default = semua rekaman yang provider-nya TIDAK tercantum
        di `caps` (= total dikurangi semua provider tercantum), dengan filter peran bila diberikan."""
        try:
            records = store.load_records(self.runs_dir)
        except ValueError as exc:
            raise ConfigInvalid(str(exc)) from None
        listed = provider in caps
        total = 0
        for r in records:
            if role is not None and r.role() != role:
                continue
            if (r.provider == provider) if listed else (r.provider not in caps):
                total += r.spend_micros()
        return total


@dataclass
class Projection:
    per_call_micros: list[int]
    total_micros: int
    effective_total_cap_micros: int
    total_cap_source: str
    role: str
    role_cap_micros: int
    spent_micros: int
    spent_role_micros: int
    verdict: str  # "ok" | "budget_exceeded"
    reason: str | None = field(default=None)
    pool: str = "default"  # "default" atau nama provider berplafon (H-101 S10 (g))
    pool_cap_micros: int = 0
    pool_spent_micros: int = 0


def evaluate(role: str, caps: Caps, projected: list[int], spent_total: int, spent_role: int, *,
             provider: str | None = None, spent_provider: int | None = None) -> Projection:
    """Pool default (provider tak tercantum di `caps.provider_micros`): `spent_total`/`spent_role` = belanja pool default,
    dibanding cap total dan cap peran. Pool provider: `spent_provider` dibanding plafon provider; cap total dan cap peran
    tidak berlaku (H-101 P6, S10)."""
    if role not in caps.per_role_micros:
        raise ConfigInvalid(f"config/budget: no per_role_cap_micros entry for role '{role}'")
    role_cap = caps.per_role_micros[role]
    total_proj = sum(projected)
    if provider is not None and provider in caps.provider_micros:
        if spent_provider is None:
            raise ConfigInvalid("provider pool spend is required for a provider with a cap")
        pcap = caps.provider_micros[provider]
        reason = None
        if spent_provider + total_proj > pcap:
            reason = (f"spent {spent_provider} + projected {total_proj} = {spent_provider + total_proj} micro-USD "
                      f"exceeds provider {provider} cap {pcap} micro-USD")
        return Projection(
            per_call_micros=list(projected), total_micros=total_proj,
            effective_total_cap_micros=caps.total_micros, total_cap_source=caps.total_source,
            role=role, role_cap_micros=role_cap, spent_micros=spent_provider, spent_role_micros=spent_role,
            verdict="ok" if reason is None else "budget_exceeded", reason=reason,
            pool=provider, pool_cap_micros=pcap, pool_spent_micros=spent_provider,
        )
    parts = []
    if spent_role + total_proj > role_cap:
        parts.append(f"spent {spent_role} + projected {total_proj} = {spent_role + total_proj} micro-USD "
                     f"exceeds role {role} cap {role_cap} micro-USD")
    if spent_total + total_proj > caps.total_micros:
        parts.append(f"spent {spent_total} + projected {total_proj} = {spent_total + total_proj} micro-USD "
                     f"exceeds total cap {caps.total_micros} micro-USD (source: {caps.total_source})")
    reason = "; ".join(parts) if parts else None
    return Projection(
        per_call_micros=list(projected), total_micros=total_proj,
        effective_total_cap_micros=caps.total_micros, total_cap_source=caps.total_source,
        role=role, role_cap_micros=role_cap, spent_micros=spent_total, spent_role_micros=spent_role,
        verdict="ok" if reason is None else "budget_exceeded", reason=reason,
        pool="default", pool_cap_micros=caps.total_micros, pool_spent_micros=spent_total,
    )
