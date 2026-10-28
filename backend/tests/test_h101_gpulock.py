"""H-101 bagian 3 (skenario M3.2-open-weight-B S16, P12): kunci GPU eksklusif `runs/locks/gpu.lock` antara Glimmer lokal
(B pembanding, CLI A/C) dan runner grid yang memuat encoder. `pid_alive` disuntikkan. Tanpa Model API, tanpa GPU."""

import json
import os
import sys

import pytest

from backend import gpulock
from backend.gpulock import GpuBusy, GpuLockStale, acquire, check_free, lock_path, read_lock
from backend.header_b import compare as cmp
from backend.header_b.compare_store import snapshot_main
from backend.pipeline.grid_run import run_family_grid
from backend.tests._chunk_util import ToyWs, u_doc
from backend.tests.pipeline_fakes import FakeEncoder, toy_config_dir, write_toy_butir

from .h101_helpers import PROMPT12, Tok, hc_b, make_prepared, model_b, rig_for
from .test_h101_compare_store import cli_args, cli_run


def hold(runs, holder, pid=4242):
    p = lock_path(runs)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": pid, "holder": holder, "started_at": "2026-10-28T00:00:00Z"}), encoding="utf-8")
    return p


ALIVE, DEAD = (lambda pid: True), (lambda pid: False)


# ------------------------------------------------------------------------------------------------ modul
def test_acquire_writes_pid_holder_started_and_release_removes(tmp_path):
    lk = acquire(tmp_path, "glimmer-b", pid=77, pid_alive=ALIVE, now=lambda: "2026-10-28T01:02:03Z")
    assert read_lock(lock_path(tmp_path)) == {"pid": 77, "holder": "glimmer-b", "started_at": "2026-10-28T01:02:03Z"}
    assert lock_path(tmp_path) == tmp_path / "locks" / "gpu.lock"
    lk.release()
    lk.release()  # idempoten
    assert not lock_path(tmp_path).exists()
    assert list((tmp_path / "locks").iterdir()) == []  # tanpa sisa berkas sementara


def test_s16e_atomic_creation_second_acquire_is_gpu_busy(tmp_path):
    a = acquire(tmp_path, "glimmer-b", pid=1, pid_alive=ALIVE)
    with pytest.raises(GpuBusy) as ei:
        acquire(tmp_path, "embedding", pid=2, pid_alive=ALIVE)
    assert ei.value.code == "gpu_busy" and "glimmer-b" in str(ei.value) and "pid 1" in str(ei.value)
    a.release()
    acquire(tmp_path, "embedding", pid=2, pid_alive=ALIVE).release()  # bisa mulai setelah dilepas


def test_s16c_released_on_normal_error_and_keyboard_interrupt(tmp_path):
    with acquire(tmp_path, "glimmer-b", pid_alive=ALIVE):
        assert lock_path(tmp_path).exists()
    assert not lock_path(tmp_path).exists()
    for exc in (RuntimeError("boom"), KeyboardInterrupt()):
        with pytest.raises(type(exc)):
            with acquire(tmp_path, "embedding", pid_alive=ALIVE):
                raise exc
        assert not lock_path(tmp_path).exists()
        acquire(tmp_path, "glimmer-b", pid_alive=ALIVE).release()  # run berikutnya bisa mulai


def test_release_does_not_remove_someone_elses_lock(tmp_path):
    a = acquire(tmp_path, "glimmer-b", pid=1, pid_alive=ALIVE, now=lambda: "t1")
    lock_path(tmp_path).unlink()
    acquire(tmp_path, "embedding", pid=2, pid_alive=ALIVE, now=lambda: "t2")
    a.release()
    assert read_lock(lock_path(tmp_path))["holder"] == "embedding"


def test_s16d_stale_lock_is_refused_not_auto_deleted_unless_flag(tmp_path):
    hold(tmp_path, "glimmer-b", pid=999)
    with pytest.raises(GpuLockStale) as ei:
        acquire(tmp_path, "embedding", pid_alive=DEAD)
    assert ei.value.code == "gpu_lock_stale" and "gpu.lock" in str(ei.value) and "--break-stale-lock" in str(ei.value)
    assert lock_path(tmp_path).exists()  # tidak dihapus otomatis
    with pytest.raises(GpuBusy):  # pid hidup = tolak seperti busy
        acquire(tmp_path, "embedding", pid_alive=ALIVE)
    lk = acquire(tmp_path, "embedding", pid_alive=DEAD, break_stale=True)
    assert lk.broke_stale == {"holder": "glimmer-b", "pid": 999, "started_at": "2026-10-28T00:00:00Z"}
    assert read_lock(lock_path(tmp_path))["holder"] == "embedding"
    lk.release()


