"""W56 / M4.1 (H-090): peta unit akta dari skema A aktif di `Pipeline`. Skenario `docs/scenarios/M4.1-akta-unitmap.md` S1-S14
(semua "Dipilih" P1-P11 disetujui operator). Dokumen mainan T "Akta 91" (sintetis), tokenizer toy-ws, encoder palsu; tanpa
jaringan, GPU, Model API, `data/`, atau `runs/` repo. Setiap S-nn mengunci angka persis dari skenario."""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from backend import config
from backend.answer.context import ContextEntry, build_context, entry_labels, unit_label
from backend.answer.prompt import load_prompt
from backend.chunking import build_address_map
from backend.chunking.akta_address import schema_address_map
from backend.grid.expand import expand_grid
from backend.grid.schemas import SchemaBinding, bind_schema_versions
from backend.grid.types import GridItem
from backend.metrics.item import compute_item_metrics, gold_parts, recall_at_k_from_parts
from backend.metrics.types import RankedChunk
from backend.pipeline.grid_run import (UNIT_MAP_CONFIG, GridRunError, _quality_doc, make_plan, pipeline_config_hash, quality_for,
                                       run_family_grid)
from backend.pipeline.multi import MultiDocPipeline
from backend.pipeline.pipeline import Pipeline, SettingNotAvailable, unavailable_reason
from backend.quality.boundaries import boundary_counts
from backend.quality.types import ChunkSpan
from backend.verifier import units_from_address_map
from backend.verifier.config import VerifierConfig
from backend.verifier.verify import verify_citation

from ._chunk_util import ToyWs, make_doc, u_doc
from .pipeline_fakes import FakeEncoder, toy_config_dir, write_toy_butir

# ---- dokumen mainan T (skenario "Dokumen mainan") ----------------------------------------------------------------
T = ("Salinan.\nAKTA TOY\nNotaris Budi.\nMenghadap saya Ani.\nPasal 1\n(1) Para pihak sepakat.\n(2) Kewajiban:\n"
     "a. membayar;\nb. menyerahkan.\nPasal 2\nHarga tetap.\nPENUTUP\nSelesai.\n")
assert len(T) == 166 and [i for i, c in enumerate(T) if c == "\n"] == [8, 17, 31, 51, 59, 83, 98, 111, 127, 135, 148, 156, 165]

P1_V2 = r"^Pasal\s+\d+\s*$|^(?P<kepala_akta>AKTA TOY)$|^(?P<komparisi>Menghadap saya)\b|^(?P<penutup_akta>PENUTUP)\s*$"
P1_V1 = r"^Pasal\s+\d+\s*$|^(?P<kepala_akta>AKTA TOY)$|^(?P<penutup_akta>PENUTUP)\s*$"
P1_V2B = r"^Pasal\s+\d+\s*$|^(?P<kepala_akta>AKTA TOY)$|^(?P<penutup_akta>PENUTUP)\s*$|^(?P<komparisi>Menghadap saya)\b"  # isi beda


def lv(order, name, parent, pattern, unit=False):
    return {"order": order, "name": name, "parent_order": parent, "marker_pattern": pattern, "is_chunk_unit": unit, "examples": []}


def rec(version, source, p1):
    return {"family": "akta", "schema_version": version, "source": source, "parent_version": None,
            "body": {"family": "akta", "default_chunk_level": 1,
                     "levels": [lv(1, "Pasal", None, p1, True), lv(2, "Ayat", 1, r"^\(\d+\)"), lv(3, "Huruf", 2, r"^[a-z]\.")]}}


V2, V1 = rec(2, "operator", P1_V2), rec(1, "spark", P1_V1)
V3_SPARK, V3_OP = rec(3, "spark", P1_V1), rec(3, "operator", P1_V2B)  # v3 Spark berpola beda dari v2 (tanpa Komparisi)
SCHEMA_N = rec(3, "operator", r"^ZZZ\d+$")


def bind(*records):
    return SchemaBinding("akta", tuple(records))


def deed(text=T, prefix="Akta 91", doc_id="akta-91"):
    return replace(make_doc(text, [("batang_tubuh", 0, len(text))], prefix=prefix, doc_id=doc_id), family="akta",
                   loader_rules_version="akta-1")


@pytest.fixture(scope="module")
def cfg(tmp_path_factory):
    return toy_config_dir(tmp_path_factory.mktemp("w56cfg"))


@pytest.fixture(scope="module")
def cfgs(cfg):
    return config.load("retrieval", cfg), config.load("grid", cfg)


def pipe_for(cfgs, binding, doc=None):
    r, g = cfgs
    return Pipeline(doc or deed(), tokenizer=ToyWs(), retrieval_cfg=r, grid_cfg=g, schemas=binding, encoder=FakeEncoder())


def setting(cfgs, chunker, binding=None, version=None, mode="bm25"):
    ss = bind_schema_versions(expand_grid(cfgs[1], "akta"), binding)
    s = next(x for x in ss if x.chunker == chunker and x.retrieval_mode == mode and not x.header_b)
    return replace(s, schema_version=version) if version is not None else s


