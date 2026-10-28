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
from .runrecord import role_for_kind

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


def _rec_field(rec: Any, name: str) -> Any:
    return rec.get(name) if isinstance(rec, Mapping) else getattr(rec, name, None)


def _opt_quant(p: Mapping[str, Any]) -> str | None:
    q = p.get("quantization")
    return q if isinstance(q, str) else None


def _effective_efforts(model_cfg: Mapping[str, Any], p: Mapping[str, Any], role: str | None) -> set[str] | None:
    """Himpunan effort efektif profil non-`sweep` `p`: pin `reasoning_effort` bila ada; selain itu `[effort].<role>`
    (`role` None = semua peran di `[effort]`, untuk gerbang laporan kind `grid`). None = tak terdefinisi."""
    pin = p.get("reasoning_effort")
    if isinstance(pin, str) and pin:
        return {pin}
    tbl = model_cfg.get("effort") if isinstance(model_cfg, Mapping) else None
    if not isinstance(tbl, Mapping):
        return None
    if role is None:
        vals = {v for v in tbl.values() if isinstance(v, str) and v}
        return vals or None
    v = tbl.get(role)
    return {v} if isinstance(v, str) and v else None


def is_off_pin(record: Any, model_cfg: Mapping[str, Any], *, grid_by_set: bool = False) -> bool:
    """Rekaman OFF-PIN (H-102 P3): (`provider`, `model`, `quantization`) cocok profil NON-`sweep` di `config/model`
    tetapi `effort` bukan effort efektif profil itu untuk peran rekaman (pin `reasoning_effort` profil, selain itu
    `[effort].<peran>`). Kasus tepi (semua = ON-PIN, tetap di pool utama seperti basis): `provider`/`effort` null; tak ada
    profil yang cocok; kind tanpa peran (`grid`; biaya 0) kecuali `grid_by_set=True` (gerbang laporan S9: himpunan
    effort efektif profil); effort efektif tak terdefinisi. Beberapa profil cocok -> off-pin hanya bila effort
    berbeda dari SEMUA effort efektifnya. Hanya membaca `config/model` (jalur utama, ter-hash)."""
    provider, model, effort = _rec_field(record, "provider"), _rec_field(record, "model"), _rec_field(record, "effort")
    if provider is None or effort is None:
        return False
    kind = _rec_field(record, "kind")
    role = role_for_kind(kind) if isinstance(kind, str) else None
    if role is None and not grid_by_set:
        return False
    profiles = model_cfg.get("profiles") if isinstance(model_cfg, Mapping) else None
    if not isinstance(profiles, Mapping):
        return False
    quant = _rec_field(record, "quantization")
    effs: set[str] = set()
    matched = False
    for p in profiles.values():
        if not isinstance(p, Mapping) or p.get("sweep") is True:
            continue
        if p.get("provider") == provider and p.get("model") == model and _opt_quant(p) == quant:
            matched = True
            e = _effective_efforts(model_cfg, p, role)
            if e is None:
                return False
            effs |= e
    return matched and effort not in effs


class Ledger:
    """Buku belanja = jumlah `cost ?? projected` semua RunRecord tersimpan (T6, O-3 cabang A).

    Pool (H-102): rekaman off-pin (`is_off_pin`) dikecualikan dari pool default dan pool provider berplafon dan hanya
    dihitung di pool sapuan (`spent_off_pin`). `model_cfg` = isi `config/model` (jalur utama), keyword WAJIB tanpa default:
    pemanggil yang lupa meneruskannya mendapat `TypeError`, bukan pool basis diam-diam."""

    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = Path(runs_dir)

    def spent(self, role: str | None = None, provider: str | None = None) -> int:
        """Total SEMUA rekaman (termasuk off-pin). Hanya untuk tampilan (`/api/health` `ledger_spent_usd_micros`),
        BUKAN untuk keputusan biaya: gunakan `spent_pool`/`spent_off_pin`."""
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

    def spent_pool(self, provider: str, caps: Mapping[str, int], role: str | None = None, *,
                   model_cfg: Mapping[str, Any]) -> int:
        """Belanja pool tempat `provider` berada (H-101 P6). Provider tercantum di `caps` -> belanja provider itu saja
        (semua peran, atau satu peran). Selain itu -> pool default = semua rekaman yang provider-nya TIDAK tercantum
        di `caps` (= total dikurangi semua provider tercantum), dengan filter peran bila diberikan. Rekaman off-pin
        (H-102 P3) tidak dihitung."""
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
                if not is_off_pin(r, model_cfg):
                    total += r.spend_micros()
        return total

    def spent_off_pin(self, *, model_cfg: Mapping[str, Any]) -> int:
        """Belanja pool sapuan (H-102 P3): jumlah `spend_micros()` SEMUA rekaman off-pin, semua provider."""
        try:
            records = store.load_records(self.runs_dir)
        except ValueError as exc:
            raise ConfigInvalid(str(exc)) from None
        return sum(r.spend_micros() for r in records if is_off_pin(r, model_cfg))


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


