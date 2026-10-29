"""S8 (H-103 S3 bagian C): perubahan `backend/grid/headers.py` dan `backend/pipeline/pipeline.py` (kebijakan cakupan, hanya jalur
pembanding) tidak mengubah grid utama: identitas binding utama tanpa kunci baru, hasil `run_grid` header-on utama (UU PT dan akta
fixture H-101) byte-sama antara binding tanpa dan dengan kebijakan `strict` yang tak aktif, dan kunci amplop utama NYATA di
`runs/grid` (UU PT e7ffa7b0..., akta 86e701f5...) masih dihitung `make_plan` dari masukan sekarang."""

import json
from pathlib import Path

import pytest

from backend import config as bc
from backend.grid.headers import HeaderBinding
from backend.pipeline.grid_run import make_plan
from backend.spark import sweep_run

from .test_h101_grid_compare import main_binding, run_main, store_of, tree, w  # noqa: F401

REPO = Path(__file__).resolve().parents[2]


def test_main_binding_identity_has_no_coverage_or_mask_keys(w):
    b = main_binding(w)
    assert set(b.identity()) == {"store", "granularity", "prompt_hash", "model", "scope"}
    assert b.coverage is None and b.mask == frozenset()
    pol_only = HeaderBinding(b.store, b.granularity, b.scope, b.prompt_hash, b.model, coverage=("mask_ref", 95))
    assert pol_only.identity() == b.identity()  # kebijakan tidak masuk identitas binding (kunci pembanding lewat blok `compare`)


def test_toy_main_grid_header_on_is_byte_identical_with_inactive_policy(w, tmp_path):
    first = run_main(w)
    raw = first.path.read_bytes()
    ids = sorted(json.loads(raw)["settings_run"], key=lambda s: s["setting_id"])
    assert any(s["header_b"] for s in ids)
    # binding dengan (strict, 100) pada grid utama: hasil sama (cache hit atas kunci yang sama; tidak ada kunci baru di identitas)
    strict = HeaderBinding(main_binding(w).store, "ayat", "frontier_only", "ph", "meta-model", coverage=("strict", 100))
    again = run_main(w, strict)
    assert again.key == first.key and again.path.read_bytes() == raw
    # dan main grid satu header hilang tetap header_missing (A4/A15): tidak ada kebijakan bocor
    miss = store_of(w, "Hdr")
    victim = next(k for k, r in miss.records.items() if r["granularity"] == "ayat")
    miss.records.pop(victim)
    w2 = dict(w, runs=tmp_path / "runs2")
    res = run_main(w2, HeaderBinding(miss, "ayat", "frontier_only", "ph", "meta-model"))
    assert res.envelope["record"]["failed_settings"] and all(f["reason"] == "header_missing" for f in res.envelope["record"]["failed_settings"])


@pytest.mark.parametrize("family,prefix", [("uupt", "e7ffa7b0"), ("akta", "86e701f5")])
def test_real_main_grid_keys_are_still_found(family, prefix):
    grid = REPO / "runs" / "grid"
    names = [p.name for p in grid.glob(f"{prefix}*.json")] if grid.is_dir() else []
    if not names:
        pytest.skip("real runs/grid envelope is not present in this checkout")
    from backend.api.service import Service
    from backend.grid.schemas import SchemaBinding
    from backend.pipeline.grid_run import load_header_binding
    from backend.corpus import akta_entries, load_corpus
    from backend.grid.types import MULTI_DOC_FAMILIES
    svc = Service(runs_dir=REPO / "runs")
    kw = ({"docs": [load_corpus(i) for i, e in akta_entries().items() if e.get("family", family) == family]}
          if family in MULTI_DOC_FAMILIES else {"doc": load_corpus()})
    sb = SchemaBinding.from_store(REPO / "runs", family)
    plan = make_plan(family, tokenizer=svc.tok(), butir_dir=REPO / "data" / "butir", runs_dir=REPO / "runs", create_split=False,
                     headers=load_header_binding(runs_dir=REPO / "runs", family=family), schemas=sb if sb.records else None, **kw)
    stored = {n[:-5] for n in (p.name for p in grid.glob("*.json"))}
    assert plan.key in stored, f"main plan key {plan.key} for {family} is not among runs/grid"
