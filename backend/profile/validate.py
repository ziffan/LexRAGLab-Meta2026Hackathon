"""Validasi bentuk `Profile` (DATA-CONTRACTS 11, 10; M4.3 A3, A12, A13). Dijalankan sebelum cek hash apa pun.
Pelanggaran -> `ProfileError("validation_failed")` dengan pesan yang menyebut field bermasalah. Tanpa membaca korpus."""

from __future__ import annotations

import math
import re
from typing import Any

from backend.chunking.model import make_setting_id
from backend.schema_a.schema import validate_body

from .errors import ProfileError

PROFILE_VERSION = "1"  # A3: versi format, bukan penghitung ekspor
FAMILIES = ("uupt", "akta")
CHUNKERS = ("structure_handwritten", "structure_schema", "fixed_size")
MODES = ("dense", "bm25", "hybrid")
PACKING = ("stop", "skip", "truncate")
PROFILE_KEYS = ("profile_version", "family", "setting", "schema", "corpus_hash", "config_hash", "chunk_set_hash", "tokenizer",
                "clean_sha256", "loader_rules_version", "packing", "embedder", "held_out", "created_at")
SETTING_KEYS = ("setting_id", "family", "chunker", "chunk_size_tokens", "overlap_tokens", "schema_version", "retrieval_mode",
                "header_b", "budget_tokens")
HELD_OUT_KEYS = ("n_items", "by_origin", "mean_span_recall", "mean_token_precision", "fully_covered")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def _bad(msg: str) -> ProfileError:
    return ProfileError("validation_failed", msg)


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return (isinstance(x, (int, float)) and not isinstance(x, bool)) and math.isfinite(x)


def _keys(obj: Any, expected: tuple[str, ...], where: str) -> None:
    if not isinstance(obj, dict):
        raise _bad(f"{where} must be an object")
    for k in expected:
        if k not in obj:
            raise _bad(f"{where}.{k} is missing" if where != "profile" else f"profile field {k!r} is missing")
    extra = sorted(set(obj) - set(expected))
    if extra:
        raise _bad(f"{where} has unexpected field {extra[0]!r}")


def validate_setting(s: Any, family: str) -> None:
    _keys(s, SETTING_KEYS, "setting")
    if s["family"] != family:
        raise _bad("setting.family must equal profile.family")
    if s["chunker"] not in CHUNKERS:
        raise _bad(f"setting.chunker must be one of {list(CHUNKERS)}")
    if s["retrieval_mode"] not in MODES:
        raise _bad(f"setting.retrieval_mode must be one of {list(MODES)}")
    if not isinstance(s["header_b"], bool):
        raise _bad("setting.header_b must be a boolean")
    if not _is_int(s["budget_tokens"]) or s["budget_tokens"] <= 0:
        raise _bad("setting.budget_tokens must be a positive integer")
    size, ov, sv = s["chunk_size_tokens"], s["overlap_tokens"], s["schema_version"]
    if s["chunker"] == "fixed_size":
        if not _is_int(size) or size <= 0:
            raise _bad("setting.chunk_size_tokens must be a positive integer for fixed_size")
        if not _is_int(ov) or not 0 <= ov < size:
            raise _bad("setting.overlap_tokens must be an integer in [0, chunk_size_tokens) for fixed_size")
        if sv is not None:
            raise _bad("setting.schema_version must be null for fixed_size")
    elif s["chunker"] == "structure_schema":
        if not _is_int(sv) or sv < 1:
            raise _bad("setting.schema_version must be a positive integer for structure_schema")
        if size is not None or ov is not None:
            raise _bad("setting.chunk_size_tokens and setting.overlap_tokens must be null for structure_schema")
    else:
        if size is not None or ov is not None or sv is not None:
            raise _bad("setting.chunk_size_tokens, overlap_tokens and schema_version must be null for structure_handwritten")
    if not isinstance(s["setting_id"], str) or s["setting_id"] != make_setting_id(s):
        raise _bad("setting.setting_id does not match the canonical hash of the setting fields")


def _validate_held_out(h: Any) -> None:
    _keys(h, HELD_OUT_KEYS, "held_out")
    if not _is_int(h["n_items"]) or h["n_items"] < 0:
        raise _bad("held_out.n_items must be a non-negative integer")
    bo = h["by_origin"]
    if not isinstance(bo, dict) or not all(isinstance(k, str) and _is_int(v) and v >= 0 for k, v in bo.items()):
        raise _bad("held_out.by_origin must map origin names to non-negative integers")
    for k in ("mean_span_recall", "mean_token_precision"):
        if h[k] is not None and not _is_num(h[k]):
            raise _bad(f"held_out.{k} must be a number or null")
    fc = h["fully_covered"]
    if (not isinstance(fc, dict) or set(fc) != {"covered", "total"} or not _is_int(fc["covered"]) or not _is_int(fc["total"])
            or fc["covered"] < 0 or fc["covered"] > fc["total"]):
        raise _bad("held_out.fully_covered must be {covered, total} integers with covered <= total")


def validate_profile_shape(p: Any) -> None:
    _keys(p, PROFILE_KEYS, "profile")
    if p["profile_version"] != PROFILE_VERSION:
        raise _bad(f"profile_version must be {PROFILE_VERSION!r}")
    if p["family"] not in FAMILIES:
        raise _bad(f"family must be one of {list(FAMILIES)}")
    family = p["family"]
    validate_setting(p["setting"], family)
    chunker = p["setting"]["chunker"]
    if chunker == "structure_schema":
        if not isinstance(p["schema"], dict):
            raise _bad("schema must be the embedded schema body for structure_schema")
        # Bentuk skema tertanam dicek terhadap SCHEMA_A (struktur + semantik tanpa sampel) agar impor cacat -> 422, bukan 500.
        errs, _ = validate_body(p["schema"], family=family)
        if errs:
            raise _bad(f"schema is not a valid schema A body: {errs[0]}")
    elif p["schema"] is not None:
        raise _bad("schema must be null unless the chunker is structure_schema")
    for k in ("corpus_hash", "config_hash", "chunk_set_hash", "clean_sha256"):
        if not isinstance(p[k], str) or not _HEX64.match(p[k]):
            raise _bad(f"{k} must be a 64-character lowercase hex SHA-256")
    tk = p["tokenizer"]
    if (not isinstance(tk, dict) or set(tk) != {"name", "version"} or not all(isinstance(v, str) and v for v in tk.values())):
        raise _bad("tokenizer must be {name, version} strings")
    if not isinstance(p["loader_rules_version"], str) or not p["loader_rules_version"]:
        raise _bad("loader_rules_version must be a non-empty string")
    if p["packing"] not in PACKING:
        raise _bad(f"packing must be one of {list(PACKING)}")
    e = p["embedder"]
    if e is not None and (not isinstance(e, dict) or set(e) != {"name", "revision", "max_seq_length"}
                          or not isinstance(e["name"], str) or not isinstance(e["revision"], str) or not _is_int(e["max_seq_length"])):
        raise _bad("embedder must be {name, revision, max_seq_length} or null")
    if family == "uupt":
        if p["held_out"] is None:
            raise _bad("held_out must not be null for a uupt profile")
        _validate_held_out(p["held_out"])
    elif p["held_out"] is not None:
        raise _bad("held_out must be null for an akta profile (no split, H-054)")
    if not isinstance(p["created_at"], str) or not _TS.match(p["created_at"]):
        raise _bad("created_at must be a UTC ISO 8601 timestamp ending with Z")
