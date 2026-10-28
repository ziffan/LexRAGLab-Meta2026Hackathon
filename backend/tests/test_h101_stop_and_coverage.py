"""Putusan operator 13: semantic_invalid (header kepanjangan) tidak menghentikan run pembanding, galat teknis tetap; coverage grid
pembanding diturunkan dari isi store."""

from backend.grid.headers import DirHeaderStore, HeaderBinding
from backend.grid.types import Setting
from backend.header_b.caller import run_headers
from backend.header_b.compare_store import compare_store_dir
from backend.pipeline import grid_compare as gc

from .h101_helpers import PROMPT12, Tok, hc_b, make_prepared, put_header, rig_for, words
from .h101_run import go


def run_cmp_glimmer(tmp_path, behaviours, n=8):
    rig = rig_for(tmp_path, "glimmer_local", behaviours)
    d = compare_store_dir(rig.runs, "glimmer_local")
    s = go(rig, make_prepared(n), d, profile="glimmer_local", hc=hc_b(max_consecutive_errors=5), max_attempts=1)
    return rig, s


def test_six_semantic_invalid_in_a_row_do_not_stop_comparison_run(tmp_path):
    rig, s = run_cmp_glimmer(tmp_path, {f"CH-U{i}": [words(41)] for i in range(1, 7)})
    assert s["stopped"] is None and rig.tr.calls == 8 and s["stored"] == 2
    assert s["failed"] == {"uupt-x/pasal": [f"CH-U{i}" for i in range(1, 7)]}


def test_five_timeouts_in_a_row_still_stop_too_many_errors(tmp_path):
    rig, s = run_cmp_glimmer(tmp_path, {f"CH-U{i}": ["TIMEOUT"] for i in range(1, 6)})
    assert s["stopped"] == "too_many_errors" and rig.tr.calls == 5


def test_mixed_semantic_ignored_but_technical_errors_accumulate(tmp_path):
    beh = {**{f"CH-U{i}": ["TIMEOUT"] for i in range(1, 5)}, **{f"CH-U{i}": [words(41)] for i in range(5, 8)}, "CH-U8": ["TIMEOUT"]}
    rig, s = run_cmp_glimmer(tmp_path, beh)
    assert s["stopped"] == "too_many_errors" and rig.tr.calls == 8  # 4 timeout + 3 semantic (tak dihitung) + timeout ke-5
    beh2 = {**{f"CH-U{i}": ["TIMEOUT"] for i in range(1, 5)}, "CH-U5": [words(41)]}
    rig2, s2 = run_cmp_glimmer(tmp_path / "x", beh2, n=6)
    assert s2["stopped"] is None  # 4 teknis + 1 semantic + sukses: di bawah batas


def test_contributor_default_still_counts_semantic_invalid(tmp_path):
    rig = rig_for(tmp_path, "baseten_open", {f"CH-U{i}": [words(41)] for i in range(1, 9)})
    p = make_prepared(8)
    res = run_headers(rig.client, p.prompt, p.prefix, p.units, granularity="pasal", tokenizer=Tok(), headers_dir=tmp_path / "h",
                      max_header_tokens=40, max_output_tokens=1000, max_consecutive_errors=5, warm_max_output_tokens=1000, meta={})
    assert res.stopped_reason == "too_many_errors" and len(res.outcomes) == 5  # perilaku lama tak berubah
    res2 = run_headers(rig.client, p.prompt, p.prefix, p.units, granularity="pasal", tokenizer=Tok(), headers_dir=tmp_path / "h2",
                       max_header_tokens=40, max_output_tokens=1000, max_consecutive_errors=5, warm_max_output_tokens=1000, meta={},
                       count_semantic_errors=False)
    assert res2.stopped_reason is None and len(res2.outcomes) == 8


def test_coverage_derives_from_store_content_akta_117_of_118(tmp_path):
    hdir = tmp_path / "headers" / "akta"
    for i in range(117):
        put_header(hdir, "structure_schema", f"S{i}", f"Header {i}")
    put_header(hdir, "pasal", "P1", "Header pasal")
    store = DirHeaderStore(hdir, "a" * 64, tmp_path)
    binding = HeaderBinding(store, "pasal", "frontier_only", "a" * 64, "m")

    def st(sid, chunker):
        return Setting(sid, "akta", chunker, None, None, None, "bm25", True, 2000)

    twins = [st("a+hdr", "structure_handwritten"), st("b+hdr", "structure_schema"), st("c+hdr", "fixed_size")]
    cov = gc.coverage_of(twins, binding)
    assert cov == {"sources_run": ["pasal", "structure_schema"], "sources_not_run": ["fixed_size"]}  # 117/118 tersimpan: tetap "run"
    assert PROMPT12 == "a" * 12
