"""Tokenizer lokal deterministik H-014 (EVAL-SPEC §2).

Pilihan pertama: tokenizer Muse Spark Open dari cache HF lokal (tidak di-commit, H-029).
Cadangan: `o200k_base` (tiktoken). Nama dan versi dicatat di setiap RunRecord.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend import config


@dataclass(frozen=True)
class TokenizerInfo:
    name: str
    version: str


class LocalTokenizer:
    def __init__(self, info: TokenizerInfo, impl: Any, kind: str):
        self.info = info
        self._impl = impl
        self._kind = kind

    def count(self, text: str) -> int:
        if self._kind == "hf":
            return len(self._impl.encode(text, add_special_tokens=False).ids)
        return len(self._impl.encode(text, disallowed_special=()))

    def offsets(self, text: str) -> list[tuple[int, int]]:
        """Offset code point `[start, end)` per token (hanya tokenizer HF)."""
        if self._kind != "hf":
            raise NotImplementedError("offsets are only available for the HF tokenizer")
        return list(self._impl.encode(text, add_special_tokens=False).offsets)


def hf_snapshot_file(repo: str, revision: str, filename: str) -> Path:
    hub = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub")
    return hub / ("models--" + repo.replace("/", "--")) / "snapshots" / revision / filename


def _load_hf(cfg: dict[str, Any]) -> LocalTokenizer | None:
    from tokenizers import Tokenizer

    sec = cfg[cfg["primary"]]
    path = hf_snapshot_file(sec["hf_repo"], sec["hf_revision"], "tokenizer.json")
    if not path.is_file():
        return None
    raw = path.read_bytes()  # symlink ke blobs diikuti; berkas 0 byte ditolak
    if not raw:
        raise RuntimeError(f"tokenizer file is empty: {path.name}")
    digest = hashlib.sha256(raw).hexdigest()
    impl = Tokenizer.from_str(raw.decode("utf-8"))
    info = TokenizerInfo(name=cfg["primary"], version=f"{sec['hf_repo']}@{sec['hf_revision']}#sha256:{digest[:16]}")
    return LocalTokenizer(info, impl, "hf")


def _load_fallback(cfg: dict[str, Any]) -> LocalTokenizer:
    import tiktoken

    enc = tiktoken.get_encoding(cfg["fallback"])
    return LocalTokenizer(TokenizerInfo(name=cfg["fallback"], version=f"tiktoken-{tiktoken.__version__}"), enc, "tiktoken")


@lru_cache(maxsize=1)
def get_tokenizer() -> LocalTokenizer:
    cfg = config.load("tokenizer")
    return _load_hf(cfg) or _load_fallback(cfg)
