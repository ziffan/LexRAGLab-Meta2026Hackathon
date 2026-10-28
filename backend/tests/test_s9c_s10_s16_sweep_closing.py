"""M3.2-effort-sweep (H-103 S3 bagian C): S9(c) konsumen utama tidak membaca jalur sapuan (spy pembacaan), S10(a)(d) validator
40/190 dan guard cache untuk profil sapuan, S16(e)(f) GPU lock runner Glimmer sapuan dan gpu_busy grid dense. Transport palsu."""

import builtins
import json
from pathlib import Path

import pytest

from backend.gpulock import GpuBusy, lock_path, read_lock
from backend.header_b import caller
from backend.header_b.compare_store import compare_store_dir
from backend.schema_a import SchemaStore, compare_a
from backend.spark import ConfigInvalid
from backend.spark.runrecord import RunRecord  # noqa: F401

from .h101_helpers import PROMPT12, hc_b, make_prepared, words
from .m25_fakes import env_m25
from .s8_potret import seed_main, sweep_artifacts
from .spark_fakes import Resp
from .sweep_b_helpers import args, go_sweep, run_main, sweep_cfg, sweep_rig
from .test_h101_compare_run import usage_seq
from .test_h101_gpulock import ALIVE, hold
from .test_answer_api import svc  # noqa: F401
from .test_s13_s14_s20_a_c_sweep import SweepRun, a_default

BAD = ("headers_compare", "grid_compare", "compare_report", "/compare/")


# ------------------------------------------------------------------------------------------------ S9 (c)
def test_s9c_main_consumers_never_touch_sweep_paths(tmp_path, monkeypatch):
    from backend.answer.compare_c import stored_answers
    from backend.api.routers.snapshot import grid_view
    from backend.grid.headers import DirHeaderStore
    from backend.spark import Ledger
    from backend.spark.settings import load_configs
    from .s8_potret import K0, PH
    R = tmp_path / "runs"
    seed_main(R)
    sweep_artifacts(R)
    put = (R / "headers_compare" / "sweep_meta_medium" / "pasal" / PH[:12])
    put.mkdir(parents=True)
    (put / "CH-U1.json").write_text("{}", encoding="utf-8")
    touched: list[str] = []
    orig_open, orig_rb, orig_rt = builtins.open, Path.read_bytes, Path.read_text
    orig_glob, orig_rglob, orig_iter = Path.glob, Path.rglob, Path.iterdir

    def note(p):
        touched.append(str(p).replace("\\", "/"))

    def sopen(f, *a, **k):
        note(f)
        return orig_open(f, *a, **k)

    def srb(self):
        note(self)
        return orig_rb(self)

    def srt(self, *a, **k):
        note(self)
        return orig_rt(self, *a, **k)

    def sglob(self, pat):
        note(self / pat)
        return orig_glob(self, pat)

    def srglob(self, pat):
        note(self / pat)
        return orig_rglob(self, pat)

    def siter(self):
        note(self)
        return orig_iter(self)

    monkeypatch.setattr(builtins, "open", sopen)
    monkeypatch.setattr(Path, "read_bytes", srb)
    monkeypatch.setattr(Path, "read_text", srt)
    monkeypatch.setattr(Path, "glob", sglob)
    monkeypatch.setattr(Path, "rglob", srglob)
    monkeypatch.setattr(Path, "iterdir", siter)
    # konsumen utama: potret R3 (grid_view atas amplop utama), 2x2 C utama, store skema utama, store header utama, ledger utama
    env = json.loads((R / "grid" / f"{K0}.json").read_text(encoding="utf-8"))
    grid_view(env, 2000)
    stored_answers(R / "answers", "meta")
    DirHeaderStore(R / "headers", PH, R).content_hash()
    model, _ = load_configs()
    Ledger(R).spent_pool("meta", {}, model_cfg=model)
    from backend.header_b.compare_store import tree_listing
    tree_listing(R / "grid")
    bad = [t for t in touched if any(b in t for b in BAD)]
    assert bad == [] and touched  # spy hidup (ada pembacaan) tetapi nol pembacaan jalur sapuan


