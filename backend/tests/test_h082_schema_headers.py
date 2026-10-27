"""H-082: header B untuk potongan structure_schema (semua dipanggil B; tanpa reuse header Pasal). Sintetis, tanpa jaringan."""

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.pipeline.pipeline import chunk_params
from backend.grid.headers import DirHeaderStore, HeaderBinding, HeaderGranularityError, MemoryHeaderStore, _pairs_hash
from backend.header_b import units as units_mod
from backend.header_b.caller import load_header, store_dir
from backend.header_b.prompt import load_prompt
from backend.header_b.render import build_prefix
from backend.header_b.schema import plan_schema, project_schema
from backend.header_b.run import Prepared, load_all_configs, project
from backend.header_b.units import build_units
from backend.tests.header_grid_helpers import account, doc_of, make_pipe, setting
from backend.tests.toy_ws import TOK

TEXT = "Pasal 1\n(1) Aaa bbb.\n(2) Ccc ddd.\n\nPasal 2\n(1) Eee fff.\n\nPasal 3\n(1) Ggg hhh.\n"
P2 = (TEXT.index("Pasal 2"), TEXT.index("\n\nPasal 3"))
P3 = (TEXT.index("Pasal 3"), len(TEXT) - 1)
A11 = (TEXT.index("(1) Aaa"), TEXT.index("\n(2) Ccc"))
A12 = (TEXT.index("(2) Ccc"), TEXT.index("\n\nPasal 2"))
U1 = (A11[0], A12[1])  # unit Pasal 1 = gabungan anggota ayatnya
SEPS = " › "
CLEAN = "C" * 64
RCFG, GCFG = {}, {}


class Tok:
    def count(self, text):
        return len(text.split())


def doc():
    return SimpleNamespace(doc_id="d", text=TEXT, clean_sha256=CLEAN, sha256="s")


def mk(cid, span, label, address, section="body"):
    return SimpleNamespace(chunk_id=cid, start=span[0], end=span[1], section=section, address=address,
                           address_levels=[{"level": "pasal", "label": label}], tokens_local=len(TEXT[span[0]:span[1]].split()))


# chunker tangan (sumber unit pasal): Pasal 1 = 2 ayat; Pasal 2 dan 3 = 1 ayat
HAND = [mk("h11", A11, "Pasal 1", SEPS.join(["Pasal 1", "ayat (1)"])), mk("h12", A12, "Pasal 1", SEPS.join(["Pasal 1", "ayat (2)"])),
        mk("h2", P2, "Pasal 2", SEPS.join(["Pasal 2", "ayat (1)"])), mk("h3", P3, "Pasal 3", SEPS.join(["Pasal 3", "ayat (1)"]))]


def schema_chunks(**over):
    c = {"s1": mk("s1", U1, "Pasal 1", "Pasal 1"), "s2": mk("s2", P2, "Pasal 2", "Pasal 2"),
         "s3": mk("s3", P3, "Pasal 3", "Pasal 3")}
    c.update(over)
    return list(c.values())


@pytest.fixture(autouse=True)
def fake_chunker(monkeypatch):
    state = {"schema": schema_chunks()}

    def fake(d, setting_, **kw):
        return list(HAND) if setting_["chunker"] == "structure_handwritten" else list(state["schema"])

    monkeypatch.setattr(units_mod, "chunk_document", fake)
    return state




def inject_schema_chunks(pipe, s):
    """Pipeline menghitung kunci potongan dari rekaman skema utuh; test memakai potongan yang sudah disuntik (make_pipe)."""
    cs = pipe._sets[chunk_params(s)]
    pipe.chunk_set = lambda _s: cs


PROMPT = load_prompt(40, "v2")
V1 = load_prompt(40, "v1")


def prep():
    d = doc()
    us = build_units(d, "structure_schema", tokenizer=Tok(), retrieval_cfg=RCFG, grid_cfg=GCFG, schema_record={"x": 1})
    return Prepared(d, PROMPT, build_prefix(PROMPT, d, Tok()), us, "structure_schema")


def put(hdir, gran, prompt, cid, header="Hdr satu", **extra):
    d = store_dir(hdir, gran, prompt)
    d.mkdir(parents=True, exist_ok=True)
    rec = {"chunk_id": cid, "header": header, "granularity": gran, "prompt_version": prompt.version,
           "tokens_local": len(header.split()), "run_id": "runB1", **extra}
    (d / f"{cid}.json").write_text(json.dumps(rec, sort_keys=True), encoding="utf-8", newline="\n")
    return rec


