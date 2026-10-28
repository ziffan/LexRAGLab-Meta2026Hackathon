"""Pemanggil peran B: satu request pemanas, lalu panggilan BERURUTAN per unit dengan `prompt_cache_key` yang sama.

Cache hasil per hash (instruksi, dokumen, potongan, model, effort) ditangani `SparkClient`. `HeaderB` (DATA-CONTRACTS 7)
disimpan di `runs/headers/<granularity>/<prompt_hash[:12]>/<chunk_id>.json`, tidak menimpa berkas yang sudah ada.
Keluaran yang lolos skema tetapi gagal validasi semantik (H-079) disimpan terpisah di
`.../<prompt_hash[:12]>/rejected/<chunk_id>.<n>.json` (diagnosis; bukan cache sukses, tidak dibaca store header).
Guard biaya klien menganggap seluruh masukan tak ter-cache (konservatif), jadi dipakai `call` per unit, bukan `run_batch`
(proyeksi batch klien akan menolak korpus penuh walau awalan ter-cache); proyeksi sadar-cache ada di `project.py`."""

from __future__ import annotations

import json
import os
from fractions import Fraction
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.spark import BudgetExceeded, RunRecord, SparkClient

from .prompt import SCHEMA_NAME, PromptB, header_schema, schema_hash, validate_schema
from .render import WARM_UNIT, DocPrefix, render_input, render_suffix
from .units import Unit

ROLE = "b"


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
    stopped_reason: str | None = None  # None | budget_exceeded | too_many_errors | warm_failed | cache_ratio_low


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
              max_output_tokens: int, warm_max_output_tokens: int, meta: dict[str, Any],
              max_length_chars: int | None = None) -> dict[str, Any]:
    validate_schema(max_length_chars)
    warm = unit is WARM_UNIT or (unit.key == WARM_UNIT.key and not unit.chunk_ids)  # pemanas (juga varian ber-nonce H-101)
    est = prefix.tokens + tokenizer.count(render_suffix(prefix, unit))
    if warm:
        def validator(out: dict) -> str | None:
            return None if out.get("chunk_id") == unit.key else "chunk_id does not match"
    else:
        validator = make_validator(unit, tokenizer, max_header_tokens)
    return dict(role=ROLE, prompt_version=prompt.version, prompt_hash=prompt.prompt_hash, input=render_input(prefix, unit),
                schema=header_schema(max_length_chars), schema_name=SCHEMA_NAME, schema_hash=schema_hash(max_length_chars),
                prompt_cache_key=prefix.cache_key, max_output_tokens=warm_max_output_tokens if warm else max_output_tokens,
                est_input=est, validator=validator, meta=dict(meta))


def store_dir(headers_dir: Path, granularity: str, prompt: PromptB) -> Path:
    return Path(headers_dir) / granularity / prompt.prompt_hash[:12]


