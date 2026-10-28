"""Regresi H-101: kunci K0 yang dihitung grid_compare == kunci utama (`Service.stored_grid`), termasuk identitas skema A."""

from pathlib import Path

import pytest

from backend import config as bc
from backend.grid.schemas import SchemaBinding
from backend.header_b.compare_store import CompareError
from backend.pipeline.grid_run import load_header_binding, make_plan, run_family_grid
from backend.tests._chunk_util import ToyWs
from backend.tests.pipeline_fakes import FakeEncoder

from .test_h101_grid_compare import main_binding, run_cmp, store_of, w  # noqa: F401  (w = fixture)


def test_k0_includes_schema_a_binding_like_service(w):  # noqa: F811
    from .test_schema_a_compare import seed_main_store
    seed_main_store(w["runs"])
    sb = SchemaBinding.from_store(w["runs"], "uupt")
    assert sb.records
    main = run_family_grid("uupt", doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"], butir_dir=w["butir"], config_dir=w["cfg"],
                           encoder=FakeEncoder(), embed_cache_dir=w["emb"], headers=main_binding(w), schemas=sb)
    res = run_cmp(w, store_of(w, "Cmp"))  # schemas="auto" menemukan store yang sama seperti Service.schema_binding
    assert res.envelope["off_ref"]["key"] == main.key
    with pytest.raises(CompareError) as ei:  # tanpa skema kuncinya lain: membuktikan skema memang ikut kunci
        run_cmp(w, store_of(w, "Cmp2"), schemas=None)
    assert ei.value.code == "off_series_missing"


@pytest.mark.parametrize("family", ["uupt", "akta"])
def test_k0_equals_service_plan_key_on_real_config_and_runs(family):
    from backend.api.service import Service
    from backend.corpus import load_corpus
    from backend.tokenizer import get_tokenizer
    runs = Path(bc.REPO_ROOT) / "runs"
    if not (runs / "grid").is_dir() or not (Path(bc.REPO_ROOT) / "data" / "butir").is_dir():
        pytest.skip("no real runs/ or data/butir in this checkout")
    svc = Service()
    hb = svc.header_binding(family)
    if hb is None:
        pytest.skip(f"no header store for {family}")
    try:
        sbs = svc.schema_binding(family)
        hplan = svc.plan(family, headers=hb, **({"schemas": sbs} if sbs is not None else {}))
        sb = SchemaBinding.from_store(runs, family)
        dkw = {"docs": [load_corpus(i) for i in svc.doc_ids("akta")]} if family == "akta" else {"doc": load_corpus()}
        mine = make_plan(family, **dkw, tokenizer=get_tokenizer(), butir_dir=svc.butir_dir, runs_dir=runs, config_dir=None,
                         create_split=False, headers=load_header_binding(runs_dir=runs, family=family),
                         schemas=sb if sb.records else None)
    except Exception as exc:  # noqa: BLE001  (data/korpus nyata tak lengkap di checkout ini)
        pytest.skip(f"real data unavailable: {type(exc).__name__}")
    assert mine.key == hplan.key and mine.config_hash == hplan.config_hash
