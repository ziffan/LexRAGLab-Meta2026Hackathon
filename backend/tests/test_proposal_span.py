"""M2.1 Tier 1: validasi span (S26 tingkat fungsi), usulan D lewat W4 (S10, S10b), validasi `edited` (S7)."""

import unicodedata

import pytest

from backend.proposal.span import validate_span

from .proposal_fakes import DX_TEXT, EXPECT, LIT, PAR, STORED_LIT, Env, run_responder, valid_edit

DX = DX_TEXT
DY = "aaa"
DZ = "café"
NL = "\n"


# ---------------------------------------------------------------- S26
@pytest.mark.parametrize("name,doc,teks,s,e,exp", [
    ("V1", DX, "(2) Ggg hhh iii.\n", 69, 87, (False, False, None)),
    ("V2", DX, "(2) Ggg hhh iii.\n", 69, 86, (True, True, {"start": 69, "end": 86})),
    ("V3", DX, "i.\n", -3, 86, (False, False, None)),
    ("V4", DX, "(1) Aaa bbb ccc.", 52, 68, (True, True, {"start": 52, "end": 68})),
    ("V5", DX, "(1) Aaa bbb ccc.", 10, 26, (True, True, {"start": 10, "end": 26})),
    ("V6", DX, "(1) Aaa bbb ccc. (2) Ddd eee fff.", None, None, (False, False, None)),
    ("V7", DX, "(1) Aaa bbb ccc.\r\n(2) Ddd eee fff.", None, None, (False, False, None)),
    ("V8", DX, "(2) Ddd eee fff. ", None, None, (False, False, None)),
    ("V9", DX, "(1) Aaa bbb ccc.\n(2) Ddd eee fff.", 10, 43, (True, True, {"start": 10, "end": 43})),
    ("V10", DY, "aa", None, None, (False, False, None)),
    ("V11", DZ, "café", None, None, (False, False, None)),
    ("V12", DZ, "café", None, None, (True, True, {"start": 0, "end": 4})),
])
def test_s26_span_function(name, doc, teks, s, e, exp):
    assert len(DX) == 86 and len(DZ) == 4 and unicodedata.is_normalized("NFC", DZ)
    assert tuple(validate_span(doc, teks, s, e)) == exp, name


def test_s26_utf16_length_would_pass_v1():
    """Panjang UTF-16 DX = 87 sehingga end=87 lolos kalau salah hitung; code point = 86."""
    assert len(DX.encode("utf-16-le")) // 2 == 87 and len(DX) == 86
    assert validate_span(DX, DX[69:87], 69, 87).offset_found is False


# ---------------------------------------------------------------- S10
def test_s10_w4_validation_table(tmp_path):
    env = Env(tmp_path)
    d = env.gen_ok()
    props = d["proposals"]
    assert len(props) == 13
    names = STORED_LIT + ["PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PA8"]
    assert [p["body"]["query"] for p in props] == [{**LIT, **PAR}[n]["query"] for n in names]  # urutan keluaran dipertahankan
    for n, p in zip(names, props):
        of, tm, rs = EXPECT[n]
        assert p["validation"] == {"offset_found": of, "text_matches": tm}, n
        assert p["resolved_span"] == rs, n
        assert p["review_status"] == "usulan" and p["edited"] is None and p["item_id"] is None and p["reviewed_at"] is None
        assert p["family"] == "uupt" and p["operator_note"] is None
    assert not any(p["body"]["query"] in ("QL6", "QL7") for p in props)  # L6 (doc salah) dan L7 (mode salah) dibuang
    approvable = [p["body"]["query"] for p in props if p["validation"]["text_matches"]]
    assert approvable == ["QL1", "QP1", "QP5", "Ddd eee fff?"] and len(props) - len(approvable) == 9
    pa6 = next(p for p in props if p["body"]["query"] == "Ddd eee fff?")
    assert pa6["body"]["mode"] == "parafrase"  # A10: mode disimpan apa adanya
    assert env.items_on_disk() and len(env.items_on_disk()) == 2  # W4 tidak membuat Item