V2_UNITS = [(9, 31), (32, 51), (52, 127), (128, 148), (149, 165)]
V2_ADDR = ["Akta 91 › Kepala Akta", "Akta 91 › Komparisi", "Akta 91 › Pasal 1", "Akta 91 › Pasal 2", "Akta 91 › Penutup Akta"]
RINCIAN = [("Akta 91 › Pasal 1 › ayat (1)", 60, 83), ("Akta 91 › Pasal 1 › ayat (2)", 84, 127),
           ("Akta 91 › Pasal 1 › ayat (2) › huruf a", 99, 111), ("Akta 91 › Pasal 1 › ayat (2) › huruf b", 112, 127)]


def simple(amap):
    return [(u.address, u.start, u.end) for u in amap.units]


# ---- S1 -----------------------------------------------------------------------------------------------------------
def test_s1_unit_map_v2_exact():
    amap = schema_address_map(deed(), V2)
    assert simple(amap) == [(a, s, e) for a, (s, e) in zip(V2_ADDR, V2_UNITS)]
    assert [T[s:e] for s, e in V2_UNITS] == ["AKTA TOY\nNotaris Budi.", "Menghadap saya Ani.", T[52:127], "Pasal 2\nHarga tetap.", "PENUTUP\nSelesai."]
    assert T[52:127].startswith("Pasal 1") and T[52:127].endswith("b. menyerahkan.")
    pasal1 = amap.units[2]
    assert [(r.address, r.start, r.end) for r in pasal1.children] == RINCIAN
    assert all(u.children == () for i, u in enumerate(amap.units) if i != 2)
    covered = {i for u in amap.units for i in range(u.start, u.end)}
    assert not covered & {0, 8, 31, 51, 127, 148, 165} and not covered & set(range(0, 9))


def test_s1_v1_and_n_and_legacy_maps():
    v1 = schema_address_map(deed(), V1)
    assert simple(v1) == [("Akta 91 › Kepala Akta", 9, 51), ("Akta 91 › Pasal 1", 52, 127), ("Akta 91 › Pasal 2", 128, 148),
                          ("Akta 91 › Penutup Akta", 149, 165)]
    assert schema_address_map(deed(), SCHEMA_N).units == []
    d = deed()
    legacy = build_address_map(d.text, d.sections, "Akta 91", {"batang_tubuh"}, {"batang_tubuh": "Batang Tubuh"})
    assert simple(legacy) == [("Akta 91 › Batang Tubuh", 0, 165)]


# ---- S2 -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("chunker", ["structure_schema", "fixed_size", "structure_handwritten"])
def test_s2_pipeline_uses_active_schema_map_for_every_setting(cfgs, chunker):
    p = pipe_for(cfgs, bind(V2))
    cs = p.chunk_set(setting(cfgs, chunker, bind(V2)))
    assert cs.units == V2_UNITS and cs.unit_map_kind == "schema"
    assert simple(cs.amap) == simple(schema_address_map(deed(), V2))
    if chunker == "structure_schema":  # potongan skema yang persis satu unit beralamat sama dengan unitnya
        assert [(c.start, c.end, c.address) for c in cs.chunks] == [(s, e, a) for a, (s, e) in zip(V2_ADDR, V2_UNITS)]


def test_s2c_pinned_non_active_version_keeps_active_map(cfgs):
    b = bind(V1, V2)
    p = pipe_for(cfgs, b)
    cs = p.chunk_set(setting(cfgs, "structure_schema", b, version=1))
    assert [(c.start, c.end) for c in cs.chunks] == [(9, 51), (52, 127), (128, 148), (149, 165)]  # potongan v1
    assert cs.units == V2_UNITS and simple(cs.amap) == simple(schema_address_map(deed(), V2))  # peta v2 aktif (P11)
    ov = cs.amap.overlapping(9, 51)
    assert [u.address for u in ov] == V2_ADDR[:2]  # potongan v1 [9,51) melintasi dua unit v2
    addr, _lv, _w = cs.amap.address_for_range(9, 51, "batang_tubuh", "Akta 91", "Batang Tubuh")
    assert addr == "Akta 91 › Kepala Akta – Akta 91 › Komparisi"
    gone = replace(setting(cfgs, "structure_schema", b), schema_version=7)  # pin ke versi yang tidak ada
    assert unavailable_reason(gone, schemas=b) is not None
    with pytest.raises(SettingNotAvailable):
        p.chunk_set(gone)


