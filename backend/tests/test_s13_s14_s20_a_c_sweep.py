"""M3.2-effort-sweep (H-103 S3 bagian B): S13 compare_a sapuan + gerbang pool sapuan, S14 compare_c sapuan + `--grade` offline,
S20 (a)(b)(c) gerbang G-36 compare_c/compare_a. Transport palsu; tanpa jaringan."""

import json

import pytest

from backend.answer import compare_c
from backend.proposal.gate import GateConfig, evaluate_gate
from backend.schema_a import SchemaStore, compare_a
from backend.spark import store
from backend.spark.sweep import sweep_pool_cap, sweep_pool_cumulative_pct

from .h101_helpers import GATE, budget_b
from .m25_fakes import chat_body, env_m25, m25_model_cfg
from .spark_fakes import Clock, FakeTransport, Resp, body_ok
from .sweep_b_helpers import sweep_cfg
from .sweep_helpers import syn
from .test_answer_api import ITEM, JAWAB, URL, body, svc  # noqa: F401
from .test_m25_w6_cli import make
from .test_schema_a_compare import Run, Tok, doc, model_a, responses, seed_main_store, body_for, chats, budget

OPEN = "meta-models/muse-spark-open-1026"
CONTRIB = "muse-spark-1.3-contributor"


def reflect(payload_fn):
    """Responses palsu yang memantulkan `reasoning.effort` yang dikirim (P5)."""
    def act(tr, request):
        e = (json.loads(request.content.decode("utf-8")).get("reasoning") or {}).get("effort")
        return Resp(200, body_ok(payload_fn(request), reasoning={"effort": e}))
    return act


# ------------------------------------------------------------------------------------------------ S13 compare_a
class SweepRun(Run):
    def __init__(self, tmp_path, *, sweep=None, **kw):
        super().__init__(tmp_path, **kw)
        self.sweep = sweep if sweep is not None else sweep_cfg()

    def __call__(self, *argv, **kw):
        return compare_a.main(list(argv), env=env_m25(), model_config=self.model, budget_config=self.budget, runs_dir=self.runs,
                              transport=self.tr.transport, out=self.lines.append, probe=self.probe, load_doc=doc, tokenizer=Tok(),
                              sweep_config=self.sweep, **kw)


def a_default(fam="uupt"):
    return reflect(lambda req: body_for(fam))


def test_s13a_sweep_a_saved_under_compare_store_never_active_with_effort(tmp_path):
    r = SweepRun(tmp_path, default=a_default())
    main_bytes = {p: p.read_bytes() for p in sorted((r.runs / "schemas").rglob("*.json"))}
    assert r("--model-profile", "sweep_meta_medium", "--family", "uupt") == 0, r.lines
    st = SchemaStore(r.runs, compare_profile="sweep_meta_medium")
    recs = st.list("uupt")
    assert [c["schema_version"] for c in recs] == [1] and recs[0]["model_profile"] == "sweep_meta_medium"
    assert (r.runs / "schemas" / "uupt" / "compare" / "sweep_meta_medium" / "v1.json").is_file()
    assert [x["schema_version"] for x in SchemaStore(r.runs).list("uupt")] == [1, 2]  # store utama tidak bertambah
    for p, b in main_bytes.items():
        assert p.read_bytes() == b
    rec = [x for x in store.load_records(r.runs) if x.kind == "spark_a"][0]
    assert (rec.provider, rec.effort, rec.model) == ("meta", "medium", CONTRIB)  # S13 (c)
    # dua effort -> versi sendiri masing-masing (S7 c)
    r2 = SweepRun(tmp_path, default=a_default())
    assert r2("--model-profile", "sweep_meta_high", "--family", "uupt") == 0
    assert [c["schema_version"] for c in SchemaStore(r.runs, compare_profile="sweep_meta_high").list("uupt")] == [1]
    assert r2("--model-profile", "sweep_meta_medium", "--diff", "--family", "uupt") == 0


def test_s13a_reported_or_default_profile_still_rejected_and_sweep_profile_ok(tmp_path):
    r = SweepRun(tmp_path, default=a_default())
    assert r("--model-profile", "meta") == 2
    assert r("--model-profile", "sweep_meta_medium", "--project-only", "--family", "uupt") == 0


