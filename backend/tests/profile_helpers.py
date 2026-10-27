"""Fixture bersama test M4.3 (docs/scenarios/M4.3.md): dokumen mainan, tokenizer `toy-ws`, chunker fake menurut tabel
skenario, butir dan ItemMetrics sintetis. Chunker fake hanya menentukan offset; `chunker_key` dan `chunk_id` dibuat kode nyata
(`backend.chunking.model`). Kunci yang tak ada di tabel melempar galat keras."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.chunking.model import make_chunk_id, make_chunker_key, make_setting_id, sha256_hex
from backend.metrics.types import ItemMetrics
from backend.profile import ProfileDeps
from backend.tests.toy_ws import ToyWs

TOK = ToyWs()
T1, T2 = "2026-10-27T10:00:00Z", "2026-10-27T10:00:05Z"


class ToyWs2(ToyWs):
    info = SimpleNamespace(name="toy-ws", version="2")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Doc:
    doc_id: str
    family: str
    text: str  # teks bersih
    sha256: str  # SHA-256 mentah
    clean_sha256: str
    loader_rules_version: str = "1"


def make_doc(doc_id: str, family: str, raw: str, clean: str | None = None, rules: str = "1") -> Doc:
    clean = raw if clean is None else clean
    return Doc(doc_id, family, clean, sha(raw), sha(clean), rules)


D1T = " ".join(f"a{i}" for i in range(10))
D2T = " ".join(f"b{i}" for i in range(6))
DA_T = "Pasal 1\nAa bb.\nPasal 2\nCc dd.\nPasal 3\nEe ff.\n"
D4_RAW, D4_CLEAN = "Café ab[^1] c› d", "Café ab c› d"
assert (len(D1T), len(D2T), len(DA_T), len(D4_CLEAN)) == (29, 17, 45, 12)

d1 = make_doc("d1", "uupt", D1T)
d2 = make_doc("d2", "uupt", D2T)
d1x = make_doc("d1", "uupt", D1T.replace("a9", "x9"))
d1n = make_doc("d1", "uupt", D1T + "\n")
d3 = make_doc("d3", "uupt", "c0 c1 c2")
d4 = make_doc("d4", "uupt", D4_RAW, D4_CLEAN)
da = make_doc("da", "akta", DA_T)
da_p = make_doc("da", "akta", DA_T.replace("Aa bb.", "Xx bb."))
da2 = make_doc("da2", "akta", "Pasal 9\nZz yy.\n")
d1_swapped = make_doc("d1", "uupt", D2T)  # S5(b): isi bertukar doc_id
d2_swapped = make_doc("d2", "uupt", D1T)

# ---- tabel chunker fake (skenario "Chunker injeksi") ----
TABLE: dict[tuple, dict[str, list[tuple[int, int]]]] = {
    ("fixed_size", 4, 1, "toy-ws/1"): {"d1": [(0, 11), (9, 20), (18, 29)], "d2": [(0, 11), (9, 17)]},
    ("fixed_size", 4, 2, "toy-ws/1"): {"d1": [(0, 11), (6, 17), (12, 23), (18, 29)], "d2": [(0, 11), (6, 17)]},
    ("fixed_size", 4, 1, "toy-ws/2"): {"d1": [(0, 11), (12, 23), (24, 29)], "d2": [(0, 11), (12, 17)]},
    ("fixed_size", 2, 0, "toy-ws/1"): {"d4": [(0, 7), (8, 12)]},
    ("structure_handwritten", "1"): {"d1": [(0, 14), (15, 29)], "d2": [(0, 17)]},
    ("structure_handwritten", "2"): {"d1": [(0, 29)], "d2": [(0, 17)]},
    ("structure_schema", "Pasal"): {"da": [(0, 15), (15, 30), (30, 45)]},
    ("structure_schema", "Isi"): {"da": [(8, 15), (23, 30), (38, 45)]},
}
# Badan skema A format nyata (DATA-CONTRACTS 6: levels[].marker_pattern, default_chunk_level). Hanya chunker FAKE yang membaca
# nama level unit (`unit_name`) untuk memilih baris tabel; chunker produksi diuji terpisah (test_profile_roundtrip, SHOULD-2).
_PASAL = {"order": 1, "name": "Pasal", "marker_pattern": r"^Pasal \d+$", "examples": ["Pasal 1"], "parent_order": None,
          "is_chunk_unit": True}
_ISI = {"order": 2, "name": "Isi", "marker_pattern": r"^[A-Z][a-z]+ [a-z]+\.$", "examples": ["Aa bb."], "parent_order": 1,
        "is_chunk_unit": True}
V1_BODY = {"family": "akta", "levels": [_PASAL], "default_chunk_level": 1, "notes": None}
V2_BODY = {"family": "akta", "levels": [_PASAL, _ISI], "default_chunk_level": 2, "notes": None}


def unit_name(body: dict[str, Any]) -> str:
    return next(lv["name"] for lv in body["levels"] if lv["order"] == body["default_chunk_level"])


SCHEMAS = {("akta", 1): {"family": "akta", "schema_version": 1, "body": V1_BODY},
           ("akta", 2): {"family": "akta", "schema_version": 2, "body": V2_BODY}}


class FakeChunker:
    def __init__(self, parser_version: str = "1"):
        self.parser_version = parser_version
        self.calls = 0
        self.log: list[tuple[str, list[tuple[int, int]]]] = []  # (doc_id, [(start, end)]) tiap panggilan

    def __call__(self, doc: Any, setting: dict[str, Any], schema_record: Any, tokenizer: Any):
        self.calls += 1
        tokkey = f"{tokenizer.info.name}/{tokenizer.info.version}"
        ch = setting["chunker"]
        if ch == "fixed_size":
            key = (ch, setting["chunk_size_tokens"], setting["overlap_tokens"], tokkey)
            params = {"chunk_size_tokens": key[1], "overlap_tokens": key[2], "tokenizer": tokkey, "impl_version": "1"}
        elif ch == "structure_handwritten":
            key = (ch, self.parser_version)
            params = {"parser_version": self.parser_version, "tokenizer": tokkey}
        else:
            body = schema_record["body"]
            key = (ch, unit_name(body))
            params = {"schema_version": schema_record["schema_version"], "schema_hash": sha256_hex(body), "tokenizer": tokkey}
        spans = TABLE[key][doc.doc_id]  # KeyError = galat keras (bukan daftar kosong)
        ck = make_chunker_key(ch, params)
        self.log.append((doc.doc_id, list(spans)))
        return [SimpleNamespace(chunk_id=make_chunk_id(doc.doc_id, s, e, ck), doc_id=doc.doc_id, start=s, end=e, chunker_key=ck)
                for s, e in spans]


# ---- setting ----
def setting(family="uupt", chunker="fixed_size", size=4, ov=1, sv=None, mode="bm25", header_b=False, budget=1000) -> dict[str, Any]:
    content = {"family": family, "chunker": chunker, "chunk_size_tokens": size, "overlap_tokens": ov, "schema_version": sv,
               "retrieval_mode": mode, "header_b": header_b, "budget_tokens": budget}
    return {"setting_id": make_setting_id(content), **content}


P1 = setting()
P2 = setting(ov=2)
PD = setting(mode="dense")
PD2 = setting(mode="hybrid", header_b=True)
PM = setting(size=2, ov=0)
PH = setting(chunker="structure_handwritten", size=None, ov=None)
PA1 = setting(family="akta", chunker="structure_schema", size=None, ov=None, sv=1)
PA2 = setting(family="akta", chunker="structure_schema", size=None, ov=None, sv=2)
UUPT_SETTINGS = [P1, P2, PD, PD2, PM, PH]
AKTA_SETTINGS = [PA1, PA2]

EMBEDDER = {"name": "BAAI/bge-m3", "revision": "5617a9f61b028005a4858fdac845db406aefb181", "max_seq_length": 8192}


# ---- butir dan ItemMetrics (S8) ----
ITEMS = [{"id": "h1", "origin": "operator", "mode": "literal"}, {"id": "h2", "origin": "operator", "mode": "parafrase"},
         {"id": "h3", "origin": "spark_disetujui", "mode": "parafrase"}, {"id": "h4", "origin": "operator", "mode": "literal"},
         {"id": "t1", "origin": "spark_disetujui", "mode": "literal"}, {"id": "t2", "origin": "operator", "mode": "parafrase"}]


def im(item_id, split, sid, gold, covered, retrieved, gold_tok, rank=None, total=0, hit=0) -> ItemMetrics:
    return ItemMetrics(gold_chars=gold, covered_gold_chars=covered, retrieved_tokens=retrieved, gold_tokens_retrieved=gold_tok,
                       rank=rank, parts_total=total, parts_hit=hit, item_id=item_id, setting_id=sid, split=split)


def s8_metrics(sid: str) -> list[ItemMetrics]:
    return [im("h1", "held_out", sid, 10, 10, 8, 4, 1, 1, 1), im("h2", "held_out", sid, 20, 15, 10, 2, 2, 2, 1),
            im("h3", "held_out", sid, 5, 0, 6, 0, None, 1, 0), im("h4", "held_out", sid, 0, 0, 7, 0),
            im("t1", "tune", sid, 10, 10, 10, 9, 1, 1, 1), im("t2", "tune", sid, 10, 10, 10, 8, 1, 1, 1)]


def distractor(sid: str) -> list[ItemMetrics]:
    """Setting lain: semua held-out sempurna (bila bocor, angka S8 berubah)."""
    return [im(i, "held_out", sid, 10, 10, 10, 10, 1, 1, 1) for i in ("h1", "h2", "h3", "h4")]


def make_deps(tmp_path: Path, *, docs: dict[str, list[Doc]] | None = None, chunker: Any = None, tokenizer: Any = TOK,
              metrics: list[ItemMetrics] | None = None, items: list[dict[str, Any]] | None = None, clock: Any = None,
              schemas: dict | None = None, config_hash: str = "c" * 64, embedder: Any = EMBEDDER,
              packing: str = "stop") -> ProfileDeps:
    docs = docs if docs is not None else {"uupt": [d1, d2], "akta": [da]}
    if metrics is None:  # angka S8 untuk setiap setting UU PT
        metrics = [m for st in UUPT_SETTINGS for m in s8_metrics(st["setting_id"])]
    sch = SCHEMAS if schemas is None else schemas
    return ProfileDeps(
        docs=lambda fam: list(docs.get(fam, ())), settings=lambda fam: {"uupt": UUPT_SETTINGS, "akta": AKTA_SETTINGS}.get(fam, []),
        chunker=chunker or FakeChunker(), tokenizer=tokenizer, config_hash=config_hash, packing=packing, embedder=embedder,
        grid_metrics=lambda fam: (items if items is not None else ITEMS, metrics) if fam == "uupt" else None,
        schema=lambda fam, v: sch.get((fam, v)), clock=clock or (lambda: T1), profiles_dir=tmp_path / "profiles")


def tree(root: Path) -> dict[str, bytes]:
    """Isi semua berkas di bawah `root` (untuk perbandingan sebelum/sesudah)."""
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()} if root.exists() else {}
