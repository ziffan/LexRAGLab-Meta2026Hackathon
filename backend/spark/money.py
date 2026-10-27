"""Hitung biaya integer micro-USD (O-1) dan format tampilan (S39). Tanpa float."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import UsageInvalid

MTOK = 1_000_000


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_pricing(pricing: Mapping[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k in ("input", "cached", "output"):
        v = pricing.get(k) if isinstance(pricing, Mapping) else None
        if not _is_int(v) or v < 0:
            raise ValueError(f"pricing.{k} must be a non-negative integer (micro-USD per 1M tokens)")
        out[k] = v
    return out


def validate_usage(usage: Mapping[str, Any]) -> dict[str, int]:
    """`usage` = {input, cached, output}; semua int >= 0 dan cached <= input."""
    if not isinstance(usage, Mapping):
        raise UsageInvalid("usage is missing or not an object")
    out: dict[str, int] = {}
    for k in ("input", "cached", "output"):
        v = usage.get(k)
        if not _is_int(v) or v < 0:
            raise UsageInvalid(f"usage.{k} is missing, negative, or not an integer")
        out[k] = v
    if out["cached"] > out["input"]:
        raise UsageInvalid("usage.cached exceeds usage.input")
    return out


def compute_cost_micros(usage: Mapping[str, Any], pricing: Mapping[str, Any]) -> int:
    """ceil((uncached*in + cached*cached + output*out) / 1e6), integer murni, per panggilan (O-1)."""
    u = validate_usage(usage)
    p = validate_pricing(pricing)
    numerator = (u["input"] - u["cached"]) * p["input"] + u["cached"] * p["cached"] + u["output"] * p["output"]
    return -((-numerator) // MTOK)


def format_usd_micros(micros: int) -> str:
    """`$d.dddddd` dari integer micro-USD."""
    if not _is_int(micros):
        raise TypeError("micro-USD must be an int")
    if micros < 0:
        raise ValueError("micro-USD must not be negative")
    return f"${micros // MTOK}.{micros % MTOK:06d}"
