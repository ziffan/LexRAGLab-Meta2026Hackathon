"""Proyeksi biaya dan waktu B untuk seluruh korpus (M3.1). Fungsi murni, integer micro-USD, tanpa jaringan.

Tiga skenario per sumber potongan, semuanya per panggilan dengan `compute_cost_micros` (pembulatan ke atas):
- `expected`: awalan ter-cache setelah request pemanas, output = `expected_output_tokens`.
- `upper_cached`: awalan ter-cache, output = `max_output_tokens`.
- `upper_no_cache`: tak ada cache sama sekali, output = `max_output_tokens`.
Waktu: panggilan berurutan, tiap panggilan butuh paling sedikit max(60/RPM, latensi asumsi)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from backend.spark import compute_cost_micros

from .render import WARM_UNIT, DocPrefix, render_suffix
from .units import Unit


def _seconds(calls: int, rpm: int, latency_ms: int) -> dict[str, int]:
    floor_ms = -(-calls * 60_000 // rpm)
    seq_ms = calls * latency_ms
    return {"rpm_floor_seconds": -(-floor_ms // 1000), "sequential_seconds": -(-seq_ms // 1000),
            "estimated_seconds": -(-max(floor_ms, seq_ms) // 1000)}


def project_units(units: list[Unit], prefix: DocPrefix, tokenizer: Any, pricing: Mapping[str, Any], *, rpm: int,
                  expected_output_tokens: int, max_output_tokens: int, warm_max_output_tokens: int, assumed_latency_ms: int) -> dict[str, Any]:
    """Proyeksi untuk `units` ditambah satu request pemanas."""
    suffixes = [tokenizer.count(render_suffix(prefix, u)) for u in units]
    warm_suffix = tokenizer.count(render_suffix(prefix, WARM_UNIT))
    p = prefix.tokens

    def total(cached: bool, out: int) -> int:
        warm = compute_cost_micros({"input": p + warm_suffix, "cached": 0, "output": min(out, warm_max_output_tokens)}, pricing)
        body = sum(compute_cost_micros({"input": p + s, "cached": p if cached else 0, "output": out}, pricing)
                   for s in suffixes)
        return warm + body

    calls = len(units) + 1
    return {
        "units": len(units), "calls": calls, "prefix_tokens": p, "suffix_tokens_total": sum(suffixes),
        "source_tokens_total": sum(u.tokens for u in units),
        "cost_usd_micros": {"expected": total(True, expected_output_tokens),
                            "upper_cached": total(True, max_output_tokens),
                            "upper_no_cache": total(False, max_output_tokens)},
        "time": _seconds(calls, rpm, assumed_latency_ms), "rpm": rpm, "assumed_latency_ms": assumed_latency_ms,
        "assumptions": {"expected_output_tokens": expected_output_tokens, "max_output_tokens": max_output_tokens,
                        "prefix_fully_cached_after_warmup": True},
    }


def write_projection(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)
