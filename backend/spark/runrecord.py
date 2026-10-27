"""RunRecord (docs/DATA-CONTRACTS.md §12). Waktu UTC ISO 8601, uang integer micro-USD."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from typing import Any

KINDS = ("spark_a", "spark_b", "spark_c", "spark_d", "grid", "measure")
STATUSES = ("ok", "error", "cached", "replay")


def utc_iso(epoch_s: float) -> str:
    return datetime.fromtimestamp(epoch_s, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def kind_for_role(role: str) -> str:
    return "measure" if role == "measure" else f"spark_{role}"


def role_for_kind(kind: str) -> str | None:
    if kind == "measure":
        return "measure"
    if isinstance(kind, str) and kind.startswith("spark_"):
        return kind[len("spark_"):]
    return None


@dataclass
class RunRecord:
    run_id: str
    kind: str
    created_at: str
    cache_key: str
    corpus_hash: str | None
    config_hash: str | None
    clean_sha256: str | None
    loader_rules_version: str | None
    prompt_version: str | None
    prompt_hash: str | None
    model: str | None
    effort: str | None
    tokenizer: dict[str, Any] | None
    embedder: dict[str, Any] | None
    packing: str | None
    usage_input_tokens: int | None
    usage_cached_tokens: int | None
    usage_output_tokens: int | None
    cost_usd_micros: int | None
    projected_cost_usd_micros: int | None
    latency_ms: int
    host: str
    device: str
    provider: str | None
    quantization: str | None
    status: str
    error: dict[str, str] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunRecord:
        names = [f.name for f in fields(cls)]
        if not isinstance(d, dict) or any(n not in d for n in names):
            raise ValueError("run record has missing fields")
        return cls(**{n: d[n] for n in names})

    def spend_micros(self) -> int:
        """Belanja untuk buku: `(cost ?? 0) + (projected ?? 0)` (O-3 cabang A; H-071: cost murni usage,
        projected pada record ok = proyeksi upaya timeout yang mendahului)."""
        return (self.cost_usd_micros or 0) + (self.projected_cost_usd_micros or 0)

    def role(self) -> str | None:
        return role_for_kind(self.kind)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
