"""Penggerak test H-101: jalankan `run_compare` atas Prepared sintetis dengan rig palsu."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.header_b.compare import make_gate, run_compare, select_pairs
from backend.header_b.run import Prepared

from .h101_helpers import GATE, Tok, hc_b
from .spark_fakes import Rig


def meta_for(p: Prepared) -> dict:
    return {"corpus_hash": "ch-" + p.doc.sha256, "clean_sha256": p.doc.clean_sha256, "loader_rules_version": p.doc.loader_rules_version,
            "tokenizer": {"name": "words", "version": "1"}}


def go(rig: Rig, prepared: Prepared | list[Prepared], store_dir: Path, *, profile: str = "baseten_open", hc: dict | None = None,
       max_attempts: int = 8, gate: Any = "auto", sample: int | None = None, max_units: int | None = None,
       gate_cfg: dict | None = None, tokenizer: Any = None) -> dict:
    """Jalankan `run_compare` atas satu atau beberapa Prepared (satu dokumen/sumber masing-masing). `gate="auto"` = gerbang
    nyata per pool (Baseten; profil lokal tanpa gerbang), None = tanpa gerbang."""
    ps = prepared if isinstance(prepared, list) else [prepared]
    prepared_map: dict[str, dict[str, Prepared]] = {}
    for p in ps:
        prepared_map.setdefault(p.doc.doc_id, {})[p.source] = p
    pairs = select_pairs(prepared_map, store_dir, sample=sample, max_units=max_units)
    prof = rig.model["profiles"][profile]
    g = {"factor_bp": GATE["factor_bp"], "batch_cap_micros": GATE["batch_cap_micros"], **(gate_cfg or {})}
    if gate == "auto":
        gate = None if prof.get("api") == "chat_completions" else make_gate(prof["provider"], rig.budget, rig.model, rig.env, rig.runs)
    return run_compare(rig.client, pairs, profile=profile, prof=prof, model_cfg=rig.model, hc=hc or hc_b(), gate_cfg=g,
                       tokenizer=tokenizer or Tok(), store_dir=store_dir, meta_for=meta_for, max_attempts=max_attempts, gate=gate)
