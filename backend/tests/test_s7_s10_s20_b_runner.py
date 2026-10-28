"""M3.2-effort-sweep (H-103 S3 bagian B): runner B sapuan `header_b.compare` -- S20 (d) penahanan B Spark Open, S7 identitas dan
pewarisan induk, S2 (d)(e) identitas = effort terkirim, S10 B per effort, rpmlock Contributor sapuan, S5 (m)(o) keterpisahan.
Transport palsu; tanpa jaringan."""

import json

import pytest

from backend.header_b import compare as cmp
from backend.header_b.compare_store import CompareError, check_identity, compare_store_dir
from backend.spark import ConfigInvalid, rpmlock, sweep_run
from backend.spark.sweep import SWEEP_BASETEN_FACTOR_BP_MIN

from .h101_helpers import PROMPT12, hc_b, make_prepared, model_b, words
from .sweep_b_helpers import args, go_sweep, run_main, sweep_cfg, sweep_rig


def listing(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()) if root.exists() else []


# ------------------------------------------------------------------------------------------------ S20 (d)
def test_s20d_baseten_sweep_held_until_confirm_go(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_baseten_medium")
    out: list[str] = []
    assert run_main(rig, args("sweep_baseten_medium"), sweep=sw, out=out) == 2  # go_required
    assert rig.tr.calls == 0 and not (rig.runs / "headers_compare").exists()
    # --project-only: proyeksi tercetak, tanpa panggilan dan tanpa tulis
    assert run_main(rig, args("sweep_baseten_medium", "--project-only"), sweep=sw, out=out) == 0
    text = "\n".join(out)
    assert rig.tr.calls == 0 and not (rig.runs / "headers_compare").exists()
    assert "sweep projection: profile=sweep_baseten_medium effort=medium role=b" in text and "factor_bp=19312" in text
    assert "sweep_pool_remaining=50000000" in text
    # --confirm-go: jalan (lewat gerbang)
    assert run_main(rig, args("sweep_baseten_medium", "--confirm-go"), sweep=sw) == 0
    assert rig.tr.calls > 0
    assert (rig.runs / "headers_compare" / "sweep_baseten_medium" / "identity.json").exists()


def test_s20d_contributor_and_glimmer_sweep_and_baseten_open_run_without_flag(tmp_path):
    for prof in ("sweep_meta_medium", "sweep_glimmer_medium"):
        rig, sw = sweep_rig(tmp_path / prof, prof)
        assert run_main(rig, args(prof, "--max-units", "1"), sweep=sw) == 0 and rig.tr.calls >= 1
    rig, sw = sweep_rig(tmp_path / "bo", "baseten_open")
    assert run_main(rig, args("baseten_open", "--max-units", "1"), sweep=None) == 0 and rig.tr.calls >= 1  # H-101 apa adanya


# ------------------------------------------------------------------------------------------------ S2 (d)(e), S7 (a)
def test_s2de_identity_effort_equals_sent_effort_and_console_line(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium", usage=None)
    out: list[str] = []
    assert run_main(rig, args("sweep_meta_medium", "--max-units", "1"), sweep=sw, out=out) in (0, 1)
    ident = json.loads((rig.runs / "headers_compare" / "sweep_meta_medium" / "identity.json").read_text(encoding="utf-8"))
    sent = {r["body"]["reasoning"]["effort"] for r in rig.tr.requests}
    assert ident["effort"] == "medium" and sent == {"medium"} and ident["provider"] == "meta"  # identitas = effort DIKIRIM
    assert any("effort=medium" in line for line in out) and not any("effort=low" in line for line in out)


def test_s7a_stores_are_per_profile_and_identity_mismatch_rejected_before_network(tmp_path):
    rig_m, sw = sweep_rig(tmp_path / "m", "sweep_meta_medium")
    rig_h, _ = sweep_rig(tmp_path / "h", "sweep_meta_high")
    assert run_main(rig_m, args("sweep_meta_medium", "--max-units", "1"), sweep=sw) == 0
    assert run_main(rig_h, args("sweep_meta_high", "--max-units", "1"), sweep=sw) == 0
    dm, dh = compare_store_dir(rig_m.runs, "sweep_meta_medium"), compare_store_dir(rig_h.runs, "sweep_meta_high")
    assert dm != dh and dm.name == "sweep_meta_medium" and dh.name == "sweep_meta_high"
    idh = json.loads((dh / "identity.json").read_text(encoding="utf-8"))
    assert idh["effort"] == "high" and idh["provider"] == "meta"
    # identitas `sweep_meta_medium` disuntik ke direktori `sweep_meta_high` -> mismatch sebelum jaringan, tanpa tulis
    import shutil
    shutil.copytree(dm, rig_h.runs / "headers_compare" / "sweep_meta_high2")
    rig3, _ = sweep_rig(tmp_path / "x", "sweep_meta_high")
    root = rig3.runs / "headers_compare" / "sweep_meta_high"
    root.mkdir(parents=True)
    (root / "identity.json").write_text((dm / "identity.json").read_text(encoding="utf-8").replace('"profile": "sweep_meta_medium"',
                                                                                                    '"profile": "sweep_meta_high"'),
                                        encoding="utf-8")
    before = listing(root)
    with pytest.raises(CompareError) as ei:
        from backend.header_b.compare_store import build_identity
        from backend.spark.sweep import merge_sweep
        eff = merge_sweep(rig3.model, sw)
        ident = build_identity("sweep_meta_high", eff["profiles"]["sweep_meta_high"], eff, prompt_hash=PROMPT12, max_header_tokens=40,
                               schema_max_length_chars=190)
        check_identity(root, ident)
    assert ei.value.code == "compare_identity_mismatch" and "effort: 'medium' -> 'high'" in str(ei.value)
    assert run_main(rig3, args("sweep_meta_high"), sweep=sw) == 2 and rig3.tr.calls == 0 and listing(root) == before


# ------------------------------------------------------------------------------------------------ S7 (e)
def test_s7e_inheritance_of_attempts_time_params_and_factor():
    sw = sweep_cfg()
    hc = hc_b()
    assert sweep_run.max_attempts(hc, sw, "sweep_glimmer_medium") == 3  # induk glimmer_local = 3, bukan 8
    sw["max_attempts"] = {"sweep_glimmer_medium": 2}
    assert sweep_run.max_attempts(hc, sw, "sweep_glimmer_medium") == 2
    assert sweep_run.max_attempts(hc, sw, "sweep_meta_medium") == 8
    assert sweep_run.time_params(hc, sw, "sweep_glimmer_medium") == {"prefill_tokens_per_s": 650, "base_ms": 4800,
                                                                      "output_tokens_per_10s": 237}
    assert sweep_run.time_params(hc, sw, "sweep_meta_medium") is None
    assert sweep_run.factor_bp(hc, sw, "sweep_baseten_high", 15700) == 19312
    sw["factor_bp"]["sweep_baseten_high"] = 20438
    assert sweep_run.factor_bp(hc, sw, "sweep_baseten_high", 15700) == 20438
    assert sweep_run.factor_bp(hc, sw, "sweep_meta_medium", 15700) == 15700
    assert sweep_run.factor_bp(hc, sw, "sweep_glimmer_medium", 15700) == 15700
    hc2 = hc_b(factor_bp={"baseten_open": 16553})
    sw2 = sweep_cfg()
    assert sweep_run.factor_bp(hc2, sw2, "sweep_baseten_high", 15700) == 19312  # max(15.700, 16.553, 19.312)
    assert SWEEP_BASETEN_FACTOR_BP_MIN == 19312


@pytest.mark.parametrize("mut", [
    lambda s: s["factor_bp"].pop("sweep_baseten_high"),
    lambda s: s["factor_bp"].__setitem__("sweep_baseten_high", 12000),
    lambda s: s["factor_bp"].__setitem__("sweep_baseten_high", 19311),
    lambda s: s["factor_bp"].__setitem__("sweep_meta_medium", 9999),
    lambda s: s["factor_bp"].__setitem__("tidak_ada", 20000),
    lambda s: s.__setitem__("max_attempts", {"tidak_ada": 2}),
    lambda s: s.__setitem__("max_attempts", {"sweep_meta_medium": 0}),
    lambda s: s.__setitem__("projection", {"tidak_ada": {"out_tokens": 5}}),
    lambda s: s.__setitem__("projection", {"sweep_glimmer_low": {"out_tokens": 0}}),
])
def test_s7e_invalid_runner_cfg_is_config_invalid(mut):
    sw = sweep_cfg()
    mut(sw)
    with pytest.raises(ConfigInvalid):
        sweep_run.validate_runner_cfg(sw)


def test_s7e_missing_baseten_factor_entry_stops_runner_before_network(tmp_path):
    sw = sweep_cfg()
    del sw["factor_bp"]["sweep_baseten_high"]
    rig, _ = sweep_rig(tmp_path, "sweep_baseten_high", sweep=sweep_cfg())
    assert run_main(rig, args("sweep_baseten_high", "--project-only"), sweep=sw) == 2 and rig.tr.calls == 0


# ------------------------------------------------------------------------------------------------ S10
def test_s10b_floor_6000_request_and_validator_unchanged(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium")
    assert rig.client._s.max_output_tokens_floor == 6000
    s = go_sweep(rig, sw, make_prepared(2), compare_store_dir(rig.runs, "sweep_meta_medium"), profile="sweep_meta_medium", max_attempts=1,
           gate=None)
    assert s["stored"] == 2
    assert {r["body"]["max_output_tokens"] for r in rig.tr.requests} == {max(1000, 6000)}
    assert {r["body"]["reasoning"]["effort"] for r in rig.tr.requests} == {"medium"}


def test_s10c_cost_of_unit_medium(tmp_path):
    usage = {"input_tokens": 40300, "input_tokens_details": {"cached_tokens": 40000}, "output_tokens": 900}
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium", usage=lambda k: usage)
    go_sweep(rig, sw, make_prepared(1), compare_store_dir(rig.runs, "sweep_meta_medium"), profile="sweep_meta_medium", max_attempts=1,
             gate=None)
    from backend.spark import store
    recs = [r for r in store.load_records(rig.runs) if r.kind == "spark_b" and r.usage_input_tokens == 40300]
    assert len(recs) == 1
    r = recs[0]
    # (300 x 100.000 + 40.000 x 2.000 + 900 x 200.000) / 1e6 = 290 (S10 c)
    assert (r.provider, r.effort, r.cost_usd_micros) == ("meta", "medium", 290)


def test_s10e_honest_failure_no_fallback_to_main_or_other_effort(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium", {"CH-U3": [words(41)]})
    main_store = rig.runs / "headers"
    from .h101_helpers import put_header
    put_header(main_store, "pasal", "CH-U3", "header utama low")
    other = compare_store_dir(rig.runs, "sweep_meta_high")
    put_header(other, "pasal", "CH-U3", "header effort lain")
    d = compare_store_dir(rig.runs, "sweep_meta_medium")
    s = go_sweep(rig, sw, make_prepared(4), d, profile="sweep_meta_medium", max_attempts=8, gate=None)
    assert s["failed"] == {"uupt-x/pasal": ["CH-U3"]} and not (d / "pasal" / PROMPT12 / "CH-U3.json").exists()


def test_s10f_glimmer_sweep_no_warmup_three_attempts(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_glimmer_medium", {"CH-U3": [words(41)]})
    log: list[str] = []
    from backend.header_b.compare import run_compare
    s = go_sweep(rig, sw, make_prepared(4), compare_store_dir(rig.runs, "sweep_glimmer_medium"), profile="sweep_glimmer_medium", max_attempts=3,
           gate=None)
    assert s["warm"] is False and s["cache_guard"] == "skipped" and s["failed"] == {"uupt-x/pasal": ["CH-U3"]}
    assert rig.tr.calls == 6  # 4 unit ronde 1 + CH-U3 ulang di ronde 2 dan 3; tanpa pemanas


# ------------------------------------------------------------------------------------------------ P9 rpmlock
def test_s18d_contributor_sweep_takes_model_api_lock_and_releases(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium")
    held = rpmlock.acquire(rig.runs, "sweep-a", pid=4242, pid_alive=lambda p: True)
    out: list[str] = []
    rc = run_main(rig, args("sweep_meta_medium", "--max-units", "1"), sweep=sw, pid_alive_rpm=lambda p: True)
    assert rc == 3 and rig.tr.calls == 0  # rpm_lock_busy sebelum request apa pun
    held.release()
    assert run_main(rig, args("sweep_meta_medium", "--max-units", "1"), sweep=sw) == 0
    assert not rpmlock.lock_path(rig.runs).exists()  # dilepas pada akhir normal


def test_s18d_baseten_and_glimmer_sweep_do_not_take_rpm_lock(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_baseten_medium")
    held = rpmlock.acquire(rig.runs, "sweep-a", pid=4242, pid_alive=lambda p: True)
    assert run_main(rig, args("sweep_baseten_medium", "--confirm-go", "--max-units", "1"), sweep=sw) == 0
    held.release()


# ------------------------------------------------------------------------------------------------ S5 (m)(o)
def test_s5m_non_sweep_profile_never_reads_sweep_file(tmp_path, monkeypatch):
    import backend.spark.sweep as sweepmod
    reads: list[str] = []
    monkeypatch.setattr(sweepmod, "load_sweep", lambda *a, **k: reads.append("read") or {})
    rig, _ = sweep_rig(tmp_path, "baseten_open", sweep={"version": 1})
    rig2 = rig
    assert run_main(rig2, args("baseten_open", "--max-units", "1"), sweep=None) == 0
    assert reads == []
    # profil sapuan + berkas hilang -> sweep_config_missing (rc 2, sebelum jaringan)
    from backend.spark.sweep import SweepConfigMissing

    def missing(*a, **k):
        raise SweepConfigMissing("sweep_config_missing: config/sweep.toml is not present")

    monkeypatch.setattr(sweep_run, "load_sweep", missing)
    rig3, _ = sweep_rig(tmp_path / "z", "baseten_open")
    assert run_main(rig3, args("sweep_meta_medium"), sweep=None) == 2 and rig3.tr.calls == 0


# ------------------------------------------------------------------------------------------------ S8 (potongan runner B)
def test_s8_b_sweeps_leave_main_store_grid_schemas_answers_untouched(tmp_path):
    from .h101_helpers import put_header
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium")
    put_header(rig.runs / "headers", "pasal", "CH-U9", "header utama")
    main_before = {p: p.read_bytes() for p in sorted((rig.runs / "headers").rglob("*.json"))}
    for prof in ("sweep_meta_medium", "sweep_meta_high"):
        assert run_main(rig, args(prof, "--max-units", "2"), sweep=sw) == 0
    assert run_main(rig, args("sweep_baseten_high", "--confirm-go", "--max-units", "2"), sweep=sw) == 0
    assert {p: p.read_bytes() for p in sorted((rig.runs / "headers").rglob("*.json"))} == main_before
    for d in ("grid", "answers", "schemas"):
        assert not (rig.runs / d).exists()
    assert sorted(p.name for p in (rig.runs / "headers_compare").iterdir()) == ["sweep_baseten_high", "sweep_meta_high", "sweep_meta_medium"]
