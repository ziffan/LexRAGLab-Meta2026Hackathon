"""Operasi skema A: induksi lewat Spark (W2), koreksi operator tanpa Spark (W9, fallback berkas H-055), diff antar versi.

Panggilan Spark hanya lewat `SparkClient` (Responses API, strict). Keluaran gagal validasi semantik dicatat di
RunRecord (`status=error`, `semantic_invalid`), tidak di-cache sebagai sah, dan tidak menjadi `SchemaRecord`."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.spark import BatchResult, BudgetExceeded, RunRecord, SparkClient
from backend.spark.runrecord import utc_iso

from .prompt import PromptA, render_input
from .schema import SCHEMA_A, SCHEMA_NAME, schema_hash, validate_body, validate_schema
from .store import SchemaStore

ROLE = "a"
LEVEL_FIELDS = ("name", "marker_pattern", "examples", "parent_order", "is_chunk_unit")
TOP_FIELDS = ("family", "default_chunk_level", "notes")


class SchemaInvalid(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


class ParentNotFound(Exception):
    pass


class SampleHashMismatch(Exception):
    """Teks bersih sampel sekarang berbeda dari yang dipakai induksi (clean_sha256)."""


@dataclass(frozen=True)
class SampleDoc:
    doc_id: str
    text: str
    clean_sha256: str


@dataclass
class InduceOutcome:
    run: RunRecord
    record: dict[str, Any] | None  # SchemaRecord; None bila panggilan galat atau tidak ada record tersimpan (replay)
    error: dict[str, str] | None = None
    created: bool = False  # True bila versi baru ditulis pada panggilan ini


def _now_iso() -> str:
    return utc_iso(time.time())


def sample_meta(samples: list[SampleDoc]) -> list[dict[str, str]]:
    return [{"doc_id": s.doc_id, "clean_sha256": s.clean_sha256} for s in samples]


def make_call(prompt: PromptA, family: str, samples: list[SampleDoc], count_tokens: Callable[[str], int],
              meta: Mapping[str, Any], rejected: list | None = None) -> dict[str, Any]:
    """Argumen `SparkClient.call`. Validator semantik memeriksa family dan contoh terhadap sampel yang dikirim."""
    validate_schema()
    text, _nonce = render_input(prompt, family, [(s.doc_id, s.text) for s in samples])
    texts = [s.text for s in samples]

    def validator(body: dict) -> str | None:
        errs, _v = validate_body(body, family=family, samples=texts)
        if errs and rejected is not None:
            rejected[:] = [(body, errs)]  # keluaran ditolak disimpan pemanggil sebagai berkas `rejected`
        return "; ".join(errs[:5]) if errs else None

    return dict(role=ROLE, prompt_version=prompt.version, prompt_hash=prompt.prompt_hash, input=text,
                schema=SCHEMA_A, schema_name=SCHEMA_NAME, schema_hash=schema_hash(),
                prompt_cache_key=prompt.prompt_cache_key, max_output_tokens=prompt.max_output_tokens,
                est_input=int(count_tokens(text)), validator=validator, meta=dict(meta))


def induce(client: SparkClient, prompt: PromptA, *, family: str, samples: list[SampleDoc],
           count_tokens: Callable[[str], int], meta: Mapping[str, Any], store: SchemaStore,
           replay: bool = False, extra: Mapping[str, Any] | None = None) -> InduceOutcome:
    """Satu panggilan A. Raises `BudgetExceeded` (sebelum jaringan). Cache hit tidak memanggil API dan tidak
    menambah versi: record yang sudah dibuat untuk `cache_key` yang sama dikembalikan. `replay=True` tidak menulis.
    `extra`: bidang tambahan record (pembanding H-100: identitas model); bidang inti selalu menang."""
    rej: list = []
    call = make_call(prompt, family, samples, count_tokens, meta, rej)
    batch: BatchResult = client.run_batch([call])  # proyeksi dulu di dalam; replay tidak memanggil API
    res = batch.results[0]
    if res is None:
        raise BudgetExceeded(f"role a call not run ({batch.stopped_reason or 'stopped'})")
    if res.output is None:
        if rej and not replay and (res.record.error or {}).get("code") == "semantic_invalid":
            body, errs = rej[0]
            store.save_rejected(family, {"run_id": res.record.run_id, "cache_key": res.record.cache_key, "body": body,
                                         "errors": errs, "created_at": _now_iso(), "sample": sample_meta(samples)})
        return InduceOutcome(res.record, None, dict(res.record.error or {"code": "model_error", "message": "call failed"}))
    existing = store.find_by_cache_key(family, res.record.cache_key)
    if existing is not None:
        return InduceOutcome(res.record, existing)
    if replay:
        return InduceOutcome(res.record, None, {"code": "replay_no_stored_run",
                                                "message": "No stored schema record for this request."})
    body = res.parsed
    errs, validation = validate_body(body, family=family, samples=[s.text for s in samples])
    if errs:  # tidak terjadi bila validator klien dipasang; jaga cache lama dari versi kode lain
        return InduceOutcome(res.record, None, {"code": "semantic_invalid", "message": "; ".join(errs[:5])[:300]})
    rec = store.append(family, {
        **dict(extra or {}),
        "source": "spark", "parent_version": None, "body": body, "validation": validation,
        "run_id": res.record.run_id, "created_at": _now_iso(), "operator_note": None,
        "sample": sample_meta(samples), "sample_checked": True, "cache_key": res.record.cache_key})
    return InduceOutcome(res.record, rec, created=True)


def correct(store: SchemaStore, *, family: str, parent_version: int, schema: Any, operator_note: str | None,
            samples: list[str] | None = None) -> dict[str, Any]:
    """Koreksi operator: tanpa Spark. Validasi sama dengan keluaran A (struktur + semantik). Selalu versi baru;
    versi lama dan usulan Spark tidak ditimpa. `samples=None` = pemeriksaan "contoh ada di sampel" dilewati dan
    dicatat (`sample_checked=false`)."""
    parent = store.get(family, parent_version)
    if parent is None:
        raise ParentNotFound(f"no schema version {parent_version} for family {family!r}")
    errs, validation = validate_body(schema, family=family, samples=samples)
    if errs:
        raise SchemaInvalid(errs)
    return store.append(family, {
        "source": "operator", "parent_version": int(parent_version), "body": schema, "validation": validation,
        "run_id": None, "created_at": _now_iso(), "operator_note": operator_note,
        "sample": parent.get("sample", []), "sample_checked": samples is not None, "cache_key": None})


def parent_samples(parent: Mapping[str, Any], load_doc: Callable[[str], Any]) -> list[str] | None:
    """Teks sampel induksi induk untuk pemeriksaan "contoh ada di sampel" pada koreksi. `load_doc(doc_id)` mengembalikan
    objek dengan `.text` dan `.clean_sha256`. None bila induk tanpa sampel atau dokumen tidak bisa dimuat (dicatat
    pemanggil lewat `sample_checked=false`). `clean_sha256` berbeda -> `SampleHashMismatch`."""
    meta = parent.get("sample") or []
    if not meta:
        return None
    texts: list[str] = []
    for m in meta:
        try:
            doc = load_doc(m["doc_id"])
        except Exception:  # noqa: BLE001 - dokumen tak bisa dimuat: pemeriksaan sampel dilewati dan dicatat
            return None
        if doc.clean_sha256 != m["clean_sha256"]:
            raise SampleHashMismatch(m["doc_id"])
        texts.append(doc.text)
    return texts


def load_correction_file(path: Path | str) -> dict[str, Any]:
    """Berkas koreksi operator (H-055): JSON `{"family", "parent_version", "operator_note", "schema"}`.
    Hanya membaca dan memeriksa bentuk; isi koreksi ditulis operator (H-037)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SchemaInvalid([f"correction file unreadable ({type(exc).__name__})"]) from None
    if not isinstance(data, dict) or set(data) - {"family", "parent_version", "operator_note", "schema"}:
        raise SchemaInvalid(["correction file must be an object with keys family, parent_version, operator_note, schema"])
    pv = data.get("parent_version")
    if not isinstance(data.get("family"), str) or not isinstance(pv, int) or isinstance(pv, bool) or pv < 1:
        raise SchemaInvalid(["correction file needs family (string) and parent_version (integer >= 1)"])
    note = data.get("operator_note")
    if note is not None and not isinstance(note, str):
        raise SchemaInvalid(["operator_note must be a string or null"])
    if "schema" not in data:
        raise SchemaInvalid(["correction file has no schema"])
    return {"family": data["family"], "parent_version": pv, "operator_note": note, "schema": data["schema"]}