def test_s13b_gate_uses_sweep_pool_and_threshold_50m(tmp_path):
    """H-105: ambang sapuan 100% = 50.000.000. Pool sapuan 48.005.250 + batas atas 1.994.750 lolos; 1.994.751 ditolak."""
    cfg = GateConfig(**GATE)
    thr = 50_000_000
    assert sweep_pool_cap(sweep_cfg()) * sweep_pool_cumulative_pct(sweep_cfg()) // 100 == thr
    assert evaluate_gate([0], 48_005_250, cfg, upper_floor=1_994_750, threshold_micros=thr).ok
    v = evaluate_gate([0], 48_005_250, cfg, upper_floor=1_994_751, threshold_micros=thr)
    assert not v.ok and "cumulative_over_threshold" in v.reasons


def test_s13b_a_runner_gate_rejects_when_sweep_pool_is_full_before_any_request(tmp_path):
    r = SweepRun(tmp_path, default=a_default())
    syn(r.runs, "b", "baseten", OPEN, "xhigh", 49_999_990, rid="sweep-fill")  # off-pin -> pool sapuan 49.999.990
    n = r("--model-profile", "sweep_meta_medium", "--family", "uupt")
    assert n == 3 and r.tr.calls == 0 and any("cumulative_over_threshold" in ln for ln in r.lines)
    # profil non-sapuan memakai pool lain: belanja sapuan tidak menggeser gerbang baseten_open (S6 d)
    r2 = SweepRun(tmp_path / "x", default=reflect(lambda req: body_for("uupt")))
    syn(r2.runs, "b", "baseten", OPEN, "xhigh", 49_999_990, rid="sweep-fill")
    assert r2("--model-profile", "baseten_open", "--family", "uupt", "--project-only") == 0
    gate_line = next(ln for ln in r2.lines if ln.startswith("gate [batch_gate]"))
    assert "spent=0" in gate_line


def test_s13_glimmer_sweep_a_passes_gate_cost_zero(tmp_path):
    r = SweepRun(tmp_path, default=Resp(200, chat_body(body_for("uupt"))))
    syn(r.runs, "b", "baseten", OPEN, "xhigh", 49_999_990, rid="sweep-fill")
    assert r("--model-profile", "sweep_glimmer_medium", "--family", "uupt") == 0, r.lines
    assert r.tr.requests[0]["body"]["reasoning_effort"] == "medium"


def test_s13_contributor_sweep_a_takes_rpm_lock(tmp_path):
    from backend.spark import rpmlock
    r = SweepRun(tmp_path, default=a_default())
    held = rpmlock.acquire(r.runs, "sweep-b", pid=4242, pid_alive=lambda p: True)
    assert r("--model-profile", "sweep_meta_medium", "--family", "uupt", pid_alive_rpm=lambda p: True) == 3 and r.tr.calls == 0
    held.release()
    assert r("--model-profile", "sweep_meta_medium", "--family", "uupt") == 0 and not rpmlock.lock_path(r.runs).exists()


# ------------------------------------------------------------------------------------------------ S20 (a)(b)
def test_s20a_numbers_two_slots_110000_inclusive_and_batch_cap():
    cfg = GateConfig(**GATE)
    per = (2_000 * 1_250_000 + 10_000 * 150_000 + 12_000 * 4_250_000 + 999_999) // 1_000_000
    assert per == 55_000
    thr = 40_000_000
    assert evaluate_gate([0], 39_890_000, cfg, upper_floor=110_000, threshold_micros=thr).ok
    v = evaluate_gate([0], 39_890_001, cfg, upper_floor=110_000, threshold_micros=thr)
    assert not v.ok and v.reasons == ("cumulative_over_threshold",)
    assert evaluate_gate([0], 0, cfg, upper_floor=36 * 55_000, threshold_micros=thr).ok  # 1.980.000
    v = evaluate_gate([0], 0, cfg, upper_floor=37 * 55_000, threshold_micros=thr)
    assert v.batas_atas == 2_035_000 and "batas_atas_over_batch_cap" in v.reasons


def _seed(svc, tmp_path):
    c, tr, s = make(svc, tmp_path)
    assert c.post(URL, json=body(svc, model_profile="meta")).status_code == 200
    return s


def _cli(s, argv, tr, *, sweep=None, pid_alive_rpm=None, out=None):
    lines = [] if out is None else out
    rc = compare_c.main(argv, service=s, env=env_m25(), model_config=m25_model_cfg(), budget_config=budget_b(), runs_dir=s.runs_dir,
                        transport=tr.transport, out=lines.append, probe=lambda u, m: (True, "ok"),
                        sweep_config=sweep if sweep is not None else sweep_cfg(), pid_alive_rpm=pid_alive_rpm)
    return rc, lines


