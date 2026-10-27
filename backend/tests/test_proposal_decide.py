"""M2.1 Tier 1: mesin status W5 (S1, S2, S3, S5, S6, S8, S9, S15, S16, S18, S29, S30). Klien Spark palsu, jam suntikan."""

import dataclasses
import threading

import pytest

from backend.proposal import prompt as pm
from backend.proposal.service import Hooks

from .proposal_fakes import Env, T0, at, valid_edit

APPROVE = {"decision": "disetujui", "edited": None, "operator_note": None}


def approve(note=None):
    return {"decision": "disetujui", "edited": None, "operator_note": note}


def change(edited=None, note=None):
    return {"decision": "diubah", "edited": edited or valid_edit(), "operator_note": note}


def reject(note=None):
    return {"decision": "ditolak", "edited": None, "operator_note": note}


def fresh(tmp_path, sub="e", modes=("literal", "parafrase"), **kw):
    env = Env(tmp_path / sub, **kw)
    return env, env.by_key(env.gen_ok(modes))


def err(r, status, code):
    assert r.status_code == status, r.text
    assert set(r.json()) == {"error"} and r.json()["error"]["code"] == code, r.text


# ---------------------------------------------------------------- S1
def test_s1_three_legal_transitions(tmp_path):
    env, ids = fresh(tmp_path, "a")
    r = env.decide(ids["L1"], approve("n1"))
    assert r.status_code == 200
    d = r.json()
    assert d["proposal"]["review_status"] == "disetujui" and d["proposal"]["reviewed_at"] == "2026-10-29T10:00:00Z"
    assert d["proposal"]["item_id"] and d["item"]["id"] == d["proposal"]["item_id"] and len(env.spark_items()) == 1
    env, ids = fresh(tmp_path, "b")
    d = env.decide(ids["L1"], change(valid_edit("QE", [(27, 43)]), None)).json()
    assert d["proposal"]["review_status"] == "diubah" and d["proposal"]["item_id"] and len(env.spark_items()) == 1
    env, ids = fresh(tmp_path, "c")
    d = env.decide(ids["L1"], reject("n3")).json()
    assert d["proposal"]["review_status"] == "ditolak" and d["proposal"]["item_id"] is None and d["item"] is None
    assert d["proposal"]["operator_note"] == "n3" and d["proposal"]["reviewed_at"] == "2026-10-29T10:00:00Z"
    assert not env.spark_items()


# ---------------------------------------------------------------- S2
def test_s2_no_transition_out_of_final_state(tmp_path):
    env, ids = fresh(tmp_path)
    pa, pb, pc = ids["L1"], ids["PA1"], ids["PA6"]
    assert env.decide(pa, approve("n0")).status_code == 200
    assert env.decide(pb, change(valid_edit("QB", [(10, 43)], "parafrase"), "n0")).status_code == 200
    assert env.decide(pc, reject("n0")).status_code == 200
    recs = {p: env.record_bytes(p) for p in (pa, pb, pc)}
    files = env.butir_snapshot()
    n = 0
    for p in (pa, pb, pc):
        for body in (approve("n1"), change(valid_edit("Q2"), "n1"), reject("n1")):
            err(env.decide(p, body), 409, "invalid_transition")
            n += 1
            assert env.record_bytes(p) == recs[p] and env.butir_snapshot() == files
    assert n == 9 and len(env.spark_items()) == 2


# ---------------------------------------------------------------- S3
@pytest.mark.parametrize("decision", ["usulan", "approved", "DISETUJUI", "Disetujui", None, "__missing__"])
def test_s3_invalid_decision_is_400(tmp_path, decision):
    env, ids = fresh(tmp_path, modes=("literal",))
    before = env.record_bytes(ids["L1"])
    body = {"edited": None, "operator_note": None}
    if decision != "__missing__":
        body["decision"] = decision
    err(env.decide(ids["L1"], body), 400, "invalid_request")
    assert env.record_bytes(ids["L1"]) == before and not env.spark_items()


