"""M2.1 tambahan Tier 1: mode D `unanswerable` (H-087, H-092), SU1-SU18 dan SU20-SU22 (scenarios/M2.1-unanswerable.md, revisi 3).

Data sintetis ("PT Maju Bersama"), klien Spark palsu, ranker/encoder suntikan, direktori sementara. Tanpa jaringan, tanpa Model API,
tanpa GPU; tidak menulis `data/` atau `runs/` repo. Angka = angka skenario."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import shutil
import socket
import threading
from fractions import Fraction
from pathlib import Path

import pytest

from backend import config
from backend.api.app import Service
from backend.config import REPO_ROOT
from backend.metrics.aggregate import aggregate, mean_recall_at_k
from backend.metrics.types import ItemMetrics
from backend.pipeline.grid_run import GridRunError, load_items
from backend.proposal import prompt as pm
from backend.proposal.absence import (AbsenceChecker, AbsenceConfig, DenseUnavailable, load_absence_config, normalize_query,
                                      production_checker)
from backend.proposal.gate import GateConfig, evaluate_gate, load_gate_config, upper_bound
from backend.proposal.report import (filter_items, items_summary, mode_report, must_abstain_summary, origin_report)
from backend.proposal.service import DocInfo, Hooks
from backend.retrieval.bm25 import Bm25Retriever
from backend.spark import ConfigInvalid, Ledger
from backend.spark.store import canonical_json, sha256_hex

from .proposal_fakes import Env
from .spark_fakes import Resp, body_ok
from .test_proposal_decide import approve, err, reject
from .test_verifier_summary import A11, G1, T11, ans, cell

# ----------------------------------------------------------------------------- fixture AKT
LINES = [
    "AKTA PENDIRIAN PT MAJU BERSAMA",
    "Pasal 1 Nama dan kedudukan: Perseroan bernama PT Maju Bersama dan berkedudukan di Kota Contoh.",
    "Pasal 2 Modal dasar Perseroan adalah Rp 1.000.000 (satu juta rupiah).",
    "Pasal 3 Direktur Perseroan adalah Tuan Budi Santoso.",
    "Pasal 4 Perseroan akan mengurus NPWP setelah pengesahan.",
    "Pasal 5 Jangka waktu Perseroan tidak terbatas.",
]
AKT = "\n".join(LINES)
UNITS = [(f"L{i}", t) for i, t in enumerate(LINES)]
STOP = {"apa", "siapa", "berapa", "yang", "dan", "di", "adalah", "dari", "dalam", "itu", "akan", "setelah", "tidak"}
DOC = "akta-x"


def fx_tok(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if w not in STOP]


def overlap_ranker(q: str) -> list[tuple[str, float]]:
    """Ranker BM25 suntikan SU5: semua unit berbagi token, urut jumlah token sama menurun, seri `unit_id`."""
    qs = set(fx_tok(q))
    hits = [(uid, float(len(qs & set(fx_tok(t))))) for uid, t in UNITS if qs & set(fx_tok(t))]
    return sorted(hits, key=lambda x: (-x[1], x[0]))


def acfg(**over) -> AbsenceConfig:
    base = dict(check_top_k=3, lexical_coverage_threshold=Fraction(1, 2), generic_df_ratio=Fraction(1, 2),
                dense_cosine_threshold=0.80, device="cpu", max_per_call=3, projection_expected_output_tokens=2000)
    base.update(over)
    return AbsenceConfig(**base)


def fx_checker(*, cfg: AbsenceConfig | None = None, bm25=overlap_ranker, dense=None, dense_off=True) -> AbsenceChecker:
    return AbsenceChecker(UNITS, fx_tok, bm25, dense, cfg or acfg(), dense_off=dense_off)


U = {
    "U1": ("Berapa nomor NIK Tuan Budi Santoso?", "data_tidak_dimuat", "NIK tidak dimuat"),
    "U2": ("Apa nomor NPWP Perseroan?", "data_tidak_dimuat", "Nomor NPWP tidak disebut"),
    "U3": ("Siapa komisaris Perseroan?", "rincian_tidak_diatur", "Komisaris tidak diatur"),
    "U4": ("Apa nomor rekening bank Perseroan?", "data_tidak_dimuat", "Rekening tidak dimuat"),
    "U5": ("Apa itu Perseroan?", "di_luar_akta", "Terlalu umum"),
    "U6": ("Berapa gaji bulanan Direktur?", "rincian_tidak_diatur", "Gaji tidak diatur"),
}


def cand(k: str, doc: str = DOC) -> dict:
    q, kode, teks = U[k]
    return {"query": q, "doc_id": doc, "alasan_kode": kode, "alasan_teks": teks}


LIT_GOLD = "Pasal 3 Direktur Perseroan adalah Tuan Budi Santoso."
LIT_START = AKT.index(LIT_GOLD)
LIT = {"query": "Siapa direktur?", "mode": "literal", "doc_id": DOC, "teks_gold": LIT_GOLD, "start": None, "end": None}


def responder(u_out, lit_out=None):
    def respond(_tr, request):
        text = json.loads(request.content.decode("utf-8"))["input"]
        if "\nMODE: unanswerable\n" in text:
            return Resp(200, body_ok({"usulan": u_out}))
        return Resp(200, body_ok({"usulan": lit_out if lit_out is not None else []}))
    return respond


def mk(tmp, sub="e", u_out=None, checker=None, *, max_per_call=None, lit_out=None, **kw) -> Env:
    out = u_out if u_out is not None else [cand("U1"), cand("U2"), cand("U3")]
    kw.setdefault("default", responder(out, lit_out))
    env = Env(tmp / sub, with_v1=False, doc_id=DOC, doc_text=AKT, sha="ha1", **kw)
    env.docs[DOC] = DocInfo(DOC, "akta", AKT, "ha1")
    env.ps.checker_provider = lambda doc, c=checker: c or fx_checker()
    if max_per_call is not None:
        env.ps.max_per_call = max_per_call
    return env


def gen(env, modes=("unanswerable",), family="akta", doc_id=DOC):
    return env.http.post(f"/api/families/{family}/proposals/generate", json={"doc_id": doc_id, "modes": list(modes)})


def gen_ok(env, modes=("unanswerable",)):
    r = gen(env, modes)
    assert r.status_code == 200, r.text
    return r.json()


def by_q(resp) -> dict[str, str]:
    inv = {v[0]: k for k, v in U.items()}
    return {inv[p["body"]["query"]]: p["proposal_id"] for p in resp["proposals"] if p["body"]["query"] in inv}


def write_items(env, name, rows):
    (env.butir / name).write_bytes(b"".join(json.dumps(r, sort_keys=True, ensure_ascii=False).encode() + b"\n" for r in rows))


def op_item(i, mode="literal", gold=((0, 5),)):
    return {"id": f"OP{i}", "family": "akta", "query": f"op{i}", "doc_id": DOC, "gold_spans": [{"start": s, "end": e} for s, e in gold],
            "clean_sha256": "ha1", "mode": mode, "origin": "operator", "review_status": None, "proposal_id": None,
            "reference_date": None, "scene_checked": False, "operator_note": None, "created_at": "2026-10-27T03:18:10Z"}


# ============================================================================= SU1
@pytest.mark.parametrize("name,out,status,n", [
    ("a", [cand("U1"), cand("U2"), cand("U3")], 200, 3),
    ("b", [{**cand("U1"), "teks_gold": "x"}], 502, 0),
    ("c", [{k: v for k, v in cand("U1").items() if k != "alasan_kode"}], 502, 0),
    ("d", [{**cand("U1"), "alasan_kode": "lain"}], 502, 0),
    ("e", [{**cand("U1"), "alasan_teks": ""}, cand("U2")], 200, 1),
    ("f", [{**cand("U1"), "start": 1, "end": 2}], 502, 0),
    ("g", [{**cand("U1"), "query": "  "}], 200, 0),
    ("h", [], 200, 0),
])
def test_su1_proposalu_strict_no_gold(tmp_path, name, out, status, n):
    env = mk(tmp_path, name, out)
    r = gen(env)
    assert r.status_code == status, r.text
    if status == 502:
        assert r.json()["error"]["code"] == "model_error" and "Traceback" not in r.text
        assert env.ps.list_proposals() == [] and not list(env.ps.index_dir.glob("*.json"))  # tidak di-cache sebagai sah
        assert Ledger(env.runs).spent(role="d") > 0  # RunRecord galat ada, biaya tercatat (M0.1)
        assert gen(env).status_code == 502 and env.tr.calls == 2  # W4 ulang memanggil klien lagi
    else:
        assert len(r.json()["proposals"]) == n and r.json()["runs"][0]["status"] == "ok"
        assert all(p["body"].keys() == {"query", "mode", "doc_id", "alasan_kode", "alasan_teks"} for p in r.json()["proposals"])


def test_su1_schema_is_strict_with_no_span_fields():
    props = pm.PROPOSAL_U_SCHEMA["properties"]["usulan"]["items"]
    assert props["additionalProperties"] is False and props["required"] == ["query", "doc_id", "alasan_kode", "alasan_teks"]
    assert set(props["properties"]) == {"query", "doc_id", "alasan_kode", "alasan_teks"}
    assert props["properties"]["alasan_kode"]["enum"] == ["data_tidak_dimuat", "di_luar_akta", "rincian_tidak_diatur"]
    pm.validate_schema("unanswerable")


# ============================================================================= SU2
OLD_PROPOSALD_HASH = "047ffa2ee99f6be6daf77c72407d5efeb1c10eb337afa2c2b3a801716c5e3af8"  # dikunci literal (keluaran sebelum revisi)


def ref_key(prompt_hash, schema_hash, mode, cap, sha="ha1"):
    return sha256_hex(canonical_json(["d", "meta", "muse-spark-1.3-contributor", "low", prompt_hash, schema_hash, sha, DOC, mode, cap]))


def test_su2_cache_keys_and_prompt_per_mode(tmp_path):
    assert pm.schema_hash() == OLD_PROPOSALD_HASH and pm.schema_hash("literal") == OLD_PROPOSALD_HASH
    v1, v2 = pm.load_prompt(), pm.load_prompt(mode="unanswerable")
    assert (v1.version, v2.version) == ("v1", "v2") and pm.load_prompt(mode="literal").version == "v1"
    assert pm.load_prompt().prompt_hash == hashlib.sha256((REPO_ROOT / "prompts/d/v1.md").read_bytes()).hexdigest()
    env = mk(tmp_path, lit_out=[LIT])
    first = gen_ok(env, ("literal", "parafrase", "unanswerable"))
    want = {ref_key(v1.prompt_hash, OLD_PROPOSALD_HASH, "literal", 20), ref_key(v1.prompt_hash, OLD_PROPOSALD_HASH, "parafrase", 20),
            ref_key(v2.prompt_hash, pm.schema_hash("unanswerable"), "unanswerable", 3)}
    assert len(want) == 3 and {p.stem for p in env.ps.index_dir.glob("*.json")} == want
    assert env.tr.calls == 3
    # konfigurasi pemeriksaan tidak ikut kunci: ubah K dan ambang, W4 kedua = cache, tanpa panggilan
    env.ps.absence_cfg = dataclasses.replace(env.ps.absence_cfg, check_top_k=5, lexical_coverage_threshold=Fraction(3, 4))
    env.ps.checker_provider = lambda d: fx_checker(cfg=acfg(check_top_k=5))
    again = gen_ok(env, ("unanswerable",))
    assert env.tr.calls == 3 and again["runs"][0]["status"] == "cached"
    assert [p["proposal_id"] for p in again["proposals"]] == [p["proposal_id"] for p in first["proposals"] if p["body"]["mode"] == "unanswerable"]
    # keputusan tidak ter-reset
    pid = again["proposals"][0]["proposal_id"]
    assert env.decide(pid, approve()).status_code == 200
    assert gen_ok(env)["proposals"][0]["review_status"] == "disetujui" and env.tr.calls == 3
    # clean_sha256 atau max_per_call berubah -> kunci berubah
    env.ps.max_per_call = 2
    gen_ok(env)
    assert env.tr.calls == 4 and ref_key(v2.prompt_hash, pm.schema_hash("unanswerable"), "unanswerable", 2) in {p.stem for p in env.ps.index_dir.glob("*.json")}
    env.docs[DOC] = DocInfo(DOC, "akta", AKT, "ha2")
    gen_ok(env)
    assert env.tr.calls == 5 and ref_key(v2.prompt_hash, pm.schema_hash("unanswerable"), "unanswerable", 2, "ha2") in {
        p.stem for p in env.ps.index_dir.glob("*.json")}


def test_su2_existing_cache_keys_of_repo_records_still_found():
    """82 rekaman lama (mode literal/parafrase): `versions.json` current tetap v1, jadi kunci lama tidak batal."""
    meta = json.loads((REPO_ROOT / "prompts/d/versions.json").read_text(encoding="utf-8"))
    assert meta["current"] == "v1" and meta["by_mode"] == {"unanswerable": "v2"}
    assert pm.load_prompt().version == "v1"


# ============================================================================= SU3
def test_su3_modes_and_family(tmp_path):
    env = mk(tmp_path, "a", lit_out=[LIT])
    d = gen_ok(env, ("literal", "unanswerable"))
    assert env.tr.calls == 2 and len(d["runs"]) == 2
    assert [p["body"]["mode"] for p in d["proposals"]] == ["literal", "unanswerable", "unanswerable", "unanswerable"]
    env = mk(tmp_path, "b")
    gen_ok(env, ("unanswerable", "unanswerable"))
    assert env.tr.calls == 1
    # (c) dibalik H-099 (scenarios/M2.1-unanswerable-uupt SV1 (c)): uupt + unanswerable sah; doc akta di bawah uupt = 404
    for sub, modes, fam, status, code in (("c", ["unanswerable"], "uupt", 404, "not_found"),
                                          ("d", ["unanswerable", "campur"], "akta", 400, "invalid_request"),
                                          ("e", ["tolak"], "akta", 400, "invalid_request")):
        env = mk(tmp_path, sub)
        r = env.http.post(f"/api/families/{fam}/proposals/generate", json={"doc_id": DOC, "modes": modes})
        assert r.status_code == status and r.json()["error"]["code"] == code
        assert env.tr.calls == 0 and list(env.ps.index_dir.glob("*.json")) == []


# ============================================================================= SU4
def test_su4_cap_after_discard(tmp_path):
    raw = [cand("U1"), cand("U1", "akta-y"), cand("U2"), cand("U3"), cand("U4"), cand("U5")]
    d = gen_ok(mk(tmp_path, "a", raw))
    assert [p["body"]["query"] for p in d["proposals"]] == [U["U1"][0], U["U2"][0], U["U3"][0]]
    assert len(gen_ok(mk(tmp_path, "b", [cand("U1")]))["proposals"]) == 1
    assert gen_ok(mk(tmp_path, "c", []))["proposals"] == []


# ============================================================================= SU5
def test_su5_hand_computed_table(tmp_path):
    env = mk(tmp_path, u_out=[cand(k) for k in U], max_per_call=6)
    d = gen_ok(env)
    ids = by_q(d)
    assert len(d["proposals"]) == 6
    want = {"U1": ("doubtful", ["lexical_overlap"], (3, 5)), "U2": ("doubtful", ["lexical_overlap"], (1, 2)),
            "U3": ("ok", [], (0, 1)), "U4": ("ok", [], (0, 3)), "U5": ("doubtful", ["no_distinctive_terms"], (0, 0)),
            "U6": ("ok", [], (1, 3))}
    hashes = set()
    for k, (st, rs, (num, den)) in want.items():
        rec = env.ps.get(ids[k])
        a = rec["absence_check"]
        assert (a["status"], a["reasons"], a["max_cov"], a["max_cosine"]) == (st, rs, {"num": num, "den": den}, None), k
        assert rec["validation"] is None and rec["resolved_span"] is None and rec["review_status"] == "usulan"
        assert rec["body"]["mode"] == "unanswerable"
        hashes.add(a["config_hash"])
    assert len(hashes) == 1 and hashes.pop()


def test_su5_generic_tokens_and_df():
    ck = fx_checker()
    assert ck.generic == {"pasal", "perseroan"}  # df 5/6 > 0,5; pt/maju/bersama df 2 tidak generik


def test_su5_threshold_is_exact_fraction_and_inclusive():
    assert fx_checker().check(U["U2"][0])["reasons"] == ["lexical_overlap"]  # 1/2 = ambang
    strict = fx_checker(cfg=acfg(lexical_coverage_threshold=Fraction("0.51")))
    assert strict.check(U["U2"][0])["status"] == "ok"
    assert load_absence_config(cfg={"unanswerable": {**config.load("proposals")["unanswerable"],
                                                     "lexical_coverage_threshold": 0.5}}).lexical_coverage_threshold == Fraction(1, 2)


# ============================================================================= SU6
def test_su6_k_matters():
    order = lambda q: [(f"L{i}", 1.0) for i in (2, 0, 3, 4, 1, 5)]  # noqa: E731
    a = fx_checker(cfg=acfg(check_top_k=1), bm25=order).check(U["U1"][0])
    assert a["status"] == "ok" and a["max_cov"] == {"num": 0, "den": 5}
    assert a["top_k"] == [{"source": "bm25", "rank": 1, "unit_text": LINES[2]}]
    b = fx_checker(cfg=acfg(check_top_k=3), bm25=order).check(U["U1"][0])
    assert b["status"] == "doubtful" and b["max_cov"] == {"num": 3, "den": 5}
    assert [(t["source"], t["rank"], t["unit_text"]) for t in b["top_k"]] == [("bm25", 1, LINES[2]), ("bm25", 2, LINES[0]), ("bm25", 3, LINES[3])]


@pytest.mark.parametrize("bad", [0, -1, 3.5, True, "3"])
def test_su6_invalid_k_is_config_invalid_at_load(bad, tmp_path):
    raw = config.load("proposals")
    with pytest.raises(ConfigInvalid):
        load_absence_config(cfg={**raw, "unanswerable": {**raw["unanswerable"], "check_top_k": bad}})
    cdir = tmp_path / "cfg"
    cdir.mkdir()
    text = (REPO_ROOT / "config/proposals.toml").read_text(encoding="utf-8").replace("check_top_k = 3", f"check_top_k = {json.dumps(bad)}")
    (cdir / "proposals.toml").write_text(text, encoding="utf-8", newline="\n")
    with pytest.raises(ConfigInvalid):
        load_absence_config(cdir)
    assert ConfigInvalid.code == "config_invalid"


def test_su6_repo_config_values_are_the_scenario_values():
    c = load_absence_config()
    assert (c.check_top_k, c.lexical_coverage_threshold, c.generic_df_ratio, c.dense_cosine_threshold, c.max_per_call) == (
        3, Fraction(1, 2), Fraction(1, 2), 0.80, 3)


# ============================================================================= SU7
def dense_of(*scores):
    ids = ["L3", "L5", "L1"]
    return lambda q: list(zip(ids, scores))


@pytest.mark.parametrize("scores,status,reasons,cos", [
    ((0.82, 0.40, 0.10), "doubtful", ["dense_similar"], 0.82),
    ((0.79, 0.40, 0.10), "ok", [], 0.79),
    ((0.80, 0.40, 0.10), "doubtful", ["dense_similar"], 0.80),
])
def test_su7_dense_threshold_inclusive(scores, status, reasons, cos):
    a = fx_checker(dense_off=False, dense=dense_of(*scores)).check(U["U3"][0])
    assert (a["status"], a["reasons"], a["max_cosine"]) == (status, reasons, cos)
    assert [t["source"] for t in a["top_k"]].count("dense") == 3


def test_su7_reason_order_and_sources():
    a = fx_checker(dense_off=False, dense=dense_of(0.82, 0.4, 0.1)).check(U["U1"][0])
    assert a["reasons"] == ["lexical_overlap", "dense_similar"]
    assert [t["source"] for t in a["top_k"]] == ["bm25", "dense", "dense", "dense"]  # P15: BM25 lalu dense, tanpa dedup


def test_su7_dense_unavailable_not_silent_ok_and_w4_still_200(tmp_path):
    def boom(q):
        raise DenseUnavailable("no encoder")
    for dense in (boom, None):
        env = mk(tmp_path, f"d{dense is None}", checker=fx_checker(dense_off=False, dense=dense), u_out=[cand("U3")])
        d = gen_ok(env)
        a = d["proposals"][0]["absence_check"]
        assert (a["status"], a["reasons"], a["max_cosine"]) == ("doubtful", ["dense_unavailable"], None) and env.tr.calls == 1
    # dense sengaja dimatikan (config) = tanpa alasan
    assert fx_checker().check(U["U3"][0])["reasons"] == []


# ============================================================================= SU8
@pytest.fixture(scope="module")
def prod():
    r = config.load("retrieval")
    b = r["bm25"]
    ck = production_checker(UNITS, acfg(), r, dense_off=True)
    bm = Bm25Retriever(UNITS, k1=b["k1"], b=b["b"], stemming=b["stemming"], stopwords=b["stopwords"])
    return ck, bm


Q = {**{k: v[0] for k, v in U.items()}, "Q1": "Di mana domisili kedudukan Perseroan?", "Q2": "Siapa pengurus Perseroan?",
     "U7": "Siapa pemilik Perseroan?"}
SU8 = {  # (T*, top_k [(unit, skor)], max_cov, status)
    "U1": (["berapa", "budi", "nik", "nomor", "santoso", "tuan"], [("L3", 4.13)], (3, 6), "doubtful"),
    "U2": (["apa", "nomor", "npwp"], [("L4", 1.763), ("L5", 0.299), ("L3", 0.282)], (1, 3), "ok"),
    "U3": (["komisaris", "siapa"], [("L4", 0.299), ("L5", 0.299), ("L3", 0.282)], (0, 2), "ok"),
    "U4": (["apa", "bank", "nomor", "rekening"], [("L4", 0.299), ("L5", 0.299), ("L3", 0.282)], (0, 4), "ok"),
    "U5": (["apa"], [("L4", 0.299), ("L5", 0.299), ("L3", 0.282)], (0, 1), "ok"),
    "U6": (["berapa", "bulan", "direktur", "gaji"], [("L3", 1.377)], (1, 4), "ok"),
    "Q1": (["domisili", "duduk", "mana"], [("L1", 1.278), ("L4", 0.299), ("L5", 0.299)], (1, 3), "ok"),
    "Q2": (["siapa", "urus"], [("L4", 1.763), ("L5", 0.299), ("L3", 0.282)], (1, 2), "doubtful"),
}


@pytest.mark.parametrize("k", list(SU8))
def test_su8_production_tokenizer_and_bm25(prod, k):
    ck, bm = prod
    tstar, top, (num, den), status = SU8[k]
    assert sorted(set(ck.tokenize(Q[k])) - ck.generic) == tstar
    ranked = bm.rank(Q[k], 3)
    assert [(u, round(s, 3 if s < 3 else 2)) for u, s in ranked] == top
    a = ck.check(Q[k])
    assert a["max_cov"] == {"num": num, "den": den} and a["status"] == status
    assert a["reasons"] == (["lexical_overlap"] if status == "doubtful" else [])  # U5: tanpa no_distinctive_terms di produksi
    assert [t["unit_text"] for t in a["top_k"]] == [LINES[int(u[1])] for u, _ in top]


def test_su8_stems_and_generic(prod):
    ck, _ = prod
    assert ck.generic == {"persero", "pasal"}
    t = ck.tokenize
    assert t("kedudukan") == ["duduk"] and t("berkedudukan") == ["keduduk"] and t("mengurus") == t("pengurus") == ["urus"]
    assert t("Perseroan") == ["persero"] and t("pengesahan") == ["kesah"] and t("bulanan") == ["bulan"]


def test_su8_checker_uses_the_same_tokenizer_as_bm25(prod):
    ck, bm = prod
    from backend.retrieval import bm25 as bmod
    assert ck.tokenize("Mengurus NPWP") == bmod.tokenize("Mengurus NPWP", stemming=True, stopwords=True)
    assert bm._stemming and bm._stopwords


# ============================================================================= SU9
def test_su9_local_deterministic_no_network(tmp_path, monkeypatch):
    env = mk(tmp_path, u_out=[cand("U1"), cand("U2"), cand("U6")])
    d = gen_ok(env)
    assert env.tr.calls == 1
    real = socket.socket.connect

    def guarded(self, addr, *a, **k):  # loopback (event loop internal) boleh; selain itu = jaringan
        if not (isinstance(addr, tuple) and addr[0] in ("127.0.0.1", "::1")):
            raise AssertionError("network used")
        return real(self, addr, *a, **k)
    monkeypatch.setattr(socket.socket, "connect", guarded)
    pid = d["proposals"][0]["proposal_id"]
    r1, r2 = env.ps.recheck(pid), env.ps.recheck(pid)
    assert canonical_json(r1) == canonical_json(r2) == canonical_json(d["proposals"][0]["absence_check"]) and env.tr.calls == 1
    before = env.record_bytes(pid)
    # config berubah: cache hit tidak menulis ulang catatan; config_hash lama tetap; tanda "settings changed" dapat dihitung
    env.ps.absence_cfg = dataclasses.replace(env.ps.absence_cfg, check_top_k=5)
    env.ps.checker_provider = lambda doc: fx_checker(cfg=acfg(check_top_k=5))
    again = gen_ok(env)
    assert env.record_bytes(pid) == before and env.tr.calls == 1
    old = again["proposals"][0]["absence_check"]["config_hash"]
    assert old == d["proposals"][0]["absence_check"]["config_hash"] != env.ps.check_config_hash()
    assert env.http.get("/api/families/akta/proposals").json()["check_config_hash"] == env.ps.check_config_hash()


# ============================================================================= SU10
def test_su10_approve_makes_tolak_item(tmp_path):
    env = mk(tmp_path, u_out=[cand("U2"), cand("U3")])
    ids = by_q(gen_ok(env))
    for k in ("U2", "U3"):
        before = env.ps.get(ids[k])
        r = env.decide(ids[k], {"decision": "disetujui", "edited": None, "operator_note": "n1"})
        assert r.status_code == 200, r.text
        item = r.json()["item"]
        assert item == {"id": f"usulan-{ids[k]}", "family": "akta", "query": U[k][0], "doc_id": DOC, "gold_spans": [],
                        "clean_sha256": "ha1", "mode": "tolak", "origin": "spark_disetujui", "review_status": "disetujui",
                        "proposal_id": ids[k], "reference_date": None, "scene_checked": False, "operator_note": "n1",
                        "created_at": "2026-10-29T10:00:00Z"}
        rec = env.ps.get(ids[k])
        assert rec["item_id"] == item["id"] and rec["body"] == before["body"] and rec["absence_check"] == before["absence_check"]
    assert env.ps.get(ids["U2"])["absence_check"]["status"] == "doubtful"  # doubtful tidak diblokir (P3)
    files = sorted(p.name for p in env.butir.glob("akta.v*.jsonl"))
    assert files == ["akta.v2.jsonl", "akta.v3.jsonl"]
    items = Service(runs_dir=env.runs, butir_dir=env.butir).items("akta")
    assert len(items) == 2 and {i["mode"] for i in items} == {"tolak"}


# ============================================================================= SU10b
def _row(**over):
    base = op_item(1, "tolak", ())
    base.update(over)
    return base


def test_su10b_item_validator_and_loader(tmp_path):
    def load(rows, family="akta"):
        d = tmp_path / f"d{len(list(tmp_path.iterdir()))}"
        d.mkdir()
        (d / f"{family}.v1.jsonl").write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in rows))
        return load_items(family, d)[0]
    assert len(load([_row()])) == 1  # (a)
    with pytest.raises(GridRunError):  # (b) tolak ber-gold
        load([op_item(2), _row(gold_spans=[{"start": 0, "end": 5}], id="X")])
    assert len(load([_row(mode="parafrase")])) == 1  # (c) gold kosong + parafrase sah
    k08 = next(ln for ln in (REPO_ROOT / "data/butir/uupt.v1.jsonl").read_text(encoding="utf-8").split("\n") if '"kontrol-K-08"' in ln)
    d = tmp_path / "k08"
    d.mkdir()
    (d / "uupt.v1.jsonl").write_bytes((k08 + "\n").encode("utf-8"))
    row = json.loads(k08)
    assert row["mode"] == "parafrase" and row["gold_spans"] == [] and len(load_items("uupt", d)[0]) == 1
    with pytest.raises(GridRunError):  # (d) nama body.mode bukan enum Item.mode
        load([_row(mode="unanswerable")])
    assert len(load([_row(family="uupt")], "uupt")) == 1  # (e) dibalik H-099 V4: uupt + tolak sah


# ============================================================================= SU11
def test_su11_reject_and_transitions(tmp_path):
    env = mk(tmp_path)
    ids = by_q(gen_ok(env))
    r = env.decide(ids["U1"], {"decision": "ditolak", "edited": None, "operator_note": "x"})
    assert r.status_code == 200 and r.json()["item"] is None and r.json()["proposal"]["item_id"] is None
    assert env.ps.items("akta") == []
    assert env.decide(ids["U3"], approve()).status_code == 200
    snap = env.record_bytes(ids["U3"])
    for body in (approve(), reject(), {"decision": "diubah", "edited": {"query": "q", "gold_spans": [], "mode": "tolak"}, "operator_note": None}):
        err(env.decide(ids["U3"], body), 409, "invalid_transition")
    assert env.record_bytes(ids["U3"]) == snap
    err(env.decide("0" * 16, approve()), 404, "not_found")
    for dec in ("unanswerable", "usulan"):
        err(env.decide(ids["U2"], {"decision": dec, "edited": None, "operator_note": None}), 400, "invalid_request")


# ============================================================================= SU12
def edit(q="Siapa pemegang saham?", gold=(), mode="tolak"):
    e = {"query": q, "gold_spans": list(gold)}
    if mode is not None:
        e["mode"] = mode
    return {"decision": "diubah", "edited": e, "operator_note": None}


def fresh_u3(tmp, name, **kw):
    env = mk(tmp, name, [cand("U3")], **kw)
    d = gen_ok(env)
    return env, d["proposals"][0]["proposal_id"]


def test_su12_edit_recomputes_absence(tmp_path):
    env, pid = fresh_u3(tmp_path, "e1")
    old_body = env.ps.get(pid)["body"]
    r = env.decide(pid, edit())
    assert r.status_code == 200, r.text
    it = r.json()["item"]
    assert (it["gold_spans"], it["mode"], it["query"], it["review_status"]) == ([], "tolak", "Siapa pemegang saham?", "diubah")
    rec = env.ps.get(pid)
    assert rec["body"] == old_body and rec["edited"]["query"] == "Siapa pemegang saham?"
    assert (rec["absence_check"]["max_cov"], rec["absence_check"]["status"]) == ({"num": 0, "den": 2}, "ok")
    env, pid = fresh_u3(tmp_path, "e5")
    r = env.decide(pid, edit("Siapa Direktur Perseroan?"))
    a = env.ps.get(pid)["absence_check"]
    assert r.status_code == 200 and a["max_cov"] == {"num": 1, "den": 1} and a["status"] == "doubtful"


@pytest.mark.parametrize("name,body", [
    ("e2", edit(gold=[{"start": 10, "end": 26}])),
    ("e3", edit("")),
    ("e4a", {"decision": "diubah", "edited": {"query": "q", "mode": "tolak"}, "operator_note": None}),
    ("e4b", {"decision": "diubah", "edited": {"query": "q", "gold_spans": None, "mode": "tolak"}, "operator_note": None}),
    ("e6", {"decision": "disetujui", "edited": edit()["edited"], "operator_note": None}),
    ("e7", edit(mode="parafrase")),
    ("e8", edit(mode=None)),
    ("e9", edit(mode="unanswerable")),
])
def test_su12_invalid_edits_422(tmp_path, name, body):
    env, pid = fresh_u3(tmp_path, name)
    snap = env.record_bytes(pid)
    err(env.decide(pid, body), 422, "validation_failed")
    assert env.record_bytes(pid) == snap and env.ps.items("akta") == []


def _gold_span():
    return {"start": LIT_START, "end": LIT_START + len(LIT_GOLD)}


@pytest.mark.parametrize("name,edited", [
    ("f", {"query": "Siapa direktur?", "gold_spans": [], "mode": "literal"}),
    ("f2", {"query": "Siapa direktur?", "gold_spans": [], "mode": "tolak"}),
    ("f3", {"query": "Siapa direktur?", "gold_spans": [_gold_span()], "mode": "tolak"}),
])
def test_su12_span_proposals_cannot_become_tolak(tmp_path, name, edited):
    env = mk(tmp_path, name, lit_out=[LIT])
    pid = gen_ok(env, ("literal",))["proposals"][0]["proposal_id"]
    snap = env.record_bytes(pid)
    err(env.decide(pid, {"decision": "diubah", "edited": edited, "operator_note": None}), 422, "validation_failed")
    assert env.record_bytes(pid) == snap and env.ps.items("akta") == []
    ok = env.decide(pid, {"decision": "diubah", "edited": {"query": "Siapa direktur?", "gold_spans": [_gold_span()], "mode": "literal"},
                          "operator_note": None})
    assert ok.status_code == 200 and ok.json()["item"]["mode"] == "literal"  # literal tetap berjalan (regresi)


# ============================================================================= SU13
def test_su13_body_cannot_inject(tmp_path):
    env, pid = fresh_u3(tmp_path, "a")
    snap = env.record_bytes(pid)
    for extra in ({"gold_spans": []}, {"origin": "operator"}, {"absence_check": {"status": "ok"}}, {"mode": "literal"}):
        err(env.decide(pid, {**approve(), **extra}), 422, "validation_failed")
        assert env.record_bytes(pid) == snap and env.ps.items("akta") == []
    r = env.decide(pid, {"decision": "ditolak"})
    assert r.status_code == 200 and r.json()["proposal"]["operator_note"] is None


# ============================================================================= SU14
def test_su14_no_path_to_evaluation_and_atomicity(tmp_path):
    env = mk(tmp_path, u_out=[cand("U1"), cand("U2"), cand("U3")])
    write_items(env, "akta.v1.jsonl", [op_item(1), op_item(2)])
    svc = lambda: Service(runs_dir=env.runs, butir_dir=env.butir)  # noqa: E731
    ids = by_q(gen_ok(env))
    assert len(svc().items("akta")) == 2 and items_summary(svc().items("akta"))["n_items"] == 2
    assert env.decide(ids["U1"], approve()).status_code == 200
    s = items_summary(svc().items("akta"))
    assert s["n_items"] == 3 and s["by_origin"] == {"operator": 2, "spark_disetujui": 1}
    shutil.rmtree(env.ps.base)
    assert len(svc().items("akta")) == 3


def _boom():
    raise RuntimeError("secret internal detail")


def test_su14_s16_failures_leave_no_orphans(tmp_path):
    hooks = Hooks()
    env = mk(tmp_path, hooks=hooks)
    ids = by_q(gen_ok(env))
    before = env.record_bytes(ids["U1"])
    for attr in ("before_item_write", "before_record_write", "before_item_commit"):
        setattr(hooks, attr, _boom)
        r = env.decide(ids["U1"], approve())
        assert r.status_code == 500 and r.json()["error"]["code"] == "storage_error" and "Traceback" not in r.text
        assert env.record_bytes(ids["U1"]) == before and env.ps.items("akta") == [] and not list(env.butir.glob("*.tmp"))
        setattr(hooks, attr, None)
    assert env.decide(ids["U1"], approve()).status_code == 200 and len(env.ps.items("akta")) == 1


def test_su14_s15_second_writer_loses(tmp_path):
    hooks = Hooks()
    env = mk(tmp_path, hooks=hooks)
    ids = by_q(gen_ok(env))
    entered, release, out = threading.Event(), threading.Event(), []
    first = {}

    def hold():
        if threading.current_thread() is first.get("t"):
            entered.set()
            assert release.wait(10)
    hooks.after_read = hold
    from backend.api.errors import ApiError

    def run(box):
        try:
            env.ps.decide(ids["U1"], approve())
            box.append(200)
        except ApiError as exc:
            box.append(exc.status)
    t = threading.Thread(target=run, args=(out,))
    first["t"] = t
    t.start()
    assert entered.wait(10)
    second = []
    run(second)
    release.set()
    t.join(10)
    assert second == [200] and out == [409] and len(env.ps.items("akta")) == 1


# ============================================================================= SU15
def test_su15_new_version_file_and_by_mode(tmp_path):
    env = mk(tmp_path, u_out=[cand("U1"), cand("U3")])
    write_items(env, "akta.v1.jsonl", [op_item(1), op_item(2)])
    write_items(env, "akta.v2.jsonl", [op_item(3)])
    h = lambda n: hashlib.sha256((env.butir / n).read_bytes()).hexdigest()  # noqa: E731
    h1, h2 = h("akta.v1.jsonl"), h("akta.v2.jsonl")
    ids = by_q(gen_ok(env))
    assert env.decide(ids["U1"], approve()).status_code == 200
    h3 = h("akta.v3.jsonl")
    lines = lambda n: (env.butir / n).read_bytes().split(b"\n")[:-1]  # noqa: E731
    assert len(lines("akta.v3.jsonl")) == 2
    assert env.decide(ids["U3"], approve()).status_code == 200
    assert len(lines("akta.v4.jsonl")) == 3
    assert (h("akta.v1.jsonl"), h("akta.v2.jsonl"), h("akta.v3.jsonl")) == (h1, h2, h3)
    for n in ("akta.v3.jsonl", "akta.v4.jsonl"):
        raw = (env.butir / n).read_bytes()
        assert b"\r" not in raw and raw.endswith(b"\n")
        for ln in raw.split(b"\n")[:-1]:
            assert set(json.loads(ln)) == set(__import__("backend.proposal.service", fromlist=["ITEM_KEYS"]).ITEM_KEYS)
    items = Service(runs_dir=env.runs, butir_dir=env.butir).items("akta")
    assert len(items) == 3 and len({i["id"] for i in items}) == 3
    assert [i["gold_spans"] for i in items[1:]] == [[], []]
    s = items_summary(items)
    assert s["n_items"] == 3 and s["by_mode"] == {"literal": 1, "parafrase": 0, "tolak": 2}
    assert items_summary([])["by_mode"] == {"literal": 0, "parafrase": 0, "tolak": 0}
    new_proc = Service(runs_dir=env.runs, butir_dir=env.butir).items("akta")  # proses baru
    assert [i["id"] for i in new_proc] == [i["id"] for i in items]


# ============================================================================= SU16
def met(iid, gold, cov, rt, gt, rank, parts=(1, 1)):
    return ItemMetrics(gold_chars=gold, covered_gold_chars=cov, retrieved_tokens=rt, gold_tokens_retrieved=gt, rank=rank,
                       parts_total=parts[0], parts_hit=parts[1], item_id=iid, setting_id="S", split=None)


A1, A2 = met("A1", 100, 100, 20, 10, 1), met("A2", 80, 40, 40, 8, 2, (2, 1))
N1, N2 = met("N1", 0, 0, 30, 0, None, (0, 0)), met("N2", 0, 0, 25, 0, None, (0, 0))


def test_su16_aggregates_exclude_no_gold():
    for n in (N1, N2):
        assert (n.span_recall, n.token_precision, n.reciprocal_rank, n.recall_at_k, n.fully_covered) == (None,) * 5
    g = aggregate([A1, A2, N1, N2], setting_id="S", split=None, budget_tokens=1)
    assert (g.mean_span_recall, g.mean_token_precision, g.mrr) == (Fraction(3, 4), Fraction(7, 20), Fraction(3, 4))
    assert g.mean_retrieved_tokens == 30 and g.fully_covered_count == {"covered": 1, "total": 2} and g.no_gold_count == 2
    assert mean_recall_at_k([A1, A2, N1, N2]) == Fraction(3, 4)
    assert (N1.retrieved_tokens, N2.retrieved_tokens) == (30, 25)
    z = aggregate([N1, N2], setting_id="S", split=None, budget_tokens=1)
    assert (z.mean_span_recall, z.mean_token_precision, z.mrr, z.mean_retrieved_tokens) == (None,) * 4
    assert z.fully_covered_count == {"covered": 0, "total": 0} and mean_recall_at_k([N1, N2]) is None


# ============================================================================= SU17
def rit(i, origin, mode, status):
    return {"id": i, "origin": origin, "mode": mode, "review_status": status, "split": None, "family": "akta"}


ITEMS17 = [rit("A1", "spark_disetujui", "literal", "disetujui"), rit("A2", "spark_disetujui", "parafrase", "diubah"),
           rit("N1", "spark_disetujui", "tolak", "disetujui"), rit("N2", "spark_disetujui", "tolak", "diubah")]
MET17 = [A1, A2, N1, N2]


def test_su17_origin_and_mode_reports():
    r = origin_report(ITEMS17, MET17, split=None)["spark_disetujui"]
    assert (r["n_items"], r["n_with_gold"], r["n_no_gold"], r["mean_span_recall"], r["fully_covered"]) == (
        4, 2, 2, 0.75, {"covered": 1, "total": 2})
    assert r["mean_token_precision"] == pytest.approx(0.35)
    op = origin_report(ITEMS17, MET17, split=None)["operator"]
    assert (op["n_items"], op["mean_span_recall"], op["fully_covered"]) == (0, None, {"covered": 0, "total": 0})
    m = mode_report(ITEMS17, MET17, split=None)
    assert set(m) == {"literal", "parafrase", "tolak"}
    assert (m["parafrase"]["n_items"], m["parafrase"]["n_with_gold"], m["parafrase"]["n_no_gold"], m["parafrase"]["mean_span_recall"],
            m["parafrase"]["fully_covered"]) == (1, 1, 0, 0.5, {"covered": 0, "total": 1})
    assert m["parafrase"]["mean_token_precision"] == pytest.approx(0.2)
    assert (m["tolak"]["n_items"], m["tolak"]["n_with_gold"], m["tolak"]["n_no_gold"], m["tolak"]["mean_span_recall"],
            m["tolak"]["mean_token_precision"], m["tolak"]["fully_covered"]) == (2, 0, 2, None, None, {"covered": 0, "total": 0})
    assert (m["literal"]["n_items"], m["literal"]["mean_span_recall"], m["literal"]["mean_token_precision"], m["literal"]["fully_covered"]) == (
        1, 1.0, 0.5, {"covered": 1, "total": 1})
    empty = mode_report([], [], split=None)
    assert set(empty) == {"literal", "parafrase", "tolak"} and empty["tolak"]["mean_span_recall"] is None
    # MRR dan Recall@K per mode
    gp = lambda ms: aggregate(ms, setting_id="S", split=None, budget_tokens=1)  # noqa: E731
    assert (gp([A1]).mrr, mean_recall_at_k([A1])) == (1, 1) and (gp([A2]).mrr, mean_recall_at_k([A2])) == (Fraction(1, 2), Fraction(1, 2))
    assert (gp([N1, N2]).mrr, mean_recall_at_k([N1, N2])) == (None, None)
    assert [i["id"] for i in filter_items(ITEMS17, mode="tolak")] == ["N1", "N2"]
    with pytest.raises(Exception):
        filter_items(ITEMS17, mode="unanswerable")
    with pytest.raises(Exception):
        origin_report(ITEMS17, MET17, split="bogus")


def test_su17_split_none_does_not_leak_into_uupt_filter():
    held = [{**i, "split": "held_out"} for i in ITEMS17]
    assert origin_report(held, MET17)["spark_disetujui"]["n_items"] == 4  # default tetap held_out
    assert origin_report(ITEMS17, MET17)["spark_disetujui"]["n_items"] == 0  # akta tanpa split: split="held_out" tidak memilih apa pun


def test_su17_rejection_cells_and_must_abstain_row():
    cells = {
        "N1": cell("tolak", [], ["c1", "c2"], []),
        "N2": cell("bukti_tidak_cukup", [], ["c1"], []),
        "N3": cell("jawab", [(A11, T11)], ["c1"], []),
        "A1": cell("tolak", [], ["c1"], G1),
        "A2": cell("jawab", [(A11, T11)], ["c1", "c2"], G1),
    }
    assert cells == {"N1": "abstained_correct", "N2": "abstained_correct", "N3": "answered_unsupported",
                     "A1": "abstained_should_answer", "A2": "answered_supported"}
    items = [*ITEMS17, rit("N3", "spark_disetujui", "tolak", "disetujui")]
    answers = [{"item_id": k, "output": ans({"N1": "tolak", "N2": "bukti_tidak_cukup", "N3": "jawab", "A1": "tolak", "A2": "jawab"}[k])}
               for k in cells]
    answers = [{"item_id": a["item_id"], "output": {"status": {"N1": "tolak", "N2": "bukti_tidak_cukup", "N3": "jawab", "A1": "tolak",
                                                              "A2": "jawab"}[a["item_id"]]}} for a in answers]
    assert must_abstain_summary(items, answers) == {"n": 3, "abstained_correct": 2}  # bukan semua sel Abstained-correctly


# ============================================================================= SU18
G = GateConfig(factor_bp=15700, batch_cap_micros=2_000_000, cumulative_cap_micros=20_000_000, cumulative_pct=80)


def test_su18_gate_cases():
    assert G.cumulative_threshold_micros == 16_000_000
    v = evaluate_gate([100] * 5, 0, G)
    assert (v.expected, v.batas_atas, v.ok) == (500, 785, True)
    v = evaluate_gate([100] * 5, 15_999_300, G)
    assert (v.batas_atas, v.ok, v.reasons) == (785, False, ("cumulative_over_threshold",))  # tanpa faktor: 15.999.800 lolos
    assert upper_bound(101, 15700) == 159
    assert evaluate_gate([100] * 5, 15_999_215, G).ok is True  # tepat 16.000.000 lolos
    assert evaluate_gate([100] * 5, 15_999_216, G).ok is False
    g1 = dataclasses.replace(G, factor_bp=10000)
    assert evaluate_gate([2_000_000], 0, g1).ok is True
    v = evaluate_gate([2_000_001], 0, g1)
    assert v.ok is False and v.reasons == ("batas_atas_over_batch_cap",)
    assert all(isinstance(x, int) for x in (v.expected, v.batas_atas, v.spent))


def test_su18_config_from_repo_and_invalid():
    c = load_gate_config(config.load("budget"))
    assert c == G
    b = config.load("budget")
    for bad in (0, -1, 1.57, True, "15700"):
        with pytest.raises(ConfigInvalid):
            load_gate_config({**b, "batch_gate": {**b["batch_gate"], "factor_bp": bad}})
    with pytest.raises(ConfigInvalid):
        load_gate_config({k: v for k, v in b.items() if k != "batch_gate"})


def test_su18_cli_refuses_before_spark(tmp_path, capsys):
    from backend.proposal.__main__ import main

    def forbidden():
        raise AssertionError("client must not be created")
    rc = main(["unanswerable", "--family", "akta", "--doc", "akta-01", "--run"], spent=15_999_999, client_factory=forbidden)
    out = capsys.readouterr()
    assert rc == 3 and "REFUSED" in out.out and "gate refused" in out.err
    rc = main(["unanswerable", "--family", "akta", "--doc", "akta-01", "--project-only"], spent=0)
    out = capsys.readouterr().out
    assert rc == 0 and "batas_atas=" in out and "gate: PASS" in out and "akta-01" in out
    assert main(["unanswerable", "--family", "lain", "--project-only"]) == 2  # uupt kini sah (H-099 V1), lihat SV1


# ============================================================================= SU20
def test_su20_implied_candidate_only_dense_catches(prod):
    ck, _ = prod
    cfg = acfg()
    dense = lambda q: [("L3", 0.85), ("L5", 0.30), ("L1", 0.10)]  # noqa: E731
    on = AbsenceChecker(UNITS, ck.tokenize, ck.bm25_rank, dense, cfg).check(Q["U7"])
    assert on["status"] == "doubtful" and on["reasons"] == ["dense_similar"] and on["max_cov"] == {"num": 0, "den": 2}
    assert [(t["source"], t["rank"], t["unit_text"]) for t in on["top_k"]] == [
        ("bm25", 1, LINES[4]), ("bm25", 2, LINES[5]), ("bm25", 3, LINES[3]),
        ("dense", 1, LINES[3]), ("dense", 2, LINES[5]), ("dense", 3, LINES[1])]
    off = AbsenceChecker(UNITS, ck.tokenize, ck.bm25_rank, None, cfg).check(Q["U7"])
    assert off["status"] == "doubtful" and off["reasons"] == ["dense_unavailable"]
    fx = fx_checker().check("Siapa pemilik Perseroan?")  # fixture: T* = {pemilik}
    assert fx["max_cov"] == {"num": 0, "den": 1} and fx["status"] == "ok"


# ============================================================================= SU21
def test_su21_duplicates(tmp_path):
    dup = {**cand("U3"), "query": "siapa KOMISARIS perseroan?  "}
    env = mk(tmp_path, "a", [cand("U3"), dup, cand("U4")])
    d = gen_ok(env)
    assert [p["body"]["query"] for p in d["proposals"]] == [U["U3"][0], U["U4"][0]] and all(p["duplicate_of"] is None for p in d["proposals"])
    assert normalize_query(dup["query"]) == normalize_query(U["U3"][0])
    first = d["proposals"][0]["proposal_id"]
    assert env.decide(first, approve()).status_code == 200
    # run baru (kunci cache beda) menghasilkan U3 lagi: tidak dibuang, lencana informatif
    env.ps.max_per_call = 2
    env.tr.default = responder([cand("U3"), cand("U5")])
    d2 = gen_ok(env)
    new = next(p for p in d2["proposals"] if p["proposal_id"] != first and p["body"]["query"] == U["U3"][0])
    assert new["duplicate_of"] == first and new["absence_check"]["reasons"] == env.ps.get(first)["absence_check"]["reasons"]
    r = env.decide(new["proposal_id"], approve())
    assert r.status_code == 200 and r.json()["proposal"]["duplicate_of"] == first
    ids = {i["id"] for i in env.ps.items("akta")}
    assert len(ids) == 2  # dua Item beda id
    q = env.http.get("/api/families/akta/proposals").json()
    assert {p["proposal_id"]: p["duplicate_of"] for p in q["proposals"] if p["body"]["query"] == U["U3"][0]} == {first: None, new["proposal_id"]: first}


# ============================================================================= SU22
def test_su22_replay(tmp_path):
    env = mk(tmp_path, "r")
    d = gen_ok(env)
    calls = env.tr.calls
    rep = mk(tmp_path, "r", replay=True)  # direktori yang sama, mode replay
    r = gen(rep)
    assert r.status_code == 200, r.text
    assert rep.tr.calls == 0 and r.json()["runs"][0]["status"] == "replay"
    assert [p["proposal_id"] for p in r.json()["proposals"]] == [p["proposal_id"] for p in d["proposals"]] and calls == 1
    miss = mk(tmp_path, "empty", replay=True)
    rr = gen(miss)
    assert rr.status_code == 409 and rr.json()["error"]["code"] == "replay_no_stored_run" and miss.tr.calls == 0


def test_su22_roundtrip_keeps_empty_gold(tmp_path):
    from backend.replay.export import dump
    env = mk(tmp_path, u_out=[cand("U3")])
    pid = by_q(gen_ok(env))["U3"]
    item = env.decide(pid, approve()).json()["item"]
    got = json.loads(dump({"items": [item]}))["items"][0]
    assert got["gold_spans"] == [] and got["mode"] == "tolak"
    before = items_summary([item])
    after = items_summary(json.loads(dump({"items": [item]}))["items"])
    assert before == after and after["by_mode"]["tolak"] == 1
    snap = Service(runs_dir=env.runs, butir_dir=env.butir).items("akta")
    assert snap[0]["gold_spans"] == [] and snap[0]["mode"] == "tolak"


# ============================================================================= umum
def test_repo_data_and_runs_untouched_hint():
    """Test ini tidak menulis `data/butir`/`runs` repo; prompt v2 dan config terbaca dari repo saja."""
    assert (REPO_ROOT / "prompts/d/v2.md").read_text(encoding="utf-8").startswith("Kamu membantu operator")


# ============================================================================= perbaikan W60
def test_w60_s1_no_dense_switch_in_config_and_production_default_tries_dense():
    assert "dense_enabled" not in config.load("proposals")["unanswerable"]
    assert load_absence_config().device == "cpu"
    ck = production_checker(UNITS, acfg(), config.load("retrieval"))  # tanpa encoder: produksi tetap mencoba dense
    a = ck.check(Q["U3"])
    assert a["status"] == "doubtful" and a["reasons"] == ["dense_unavailable"] and a["max_cosine"] is None


def test_w60_s2_device_from_config_and_cli_override(monkeypatch):
    import backend.chunking as chunking
    from backend.proposal import absence as ab
    seen = []
    monkeypatch.setattr(ab, "encoder_dense_ranker", lambda units, rcfg, *, device, encoder, cache_dir: seen.append(device) or (lambda q: []))
    monkeypatch.setattr(chunking, "schema_identity", lambda rec: {"schema_version": 2, "schema_hash": "h"})

    class Base:
        config_dir = None
        schema_binding = lambda self, fam: type("SB", (), {"active": lambda s: {"schema_version": 2}})()  # noqa: E731
        doc = lambda self, i: type("D", (), {"text": AKT})()  # noqa: E731
        schema_chunks = lambda self, d, v: [{"chunk_id": u, "start": AKT.index(t), "end": AKT.index(t) + len(t)} for u, t in UNITS]  # noqa: E731
        cfg = lambda self, n: config.load(n)  # noqa: E731
    d = DocInfo(DOC, "akta", AKT, "ha1")
    ab.service_checker_provider(Base())(d).check(Q["U3"])
    ab.service_checker_provider(Base(), device="cuda")(d).check(Q["U3"])
    assert seen == ["cpu", "cuda"]


def test_w60_s3_encoder_failure_is_memoized():
    calls = []

    def factory():
        calls.append(1)
        raise OSError("model missing")
    ck = production_checker(UNITS, acfg(), config.load("retrieval"), dense_factory=factory)
    for k in ("U1", "U2", "U3"):
        assert ck.check(Q[k])["reasons"].count("dense_unavailable") == 1
    assert len(calls) == 1


def test_w60_m26_generic_boundary_is_strictly_greater():
    four = [(f"u{i}", t) for i, t in enumerate(["x a", "x b", "c", "d"])]  # df(x) = 2/4 = 0,5 persis
    ck = AbsenceChecker(four, fx_tok, lambda q: [], None, acfg(), dense_off=True)
    assert "x" not in ck.generic  # `>` bukan `>=` (P2)
    three = [(f"u{i}", t) for i, t in enumerate(["x a", "x b", "x c", "d"])]  # 3/4 > 0,5
    assert "x" in AbsenceChecker(three, fx_tok, lambda q: [], None, acfg(), dense_off=True).generic


def test_w60_m14_stage_item_enforces_mode_invariant(tmp_path):
    env = mk(tmp_path)
    base = {k: None for k in __import__("backend.proposal.service", fromlist=["ITEM_KEYS"]).ITEM_KEYS}
    ok = {**base, "id": "x1", "family": "akta", "mode": "tolak", "gold_spans": [], "query": "q"}
    assert env.ps._stage_item(ok)[0].exists()
    for bad in ({**ok, "id": "x2", "gold_spans": [{"start": 0, "end": 1}]},  # x3 (uupt + tolak) kini sah, H-099 V4
                {**ok, "id": "x4", "mode": "unanswerable"}):
        with pytest.raises(OSError):
            env.ps._stage_item(bad)