def test_unreadable_lock_is_stale_not_deleted(tmp_path):
    p = lock_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("garbage", encoding="utf-8")
    with pytest.raises(GpuLockStale):
        acquire(tmp_path, "glimmer-b", pid_alive=ALIVE)
    assert p.read_text(encoding="utf-8") == "garbage"
    with pytest.raises(GpuLockStale):
        check_free(tmp_path, pid_alive=ALIVE)


def test_default_pid_alive_knows_this_process_and_not_a_dead_one(tmp_path):
    assert gpulock.default_pid_alive(os.getpid()) is True
    assert gpulock.default_pid_alive(0) is False and gpulock.default_pid_alive(-5) is False
    import subprocess
    pr = subprocess.Popen([sys.executable, "-c", "pass"])
    pr.wait()
    assert gpulock.default_pid_alive(pr.pid) is False
    import inspect
    assert "os.kill" not in inspect.getsource(gpulock.default_pid_alive).split('if sys.platform == "win32":')[1].split("try:\n        os.kill")[0]


# ------------------------------------------------------------------------------------------------ S16 (a): runner grid
@pytest.fixture()
def w(tmp_path):
    doc = u_doc()
    cfg = toy_config_dir(tmp_path / "cfg")
    butir = tmp_path / "butir"
    write_toy_butir(butir, doc.clean_sha256)
    return {"doc": doc, "cfg": cfg, "butir": butir, "runs": tmp_path / "runs", "emb": tmp_path / "emb"}


def grid(w, **kw):
    return run_family_grid("uupt", doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"], butir_dir=w["butir"], config_dir=w["cfg"],
                           embed_cache_dir=w["emb"], **kw)


def test_s16a_grid_refuses_while_glimmer_holds_before_loading_encoder_or_writing(w):
    hold(w["runs"], "glimmer-b")
    loads = []

    def factory():
        loads.append(1)
        return FakeEncoder()

    with pytest.raises(GpuBusy) as ei:
        grid(w, encoder_factory=factory, gpu_lock=True, gpu_pid_alive=ALIVE)
    assert "glimmer-b" in str(ei.value) and "4242" in str(ei.value) and loads == []
    assert not (w["runs"] / "grid").exists()  # tidak ada amplop
    assert lock_path(w["runs"]).exists()  # milik pemegang, tidak disentuh


def test_s16_grid_takes_and_releases_lock_when_encoder_is_used(w):
    seen = []

    class SpyEnc(FakeEncoder):
        def encode(self, texts):
            seen.append(read_lock(lock_path(w["runs"])))
            return super().encode(texts)

    grid(w, encoder=SpyEnc(), gpu_lock=True, gpu_pid_alive=ALIVE)
    assert seen and seen[0]["holder"] == "embedding" and not lock_path(w["runs"]).exists()


def test_s16_grid_releases_lock_on_error(w):
    class Boom(FakeEncoder):
        def encode(self, texts):
            raise RuntimeError("gpu error")

    with pytest.raises(RuntimeError):
        grid(w, encoder=Boom(), gpu_lock=True, gpu_pid_alive=ALIVE)
    assert not lock_path(w["runs"]).exists()


def test_s16f_bm25_only_grid_and_default_api_path_take_no_lock(w):
    hold(w["runs"], "glimmer-b")  # bahkan bila Glimmer memegang, tanpa encoder grid tetap jalan
    g = w["cfg"] / "grid.toml"
    g.write_text(g.read_text(encoding="utf-8").replace('retrieval_modes = ["dense", "bm25", "hybrid"]', 'retrieval_modes = ["bm25"]'),
                 encoding="utf-8")
    res = grid(w, encoder=FakeEncoder(), gpu_lock=True, gpu_pid_alive=ALIVE)
    assert res.envelope["settings_run"] and read_lock(lock_path(w["runs"]))["holder"] == "glimmer-b"
    w2 = {**w, "runs": w["runs"].parent / "runs2"}
    grid(w2, encoder=FakeEncoder())  # bawaan gpu_lock=False (backend API): tidak mengambil kunci
    assert not lock_path(w2["runs"]).exists()


# ------------------------------------------------------------------------------------------------ S16 (b): runner Glimmer
def test_s16b_glimmer_b_refuses_while_embedding_holds_before_any_request(tmp_path):
    rig = rig_for(tmp_path, "glimmer_local")
    hold(rig.runs, "embedding")
    probed = []
    rc = cli_run(tmp_path, rig, cli_args("glimmer_local"), pid_alive=ALIVE)
    assert rc == 3 and rig.tr.calls == 0
    assert read_lock(lock_path(rig.runs))["holder"] == "embedding"
    assert not (rig.runs / "headers_compare" / "glimmer_local" / "pasal").exists() and probed == []