def test_s3_unknown_id_is_404(tmp_path):
    env, _ids = fresh(tmp_path, modes=("literal",))
    err(env.decide("tidak-ada", reject()), 404, "not_found")
    err(env.decide("0123456789abcdef", reject()), 404, "not_found")
    assert not list((env.ps.records_dir).glob("0123*"))


# ---------------------------------------------------------------- S5
def test_s5_item_born_from_approved_proposal(tmp_path):
    env, ids = fresh(tmp_path, "a")
    d = env.decide(ids["L1"], approve("n1")).json()
    exp = {"family": "uupt", "query": "QL1", "doc_id": "doc-x", "gold_spans": [{"start": 27, "end": 43}], "clean_sha256": "hx1",
           "mode": "literal", "origin": "spark_disetujui", "review_status": "disetujui", "proposal_id": ids["L1"],
           "reference_date": None, "scene_checked": False, "operator_note": "n1", "created_at": "2026-10-29T10:00:00Z"}
    item = d["item"]
    assert item["id"] and {k: v for k, v in item.items() if k != "id"} == exp
    assert d["proposal"]["item_id"] == item["id"] and d["proposal"]["review_status"] == "disetujui"
    assert d["proposal"]["body"]["query"] == "QL1" and d["proposal"]["body"]["start"] == 27
    assert env.spark_items() == [item] and len({i["id"] for i in env.items_on_disk()}) == 3
    # (b) PA1: offset null -> gold = resolved_span
    env, ids = fresh(tmp_path, "b")
    d = env.decide(ids["PA1"], approve()).json()
    assert d["item"]["gold_spans"] == [{"start": 10, "end": 43}] and d["item"]["mode"] == "parafrase" and d["item"]["query"] == "QP1"
    assert d["proposal"]["body"]["start"] is None and d["proposal"]["body"]["end"] is None
    # (c) PA5: offset sebagian -> resolved_span
    env, ids = fresh(tmp_path, "c")
    d = env.decide(ids["PA5"], approve()).json()
    assert d["item"]["gold_spans"] == [{"start": 27, "end": 43}] and d["proposal"]["body"]["end"] is None


# ---------------------------------------------------------------- S6
def test_s6_changed_is_approved_after_edit_original_kept(tmp_path):
    env, ids = fresh(tmp_path, "a")
    ed = valid_edit("QE", [(10, 43)], "literal")
    d = env.decide(ids["L1"], change(ed)).json()
    it, pr = d["item"], d["proposal"]
    assert (it["query"], it["gold_spans"], it["mode"], it["origin"], it["review_status"]) == \
        ("QE", [{"start": 10, "end": 43}], "literal", "spark_disetujui", "diubah")
    assert pr["review_status"] == "diubah" and pr["edited"] == ed and pr["resolved_span"] == {"start": 27, "end": 43}
    assert pr["body"] == {"query": "QL1", "mode": "literal", "doc_id": "doc-x", "teks_gold": "(2) Ddd eee fff.", "start": 27, "end": 43}
    env, ids = fresh(tmp_path, "b")
    d = env.decide(ids["PA1"], change(valid_edit("QE2", [(27, 43)], "literal"))).json()
    assert d["item"]["mode"] == "literal" and d["item"]["origin"] == "spark_disetujui" and d["proposal"]["body"]["mode"] == "parafrase"


# ---------------------------------------------------------------- S8
def test_s8_failed_span_cannot_be_approved(tmp_path):
    def e(name):
        env, ids = fresh(tmp_path, name, modes=("literal",))
        return env, ids
    env, ids = e("s1")
    for k in ("L3", "L2", "L4", "L5"):
        before = env.record_bytes(ids[k])
        err(env.decide(ids[k], approve()), 422, "validation_failed")
        assert env.record_bytes(ids[k]) == before
    assert not env.spark_items()
    env, ids = e("s2")
    assert env.decide(ids["L3"], reject()).json()["proposal"]["review_status"] == "ditolak"
    env, ids = e("s3")
    d = env.decide(ids["L3"], change(valid_edit("QE", [(69, 85)]))).json()
    assert d["item"]["gold_spans"] == [{"start": 69, "end": 85}] and d["item"]["review_status"] == "diubah"
    env, ids = e("s4")
    assert env.decide(ids["L2"], change(valid_edit("QE", [(10, 26)]))).json()["item"]["gold_spans"] == [{"start": 10, "end": 26}]
    env, ids = e("s5")
    err(env.decide(ids["L4"], change(valid_edit("QE", [(80, 95)]))), 422, "validation_failed")
    assert env.ps.get(ids["L4"])["review_status"] == "usulan"
    env, ids = e("s6")
    assert env.decide(ids["L1"], approve()).json()["proposal"]["review_status"] == "disetujui"


