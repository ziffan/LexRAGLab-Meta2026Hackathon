"""H-080: header B untuk potongan structure_schema (reuse header Pasal hanya bila rentang+teks identik). Sintetis, tanpa jaringan."""

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
from backend.header_b.reuse import plan_schema, project_schema, write_reuse
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


def plan(p, hdir, **kw):
    return plan_schema(p, headers_dir=hdir, tokenizer=Tok(), retrieval_cfg=RCFG, grid_cfg=GCFG, **kw)


# ---------------------------------------------------------------- sumber unit
def test_schema_units_carry_span_and_need_record():
    p = prep()
    assert [(u.key, u.start, u.end) for u in p.units] == [("s1", *U1), ("s2", *P2), ("s3", *P3)]
    assert all(u.text == TEXT[u.start:u.end] and u.chunk_ids == (u.key,) for u in p.units)
    with pytest.raises(ValueError):
        build_units(doc(), "structure_schema", tokenizer=Tok(), retrieval_cfg=RCFG, grid_cfg=GCFG)
    pas = build_units(doc(), "pasal", tokenizer=Tok(), retrieval_cfg=RCFG, grid_cfg=GCFG)
    assert [(u.key, u.start, u.end, u.chunk_ids) for u in pas][0] == ("h11", *U1, ("h11", "h12"))


# ---------------------------------------------------------------- reuse hanya bila rentang+teks identik
def test_identical_span_and_text_reuses_without_call(tmp_path):
    seed_pasal(tmp_path)
    pl = plan(prep(), tmp_path)
    assert [r.unit.key for r in pl.reuse] == ["s1", "s2", "s3"] and pl.call == []
    assert {r.unit.key: r.source.key for r in pl.reuse} == {"s1": "h11", "s2": "h2", "s3": "h3"}
    assert write_reuse(pl, headers_dir=tmp_path, prompt=PROMPT) == 3
    rec = load_header(tmp_path, "structure_schema", PROMPT, "s1")
    assert rec["chunk_id"] == "s1" and rec["granularity"] == "structure_schema" and rec["reused_from"] == "h11"
    assert rec["run_id"] == "runB1" and rec["prompt_version"] == "v2" and rec["header"].startswith("Hdr ")
    assert rec["tokens_local"] == len(rec["header"].split())


def test_address_label_is_not_a_condition_but_is_counted(tmp_path, fake_chunker):
    seed_pasal(tmp_path)
    fake_chunker["schema"] = schema_chunks(s2=mk("s2", P2, "Pasal 2", "Pasal 2 › ayat (1) › ayat (1)"))
    pl = plan(prep(), tmp_path)
    assert len(pl.reuse) == 3 and pl.address_differs == 1 and pl.call == []


def test_one_byte_different_text_goes_to_call(tmp_path):
    seed_pasal(tmp_path)
    p = prep()
    u2 = p.units[1]
    for variant in (u2.text[:-1] + "g", u2.text + " ", u2.text.replace("Eee", "Éee"), u2.text.replace("Eee fff", "Eee fff")):
        assert variant.encode("utf-8") != u2.text.encode("utf-8")
        pl = plan(replace(p, units=[p.units[0], replace(u2, text=variant), p.units[2]]), tmp_path)
        assert [r.unit.key for r in pl.reuse] == ["s1", "s3"] and [u.key for u in pl.call] == ["s2"]


def test_same_start_different_end_with_identical_text_goes_to_call(tmp_path):
    seed_pasal(tmp_path)
    p = prep()
    u2 = p.units[1]
    pl = plan(replace(p, units=[replace(u2, end=u2.end + 1)]), tmp_path)  # teks sama, rentang beda
    assert pl.reuse == [] and [u.key for u in pl.call] == ["s2"]
    pl = plan(replace(p, units=[replace(u2, start=u2.start + 1)]), tmp_path)
    assert pl.reuse == [] and len(pl.call) == 1


