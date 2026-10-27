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


def effective_caps(budget_cfg: Mapping[str, Any], env: Mapping[str, str] | None) -> Caps:
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
    return Caps(total_micros=cap, total_source=source, per_role_micros=per_role)


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


def evaluate(role: str, caps: Caps, projected: list[int], spent_total: int, spent_role: int) -> Projection:
    if role not in caps.per_role_micros:
        raise ConfigInvalid(f"config/budget: no per_role_cap_micros entry for role '{role}'")
    role_cap = caps.per_role_micros[role]
    total_proj = sum(projected)
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
    )
