"""W57: header B keluarga akta (dua akta mainan, klien palsu, tanpa jaringan): proyeksi per akta dan total dengan faktor G-36,
gerbang belanja, rencana (unit tersimpan dilewati), run dengan ulang H-081, dan UU PT tidak berubah."""

import json
from types import SimpleNamespace

import pytest

from backend import config
from backend.header_b import family as fam
from backend.header_b.caller import load_header
from backend.header_b.prompt import load_prompt
from backend.header_b.render import build_prefix
from backend.header_b.run import HeaderConfigError, Prepared, load_all_configs, prepare, project
from backend.header_b.units import Unit

from .spark_fakes import Resp, Rig, body_ok
from .test_header_b_core import MAXH, Tok

import re

PROMPT = load_prompt(MAXH)
HC, MODEL, BUDGET, RCFG, GCFG = load_all_configs()
HC = {**HC, "max_header_tokens": MAXH, "max_consecutive_errors": 50, "cache_guard_calls": 0}


def toy(doc_id, sha, n_pasal, n_fixed):
    text = "\n".join(f"Pasal {i} isi {doc_id}" for i in range(1, n_pasal + 1)) + "\n"
    doc = SimpleNamespace(doc_id=doc_id, text=text, clean_sha256=sha * 64, sha256="s" + sha, loader_rules_version="akta-1")
    pre = build_prefix(PROMPT, doc, Tok())
    whole = [Unit(f"{doc_id}-w", f"Akta {doc_id} › Batang Tubuh", text, 99, (f"{doc_id}-w",), 0, len(text))]
    fixed = [Unit(f"{doc_id}-f{i}", f"Akta {doc_id} › Batang Tubuh", f"potongan {i}", 2, (f"{doc_id}-f{i}",)) for i in range(n_fixed)]
    schema = [Unit(f"{doc_id}-s{i}", f"Akta {doc_id} › Pasal {i}", f"Pasal {i}", 2, (f"{doc_id}-s{i}",)) for i in range(n_pasal)]
    return {"pasal": Prepared(doc, PROMPT, pre, whole, "pasal"), "fixed_size": Prepared(doc, PROMPT, pre, fixed, "fixed_size"),
            "structure_schema": Prepared(doc, PROMPT, pre, schema, "structure_schema")}


def family():
    return {"akta-t1": toy("akta-t1", "a", 3, 2), "akta-t2": toy("akta-t2", "b", 4, 2)}


def put(hdir, gran, cid):
    d = hdir / gran / PROMPT.prompt_hash[:12]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{cid}.json").write_text(json.dumps({"chunk_id": cid, "header": "H"}), encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- faktor dan gerbang
def test_upper_bound_is_ceiling_of_expected_times_factor():
    assert fam.upper_bound(0, 15700) == 0
    assert fam.upper_bound(10000, 15700) == 15700
    assert fam.upper_bound(1, 15700) == 2 and fam.upper_bound(3, 15700) == 5  # 4,71 -> 5


GATE_CFG = {"batch_gate": {"factor_bp": 15700, "batch_cap_micros": 2_000_000, "cumulative_cap_micros": 20_000_000,
                           "cumulative_pct": 80}}


def test_gate_config_is_read_from_batch_gate_and_validated():
    assert fam.batch_gate_cfg(GATE_CFG)["factor_bp"] == 15700
    assert fam.batch_gate_cfg(BUDGET)["batch_cap_micros"] == 2_000_000  # config/budget nyata
    for bad in ({}, {"batch_gate": {**GATE_CFG["batch_gate"], "factor_bp": 100}},
                {"batch_gate": {k: v for k, v in GATE_CFG["batch_gate"].items() if k != "batch_cap_micros"}}):
        with pytest.raises(HeaderConfigError):
            fam.batch_gate_cfg(bad)


def test_gate_rejects_single_and_cumulative_over_limit():
    thr = 16_000_000  # 20.000.000 * 80%
    assert fam.gate(2_000_000, 0, GATE_CFG)["verdict"] == "allow"
    g = fam.gate(2_000_001, 0, GATE_CFG)
    assert g["verdict"] == "reject" and len(g["reasons"]) == 1 and "batch_cap" in g["reasons"][0]
    assert fam.gate(1_000_000, thr - 1_000_000, GATE_CFG)["verdict"] == "allow"
    g = fam.gate(1_000_000, thr - 999_999, GATE_CFG)
    assert g["verdict"] == "reject" and "cumulative" in g["reasons"][0] and g["cumulative_limit"] == thr
    assert len(fam.gate(2_000_001, thr, GATE_CFG)["reasons"]) == 2


