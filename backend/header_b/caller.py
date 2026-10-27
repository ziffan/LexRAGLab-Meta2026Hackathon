"""Pemanggil peran B: satu request pemanas, lalu panggilan BERURUTAN per unit dengan `prompt_cache_key` yang sama.

Cache hasil per hash (instruksi, dokumen, potongan, model, effort) ditangani `SparkClient`. `HeaderB` (DATA-CONTRACTS 7)
disimpan di `runs/headers/<granularity>/<prompt_hash[:12]>/<chunk_id>.json`, tidak menimpa berkas yang sudah ada.
Guard biaya klien menganggap seluruh masukan tak ter-cache (konservatif), jadi dipakai `call` per unit, bukan `run_batch`
(proyeksi batch klien akan menolak korpus penuh walau awalan ter-cache); proyeksi sadar-cache ada di `project.py`."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.spark import BudgetExceeded, RunRecord, SparkClient

from .prompt import HEADER_B_SCHEMA, SCHEMA_NAME, PromptB, schema_hash, validate_schema
from .render import WARM_UNIT, DocPrefix, render_input, render_suffix
from .units import Unit

ROLE = "b"
WARM_MAX_OUTPUT = 300


@dataclass
class HeaderOutcome:
    unit: Unit
    run: RunRecord
    headers: list[dict[str, Any]]  # HeaderB per chunk penerima; kosong bila gagal
    error: dict[str, str] | None = None


@dataclass
class HeaderRun:
    outcomes: list[HeaderOutcome] = field(default_factory=list)
    warm: RunRecord | None = None
    stopped_reason: str | None = None  # None | budget_exceeded | too_many_errors | warm_failed


def make_validator(unit: Unit, tokenizer: Any, max_header_tokens: int) -> Callable[[dict], str | None]:
    def check(out: dict) -> str | None:
        if out.get("chunk_id") != unit.key:
            return "chunk_id does not match the requested chunk"
        h = out.get("header")
        if not isinstance(h, str) or not h.strip():
            return "header is empty"
        if tokenizer.count(h.strip()) > max_header_tokens:
            return f"header exceeds {max_header_tokens} tokens"
        return None
    return check


def make_call(prompt: PromptB, prefix: DocPrefix, unit: Unit, tokenizer: Any, *, max_header_tokens: int,
              max_output_tokens: int, meta: dict[str, Any]) -> dict[str, Any]:
    validate_schema()
    warm = unit is WARM_UNIT
    est = prefix.tokens + tokenizer.count(render_suffix(prefix, unit))
    if warm:
        def validator(out: dict) -> str | None:
            return None if out.get("chunk_id") == unit.key else "chunk_id does not match"
    else:
        validator = make_validator(unit, tokenizer, max_header_tokens)
    return dict(role=ROLE, prompt_version=prompt.version, prompt_hash=prompt.prompt_hash, input=render_input(prefix, unit),
                schema=HEADER_B_SCHEMA, schema_name=SCHEMA_NAME, schema_hash=schema_hash(),
                prompt_cache_key=prefix.cache_key, max_output_tokens=WARM_MAX_OUTPUT if warm else max_output_tokens,
                est_input=est, validator=validator, meta=dict(meta))


def store_dir(headers_dir: Path, granularity: str, prompt: PromptB) -> Path:
    return Path(headers_dir) / granularity / prompt.prompt_hash[:12]


def load_header(headers_dir: Path, granularity: str, prompt: PromptB, chunk_id: str) -> dict[str, Any] | None:
    try:
        return json.loads((store_dir(headers_dir, granularity, prompt) / f"{chunk_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(path: Path, rec: dict[str, Any]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def run_headers(client: SparkClient, prompt: PromptB, prefix: DocPrefix, units: list[Unit], *, granularity: str,
                tokenizer: Any, headers_dir: Path, max_header_tokens: int, max_output_tokens: int,
                max_consecutive_errors: int, meta: dict[str, Any], warm: bool = True) -> HeaderRun:
    run = HeaderRun()
    if warm and units:
        w = client.call(**make_call(prompt, prefix, WARM_UNIT, tokenizer, max_header_tokens=max_header_tokens,
                                    max_output_tokens=max_output_tokens, meta=meta))
        run.warm = w.record
        if w.output is None:
            run.stopped_reason = "warm_failed"
            return run
    consecutive = 0
    for u in units:
        try:
            res = client.call(**make_call(prompt, prefix, u, tokenizer, max_header_tokens=max_header_tokens,
                                          max_output_tokens=max_output_tokens, meta=meta))
        except BudgetExceeded:
            run.stopped_reason = "budget_exceeded"
            return run
        if res.output is None:
            err = res.record.error or {"code": "model_error", "message": "call failed"}
            run.outcomes.append(HeaderOutcome(u, res.record, [], dict(err)))
            consecutive += 1
            if consecutive >= max_consecutive_errors:
                run.stopped_reason = "too_many_errors"
                return run
            continue
        consecutive = 0
        header = res.parsed["header"].strip()
        n = tokenizer.count(header)
        recs = [{"chunk_id": cid, "header": header, "granularity": granularity, "prompt_version": prompt.version,
                 "tokens_local": n, "run_id": res.record.run_id} for cid in u.chunk_ids]
        d = store_dir(headers_dir, granularity, prompt)
        for r in recs:
            _save(d / f"{r['chunk_id']}.json", r)
        run.outcomes.append(HeaderOutcome(u, res.record, recs))
    return run