def test_s10b_w4_enforces_upper_bound(tmp_path):
    l8 = {"query": "QL8", "mode": "literal", "doc_id": "doc-x", "teks_gold": "(2) Ggg hhh iii.\n", "start": 69, "end": 87}
    env = Env(tmp_path, default=run_responder(lit=[l8]))
    d = env.gen_ok(("literal",))
    assert len(d["proposals"]) == 1
    p = d["proposals"][0]
    assert p["validation"] == {"offset_found": False, "text_matches": False} and p["resolved_span"] is None
    r = env.decide(p["proposal_id"], {"decision": "disetujui", "edited": None, "operator_note": None})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"


# ---------------------------------------------------------------- S7
def _fresh(tmp_path):
    env = Env(tmp_path)
    ids = env.by_key(env.gen_ok(("literal",)))
    return env, ids["L1"]


def _body(spans, **over):
    e = {"query": "QE", "gold_spans": spans, "mode": "literal"}
    e.update(over)
    return {"decision": "diubah", "edited": e, "operator_note": None}


def sp(s, e):
    return {"start": s, "end": e}


S7_422 = [
    ("e2", _body([])),
    ("e3", _body([sp(10, 10)])),
    ("e4", _body([sp(43, 10)])),
    ("e5", _body([sp(-1, 5)])),
    ("e6", _body([sp(85, 87)])),
    ("e7", _body([sp(10, 87)])),
    ("e11a", _body([sp(10, 26)], query="")),
    ("e11b", _body([sp(10, 26)], query="   ")),
    ("e12", _body([sp(10, 26)], mode="campur")),
    ("e13a", _body([{"start": "10", "end": 26}])),
    ("e13b", _body([{"start": 10.5, "end": 26}])),
    ("e13c", _body([{"start": 10.0, "end": 26}])),
    ("e14a", _body([{"start": True, "end": 26}])),
    ("e14b", _body([{"start": None, "end": 26}])),
    ("e14c", _body([{"start": 10}])),
    ("e14d", _body([{"start": 10, "end": 26, "x": 1}])),
    ("e14e", _body([[10, 26]])),
    ("e14f", _body({"start": 10, "end": 26})),
    ("e14g", _body("10-26")),
    ("e14h", _body([sp(10, 26)], query=123)),
    ("e14i", _body([sp(10, 26)], query=None)),
    ("e14j", _body([sp(10, 26)], mode=None)),
    ("e1", {"decision": "diubah", "edited": None, "operator_note": None}),
]


@pytest.mark.parametrize("name,body", S7_422, ids=[n for n, _ in S7_422])
def test_s7_invalid_edited_is_422_and_changes_nothing(tmp_path, name, body):
    env, pid = _fresh(tmp_path)
    before = env.record_bytes(pid)
    files = env.butir_snapshot()
    r = env.decide(pid, body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed", (name, r.text)
    assert env.record_bytes(pid) == before and env.butir_snapshot() == files and not env.spark_items()


@pytest.mark.parametrize("name,spans,query", [
    ("e8", [(0, 1)], "QE"),
    ("e9", [(10, 26), (27, 43)], "QE"),
    ("e10", [(85, 86)], "QE"),
    ("e15", [(10, 26)], "  QE  "),
])
def test_s7_valid_edited_is_200_with_one_item(tmp_path, name, spans, query):
    env, pid = _fresh(tmp_path)
    r = env.decide(pid, {"decision": "diubah", "edited": valid_edit(query, spans), "operator_note": None})
    assert r.status_code == 200, (name, r.text)
    items = env.spark_items()
    assert len(items) == 1 and items[0]["gold_spans"] == [sp(s, e) for s, e in spans] and items[0]["query"] == query