# ---- S3 -----------------------------------------------------------------------------------------------------------
def test_s3_uupt_pipeline_unchanged(cfgs):
    r, g = cfgs
    for binding in (None, SchemaBinding("uupt", ())):
        p = Pipeline(u_doc(), tokenizer=ToyWs(), retrieval_cfg=r, grid_cfg=g, schemas=binding, encoder=FakeEncoder())
        s = next(x for x in expand_grid(g, "uupt") if x.chunker == "fixed_size")
        cs = p.chunk_set(s)
        want = build_address_map(u_doc().text, u_doc().sections, "UU 40/2007", set(r["scope_sections"]),
                                 dict(r["chunking"]["section_labels"]))
        assert simple(cs.amap) == simple(want) and cs.units == [(u.start, u.end) for u in want.in_sections(set(r["scope_sections"]))]
        assert cs.unit_map_kind == "parser" and not p.is_akta
        m = p(s, [GridItem("x", "uupt", "operator", "literal", "h", ((12, 24),), "Aaa bbb")])[0]
        assert m.gold_chars_outside_units is None  # UU PT tidak membawa field P7


def uupt_world(tmp_path, cfg):
    doc = u_doc()
    butir = tmp_path / "butir"
    write_toy_butir(butir, doc.clean_sha256)
    return doc, butir


def test_s3_uupt_hash_and_envelope_unchanged(tmp_path, cfg):
    doc, butir = uupt_world(tmp_path, cfg)
    kw = dict(doc=doc, tokenizer=ToyWs(), butir_dir=butir, runs_dir=tmp_path / "runs", config_dir=cfg, create_split=False)
    plan = make_plan("uupt", **kw)
    assert set(plan.cfgs) == {"grid", "retrieval", "tokenizer", "corpus"} and UNIT_MAP_CONFIG not in plan.cfgs
    old_formula = pipeline_config_hash(plan.cfgs, ToyWs().info, None, [])  # tanpa unit_map = rumus sebelum W56
    assert plan.config_hash == old_formula
    with_schema = make_plan("uupt", schemas=SchemaBinding("uupt", ()), **kw)
    assert with_schema.config_hash == plan.config_hash and with_schema.key == plan.key


def fixed_only_cfg(src: Path, dest: Path, extra_unit_version: int | None = None) -> Path:
    cfg = toy_config_dir(dest)
    g = cfg / "grid.toml"
    t = g.read_bytes().decode("utf-8")
    t = (t.replace('chunkers = ["structure_handwritten", "structure_schema", "fixed_size"]', 'chunkers = ["fixed_size"]')
         .replace('retrieval_modes = ["dense", "bm25", "hybrid"]', 'retrieval_modes = ["bm25"]').replace("header_b = [false, true]", "header_b = [false]")
         .replace("default_tokens = 2000", "default_tokens = 40").replace("comparison_tokens = [1000]", "comparison_tokens = [20]"))
    g.write_bytes(t.encode("utf-8"))
    if extra_unit_version is not None:
        u = cfg / f"{UNIT_MAP_CONFIG}.toml"
        u.write_bytes(u.read_bytes().replace(b"unit_map_version = 1", f"unit_map_version = {extra_unit_version}".encode()))
    return cfg


def test_s3_control_uupt_fixed_only_unchanged_akta_fixed_only_changes(tmp_path):
    cfg = fixed_only_cfg(None, tmp_path / "cfg")
    doc, butir = uupt_world(tmp_path, cfg)
    ukw = dict(tokenizer=ToyWs(), butir_dir=butir, runs_dir=tmp_path / "runs", config_dir=cfg)
    plain = make_plan("uupt", doc=doc, create_split=False, **ukw)
    bound = make_plan("uupt", doc=doc, create_split=False, schemas=SchemaBinding("uupt", (rec(1, "spark", P1_V1),)), **ukw)
    assert bound.config_hash == plain.config_hash == pipeline_config_hash(plain.cfgs, ToyWs().info, None, [])
    res = run_family_grid("uupt", doc=doc, runs_dir=tmp_path / "runs", encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb",
                          schemas=SchemaBinding("uupt", (rec(1, "spark", P1_V1),)), **{k: v for k, v in ukw.items() if k != "runs_dir"})
    assert res.record["config_hash"] == plain.config_hash
    env = res.envelope
    assert "unit_map" not in env and "recall_unit" not in env and all("recall_unit" not in q and "unit_map_kind" not in q for q in env["quality"])
    assert all("gold_chars_outside_units" not in m for m in env["metrics"])
    assert {q["items_scope"] for q in env["quality"]} == {"held_out"}  # UU PT: [quality].recall_items tidak berubah
    # grid akta fixed_size-saja: hash BERUBAH terhadap rumus lama dan memuat blok unit_map
    d = deed()
    akw = dict(docs=[d], tokenizer=ToyWs(), runs_dir=tmp_path / "aruns", config_dir=cfg, create_split=False)
    abut = tmp_path / "abutir"
    write_akta(abut, d, [("i1", [(60, 83)], "Para pihak")])
    ap = make_plan("akta", butir_dir=abut, schemas=bind(V2), **akw)
    assert ap.config_hash != pipeline_config_hash(ap.cfgs, ToyWs().info, None, [])
    assert UNIT_MAP_CONFIG in ap.cfgs


