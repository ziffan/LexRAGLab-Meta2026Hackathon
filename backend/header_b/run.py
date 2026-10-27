"""Perakitan M3.1 yang dipakai CLI dan API: konfigurasi, awalan dokumen, unit, proyeksi, run."""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from typing import Any

from backend import config
from backend.corpus import load_corpus
from backend.spark.settings import load_configs

from .caller import run_headers
from .project import project_units
from .prompt import PromptB, load_prompt
from .render import DocPrefix, build_prefix
from .units import ALL_SOURCES, Unit, build_units

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
    pv = c.get("prompt_version")
    if pv is not None and (not isinstance(pv, str) or not pv):
        raise HeaderConfigError("config/header_b: prompt_version must be a non-empty string")
    ml = c.get("schema_max_length_chars")
    if ml is not None and (not isinstance(ml, int) or isinstance(ml, bool) or ml < 1):
        raise HeaderConfigError("config/header_b: schema_max_length_chars must be a positive integer or omitted")
    c["schema_max_length_chars"] = ml
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
            prompt: PromptB | None = None, schema_record: Any = None) -> Prepared:
    if source not in ALL_SOURCES:
        raise HeaderConfigError(f"source must be one of {list(ALL_SOURCES)}")
    if source == "structure_schema" and schema_record is None:
        raise HeaderConfigError("source structure_schema needs an active schema A record (runs/schemas/<family>)")
    doc = doc or load_corpus(doc_id, config_dir=config_dir)
    prompt = prompt or load_prompt(header_cfg["max_header_tokens"], header_cfg.get("prompt_version"))
    prefix = build_prefix(prompt, doc, tokenizer)
    units = build_units(doc, source, tokenizer=tokenizer, retrieval_cfg=retrieval_cfg, grid_cfg=grid_cfg,
                        schema_record=schema_record)
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


def find_unit(p: Prepared, ref: str) -> Unit:
    """Unit dengan `chunk_id` (key) atau alamat yang sama persis dengan `ref`; ambigu atau tak ada -> HeaderConfigError."""
    hits = [u for u in p.units if u.key == ref or u.address == ref]
    if not hits:
        raise HeaderConfigError(f"no unit with chunk_id or address {ref!r} in source {p.source!r}")
    if len(hits) > 1:
        raise HeaderConfigError(f"{ref!r} matches {len(hits)} units in source {p.source!r}; use the chunk_id")
    return hits[0]


def smoke_status(outcome: Any | None, stopped: str | None) -> tuple[str, str | None]:
    """(`accepted` | `rejected_by_api` | `inconclusive`, kode galat). `accepted` = API menerima request (termasuk bila keluaran
    kemudian ditolak validasi semantik lokal: itu masuk `rejected/`). `rejected_by_api` = HTTP 4xx dari API (mis. skema)."""
    if outcome is None:
        return "inconclusive", stopped
    if outcome.error is None:
        return "accepted", None
    code = outcome.error.get("code")
    if code == "semantic_invalid":
        return "accepted", code
    if code == "invalid_request" and str(outcome.error.get("message", "")).startswith("HTTP 4"):
        return "rejected_by_api", code
    return "inconclusive", code


def smoke_projection(p: Prepared, unit: Unit, tokenizer: Any, header_cfg: dict[str, Any], model_cfg: dict[str, Any], *,
                     profile: str | None = None, rpm: int | None = None) -> dict[str, Any]:
    """Proyeksi satu panggilan. Biaya memuat satu request pemanas yang TIDAK dikirim smoke (batas atas konservatif)."""
    return project(replace(p, units=[unit]), tokenizer, header_cfg, model_cfg, profile=profile, rpm=rpm)


def run_smoke(client: Any, p: Prepared, unit: Unit, *, tokenizer: Any, header_cfg: dict[str, Any], headers_dir: Path,
              meta: dict[str, Any]) -> dict[str, Any]:
    """Tepat satu panggilan untuk `unit`, tanpa pemanas. Header sukses TIDAK disimpan ke store header (smoke = diagnosis;
    hasilnya tetap ada di cache klien dan RunRecord). Keluaran yang ditolak validasi semantik disimpan di `rejected/`."""
    res = run_headers(client, p.prompt, p.prefix, [unit], granularity=p.source, tokenizer=tokenizer, headers_dir=headers_dir,
                      max_header_tokens=header_cfg["max_header_tokens"], max_output_tokens=header_cfg["max_output_tokens"],
                      max_consecutive_errors=header_cfg["max_consecutive_errors"],
                      warm_max_output_tokens=header_cfg["warm_max_output_tokens"], meta=meta, warm=False,
                      max_length_chars=header_cfg.get("schema_max_length_chars"), save_headers=False)
    o = res.outcomes[0] if res.outcomes else None
    status, code = smoke_status(o, res.stopped_reason)
    return {"status": status, "error_code": code, "unit": unit.key, "address": unit.address,
            "run_id": o.run.run_id if o else None,
            "header": o.headers[0]["header"] if o and o.headers else None, "stopped": res.stopped_reason}