def load_header(headers_dir: Path, granularity: str, prompt: PromptB, chunk_id: str) -> dict[str, Any] | None:
    try:
        return json.loads((store_dir(headers_dir, granularity, prompt) / f"{chunk_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rejected_dir(headers_dir: Path, granularity: str, prompt: PromptB) -> Path:
    return store_dir(headers_dir, granularity, prompt) / "rejected"


def _save_rejected(headers_dir: Path, granularity: str, prompt: PromptB, unit: Unit, res: Any, tokenizer: Any) -> None:
    """Simpan teks keluaran yang gagal validasi semantik; `<chunk_id>.<n>.json`, n = upaya berikutnya (mulai 1)."""
    try:
        out = json.loads(res.rejected_output)
    except (TypeError, ValueError):
        return
    text = out.get("header") if isinstance(out, dict) else None
    text = text if isinstance(text, str) else ""
    err = res.record.error or {}
    rec = {"chunk_id": unit.key, "chunk_id_returned": out.get("chunk_id") if isinstance(out, dict) else None,
           "granularity": granularity, "prompt_version": prompt.version, "text": text,
           "tokens_local": tokenizer.count(text.strip()), "error_code": err.get("code"),
           "error_message": err.get("message"), "run_id": res.record.run_id}
    d = rejected_dir(headers_dir, granularity, prompt)
    d.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(rec, sort_keys=True, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    n = 1
    while True:
        try:
            with open(d / f"{unit.key}.{n}.json", "xb") as f:  # eksklusif: tidak menimpa upaya sebelumnya
                f.write(body)
            return
        except FileExistsError:
            n += 1


def _save(path: Path, rec: dict[str, Any]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def run_headers(client: SparkClient, prompt: PromptB, prefix: DocPrefix, units: list[Unit], *, granularity: str,
                tokenizer: Any, headers_dir: Path, max_header_tokens: int, max_output_tokens: int,
                max_consecutive_errors: int, warm_max_output_tokens: int, meta: dict[str, Any], warm: bool = True,
                cache_guard_calls: int | None = None, cache_guard_min_ratio: Fraction | None = None,
                max_length_chars: int | None = None, save_headers: bool = True, warm_unit: Unit | None = None,
                count_semantic_errors: bool = True) -> HeaderRun:
    """Guard cache (H-074): setelah `cache_guard_calls` panggilan berbayar (bukan cache hit lokal, tanpa pemanas) rasio
    agregat cached/input < `cache_guard_min_ratio` (inklusif: sama dengan batas lanjut) -> berhenti `cache_ratio_low`."""
    run = HeaderRun()
    paid = in_tok = cached_tok = 0
    if warm and units:
        w = client.call(**make_call(prompt, prefix, warm_unit or WARM_UNIT, tokenizer, max_header_tokens=max_header_tokens,
                                    max_output_tokens=max_output_tokens,
                                    warm_max_output_tokens=warm_max_output_tokens, meta=meta,
                                    max_length_chars=max_length_chars))
        run.warm = w.record
        if w.output is None:
            run.stopped_reason = "warm_failed"
            return run
    consecutive = 0
    for u in units:
        try:
            res = client.call(**make_call(prompt, prefix, u, tokenizer, max_header_tokens=max_header_tokens,
                                          max_output_tokens=max_output_tokens,
                                          warm_max_output_tokens=warm_max_output_tokens, meta=meta,
                                          max_length_chars=max_length_chars))
        except BudgetExceeded:
            run.stopped_reason = "budget_exceeded"
            return run
        r = res.record
        guard_stop = False
        if cache_guard_calls and r.status == "ok" and r.usage_input_tokens is not None and paid < cache_guard_calls:
            paid += 1
            in_tok += r.usage_input_tokens
            cached_tok += r.usage_cached_tokens or 0
            guard_stop = (paid == cache_guard_calls and cache_guard_min_ratio is not None
                          and Fraction(cached_tok, max(in_tok, 1)) < cache_guard_min_ratio)
        if res.output is None:
            if res.rejected_output is not None:
                _save_rejected(headers_dir, granularity, prompt, u, res, tokenizer)
            err = res.record.error or {"code": "model_error", "message": "call failed"}
            run.outcomes.append(HeaderOutcome(u, res.record, [], dict(err)))
            # H-101 (putusan 13): jalur pembanding boleh tidak menghitung `semantic_invalid` (keluaran sah transport yang ditolak
            # validator 40 token/maxLength); galat teknis tetap dihitung. Bawaan True = perilaku lama.
            if count_semantic_errors or err.get("code") != "semantic_invalid":
                consecutive += 1
            if consecutive >= max_consecutive_errors:
                run.stopped_reason = "too_many_errors"
                return run
            if guard_stop:
                run.stopped_reason = "cache_ratio_low"
                return run
            continue
        consecutive = 0
        header = res.parsed["header"].strip()
        n = tokenizer.count(header)
        recs = [{"chunk_id": cid, "header": header, "granularity": granularity, "prompt_version": prompt.version,
                 "tokens_local": n, "run_id": res.record.run_id} for cid in u.chunk_ids]
        d = store_dir(headers_dir, granularity, prompt)
        for r in recs if save_headers else ():
            _save(d / f"{r['chunk_id']}.json", r)
        run.outcomes.append(HeaderOutcome(u, res.record, recs))
        if guard_stop:
            run.stopped_reason = "cache_ratio_low"
            return run
    return run
