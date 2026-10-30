"""Penyimpanan run: `runs/spark/records/<run_id>.json` (semua RunRecord) dan
`runs/spark/<peran>/<cache_key>.json` (cache keluaran sah; ARCHITECTURE §8, T8).
Tulis atomik, UTF-8, LF. Berkas cache rusak dianggap miss."""

from __future__ import annotations

import hashlib
import json
import os
import threading
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


def origin_record(runs_dir: Path, role: str, key: str) -> RunRecord | None:
    """RunRecord panggilan asal (berbayar) yang menghasilkan entri cache `key` (UX-03): `run_id` dari entri cache, lalu record
    tersimpan `records/<run_id>.json` (sumber kebenaran, bukan salinan di cache). Hanya bila record itu berstatus `ok` dengan
    `cache_key` yang sama. Selain itu None. Hanya membaca."""
    try:
        entry = json.loads(cache_path(runs_dir, role, key).read_text(encoding="utf-8"))
        rid = entry["record"]["run_id"]
        if entry.get("cache_key") != key or not isinstance(rid, str) or not rid.isalnum():
            return None
        rec = RunRecord.from_dict(json.loads((spark_dir(runs_dir) / RECORDS_DIR / f"{rid}.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return rec if rec.status == "ok" and rec.cache_key == key else None


class _Skip:
    """Hasil parse yang boleh di-cache sebagai "lewati" (isi rusak / tanpa record); bukan galat baca sesaat."""


SKIP = _Skip()

_StatKey = tuple[int, int, int, int]


class DirIndex:
    """Indeks inkremental berkas `*.json` satu direktori (M5.1-N1): `nama -> (kunci stat, hasil parse)`.

    Tiap `load()`: `os.scandir`; stat diambil dari `DirEntry` SEBELUM berkas dibaca dan stat itulah yang disimpan, jadi
    penulisan di antaranya membuat stat berikut berbeda dan berkas di-parse ulang. Kunci = (`st_mtime_ns`, `st_ctime_ns`,
    `st_size`, `st_ino`). Hanya berkas baru/berubah yang di-parse; entri yang hilang dibuang. Urutan hasil = `sorted` atas
    `Path` (sama dengan `sorted(d.glob("*.json"))`). `parse(path)` mengembalikan nilai, `SKIP` (di-cache, dilewati), atau
    melempar; galat diteruskan dan tidak di-cache (dicoba ulang panggilan berikut), kecuali `FileNotFoundError` (berkas
    hilang di antara scandir dan baca = dilewati) dan `skip_errors` (dilewati panggilan ini saja, tidak di-cache). Satu lock per indeks: pemanggil serentak menunggu satu
    pemindaian. Hasil = list BARU; objek di dalamnya di-share dan diperlakukan baca-saja."""

    def __init__(self, directory: Path, parse: Any, *, skip_errors: tuple[type[BaseException], ...] = ()) -> None:
        self.dir = Path(directory)
        self._parse = parse
        self._skip_errors = skip_errors
        self._entries: dict[str, tuple[_StatKey, Any]] = {}
        self._order: list[str] | None = None
        self._lock = threading.Lock()

    def load(self) -> list[Any]:
        with self._lock:
            try:
                listing = list(os.scandir(self.dir))
            except (FileNotFoundError, NotADirectoryError):
                self._entries, self._order = {}, None
                return []
            seen: dict[str, tuple[_StatKey, Any]] = {}
            changed = False
            for e in listing:
                if not os.path.normcase(e.name).endswith(".json"):  # = glob("*.json"): tanpa beda huruf di Windows
                    continue
                try:
                    if not e.is_file():
                        continue
                    st = e.stat()
                except FileNotFoundError:
                    continue
                key = (st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_ino)
                old = self._entries.get(e.name)
                if old is not None and old[0] == key:
                    seen[e.name] = old
                    continue
                changed = True
                try:
                    val = self._parse(Path(e.path))
                except FileNotFoundError:
                    continue
                except self._skip_errors:
                    continue  # galat baca sesaat: dilewati panggilan ini, tidak di-cache
                seen[e.name] = (key, val)
            if changed or self._order is None or len(seen) != len(self._entries):
                # Urutan = sorted(Path) jalur lama: satu direktori, jadi sama dengan membandingkan normcase(nama).
                self._order = sorted(seen, key=os.path.normcase)
            self._entries = seen
            return [v for v in (seen[n][1] for n in self._order) if v is not SKIP]


def _parse_record(p: Path) -> RunRecord:
    try:
        return RunRecord.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except FileNotFoundError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError(f"unreadable run record file: {p.name}") from None


def records_index(runs_dir: Path) -> DirIndex:
    """Indeks `runs/spark/records/`; semantik galat = `load_records` (berkas rusak -> ValueError, tidak di-cache)."""
    return DirIndex(spark_dir(runs_dir) / RECORDS_DIR, _parse_record)
