"""M2.1 Tier 1: W4 (S4, S11, S12, S13, S14, S17, S27, S28). Klien Spark palsu, direktori sementara, nol jaringan."""

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.api.app import Service
from backend.config import REPO_ROOT
from backend.proposal import prompt as pm
from backend.proposal.report import items_summary
from backend.proposal.service import ITEM_KEYS

from .proposal_fakes import EXPECT, LIT, PAR, Env, run_responder, valid_edit
from .spark_fakes import Resp, body_ok, budget_cfg
from .test_proposal_decide import approve, change, err, reject

REPO_V1 = REPO_ROOT / "data" / "butir" / "uupt.v1.jsonl"


def _git_butir() -> str:
    try:
        return subprocess.run(["git", "status", "--porcelain", "--", "data/butir"], cwd=REPO_ROOT, capture_output=True, text=True,
                              timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


@pytest.fixture(scope="module", autouse=True)
def _repo_butir_untouched():
    """S17: berkas butir repo tidak berubah oleh sesi test ini (hash dan git status sebelum = sesudah)."""
    h0 = hashlib.sha256(REPO_V1.read_bytes()).hexdigest()
    g0 = _git_butir()
    yield
    assert hashlib.sha256(REPO_V1.read_bytes()).hexdigest() == h0
    assert _git_butir() == g0


def load_real(env: Env) -> list[dict]:
    return Service(runs_dir=env.runs, butir_dir=env.butir).items("uupt")


# ---------------------------------------------------------------- S4
def test_s4_no_path_from_proposal_to_evaluation(tmp_path):
    env = Env(tmp_path)
    ids = env.by_key(env.gen_ok())
    ids_of = lambda: {i["id"] for i in load_real(env)}  # noqa: E731
    assert ids_of() == {"OP1", "OP2"} and items_summary(load_real(env))["n_items"] == 2  # (i) 13 usulan, nol butir
    env.decide(ids["L1"], reject())
    assert ids_of() == {"OP1", "OP2"}  # (ii)
    d = env.decide(ids["PA1"], approve()).json()
    now = load_real(env)
    assert {i["id"] for i in now} == {"OP1", "OP2", d["item"]["id"]} and items_summary(now)["n_items"] == 3  # (iii)
    assert next(i for i in now if i["id"] == d["item"]["id"])["origin"] == "spark_disetujui"
    fresh = Service(runs_dir=env.runs, butir_dir=env.butir)  # (iv) proses baru: objek baru, baca disk
    assert {i["id"] for i in fresh.items("uupt")} == ids_of()
    import shutil
    shutil.rmtree(env.ps.base)  # (v) catatan usulan dibuang seluruhnya
    assert len(load_real(env)) == 3


# ---------------------------------------------------------------- S11
def test_s11_w4_calls_stores_runs_makes_no_items(tmp_path):
    env = Env(tmp_path)
    files = env.butir_snapshot()
    d = env.gen_ok()
    assert env.tr.calls == 2 and len(d["proposals"]) == 13 and len(d["runs"]) == 2
    assert [r["kind"] for r in d["runs"]] == ["spark_d", "spark_d"] and all(r["status"] == "ok" for r in d["runs"])
    for r in d["runs"]:
        assert r["model"] == "muse-spark-1.3-contributor" and r["prompt_hash"] and r["clean_sha256"] == "hx1" and r["prompt_version"] == "v1"
    run_ids = {r["run_id"] for r in d["runs"]}
    assert {p["run_id"] for p in d["proposals"]} == run_ids and len({p["proposal_id"] for p in d["proposals"]}) == 13
    assert all(p["family"] == "uupt" for p in d["proposals"])
    modes_in_calls = ["parafrase" if "\nMODE: parafrase\n" in r["input"] else "literal" for r in env.tr.requests]
    assert modes_in_calls == ["literal", "parafrase"]
    assert all(r["body"]["text"]["format"]["strict"] is True and "tools" not in r["body"] for r in env.tr.requests)
    assert len(env.spark_items()) == 0 and env.butir_snapshot() == files
    # replay (a): run tersimpan untuk kedua mode -> dari disk, nol panggilan
    rp = Env(tmp_path, replay=True)
    r = rp.gen(("literal", "parafrase"))
    assert r.status_code == 200 and rp.tr.calls == 0 and len(r.json()["proposals"]) == 13
    assert [x["status"] for x in r.json()["runs"]] == ["replay", "replay"]


def test_s11_replay_without_stored_run(tmp_path):
    env = Env(tmp_path, replay=True)
    err(env.gen(("literal", "parafrase")), 409, "replay_no_stored_run")
    assert env.tr.calls == 0 and env.ps.list_proposals() == []


# ---------------------------------------------------------------- S12
def test_s12_second_w4_is_cache_hit_and_keeps_decisions(tmp_path):
    env = Env(tmp_path)
    first = env.gen_ok()
    ids = env.by_key(first)
    env.decide(ids["L1"], approve())
    env.decide(ids["L4"], reject())
    env.decide(ids["PA2"], change(valid_edit("QE", [(27, 43)], "parafrase")))
    d2 = env.gen_ok()
    assert env.tr.calls == 2 and [r["status"] for r in d2["runs"]] == ["cached", "cached"]
    assert len(d2["proposals"]) == 13 and len(env.ps.list_proposals()) == 13
    assert [p["proposal_id"] for p in d2["proposals"]] == [p["proposal_id"] for p in first["proposals"]]
    st = {p["body"]["query"]: p["review_status"] for p in d2["proposals"]}
    assert st["QL1"] == "disetujui" and st["QL4"] == "ditolak" and st["QP2"] == "diubah"
    assert sum(1 for p in d2["proposals"] if p["review_status"] == "usulan") == 10
    assert next(p for p in d2["proposals"] if p["body"]["query"] == "QL1")["item_id"]
    assert next(p for p in d2["proposals"] if p["body"]["query"] == "QP2")["edited"] == valid_edit("QE", [(27, 43)], "parafrase")
    assert len(env.spark_items()) == 2
    d3 = env.gen_ok(("literal",))
    assert [p["body"]["query"] for p in d3["proposals"]] == ["QL1", "QL2", "QL3", "QL4", "QL5"] and env.tr.calls == 2


# ---------------------------------------------------------------- S13
def test_s13_cap_after_semantic_discard_keeps_order(tmp_path):
    env = Env(tmp_path, max_proposals=3)
    d = env.gen_ok()
    assert [p["body"]["query"] for p in d["proposals"]] == ["QL1", "QL2", "QL3", "QP1", "QP2", "QP3"]
    cfg_default = Env(tmp_path / "d").ps.max_proposals
    assert cfg_default == 20  # dibaca dari config/proposals.toml


# ---------------------------------------------------------------- S14
def test_s14_invalid_requests_and_spark_errors(tmp_path):
    env = Env(tmp_path / "a")
    err(env.gen(("literal",), doc_id="nope"), 404, "not_found")
    for m in ([], ["literal", "campur"], None, "literal"):
        err(env.gen(m), 400, "invalid_request")
    err(env.http.post("/api/families/uupt/proposals/generate", json={"doc_id": "doc-x"}), 400, "invalid_request")  # modes hilang
    assert env.tr.calls == 0 and env.ps.list_proposals() == []
    d = env.gen(["literal", "literal"])  # (d)
    assert d.status_code == 200 and env.tr.calls == 1 and len(d.json()["proposals"]) == 5 and len(d.json()["runs"]) == 1
    env = Env(tmp_path / "e", budget=budget_cfg(total=1, role=1))  # (e)
    err(env.gen(), 402, "budget_exceeded")
    assert env.tr.calls == 0 and env.ps.list_proposals() == []
    env = Env(tmp_path / "f", script=[Resp(200, body_ok({"bukan_usulan": []}))])  # (f)
    r = env.gen(("literal",))
    err(r, 502, "model_error")
    assert "Traceback" not in r.text and env.ps.list_proposals() == [] and env.tr.calls == 1
    r2 = env.gen(("literal",))
    assert r2.status_code == 200 and env.tr.calls == 2 and len(r2.json()["proposals"]) == 5  # tidak di-cache sebagai sah


# ---------------------------------------------------------------- S17
def test_s17_operator_file_untouched_and_new_file_is_clean(tmp_path):
    env = Env(tmp_path)
    ids = env.by_key(env.gen_ok())
    h_v1 = hashlib.sha256(env.v1_bytes).hexdigest()
    a = env.decide(ids["L1"], approve()).json()
    b = env.decide(ids["PA1"], change(valid_edit("QE", [(10, 43)], "parafrase"))).json()
    assert hashlib.sha256((env.butir / "uupt.v1.jsonl").read_bytes()).hexdigest() == h_v1
    fresh = load_real(env)
    assert len(fresh) == 4 and len({i["id"] for i in fresh}) == 4
    assert sorted(i["origin"] for i in fresh) == ["operator", "operator", "spark_disetujui", "spark_disetujui"]
    newest = sorted(env.butir.glob("uupt.v*.jsonl"))[-1]
    raw = newest.read_bytes()
    assert newest.name != "uupt.v1.jsonl" and raw.endswith(b"\n") and b"\r" not in raw
    for line in raw.decode("utf-8").split("\n"):
        if line:
            assert set(json.loads(line)) == set(ITEM_KEYS)
    assert raw.startswith(env.v1_bytes)  # byte operator dipertahankan persis
    assert a["item"]["id"] != b["item"]["id"]
    assert env.ps.get(ids["L1"])["body"]["query"] == "QL1"


# ---------------------------------------------------------------- S27
def test_s27_cache_key_tracks_document_prompt_model(tmp_path):
    env = Env(tmp_path)
    first = env.gen_ok()
    ids = env.by_key(first)
    ok_run_ids = {r["run_id"] for r in first["runs"]}
    old_ids = [p["proposal_id"] for p in first["proposals"]]
    env.decide(ids["L1"], approve())
    env.decide(ids["L4"], reject())
    n_records = len(list((env.runs / "spark" / "records").glob("*.json")))
    # (a) tanpa perubahan
    a = env.gen_ok()
    assert env.tr.calls == 2 and [r["status"] for r in a["runs"]] == ["cached"] * 2 and {r["run_id"] for r in a["runs"]} == ok_run_ids
    assert [p["proposal_id"] for p in a["proposals"]] == old_ids
    assert len(list((env.runs / "spark" / "records").glob("*.json"))) == n_records  # tidak ada RunRecord baru
    # (b) dokumen melaporkan hx2
    env.docs["doc-x"].clean_sha256 = "hx2"
    b = env.gen_ok()
    assert env.tr.calls == 4 and [r["status"] for r in b["runs"]] == ["ok", "ok"] and all(r["clean_sha256"] == "hx2" for r in b["runs"])
    assert len(b["proposals"]) == 13 and not ({p["proposal_id"] for p in b["proposals"]} & set(old_ids))
    assert len(env.ps.list_proposals()) == 26
    st = {p["proposal_id"]: p["review_status"] for p in env.ps.list_proposals()}
    assert st[ids["L1"]] == "disetujui" and len(env.spark_items()) == 1
    # (c) hash kembali hx1, prompt p2
    env.docs["doc-x"].clean_sha256 = "hx1"
    env.prompt_override = dataclasses.replace(pm.load_prompt(), prompt_hash="p2" * 32)
    c = env.gen_ok()
    assert env.tr.calls == 6 and all(r["status"] == "ok" and r["prompt_hash"] == "p2" * 32 for r in c["runs"])
    assert len(c["proposals"]) == 13 and len(env.ps.list_proposals()) == 39
    # (d) kembali ke p1
    env.prompt_override = None
    d = env.gen_ok()
    assert env.tr.calls == 6 and [r["status"] for r in d["runs"]] == ["cached"] * 2 and {r["run_id"] for r in d["runs"]} == ok_run_ids
    assert [p["proposal_id"] for p in d["proposals"]] == old_ids
    assert {p["run_id"] for p in env.ps.list_proposals()} .isdisjoint({r["run_id"] for r in a["runs"] if r["status"] == "cached"} - ok_run_ids)
    # (e) model berganti
    env.model["profiles"]["meta"]["model"] = "M2"
    e = env.gen_ok()
    assert env.tr.calls == 8 and all(r["status"] == "ok" and r["model"] == "M2" for r in e["runs"])
    # (f) Item.id unik untuk isi identik dari run berbeda
    env.prompt_override = dataclasses.replace(pm.load_prompt(), prompt_hash="p2" * 32)
    env.model["profiles"]["meta"]["model"] = "muse-spark-1.3-contributor"
    l1b = next(p for p in env.gen_ok()["proposals"] if p["body"]["query"] == "QL1")
    assert l1b["proposal_id"] != ids["L1"]
    r = env.decide(l1b["proposal_id"], approve())
    assert r.status_code == 200
    sp = [i for i in env.spark_items() if i["query"] == "QL1"]
    assert len(sp) == 2 and sp[0]["id"] != sp[1]["id"] and sp[0]["proposal_id"] != sp[1]["proposal_id"]
    assert sp[0]["gold_spans"] == sp[1]["gold_spans"] and sp[0]["mode"] == sp[1]["mode"]


# ---------------------------------------------------------------- S28
DU = "\U0001F600 “perseroan” — Pasal 1 ayat (2)\nAaa.\n"
Q1 = "apa arti “perseroan” — \U0001F600?"
GOLD = "“perseroan” — Pasal 1"

_SCRIPT = r'''
import json, sys
from pathlib import Path
from backend.proposal.service import DocInfo, ProposalService
args = json.loads(Path(sys.argv[1]).read_bytes().decode("utf-8"))
doc = DocInfo("doc-u", "uupt", args["doc_text"], "hu1")
ps = ProposalService(runs_dir=Path(args["runs"]), butir_dir=Path(args["butir"]), doc_provider=lambda d: doc, clock=lambda: 1793268000.0)
for pid, body in args["decisions"]:
    ps.decide(pid, body)
'''


def test_s28_utf8_storage_under_cp1252_locale(tmp_path):
    assert len(DU) == 38 and len(DU.encode("utf-16-le")) // 2 == 39 and len(DU.encode("utf-8")) == 47 and len(GOLD) == 21
    u = lambda q: {"query": q, "mode": "literal", "doc_id": "doc-u", "teks_gold": GOLD, "start": None, "end": None}  # noqa: E731
    env = Env(tmp_path, doc_text=DU, doc_id="doc-u", sha="hu1", default=run_responder(lit=[u(Q1), u(Q1 + " 2")]))
    p = env.gen_ok(("literal",), doc_id="doc-u")["proposals"]
    assert [x["resolved_span"] for x in p] == [{"start": 2, "end": 23}] * 2
    note = "catatan — é"
    qe = "“QE” \U0001F600"
    args = {"doc_text": DU, "runs": str(env.runs), "butir": str(env.butir),
            "decisions": [[p[0]["proposal_id"], {"decision": "disetujui", "edited": None, "operator_note": note}],
                          [p[1]["proposal_id"], {"decision": "diubah", "edited": {"query": qe, "gold_spans": [{"start": 2, "end": 23}], "mode": "literal"},
                                                  "operator_note": None}]]}
    argf, script = tmp_path / "args.json", tmp_path / "w.py"
    argf.write_bytes(json.dumps(args, ensure_ascii=False).encode("utf-8"))
    script.write_text(_SCRIPT, encoding="utf-8", newline="\n")
    penv = {**os.environ, "PYTHONUTF8": "0", "PYTHONPATH": str(REPO_ROOT)}
    penv.pop("PYTHONIOENCODING", None)
    r = subprocess.run([sys.executable, "-X", "utf8=0", str(script), str(argf)], cwd=REPO_ROOT, env=penv, capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode("cp1252", "replace")
    newest = sorted(env.butir.glob("uupt.v*.jsonl"))[-1]
    files = [newest, *sorted(env.ps.records_dir.glob("*.json"))]
    for f in files:
        raw = f.read_bytes()
        txt = raw.decode("utf-8")  # ketat
        assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw and "â€" not in txt
    items = [json.loads(x) for x in newest.read_bytes().decode("utf-8").split("\n") if x][2:]
    by = {i["proposal_id"]: i for i in items}
    a, b = by[p[0]["proposal_id"]], by[p[1]["proposal_id"]]
    assert a["query"] == Q1 and a["operator_note"] == note and a["gold_spans"] == [{"start": 2, "end": 23}]
    assert b["query"] == qe and b["gold_spans"] == [{"start": 2, "end": 23}]
    raw = newest.read_bytes()
    again = b"".join((json.dumps(json.loads(x), sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
                     for x in raw.decode("utf-8").split("\n") if x)
    assert again == raw  # baca lalu tulis ulang = byte identik
    assert env.ps.get(p[0]["proposal_id"])["body"]["query"] == Q1


def test_queue_endpoint_lists_pending_and_context_lines(tmp_path):
    env = Env(tmp_path)
    ids = env.by_key(env.gen_ok())
    env.decide(ids["L1"], reject())
    d = env.http.get("/api/families/uupt/proposals").json()
    assert len(d["proposals"]) == 13 and d["pending"] == 12 and d["context_lines"] == 2
    assert env.http.get("/api/families/xyz/proposals").status_code == 400
