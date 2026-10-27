"""Skema A sebagai sumbu grid (M3.4; H-037, H-072, H-074). Pembacaan `SchemaRecord`, versi aktif, status persetujuan.

- Versi aktif per keluarga = `SchemaRecord` operator dengan versi tertinggi; bila belum ada koreksi operator, record Spark
  dengan versi tertinggi. Alasan: koreksi operator (H-037) menang atas keluaran model; tanpa koreksi, usulan Spark dipakai
  untuk run uji.
- "Disetujui" (`schema_approved`) = HANYA record `source = "operator"` (koreksi W9 atau berkas fallback H-055; H-075).
  Jalur flag `operator_approved` dihapus: menyetujui v1 Spark tanpa perubahan = operator menyimpan salinan lewat W9 dengan
  `operator_note`. Record Spark tak pernah disetujui, apa pun isi field lainnya.
  Run dengan skema belum disetujui boleh untuk uji, tetapi amplop grid menandainya `schema_approved: false`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.chunking.schema_chunker import schema_identity
from backend.grid.types import Setting, compute_setting_id, setting_content

CHUNKER = "structure_schema"
APPROVAL_RULE = "source == operator (H-075)"


def is_approved(record: Mapping[str, Any]) -> bool:
    return record.get("source") == "operator"


def pick_active(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for src in ("operator", "spark"):
        got = [r for r in records if r.get("source") == src]
        if got:
            return max(got, key=lambda r: r["schema_version"])
    return None


@dataclass(frozen=True)
class SchemaBinding:
    """Rekaman skema satu keluarga yang boleh dipakai grid. Tanpa jaringan; hanya membaca."""

    family: str
    records: tuple[Mapping[str, Any], ...]

    @classmethod
    def from_store(cls, runs_dir: Path | str, family: str) -> "SchemaBinding":
        from backend.schema_a.store import SchemaStore

        return cls(family, tuple(SchemaStore(runs_dir).list(family)))

    def active(self) -> Mapping[str, Any] | None:
        return pick_active(self.records)

    def resolve(self, version: int | None) -> Mapping[str, Any] | None:
        """Record untuk `Setting.schema_version`; `None` = versi aktif."""
        if version is None:
            return self.active()
        return next((r for r in self.records if r["schema_version"] == version), None)

    def identity(self) -> dict[str, Any] | None:
        """Komponen `config_hash` grid: versi dan hash isi skema aktif. None bila tak ada skema (hash grid tak berubah)."""
        act = self.active()
        return None if act is None else {**schema_identity(act), "source": act.get("source")}

    def describe(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return {**schema_identity(record), "source": record.get("source"), "schema_approved": is_approved(record),
                "approval_rule": APPROVAL_RULE}


def bind_schema_versions(settings: Sequence[Setting], binding: SchemaBinding | None) -> list[Setting]:
    """Setting `structure_schema` ber-`schema_version = None` diberi versi aktif konkret dan `setting_id` dihitung ulang
    (versi skema berbeda = potongan berbeda = setting berbeda). Tanpa binding atau skema aktif: tak berubah."""
    act = binding.active() if binding is not None else None
    out: list[Setting] = []
    for s in settings:
        if s.chunker == CHUNKER and s.schema_version is None and act is not None:
            s = replace(s, schema_version=act["schema_version"])
            s = replace(s, setting_id=compute_setting_id(setting_content(s)))
        out.append(s)
    return out