# ---- helper grid akta -----------------------------------------------------------------------------------------------
def write_akta(directory: Path, docs, rows, version: int = 1):
    """rows = [(id, gold_spans, query)] atau (id, gold, query, doc_id); `docs` = satu dokumen atau dict doc_id -> doc."""
    directory.mkdir(parents=True, exist_ok=True)
    dd = docs if isinstance(docs, dict) else {docs.doc_id: docs}
    lines = []
    for row in rows:
        iid, spans, q, *rest = row
        did = rest[0] if rest else next(iter(dd))
        lines.append(json.dumps({"clean_sha256": dd[did].clean_sha256, "doc_id": did, "family": "akta", "id": iid, "mode": "literal",
                                 "origin": "operator", "query": q, "gold_spans": [{"start": s, "end": e} for s, e in spans]}, sort_keys=True))
    p = directory / f"akta.v{version}.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def grid(tmp_path, cfg, binding, rows, docs=None, name="r"):
    d = deed()
    docs = docs or {d.doc_id: d}
    butir = tmp_path / f"b-{name}"
    write_akta(butir, docs, rows)
    return run_family_grid("akta", docs=list(docs.values()), tokenizer=ToyWs(), runs_dir=tmp_path / f"runs-{name}", butir_dir=butir,
                           config_dir=cfg, encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb", schemas=binding)


# ---- S4 -----------------------------------------------------------------------------------------------------------
def r1(start, end):
    return [RankedChunk(start, end, "", "c")]


def recall1(gold, top, units=V2_UNITS):
    return recall_at_k_from_parts(gold_parts(gold, units), r1(*top), 1)


def test_s4a_gold_across_two_units():
    assert gold_parts([(100, 140)], V2_UNITS) == [(100, 127), (128, 140)]  # LF 127 tidak masuk
    assert recall1([(100, 140)], (52, 127)) == Fraction(1, 2)
    assert recall1([(100, 140)], (52, 148)) == Fraction(2, 2)
    old = [(0, 165)]
    assert gold_parts([(100, 140)], old) == [(100, 140)] and recall1([(100, 140)], (52, 127), old) == 0
    assert recall1([(100, 140)], (52, 148), old) == 1


def test_s4b_gold_outside_every_unit_is_null():
    for g in ([(127, 128)], [(0, 8)]):
        assert gold_parts(g, V2_UNITS) == [] and recall1(g, (52, 127)) is None
    assert gold_parts([(127, 128)], [(0, 165)]) == [(127, 128)] and gold_parts([(0, 8)], [(0, 165)]) == [(0, 8)]  # peta lama
    m = compute_item_metrics(T, [(127, 128)], r1(52, 127), 40, ToyWs(), k=1, units=V2_UNITS, report_outside=True)
    assert m.recall_at_k is None and m.parts_total == 0 and m.gold_chars_outside_units == 1


def test_s4c_ayat_does_not_split_gold():
    assert gold_parts([(60, 100)], V2_UNITS) == [(60, 100)]  # satu bagian (P3)
    assert recall1([(60, 100)], (52, 83)) == 0


def test_s4d_gold_partly_outside_units():
    assert gold_parts([(0, 40)], V2_UNITS) == [(9, 31), (32, 40)]  # 22 + 8 karakter
    m = compute_item_metrics(T, [(0, 40)], r1(9, 31), 40, ToyWs(), k=1, units=V2_UNITS, report_outside=True)
    assert (m.parts_total, m.parts_hit, m.recall_at_k, m.gold_chars_outside_units) == (2, 1, Fraction(1, 2), 10)  # [0,9) + [31,32)
    m0 = compute_item_metrics(T, [(0, 40)], r1(9, 31), 40, ToyWs(), k=1, units=V2_UNITS)
    assert m0.gold_chars_outside_units is None  # tanpa report_outside (UU PT): tak dilaporkan


def test_s4e_gold_across_pasal_and_other_unit_follows_same_mechanism():
    assert gold_parts([(20, 60)], V2_UNITS) == [(20, 31), (32, 51), (52, 60)]  # Kepala Akta, Komparisi, Pasal 1


def test_s4_pipeline_account_reports_outside_for_akta(cfgs):
    p = pipe_for(cfgs, bind(V2))
    s = setting(cfgs, "structure_schema", bind(V2))
    cs = p.chunk_set(s)
    first = cs.chunks[0]
    ranking = [(c.chunk_id, 1.0 / (i + 1)) for i, c in enumerate(cs.chunks)]
    item = GridItem("g", "akta", "operator", "literal", "h", ((0, 40),), "q", doc_id="akta-91")
    got = p.account(s, item, ranking).metrics
    assert (got.gold_chars_outside_units, got.parts_total) == (10, 2) and first.start == 9
    # K=5 (config): kedua bagian ada di dua potongan berbeda (Kepala Akta, Komparisi) -> 2 bagian, masing-masing utuh di salah satu potongan
    assert got.parts_hit == 2


# ---- S5 -----------------------------------------------------------------------------------------------------------
def test_s5_boundary_coherence_with_unit_map(cfgs):
    p = pipe_for(cfgs, bind(V2))
    qd = _quality_doc(p, setting(cfgs, "structure_schema", bind(V2)))
    assert qd.structure_bounds == frozenset({0, 166} | {9, 32, 52, 128, 149} | {31, 51, 127, 148, 165})
    spans = (ChunkSpan(0, 98), ChunkSpan(98, 149), ChunkSpan(149, 166))
    abbr = config.load("retrieval")["quality"]["abbreviations"]
    assert T[97] == ":" and T[148] == "\n"
    assert boundary_counts(T, spans, qd.structure_bounds, abbr) == (1, 2)
    legacy = _quality_doc(pipe_for(cfgs, None), setting(cfgs, "structure_handwritten"))
    assert legacy.structure_bounds == frozenset({0, 165, 166})
    assert boundary_counts(T, spans, legacy.structure_bounds, abbr) == (0, 2)


# ---- S6 -----------------------------------------------------------------------------------------------------------
def test_s6_context_labels(cfgs):
    amap = pipe_for(cfgs, bind(V2)).chunk_set(setting(cfgs, "fixed_size", bind(V2))).amap
    lab = lambda a: f"[ALAMAT UNIT: {a}]\n"  # noqa: E731
    assert unit_label("Akta 91 › Pasal 1") == lab("Akta 91 › Pasal 1")
    a = entry_labels(amap, 100, 150)
    assert a == ((0, lab("Akta 91 › Pasal 1")), (28, lab("Akta 91 › Pasal 2")), (49, lab("Akta 91 › Penutup Akta")))
    e = ContextEntry("c", "x", T[100:150], 1, 1, a)
    assert e.shown() == lab("Akta 91 › Pasal 1") + T[100:128] + lab("Akta 91 › Pasal 2") + T[128:149] + lab("Akta 91 › Penutup Akta") + T[149:150]
    assert entry_labels(amap, 90, 135) == ((0, lab("Akta 91 › Pasal 1")), (38, lab("Akta 91 › Pasal 2")))
    assert entry_labels(amap, 52, 127) == () and entry_labels(amap, 84, 127) == ()
    assert ContextEntry("c", "x", T[52:127], 1, 1, ()).shown() == T[52:127]
    assert entry_labels(amap, 0, 60) == ((9, lab("Akta 91 › Kepala Akta")), (32, lab("Akta 91 › Komparisi")), (52, lab("Akta 91 › Pasal 1")))
    assert entry_labels(amap, 0, 20) == ()
    # peta lama: potongan multi-Pasal tak berlabel (gejala I-63)
    old = pipe_for(cfgs, None).chunk_set(setting(cfgs, "fixed_size")).amap
    assert entry_labels(old, 100, 150) == () and entry_labels(old, 90, 135) == ()


def test_s6d_labels_do_not_change_budget(cfgs):
    b = bind(V2)
    p = pipe_for(cfgs, b)
    s = replace(setting(cfgs, "fixed_size", b), budget_tokens=40)
    item = GridItem("q", "akta", "operator", "literal", "h", ((60, 83),), "Notaris Budi Menghadap Ani", doc_id="akta-91")
    b1 = build_context(p, s, item, load_prompt("v1"))
    b2 = build_context(p, s, item, load_prompt("v2"))
    assert b1.packed_tokens == b2.packed_tokens and b1.chunk_ids == b2.chunk_ids
    assert any(e.labels for e in b2.entries) and all(e.labels == () for e in b1.entries)
    assert all(e.text == T[p.chunk_set(s).by_id[e.chunk_id].start:p.chunk_set(s).by_id[e.chunk_id].end] for e in b2.entries)


# ---- S7 / S8 ------------------------------------------------------------------------------------------------------
VCFG = VerifierConfig(theta=Fraction(95, 100), d_max=3)


def cite(units, addr, quote):
    return verify_citation({"alamat": addr, "teks": quote}, units, [], VCFG).result


@pytest.fixture(scope="module")
def units_v2(cfgs):
    cs = pipe_for(cfgs, bind(V2)).chunk_set(setting(cfgs, "fixed_size", bind(V2)))
    return units_from_address_map(cs.amap, T)


def test_s7_v5_over_unit_map(units_v2):
    assert len(units_v2) == 9 and set(units_v2) == set(V2_ADDR) | {a for a, _s, _e in RINCIAN}
    for addr, quote in [("Akta 91 › Pasal 1", "Pasal 1"), ("Akta 91 › Pasal 1 › ayat (2) › huruf a", "a. membayar;"),
                        ("Akta 91 › Komparisi", "Menghadap saya Ani."), ("Akta 91 › Kepala Akta", "AKTA TOY"),
                        ("Akta 91 › Penutup Akta", "Selesai.")]:
        r = cite(units_v2, addr, quote)
        assert (r.exists, r.faithful, r.faithful_score) == ("lulus", "lulus", None), addr
    for addr in ["Akta 91 › Batang Tubuh", "Akta 91 › Pasal 1 › ayat (3)", "Akta 91 › Pasal 1 – Akta 91 › Pasal 2", "Akta 92 › Pasal 1",
                 "Akta 91 › Komparisi › ayat (1)"]:
        r = cite(units_v2, addr, "Pasal 1")
        assert (r.exists, r.faithful, r.faithful_score) == ("gagal", "gagal", None), addr
    r = cite(units_v2, "Akta 91 › Pasal 1 › ayat (2) › huruf a", "b. menyerahkan.")
    assert (r.exists, r.faithful) == ("lulus", "gagal")
    r = cite(units_v2, "Akta 91 > Pasal 1", "Pasal 1")  # ASCII ">" tanpa normalisasi (D1)
    assert (r.exists, r.faithful) == ("gagal", "gagal")
    r = cite(units_v2, "Akta 91 › Pasal 1", "Pasal 1 ")  # spasi akhir: bukan substring, d_min 1, n 8 -> 7/8 < 0,95
    assert (r.exists, r.faithful, r.faithful_score) == ("lulus", "gagal", Fraction(7, 8))


def test_s7_control_legacy_map_only_batang_tubuh(cfgs):
    cs = pipe_for(cfgs, None).chunk_set(setting(cfgs, "fixed_size"))
    legacy = units_from_address_map(cs.amap, T)
    assert set(legacy) == {"Akta 91 › Batang Tubuh"}
    assert cite(legacy, "Akta 91 › Pasal 1", "Pasal 1").exists == "gagal"


def test_s8_rincian_address_is_valid_citation(cfgs, units_v2):
    amap = pipe_for(cfgs, bind(V2)).chunk_set(setting(cfgs, "fixed_size", bind(V2))).amap
    assert entry_labels(amap, 84, 127) == ()
    r = cite(units_v2, "Akta 91 › Pasal 1 › ayat (2)", "(2) Kewajiban:")
    assert (r.exists, r.faithful, r.faithful_score) == ("lulus", "lulus", None)
    assert cite(units_v2, "Akta 91 › Pasal 1 › ayat 2", "(2) Kewajiban:").exists == "gagal"


# ---- S9 -----------------------------------------------------------------------------------------------------------
def test_s9_active_schema_including_spark(cfgs):
    cases = [((V1,), 1, False, 4), ((V1, V2), 2, True, 5), ((V1, V2, V3_SPARK), 2, True, 5)]
    for recs, active_v, approved, n_units in cases:
        b = bind(*recs)
        assert b.active()["schema_version"] == active_v
        cs = pipe_for(cfgs, b).chunk_set(setting(cfgs, "fixed_size", b))
        assert len(cs.units) == n_units and cs.unit_map_kind == "schema"
        assert simple(cs.amap) == simple(schema_address_map(deed(), b.active()))
        assert b.describe(b.active())["schema_approved"] is approved
    v1map = pipe_for(cfgs, bind(V1)).chunk_set(setting(cfgs, "fixed_size", bind(V1))).amap
    assert ("Akta 91 › Kepala Akta", 9, 51) in simple(v1map) and not any("Komparisi" in a for a, _s, _e in simple(v1map))


def test_s9_envelope_flags_unapproved_spark_and_fixed_only(tmp_path):
    cfg = fixed_only_cfg(None, tmp_path / "cfg")
    res = grid(tmp_path, cfg, bind(V1), [("i1", [(60, 83)], "Para pihak")], name="spark")
    env = res.envelope
    assert env["schemas_used"] == [] and env["schema_approved"] is None  # fixed_size-saja: schema_report kosong (perilaku lama)
    um = env["unit_map"]
    assert (um["schema_version"], um["source"], um["schema_approved"], um["kind"]) == (1, "spark", False, "schema")
    assert um["schema_hash"] and um["unit_map_version"] == 1 and um["fallback_doc_ids"] == []
    ok = grid(tmp_path, cfg, bind(V1, V2), [("i1", [(60, 83)], "Para pihak")], name="op").envelope["unit_map"]
    assert (ok["schema_version"], ok["source"], ok["schema_approved"]) == (2, "operator", True)
    assert ok["schema_hash"] != um["schema_hash"]


def test_s9_structure_schema_setting_reports_unapproved(tmp_path, cfg):
    res = grid(tmp_path, cfg, bind(V1), [("i1", [(60, 83)], "Para pihak")], name="sp")
    env = res.envelope
    assert env["schema_approved"] is False and env["schemas_used"][0]["schema_approved"] is False
    assert env["unit_map"]["schema_approved"] is False


# ---- S10 ----------------------------------------------------------------------------------------------------------
def test_s10_schema_or_version_change_changes_key_and_repeat_hits_cache(tmp_path):
    cfg = fixed_only_cfg(None, tmp_path / "cfg")
    rows = [("i1", [(60, 83)], "Para pihak")]
    a = grid(tmp_path, cfg, bind(V2), rows, name="s10")
    b = grid(tmp_path, cfg, bind(V2, V3_OP), rows, name="s10")  # v2' operator v3, pola level 1 diubah (hash isi beda)
    assert b.key != a.key and b.record["config_hash"] != a.record["config_hash"]
    cfg2 = fixed_only_cfg(None, tmp_path / "cfg2", extra_unit_version=2)
    c = grid(tmp_path, cfg2, bind(V2), rows, name="s10")
    assert c.key != a.key and c.envelope["unit_map"]["unit_map_version"] == 2
    assert len({a.key, b.key, c.key}) == 3
    again = grid(tmp_path, cfg, bind(V2), rows, name="s10")
    assert again.key == a.key and again.cache_hit
    assert a.envelope["schemas_used"] == [] and a.envelope["unit_map"]["schema_version"] == 2  # blok ada walau schema_report kosong
    # pipa tidak dipanggil ulang pada cache hit
    out: list = []
    run_family_grid("akta", docs=[deed()], tokenizer=ToyWs(), runs_dir=tmp_path / "runs-s10", butir_dir=tmp_path / "b-s10",
                    config_dir=cfg, encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb", schemas=bind(V2), pipeline_out=out)
    assert out == []


# ---- S11 ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("binding", [bind(SCHEMA_N), bind(), None])
def test_s11_fallback_map_when_no_marker_or_no_schema(cfgs, binding):
    p = pipe_for(cfgs, binding)
    s = setting(cfgs, "fixed_size")
    cs = p.chunk_set(s)
    assert simple(cs.amap) == [("Akta 91 › Batang Tubuh", 0, 165)] and cs.units == [(0, 165)] and cs.unit_map_kind == "fallback"
    assert any("peta cadangan" in n for n in cs.amap.notes)
    assert set(units_from_address_map(cs.amap, T)) == {"Akta 91 › Batang Tubuh"}  # satu-satunya unit sah (P6 pengecualian)
    ss = unavailable_reason(replace(s, chunker="structure_schema"), schemas=binding)
    assert (ss is None) == (binding is not None and bool(binding.records))  # tanpa skema: dilewati


def test_s11_envelope_marks_fallback(tmp_path):
    cfg = fixed_only_cfg(None, tmp_path / "cfg")
    for name, b in (("n", bind(SCHEMA_N)), ("none", bind())):
        res = grid(tmp_path, cfg, b, [("i1", [(60, 83)], "Para pihak")], name=name)
        env = res.envelope
        assert env["unit_map"]["kind"] == "fallback" and env["unit_map"]["fallback_doc_ids"] == ["akta-91"]
        assert {q["unit_map_kind"] for q in env["quality"]} == {"fallback"}
        assert env["unit_map"]["schema_version"] == (3 if name == "n" else None)


# ---- S12 ----------------------------------------------------------------------------------------------------------
def test_s12_multi_document_maps_per_deed(cfgs, tmp_path):
    r, g = cfgs
    d1, d2 = deed(), deed(prefix="Akta 92", doc_id="akta-92")
    b = bind(V2)
    mp = MultiDocPipeline([d1, d2], tokenizer=ToyWs(), retrieval_cfg=r, grid_cfg=g, schemas=b, encoder=FakeEncoder())
    s = setting(cfgs, "fixed_size", b)
    m1, m2 = (mp.pipes[i].chunk_set(s).amap for i in ("akta-91", "akta-92"))
    assert [(u.start, u.end) for u in m1.units] == [(u.start, u.end) for u in m2.units] == V2_UNITS
    assert [u.address for u in m2.units] == [a.replace("Akta 91", "Akta 92") for a in V2_ADDR]
    assert "Akta 92 › Pasal 1" not in units_from_address_map(m1, T) and "Akta 92 › Pasal 1" in units_from_address_map(m2, T)
    cfgd = fixed_only_cfg(None, tmp_path / "cfg")
    docs = {d.doc_id: d for d in (d1, d2)}
    res = grid(tmp_path, cfgd, b, [("a", [(100, 140)], "Harga tetap", "akta-91"), ("b", [(127, 128)], "Selesai", "akta-92")], docs=docs, name="mx")
    env = res.envelope
    assert env["unit_map"]["kind"] == "schema" and isinstance(env["unit_map"], dict) and "unit_map" not in env["unit_map"]
    assert env["unit_map"]["n_items_recall_null"] == 1  # butir b (LF antar unit) di akta-92


# ---- S13 ----------------------------------------------------------------------------------------------------------
def test_s13_pure_and_no_mutation(cfgs):
    d = deed()
    before = (d.text, json.dumps(V2, sort_keys=True), json.dumps(d.sections))
    outs = []
    for _ in range(2):
        amap = schema_address_map(d, V2)
        outs.append((simple(amap), [(r.address, r.start, r.end) for u in amap.units for r in u.children],
                     entry_labels(amap, 100, 150), entry_labels(amap, 90, 135)))
    assert outs[0] == outs[1]
    assert (d.text, json.dumps(V2, sort_keys=True), json.dumps(d.sections)) == before
    p = pipe_for(cfgs, bind(V2))
    assert simple(p.chunk_set(setting(cfgs, "fixed_size", bind(V2))).amap) == simple(p.chunk_set(setting(cfgs, "structure_schema", bind(V2))).amap)


# ---- S14 ----------------------------------------------------------------------------------------------------------
def test_s14_stored_verdicts_carry_map_identity_in_envelope(tmp_path):
    """Replay membaca verdict tersimpan apa adanya; identitas peta saat run dicatat di amplop grid (`unit_map`), sehingga
    peta berbeda dari peta sekarang dapat dikenali. Kunci grid berubah bila peta berubah (S10), jadi run lama tidak dipakai ulang."""
    cfg = fixed_only_cfg(None, tmp_path / "cfg")
    old = grid(tmp_path, cfg, bind(V1), [("i1", [(60, 83)], "Para pihak")], name="o")
    new = grid(tmp_path, cfg, bind(V1, V2), [("i1", [(60, 83)], "Para pihak")], name="n")
    ident = lambda e: (e["unit_map"]["schema_version"], e["unit_map"]["schema_hash"], e["unit_map"]["unit_map_version"])  # noqa: E731
    assert ident(old.envelope) != ident(new.envelope) and old.key != new.key
    # kutipan "Batang Tubuh" ditolak oleh peta baru (pembuatan ulang snapshot memakai peta baru)
    d = deed()
    p = Pipeline(d, tokenizer=ToyWs(), retrieval_cfg=config.load("retrieval", cfg), grid_cfg=config.load("grid", cfg), schemas=bind(V1, V2))
    cs = p.chunk_set(next(s for s in expand_grid(config.load("grid", cfg), "akta")))
    assert cite(units_from_address_map(cs.amap, T), "Akta 91 › Batang Tubuh", T[0:165]).exists == "gagal"


# ---- I-65 / P7 / P10 ------------------------------------------------------------------------------------------------
def test_i65_akta_recall_over_all_gold_items_labelled_transfer(tmp_path):
    cfg = fixed_only_cfg(None, tmp_path / "cfg")
    rows = [("a", [(52, 127)], "Pasal Para pihak"), ("b", [(128, 148)], "Harga tetap"), ("c", [(127, 128)], "Selesai"), ("d", [(0, 40)], "AKTA TOY"),
            ("e", [], "tolak tanpa gold")]  # e: butir wajib tolak (H-092), tanpa gold: tidak boleh terhitung null
    res = grid(tmp_path, cfg, bind(V2), rows, name="i65")
    env = res.envelope
    assert env["split"] is None
    for q in env["quality"]:
        assert q["items_scope"] == "transfer" and q["recall_unit"] == "default_chunk_level" and q["unit_map_kind"] == "schema"
        assert q["recall_n_items"] == 3 and q["recall_at_k"] is not None  # a, b, d berhitung; c (gold di luar unit) null
    assert env["recall_unit"] == "default_chunk_level"
    um = env["unit_map"]
    assert (um["n_items_recall_null"], um["n_items_gold_partly_outside"], um["recall_unit"]) == (1, 1, "default_chunk_level")
    ms = {m["item_id"]: m for m in env["metrics"] if m["setting_id"] == env["settings_run"][0]["setting_id"]}
    assert {k: v["gold_chars_outside_units"] for k, v in ms.items()} == {"a": 0, "b": 0, "c": 1, "d": 10, "e": 0}
    assert ms["c"]["parts_total"] == 0 and ms["d"]["parts_total"] == 2 and ms["e"]["parts_total"] == 0


def test_i65_scope_rule_comes_from_akta_config_and_uupt_stays_held_out(tmp_path):
    cfg = fixed_only_cfg(None, tmp_path / "cfg")
    u = cfg / f"{UNIT_MAP_CONFIG}.toml"
    u.write_bytes(u.read_bytes().replace(b'items = "all"', b'items = "bogus"'))
    with pytest.raises(GridRunError, match="recall_items"):
        grid(tmp_path, cfg, bind(V2), [("i1", [(60, 83)], "Para pihak")], name="bad")
    assert config.load("retrieval")["quality"]["recall_items"] == "held_out"  # UU PT tidak digeser
    assert config.load(UNIT_MAP_CONFIG)["recall"] == {"items": "all", "label": "transfer", "unit": "default_chunk_level"}


# ---- ringkasan lima akta repo (baca-saja, tanpa grid) ----------------------------------------------------------------
def test_repo_deeds_unit_counts_with_active_schema():
    """Skema A akta aktif repo (v2 operator, commit 067809e): 18/21/24/26/29 unit, satu Komparisi tiap akta. Membaca `runs/schemas`
    dan `data/akta` saja; dilewati bila tidak ada."""
    from backend.corpus import load_corpus

    runs = config.REPO_ROOT / "runs"
    b = SchemaBinding.from_store(runs, "akta") if (runs / "schemas" / "akta").is_dir() else None
    act = b.active() if b else None
    if act is None or act.get("schema_version") != 2 or act.get("source") != "operator":
        pytest.skip("skema A akta v2 operator tidak aktif")
    counts = []
    for i in range(1, 6):
        amap = schema_address_map(load_corpus(f"akta-0{i}"), act)
        counts.append(len(amap.units))
        assert sum(1 for u in amap.units if u.address.endswith("› Komparisi")) == 1
    assert counts == [18, 21, 24, 26, 29]