def seed_pasal(hdir, prompt=PROMPT):
    pas = build_units(doc(), "pasal", tokenizer=Tok(), retrieval_cfg=RCFG, grid_cfg=GCFG)
    return {u.key: put(hdir, "pasal", prompt, u.key, f"Hdr {u.address}") for u in pas}, pas


LOCKED_HASH = "f1880b86ee79c0dccbc9c73a9ff93ad58d5f6f27200e53ce15163c37f156535c"


def plan(p, hdir, **kw):
    return plan_schema(p, headers_dir=hdir, **kw)


# ---------------------------------------------------------------- sumber unit
def test_schema_units_carry_span_and_need_record():
    p = prep()
    assert [(u.key, u.start, u.end) for u in p.units] == [("s1", *U1), ("s2", *P2), ("s3", *P3)]
    assert all(u.text == TEXT[u.start:u.end] and u.chunk_ids == (u.key,) for u in p.units)
    with pytest.raises(ValueError):
        build_units(doc(), "structure_schema", tokenizer=Tok(), retrieval_cfg=RCFG, grid_cfg=GCFG)
    pas = build_units(doc(), "pasal", tokenizer=Tok(), retrieval_cfg=RCFG, grid_cfg=GCFG)
    assert [(u.key, u.start, u.end, u.chunk_ids) for u in pas][0] == ("h11", *U1, ("h11", "h12"))


# ---------------------------------------------------------------- rencana: semua dipanggil kecuali yang tersimpan
def test_empty_store_calls_all_even_when_identical_pasal_headers_exist(tmp_path):
    seed_pasal(tmp_path)  # header Pasal dengan rentang+teks identik tersedia, tetapi tidak dipakai
    pl = plan(prep(), tmp_path)
    assert [u.key for u in pl.call] == ["s1", "s2", "s3"] and pl.stored == [] and pl.total == 3
    assert not store_dir(tmp_path, "structure_schema", PROMPT).exists()  # perencanaan tidak menulis apa pun


def test_stored_units_are_skipped_and_not_overwritten(tmp_path):
    seed_pasal(tmp_path)
    put(tmp_path, "structure_schema", PROMPT, "s2", "Dipanggil sendiri")
    before = (store_dir(tmp_path, "structure_schema", PROMPT) / "s2.json").read_bytes()
    pl = plan(prep(), tmp_path)
    assert [u.key for u in pl.stored] == ["s2"] and [u.key for u in pl.call] == ["s1", "s3"]
    assert (store_dir(tmp_path, "structure_schema", PROMPT) / "s2.json").read_bytes() == before
    put(tmp_path, "structure_schema", PROMPT, "s1")
    put(tmp_path, "structure_schema", PROMPT, "s3")
    again = plan(prep(), tmp_path)
    assert len(again.stored) == 3 and again.call == []


def test_other_prompt_store_does_not_count_as_stored(tmp_path):
    put(tmp_path, "structure_schema", V1, "s1")  # prompt lain
    assert [u.key for u in plan(prep(), tmp_path).call] == ["s1", "s2", "s3"]


def test_limit_applies_to_first_schema_chunks(tmp_path):
    pl = plan(prep(), tmp_path, limit=2)
    assert pl.total == 2 and [u.key for u in pl.call] == ["s1", "s2"]


