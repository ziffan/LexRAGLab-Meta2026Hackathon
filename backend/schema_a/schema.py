"""Skema `SchemaA` (docs/DATA-CONTRACTS.md 6) dan validasi: struktur (skema yang sama untuk keluaran Spark dan koreksi
operator) lalu semantik (SPARK-ROLES 2): pola dikompilasi dan diuji terhadap contohnya sendiri, contoh ditemukan persis di sampel."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Sequence

from backend.spark.schema_check import check_schema_name, check_strict, validate_instance

SCHEMA_NAME = "SchemaA"
FAMILIES = ("uupt", "akta")

SCHEMA_A: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["family", "levels", "default_chunk_level", "notes"],
    "properties": {
        "family": {"type": "string"},
        "levels": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["order", "name", "marker_pattern", "examples", "parent_order", "is_chunk_unit"],
                "properties": {
                    "order": {"type": "integer"},
                    "name": {"type": "string"},
                    "marker_pattern": {"type": "string"},
                    "examples": {"type": "array", "items": {"type": "string"}},
                    "parent_order": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                    "is_chunk_unit": {"type": "boolean"},
                },
            },
        },
        "default_chunk_level": {"type": "integer"},
        "notes": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
}

# Batas kewajaran (bukan aturan hukum): menjaga editor dan regex dari masukan patologis.
MAX_LEVELS = 12
MAX_EXAMPLES = 10
MAX_PATTERN_CHARS = 500
MAX_EXAMPLE_CHARS = 300
MAX_ERRORS = 20
_NESTED_QUANTIFIER = re.compile(r"\([^()]*[+*][^()]*\)\s*(?:[+*]|\{\d)")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def schema_hash() -> str:
    return sha256_text(json.dumps(SCHEMA_A, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def validate_schema() -> None:
    """Skema patuh strict dan nama sah; dipanggil sebelum kirim (G-03)."""
    bad = check_schema_name(SCHEMA_NAME) or check_strict(SCHEMA_A)
    if bad:
        raise ValueError(f"SchemaA schema is not strict-compliant: {bad}")


def compile_marker(pattern: str) -> tuple[re.Pattern[str] | None, str | None]:
    """(pola terkompilasi, None) atau (None, alasan). Pola dijalankan dengan `re.search` + `re.MULTILINE`."""
    if not isinstance(pattern, str) or not pattern.strip():
        return None, "marker_pattern is empty"
    if len(pattern) > MAX_PATTERN_CHARS:
        return None, f"marker_pattern is longer than {MAX_PATTERN_CHARS} characters"
    if _NESTED_QUANTIFIER.search(pattern):
        return None, "marker_pattern has a nested quantifier (unsafe)"
    try:
        rx = re.compile(pattern, re.MULTILINE)
    except (re.error, RecursionError, OverflowError) as exc:
        return None, f"marker_pattern does not compile ({type(exc).__name__})"
    if rx.search("") is not None:
        return None, "marker_pattern matches the empty string"
    return rx, None


def check_body(body: Any) -> str | None:
    """Validasi struktur terhadap SCHEMA_A (sama untuk Spark dan operator). None bila sah."""
    return validate_instance(body, SCHEMA_A)


def semantic_check(body: dict[str, Any], *, family: str | None = None,
                   samples: Sequence[str] | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    """(galat, validation). `validation` = `[{order, example, matched}]` (DATA-CONTRACTS 6) untuk setiap contoh,
    `matched` = pola level itu cocok dengan contohnya sendiri. Galat kosong = sah. `samples=None` melewati
    pemeriksaan "contoh ada di sampel" (pemanggil harus mencatat bahwa itu dilewati)."""
    errs: list[str] = []
    validation: list[dict[str, Any]] = []
    levels = body.get("levels") or []
    if family is not None and body.get("family") != family:
        errs.append("family differs from the requested family")
    if not levels:
        errs.append("levels is empty")
    if len(levels) > MAX_LEVELS:
        errs.append(f"more than {MAX_LEVELS} levels")
    orders: list[int] = []
    for idx, lv in enumerate(levels[:MAX_LEVELS]):
        o = lv["order"]
        tag = f"level[{idx}] order {o}"
        if orders and o <= orders[-1]:
            errs.append(f"{tag}: order must be strictly ascending")
        if not lv["name"].strip():
            errs.append(f"{tag}: name is empty")
        po = lv["parent_order"]
        if po is not None and po not in orders:
            errs.append(f"{tag}: parent_order {po} is not an earlier order")
        orders.append(o)
        rx, why = compile_marker(lv["marker_pattern"])
        if why:
            errs.append(f"{tag}: {why}")
        exs = lv["examples"]
        if not exs:
            errs.append(f"{tag}: examples is empty")
        if len(exs) > MAX_EXAMPLES:
            errs.append(f"{tag}: more than {MAX_EXAMPLES} examples")
        for ex in exs[:MAX_EXAMPLES]:
            matched = False
            if not ex.strip():
                errs.append(f"{tag}: an example is empty")
            elif len(ex) > MAX_EXAMPLE_CHARS or "\n" in ex or "\r" in ex:
                errs.append(f"{tag}: an example is not a single short line")
            else:
                if rx is not None:
                    matched = rx.search(ex) is not None
                    if not matched:
                        errs.append(f"{tag}: marker_pattern does not match its own example {ex[:40]!r}")
                if samples is not None and not any(ex in s for s in samples):
                    errs.append(f"{tag}: example not found verbatim in the sample {ex[:40]!r}")
            validation.append({"order": o, "example": ex, "matched": matched})
    d = body.get("default_chunk_level")
    unit = next((lv for lv in levels if lv["order"] == d), None)
    if unit is None:
        errs.append(f"default_chunk_level {d} is not an existing order")
    elif not unit["is_chunk_unit"]:
        errs.append(f"default_chunk_level {d} has is_chunk_unit = false")
    return errs[:MAX_ERRORS], validation


def validate_body(body: Any, *, family: str | None = None,
                  samples: Sequence[str] | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    """Struktur lalu semantik. Galat struktur menghentikan pemeriksaan semantik."""
    bad = check_body(body)
    if bad:
        return [f"schema: {bad}"], []
    return semantic_check(body, family=family, samples=samples)
