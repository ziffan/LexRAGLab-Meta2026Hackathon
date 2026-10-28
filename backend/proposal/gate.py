"""Proyeksi dan gerbang biaya batch D `unanswerable` (H-092 P10, G-36). Fungsi murni, integer micro-USD, tanpa float.

`batas_atas = ceil(expected * factor_bp / 10000)`. Gerbang menolak bila `batas_atas > batch_cap_micros` ATAU
`kumulatif_terpakai + batas_atas > cumulative_cap_micros * cumulative_pct / 100` (batas inklusif: sama persis lolos).
Gerbang ini terpisah dari cap peran `d` di penjaga klien (M0.1), yang tetap berlaku."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from backend.spark.errors import ConfigInvalid
from backend.spark.money import compute_cost_micros


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


@dataclass(frozen=True)
class GateConfig:
    factor_bp: int
    batch_cap_micros: int
    cumulative_cap_micros: int
    cumulative_pct: int

    @property
    def cumulative_threshold_micros(self) -> int:
        return self.cumulative_cap_micros * self.cumulative_pct // 100


def load_gate_config(budget_cfg: Mapping[str, Any]) -> GateConfig:
    """`config/budget` tabel `[batch_gate]`. Nilai bukan integer atau <= 0 (persen di luar 1..100) -> `ConfigInvalid`."""
    t = budget_cfg.get("batch_gate") if isinstance(budget_cfg, Mapping) else None
    if not isinstance(t, Mapping):
        raise ConfigInvalid("config/budget: table [batch_gate] is missing")
    vals = {}
    for key in ("factor_bp", "batch_cap_micros", "cumulative_cap_micros", "cumulative_pct"):
        v = t.get(key)
        if not _is_int(v) or v <= 0:
            raise ConfigInvalid(f"config/budget [batch_gate]: {key} must be an integer > 0")
        vals[key] = v
    if vals["cumulative_pct"] > 100:
        raise ConfigInvalid("config/budget [batch_gate]: cumulative_pct must be between 1 and 100")
    return GateConfig(**vals)


def upper_bound(expected: int, factor_bp: int) -> int:
    """`ceil(expected * factor_bp / 10000)` dengan aritmetika integer."""
    if not _is_int(expected) or expected < 0:
        raise ValueError("expected must be a non-negative integer (micro-USD)")
    if not _is_int(factor_bp) or factor_bp <= 0:
        raise ConfigInvalid("factor_bp must be an integer > 0")
    return -(-expected * factor_bp // 10000)


@dataclass(frozen=True)
class GateVerdict:
    expected: int
    batas_atas: int
    spent: int
    ok: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"expected": self.expected, "batas_atas": self.batas_atas, "spent": self.spent, "ok": self.ok,
                "reasons": list(self.reasons)}


def cumulative_threshold_for(provider: str, budget_cfg: Mapping[str, Any], caps: Mapping[str, int]) -> int:
    """Ambang kumulatif gerbang per pool (H-101 P9). Provider tercantum di `caps` (`[provider_cap_micros]`) ->
    `caps[provider] * cumulative_pct // 100`; selain itu (pool default) -> `cumulative_cap_micros * cumulative_pct // 100`."""
    gcfg = load_gate_config(budget_cfg)
    if provider in caps:
        return caps[provider] * gcfg.cumulative_pct // 100
    return gcfg.cumulative_threshold_micros


def evaluate_gate(expected_per_call: Sequence[int], spent: int, cfg: GateConfig, *, upper_floor: int = 0,
                  threshold_micros: int | None = None) -> GateVerdict:
    """Putusan gerbang atas `expected` = jumlah ekspektasi per panggilan (satu per akta).

    `batas_atas = max(ceil(expected * factor_bp / 10000), upper_floor)` (H-101 P7; `upper_floor=0` = perilaku lama persis).
    Ambang kumulatif = `threshold_micros` bila diberikan (ambang per pool, P9), selain itu `cfg.cumulative_threshold_micros`."""
    if not _is_int(spent) or spent < 0:
        raise ValueError("spent must be a non-negative integer (micro-USD)")
    if not _is_int(upper_floor) or upper_floor < 0:
        raise ValueError("upper_floor must be a non-negative integer (micro-USD)")
    if threshold_micros is not None and (not _is_int(threshold_micros) or threshold_micros < 0):
        raise ValueError("threshold_micros must be a non-negative integer (micro-USD)")
    threshold = cfg.cumulative_threshold_micros if threshold_micros is None else threshold_micros
    expected = sum(expected_per_call)
    upper = max(upper_bound(expected, cfg.factor_bp), upper_floor)
    reasons = []
    if upper > cfg.batch_cap_micros:
        reasons.append("batas_atas_over_batch_cap")
    if spent + upper > threshold:
        reasons.append("cumulative_over_threshold")
    return GateVerdict(expected, upper, spent, not reasons, tuple(reasons))


def expected_cost_micros(input_tokens: int, output_tokens: int, pricing: Mapping[str, Any]) -> int:
    """Biaya ekspektasi satu panggilan tanpa cache (satu panggilan per akta, tanpa pemanas)."""
    return compute_cost_micros({"input": input_tokens, "cached": 0, "output": output_tokens}, pricing)
