"""Konfigurasi verifier (`config/verifier.toml`): theta eksak (Fraction), D_max bulat, V3-on. Tanpa default tersembunyi."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from backend import config as _config

_DECIMAL = re.compile(r"^[0-9]+(\.[0-9]+)?$")


class VerifierConfigError(ValueError):
    """Konfigurasi verifier hilang atau tidak sah; dilempar sebelum penilaian apa pun."""


@dataclass(frozen=True)
class VerifierConfig:
    theta: Fraction  # 0 < theta <= 1, inklusif
    d_max: int  # >= 0, inklusif
    v3_on: bool = True


def _theta(v: Any) -> Fraction:
    if isinstance(v, bool) or v is None:
        raise VerifierConfigError(f"theta must be a decimal in (0, 1], got {v!r}")
    if isinstance(v, Fraction):
        f = v
    elif isinstance(v, int):
        f = Fraction(v)
    elif isinstance(v, float):
        if not math.isfinite(v):
            raise VerifierConfigError(f"theta must be finite, got {v!r}")
        f = Fraction(repr(v))  # repr terpendek = teks desimal yang ditulis operator (0.9 -> 9/10, bukan float biner)
    elif isinstance(v, str):
        if not _DECIMAL.match(v):
            raise VerifierConfigError(f"theta text must be a plain decimal like '0.95' (dot, no comma), got {v!r}")
        f = Fraction(v)
    else:
        raise VerifierConfigError(f"theta has an unsupported type: {type(v).__name__}")
    if not (0 < f <= 1):
        raise VerifierConfigError(f"theta must satisfy 0 < theta <= 1, got {v!r}")
    return f


def _d_max(v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise VerifierConfigError(f"d_max must be an integer >= 0, got {v!r}")
    if v < 0:
        raise VerifierConfigError(f"d_max must be >= 0, got {v!r}")
    return v


def parse_verifier_config(raw: Mapping[str, Any]) -> VerifierConfig:
    """Validasi dict konfigurasi. Kunci hilang = galat (tidak ada default)."""
    for key in ("theta", "d_max", "v3_on"):
        if key not in raw:
            raise VerifierConfigError(f"verifier config is missing {key!r}")
    v3 = raw["v3_on"]
    if not isinstance(v3, bool):
        raise VerifierConfigError(f"v3_on must be true or false, got {v3!r}")
    return VerifierConfig(theta=_theta(raw["theta"]), d_max=_d_max(raw["d_max"]), v3_on=v3)


def load_verifier_config(config_dir: Path | None = None) -> VerifierConfig:
    try:
        raw = _config.load("verifier", config_dir)
    except _config.ConfigError as exc:
        raise VerifierConfigError(str(exc)) from exc
    return parse_verifier_config(raw)
