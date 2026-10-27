"""Perakitan M3.1 yang dipakai CLI dan API: konfigurasi, awalan dokumen, unit, proyeksi, run."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from backend import config
from backend.corpus import load_corpus
from backend.spark.settings import load_configs

from .project import project_units
from .prompt import PromptB, load_prompt
from .render import DocPrefix, build_prefix
from .units import SOURCES, Unit, build_units

DEFAULT_DOC = "uupt-40-2007"
KEYS = ("max_header_tokens", "max_output_tokens", "warm_max_output_tokens", "expected_output_tokens", "assumed_latency_ms", "max_consecutive_errors")


class HeaderConfigError(ValueError):
    pass


def load_header_cfg(config_dir: Path | None = None) -> dict[str, Any]:
    c = config.load("header_b", config_dir)
    for k in KEYS:
        v = c.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise HeaderConfigError(f"config/header_b: {k} must be a positive integer")
    for k in ("cache_guard_calls",):
        v = c.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise HeaderConfigError(f"config/header_b: {k} must be a positive integer")
    try:
        c["cache_guard_min_ratio"] = Fraction(str(c.get("cache_guard_min_ratio")))
    except (ValueError, ZeroDivisionError):
        raise HeaderConfigError("config/header_b: cache_guard_min_ratio must be a fraction string such as '4/5'") from None
    if not 0 <= c["cache_guard_min_ratio"] <= 1:
        raise HeaderConfigError("config/header_b: cache_guard_min_ratio must be between 0 and 1")
    if c.get("granularity") not in ("pasal", "ayat"):
        raise HeaderConfigError("config/header_b: granularity must be 'pasal' or 'ayat'")
    return c


@dataclass
class Prepared:
    doc: Any
    prompt: PromptB
    prefix: DocPrefix
    units: list[Unit]
    source: str


def prepare(source: str, *, doc: Any = None, tokenizer: Any, header_cfg: dict[str, Any], retrieval_cfg: dict[str, Any],
            grid_cfg: dict[str, Any], config_dir: Path | None = None, doc_id: str = DEFAULT_DOC,
            prompt: PromptB | None = None) -> Prepared:
    if source not in SOURCES:
        raise HeaderConfigError(f"source must be one of {list(SOURCES)}")
    doc = doc or load_corpus(doc_id, config_dir=config_dir)
    prompt = prompt or load_prompt(header_cfg["max_header_tokens"])
    prefix = build_prefix(prompt, doc, tokenizer)
    units = build_units(doc, source, tokenizer=tokenizer, retrieval_cfg=retrieval_cfg, grid_cfg=grid_cfg)
    return Prepared(doc, prompt, prefix, units, source)


def project(p: Prepared, tokenizer: Any, header_cfg: dict[str, Any], model_cfg: dict[str, Any], *, profile: str | None = None,
            rpm: int | None = None, limit: int | None = None) -> dict[str, Any]:
    profile = profile or model_cfg["default_profile"]
    prof = model_cfg["profiles"][profile]
    raw = model_cfg["pricing"][prof.get("pricing", profile)]
    pricing = {k: raw[f"{k}_per_mtok_micros"] for k in ("input", "cached", "output")}
    units = p.units if limit is None else p.units[:limit]
    out = project_units(units, p.prefix, tokenizer, pricing, rpm=rpm or model_cfg["limits"]["max_rpm"],
                        expected_output_tokens=header_cfg["expected_output_tokens"],
                        max_output_tokens=header_cfg["max_output_tokens"],
                        warm_max_output_tokens=header_cfg["warm_max_output_tokens"],
                        assumed_latency_ms=header_cfg["assumed_latency_ms"])
    out.update({"source": p.source, "doc_id": p.doc.doc_id, "profile": profile, "prompt_version": p.prompt.version,
                "prompt_hash": p.prompt.prompt_hash, "clean_sha256": p.doc.clean_sha256})
    return out


def load_all_configs(config_dir: Path | None = None) -> tuple[dict, dict, dict, dict, dict]:
    hc = load_header_cfg(config_dir)
    model_cfg, budget_cfg = load_configs(config_dir)
    return hc, model_cfg, budget_cfg, config.load("retrieval", config_dir), config.load("grid", config_dir)
