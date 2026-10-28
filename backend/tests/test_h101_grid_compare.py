"""H-101 bagian 4 (skenario M3.2-open-weight-B S2 (3), S6 (grid), S13, S14 (c), S15, S16 (a), S17 (d)): grid ulang per model pembanding,
amplop terpisah, kunci memuat identitas model, himpunan kembaran sama, laporan berkas, laporan utama byte-identik.
Dokumen mainan U, store header di memori, encoder palsu. Tanpa Model API."""

import hashlib
import json
import re
from fractions import Fraction

import pytest

from backend import config as bc
from backend.grid.expand import expand_grid
from backend.grid.headers import HeaderBinding, MemoryHeaderStore, twin_key
from backend.grid.types import GridPoint, Setting
from backend.header_b.compare_store import CompareError, build_identity
from backend.pipeline import grid_compare as gc
from backend.pipeline.grid_run import make_plan, run_family_grid
from backend.pipeline.pipeline import Pipeline
from backend.tests._chunk_util import ToyWs, u_doc
from backend.tests.pipeline_fakes import FakeEncoder, toy_config_dir, write_toy_butir

from .h101_helpers import model_b
from .test_h101_gpulock import ALIVE, hold

M = model_b()


@pytest.fixture()
def w(tmp_path):
    doc = u_doc()
    cfg = toy_config_dir(tmp_path / "cfg")
    butir = tmp_path / "butir"
    write_toy_butir(butir, doc.clean_sha256)
    return {"doc": doc, "cfg": cfg, "butir": butir, "runs": tmp_path / "runs", "emb": tmp_path / "emb"}


def store_of(w, prefix, *, skip_chunker=None, run_id="bT"):
    gcfg, rcfg = bc.load("grid", w["cfg"]), bc.load("retrieval", w["cfg"])
    pipe = Pipeline(w["doc"], tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg)
    st = MemoryHeaderStore({}, {run_id: w["doc"].clean_sha256})
    for s in expand_grid(gcfg, "uupt"):
        if s.header_b or s.chunker not in ("structure_handwritten", "fixed_size") or s.chunker == skip_chunker:
            continue
        gran = "fixed_size" if s.chunker == "fixed_size" else "ayat"
        for c in pipe.chunk_set(s).chunks:
            st.records[c.chunk_id] = {"chunk_id": c.chunk_id, "header": f"{prefix} {c.start}", "granularity": gran, "run_id": run_id}
    return st


def main_binding(w):
    return HeaderBinding(store_of(w, "Hdr"), "ayat", "frontier_only", "ph", "meta-model")


def ident(profile, **over):
    i = build_identity(profile, M["profiles"][profile], M, prompt_hash="ph", max_header_tokens=40, schema_max_length_chars=190)
    i.update(over)
    return i


def run_main(w, binding=None):
    return run_family_grid("uupt", doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"], butir_dir=w["butir"], config_dir=w["cfg"],
                           encoder=FakeEncoder(), embed_cache_dir=w["emb"], headers=binding or main_binding(w))


def run_cmp(w, store, profile="baseten_open", identity=None, encoder=None, **kw):
    return gc.run_compare_grid("uupt", profile=profile, model_cfg=M, doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"],
                               butir_dir=w["butir"], config_dir=w["cfg"], encoder=encoder or FakeEncoder(), embed_cache_dir=w["emb"],
                               main_headers=main_binding(w), compare_store=store, identity=identity or ident(profile), **kw)