def diff_bodies(a: Mapping[str, Any], b: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Selisih deterministik `SchemaA` a -> b: `[{order, field, before, after}]`. Level dicocokkan per `order`;
    level yang hanya ada di satu sisi memakai `field = "level"` (nilai: objek level atau null). Urutan: per `order`
    naik (field menurut urutan skema), lalu bidang tingkat atas (`order = null`)."""
    la = {lv["order"]: lv for lv in a.get("levels", [])}
    lb = {lv["order"]: lv for lv in b.get("levels", [])}
    out: list[dict[str, Any]] = []
    for o in sorted(set(la) | set(lb)):
        x, y = la.get(o), lb.get(o)
        if x is None or y is None:
            out.append({"order": o, "field": "level", "before": x, "after": y})
            continue
        for f in LEVEL_FIELDS:
            if x.get(f) != y.get(f):
                out.append({"order": o, "field": f, "before": x.get(f), "after": y.get(f)})
    for f in TOP_FIELDS:
        if a.get(f) != b.get(f):
            out.append({"order": None, "field": f, "before": a.get(f), "after": b.get(f)})
    return out


def diff_versions(store: SchemaStore, family: str, v_from: int, v_to: int) -> dict[str, Any]:
    ra, rb = store.get(family, v_from), store.get(family, v_to)
    if ra is None or rb is None:
        raise ParentNotFound(f"unknown schema version for family {family!r}")
    return {"family": family, "from_version": v_from, "to_version": v_to, "changed": diff_bodies(ra["body"], rb["body"])}


def latest(records: list[dict[str, Any]], source: str) -> dict[str, Any] | None:
    return next((r for r in reversed(records) if r.get("source") == source), None)


def snapshot_view(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    # Keluaran Spark yang ditolak dibaca terpisah lewat `SchemaStore.list_rejected` (bukan SchemaRecord).
    """(`schemas`, `schema_diff`) untuk R3 (API.md 4). `schema_diff` = Spark terbaru vs operator terbaru, atau None
    bila salah satunya belum ada. `boundary_diff` diisi M3.4."""
    sp, op = latest(records, "spark"), latest(records, "operator")
    if sp is None or op is None:
        return records, None
    return records, {"spark_version": sp["schema_version"], "operator_version": op["schema_version"],
                     "changed": diff_bodies(sp["body"], op["body"]), "boundary_diff": []}