# ------------------------------------------------------------------------------------------------ S10 (a)
def test_s10a_validator_limits_unchanged_for_sweep_profile(tmp_path, monkeypatch):
    seen_tokens, seen_len = [], []
    orig_v, orig_s = caller.make_validator, caller.header_schema
    monkeypatch.setattr(caller, "make_validator", lambda u, t, n: (seen_tokens.append(n), orig_v(u, t, n))[1])
    monkeypatch.setattr(caller, "header_schema", lambda n=None: (seen_len.append(n), orig_s(n))[1])
    rig, sw = sweep_rig(tmp_path, "sweep_meta_high")
    go_sweep(rig, sw, make_prepared(1), compare_store_dir(rig.runs, "sweep_meta_high"), profile="sweep_meta_high", max_attempts=1, gate=None)
    assert set(seen_tokens) == {40} and set(seen_len) == {190}


@pytest.mark.parametrize("header,stored,code", [(words(40, 151), 1, None), (words(41), 0, "semantic_invalid"), (words(40, 152), 0, "schema_invalid")])
def test_s10a_40_tokens_190_chars_accepted_41_and_191_rejected_for_effort_high(tmp_path, header, stored, code):
    rig, sw = sweep_rig(tmp_path, "sweep_meta_high", {"CH-U1": [header]})
    d = compare_store_dir(rig.runs, "sweep_meta_high")
    s = go_sweep(rig, sw, make_prepared(1), d, profile="sweep_meta_high", max_attempts=1, gate=None)
    assert s["stored"] == stored
    from backend.spark import store
    errs = [r.error["code"] for r in store.load_records(rig.runs) if r.status == "error"]
    assert errs == ([code] if code else [])
    if code == "semantic_invalid":
        assert (d / "pasal" / PROMPT12 / "rejected" / "CH-U1.1.json").is_file()  # effort tinggi tidak melonggarkan


# ------------------------------------------------------------------------------------------------ S10 (d)
def test_s10d_cache_guard_active_for_responses_sweep_and_skipped_for_glimmer(tmp_path):
    rig, sw = sweep_rig(tmp_path / "ok", "sweep_baseten_high", usage=usage_seq(lambda k: 38_000))
    s = go_sweep(rig, sw, make_prepared(12), compare_store_dir(rig.runs, "sweep_baseten_high"), profile="sweep_baseten_high", gate=None)
    assert s["stopped"] is None and s["cache_guard"] == "active" and s["stored"] == 12  # tepat 4/5 lanjut
    rig2, sw2 = sweep_rig(tmp_path / "low", "sweep_baseten_high", usage=usage_seq(lambda k: 38_000 if k < 9 else 37_999))
    s2 = go_sweep(rig2, sw2, make_prepared(12), compare_store_dir(rig2.runs, "sweep_baseten_high"), profile="sweep_baseten_high", gate=None)
    assert s2["stopped"] == "cache_ratio_low" and s2["stored"] == 10
    rig3, sw3 = sweep_rig(tmp_path / "meta", "sweep_meta_medium", usage=usage_seq(lambda k: 0))
    s3 = go_sweep(rig3, sw3, make_prepared(12), compare_store_dir(rig3.runs, "sweep_meta_medium"), profile="sweep_meta_medium", gate=None)
    assert s3["stopped"] == "cache_ratio_low"  # guard H-074 juga untuk Contributor sapuan
    rig4, sw4 = sweep_rig(tmp_path / "gl", "sweep_glimmer_medium")
    s4 = go_sweep(rig4, sw4, make_prepared(12), compare_store_dir(rig4.runs, "sweep_glimmer_medium"), profile="sweep_glimmer_medium",
                  gate=None)
    assert s4["cache_guard"] == "skipped" and s4["stopped"] is None


