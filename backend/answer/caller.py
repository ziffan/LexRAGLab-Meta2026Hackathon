"""Pemanggil peran C: proyeksi biaya dulu, panggilan berurutan lewat `SparkClient` (cache per hash klien M0.1),
`AnswerRecord` (DATA-CONTRACTS 8) disimpan per hash di `runs/answers/`.

`tolak` dan `bukti_tidak_cukup` adalah keluaran sah. Galat provider (record `status=error`) tidak menghasilkan
AnswerRecord; pemanggil menerima `AnswerOutcome.error`. Hanya Responses API + strict, tanpa tool calling (H-016)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from backend.spark import BatchResult, Projection, RunRecord, SparkClient
from backend.spark.store import canonical_json, sha256_hex

from .context import ContextBundle
from .prompt import ANSWER_C_SCHEMA, SCHEMA_NAME, PromptC, schema_hash, validate_schema

ROLE = "c"
SLOTS = ("best", "baseline")


@dataclass
class AnswerOutcome:
    slot: str
    run: RunRecord
    answer: dict[str, Any] | None  # AnswerRecord; None bila panggilan galat atau tidak dijalankan
    error: dict[str, str] | None = None


def make_call(prompt: PromptC, bundle: ContextBundle, meta: Mapping[str, Any]) -> dict[str, Any]:
    """Argumen `SparkClient.call` untuk satu kolom. Instruksi, skema, dan batas keluaran identik antar kolom."""
    validate_schema()
    return dict(role=ROLE, prompt_version=prompt.version, prompt_hash=prompt.prompt_hash, input=bundle.input_text,
                schema=ANSWER_C_SCHEMA, schema_name=SCHEMA_NAME, schema_hash=schema_hash(),
                prompt_cache_key=prompt.prompt_cache_key, max_output_tokens=prompt.max_output_tokens,
                est_input=bundle.est_input, meta=dict(meta))


def project(client: SparkClient, prompt: PromptC, bundles: list[ContextBundle], meta: Mapping[str, Any]) -> Projection:
    """Proyeksi biaya batch tanpa jaringan. Panggilan yang sudah ada di cache diproyeksikan 0."""
    return client.project_batch([make_call(prompt, b, meta) for b in bundles])


def flags_for(out: Mapping[str, Any]) -> list[str]:
    """Penanda semantik (SPARK-ROLES 4): ditandai, bukan ditolak. Penilaian kutipan = verifier (M2.3)."""
    f: list[str] = []
    if out.get("status") == "jawab":
        if not out.get("kutipan"):
            f.append("jawab_tanpa_kutipan")
        if not (out.get("jawaban") or "").strip():
            f.append("jawab_tanpa_jawaban")
    return f


def answer_id_for(item_id: str, setting_id: str, slot: str, model_profile: str, cache_key: str) -> str:
    return sha256_hex(canonical_json([item_id, setting_id, slot, model_profile, cache_key]))


def _save(answers_dir: Path, rec: dict[str, Any]) -> None:
    """Tulis atomik bila belum ada: run_id berkas = run berbayar pertama; panggilan cache berikut tidak menimpa."""
    path = Path(answers_dir) / f"{rec['answer_id']}.json"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def load_answer(answers_dir: Path, answer_id: str) -> dict[str, Any] | None:
    try:
        return json.loads((Path(answers_dir) / f"{answer_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run_answers(client: SparkClient, prompt: PromptC, slots: list[tuple[str, ContextBundle]], *, item_id: str,
                model_profile: str, meta: Mapping[str, Any], answers_dir: Path,
                persist: bool = True) -> tuple[list[AnswerOutcome], BatchResult]:
    """Jalankan kolom berurutan. Raises `BudgetExceeded` (sebelum jaringan) bila proyeksi melewati cap.
    `persist=False` (jalur baca/replay): tidak menulis `answers_dir` (H-051; run_id replay bukan run berbayar)."""
    calls = [make_call(prompt, b, meta) for _s, b in slots]
    batch = client.run_batch(calls)  # proyeksi dulu di dalam; replay tidak memanggil API
    outcomes: list[AnswerOutcome] = []
    for (slot, bundle), res in zip(slots, batch.results):
        if res is None:
            raise RuntimeError("answer batch stopped before completion")  # BudgetExceeded sudah dilempar bila cap lewat
        if res.output is None:
            err = res.record.error or {"code": "model_error", "message": "call failed"}
            outcomes.append(AnswerOutcome(slot, res.record, None, dict(err)))
            continue
        out = res.parsed
        aid = answer_id_for(item_id, bundle.setting_id, slot, model_profile, res.record.cache_key)
        rec = {"answer_id": aid, "item_id": item_id, "setting_id": bundle.setting_id, "slot": slot,
               "model_profile": model_profile, "context_chunk_ids": list(bundle.chunk_ids),
               "budget_tokens": bundle.budget_tokens, "output": out, "run_id": res.record.run_id,
               "flags": flags_for(out)}
        if persist:
            _save(answers_dir, rec)
        outcomes.append(AnswerOutcome(slot, res.record, rec))
    return outcomes, batch
