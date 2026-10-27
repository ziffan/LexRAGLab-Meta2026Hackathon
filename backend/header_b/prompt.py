"""Prompt peran B berversi (`prompts/b/`) dan skema `HeaderB` (docs/DATA-CONTRACTS.md 7)."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from backend import config
from backend.spark.schema_check import check_schema_name, check_strict

PROMPT_DIR = config.REPO_ROOT / "prompts" / "b"
SCHEMA_NAME = "HeaderB"

HEADER_B_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["chunk_id", "header"],
    "properties": {"chunk_id": {"type": "string"}, "header": {"type": "string"}},
}


def header_schema(max_length_chars: int | None = None) -> dict:
    """Skema `HeaderB`. `max_length_chars` (config `schema_max_length_chars`, H-079) menambah `maxLength` pada `header`;
    None (bawaan) = skema v1 tanpa `maxLength` (hash skema sama, cache lama utuh)."""
    schema = copy.deepcopy(HEADER_B_SCHEMA)
    if max_length_chars is not None:
        schema["properties"]["header"]["maxLength"] = int(max_length_chars)
    return schema


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def schema_hash(max_length_chars: int | None = None) -> str:
    return sha256_text(json.dumps(header_schema(max_length_chars), sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def validate_schema(max_length_chars: int | None = None) -> None:
    """Pra-validasi strict lokal. `maxLength` hanya sah bila flag `max_length_chars` aktif (bilangan bulat >= 1)."""
    if max_length_chars is not None and (not isinstance(max_length_chars, int) or isinstance(max_length_chars, bool)
                                         or max_length_chars < 1):
        raise ValueError("HeaderB schema_max_length_chars must be a positive integer or unset")
    schema = header_schema(max_length_chars)
    bad = check_schema_name(SCHEMA_NAME) or check_strict(schema)
    if bad:
        raise ValueError(f"HeaderB schema is not strict-compliant: {bad}")
    for name, sub in schema["properties"].items():
        has = "maxLength" in sub
        if has and not (name == "header" and max_length_chars is not None):
            raise ValueError(f"HeaderB schema: maxLength on '{name}' is not allowed unless schema_max_length_chars is set")


@dataclass(frozen=True)
class PromptB:
    version: str
    template: str  # sudah dirender (batas panjang dari config)
    prompt_hash: str  # sha256 teks terender: mengubah batas panjang mengubah kunci cache

    def cache_key_for(self, doc_clean_sha256: str) -> str:
        """`prompt_cache_key` per dokumen (SPARK-ROLES 3)."""
        return f"lexraglab-b-{self.version}-{self.prompt_hash[:12]}-{doc_clean_sha256[:12]}"


def load_prompt(max_header_tokens: int, version: str | None = None, directory: Path | None = None) -> PromptB:
    d = Path(directory) if directory is not None else PROMPT_DIR
    meta = json.loads((d / "versions.json").read_text(encoding="utf-8"))
    ver = version or meta["current"]
    raw = (d / meta["versions"][ver]["file"]).read_bytes().decode("utf-8")
    text = raw.replace("{max_header_tokens}", str(int(max_header_tokens)))
    return PromptB(version=ver, template=text, prompt_hash=sha256_text(text))
