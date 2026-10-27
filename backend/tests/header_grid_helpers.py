"""Pembantu test M3.2 (header B sebagai sumbu grid): dokumen/potongan sintetis, store header palsu, pipeline sungguhan
dengan potongan disuntik (ranking `C` diberikan). Tanpa Model API, tanpa jaringan."""

from __future__ import annotations

import math
from fractions import Fraction
from types import SimpleNamespace
from typing import Any, Sequence

from backend.grid.headers import HeaderBinding, MemoryHeaderStore
from backend.grid.types import GridItem, Setting
from backend.pipeline.pipeline import ChunkSet, Pipeline, chunk_params

from .toy_ws import T, TOK, ToyWs

RCFG = {"recall": {"k": 1}, "scope_sections": [], "bm25": {"k1": 1.5, "b": 0.75, "stemming": False, "stopwords": False},
        "hybrid": {"top_n": 0, "k_rrf": 60}}
F = Fraction


class Toy2(ToyWs):
    """Tokenizer kedua `toy-2` v1 (S3 varian b): hanya biaya, `ceil(code point / 2)` tanpa strip. Offset dipinjam dari
    `toy-ws` supaya metrik gold bisa dihitung (presisi tidak di-assert). `calls` = spy semua string yang dihitung."""

    class _Info:
        name, version = "toy-2", "1"

    info = _Info()

    def __init__(self) -> None:
        self.calls: list[str] = []

    def count(self, text: str) -> int:
        self.calls.append(text)
        return math.ceil(len(text) / 2)


def doc_of(text: str = T, clean: str = "X") -> Any:
    return SimpleNamespace(text=text, clean_sha256=clean, doc_id="t", metadata={}, sections=[])


def chunk(cid: str, span: tuple[int, int], key: str = "kT") -> Any:
    return SimpleNamespace(chunk_id=cid, start=span[0], end=span[1], chunker_key=key)


def setting(sid: str, *, header: bool, budget: int = 2000, mode: str = "bm25", chunker: str = "structure_handwritten",
            size: int | None = None, overlap: int | None = None, family: str = "akta") -> Setting:
    return Setting(sid, family, chunker, size, overlap, None, mode, header, budget)


def twin(s: Setting, *, budget: int | None = None) -> Setting:
    """Kembaran header-on dari `s` (atau sebaliknya): beda hanya `header_b` dan `setting_id`."""
    from dataclasses import replace

    return replace(s, setting_id=s.setting_id + "+", header_b=True, budget_tokens=budget or s.budget_tokens)


def header_records(headers: dict[str, str], *, granularity: str = "ayat", run_id: str = "b1", tokens_local: int | None = None) -> dict:
    return {cid: {"chunk_id": cid, "header": h, "granularity": granularity, "prompt_version": "v1",
                  "tokens_local": tokens_local if tokens_local is not None else len(h.split()), "run_id": run_id}
            for cid, h in headers.items()}


def make_store(headers: dict[str, str], *, granularity: str = "ayat", run_clean: str = "X", run_id: str = "b1",
               tokens_local: int | None = None) -> MemoryHeaderStore:
    return MemoryHeaderStore(header_records(headers, granularity=granularity, run_id=run_id, tokens_local=tokens_local),
                             {run_id: run_clean})


def make_pipe(doc: Any, sets: Sequence[tuple[Setting, dict[str, tuple[int, int]]]], store: MemoryHeaderStore | None, *,
              packing: str = "stop", granularity: str = "ayat", scope: str = "all", tokenizer: Any = TOK,
              rcfg: dict | None = None) -> Pipeline:
    """Pipeline sungguhan; potongan tiap (setting, {chunk_id: span}) disuntik ke cache potongan (kunci `chunk_params`)."""
    binding = HeaderBinding(store, granularity, scope, "ph", "m") if store is not None else None
    pipe = Pipeline(doc, tokenizer=tokenizer, retrieval_cfg=rcfg or RCFG, grid_cfg={"packing": {"rule": packing}}, headers=binding)
    for s, spans in sets:
        chunks = [chunk(cid, sp, key="k" + s.chunker) for cid, sp in spans.items()]
        pipe._sets[chunk_params(s)] = ChunkSet(chunks, "k" + s.chunker, {c.chunk_id: c for c in chunks}, [], None)
    return pipe


def item(iid: str = "i1", gold: Sequence[tuple[int, int]] = (), query: str = "") -> GridItem:
    return GridItem(iid, "akta", "operator", "literal", gold_spans=tuple(gold), query=query)


def account(pipe: Pipeline, s: Setting, c: Sequence[str], gold: Sequence[tuple[int, int]] = ()) -> Any:
    return pipe.account(s, item(gold=gold), [(cid, 1.0) for cid in c])


def source_tokens(rt: Any, doc: Any, tok: Any = TOK) -> int:
    return sum(tok.count(doc.text[p.start:p.end]) for p in rt.packed)


def header_tokens(rt: Any, doc: Any, tok: Any = TOK) -> int:
    """A9: token header per butir = retrieved_tokens - sum tok(teks sumber P)."""
    return rt.metrics.retrieved_tokens - source_tokens(rt, doc, tok)


def packed_ids(rt: Any) -> tuple[str, ...]:
    return tuple(p.chunk_id for p in rt.packed)
