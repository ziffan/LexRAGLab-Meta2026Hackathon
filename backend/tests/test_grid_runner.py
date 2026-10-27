"""M1.4 ekspansi grid dan runner/cache: S21, S22, S10 (frontier akta) (docs/scenarios/M1.4.md)."""

import copy
from dataclasses import replace

import pytest

from backend.config import config_hash, load
from backend.grid.expand import expand_grid
from backend.grid.runner import DirGridCache, GridError, MemoryGridCache, run_grid
from backend.grid.split import make_split
from backend.grid.types import GridItem, ItemMetrics
from backend.tests.grid_helpers import SIMPLICITY, ids, mk_items, mk_setting

GRID_CFG = {
    "version": 1,
    "chunkers": ["structure_handwritten", "fixed_size"],
    "retrieval_modes": ["bm25", "dense"],
    "header_b": [False, True],
    "fixed_size": {"chunk_size_tokens": [256], "overlap_tokens": [0, 32]},
    "budget": {"default_tokens": 2000, "comparison_tokens": [4000]},
}


def test_S21_expansion_cartesian_unique_canonical_ids():
    ss = expand_grid(GRID_CFG, "uupt")
    assert len(ss) == 24 and len({s.setting_id for s in ss}) == 24
    assert all(s.overlap_tokens is None and s.chunk_size_tokens is None and s.schema_version is None
               for s in ss if s.chunker == "structure_handwritten")
    reordered = copy.deepcopy(GRID_CFG)
    reordered["retrieval_modes"].reverse()
    reordered["fixed_size"]["overlap_tokens"].reverse()
    reordered["chunkers"].reverse()
    assert {s.setting_id for s in expand_grid(reordered, "uupt")} == {s.setting_id for s in ss}
    other = copy.deepcopy(GRID_CFG)
    other["budget"]["comparison_tokens"] = [3000]
    assert len({s.setting_id for s in expand_grid(other, "uupt")} & {s.setting_id for s in ss}) == 12
    assert {s.budget_tokens for s in ss} == {2000, 4000}


def test_S21_real_config_expands():
    ss = expand_grid(load("grid"), "uupt")
    # (1 + 1 struktur... structure_schema tanpa schema_version = 1 varian) + 1 fixed = 3 x 3 x 2 x 2 anggaran
    assert len(ss) == 3 * 3 * 2 * 2 and len({s.setting_id for s in ss}) == len(ss)


class FakePipeline:
    def __init__(self):
        self.calls = 0

    def __call__(self, setting, items):
        self.calls += len(items)
        return [ItemMetrics(i.id, setting.setting_id, None, 10, 5, 500, 50) for i in items]


def base_world():
    items = mk_items({("operator", "literal"): ids("i", 1, 3), ("operator", "parafrase"): ["i4"],
                      ("spark_disetujui", "literal"): ids("i", 5, 8)})
    rec = make_split(items, family="uupt", seed=7, held_out_ratio=0.4, min_control=3)
    settings = [mk_setting(s, mode=m) for s, m in (("a", "bm25"), ("b", "dense"), ("c", "hybrid"))]
    return items, rec, settings


def test_S22_cache_isolates_each_key_component(tmp_path):
    items, rec, settings = base_world()
    assert len(items) == 8
    pipe, cache = FakePipeline(), DirGridCache(tmp_path / "runs" / "grid")

    def go(items=items, rec=rec, ch="C", sha="X"):
        before = pipe.calls
        r = run_grid(settings=settings, items=items, pipeline=pipe, cache=cache, clean_sha256=sha,
                     config_hash=ch, split_record=rec, simplicity=SIMPLICITY, family="uupt")
        return r, pipe.calls - before

    r1, c1 = go()
    r2, c2 = go()
    assert (c1, c2) == (24, 0) and r2.cache_hit and not r1.cache_hit
    assert r1.metrics == r2.metrics and r1.points == r2.points and r1.frontiers == r2.frontiers
    assert r1.selections == r2.selections and r1.grid_run_id == r2.grid_run_id
    _, c3 = go(ch="C2")
    changed = [replace(items[2], gold_spans=((0, 5),))] + [i for i in items if i.id != items[2].id]
    _, c4 = go(items=changed)
    _, c5 = go(rec=replace(rec, split_version=2))
    new_items = items + [GridItem("i9", "uupt", "spark_disetujui", "literal")]
    rec2 = make_split(new_items, family="uupt", seed=7, held_out_ratio=0.4, min_control=3, previous=rec)
    assert rec2.split_version == 2
    _, c6 = go(items=new_items, rec=rec2)
    _, c7 = go(sha="Y")
    assert [c1, c2, c3, c4, c5, c6, c7] == [24, 0, 24, 24, 24, 27, 24]
    assert list((tmp_path / "runs" / "grid").glob("*.json"))


def test_memory_cache_roundtrip_is_exact():
    items, rec, settings = base_world()
    cache = MemoryGridCache()
    kw = dict(settings=settings, items=items, pipeline=FakePipeline(), cache=cache, clean_sha256="X",
              config_hash="C", split_record=rec, simplicity=SIMPLICITY, family="uupt")
    a, b = run_grid(**kw), run_grid(**kw)
    assert b.cache_hit and a.metrics == b.metrics


def test_pipeline_item_mismatch_is_error():
    items, rec, settings = base_world()
    bad = lambda s, its: [ItemMetrics("zz", s.setting_id, None, 10, 5, 500, 50)]
    with pytest.raises(GridError):
        run_grid(settings=settings, items=items, pipeline=bad, cache=MemoryGridCache(), clean_sha256="X",
                 config_hash="C", split_record=rec, simplicity=SIMPLICITY, family="uupt")


def test_config_hash_input_changes_key():
    assert config_hash({"grid": {"a": 1}}) != config_hash({"grid": {"a": 2}})


def test_S10_akta_run_has_one_group_no_split_label_no_selection():
    items = mk_items({("operator", "literal"): ["k1", "k2"], ("spark_disetujui", "literal"): ids("k", 3, 5)}, family="akta")
    settings = [mk_setting("a", family="akta"), mk_setting("b", family="akta", mode="dense")]
    r = run_grid(settings=settings, items=items, pipeline=FakePipeline(), cache=MemoryGridCache(), clean_sha256="X",
                 config_hash="C", split_record=None, simplicity=SIMPLICITY, family="akta")
    assert r.selections == {}
    assert all(m.split is None for m in r.metrics)
    assert all(p.split is None for p in r.points) and all(f.split is None for f in r.frontiers)
    assert len(r.frontiers) == 1 and {m.item_id for m in r.metrics} == {i.id for i in items}