def test_write_reuse_never_overwrites_existing_record(tmp_path):
    seed_pasal(tmp_path)
    pl = plan(prep(), tmp_path)
    put(tmp_path, "structure_schema", PROMPT, "s1", "Sudah ada")  # muncul setelah rencana dibuat
    write_reuse(pl, headers_dir=tmp_path, prompt=PROMPT)
    assert load_header(tmp_path, "structure_schema", PROMPT, "s1")["header"] == "Sudah ada"


def test_different_span_goes_to_call_and_no_address_only_match(tmp_path, fake_chunker):
    seed_pasal(tmp_path)
    shifted = mk("s2", (P2[0], P2[1] - 1), "Pasal 2", SEPS.join(["Pasal 2", "ayat (1)"]))  # alamat sama dengan sumber
    fake_chunker["schema"] = schema_chunks(s2=shifted)
    pl = plan(prep(), tmp_path)
    assert [u.key for u in pl.call] == ["s2"] and [r.unit.key for r in pl.reuse] == ["s1", "s3"]
    assert pl.near_miss == []  # tidak ada unit sumber dengan rentang itu


def test_no_reuse_across_prompt_hash_or_version(tmp_path):
    seed_pasal(tmp_path, prompt=V1)  # hanya header v1
    for f in store_dir(tmp_path, "pasal", V1).glob("*.json"):  # bahkan berlabel "v2", direktori hash v1 tidak dibaca
        d = json.loads(f.read_text(encoding="utf-8"))
        d["prompt_version"] = "v2"
        f.write_text(json.dumps(d), encoding="utf-8", newline="\n")
    pl = plan(prep(), tmp_path)
    assert pl.reuse == [] and len(pl.call) == 3
    assert {n["reason"] for n in pl.near_miss} == {"source_header_missing"}
    seed_pasal(tmp_path)  # v2 ada, tetapi satu berkas berlabel versi lain
    f = store_dir(tmp_path, "pasal", PROMPT) / "h2.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["prompt_version"] = "v1"
    f.write_text(json.dumps(d), encoding="utf-8", newline="\n")
    pl = plan(prep(), tmp_path)
    assert [u.key for u in pl.call] == ["s2"] and len(pl.reuse) == 2
    assert not list(store_dir(tmp_path, "structure_schema", V1).glob("*.json"))  # store v1 tak disentuh


def test_empty_source_header_not_reused(tmp_path):
    put(tmp_path, "pasal", PROMPT, "h11", "   ")
    assert "s1" in [u.key for u in plan(prep(), tmp_path).call]


def test_stored_units_are_not_repeated_and_never_overwritten(tmp_path):
    seed_pasal(tmp_path)
    put(tmp_path, "structure_schema", PROMPT, "s2", "Dipanggil sendiri")
    pl = plan(prep(), tmp_path)
    assert [u.key for u in pl.stored] == ["s2"] and [r.unit.key for r in pl.reuse] == ["s1", "s3"]
    write_reuse(pl, headers_dir=tmp_path, prompt=PROMPT)
    assert load_header(tmp_path, "structure_schema", PROMPT, "s2")["header"] == "Dipanggil sendiri"
    again = plan(prep(), tmp_path)
    assert len(again.stored) == 3 and again.reuse == [] and again.call == []
    assert write_reuse(again, headers_dir=tmp_path, prompt=PROMPT) == 0


def test_limit_applies_to_first_schema_chunks(tmp_path):
    seed_pasal(tmp_path)
    assert plan(prep(), tmp_path, limit=2).total == 2


# ---------------------------------------------------------------- hash identitas
def test_reused_from_changes_content_hash_dir_and_memory(tmp_path):
    dirs = [tmp_path / n for n in "abc"]
    for d, kw in zip(dirs, ({}, {"reused_from": "h11"}, {"reused_from": "hXX"})):
        (d / "runs").mkdir(parents=True)
        put(d, "structure_schema", PROMPT, "s1", "Hdr", **kw)
    hs = [DirHeaderStore(d, PROMPT.prompt_hash, d / "runs").content_hash() for d in dirs]
    assert len(set(hs)) == 3
    m = [MemoryHeaderStore({"s1": {"header": "Hdr", **kw}}).content_hash() for kw in ({}, {"reused_from": "h11"}, {"reused_from": "hXX"})]
    assert len(set(m)) == 3
    ids = [HeaderBinding(DirHeaderStore(d, PROMPT.prompt_hash, d / "runs"), "pasal", "all", PROMPT.prompt_hash, "m").identity()
           for d in dirs[:2]]
    assert ids[0]["store"] != ids[1]["store"]


