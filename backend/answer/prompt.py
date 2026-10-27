"""Prompt peran C berversi (`prompts/c/`) dan skema `AnswerC` (docs/DATA-CONTRACTS.md 8)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from backend import config
from backend.spark.schema_check import check_schema_name, check_strict

PROMPT_DIR = config.REPO_ROOT / "prompts" / "c"
SCHEMA_NAME = "AnswerC"

ANSWER_C_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "jawaban", "kutipan"],
    "properties": {
        "status": {"type": "string", "enum": ["jawab", "tolak", "bukti_tidak_cukup"]},
        "jawaban": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "kutipan": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["alamat", "teks"],
                "properties": {"alamat": {"type": "string"}, "teks": {"type": "string"}},
            },
        },
    },
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def schema_hash() -> str:
    return sha256_text(json.dumps(ANSWER_C_SCHEMA, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def validate_schema() -> None:
    """Skema patuh strict dan nama sah; dipanggil sebelum kirim (G-03)."""
    bad = check_schema_name(SCHEMA_NAME) or check_strict(ANSWER_C_SCHEMA)
    if bad:
        raise ValueError(f"AnswerC schema is not strict-compliant: {bad}")


@dataclass(frozen=True)
class PromptC:
    version: str
    template: str
    prompt_hash: str  # sha256 byte berkas
    max_output_tokens: int
    unit_labels: bool = False  # H-070: perakit konteks menyisipkan label alamat unit di potongan multi-unit (v2+)

    @property
    def prompt_cache_key(self) -> str:
        return f"lexraglab-c-{self.version}-{self.prompt_hash[:12]}"


def load_prompt(version: str | None = None, directory: Path | None = None) -> PromptC:
    d = Path(directory) if directory is not None else PROMPT_DIR
    meta = json.loads((d / "versions.json").read_text(encoding="utf-8"))
    ver = version or meta["current"]
    entry = meta["versions"][ver]
    raw = (d / entry["file"]).read_bytes()
    return PromptC(version=ver, template=raw.decode("utf-8"), prompt_hash=hashlib.sha256(raw).hexdigest(),
                   max_output_tokens=int(entry["max_output_tokens"]), unit_labels=bool(entry.get("unit_labels", False)))


def prompt_versions(directory: Path | None = None) -> list[str]:
    """Versi prompt C yang terdaftar, dari terbaru (current) ke yang lebih lama (untuk membaca hasil tersimpan)."""
    d = Path(directory) if directory is not None else PROMPT_DIR
    meta = json.loads((d / "versions.json").read_text(encoding="utf-8"))
    names = list(meta["versions"])
    cur = meta["current"]
    return [cur] + [v for v in reversed(names) if v != cur]