def test_precheck_gate_then_caps():
    ok = {"gate": {"verdict": "allow", "reasons": []}, "total": {"expected": 100}}
    kw = dict(spent_b=0, spent_total=0, per_role_b_cap=1000, total_cap=1000)
    assert fam.precheck(ok, **kw) is None
    assert fam.precheck(ok, **{**kw, "spent_b": 901}).startswith("budget_exceeded")  # cap peran b
    assert fam.precheck(ok, **{**kw, "spent_total": 901}).startswith("budget_exceeded")  # cap total
    assert fam.precheck(ok, **{**kw, "spent_b": 900, "spent_total": 900}) is None  # batas inklusif
    rej = {"gate": fam.gate(2_000_001, 0, GATE_CFG), "total": {"expected": 1}}
    assert fam.precheck(rej, **kw).startswith("gate_rejected")


# ---------------------------------------------------------------- rencana dan proyeksi
def test_plan_skips_stored_units_for_all_chunk_ids(tmp_path):
    p = family()["akta-t1"]["fixed_size"]
    put(tmp_path, "fixed_size", "akta-t1-f0")
    pl = fam.plan_prepared(p, tmp_path)
    assert [u.key for u in pl.stored] == ["akta-t1-f0"] and [u.key for u in pl.call] == ["akta-t1-f1"]
    assert [u.key for u in fam.plan_prepared(p, tmp_path, limit=1).call] == []
    assert not (tmp_path / "pasal").exists()  # perencanaan tidak menulis