def test_hash_without_reused_from_is_unchanged_legacy_formula(tmp_path):
    put(tmp_path, "pasal", PROMPT, "h2", "Hdr dua")
    put(tmp_path, "ayat", PROMPT, "a1", "Hdr ayat")
    got = DirHeaderStore(tmp_path, PROMPT.prompt_hash, tmp_path / "runs").content_hash()
    legacy = hashlib.sha256(json.dumps(sorted([("pasal/h2", "Hdr dua"), ("ayat/a1", "Hdr ayat")]), ensure_ascii=False,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    assert got == legacy == _pairs_hash([("pasal/h2", "Hdr dua"), ("ayat/a1", "Hdr ayat")])
    assert MemoryHeaderStore({"x": {"header": "H"}}).content_hash() == _pairs_hash([("x", "H")])


def test_other_stores_untouched_by_reuse_write(tmp_path):
    seed_pasal(tmp_path)
    put(tmp_path, "pasal", V1, "h2", "v1 lama")
    snap = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    write_reuse(plan(prep(), tmp_path), headers_dir=tmp_path, prompt=PROMPT)
    assert all(p.read_bytes() == b for p, b in snap.items())
    new = set(tmp_path.rglob("*.json")) - set(snap)
    assert new and {p.parent for p in new} == {store_dir(tmp_path, "structure_schema", PROMPT)}


# ---------------------------------------------------------------- proyeksi
def test_projection_counts_only_calls(tmp_path):
    hc, mc, *_ = load_all_configs()
    seed_pasal(tmp_path)
    p = prep()
    full = project(p, Tok(), hc, mc)
    mixed = replace(p, units=[p.units[0], replace(p.units[1], text=p.units[1].text + "!"), p.units[2]])
    r = project_schema(mixed, plan(mixed, tmp_path), Tok(), hc, mc)
    assert (r["chunks"], r["reused"], r["to_call"], r["already_stored"]) == (3, 2, 1, 0)
    one = project(replace(mixed, units=[mixed.units[1]]), Tok(), hc, mc)
    assert r["projection"]["cost_usd_micros"] == one["cost_usd_micros"] and r["projection"]["units"] == 1
    assert r["projection"]["cost_usd_micros"]["expected"] < full["cost_usd_micros"]["expected"]
    allreuse = project_schema(p, plan(p, tmp_path), Tok(), hc, mc)
    assert allreuse["to_call"] == 0 and allreuse["projection"]["calls"] == 0
    assert allreuse["projection"]["cost_usd_micros"] == {"expected": 0, "upper_cached": 0, "upper_no_cache": 0}


# ---------------------------------------------------------------- grid: kembaran structure_schema memakai store baru
def test_binding_points_schema_twin_to_new_store():
    assert HeaderBinding(MemoryHeaderStore(), "pasal").expected_granularity("structure_schema") == "structure_schema"
    assert HeaderBinding(MemoryHeaderStore(), "ayat").expected_granularity("structure_schema") == "structure_schema"
    b = HeaderBinding(MemoryHeaderStore(), "pasal")
    assert b.expected_granularity("structure_handwritten") == "pasal" and b.expected_granularity("fixed_size") == "fixed_size"


def test_grid_schema_twin_reads_reused_header_and_counts_tokens(tmp_path):
    from backend.tests.toy_ws import C1, C2, T

    d = doc_of(T, clean="X")
    runs = tmp_path / "runs"
    (runs / "spark" / "records").mkdir(parents=True)
    (runs / "spark" / "records" / "runB1.json").write_text(json.dumps({"clean_sha256": "X"}), encoding="utf-8", newline="\n")
    hdir = tmp_path / "headers"
    hdr = {"c1": "H1 H2", "c2": "H3"}
    for cid, h in hdr.items():
        put(hdir, "structure_schema", PROMPT, cid, h, reused_from="src-" + cid)
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
