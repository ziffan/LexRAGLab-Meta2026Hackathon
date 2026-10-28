"""W63 (Tier 1): store header B per keluarga. Akta di `runs/headers/akta/`, UU PT tetap di `runs/headers/`; `content_hash`
UU PT (komponen `config_hash` grid, A10) tidak boleh berubah oleh header akta (regresi 82ae86f). Tanpa jaringan/Model API;
`runs/` repo hanya dibaca."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import config
from backend.corpus import akta_entries, load_corpus
from backend.grid.expand import expand_grid
from backend.grid.headers import DirHeaderStore, HeaderMissingError, header_store_dir
from backend.grid.schemas import SchemaBinding, bind_schema_versions
from backend.header_b import __main__ as hb_main
from backend.header_b.family import plan_prepared, prepare_family
from backend.header_b.run import load_all_configs
from backend.pipeline.grid_run import load_header_binding
from backend.pipeline.multi import MultiDocPipeline
from backend.tokenizer import get_tokenizer

RUNS = config.REPO_ROOT / "runs"
# Dihitung dari store UU PT HEAD 77dab56 (prompt B v2, 9904b5355886), sebelum perbaikan W63.
UUPT_STORE_HASH = "d21f0e4b62476d7e826cf1ed291c67e1151efb01f17cdb2ed81353fd042e6ddf"
SOURCES = ("pasal", "fixed_size", "structure_schema")


def _need_repo_headers():
    if not (RUNS / "headers" / "akta").is_dir():
        pytest.skip("runs/headers/akta tidak ada")


# ---------------------------------------------------------------- 1. UU PT byte-identik
def test_path_function_uupt_unchanged_akta_separate(tmp_path):
    assert header_store_dir(tmp_path) == tmp_path / "headers" == header_store_dir(tmp_path, "uupt")
    assert header_store_dir(tmp_path, "akta") == tmp_path / "headers" / "akta"


def test_uupt_store_content_hash_equals_head_77dab56():
    _need_repo_headers()
    b = load_header_binding(runs_dir=RUNS)
    assert b.store.headers_dir == RUNS / "headers" and b.store.content_hash() == UUPT_STORE_HASH
    assert b.identity()["store"] == UUPT_STORE_HASH
    assert load_header_binding(runs_dir=RUNS, family="uupt").store.content_hash() == UUPT_STORE_HASH


# ---------------------------------------------------------------- 2. penulisan CLI akta tidak menyentuh store UU PT
def test_cli_akta_write_path_does_not_change_uupt_content_hash(tmp_path, monkeypatch):
    """Jalur tulis CLI `--family akta` ditangkap dari `run_family` (klien palsu, tanpa Model API); penulisan nyata dilakukan
    di salinan `tmp_path` dengan jalur relatif yang sama terhadap `runs/headers`."""
    p12 = load_header_binding(runs_dir=RUNS).prompt_hash[:12]
    base = tmp_path / "headers"
    seed = base / "pasal" / p12
    seed.mkdir(parents=True)
    (seed / "uupt-c1.json").write_text(json.dumps({"chunk_id": "uupt-c1", "header": "H"}), encoding="utf-8", newline="\n")
    before = DirHeaderStore(base, p12, tmp_path / "r").content_hash()
    seen = {}

    def spy(client, prepared, *, headers_dir, **kw):
        seen["dir"] = headers_dir
        rel = Path(headers_dir).relative_to(RUNS / "headers")
        for src in ("pasal", "fixed_size", "structure_schema"):  # penulisan nyata di salinan, jalur sama seperti caller.store_dir
            d = base / rel / src / p12
            d.mkdir(parents=True, exist_ok=True)
            (d / "akta-x.json").write_text(json.dumps({"chunk_id": "akta-x", "header": "HA"}), encoding="utf-8", newline="\n")
        return {"stored": 1, "stopped": None, "failed": {}}

    monkeypatch.setattr(hb_main, "run_family", spy)
    monkeypatch.setattr(hb_main, "_client", lambda *a, **k: object())
    monkeypatch.setattr(hb_main, "precheck", lambda *a, **k: None)
    monkeypatch.setattr(hb_main, "project_family", lambda *a, **k: {})
    monkeypatch.setattr(hb_main, "_fmt_family", lambda res: "")
    assert hb_main.main(["--family", "akta", "--chunker", "fixed_size", "--doc", "akta-03", "--sample", "1"]) == 0
    assert seen["dir"] == RUNS / "headers" / "akta"
    assert DirHeaderStore(base, p12, tmp_path / "r").content_hash() == before  # UU PT tak berubah
    assert (base / "akta" / "fixed_size" / p12 / "akta-x.json").is_file()


# ---------------------------------------------------------------- 3. grid akta header-on membaca store akta repo
def _akta_header_on(chunker):
    gcfg = config.load("grid")
    sb = SchemaBinding.from_store(RUNS, "akta")
    ss = bind_schema_versions(expand_grid(gcfg, "akta"), sb)
    return next(s for s in ss if s.header_b and s.chunker == chunker and s.retrieval_mode == "bm25")


def test_akta_grid_header_on_finds_repo_akta_headers_for_three_sources():
    _need_repo_headers()
    hb = load_header_binding(runs_dir=RUNS, family="akta")
    assert hb.store.headers_dir == RUNS / "headers" / "akta"
    ids = list(akta_entries())
    pipe = MultiDocPipeline([load_corpus(i) for i in ids], tokenizer=get_tokenizer(), retrieval_cfg=config.load("retrieval"),
                            grid_cfg=config.load("grid"), encoder=object(), headers=hb,
                            schemas=SchemaBinding.from_store(RUNS, "akta"))
    for chunker in ("structure_handwritten", "fixed_size", "structure_schema"):
        s = _akta_header_on(chunker)
        for d in ids:
            if (d, chunker) == ("akta-03", "fixed_size"):  # gagal jujur H-081: 1 unit tanpa header
                with pytest.raises(HeaderMissingError):
                    pipe.pipes[d].headers_for(s)
            else:
                assert pipe.pipes[d].headers_for(s), (d, chunker)
    # store bersama lama (runs/headers) tidak punya header akta
    old = MultiDocPipeline([load_corpus(ids[0])], tokenizer=get_tokenizer(), retrieval_cfg=config.load("retrieval"),
                           grid_cfg=config.load("grid"), encoder=object(), headers=load_header_binding(runs_dir=RUNS),
                           schemas=SchemaBinding.from_store(RUNS, "akta"))
    with pytest.raises(HeaderMissingError):
        old.pipes[ids[0]].headers_for(_akta_header_on("structure_handwritten"))


def test_akta_stored_check_and_projection_count_one_unit_left():
    _need_repo_headers()
    hc, *_rest, rcfg, gcfg = load_all_configs()
    rec = SchemaBinding.from_store(RUNS, "akta").active()
    ids = list(akta_entries())
    prepared = prepare_family(ids, ["pasal", "fixed_size", "structure_schema"], tokenizer=get_tokenizer(), header_cfg=hc,
                              retrieval_cfg=rcfg, grid_cfg=gcfg, schema_record=rec)
    left = [(d, s) for d, srcs in prepared.items() for s, p in srcs.items()
            for _ in plan_prepared(p, header_store_dir(RUNS, "akta")).call]
    assert left == [("akta-03", "fixed_size")]
    stale = sum(len(plan_prepared(p, RUNS / "headers").call) for srcs in prepared.values() for p in srcs.values())
    assert stale > 100  # store bersama lama: hampir semua unit akta tampak belum tersimpan


# ---------------------------------------------------------------- perbaikan W65 (mutan M3, M6)
def test_grid_run_cli_with_headers_binds_family_store(monkeypatch):
    """M3: `grid_run.main --family akta --with-headers` memberi run_family_grid binding store akta (bukan UU PT)."""
    _need_repo_headers()
    from backend.pipeline import grid_run
    seen = {}

    def spy(family, **kw):
        seen["family"], seen["headers"] = family, kw["headers"]
        return object()

    monkeypatch.setattr(grid_run, "run_family_grid", spy)
    monkeypatch.setattr(grid_run, "summarize", lambda res: [])
    assert grid_run.main(["--family", "akta", "--with-headers", "--runs-dir", str(RUNS)]) == 0
    assert seen["family"] == "akta" and seen["headers"].store.headers_dir == RUNS / "headers" / "akta"
    seen.clear()
    assert grid_run.main(["--family", "uupt", "--with-headers", "--runs-dir", str(RUNS)]) == 0
    assert seen["headers"].store.headers_dir == RUNS / "headers"


def test_cli_project_only_reads_akta_store_and_writes_no_files(monkeypatch, capsys):
    """M6: `--project-only` memproyeksikan atas store akta (1 unit tersisa), bukan store bersama; tulis proyeksi dinonaktifkan."""
    _need_repo_headers()
    seen = {}
    real = hb_main.project_family

    def spy(prepared, headers_dir, *a, **k):
        seen["dir"] = headers_dir
        seen["res"] = real(prepared, headers_dir, *a, **k)
        return seen["res"]

    monkeypatch.setattr(hb_main, "project_family", spy)
    monkeypatch.setattr(hb_main, "write_projection", lambda *a, **k: None)
    assert hb_main.main(["--family", "akta", "--chunker", "fixed_size", "--project-only"]) == 0
    assert seen["dir"] == RUNS / "headers" / "akta"
    assert seen["res"]["total"]["to_call"] == 1 and seen["res"]["per_doc"]["akta-03"]["sources"]["fixed_size"]["to_call"] == 1
