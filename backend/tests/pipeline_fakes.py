"""Pembantu test pipeline: encoder palsu deterministik, dokumen/butir mainan, direktori konfigurasi mainan.

Tanpa GPU, tanpa bge-m3, tanpa Model API.
"""

from __future__ import annotations

import json
import re
import shutil
import zlib
from pathlib import Path
from typing import Sequence

import numpy as np

from backend import config

from ._chunk_util import u_doc  # noqa: F401  (diekspor ulang untuk test)

DIM = 64


class FakeEncoder:
    """Bag-of-words berhash, ternormalisasi (cosine = dot). Menghitung panggilan untuk bukti nol hitung."""

    model = "fake-enc"
    revision = "r0"
    max_seq_length = 8192
    device = "cpu"

    def __init__(self) -> None:
        self.encode_calls = 0
        self.texts_encoded = 0

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        self.encode_calls += 1
        self.texts_encoded += len(texts)
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"\w+", t.lower()):
                out[i, zlib.crc32(w.encode()) % DIM] += 1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out

    def token_counts(self, texts: Sequence[str]) -> list[int]:
        return [len(re.findall(r"\S+", t)) + 2 for t in texts]


# Butir mainan atas dokumen U (201 karakter). Gold = rentang unit di U_UNITS (tolok ukur: docs/scenarios/M1.2.md).
TOY_ITEMS = [
    ("t01", "literal", "Aaa bbb", [(12, 24)]),
    ("t02", "literal", "Ccc ddd", [(25, 37)]),
    ("t03", "parafrase", "Eee fff", [(38, 50)]),
    ("t04", "parafrase", "Ggg hhh iii", [(52, 76)]),
    ("t05", "literal", "Jjj kkk", [(124, 141)]),
    ("t06", "parafrase", "Aaa Ccc Eee", [(12, 24), (25, 37), (38, 50)]),
    ("t07", "literal", "cukup jelas", [(102, 123)]),
    ("t08", "parafrase", "Ggg", [(52, 76)]),
    ("t09", "literal", "tidak ada hubungan zzz", []),
    ("t10", "parafrase", "Jjj", [(124, 141)]),
]


def write_toy_butir(directory: Path, clean_sha256: str, doc_id: str = "synthetic") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / "uupt.v1.jsonl"
    lines = []
    for iid, mode, query, spans in TOY_ITEMS:
        lines.append(json.dumps({"clean_sha256": clean_sha256, "doc_id": doc_id, "family": "uupt", "gold_spans": [{"start": s, "end": e} for s, e in spans],
                                 "id": iid, "mode": mode, "origin": "operator", "query": query}, sort_keys=True))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return p


def toy_config_dir(dest: Path, *, size: int = 6, overlap: int = 2) -> Path:
    """Salinan `config/` dengan ukuran fixed_size mainan (pembanding `[baseline]` mengikuti)."""
    dest.mkdir(parents=True, exist_ok=True)
    for f in config.CONFIG_DIR.glob("*.toml"):
        text = f.read_bytes().decode("utf-8")
        if f.name == "grid.toml":
            text = text.replace("chunk_size_tokens = 512", f"chunk_size_tokens = {size}").replace("overlap_tokens = 64", f"overlap_tokens = {overlap}")
        (dest / f.name).write_bytes(text.encode("utf-8"))
    return dest