def _tr(effort_default=True):
    return FakeTransport(Clock(), None, reflect(lambda req: JAWAB))


def test_s14b_sweep_c_stores_under_sweep_profile_and_keeps_meta_answers(svc, tmp_path):
    s = _seed(svc, tmp_path)
    meta_before = {p.name: p.read_bytes() for p in (s.runs_dir / "answers").glob("*.json")}
    tr = _tr()
    rc, lines = _cli(s, ["--model-profile", "sweep_baseten_high", "--items", ITEM], tr)
    assert rc == 0 and tr.calls == 2, lines
    answers = [json.loads(p.read_text(encoding="utf-8")) for p in (s.runs_dir / "answers").glob("*.json")]
    sweep = [a for a in answers if a["model_profile"] == "sweep_baseten_high"]
    assert {a["slot"] for a in sweep} == {"best", "baseline"}
    assert len({a["answer_id"] for a in sweep}) == 2
    for name, b in meta_before.items():
        assert (s.runs_dir / "answers" / name).read_bytes() == b  # jawaban `meta` tak tersentuh
    recs = [r for r in store.load_records(s.runs_dir) if r.provider == "baseten"]
    assert len(recs) == 2 and {r.effort for r in recs} == {"high"} and all(r.model == OPEN for r in recs)
    assert {r["body"]["reasoning"]["effort"] for r in tr.requests} == {"high"}
    rc, _ = _cli(s, ["--model-profile", "sweep_baseten_high", "--items", ITEM], tr)
    assert rc == 0 and tr.calls == 2  # run ulang = cache
    # dua effort -> answer_id berbeda (S7 d)
    tr2 = _tr()
    rc, _ = _cli(s, ["--model-profile", "sweep_baseten_medium", "--items", ITEM], tr2)
    assert rc == 0
    ids = {(a["model_profile"], a["slot"]): a["answer_id"] for a in
           (json.loads(p.read_text(encoding="utf-8")) for p in (s.runs_dir / "answers").glob("*.json"))}
    assert ids[("sweep_baseten_medium", "best")] != ids[("sweep_baseten_high", "best")]


def test_s20a_c_gate_rejects_item_not_run_zero_requests(svc, tmp_path):
    s = _seed(svc, tmp_path)
    syn(s.runs_dir, "b", "baseten", OPEN, "xhigh", 49_999_990, rid="fill")
    tr = _tr()
    rc, lines = _cli(s, ["--model-profile", "sweep_baseten_high", "--items", ITEM], tr)
    assert rc == 3 and tr.calls == 0 and any("not_run (gate rejected" in ln and "cumulative_over_threshold" in ln for ln in lines)
    assert not [a for a in (s.runs_dir / "answers").glob("*.json")
                if json.loads(a.read_text(encoding="utf-8"))["model_profile"] == "sweep_baseten_high"]


def test_s20b_non_sweep_baseten_open_c_has_no_extra_gate(svc, tmp_path):
    s = _seed(svc, tmp_path)
    syn(s.runs_dir, "b", "baseten", OPEN, "xhigh", 49_999_990, rid="fill")  # off-pin: bukan pool Baseten
    tr = FakeTransport(Clock(), None, Resp(200, body_ok(JAWAB)))
    rc, lines = _cli(s, ["--model-profile", "baseten_open", "--items", ITEM], tr, sweep={"version": 1})
    assert rc == 0 and tr.calls == 2 and not any("gate" in ln for ln in lines)


def test_s14a_source_must_be_non_sweep_and_profile_must_differ(svc, tmp_path):
    s = _seed(svc, tmp_path)
    tr = _tr()
    rc, _ = _cli(s, ["--model-profile", "sweep_baseten_high", "--source-profile", "sweep_meta_medium", "--items", ITEM], tr)
    assert rc == 2 and tr.calls == 0
    rc, _ = _cli(s, ["--model-profile", "sweep_baseten_high", "--source-profile", "sweep_baseten_high", "--items", ITEM], tr)
    assert rc == 2 and tr.calls == 0


