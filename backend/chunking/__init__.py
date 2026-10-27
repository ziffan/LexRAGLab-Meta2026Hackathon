"""Chunker M1.1: struktur tulisan tangan dan ukuran tetap, satu peta alamat (docs/ARCHITECTURE.md §4)."""

from __future__ import annotations

from typing import Any

from backend import config

from .address_map import AddressMap, Rincian, Unit, build_address_map
from .akta_address import schema_address_fn, schema_address_map
from .fixed import chunk_fixed
from .model import NO_MARKER_WARNING, Chunk, ChunkOffsetError, make_chunk_id, make_chunker_key, make_setting_id
from .schema_chunker import (AddressFn, SchemaChunkerError, boundary_diff, chunk_schema, handwritten_address_fn, schema_identity)
from .structure import chunk_structure
from .verify import verify_chunks

__all__ = [
    "AddressMap", "Chunk", "ChunkOffsetError", "NO_MARKER_WARNING", "Rincian", "Unit",
    "build_address_map", "chunk_fixed", "chunk_structure", "chunk_schema", "boundary_diff", "schema_identity",
    "handwritten_address_fn", "schema_address_fn", "schema_address_map", "AddressFn", "SchemaChunkerError", "chunk_document", "load_retrieval_config",
    "make_chunk_id", "make_chunker_key", "make_setting_id", "verify_chunks",
]


def load_retrieval_config(config_dir: Any = None) -> dict[str, Any]:
    return config.load("retrieval", config_dir)


def chunk_document(doc: Any, setting: dict[str, Any], *, tokenizer: Any = None, retrieval_cfg: dict[str, Any] | None = None,
                   grid_cfg: dict[str, Any] | None = None, schema_record: Any = None) -> list[Chunk]:
    """Chunk `doc` menurut field `chunker` pada `setting` (DATA-CONTRACTS §10), lalu verifikasi offset."""
    chunker = setting["chunker"]
    if chunker == "structure_handwritten":
        chunks = chunk_structure(doc, retrieval_cfg=retrieval_cfg, tokenizer=tokenizer)
    elif chunker == "structure_schema":
        if schema_record is None:
            raise ValueError("chunker structure_schema needs a schema_record (SchemaRecord of schema A)")
        chunks = chunk_schema(doc, schema_record, retrieval_cfg=retrieval_cfg, tokenizer=tokenizer)
    elif chunker == "fixed_size":
        chunks = chunk_fixed(doc, size=setting["chunk_size_tokens"], overlap=setting["overlap_tokens"],
                             retrieval_cfg=retrieval_cfg, tokenizer=tokenizer)
    else:
        raise ValueError(f"chunker not available in M1.1: {chunker!r}")
    verify_chunks(doc, chunks, set((retrieval_cfg if retrieval_cfg is not None else config.load("retrieval"))["scope_sections"]))
    return chunks
