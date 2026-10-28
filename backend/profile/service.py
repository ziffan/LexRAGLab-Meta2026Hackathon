"""Ekspor (W7) dan impor (W8) profil berversi (M4.3, DATA-CONTRACTS 11, H-068). Tanpa Model API, tanpa jaringan.

Semua ketergantungan disuntikkan lewat `ProfileDeps` (korpus, setting, chunker, hasil grid tersimpan, skema, jam, direktori).
Urutan impor: bentuk (422) -> korpus/aturan pemuat/teks bersih (409) -> bangun ulang potongan dan bandingkan hash (200).
Impor tidak menulis apa pun (A7); ekspor menulis `profiles/{family}/{setting_id}.json` kecuali replay (A8).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from backend.chunking.model import canonical_json

from .aggregate import held_out_block
from .errors import ProfileError
from .hashing import chunk_rows, clean_text_hash, corpus_hash, loader_rules, profile_chunk_set_hash
from .validate import FAMILIES, PROFILE_VERSION, validate_profile_shape

SETTING_FIELDS = ("family", "chunker", "chunk_size_tokens", "overlap_tokens", "schema_version", "retrieval_mode", "header_b",
                  "budget_tokens")

# (doc, setting_content, schema_record | None, tokenizer) -> potongan (chunk_id, start, end)
Chunker = Callable[[Any, dict[str, Any], "dict[str, Any] | None", Any], Sequence[Any]]


@dataclass
class ProfileDeps:
    docs: Callable[[str], Sequence[Any]]  # dokumen keluarga itu (doc_id, sha256, clean_sha256, loader_rules_version, text)
    settings: Callable[[str], Sequence[Mapping[str, Any]]]  # setting_id + field Setting, per keluarga
    chunker: Chunker
    tokenizer: Any  # punya `.info.name` dan `.info.version`
    config_hash: str
    packing: str
    embedder: Mapping[str, Any] | None  # {name, revision, max_seq_length} dari config; dipakai bila mode dense/hybrid
    grid_metrics: Callable[[str], "tuple[Sequence[Mapping[str, Any]], Sequence[Any]] | None"]  # (butir, ItemMetrics) atau None
    schema: Callable[[str, int], "Mapping[str, Any] | None"]  # SchemaRecord (punya `body`)
    clock: Callable[[], str]
    profiles_dir: Path
    # W66: identitas konfigurasi per keluarga (akta memuat config keluarga + peta unit); None = `config_hash` untuk semua keluarga
    config_hash_for: "Callable[[str], str] | None" = None


@dataclass(frozen=True)
class ExportResult:
    body: bytes
    profile: dict[str, Any]
    path: Path | None  # None bila tidak ditulis (replay)


def make_default_chunker(retrieval_cfg: dict[str, Any], grid_cfg: dict[str, Any]) -> Chunker:
    """Chunker produksi (`backend.chunking.chunk_document`); galat chunker dipetakan ke `validation_failed`."""
    from backend.chunking import ChunkOffsetError, SchemaChunkerError, chunk_document

    def run(doc: Any, setting: dict[str, Any], schema_record: Any, tokenizer: Any) -> Sequence[Any]:
        try:
            return chunk_document(doc, setting, tokenizer=tokenizer, retrieval_cfg=retrieval_cfg, grid_cfg=grid_cfg,
                                  schema_record=schema_record)
        except (ChunkOffsetError, SchemaChunkerError, ValueError) as exc:
            raise ProfileError("validation_failed", f"Chunks could not be rebuilt from the profile setting: {str(exc)[:200]}") from None

    return run


def _setting_content(setting: Mapping[str, Any]) -> dict[str, Any]:
    return {k: setting[k] for k in SETTING_FIELDS}


def _rebuild_hash(deps: ProfileDeps, docs: Sequence[Any], content: dict[str, Any], schema_record: dict[str, Any] | None) -> str:
    by_doc: dict[str, Sequence[Any]] = {}
    for d in docs:
        chunks = list(deps.chunker(d, content, schema_record, deps.tokenizer))
        for c in chunks:
            if not (0 <= c.start < c.end <= len(d.text)):
                raise ProfileError("validation_failed", "Chunker returned offsets outside the clean text.")
        by_doc[d.doc_id] = chunks
    return profile_chunk_set_hash(chunk_rows(docs, by_doc))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def export_profile(deps: ProfileDeps, family: str, setting_id: str | None, *, replay: bool = False) -> ExportResult:
    if family not in FAMILIES:
        raise ProfileError("not_found", f"Unknown family {family!r}.")
    if not setting_id:
        raise ProfileError("invalid_request", "Query parameter setting_id is required.")
    setting = next((dict(s) for s in deps.settings(family) if s.get("setting_id") == setting_id), None)
    if setting is None:
        raise ProfileError("not_found", f"Unknown setting_id {setting_id[:16]!r} for family {family!r}.")
    docs = list(deps.docs(family))
    if not docs:
        raise ProfileError("validation_failed", f"No corpus is loaded for family {family!r}.")
    content = _setting_content(setting)

    held_out = None
    if family == "uupt":  # A11: tanpa hasil grid untuk setting ini -> 422, bukan held_out nol palsu
        grid = deps.grid_metrics(family)
        metrics = [m for m in grid[1] if m.setting_id == setting_id] if grid is not None else []
        if not metrics:
            raise ProfileError("validation_failed", "No grid result for this setting; run the grid first.")
        try:
            held_out = held_out_block(grid[0], metrics)
        except KeyError as exc:
            raise ProfileError("validation_failed", f"Grid result references an unknown item {str(exc)[:40]}.") from None

    schema_body = None
    schema_record = None
    if content["chunker"] == "structure_schema":  # A12: tubuh skema versi setting, bukan versi aktif
        sv = content["schema_version"]
        schema_record = deps.schema(family, sv) if isinstance(sv, int) else None
        if schema_record is None:
            raise ProfileError("validation_failed", f"Schema version {sv!r} for family {family!r} is not available.")
        schema_body = schema_record["body"]

    profile = {
        "profile_version": PROFILE_VERSION, "family": family, "setting": {"setting_id": setting_id, **content},
        "schema": schema_body, "corpus_hash": corpus_hash(docs),
        "config_hash": deps.config_hash_for(family) if deps.config_hash_for is not None else deps.config_hash,
        "chunk_set_hash": _rebuild_hash(deps, docs, content, schema_record),
        "tokenizer": {"name": deps.tokenizer.info.name, "version": deps.tokenizer.info.version},
        "clean_sha256": clean_text_hash(docs), "loader_rules_version": loader_rules(docs), "packing": deps.packing,
        "embedder": (dict(deps.embedder) if deps.embedder is not None and content["retrieval_mode"] != "bm25" else None),
        "held_out": held_out, "created_at": deps.clock(),
    }
    validate_profile_shape(profile)
    body = canonical_json(profile).encode("utf-8")
    path = None
    if not replay:
        path = deps.profiles_dir / family / f"{setting_id}.json"
        _atomic_write(path, body)
    return ExportResult(body, profile, path)


def import_profile(deps: ProfileDeps, profile: Any) -> dict[str, bool]:
    """W8. Hanya memvalidasi dan membangun ulang di memori (A7). `config_hash` dan tokenizer profil tidak menolak (A5, A17)."""
    validate_profile_shape(profile)
    family = profile["family"]
    docs = list(deps.docs(family))
    problems = []
    live_corpus = corpus_hash(docs)
    if live_corpus != profile["corpus_hash"]:
        problems.append(f"Profile corpus hash does not match loaded corpus (profile {profile['corpus_hash'][:12]}, "
                        f"loaded {live_corpus[:12]}).")
    live_rules = loader_rules(docs)
    if live_rules != profile["loader_rules_version"]:
        problems.append(f"Profile was built with loader rules version {profile['loader_rules_version']!r} but the loaded corpus "
                        f"uses loader rules version {live_rules!r}.")
    if clean_text_hash(docs) != profile["clean_sha256"]:
        problems.append("Profile clean text hash does not match the loaded clean text.")
    if problems:
        raise ProfileError("hash_mismatch", " ".join(problems))
    s = profile["setting"]
    schema_record = None
    if s["chunker"] == "structure_schema":  # skema tertanam, bukan penyimpanan (S7)
        schema_record = {"family": family, "schema_version": s["schema_version"], "body": profile["schema"]}
    match = _rebuild_hash(deps, docs, _setting_content(s), schema_record) == profile["chunk_set_hash"]
    return {"ok": match, "chunk_set_hash_matches": match}
