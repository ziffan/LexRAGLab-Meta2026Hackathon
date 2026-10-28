"""M2.1 tambahan Tier 1 (H-095, H-099): butir `tolak` UU PT di split, metrik, pemilihan profil, grid ulang, laporan, dan
ringkasan 2x2; SV7-SV15 (docs/scenarios/M2.1-unanswerable-uupt.md). Aturan yang sudah ada dikunci, bukan kode baru.

Data sintetis (split mainan `R2`, butir `t1`..`t5`, `o1`, `o2`, `p1`, dokumen mainan `u_doc`); direktori sementara; tanpa
Model API, tanpa jaringan; tidak menulis `data/butir/` atau `runs/` repo."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

import pytest

from backend import config
from backend.api.app import Service
from backend.grid.runner import MemoryGridCache, grid_cache_key, run_grid
from backend.grid.split import load_latest_split_record, make_split, save_split_record
from backend.grid.types import Assignment, GridItem, Setting, SplitRecord, item_set_hash
from backend.metrics.aggregate import aggregate, mean_recall_at_k
from backend.metrics.types import ItemMetrics
from backend.pipeline import grid_run
from backend.pipeline.grid_run import RunFileStore, make_plan, run_family_grid
from backend.profile import ProfileError, export_profile
from backend.profile.aggregate import NO_GOLD_NOTE, TITLE_UUPT, build_report, held_out_block
from backend.proposal.report import items_summary, mode_report, must_abstain_summary, origin_report
from backend.verifier import grade_answer, summarize
from backend.verifier.verify import NOT_RUN

from . import profile_helpers as H
from ._chunk_util import ToyWs, u_doc
from .pipeline_fakes import FakeEncoder, toy_config_dir
from .test_verifier_summary import A11, G1, T11, ans, cell
from .verifier_fixtures import OP, UNITS, chunks

OPR, SP = "operator", "spark_disetujui"
LIT, PAR, TOL = "literal", "parafrase", "tolak"

# ----------------------------------------------------------------------------- R2 mainan
R2_TABLE = {(OPR, LIT): ("ol", 4, 2), (OPR, PAR): ("op", 5, 2), (SP, LIT): ("sl", 4, 2), (SP, PAR): ("sp", 7, 3)}
R2_V2 = {"sp5", "sp6", "sp7"}  # assignment ber-added_in_version 2 (sintetis)


def r2_items() -> list[GridItem]:
    return [GridItem(f"{p}{n}", "uupt", o, m) for (o, m), (p, k, _h) in R2_TABLE.items() for n in range(1, k + 1)]


def r2() -> SplitRecord:
    asg = []
    for (_o, _m), (p, k, h) in R2_TABLE.items():
        for n in range(1, k + 1):
            iid = f"{p}{n}"
            asg.append(Assignment(iid, "held_out" if n <= h else "tune", 2 if iid in R2_V2 else 1))
    asg.sort(key=lambda a: a.item_id)
    return SplitRecord("uupt", 2, 7, 0.4, ("origin", "mode"), tuple(asg), 4)


T = {f"t{i}": GridItem(f"t{i}", "uupt", SP, TOL) for i in range(1, 6)}
O = {f"o{i}": GridItem(f"o{i}", "uupt", OPR, TOL) for i in (1, 2)}
P1 = GridItem("p1", "uupt", SP, PAR)


def ext(new, prev=None, items=None):
    """Seed, rasio, dan strata argumen sengaja berbeda dari R2: record lama harus menang."""
    return make_split((items if items is not None else r2_items()) + list(new), family="uupt", seed=999, held_out_ratio=0.5,
                      min_control=3, strata=("origin", "mode", "family"), previous=prev or r2())


def held(rec: SplitRecord, ids) -> list[str]:
    s = rec.split_of()
    return sorted(i for i in ids if s[i] == "held_out")


def test_r2_fixture_matches_table():
    rec, items = r2(), r2_items()
    c = Counter((i.origin, i.mode) for i in items if rec.split_of()[i.id] == "held_out")
    assert dict(c) == {k: v[2] for k, v in R2_TABLE.items()} and len(rec.assignments) == 20
    assert make_split(items, family="uupt", seed=7, held_out_ratio=0.4, min_control=3, previous=rec) is rec  # tanpa butir baru


# ============================================================================= SV7
@pytest.mark.parametrize("n,want", [(1, 0), (2, 1), (3, 1), (4, 2), (5, 2)])
def test_sv7_one_batch_of_tolak(n, want):
    new = [T[f"t{i}"] for i in range(1, n + 1)]
    rec = ext(new)
    assert rec.split_version == 3 and (rec.seed, rec.held_out_ratio, rec.strata) == (7, 0.4, ("origin", "mode"))
    old = {a.item_id: a for a in r2().assignments}
    assert all(old[a.item_id] == a for a in rec.assignments if a.item_id in old)  # split dan added_in_version apa adanya
    assert {a.item_id: a.added_in_version for a in rec.assignments if a.item_id not in old} == {t.id: 3 for t in new}
    assert len(held(rec, [t.id for t in new])) == want and rec.control_in_held_out == 4
    if n == 1:  # tidak ada butir tolak di held-out: laporan held-out memuat kunci tolak bernilai 0/null saja
        items = [{"id": i.id, "origin": i.origin, "mode": i.mode, "split": rec.split_of()[i.id]} for i in r2_items() + new]
        rows = [ItemMetrics(10, 10, 20, 10, 1, 1, 1, item_id=i["id"], setting_id="S", split=i["split"]) for i in items if i["mode"] != TOL]
        rows += [ItemMetrics(0, 0, 30, 0, None, 0, 0, item_id="t1", setting_id="S", split="tune")]
        m = mode_report(items, rows, split="held_out")
        assert (m[TOL]["n_items"], m[TOL]["mean_span_recall"], m[TOL]["mean_token_precision"]) == (0, None, None)


# ============================================================================= SV8
def test_sv8_sequential_batches_equal_one_batch():
    recs = [r2()]
    items = r2_items()
    for batch in (["t1"], ["t2"], ["t3"], ["t4", "t5"]):
        new = [T[b] for b in batch]
        rec = ext(new, prev=recs[-1], items=items)
        prev_asg = {a.item_id: a for a in recs[-1].assignments}
        assert all(prev_asg[a.item_id] == a for a in rec.assignments if a.item_id in prev_asg)
        items = items + new
        recs.append(rec)
    assert [r.split_version for r in recs[1:]] == [3, 4, 5, 6]
    s = recs[-1].split_of()
    assert (s["t1"], s["t2"], s["t3"]) == ("tune", "held_out", "tune")
    assert len(held(recs[-1], ["t4", "t5"])) == 1 and len(held(recs[-1], T)) == 2  # = SV7 (e)
    assert ext([], prev=recs[-1], items=items) is recs[-1]  # tanpa butir baru: versi tidak naik


# ============================================================================= SV9
def test_sv9a_mixed_batch():
    rec = ext([T["t1"], T["t2"], P1, O["o1"]])
    s = rec.split_of()
    assert rec.split_version == 3 and s["p1"] == "tune" and s["o1"] == "tune" and len(held(rec, ["t1", "t2"])) == 1
    assert rec.control_in_held_out == 4


def test_sv9b_operator_tolak_counts_as_control():
    rec = ext([O["o1"], O["o2"]])
    assert len(held(rec, ["o1", "o2"])) == 1 and rec.control_in_held_out == 5  # V6 Dipilih (Q2 a)


# ============================================================================= dunia grid mainan (SV10, SV13)
def toy_grid_cfg(dest: Path) -> Path:
    """Config mainan: tiga setting (fixed_size x dense/bm25/hybrid), semua header_b = false, satu anggaran."""
    cfg = toy_config_dir(dest)
    g = cfg / "grid.toml"
    t = g.read_bytes().decode("utf-8")
    for a, b in (('chunkers = ["structure_handwritten", "structure_schema", "fixed_size"]', 'chunkers = ["fixed_size"]'),
                 ("header_b = [false, true]", "header_b = [false]"), ("default_tokens = 2000", "default_tokens = 40"),
                 ("comparison_tokens = [1000]", "comparison_tokens = []")):
        assert a in t
        t = t.replace(a, b)
    g.write_bytes(t.encode("utf-8"))
    return cfg


SPANS = [(12, 24), (25, 37), (38, 50), (52, 76), (124, 141), (102, 123)]


def item_row(it: GridItem, sha: str, k: int) -> dict:
    gold = [] if it.mode == TOL else [{"start": s, "end": e} for s, e in [SPANS[k % len(SPANS)]]]
    return {"id": it.id, "family": "uupt", "query": f"q {it.id}", "doc_id": "synthetic", "gold_spans": gold, "clean_sha256": sha,
            "mode": it.mode, "origin": it.origin, "review_status": None, "proposal_id": None, "reference_date": None,
            "scene_checked": False, "operator_note": None, "created_at": "2026-10-29T10:00:00Z"}


def write_items(butir: Path, version: int, items: list[GridItem], sha: str) -> None:
    butir.mkdir(parents=True, exist_ok=True)
    rows = [item_row(it, sha, k) for k, it in enumerate(items)]
    with open(butir / f"uupt.v{version}.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


@pytest.fixture
def world(tmp_path):
    doc = u_doc()
    cfg = toy_grid_cfg(tmp_path / "cfg")
    runs, butir = tmp_path / "runs", tmp_path / "butir"
    write_items(butir, 1, r2_items(), doc.clean_sha256)
    save_split_record(r2(), runs / "split")
    return {"doc": doc, "cfg": cfg, "runs": runs, "butir": butir, "tmp": tmp_path}


def plan_of(w, create_split=False):
    return make_plan("uupt", doc=w["doc"], tokenizer=ToyWs(), butir_dir=w["butir"], runs_dir=w["runs"], config_dir=w["cfg"],
                     create_split=create_split)


def grid(w, **kw):
    return run_family_grid("uupt", doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"], butir_dir=w["butir"], config_dir=w["cfg"],
                           encoder=FakeEncoder(), embed_cache_dir=w["tmp"] / "emb", **kw)


def tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()} if root.exists() else {}


# ============================================================================= SV10
def test_sv10_split_in_r3_and_grid_consistent(world):
    w = world
    write_items(w["butir"], 2, r2_items() + [T["t1"], T["t2"]], w["doc"].clean_sha256)
    split_dir = w["runs"] / "split"
    before = tree(split_dir)
    a = plan_of(w).split  # (a) R3: di memori, tanpa menulis
    assert a.split_version == 3 and tree(split_dir) == before and not (split_dir / "split_uupt_v0003.json").exists()
    d = make_split(r2_items() + [T["t1"], T["t2"]], family="uupt", seed=1, held_out_ratio=0.4, min_control=3, previous=r2())
    assert d == a and tree(split_dir) == before  # (d) fungsi murni yang dipakai laporan dampak V8
    res = grid(w)  # (b) run grid: split v3 ditulis, assignment identik
    assert (split_dir / "split_uupt_v0003.json").exists() and load_latest_split_record(split_dir, "uupt") == a
    assert res.envelope["split"] == a.to_dict()
    snap = tree(w["runs"])
    again = grid(w)  # (c) tanpa butir baru: versi tidak naik, tidak ada berkas baru
    assert again.cache_hit and again.envelope["split"]["split_version"] == 3 and tree(w["runs"]) == snap
    assert plan_of(w).split == a


# ============================================================================= SV13
def test_sv13_regrid_new_key_empty_window_no_spark(world, monkeypatch):
    import backend.spark as spark
    w = world

    def no_spark(*a, **k):
        raise AssertionError("Spark must not be called by the grid")
    monkeypatch.setattr(spark.SparkClient, "__init__", no_spark)
    calls: list[tuple[str, int]] = []
    real = grid_run.Pipeline

    class Counting(real):  # type: ignore[misc, valid-type]
        def __call__(self, setting, items):
            calls.append((setting.setting_id, len(items)))
            return super().__call__(setting, items)
    monkeypatch.setattr(grid_run, "Pipeline", Counting)

    k2 = grid(w)
    n_set = len(k2.envelope["settings_run"])
    assert n_set == 3 and all(not s["header_b"] for s in k2.envelope["settings_run"])
    assert calls == [(s["setting_id"], 20) for s in k2.envelope["settings_run"]] and len(k2.envelope["metrics"]) == 60
    assert k2.envelope["split"]["split_version"] == 2
    k2_bytes = k2.path.read_bytes()

    svc = Service(config_dir=w["cfg"], butir_dir=w["butir"], runs_dir=w["runs"], tokenizer=ToyWs())
    monkeypatch.setattr(svc, "grid_docs", lambda fam: {"doc": w["doc"]})
    monkeypatch.setattr(svc, "schema_binding", lambda fam="uupt": None)
    monkeypatch.setattr(svc, "header_binding", lambda fam="uupt": "HB")  # store header ada: rencana ber-header dibaca dulu
    real_plan = svc.plan

    def plan(family, *, create_split=False, headers=None, **kw):
        p = real_plan(family, create_split=create_split, **kw)
        return dataclasses.replace(p, key=hashlib.sha256(f"H{p.key}".encode()).hexdigest()) if headers is not None else p
    monkeypatch.setattr(svc, "plan", plan)
    store = RunFileStore(w["runs"] / "grid")
    hkey2 = hashlib.sha256(f"H{k2.key}".encode()).hexdigest()
    store.write(hkey2, {**k2.envelope, "key": hkey2})
    assert svc.stored_grid("uupt")[1]["key"] == hkey2  # sebelum butir baru: amplop ber-header lama

    write_items(w["butir"], 2, r2_items() + [T["t1"], T["t2"]], w["doc"].clean_sha256)
    p3 = plan_of(w)
    k3_key = grid_cache_key(w["doc"].clean_sha256, p3.config_hash, item_set_hash(p3.items), 3)
    assert p3.key == k3_key != k2.key and p3.config_hash == k2.record["config_hash"]
    plan_now, env_now = svc.stored_grid("uupt")  # (a) kedua kunci tidak ditemukan -> tanpa grid, bukan 500
    assert env_now is None and plan_now.key == k3_key

    def grid_metrics(fam):
        _p, env = svc.stored_grid(fam)
        return None if env is None else (svc.items(fam), env["metrics"])
    deps = dataclasses.replace(H.make_deps(w["tmp"]), grid_metrics=grid_metrics)
    with pytest.raises(ProfileError) as ei:  # (b)
        export_profile(deps, "uupt", H.P1["setting_id"])
    assert ei.value.kind == "validation_failed" and ei.value.message == "No grid result for this setting; run the grid first."

    calls.clear()
    k3 = grid(w)  # (c)
    assert k3.key == k3_key and not k3.cache_hit
    assert calls == [(s["setting_id"], 22) for s in k3.envelope["settings_run"]] and len(k3.envelope["metrics"]) == 66
    assert k2.path.read_bytes() == k2_bytes and k3.path.exists() and (w["runs"] / "split" / "split_uupt_v0003.json").exists()
    sel = lambda e: {b: s["setting_id"] for b, s in e["selections"].items()}  # noqa: E731
    assert sel(k3.envelope) == sel(k2.envelope)
    assert k3.envelope["quality"] == k2.envelope["quality"]
    old = {(m["setting_id"], m["item_id"]): m for m in k2.envelope["metrics"]}
    for m in k3.envelope["metrics"]:
        if m["item_id"] in ("t1", "t2"):
            assert m["gold_chars"] == 0
        else:
            assert {k: v for k, v in m.items() if k != "split"} == {k: v for k, v in old[(m["setting_id"], m["item_id"])].items() if k != "split"}
    ho = lambda e: {p["setting_id"]: p["mean_span_recall"] for p in e["points"] if p["split"] == "held_out"}  # noqa: E731
    assert ho(k3.envelope) == ho(k2.envelope)
    assert svc.stored_grid("uupt")[1]["key"] == k3_key


# ============================================================================= SV11, SV14
def im(iid, gold, cov, ret, gt, rank=None, parts=(0, 0), split="held_out", sid="S"):
    return ItemMetrics(gold, cov, ret, gt, rank, parts[0], parts[1], item_id=iid, setting_id=sid, split=split)


H1 = im("H1", 100, 100, 20, 10, 1, (1, 1))
H2 = im("H2", 100, 50, 32, 8, 2, (2, 1))
K = im("K", 0, 0, 25, 0)
T2 = im("t2", 0, 0, 300, 0)
ITEMS_HO = [{"id": "H1", "origin": OPR, "mode": LIT, "split": "held_out"}, {"id": "H2", "origin": SP, "mode": PAR, "split": "held_out"},
            {"id": "K", "origin": OPR, "mode": PAR, "split": "held_out"}, {"id": "t2", "origin": SP, "mode": TOL, "split": "held_out"}]


def test_sv11_held_out_block_and_profile(tmp_path):
    b0, b1 = held_out_block(ITEMS_HO[:3], [H1, H2, K]), held_out_block(ITEMS_HO, [H1, H2, K, T2])
    assert (b0["n_items"], b0["by_origin"]) == (3, {OPR: 2, SP: 1}) and (b1["n_items"], b1["by_origin"]) == (4, {OPR: 2, SP: 2})
    for b in (b0, b1):
        assert b["mean_span_recall"] == 0.75 and b["mean_token_precision"] == 0.375 and b["fully_covered"] == {"covered": 1, "total": 2}
    assert {k for k in b0 if b0[k] != b1[k]} == {"n_items", "by_origin"}
    rep = build_report("uupt", ITEMS_HO, [H1, H2, K, T2])
    assert rep["by_mode"][TOL] == {"n_items": 1, "n_gold": 0, "mean_span_recall": None, "mean_token_precision": None}
    assert mean_recall_at_k([H1, H2, K, T2]) == mean_recall_at_k([H1, H2]) == mean_recall_at_k([H1, H2, K])
    g0 = aggregate([H1, H2, K], setting_id="S", split="held_out", budget_tokens=1)
    g1 = aggregate([H1, H2, K, T2], setting_id="S", split="held_out", budget_tokens=1)
    assert g0.mean_retrieved_tokens == g1.mean_retrieved_tokens == 26 and g1.no_gold_count == 2
    # ekspor profil: hanya held_out.n_items dan held_out.by_origin yang berubah (created_at sama karena jam sama)
    sid = H.P1["setting_id"]
    prof = []
    for its, ms in ((ITEMS_HO[:3], [H1, H2, K]), (ITEMS_HO, [H1, H2, K, T2])):
        rows = [dataclasses.replace(m, setting_id=sid) for m in ms]
        prof.append(export_profile(H.make_deps(tmp_path / str(len(prof)), metrics=rows, items=its), "uupt", sid).profile)
    diff = {k for k in prof[0] if prof[0][k] != prof[1][k]}
    assert diff == {"held_out"} and {k for k in prof[0]["held_out"] if prof[0]["held_out"][k] != prof[1]["held_out"][k]} == {"n_items", "by_origin"}
    for k in ("chunk_set_hash", "config_hash", "corpus_hash", "setting"):
        assert prof[0][k] == prof[1][k]


def test_sv14_mode_and_origin_report_uupt():
    ms = [H1, H2, K, T2]
    m = mode_report(ITEMS_HO, ms, split="held_out")
    pick = lambda r: (r["n_items"], r["n_with_gold"], r["n_no_gold"], r["mean_span_recall"])  # noqa: E731
    assert pick(m[LIT]) == (1, 1, 0, 1.0) and pick(m[PAR]) == (2, 1, 1, 0.5)
    assert pick(m[TOL]) == (1, 0, 1, None) and m[TOL]["mean_token_precision"] is None and m[TOL]["fully_covered"] == {"covered": 0, "total": 0}
    o = origin_report(ITEMS_HO, ms, split="held_out")[SP]
    assert (o["n_items"], o["n_no_gold"]) == (2, 1)
    rep = build_report("uupt", ITEMS_HO, ms + [im("x", 10, 10, 10, 5, split="tune")])
    assert rep["title"] == TITLE_UUPT == "Held-out results" and [r["item_id"] for r in rep["rows"]] == ["H1", "H2", "K", "t2"]
    row = next(r for r in rep["rows"] if r["item_id"] == "t2")
    assert row["mode"] == TOL and row["note"] == NO_GOLD_NOTE == "no gold (must abstain)" and row["split"] == "held_out"
    assert "Transfer" not in json.dumps(rep)
    assert items_summary(ITEMS_HO)["by_mode"] == {LIT: 1, PAR: 2, TOL: 1}
    with pytest.raises(Exception):
        mode_report(ITEMS_HO, ms, split="bogus")
    # UU PT dilaporkan per split; split=None (akta) tidak memfilter apa pun
    assert mode_report(ITEMS_HO, ms, split="tune")[TOL]["n_items"] == 0


# ============================================================================= SV12
SIMPL = config.load("grid")["simplicity"]
P_SET = Setting("P", "uupt", "fixed_size", 256, 0, None, "hybrid", True, 2000)
Q_SET = Setting("Q", "uupt", "fixed_size", 256, 0, None, "bm25", False, 2000)
GOLD_IDS = ["g1", "g2", "g3", "g4"]
COV = {"P": [10, 10, 6, 6], "Q": [10, 6, 6, 2]}


def tune_pipeline(st, items):
    out = []
    for it in items:
        if it.mode == TOL:
            out.append(ItemMetrics(0, 0, 1000, 0, None, 0, 0, item_id=it.id))
        else:
            c = COV[st.setting_id][GOLD_IDS.index(it.id)]
            out.append(ItemMetrics(10, c, 100, 50, 1, 1, 1 if c == 10 else 0, item_id=it.id))
    return out


def tune_run(with_tolak: bool):
    items = [GridItem(i, "uupt", OPR, LIT) for i in GOLD_IDS] + ([T["t1"], T["t3"]] if with_tolak else [])
    rec = SplitRecord("uupt", 1, 7, 0.4, ("origin", "mode"), tuple(Assignment(i.id, "tune", 1) for i in items), 0)
    return run_grid(settings=[P_SET, Q_SET], items=items, pipeline=tune_pipeline, cache=MemoryGridCache(), clean_sha256="hu1",
                    config_hash="c", split_record=rec, simplicity=SIMPL, family="uupt")


def test_sv12_selection_not_shifted_by_tolak_in_tune():
    a, b = tune_run(False), tune_run(True)
    pts = {p.setting_id: p for p in b.points}
    assert (pts["P"].mean_span_recall, pts["Q"].mean_span_recall) == (Fraction(4, 5), Fraction(3, 5))
    assert pts["P"].n_gold == pts["Q"].n_gold == 4 and pts["P"].mean_retrieved_tokens == pts["Q"].mean_retrieved_tokens == 100
    assert {k: s.setting_id for k, s in a.selections.items()} == {k: s.setting_id for k, s in b.selections.items()} == {2000: "Q"}
    assert SIMPL["tie_margin_items"] == 1


# ============================================================================= SV15
def test_sv15_rejection_cells_and_must_abstain_uupt():
    ans_status = {"t2": "tolak", "t4": "bukti_tidak_cukup", "t5": "jawab", "K": "tolak", "H1": "jawab"}
    cases = {"t2": ("tolak", [], ["c1"], []), "t4": ("bukti_tidak_cukup", [], ["c1"], []), "t5": ("jawab", [(A11, T11)], ["c1"], []),
             "K": ("tolak", [], ["c1", "c2"], []), "H1": ("jawab", [(A11, T11)], ["c1", "c2"], G1)}
    cells = {k: cell(*v) for k, v in cases.items()}
    assert cells == {"t2": "abstained_correct", "t4": "abstained_correct", "t5": "answered_unsupported", "K": "abstained_correct",
                     "H1": "answered_supported"}
    verdicts, _ = grade_answer("x", ans("tolak"), UNITS, chunks("c1"), [], OP)
    assert verdicts == []  # jawaban tolak tidak diverifikasi
    v5, _ = grade_answer("x", ans("jawab", (A11, T11)), UNITS, chunks("c1"), [], OP)
    assert len(v5) == 1 and v5[0].result.valid_on_date == NOT_RUN and (v5[0].result.exists, v5[0].result.faithful) == ("lulus", "lulus")  # uji 3 tidak_dijalankan (reference_date = null)
    (s,) = summarize([("S", "best", "contributor", c) for c in cells.values()])
    assert (s.answered_supported, s.answered_unsupported, s.abstained_correct, s.abstained_should_answer, s.n_items) == (1, 1, 3, 0, 5)
    items = [{"id": "t2", "mode": TOL}, {"id": "t4", "mode": TOL}, {"id": "t5", "mode": TOL}, {"id": "K", "mode": PAR},
             {"id": "H1", "mode": LIT}, {"id": "t1", "mode": TOL}]
    answers = [{"item_id": k, "output": {"status": v}} for k, v in ans_status.items()]
    assert must_abstain_summary(items, answers) == {"n": 3, "abstained_correct": 2}  # K tidak dihitung (V7, Q3 a)
    # t1 (tune) ikut ringkasan mentah: tanpa filter split
    (s2,) = summarize([("S", "best", "contributor", c) for c in [*cells.values(), cell("tolak", [], ["c1"], [])]])
    assert (s2.abstained_correct, s2.n_items) == (4, 6)
    assert must_abstain_summary(items, answers + [{"item_id": "t1", "output": {"status": "tolak"}}]) == {"n": 4, "abstained_correct": 3}