# ---------------------------------------------------------------- S9
def test_s9_body_cannot_inject_origin_or_validation(tmp_path):
    env, ids = fresh(tmp_path, modes=("literal",))
    l1, l3 = ids["L1"], ids["L3"]
    bad = [
        (l1, {**approve(), "origin": "operator"}),
        (l3, {**approve(), "validation": {"offset_found": True, "text_matches": True}}),
        (l1, {"decision": "disetujui", "edited": valid_edit(), "operator_note": None}),
        (l1, {"decision": "ditolak", "edited": valid_edit(), "operator_note": None}),
        (l1, {"decision": "diubah", "edited": {**valid_edit(), "origin": "operator"}, "operator_note": None}),
        (l1, {"decision": "diubah", "edited": {**valid_edit(), "doc_id": "doc-y"}, "operator_note": None}),
        (l1, {**approve(), "review_status": "disetujui"}),
        (l1, {**approve(), "item_id": "X"}),
        (l1, {**approve(), "reviewed_at": "2020-01-01T00:00:00Z"}),
        (l1, {"decision": "diubah"}),
    ]
    snap = {k: env.record_bytes(k) for k in (l1, l3)}
    for pid, body in bad:
        err(env.decide(pid, body), 422, "validation_failed")
        assert {k: env.record_bytes(k) for k in (l1, l3)} == snap
    assert not env.spark_items()
    d = env.decide(l1, {"decision": "ditolak"}).json()  # (h): kunci dihilangkan
    assert d["proposal"]["operator_note"] is None and d["proposal"]["review_status"] == "ditolak"


# ---------------------------------------------------------------- S18
def test_s18_hash_mismatch_blocks_approve_and_edit_not_reject(tmp_path):
    env, ids = fresh(tmp_path)
    env.docs["doc-x"].clean_sha256 = "hx2"
    err(env.decide(ids["L1"], approve()), 409, "hash_mismatch")
    err(env.decide(ids["PA1"], change(valid_edit("QE", [(10, 43)], "parafrase"))), 409, "hash_mismatch")
    assert env.ps.get(ids["L1"])["review_status"] == "usulan" and not env.spark_items()
    assert env.decide(ids["L2"], reject()).status_code == 200
    env.docs["doc-x"].clean_sha256 = "hx1"
    d = env.decide(ids["L1"], approve()).json()
    assert d["item"]["clean_sha256"] == "hx1"


# ---------------------------------------------------------------- S29
def test_s29_times_come_from_w5_clock(tmp_path):
    env, ids = fresh(tmp_path)
    assert all(p["reviewed_at"] is None for p in env.ps.list_proposals())
    env.epoch = at(10, 5)
    a = env.decide(ids["L1"], approve()).json()
    env.epoch = at(10, 7)
    b = env.decide(ids["PA6"], reject()).json()
    env.epoch = at(10, 9)
    c = env.decide(ids["PA1"], change(valid_edit("QE", [(10, 43)], "parafrase"))).json()
    assert a["proposal"]["reviewed_at"] == a["item"]["created_at"] == "2026-10-29T10:05:00Z"
    assert b["proposal"]["reviewed_at"] == "2026-10-29T10:07:00Z"
    assert c["proposal"]["reviewed_at"] == c["item"]["created_at"] == "2026-10-29T10:09:00Z"
    runs = {r["created_at"] for r in env.ps._runs() for r in [r["run"]]}
    assert runs == {"2026-10-29T10:00:00Z"} and T0 > 0