def evaluate_sweep(role: str, caps: Caps, projected: list[int], spent_sweep: int, cap_micros: int) -> Projection:
    """Pool sapuan (H-102 D2/P3): belanja pool sapuan (`Ledger.spent_off_pin`) vs plafon `[sweep_pool].cap_micros`.
    Cap total, cap peran, dan plafon provider TIDAK berlaku. Batas inklusif (sama persis lolos)."""
    if role not in caps.per_role_micros:
        raise ConfigInvalid(f"config/budget: no per_role_cap_micros entry for role '{role}'")
    total_proj = sum(projected)
    reason = None
    if spent_sweep + total_proj > cap_micros:
        reason = (f"spent {spent_sweep} + projected {total_proj} = {spent_sweep + total_proj} micro-USD "
                  f"exceeds pool sweep cap {cap_micros} micro-USD")
    return Projection(
        per_call_micros=list(projected), total_micros=total_proj,
        effective_total_cap_micros=caps.total_micros, total_cap_source=caps.total_source,
        role=role, role_cap_micros=caps.per_role_micros[role], spent_micros=spent_sweep, spent_role_micros=0,
        verdict="ok" if reason is None else "budget_exceeded", reason=reason,
        pool="sweep", pool_cap_micros=cap_micros, pool_spent_micros=spent_sweep,
    )


def profile_provider(model_cfg: Mapping[str, Any], profile: str | None) -> str:
    """Provider profil (`profile` None = `default_profile`). Tak terselesaikan -> "" (pool default)."""
    name = profile or (model_cfg.get("default_profile") if isinstance(model_cfg, Mapping) else None)
    profiles = model_cfg.get("profiles") if isinstance(model_cfg, Mapping) else None
    p = profiles.get(name) if isinstance(profiles, Mapping) else None
    # Profil tak terselesaikan -> "" (pool default, perilaku lama); SparkClient yang menolak profil tak sah.
    return p["provider"] if isinstance(p, Mapping) and isinstance(p.get("provider"), str) else ""


def pool_limits(ledger: Ledger, caps: Caps, provider: str, role: str, *,
                model_cfg: Mapping[str, Any]) -> tuple[int, int, int, int]:
    """(belanja peran, batas peran, belanja total, batas total) untuk pemeriksaan pra-run CLI/API (H-101 S9 (e)).
    Pool default: belanja atas rekaman provider tak berplafon vs cap peran dan cap total. Provider berplafon: belanja
    provider vs plafon provider (cap peran dan total tidak berlaku). Rekaman off-pin tidak dihitung (H-102 P3);
    `model_cfg` keyword WAJIB."""
    pc = getattr(caps, "provider_micros", None) or {}
    if provider in pc:
        spent = ledger.spent_pool(provider, pc, model_cfg=model_cfg)
        return spent, pc[provider], spent, pc[provider]
    return (ledger.spent_pool(provider, pc, role, model_cfg=model_cfg), caps.per_role_micros[role],
            ledger.spent_pool(provider, pc, model_cfg=model_cfg), caps.total_micros)
