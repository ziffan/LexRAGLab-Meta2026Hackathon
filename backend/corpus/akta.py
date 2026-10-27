"""Pemuat korpus akta sintetis (M4.1, H-039, H-041, H-054): baca biner, tolak berkas tak sah, buang disclaimer.

Aturan: docs/DATA-CONTRACTS.md §2 ("pemuat akta hanya memeriksa UTF-8, `\r`, BOM, dan hash"). Tafsir yang dipakai:

- Baris pertama berkas wajib persis `loader_akta.disclaimer` (H-041); baris kosong sesudahnya ikut dibuang. Disclaimer
  disimpan di `metadata`, bukan di teks bersih: ia bukan isi akta, dan tidak boleh masuk sampel peran A, chunker, BM25,
  embedder (sama dengan disclaimer editorial UU PT).
- Tanpa normalisasi lain. Teks bersih = baris berkas dari baris isi pertama sampai baris isi terakhir (baris kosong di
  ujung dipangkas), diakhiri satu LF. Jadi offset teks bersih -> baris berkas lewat `line_map`, dan -> offset berkas
  mentah dengan `metadata["raw_offset_shift"]` (offset mentah = offset bersih + shift).
- `sections`: satu rentang `loader_akta.section` yang mencakup seluruh teks bersih (chunker skema dan verifikasi offset
  bekerja per section). `annotations`: kosong (kontrak §2).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend import config as _config

from .errors import CorpusError


def akta_entries(config_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """doc_id -> entri dari `config/corpus_akta.toml`. Berkas config tak ada = tidak ada akta terdaftar."""
    try:
        cfg = _config.load("corpus_akta", config_dir)
    except _config.ConfigError:
        return {}
    return {d["doc_id"]: d for d in cfg.get("documents", [])}


def load_akta(entry: dict[str, Any], *, config_dir: Path | None = None, path: Path | str | None = None,
              verify_hash: bool = True, expected_sha256: str | None = None) -> Any:
    from .loader import CorpusDoc, read_checked  # impor lambat: loader mengimpor modul ini

    cfg_all = _config.load("corpus_akta", config_dir)
    cfg = cfg_all["loader_akta"]
    file_path = Path(path) if path is not None else _config.REPO_ROOT / entry["path"]
    want_sha = (expected_sha256 or entry["sha256"]) if verify_hash else None
    text, sha = read_checked(file_path, want_sha)

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0] != cfg["disclaimer"]:
        raise CorpusError("R12", "synthetic disclaimer not found as line 1 (H-041)")
    k = 1
    while k < len(lines) and lines[k] == "":
        k += 1
    end = len(lines)
    while end > k and lines[end - 1] == "":
        end -= 1
    if k >= end:
        raise CorpusError("R12", "no deed text after the disclaimer")
    body = lines[k:end]
    clean_text = "\n".join(body) + "\n"
    starts: list[int] = []
    pos = 0
    for t in body:
        starts.append(pos)
        pos += len(t) + 1
    line_map = [[s, k + 1 + i] for i, s in enumerate(starts)]  # nomor baris berkas berbasis 1
    shift = sum(len(t) + 1 for t in lines[:k])  # code point awalan yang dibuang (sama dengan offset mentah teks bersih 0)
    rel = entry["path"][5:] if entry["path"].startswith("data/") else entry["path"]
    return CorpusDoc(
        doc_id=entry["doc_id"], family="akta", title=entry["title"], path=rel, sha256=sha,
        clean_sha256=hashlib.sha256(clean_text.encode("utf-8")).hexdigest(),
        loader_rules_version=cfg_all["loader_rules_version"], char_count=len(clean_text),
        tokens_local=None, tokens_endpoint=None, calibration_ratio=None,
        sections=[{"section": cfg["section"], "start": 0, "end": len(clean_text)}], annotations=[],
        text=clean_text, line_map=line_map,
        metadata={"address_prefix": entry["address_prefix"], "disclaimer": lines[0], "disclaimer_line": 1,
                  "raw_offset_shift": shift, "synthetic": True},
    )