# ---------------------------------------------------------------- S30
def test_s30_error_priority(tmp_path):
    env, ids = fresh(tmp_path, "a", modes=("literal",))
    err(env.decide("tidak-ada", {"decision": "x"}), 404, "not_found")
    env, ids = fresh(tmp_path, "b", modes=("literal",))
    env.decide(ids["L1"], approve())
    err(env.decide(ids["L1"], {"decision": "x"}), 400, "invalid_request")
    env, ids = fresh(tmp_path, "c", modes=("literal",))
    env.decide(ids["L1"], approve())
    err(env.decide(ids["L1"], {"decision": "diubah", "edited": valid_edit() | {"gold_spans": []}, "operator_note": None}), 409, "invalid_transition")
    env, ids = fresh(tmp_path, "d", modes=("literal",))
    env.decide(ids["L3"], reject())
    err(env.decide(ids["L3"], approve()), 409, "invalid_transition")
    env, ids = fresh(tmp_path, "e", modes=("literal",))
    err(env.decide(ids["L3"], {"decision": "disetujui", "edited": valid_edit(), "operator_note": None}), 422, "validation_failed")
    env, ids = fresh(tmp_path, "f", modes=("literal",))
    env.docs["doc-x"].clean_sha256 = "hx2"
    err(env.decide(ids["L3"], {"decision": "diubah", "edited": valid_edit() | {"gold_spans": []}, "operator_note": None}), 409, "hash_mismatch")
    env, ids = fresh(tmp_path, "g", modes=("literal",))
    err(env.decide(ids["L3"], {"decision": "x", "edited": "tak sah"}), 400, "invalid_request")
    assert env.ps.get(ids["L3"])["review_status"] == "usulan" and not env.spark_items()


# ---------------------------------------------------------------- S16
def _boom():
    raise OSError(r"C:\secret\path\disk full")


def _assert_clean_error(r):
    assert r.status_code >= 500 and set(r.json()) == {"error"} and set(r.json()["error"]) == {"code", "message"}
    t = r.text
    assert "Traceback" not in t and "secret" not in t and "OSError" not in t


def test_s16_all_or_nothing_storage(tmp_path):
    hooks = Hooks()
    env, ids = fresh(tmp_path, hooks=hooks)
    # (a) penyimpanan butir gagal
    hooks.before_item_write = _boom
    _assert_clean_error(env.decide(ids["L1"], approve()))
    rec = env.ps.get(ids["L1"])
    assert rec["review_status"] == "usulan" and rec["reviewed_at"] is None and not env.spark_items()
    hooks.before_item_write = None
    assert env.decide(ids["L1"], approve()).status_code == 200 and len(env.spark_items()) == 1
    # (b) butir tertulis, catatan gagal
    hooks.before_record_write = _boom
    _assert_clean_error(env.decide(ids["PA1"], approve()))
    assert env.ps.get(ids["PA1"])["review_status"] == "usulan"
    assert all(env.ps.get(i["proposal_id"])["review_status"] != "usulan" for i in env.spark_items())  # tanpa butir yatim
    assert len(env.spark_items()) == 1
    hooks.before_record_write = None
    assert env.decide(ids["PA1"], approve()).status_code == 200
    assert [i["proposal_id"] for i in env.spark_items()].count(ids["PA1"]) == 1
    # (c) ditolak gagal
    hooks.before_record_write = _boom
    _assert_clean_error(env.decide(ids["L4"], reject()))
    assert env.ps.get(ids["L4"])["review_status"] == "usulan"


# ---------------------------------------------------------------- S15
def _raw_decide(env, pid, body, out):
    from backend.api.errors import ApiError
    try:
        env.ps.decide(pid, body)
        out.append(200)
    except ApiError as exc:
        out.append(exc.status)


def test_s15a_sequential_double_approve(tmp_path):
    env, ids = fresh(tmp_path, modes=("literal",))
    assert env.decide(ids["L1"], approve()).status_code == 200
    err(env.decide(ids["L1"], approve()), 409, "invalid_transition")
    assert [i["proposal_id"] for i in env.spark_items()] == [ids["L1"]]