# ---------------------------------------------------------------- hash identitas
def test_store_hash_formula_is_pairs_of_chunk_id_and_header(tmp_path):
    put(tmp_path, "pasal", PROMPT, "h2", "Hdr dua")
    put(tmp_path, "ayat", PROMPT, "a1", "Hdr ayat")
    put(tmp_path, "structure_schema", PROMPT, "s1", "Hdr skema", reused_from="diabaikan")  # field lain tidak ikut hash
    got = DirHeaderStore(tmp_path, PROMPT.prompt_hash, tmp_path / "runs").content_hash()
    pairs = [("pasal/h2", "Hdr dua"), ("ayat/a1", "Hdr ayat"), ("structure_schema/s1", "Hdr skema")]
    legacy = hashlib.sha256(json.dumps(sorted(pairs), ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert got == legacy == _pairs_hash(pairs)
    assert MemoryHeaderStore({"x": {"header": "H", "reused_from": "z"}}).content_hash() == _pairs_hash([("x", "H")])


def test_store_hash_locked_value_small_fixture(tmp_path):
    put(tmp_path, "pasal", PROMPT, "h2", "Hdr dua")
    put(tmp_path, "ayat", PROMPT, "a1", "Hdr ayat")
    assert DirHeaderStore(tmp_path, PROMPT.prompt_hash, tmp_path / "runs").content_hash() == LOCKED_HASH


# ---------------------------------------------------------------- proyeksi
def test_projection_counts_only_to_call(tmp_path):
    hc, mc, *_ = load_all_configs()
    p = prep()
    full = project(p, Tok(), hc, mc)
    put(tmp_path, "structure_schema", PROMPT, "s2")
    r = project_schema(p, plan(p, tmp_path), Tok(), hc, mc)
    assert (r["chunks"], r["to_call"], r["already_stored"]) == (3, 2, 1)
    two = project(replace(p, units=[p.units[0], p.units[2]]), Tok(), hc, mc)
    assert r["projection"]["cost_usd_micros"] == two["cost_usd_micros"] and r["projection"]["units"] == 2
    assert r["projection"]["cost_usd_micros"]["expected"] < full["cost_usd_micros"]["expected"]


def test_projection_zero_when_all_stored(tmp_path):
    hc, mc, *_ = load_all_configs()
    p = prep()
    for u in p.units:
        put(tmp_path, "structure_schema", PROMPT, u.key)
    r = project_schema(p, plan(p, tmp_path), Tok(), hc, mc)
    assert r["to_call"] == 0 and r["already_stored"] == 3 and r["projection"]["calls"] == 0
    assert r["projection"]["cost_usd_micros"] == {"expected": 0, "upper_cached": 0, "upper_no_cache": 0}


# ---------------------------------------------------------------- grid: kembaran structure_schema memakai store baru
def test_binding_points_schema_twin_to_new_store():
    assert HeaderBinding(MemoryHeaderStore(), "pasal").expected_granularity("structure_schema") == "structure_schema"
    assert HeaderBinding(MemoryHeaderStore(), "ayat").expected_granularity("structure_schema") == "structure_schema"
    b = HeaderBinding(MemoryHeaderStore(), "pasal")
    assert b.expected_granularity("structure_handwritten") == "pasal" and b.expected_granularity("fixed_size") == "fixed_size"


def test_grid_schema_twin_reads_schema_store_header_and_counts_tokens(tmp_path):
    from backend.tests.toy_ws import C1, C2, T

    d = doc_of(T, clean="X")
    runs = tmp_path / "runs"
    (runs / "spark" / "records").mkdir(parents=True)
    (runs / "spark" / "records" / "runB1.json").write_text(json.dumps({"clean_sha256": "X"}), encoding="utf-8", newline="\n")
    hdir = tmp_path / "headers"
    hdr = {"c1": "H1 H2", "c2": "H3"}
    for cid, h in hdr.items():
        put(hdir, "structure_schema", PROMPT, cid, h)
    off = setting("sch", header=False, budget=100, chunker="structure_schema")
    on = replace(off, setting_id="sch+", header_b=True)
    pipe = make_pipe(d, [(off, {"c1": C1, "c2": C2})], None, tokenizer=TOK)
    inject_schema_chunks(pipe, off)
    pipe.headers = HeaderBinding(DirHeaderStore(hdir, PROMPT.prompt_hash, runs), "pasal", "all", PROMPT.prompt_hash, "m")
    rt_off, rt_on = account(pipe, off, ["c1", "c2"], [C1]), account(pipe, on, ["c1", "c2"], [C1])
    assert pipe.headers_for(on) == hdr
    assert rt_on.metrics.retrieved_tokens - rt_off.metrics.retrieved_tokens == 3  # token header (2 + 1) masuk anggaran
    assert rt_on.metrics.span_recall == rt_off.metrics.span_recall  # gold tetap pada teks sumber


def test_grid_schema_twin_rejects_pasal_labeled_header():
    from backend.tests.toy_ws import C1, T

    store = MemoryHeaderStore({"c1": {"chunk_id": "c1", "header": "H", "granularity": "pasal", "run_id": "b"}}, {"b": "X"})
    off = setting("sch", header=False, budget=100, chunker="structure_schema")
    pipe = make_pipe(doc_of(T, clean="X"), [(off, {"c1": C1})], store)
    inject_schema_chunks(pipe, off)
    with pytest.raises(HeaderGranularityError):
        pipe.headers_for(replace(off, setting_id="sch+", header_b=True))