# ------------------------------------------------------------------------------------------------ S16 (e)
def test_s16e_glimmer_sweep_b_takes_gpu_lock_before_request_and_releases(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_glimmer_medium")
    hold(rig.runs, "glimmer-a")
    assert run_main(rig, args("sweep_glimmer_medium", "--max-units", "1"), sweep=sw, pid_alive=ALIVE) == 3 and rig.tr.calls == 0  # gpu_busy
    lock_path(rig.runs).unlink()
    seen = []
    orig = rig.tr.default

    def spy(tr, request):
        seen.append(read_lock(lock_path(rig.runs)))
        return orig(tr, request)

    rig.tr.default = spy
    assert run_main(rig, args("sweep_glimmer_medium", "--max-units", "1"), sweep=sw) == 0
    assert seen and seen[0]["holder"] == "glimmer-b" and not lock_path(rig.runs).exists()


def test_s16e_contributor_and_baseten_sweep_do_not_take_gpu_lock(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium")
    hold(rig.runs, "glimmer-b")
    assert run_main(rig, args("sweep_meta_medium", "--max-units", "1"), sweep=sw) == 0
    assert run_main(rig, args("sweep_baseten_medium", "--confirm-go", "--max-units", "1"), sweep=sw) == 0
    assert read_lock(lock_path(rig.runs))["holder"] == "glimmer-b"


def test_s16e_glimmer_sweep_a_takes_gpu_lock(tmp_path):
    from backend.tests.m25_fakes import chat_body
    from .test_schema_a_compare import body_for
    r = SweepRun(tmp_path, default=Resp(200, chat_body(body_for("uupt"))))
    hold(r.runs, "glimmer-b")
    assert r("--model-profile", "sweep_glimmer_low", "--family", "uupt", pid_alive=ALIVE) == 3 and r.tr.calls == 0
    lock_path(r.runs).unlink()
    assert r("--model-profile", "sweep_glimmer_low", "--family", "uupt") == 0 and not lock_path(r.runs).exists()
    assert [c["schema_version"] for c in SchemaStore(r.runs, compare_profile="sweep_glimmer_low").list("uupt")] == [1]


def test_s16e_glimmer_sweep_c_takes_gpu_lock(svc, tmp_path):
    from backend.answer import compare_c
    from .test_s13_s14_s20_a_c_sweep import _seed, _tr
    from .h101_helpers import budget_b
    from .m25_fakes import m25_model_cfg
    s = _seed(svc, tmp_path)
    hold(s.runs_dir, "glimmer-a")
    tr = _tr()
    rc = compare_c.main(["--model-profile", "sweep_glimmer_medium", "--items", "kontrol-K-02"], service=s, env=env_m25(),
                        model_config=m25_model_cfg(), budget_config=budget_b(), runs_dir=s.runs_dir, transport=tr.transport,
                        out=lambda x: None, probe=lambda u, m: (True, "ok"), sweep_config=sweep_cfg(), pid_alive=ALIVE)
    assert rc == 3 and tr.calls == 0


# ------------------------------------------------------------------------------------------------ S16 (f)
def test_s16f_dense_grid_compare_refuses_gpu_busy_while_glimmer_sweep_runs(tmp_path):
    from backend.tests._chunk_util import ToyWs  # noqa: F401
    from backend.tests.pipeline_fakes import FakeEncoder
    from backend.pipeline import grid_compare as gc
    from .test_h101_grid_compare import M, main_binding, run_main as run_grid_main, store_of, w as _w  # noqa: F401
    from .test_s11_s12_grid_compare_sweep import sident
    import backend.tests.test_h101_grid_compare as tg
    # fixture `w` dibuat manual (fixture pytest tidak dapat dipanggil langsung)
    from backend import config as bc
    from backend.tests._chunk_util import u_doc
    from backend.tests.pipeline_fakes import toy_config_dir, write_toy_butir
    doc = u_doc()
    cfg = toy_config_dir(tmp_path / "cfg")
    butir = tmp_path / "butir"
    write_toy_butir(butir, doc.clean_sha256)
    w = {"doc": doc, "cfg": cfg, "butir": butir, "runs": tmp_path / "runs", "emb": tmp_path / "emb"}
    from backend.grid.headers import HeaderBinding
    all_scope = HeaderBinding(store_of(w, "Hdr"), "ayat", "all", "ph", "meta-model")  # scope all: kembaran dense ikut
    run_grid_main(w, all_scope)
    sw = sweep_cfg()
    sw["compare"] = {"coverage_policy": "strict", "coverage_threshold_pct": 100}
    hold(w["runs"], "glimmer-b")
    loads = []

    def factory():
        loads.append(1)
        return FakeEncoder()

    with pytest.raises(GpuBusy):
        gc.run_compare_grid("uupt", profile="sweep_glimmer_medium", model_cfg=M, doc=doc, tokenizer=ToyWs(), runs_dir=w["runs"],
                            butir_dir=butir, config_dir=cfg, encoder_factory=factory, embed_cache_dir=w["emb"],
                            main_headers=all_scope, compare_store=store_of(w, "Cmp"), identity=sident("sweep_glimmer_medium", sw),
                            sweep_cfg=sw, gpu_lock=True, gpu_pid_alive=ALIVE)
    assert loads == [] and not (w["runs"] / "grid_compare").exists()