def test_family_projection_per_doc_and_total_with_g36_factor(tmp_path):
    prepared = family()
    res = fam.project_family(prepared, tmp_path, Tok(), HC, MODEL, GATE_CFG, spent=100)
    assert set(res["per_doc"]) == {"akta-t1", "akta-t2"} and res["factor_bp"] == 15700
    t = res["total"]
    for d, row in res["per_doc"].items():
        for s, r in row["sources"].items():
            solo = project(Prepared(prepared[d][s].doc, PROMPT, prepared[d][s].prefix, prepared[d][s].units, s), Tok(), HC, MODEL)
            assert r["expected"] == solo["cost_usd_micros"]["expected"] > 0
            assert r["upper_g36"] == -(-r["expected"] * 15700 // 10000) >= r["expected"]
            assert r["units"] == len(prepared[d][s].units) and r["to_call"] == r["units"]
        assert row["expected"] == sum(r["expected"] for r in row["sources"].values())
        assert row["upper_g36"] == sum(r["upper_g36"] for r in row["sources"].values())
    assert t["expected"] == sum(r["expected"] for r in res["per_doc"].values())
    assert t["upper_g36"] == sum(r["upper_g36"] for r in res["per_doc"].values())
    assert t["calls"] == sum(len(prepared[d][s].units) + 1 for d in prepared for s in prepared[d])
    assert res["per_doc"]["akta-t1"]["sources"]["pasal"]["max_unit_tokens"] == 99
    assert res["gate"]["verdict"] == "allow" and res["gate"]["spent_cumulative"] == 100


def test_stored_units_leave_projection_and_zero_when_all_stored(tmp_path):
    prepared = family()
    full = fam.project_family(prepared, tmp_path, Tok(), HC, MODEL, GATE_CFG, spent=0)
    for s, p in prepared["akta-t1"].items():
        for u in p.units:
            put(tmp_path, s, u.key)
    part = fam.project_family(prepared, tmp_path, Tok(), HC, MODEL, GATE_CFG, spent=0)
    assert part["per_doc"]["akta-t1"]["expected"] == 0 and part["per_doc"]["akta-t1"]["sources"]["pasal"]["already_stored"] == 1
    assert part["per_doc"]["akta-t2"]["expected"] == full["per_doc"]["akta-t2"]["expected"]
    assert part["total"]["calls"] == full["per_doc"]["akta-t2"]["sources"]["pasal"]["calls"] + sum(
        full["per_doc"]["akta-t2"]["sources"][s]["calls"] for s in ("fixed_size", "structure_schema"))


def test_projection_gate_rejects_when_cumulative_would_exceed(tmp_path):
    res = fam.project_family(family(), tmp_path, Tok(), HC, MODEL, GATE_CFG, spent=16_000_000)
    assert res["gate"]["verdict"] == "reject"
    assert all(r["gate"]["verdict"] == "reject" for r in res["per_doc"].values())


def test_unit_is_stored_only_when_all_chunk_ids_are_stored(tmp_path):
    """Unit pasal memberi header ke banyak potongan: sebagian tersimpan = belum tersimpan (cegah mutan all -> any)."""
    p = family()["akta-t1"]["pasal"]
    multi = Unit("m0", "Akta › Pasal 1", "x", 1, ("m0", "m1", "m2"), 0, 1)
    p = Prepared(p.doc, p.prompt, p.prefix, [multi], "pasal")
    put(tmp_path, "pasal", "m0")
    assert [u.key for u in fam.plan_prepared(p, tmp_path).call] == ["m0"]
    put(tmp_path, "pasal", "m1")
    assert fam.plan_prepared(p, tmp_path).stored == [] and len(fam.plan_prepared(p, tmp_path).call) == 1
    put(tmp_path, "pasal", "m2")
    pl = fam.plan_prepared(p, tmp_path)
    assert pl.call == [] and [u.key for u in pl.stored] == ["m0"]


# ---------------------------------------------------------------- run live (klien palsu)
def responder(fail_first=None):
    seen: dict[str, int] = {}

    def act(tr, request):
        body = json.loads(request.content.decode("utf-8"))
        cid = re.search(r"chunk_id: (\S+)", body["input"]).group(1)
        seen[cid] = seen.get(cid, 0) + 1
        too_long = fail_first and cid in fail_first and seen[cid] <= fail_first[cid]
        return Resp(200, body_ok({"chunk_id": cid, "header": "satu dua tiga empat lima enam tujuh" if too_long else "Konteks singkat"}))
    return act, seen


def meta_for(p):
    return {"clean_sha256": p.doc.clean_sha256}


def run(rig, prepared, hdir, **kw):
    return fam.run_family(rig.client, prepared, tokenizer=Tok(), headers_dir=hdir, header_cfg=HC, meta_for=meta_for, **kw)


def test_run_stores_every_unit_and_rerun_makes_no_calls(tmp_path):
    act, seen = responder()
    rig = Rig(tmp_path, default=act)
    prepared, hdir = family(), tmp_path / "h"
    out = run(rig, prepared, hdir)
    assert out["stopped"] is None and out["failed"] == {}
    for d, srcs in prepared.items():
        for s, p in srcs.items():
            assert all(load_header(hdir, s, PROMPT, cid) is not None for u in p.units for cid in u.chunk_ids)
    n = len(rig.tr.requests)
    out2 = run(rig, prepared, hdir)
    assert out2["stored"] == 0 and len(rig.tr.requests) == n


def test_failed_unit_is_retried_then_succeeds_and_hopeless_one_fails_honestly(tmp_path):
    act, seen = responder({"akta-t1-f1": 2, "akta-t2-s0": 99})
    rig = Rig(tmp_path, default=act)
    prepared, hdir = family(), tmp_path / "h"
    out = run(rig, prepared, hdir, max_attempts=4)
    assert out["stopped"] is None
    assert load_header(hdir, "fixed_size", PROMPT, "akta-t1-f1") is not None and out["attempts"]["akta-t1/fixed_size"] == 3
    assert out["failed"] == {"akta-t2/structure_schema": ["akta-t2-s0"]}  # gagal jujur, tanpa fallback
    assert load_header(hdir, "structure_schema", PROMPT, "akta-t2-s0") is None
    assert out["attempts"]["akta-t2/structure_schema"] == 4


# ---------------------------------------------------------------- UU PT tidak berubah
def test_uupt_projection_is_byte_identical_to_stored_file():
    path = next(iter((config.REPO_ROOT / "runs" / "headers" / "projection").glob("uupt-40-2007-*-9904b5355886.json")), None)
    if path is None:
        pytest.skip("no stored UU PT projection for the active prompt")
    from backend.tokenizer import get_tokenizer
    tok = get_tokenizer()
    stored = json.loads(path.read_text(encoding="utf-8"))["projections"]
    kw = dict(tokenizer=tok, header_cfg=HC_REAL(), retrieval_cfg=RCFG, grid_cfg=GCFG)
    first = prepare("pasal", **kw)
    for s in ("pasal", "ayat", "fixed_size"):
        p = first if s == "pasal" else prepare(s, doc=first.doc, prompt=first.prompt, **kw)
        assert project(p, tok, kw["header_cfg"], MODEL) == stored[s]


def HC_REAL():
    return load_all_configs()[0]