def _invariant(env):
    for p in env.ps.list_proposals():
        n = sum(1 for i in env.spark_items() if i["proposal_id"] == p["proposal_id"])
        assert (p["review_status"] in ("disetujui", "diubah")) == (n == 1) and n <= 1, p["proposal_id"]
        if p["review_status"] == "ditolak":
            assert n == 0


def test_s15b_c_concurrent_decisions(tmp_path):
    env, ids = fresh(tmp_path, modes=("parafrase",))
    for _ in range(20):
        env2, ids2 = fresh(tmp_path, f"r{_}", modes=("parafrase",))
        gate, out = threading.Barrier(2), []

        def run(body, env2=env2, pid=ids2["PA6"]):
            gate.wait()
            _raw_decide(env2, pid, body, out)
        ts = [threading.Thread(target=run, args=(approve(),)), threading.Thread(target=run, args=(reject(),))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert sorted(out) == [200, 409]
        _invariant(env2)
    gate, out = threading.Barrier(2), []

    def run2():
        gate.wait()
        _raw_decide(env, ids["PA1"], approve(), out)
    ts = [threading.Thread(target=run2) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(out) == [200, 409] and len(env.spark_items()) == 1


def test_s15_deterministic_hook_second_writer_loses(tmp_path):
    hooks = Hooks()
    env, ids = fresh(tmp_path, hooks=hooks, modes=("literal",))
    entered, release, out = threading.Event(), threading.Event(), []
    first = {}

    def hold():
        if threading.current_thread() is first.get("t"):
            entered.set()
            assert release.wait(10)
    hooks.after_read = hold
    t = threading.Thread(target=lambda: _raw_decide(env, ids["L1"], approve(), out))
    first["t"] = t
    t.start()
    assert entered.wait(10)
    second = []
    _raw_decide(env, ids["L1"], approve(), second)  # utas kedua jalan penuh
    release.set()
    t.join(10)
    assert second == [200] and out == [409] and len(env.spark_items()) == 1
    _invariant(env)


def test_s15d_w4_does_not_overwrite_w5_decision(tmp_path):
    hooks = Hooks()
    env, ids = fresh(tmp_path, hooks=hooks)
    old = {p["proposal_id"] for p in env.ps.list_proposals()}
    env.prompt_override = dataclasses.replace(pm.load_prompt(), prompt_hash="p2" * 32)
    entered, release = threading.Event(), threading.Event()
    state = {"n": 0, "box": []}

    def hold():
        state["n"] += 1
        if state["n"] == 1:
            entered.set()
            assert release.wait(10)
    hooks.before_w4_write = hold
    from fastapi.testclient import TestClient
    other = TestClient(env.app, raise_server_exceptions=False)
    t = threading.Thread(target=lambda: state["box"].append(
        other.post("/api/families/uupt/proposals/generate", json={"doc_id": "doc-x", "modes": ["literal", "parafrase"]})))
    t.start()
    assert entered.wait(10)
    assert env.decide(ids["L1"], approve()).status_code == 200
    release.set()
    t.join(20)
    assert state["box"][0].status_code == 200
    new = [p for p in env.ps.list_proposals() if p["proposal_id"] not in old]
    assert len(new) == 13 and all(p["review_status"] == "usulan" for p in new)
    l1 = env.ps.get(ids["L1"])
    assert l1["review_status"] == "disetujui" and l1["item_id"] and len(env.spark_items()) == 1
    _invariant(env)


def test_s16_commit_failure_restores_record_and_leaves_no_orphans(tmp_path):
    hooks = Hooks()
    env, ids = fresh(tmp_path, hooks=hooks, modes=("literal",))
    before = env.record_bytes(ids["L1"])
    hooks.before_item_commit = _boom  # catatan sudah ditulis, rename butir gagal
    _assert_clean_error(env.decide(ids["L1"], approve()))
    assert env.record_bytes(ids["L1"]) == before and not env.spark_items()
    assert not list(env.butir.glob("*.tmp")) and sorted(p.name for p in env.butir.glob("uupt.v*.jsonl")) == ["uupt.v1.jsonl"]
    hooks.before_item_commit = None
    assert env.decide(ids["L1"], approve()).status_code == 200 and len(env.spark_items()) == 1