def test_s14cd_grade_offline_writes_report_byte_stable_no_model_no_ledger(svc, tmp_path):
    s = _seed(svc, tmp_path)
    tr = _tr()
    assert _cli(s, ["--model-profile", "sweep_baseten_high", "--items", ITEM], tr)[0] == 0
    calls, n_records = tr.calls, len(store.load_records(s.runs_dir))
    rc, lines = _cli(s, ["--model-profile", "sweep_baseten_high", "--items", ITEM, "--grade"], tr)
    assert rc == 0 and tr.calls == calls and len(store.load_records(s.runs_dir)) == n_records  # tidak memanggil model
    rep = s.runs_dir / "compare_report" / "c" / "sweep_baseten_high.json"
    first = rep.read_bytes()
    d = json.loads(first.decode("utf-8"))
    assert d["profile"] == "sweep_baseten_high" and {r["slot"] for r in d["summary"]} == {"best", "baseline"}
    assert all(r["model_profile"] == "sweep_baseten_high" and r["n_items"] == 1 for r in d["summary"])
    assert _cli(s, ["--model-profile", "sweep_baseten_high", "--items", ITEM, "--grade"], tr)[0] == 0
    assert rep.read_bytes() == first  # byte-sama pada run ulang
    assert (s.runs_dir / "compare_report" / "c" / "sweep_baseten_high.md").exists()
    # tidak ada jawaban -> rc 2
    assert _cli(s, ["--model-profile", "sweep_baseten_xhigh", "--grade"], tr)[0] == 2


def test_s14e_sweep_name_is_unknown_to_w6(svc, tmp_path):
    c, tr, s = make(svc, tmp_path)
    r = c.post(URL, json=body(svc, model_profile="sweep_baseten_high"))
    assert r.status_code == 400


def _item_projection(s):
    """Proyeksi butir (jumlah `per_call_micros` dua slot) dari `--project-only` (tanpa jaringan)."""
    import re
    rc, lines = _cli(s, ["--model-profile", "sweep_baseten_high", "--items", ITEM, "--project-only"], _tr())
    assert rc == 0, lines
    return int(re.search(r"total projected micro-USD=(\d+)", "\n".join(lines)).group(1))


def test_s20a_c_gate_edge_via_main_full_g36_factor_and_sum_not_max(svc, tmp_path):
    """S-2 (pemeriksa Tier 1 BC): tepi S20(a) lewat `compare_c.main`. Angka skenario (55.000 x 2 = 110.000 inklusif) mengandaikan
    faktor 1; di profil `sweep_baseten_high` gerbang G-36 penuh: expected = jumlah `per_call_micros` P (dua slot, tanpa cache),
    batas atas U = max(ceil(P x 19312 / 10000), P) (19312 = max(gerbang 15700, entri `[factor_bp]` sweep)). Tepi dihitung dari P hasil
    proyeksi nyata fixture: belanja pool 50.000.000 - U + 1 ditolak `cumulative_over_threshold`, 0 request; tepat 50.000.000 - U
    lolos (tes berikut). Membunuh mutan `sum` -> `max` (U bergeser ke satu slot) dan mutan tanpa faktor (U = P)."""
    s = _seed(svc, tmp_path)
    P = _item_projection(s)
    assert P > 0
    U = max(-(-P * 19312 // 10000), P)
    assert U > P  # faktor benar-benar berlaku
    tr = _tr()
    syn(s.runs_dir, "b", "baseten", OPEN, "xhigh", 50_000_000 - U + 1, rid="fill")
    rc, lines = _cli(s, ["--model-profile", "sweep_baseten_high", "--items", ITEM], tr)
    assert rc == 3 and tr.calls == 0, lines
    assert any("cumulative_over_threshold" in ln and f"upper_bound={U}" in ln for ln in lines), lines


def test_s20a_c_gate_edge_via_main_exact_edge_passes(svc, tmp_path):
    """Pasangan inklusif dari tes di atas: belanja = 50.000.000 - U tepat -> lolos, dua request jalan."""
    s = _seed(svc, tmp_path)
    P = _item_projection(s)
    U = max(-(-P * 19312 // 10000), P)
    syn(s.runs_dir, "b", "baseten", OPEN, "xhigh", 50_000_000 - U, rid="fill")
    tr = _tr()
    rc, lines = _cli(s, ["--model-profile", "sweep_baseten_high", "--items", ITEM], tr)
    assert rc == 0 and tr.calls == 2, lines