def tree(root):
    return sorted((p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.rglob("*") if p.is_file())


def on_ids(env):
    return {s["setting_id"] for s in env["settings_run"] if s["header_b"]}


# ------------------------------------------------------------------------------------------------ S13 (a)-(c), (g), S2 (3)
def test_s13_envelope_separate_same_twin_set_off_ref_empty_selections(w):
    main = run_main(w)
    k0, before_grid = main.key, tree(w["runs"] / "grid")
    raw_main = main.path.read_bytes()
    res = run_cmp(w, store_of(w, "Cmp"))
    assert res.path == w["runs"] / "grid_compare" / "baseten_open" / f"{res.key}.json" and res.key != k0
    assert tree(w["runs"] / "grid") == before_grid and main.path.read_bytes() == raw_main  # R/grid tidak berubah, K0 tidak ditulis
    env = res.envelope
    twins = on_ids(main.envelope)
    assert twins and set(env["settings_requested"]) == twins and on_ids(env) == twins  # himpunan kembaran sama
    assert env["off_ref"] == {"key": k0, "path": f"runs/grid/{k0}.json"}
    assert all(p["header_b"] is True and p["setting_id"] in twins for p in env["points"])  # tanpa titik off di amplop pembanding
    assert env["selections"] == {} and env["failed_settings"] == []
    assert json.loads(main.path.read_bytes())["selections"] == main.envelope["selections"]  # profil terpilih utama tidak berubah
    assert env["label"] == "Header B: Spark Open (Baseten)" and env["kind"] == "grid_compare"
    # frontier pembanding = off amplop utama + on pembanding; id frontier boleh menunjuk setting off utama
    ids = {s["setting_id"] for s in main.envelope["settings_run"]} | twins
    assert all(set(f["point_ids"]) <= ids for f in env["frontiers"])
    # S13 (g): idempoten, nol hitung baru, byte sama
    enc = FakeEncoder()
    raw = res.path.read_bytes()
    again = run_cmp(w, store_of(w, "Cmp"), encoder=enc)
    assert again.cache_hit and enc.encode_calls == 0 and res.path.read_bytes() == raw
    # S2 (3): grid utama dijalankan ulang setelah run pembanding -> cache hit, amplop ber-byte sama
    main2 = run_main(w)
    assert main2.cache_hit and main.path.read_bytes() == raw_main and main2.key == k0
    plan = make_plan("uupt", doc=w["doc"], tokenizer=ToyWs(), butir_dir=w["butir"], runs_dir=w["runs"], config_dir=w["cfg"],
                     create_split=False, headers=main_binding(w))
    assert plan.key == k0 and "compare" not in main_binding(w).identity()  # identitas utama tidak memuat blok compare


def test_s13d_key_depends_on_header_text_and_model_pin_not_on_run_id(w):
    run_main(w)
    base = run_cmp(w, store_of(w, "Cmp"))
    same_but_run_id = run_cmp(w, store_of(w, "Cmp", run_id="bOTHER"))
    assert same_but_run_id.key == base.key and same_but_run_id.cache_hit  # A10: run_id tidak ikut kunci
    assert run_cmp(w, store_of(w, "Zzz")).key != base.key  # teks header beda
    keys = {base.key}
    for over in ({"quantization": "Q8_0"}, {"effort": "medium"}, {"provider": "other"}, {"model": "meta-models/other"}):
        k = run_cmp(w, store_of(w, "Cmp"), identity=ident("baseten_open", **over)).key
        assert k not in keys
        keys.add(k)
    g1 = run_cmp(w, store_of(w, "Cmp"), profile="glimmer_local").key  # profil lain, teks sama: beda (identitas model)
    assert g1 not in keys


def test_s13e_missing_header_is_failed_setting_not_a_point_and_frontier_excludes_it(w):
    main = run_main(w)
    res = run_cmp(w, store_of(w, "Cmp", skip_chunker="structure_handwritten"))  # toy: semua kembaran header-on berasal dari handwritten
    env = res.envelope
    by_id = {s["setting_id"]: s for s in main.envelope["settings_run"]}
    fs = env["failed_settings"]
    assert fs and all(f["reason"] == "header_missing" and f["chunk_id"] for f in fs)
    failed = {f["setting_id"] for f in fs}
    assert failed.isdisjoint({p["setting_id"] for p in env["points"]}) and failed.isdisjoint(on_ids(env))
    assert failed == set(env["settings_requested"]) and env["points"] == []  # semua gagal jujur: tanpa GridPoint
    assert res.envelope["record"]["failed_settings"] == fs
    assert "Cmp" not in json.dumps({k: v for k, v in env.items() if k in ("points", "metrics", "frontiers")})  # teks header tak bocor
    assert all(i in (on_ids(env) | failed) for i in env["settings_requested"])
    assert env["coverage"] == {"sources_run": [], "sources_not_run": ["ayat"]}
    assert "partial coverage" in gc.render_report(env)


def test_s17d_partial_coverage_one_source_run_two_header_missing():
    def st(sid, chunker):
        return Setting(sid, "uupt", chunker, None, None, None, "bm25", True, 2000)

    twins = [st("sA+hdr", "structure_handwritten"), st("sB+hdr", "fixed_size"), st("sC+hdr", "structure_schema")]
    binding = HeaderBinding(MemoryHeaderStore(), "pasal", "frontier_only", "ph", "m")
    pts = [pt("sA+hdr", 100, "1/2")]
    assert gc.coverage_of(twins, pts, binding) == {"sources_run": ["pasal"], "sources_not_run": ["fixed_size", "structure_schema"]}
    env = {"label": "Header B: Glimmer (local)", "family": "uupt", "key": "K", "off_ref": {"key": "K0", "path": "runs/grid/K0.json"},
           "compare": {"provider": "lmstudio_local", "model": "m", "quantization": "Q4_K_M", "effort": "high"},
           "coverage": gc.coverage_of(twins, pts, binding), "settings_run": [{"setting_id": "sA+hdr", "chunker": "structure_handwritten",
                                                                               "retrieval_mode": "bm25"}],
           "points": [{"setting_id": "sA+hdr", "budget_tokens": 2000, "split": "tune", "mean_span_recall": 0.5,
                       "exact": {"mean_span_recall": "1/2", "mean_retrieved_tokens": "100/1"}, "mean_retrieved_tokens": 100.0, "dominated": False}],
           "frontiers": [], "failed_settings": [{"setting_id": "sB+hdr", "reason": "header_missing", "chunk_id": "c9"},
                                                {"setting_id": "sC+hdr", "reason": "header_missing", "chunk_id": "c8"}]}
    md = gc.render_report(env)
    assert "partial coverage" in md and "sources run: pasal; sources not run: fixed_size, structure_schema" in md
    assert any(ln.startswith("| Header B: Glimmer (local) (partial coverage)") for ln in md.splitlines())


def test_s13f_off_series_missing_raises_before_writing(w):
    main = run_main(w)
    main.path.unlink()
    with pytest.raises(CompareError) as ei:
        run_cmp(w, store_of(w, "Cmp"))
    assert ei.value.code == "off_series_missing"
    assert not (w["runs"] / "grid_compare").exists()


def test_s13_identity_missing_without_store_is_a_clear_error(w):
    run_main(w)
    with pytest.raises(CompareError) as ei:
        gc.run_compare_grid("uupt", profile="baseten_open", model_cfg=M, doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"],
                            butir_dir=w["butir"], config_dir=w["cfg"], encoder=FakeEncoder(), main_headers=main_binding(w))
    assert ei.value.code == "compare_store_missing"


def test_comparison_profile_rules_apply_to_grid_runs(w):
    run_main(w)
    for bad in ("meta", "c_only", "openrouter_dev", "nope"):
        with pytest.raises(CompareError):
            run_cmp(w, store_of(w, "Cmp"), profile=bad, identity=ident("baseten_open"))


# ------------------------------------------------------------------------------------------------ S13 (h)
def pt(sid, tokens, recall):
    return GridPoint(sid, "tune", 2000, Fraction(recall), Fraction(0), Fraction(0), Fraction(tokens), {"covered": 0, "total": 0}, 0,
                     family="uupt", n_gold=4)


def test_s13h_comparison_frontier_numbers():
    off = [pt("s03", 200, "1/4"), pt("s07", 300, "1/2"), pt("s11", 400, "3/4")]
    on = [pt("s03+hdr", 210, "1/2"), pt("s07+hdr", 310, "3/4"), pt("s11+hdr", 420, "3/4")]
    points, fronts = gc.comparison_frontier(off, on, "KB")
    (f,) = fronts
    assert set(f.point_ids) == {"s03", "s03+hdr", "s07+hdr"}
    assert {p.setting_id for p in points if p.dominated} == {"s07", "s11", "s11+hdr"}
    # frontier utama (hanya off + on Contributor, tanpa titik pembanding) tidak berubah oleh keberadaan titik pembanding
    _, main_fronts = gc.comparison_frontier(off, [], "K0")
    assert set(main_fronts[0].point_ids) == {"s03", "s07", "s11"}


# ------------------------------------------------------------------------------------------------ S14 (c)
def test_s14c_compare_grid_record_carries_profile_main_record_stays_null(w):
    main = run_main(w)
    res = run_cmp(w, store_of(w, "Cmp"), profile="glimmer_local")
    r, rm = res.envelope["record"], main.envelope["record"]
    assert (r["provider"], r["model"], r["quantization"], r["effort"], r["kind"], r["cost_usd_micros"]) == (
        "lmstudio_local", "meta/muse-glimmer", "Q4_K_M", "high", "grid", 0)
    assert r["failed_settings"] == [] and r["cache_key"] == res.key
    assert (rm["provider"], rm["model"], rm["quantization"], rm["effort"]) == (None, None, None, None)


# ------------------------------------------------------------------------------------------------ S15
def test_s15a_report_labels_every_row_and_reads_only_the_compare_envelope(w):
    run_main(w)
    for profile, label in (("baseten_open", "Header B: Spark Open (Baseten)"), ("glimmer_local", "Header B: Glimmer (local)")):
        res = run_cmp(w, store_of(w, "Cmp"), profile=profile)
        md_path, js_path = gc.write_report(w["runs"], profile, res.envelope)
        assert md_path == w["runs"] / "grid_compare" / profile / f"report-{res.key}.md"
        md = md_path.read_text(encoding="utf-8")
        assert md.startswith(f"# {label}")
        rows = [ln for ln in md.splitlines() if ln.startswith("| ") and "Series" not in ln and not ln.startswith("|---") and "Reason" not in ln]
        point_rows = [ln for ln in rows if re.match(r"\| Header B:", ln)]
        assert point_rows and all(ln.startswith(f"| {label}") for ln in point_rows)
        assert not re.search(r"header B on|\bHeader B\b(?!:)", md.replace(label, ""), re.I), "every Header B mention must carry the full profile label"
        assert json.loads(js_path.read_text(encoding="utf-8"))["label"] == label
        assert "Not a reported number" in md
    assert not (w["runs"] / "grid_compare" / "x").exists()


def test_s15_report_marks_partial_coverage_and_failed_settings(w):
    run_main(w)
    res = run_cmp(w, store_of(w, "Cmp", skip_chunker="structure_handwritten"), profile="glimmer_local")
    md = gc.render_report(res.envelope)
    assert "partial coverage" in md and "header_missing" in md and "sources not run: ayat" in md


from .test_answer_api import svc  # noqa: E402,F401  (fixture modul: korpus nyata, encoder palsu)


def test_s15b_main_snapshot_is_byte_identical_with_and_without_comparison_data(svc, tmp_path):
    from .spark_fakes import synth
    from .test_m25_w6_cli import make
    c, _tr, s = make(svc, tmp_path)
    for fam in ("uupt", "akta"):
        a = c.get(f"/api/families/{fam}/snapshot")
        assert a.status_code == 200
        runs = s.runs_dir
        (runs / "headers_compare" / "baseten_open" / "pasal" / ("a" * 12)).mkdir(parents=True, exist_ok=True)
        (runs / "headers_compare" / "baseten_open" / "pasal" / ("a" * 12) / "CH-U1.json").write_text(
            json.dumps({"chunk_id": "CH-U1", "granularity": "pasal", "header": "H", "run_id": "r"}), encoding="utf-8")
        (runs / "grid_compare" / "baseten_open").mkdir(parents=True, exist_ok=True)
        (runs / "grid_compare" / "baseten_open" / "KB.json").write_text(json.dumps({"key": "KB", "record": {}, "points": []}), encoding="utf-8")
        synth(runs, "b", "baseten", 20_550, run_id=f"cmp-baseten-{fam}")
        synth(runs, "b", "lmstudio_local", 0, run_id=f"cmp-glimmer-{fam}")
        b = c.get(f"/api/families/{fam}/snapshot")
        assert hashlib.sha256(a.content).hexdigest() == hashlib.sha256(b.content).hexdigest()


def test_s15e_main_readers_never_touch_the_compare_directories():
    """README/U7/snapshot/replay-export tidak membaca `*_compare` (AGENTS.md: tanpa angka karangan)."""
    from pathlib import Path
    root = Path(bc.REPO_ROOT) / "backend"
    offenders = []
    for sub in ("api", "replay"):
        for p in (root / sub).rglob("*.py"):
            t = p.read_text(encoding="utf-8")
            if re.search(r"grid_compare|headers_compare|_compare\b", t):
                offenders.append(p.name)
    assert offenders == []
    from backend.api.routers.system import grid_records, all_records
    assert callable(grid_records) and callable(all_records)


def test_s15b_grid_records_and_header_view_ignore_compare_dirs(w, tmp_path):
    from backend.api.routers.snapshot import header_b_view
    from backend.api.routers.system import grid_records
    main = run_main(w)
    before = ([r.to_dict() for r in grid_records(w["runs"])], header_b_view(w["runs"]), tree(w["runs"] / "grid"))
    (w["runs"] / "headers_compare" / "baseten_open" / "pasal" / ("a" * 12)).mkdir(parents=True)
    (w["runs"] / "headers_compare" / "baseten_open" / "pasal" / ("a" * 12) / "CH-U1.json").write_text(
        json.dumps({"chunk_id": "CH-U1", "granularity": "pasal", "header": "H", "tokens_local": 1, "prompt_version": "v2", "run_id": "r"}), encoding="utf-8")
    run_cmp(w, store_of(w, "Cmp"))
    gc.write_report(w["runs"], "baseten_open", run_cmp(w, store_of(w, "Cmp")).envelope)
    after = ([r.to_dict() for r in grid_records(w["runs"])], header_b_view(w["runs"]), tree(w["runs"] / "grid"))
    assert before == after and len(before[0]) == 1 and before[0][0]["cache_key"] == main.key


# ------------------------------------------------------------------------------------------------ S16 (a) untuk runner grid pembanding
def test_s16a_compare_grid_refuses_while_glimmer_holds_before_encoder_load(w):
    all_scope = HeaderBinding(store_of(w, "Hdr"), "ayat", "all", "ph", "meta-model")  # scope all: kembaran dense/hybrid ikut -> encoder
    run_main(w, all_scope)
    hold(w["runs"], "glimmer-b")
    loads = []

    def factory():
        loads.append(1)
        return FakeEncoder()

    with pytest.raises(Exception) as ei:
        gc.run_compare_grid("uupt", profile="baseten_open", model_cfg=M, doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"],
                            butir_dir=w["butir"], config_dir=w["cfg"], encoder_factory=factory, embed_cache_dir=w["emb"].parent / "emb-spy", main_headers=all_scope,
                            compare_store=store_of(w, "Cmp"), identity=ident("baseten_open"), gpu_lock=True, gpu_pid_alive=ALIVE)
    assert getattr(ei.value, "code", None) == "gpu_busy" and loads == []
    assert not (w["runs"] / "grid_compare").exists()
    from backend.gpulock import lock_path, read_lock
    assert read_lock(lock_path(w["runs"]))["holder"] == "glimmer-b"
    # sesudah dilepas: jalan, kunci diambil selama encoder dipakai lalu dilepas
    lock_path(w["runs"]).unlink()
    seen = []

    class Spy(FakeEncoder):
        def encode(self, texts):
            seen.append(read_lock(lock_path(w["runs"])))
            return super().encode(texts)

    gc.run_compare_grid("uupt", profile="baseten_open", model_cfg=M, doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"],
                        butir_dir=w["butir"], config_dir=w["cfg"], encoder=Spy(), embed_cache_dir=w["emb"].parent / "emb-spy", main_headers=all_scope,
                        compare_store=store_of(w, "Cmp"), identity=ident("baseten_open"), gpu_lock=True, gpu_pid_alive=ALIVE)
    assert seen and seen[0]["holder"] == "embedding" and not lock_path(w["runs"]).exists()