def test_s16b_glimmer_b_stale_lock_needs_flag_and_is_noted_in_report(tmp_path):
    rig = rig_for(tmp_path, "glimmer_local")
    hold(rig.runs, "embedding", pid=999)
    assert cli_run(tmp_path, rig, cli_args("glimmer_local"), pid_alive=DEAD) == 3 and rig.tr.calls == 0
    assert cli_run(tmp_path, rig, cli_args("glimmer_local", "--break-stale-lock"), pid_alive=DEAD) == 0
    (rep,) = list((rig.runs / "headers_compare" / "glimmer_local" / "runs").glob("*.json"))
    r = json.loads(rep.read_text(encoding="utf-8"))
    assert r["gpu_lock"]["broke_stale"]["pid"] == 999 and r["gpu_lock"]["holder"] == "glimmer-b"
    assert not lock_path(rig.runs).exists()  # dilepas selesai normal


def test_s16b_glimmer_b_holds_lock_during_run_and_releases_on_probe_interrupt(tmp_path):
    rig = rig_for(tmp_path, "glimmer_local")
    inside = []

    def probe(u, m):
        inside.append(read_lock(lock_path(rig.runs)))
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        cmp.main(cli_args("glimmer_local"), env=rig.env, model_config=rig.model, budget_config=rig.budget, header_config=hc_b(),
                 runs_dir=rig.runs, transport=rig.tr.transport, out=lambda s: None, tokenizer=Tok(), probe=probe,
                 prepare_fn=lambda ids, sources, **k: {"uupt-x": {"pasal": make_prepared(3)}})
    assert inside[0]["holder"] == "glimmer-b" and not lock_path(rig.runs).exists() and rig.tr.calls == 0


def test_s16f_baseten_b_takes_no_lock_and_locks_dir_does_not_shift_main_identity(tmp_path):
    rig = rig_for(tmp_path, "baseten_open")
    hold(rig.runs, "embedding")  # Baseten B tidak peduli GPU
    assert cli_run(tmp_path, rig, cli_args("baseten_open", "--max-units", "2")) == 0 and rig.tr.calls == 3
    assert read_lock(lock_path(rig.runs))["holder"] == "embedding"
    a = snapshot_main(rig.runs, "a" * 64)
    lock_path(rig.runs).unlink()
    assert snapshot_main(rig.runs, "a" * 64) == a  # `runs/locks/` di luar semua direktori yang di-hash


# ------------------------------------------------------------------------------------------------ CLI A dan C (profil chat_completions)
def test_s16b_compare_a_glimmer_refuses_before_request_and_baseten_ignores_lock(tmp_path):
    from .test_schema_a_compare import Run, chats, responses
    run = Run(tmp_path)
    hold(run.runs, "embedding")
    import backend.gpulock as g
    orig = g.default_pid_alive
    g.default_pid_alive = ALIVE
    try:
        assert run("--model-profile", "glimmer_local", "--family", "akta") == 3
        assert run.tr.calls == 0
        run.probe = lambda u, m: (_ for _ in ()).throw(AssertionError("probe must not run while the lock is held"))
        assert run("--model-profile", "glimmer_local", "--family", "akta") == 3
        run.tr.default = responses("akta")
        assert run("--model-profile", "baseten_open", "--family", "akta") == 0  # Responses: tanpa kunci
    finally:
        g.default_pid_alive = orig
    assert read_lock(lock_path(run.runs))["holder"] == "embedding"
    lock_path(run.runs).unlink()
    run.probe = lambda u, m: (True, "Available.")
    run.tr.default = chats("akta")
    assert run("--model-profile", "glimmer_local", "--family", "akta") == 0 and not lock_path(run.runs).exists()


from .test_answer_api import svc  # noqa: E402,F401  (fixture modul)


def test_s16b_compare_c_glimmer_refuses_before_request_and_releases_after_run(svc, tmp_path):
    from backend.tests.spark_fakes import Clock, FakeTransport, Resp
    from .m25_fakes import chat_body
    from .test_answer_api import ITEM, JAWAB
    from .test_m25_w6_cli import _cli, _seed_contributor
    s = _seed_contributor(svc, tmp_path)
    tr = FakeTransport(Clock(), None, Resp(200, chat_body(JAWAB)))
    hold(s.runs_dir, "embedding")
    import backend.gpulock as g
    orig = g.default_pid_alive
    g.default_pid_alive = ALIVE
    try:
        rc, _ = _cli(s, ["--model-profile", "glimmer_local", "--items", ITEM], tr)
        assert rc == 3 and tr.calls == 0 and read_lock(lock_path(s.runs_dir))["holder"] == "embedding"
    finally:
        g.default_pid_alive = orig
    lock_path(s.runs_dir).unlink()
    rc, _ = _cli(s, ["--model-profile", "glimmer_local", "--items", ITEM], tr)
    assert rc == 0 and tr.calls == 2 and not lock_path(s.runs_dir).exists()
