"""Penyimpanan run: `runs/spark/records/<run_id>.json` (semua RunRecord) dan
`runs/spark/<peran>/<cache_key>.json` (cache keluaran sah; ARCHITECTURE §8, T8).
Tulis atomik, UTF-8, LF. Berkas cache rusak dianggap miss."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .runrecord import RunRecord

RECORDS_DIR = "records"


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key_for(provider: Any, model: Any, quantization: Any, effort: Any,
                  prompt_hash: Any, schema_hash: Any, input_hash: Any) -> str:
    """Kunci tujuh komponen (ARCHITECTURE §8). Tanpa prompt_cache_key dan tanpa key API (T8)."""
    return sha256_hex(canonical_json([provider, model, quantization, effort, prompt_hash, schema_hash, input_hash]))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def spark_dir(runs_dir: Path) -> Path:
    return Path(runs_dir) / "spark"


def save_record(runs_dir: Path, record: RunRecord) -> Path:
    path = spark_dir(runs_dir) / RECORDS_DIR / f"{record.run_id}.json"
    _atomic_write(path, record.to_json() + "\n")
    return path


def load_records(runs_dir: Path) -> list[RunRecord]:
    """Semua record tersimpan. Berkas rusak -> ValueError (buku belanja gagal tertutup)."""
    d = spark_dir(runs_dir) / RECORDS_DIR
    out: list[RunRecord] = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            out.append(RunRecord.from_dict(json.loads(p.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError, KeyError):
            raise ValueError(f"unreadable run record file: {p.name}") from None
    return out


def cache_path(runs_dir: Path, role: str, key: str) -> Path:
    return spark_dir(runs_dir) / role / f"{key}.json"


def cache_write(runs_dir: Path, role: str, key: str, output_canonical: str, record: RunRecord) -> None:
    entry = {"cache_key": key, "output": output_canonical, "output_sha256": sha256_hex(output_canonical),
             "record": record.to_dict()}
    _atomic_write(cache_path(runs_dir, role, key), canonical_json(entry) + "\n")


def cache_read(runs_dir: Path, role: str, key: str) -> str | None:
    """Keluaran terkanon dari cache, atau None bila tidak ada / rusak (miss)."""
    p = cache_path(runs_dir, role, key)
    try:
        entry = json.loads(p.read_text(encoding="utf-8"))
        out = entry["output"]
        if entry["cache_key"] != key or not isinstance(out, str):
            return None
        if entry.get("output_sha256") != sha256_hex(out):
            return None
        parsed = json.loads(out)
        if not isinstance(parsed, dict):
            return None
        return canonical_json(parsed)
    except (OSError, ValueError, KeyError, TypeError):
        return None
