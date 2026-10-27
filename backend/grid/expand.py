"""Ekspansi `config/grid` menjadi daftar Setting (docs/DATA-CONTRACTS.md §10, H-012, S21)."""

from __future__ import annotations

from typing import Any, Mapping

from backend.grid.types import Setting, compute_setting_id


def _as_list(v: Any) -> list:
    if v is None:
        return [None]
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _budgets(cfg: Mapping[str, Any]) -> list[int]:
    b = cfg["budget"]
    out: list[int] = []
    for v in [b["default_tokens"], *_as_list(b.get("comparison_tokens", []) or [])]:
        if v is not None and v not in out:
            out.append(v)
    return out


def _chunker_variants(cfg: Mapping[str, Any]) -> list[tuple[str, int | None, int | None, int | None]]:
    out = []
    for name in cfg["chunkers"]:
        if name == "fixed_size":
            fs = cfg["fixed_size"]
            for size in _as_list(fs["chunk_size_tokens"]):
                for ov in _as_list(fs["overlap_tokens"]):
                    out.append((name, size, ov, None))
        elif name == "structure_schema":
            for sv in _as_list(cfg.get("structure_schema", {}).get("schema_version")):
                out.append((name, None, None, sv))
        elif name == "structure_handwritten":
            out.append((name, None, None, None))
        else:
            raise ValueError(f"unknown chunker: {name!r}")
    return out


def expand_grid(cfg: Mapping[str, Any], family: str) -> list[Setting]:
    """Produk Cartesian penuh varian chunker x mode retrieval x header B x anggaran (A15).
    Sumbu tak relevan (ukuran/overlap untuk struktur) bernilai null, bukan dikalikan."""
    settings = []
    for chunker, size, ov, sv in _chunker_variants(cfg):
        for mode in cfg["retrieval_modes"]:
            for hb in cfg["header_b"]:
                for budget in _budgets(cfg):
                    content = {
                        "family": family,
                        "chunker": chunker,
                        "chunk_size_tokens": size,
                        "overlap_tokens": ov,
                        "schema_version": sv,
                        "retrieval_mode": mode,
                        "header_b": bool(hb),
                        "budget_tokens": budget,
                    }
                    settings.append(Setting(setting_id=compute_setting_id(content), **content))
    return settings
