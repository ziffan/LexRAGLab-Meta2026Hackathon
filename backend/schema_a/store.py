"""Penyimpan `SchemaRecord` berversi (DATA-CONTRACTS 6): `runs/schemas/<family>/v<n>.json`.

Versi hanya bertambah; berkas yang ada tidak pernah ditimpa. v1 = Spark, v2+ = koreksi operator (atau induksi Spark
lain dengan masukan berbeda, `source` membedakan). Tulis atomik, UTF-8, LF."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from .schema import FAMILIES

_LOCK = threading.Lock()
_NAME = re.compile(r"^v([1-9][0-9]*)\.json$")


class SchemaStoreError(Exception):
    """Berkas skema rusak atau tak bisa ditulis."""


class SchemaStore:
    def __init__(self, runs_dir: Path | str) -> None:
        self.root = Path(runs_dir) / "schemas"

    def _dir(self, family: str) -> Path:
        if family not in FAMILIES:
            raise ValueError(f"unknown family {family!r}")
        return self.root / family

    def versions(self, family: str) -> list[int]:
        d = self._dir(family)
        if not d.is_dir():
            return []
        return sorted(int(m.group(1)) for p in d.iterdir() if (m := _NAME.match(p.name)))

    def get(self, family: str, version: int) -> dict[str, Any] | None:
        p = self._dir(family) / f"v{int(version)}.json"
        if not p.is_file():
            return None
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise SchemaStoreError(f"unreadable schema record file: {p.name}") from None
        if not isinstance(rec, dict) or rec.get("schema_version") != int(version) or rec.get("family") != family:
            raise SchemaStoreError(f"inconsistent schema record file: {p.name}")
        return rec

    def list(self, family: str) -> list[dict[str, Any]]:
        return [r for v in self.versions(family) if (r := self.get(family, v)) is not None]

    def find_by_cache_key(self, family: str, cache_key: str) -> dict[str, Any] | None:
        return next((r for r in self.list(family) if r.get("source") == "spark" and r.get("cache_key") == cache_key), None)

    def save_rejected(self, family: str, rec: dict[str, Any]) -> dict[str, Any]:
        """Keluaran Spark yang gagal validasi semantik: `runs/schemas/<family>/rejected/<run_id>.json`. Bukan SchemaRecord,
        tidak punya versi, tidak pernah dipakai chunker. Tidak menimpa berkas yang ada."""
        rid = str(rec.get("run_id", ""))
        if not re.fullmatch(r"[0-9a-f]{32}", rid):
            raise SchemaStoreError("invalid run_id for rejected output")
        path = self._dir(family) / "rejected" / f"{rid}.json"
        with _LOCK:
            if path.exists():
                return rec
            tmp = path.with_name(path.name + ".tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps({**rec, "family": family}, sort_keys=True, ensure_ascii=False, indent=1) + "\n")
                os.replace(tmp, path)
            except OSError:
                raise SchemaStoreError("could not write the rejected output") from None
        return rec

    def list_rejected(self, family: str) -> list[dict[str, Any]]:
        d = self._dir(family) / "rejected"
        if not d.is_dir():
            return []
        out = []
        for p in sorted(d.glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                raise SchemaStoreError(f"unreadable rejected file: {p.name}") from None
        return sorted(out, key=lambda r: (r.get("created_at", ""), r.get("run_id", "")))

    def append(self, family: str, record: dict[str, Any]) -> dict[str, Any]:
        """Beri `schema_version` berikutnya dan tulis. Tidak pernah menimpa."""
        d = self._dir(family)
        with _LOCK:
            vs = self.versions(family)
            n = (vs[-1] if vs else 0) + 1
            rec = {**record, "family": family, "schema_version": n}
            path = d / f"v{n}.json"
            if path.exists():
                raise SchemaStoreError(f"refusing to overwrite {path.name}")
            tmp = path.with_name(path.name + ".tmp")
            try:
                d.mkdir(parents=True, exist_ok=True)
                with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False, indent=1) + "\n")
                os.replace(tmp, path)
            except OSError:
                raise SchemaStoreError("could not write the schema record") from None
        return rec
