"""M2.1 tambahan Tier 1: butir wajib tolak UU PT (`tolak` untuk `uupt`, D `unanswerable` UU PT; H-095, H-099), SV1-SV17
(docs/scenarios/M2.1-unanswerable-uupt.md, disetujui H-099).

Teks UU mainan sintetis ("UU Mainan", bukan UU 40/2007); id butir sintetis; tidak menulis `data/butir/` atau `runs/` repo.
Klien Spark palsu menghitung panggilan, ranker suntikan, jam suntikan 2026-10-29T10:00:00Z, direktori sementara. Tanpa Model
API dan tanpa jaringan. `prompt_hash(v3)` tidak dikunci literal: dihitung dari berkas (v3 sedang ditinjau operator)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import shutil
from fractions import Fraction
from pathlib import Path

import pytest

from backend import config
from backend.api.app import Service
from backend.api.errors import ApiError
from backend.config import REPO_ROOT
from backend.pipeline.grid_run import GridRunError, load_items
from backend.proposal import prompt as pm
from backend.proposal.absence import AbsenceChecker, load_absence_config, production_checker
from backend.proposal.item import item_mode_problem
from backend.proposal.report import items_summary
from backend.proposal.service import ITEM_KEYS, DocInfo
from backend.spark import ConfigInvalid, Ledger
from backend.spark.store import canonical_json, sha256_hex

from .proposal_fakes import Env
from .test_proposal_decide import approve
from .test_proposal_unanswerable import AKT, OLD_PROPOSALD_HASH, acfg, responder
from .test_proposal_unanswerable import fx_checker as akta_fx_checker

# ----------------------------------------------------------------------------- fixture UUM
A = [
    "Pasal 1 (1) Perseroan adalah badan hukum.",
    "(2) Badan hukum didirikan berdasarkan perjanjian.",
    "Pasal 2 (1) Modal dasar Perseroan paling sedikit Rp 50.000.000.",
    "(2) Modal dasar dapat diubah oleh RUPS.",
    "Pasal 3 (1) Direksi menjalankan pengurusan Perseroan.",
    "(2) Direksi terdiri atas satu orang atau lebih.",
    "Pasal 4 Dewan Komisaris melakukan pengawasan atas Direksi.",
    "Pasal 5 RUPS memutuskan penggunaan laba bersih Perseroan.",
    "Penjelasan Pasal 3 Cukup jelas.",
]
UUM = "\n".join(A)
S_UNITS = [("S1", A[0] + "\n" + A[1]), ("S2", A[2] + "\n" + A[3]), ("S3", A[4] + "\n" + A[5]), ("S4", A[6]), ("S5", A[7]),
           ("S6", A[8])]
S_TEXT = dict(S_UNITS)
UDOC, ADOC = "uupt-mainan", "akta-x"
STOP_UU = {"apa", "siapa", "berapa", "yang", "dan", "di", "adalah", "dari", "dalam", "itu", "akan", "setelah", "tidak", "atas", "atau",
           "oleh", "dapat"}


def uu_tok(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if w not in STOP_UU]


def doc_order_ranker(units):
    """Ranker BM25 suntikan SV3: semua unit berbagi >= 1 token T(q) (termasuk generik), urutan dokumen."""
    def rank(q: str) -> list[tuple[str, float]]:
        qs = set(uu_tok(q))
        return [(uid, 1.0) for uid, t in units if qs & set(uu_tok(t))]
    return rank


def uu_checker(units=S_UNITS, **cfg) -> AbsenceChecker:
    return AbsenceChecker(units, uu_tok, doc_order_ranker(units), None, acfg(**cfg), dense_off=True)


V = {
    "V1": ("Siapa auditor Perseroan?", "rincian_tidak_diatur", "Auditor tidak diatur"),
    "V2": ("Berapa gaji anggota Direksi?", "rincian_tidak_diatur", "Gaji Direksi tidak diatur"),
    "V3": ("Siapa yang melakukan pengawasan atas Direksi?", "di_luar_akta", "Kandidat buruk: jawaban ada (Pasal 4)"),
    "V4": ("Apa itu Perseroan?", "di_luar_akta", "Terlalu umum"),
    "V5": ("Berapa biaya pengesahan badan hukum Perseroan?", "rincian_tidak_diatur", "Biaya diatur peraturan pelaksana"),
}
EDIT_Q = "Berapa biaya pengesahan Perseroan?"


def vc(k: str, doc: str = UDOC) -> dict:
    q, kode, teks = V[k]
    return {"query": q, "doc_id": doc, "alasan_kode": kode, "alasan_teks": teks}


class Capture:
    """Responder terskrip yang juga merekam teks masukan tiap permintaan."""

    def __init__(self, u_out, lit_out=None):
        self.inputs: list[str] = []
        self._r = responder(u_out, lit_out)

    def __call__(self, tr, request):
        self.inputs.append(json.loads(request.content.decode("utf-8"))["input"])
        return self._r(tr, request)


def mku(tmp: Path, sub: str = "e", u_out=None, *, lit_out=None, checker=None, **kw) -> Env:
    """Env UU mainan: dokumen `uupt-mainan` (uupt, hu1) + `akta-x` (akta, ha1); pemeriksa fixture per keluarga."""
    out = u_out if u_out is not None else [vc("V1"), vc("V2"), vc("V3")]
    kw.setdefault("default", Capture(out, lit_out))
    env = Env(tmp / sub, with_v1=False, doc_id=UDOC, doc_text=UUM, sha="hu1", **kw)
    env.docs[ADOC] = DocInfo(ADOC, "akta", AKT, "ha1")
    env.ps.checker_provider = checker or (lambda d: uu_checker() if d.family == "uupt" else akta_fx_checker())
    return env


def gen(env, modes=("unanswerable",), family="uupt", doc_id=UDOC):
    return env.http.post(f"/api/families/{family}/proposals/generate", json={"doc_id": doc_id, "modes": list(modes)})


def gen_ok(env, modes=("unanswerable",), family="uupt", doc_id=UDOC):
    r = gen(env, modes, family, doc_id)
    assert r.status_code == 200, r.text
    return r.json()


def by_q(resp) -> dict[str, str]:
    inv = {v[0]: k for k, v in V.items()}
    return {inv[p["body"]["query"]]: p["proposal_id"] for p in resp["proposals"] if p["body"]["query"] in inv}


def no_client():
    raise AssertionError("Spark client must not be created")


def file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def repo_snapshot() -> dict[str, str]:
    """Isi `data/butir/` repo (baca saja) untuk memastikan test tidak menulisnya."""
    return {p.name: file_sha(p) for p in sorted((REPO_ROOT / "data" / "butir").glob("*"))}


# ============================================================================= SV1
def test_sv1a_w4_unanswerable_uupt(tmp_path):
    env = mku(tmp_path)
    d = gen_ok(env)
    assert env.tr.calls == 1 and len(d["runs"]) == 1 and d["runs"][0]["status"] == "ok"
    assert len(d["proposals"]) == 3
    for p in d["proposals"]:
        assert p["family"] == "uupt" and p["body"]["mode"] == "unanswerable" and p["body"]["doc_id"] == UDOC
        assert p["absence_check"] is not None and p["absence_check"]["status"] in ("ok", "doubtful")
        assert p["validation"] is None and p["resolved_span"] is None and p["review_status"] == "usulan"
    assert [p["proposal_id"] for p in env.ps.list_proposals("uupt")] == [p["proposal_id"] for p in d["proposals"]]
    assert env.ps.list_proposals("akta") == []


def test_sv1b_literal_and_unanswerable_two_runs(tmp_path):
    env = mku(tmp_path, lit_out=[])
    d = gen_ok(env, ("literal", "unanswerable"))
    assert env.tr.calls == 2 and len(d["runs"]) == 2 and d["runs"][0]["run_id"] != d["runs"][1]["run_id"]
    assert [p["body"]["mode"] for p in d["proposals"]] == ["unanswerable"] * 3


@pytest.mark.parametrize("name,family,doc_id,modes,status,code", [
    ("c", "uupt", ADOC, ["unanswerable"], 404, "not_found"),
    ("d", "lain", UDOC, ["unanswerable"], 400, "invalid_request"),
    ("e", "uupt", UDOC, ["tolak"], 400, "invalid_request"),
])
def test_sv1_cde_errors_before_any_call(tmp_path, name, family, doc_id, modes, status, code):
    env = mku(tmp_path, name)
    r = gen(env, modes, family, doc_id)
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert env.tr.calls == 0 and not env.ps.index_dir.exists() and Ledger(env.runs).spent() == 0


def test_sv1d_service_family_list_is_single_source(tmp_path):
    """Lapisan service sendiri (bukan hanya router) menolak keluarga di luar daftar sah; daftar = `prompt.FAMILIES_U`."""
    assert pm.FAMILIES_U == ("akta", "uupt")
    env = mku(tmp_path)
    env.docs["lain-1"] = DocInfo("lain-1", "lain", UUM, "hl1")
    with pytest.raises(ApiError) as ei:
        env.ps.generate("lain", "lain-1", ["unanswerable"], profile="meta", model_config=env.model, client_factory=no_client)
    assert ei.value.status == 400 and ei.value.code == "invalid_request" and "'akta', 'uupt'" in ei.value.message
    # mode ber-span untuk keluarga lain tidak ikut tertolak oleh gerbang `unanswerable`
    with pytest.raises(ApiError) as ei:
        env.ps.generate("uupt", "lain-1", ["literal"], profile="meta", model_config=env.model, client_factory=no_client)
    assert ei.value.status == 404


def _cli(argv, tmp_path, **kw):
    from backend.proposal.__main__ import main
    return main(argv, base=Service(runs_dir=tmp_path / "runs", butir_dir=tmp_path / "butir"), **kw)


def test_sv1f_sv17_cli_project_only_uupt(tmp_path, capsys, monkeypatch):
    import backend.proposal.__main__ as cli
    from backend.proposal.gate import evaluate_gate as real_gate
    seen = []
    monkeypatch.setattr(cli, "evaluate_gate", lambda e, s, c: seen.append((list(e), s, real_gate(e, s, c))) or seen[-1][2])
    before = repo_snapshot()
    rc = _cli(["unanswerable", "--family", "uupt", "--project-only"], tmp_path, spent=585_376, client_factory=no_client)
    out = capsys.readouterr().out
    assert rc == 0
    doc_lines = [ln for ln in out.splitlines() if ln.startswith("  ")]
    assert len(doc_lines) == 1 and doc_lines[0].split()[0] == "uupt-40-2007"  # satu dokumen UU PT, bukan akta
    (exp, spent, v), = seen
    assert len(exp) == 1 and spent == 585_376
    assert f"total expected={v.expected} batas_atas={v.batas_atas} " in out and "gate: PASS" in out
    assert f"expected micro-USD={exp[0]} " in doc_lines[0]
    # prompt v3 (by_family_mode), batas 3; expected dari tokenizer lokal atas render_input yang sama
    prm = pm.prompt_for("uupt", "unanswerable")
    assert prm.version == "v3" and prm.prompt_hash == file_sha(pm.PROMPT_DIR / "v3.md")
    assert f"prompt v3 {prm.prompt_hash[:12]}" in out and "family=uupt max_per_call=3" in out
    base = Service(runs_dir=tmp_path / "runs")
    d = base.doc("uupt-40-2007")
    n_in = int(base.tok().count(pm.render_input(prm, d.doc_id, d.text, "unanswerable", 3, d.clean_sha256)))
    assert f"input_tokens={n_in} " in doc_lines[0]
    assert not (tmp_path / "runs").exists() and not (tmp_path / "butir").exists()  # 0 berkas ditulis
    assert repo_snapshot() == before


def test_sv1g_cli_unknown_family_exit_2(tmp_path, capsys):
    rc = _cli(["unanswerable", "--family", "lain", "--project-only"], tmp_path, client_factory=no_client)
    err = capsys.readouterr().err
    assert rc == 2 and "akta, uupt" in err


def test_sv17_cli_run_refused_exit_3_no_call(tmp_path, capsys):
    def no_checker(doc):
        raise AssertionError("checker must not be built")
    rc = _cli(["unanswerable", "--family", "uupt", "--run"], tmp_path, spent=16_000_000, client_factory=no_client,
              checker_provider=no_checker)
    out = capsys.readouterr()
    assert rc == 3 and "REFUSED (cumulative_over_threshold)" in out.out and "gate refused" in out.err
    assert not (tmp_path / "runs").exists()


# ============================================================================= SV2
class FakeBase:
    """Pengganti `Service` untuk `service_checker_provider`: store skema UU PT yang bisa diganti; unit = potongan skema."""

    def __init__(self, versions: dict[int, list[tuple[str, str]]], active: int | None):
        self.config_dir = None
        self.versions, self.active_v, self.chunk_calls, self.fams_asked = versions, active, [], []

    def schema_binding(self, fam):
        base = self
        base.fams_asked.append(fam)
        if fam != "uupt":  # skema keluarga lain tidak boleh dipakai pemeriksa UU PT
            return type("SB", (), {"active": lambda s: None})()
        return type("SB", (), {"active": lambda s: None if base.active_v is None else {"schema_version": base.active_v, "family": fam}})()

    def doc(self, doc_id):
        return type("D", (), {"text": UUM, "doc_id": doc_id, "family": "uupt"})()

    def schema_chunks(self, d, v):
        self.chunk_calls.append((d.doc_id, v))
        return [{"chunk_id": u, "start": UUM.index(t), "end": UUM.index(t) + len(t)} for u, t in self.versions[v]]

    def cfg(self, n):
        return config.load(n)


@pytest.fixture
def schema_ident(monkeypatch):
    import backend.chunking as chunking
    from backend.proposal import absence as ab
    monkeypatch.setattr(chunking, "schema_identity", lambda rec: {"schema_version": rec["schema_version"], "schema_hash": f"h{rec['schema_version']}"})
    monkeypatch.setattr(ab, "encoder_dense_ranker", lambda units, rcfg, **kw: (lambda q: []))  # tanpa bge-m3


def test_sv2a_units_are_active_schema_chunks(tmp_path, schema_ident):
    from backend.proposal.absence import service_checker_provider
    base = FakeBase({2: S_UNITS}, 2)
    ck = service_checker_provider(base)(DocInfo(UDOC, "uupt", UUM, "hu1"))
    assert base.fams_asked == ["uupt"]  # unit dari skema A keluarga uupt, bukan akta
    assert list(ck.units) == S_UNITS and base.chunk_calls == [(UDOC, 2)]  # skema v2 aktif, bukan structure_handwritten
    assert ck.generic == {"pasal", "persero"}  # tokenizer produksi atas unit Pasal (V2)


def test_sv2b_no_active_schema_404_before_spark(tmp_path, schema_ident):
    from backend.proposal.absence import service_checker_provider
    fb = FakeBase({}, None)
    env = mku(tmp_path, checker=service_checker_provider(fb))
    r = gen(env)
    assert fb.fams_asked == ["uupt"]
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert "No schema A record for family 'uupt'" in r.json()["error"]["message"]
    assert env.tr.calls == 0 and Ledger(env.runs).spent() == 0 and env.ps.list_proposals() == []
    assert not env.ps.index_dir.exists() and not env.ps.records_dir.exists()


def test_sv2c_checker_rebuilt_when_active_schema_changes(tmp_path, schema_ident):
    from backend.proposal.absence import service_checker_provider
    base = FakeBase({2: S_UNITS, 3: S_UNITS[:5]}, 2)
    prov = service_checker_provider(base)
    built = []
    env = mku(tmp_path, checker=lambda d: built.append(prov(d)) or built[-1])
    first = gen_ok(env)
    snap = {p["proposal_id"]: env.record_bytes(p["proposal_id"]) for p in first["proposals"]}
    base.active_v = 3
    env.ps.max_per_call = 2  # kunci D berbeda -> W4 kedua memanggil Spark dan membangun pemeriksa lagi
    gen_ok(env)
    assert env.tr.calls == 2 and base.chunk_calls == [(UDOC, 2), (UDOC, 3)]
    assert built[0] is not built[1] and list(built[1].units) == S_UNITS[:5]
    assert {pid: env.record_bytes(pid) for pid in snap} == snap  # rekaman lama tidak ditulis ulang


# ============================================================================= SV3
SV3_WANT = {"V1": ("ok", [], (0, 1)), "V2": ("ok", [], (1, 3)), "V3": ("doubtful", ["lexical_overlap"], (3, 3)),
            "V4": ("doubtful", ["no_distinctive_terms"], (0, 0)), "V5": ("doubtful", ["lexical_overlap"], (2, 4))}


def test_sv3_fixture_table_schema_units(tmp_path):
    assert uu_checker().generic == {"pasal", "perseroan"}
    env = mku(tmp_path, u_out=[vc(k) for k in V])
    env.ps.max_per_call = 5
    d = gen_ok(env)
    ids = by_q(d)
    assert set(ids) == set(V)  # kelimanya tersimpan (doubtful tidak dibuang, P3)
    hashes = set()
    for k, (st, rs, (num, den)) in SV3_WANT.items():
        a = env.ps.get(ids[k])["absence_check"]
        assert (a["status"], a["reasons"], a["max_cov"], a["max_cosine"]) == (st, rs, {"num": num, "den": den}, None), k
        hashes.add(a["config_hash"])
    assert len(hashes) == 1
    v1 = env.ps.get(ids["V1"])["absence_check"]
    assert [t["unit_text"] for t in v1["top_k"]] == [S_TEXT["S1"], S_TEXT["S2"], S_TEXT["S3"]]
    # generik per dokumen (bukan gabungan akta + UU PT): pemeriksa akta tetap punya himpunan generiknya sendiri
    assert akta_fx_checker().generic == {"pasal", "perseroan"} and uu_checker(units=S_UNITS[:1]).generic != uu_checker().generic


# ============================================================================= SV3b
SV3B = {  # T* produksi, top_k (unit), max_cov, status
    "V1": (["auditor", "siapa"], ["S5", "S1", "S3"], (0, 2), "ok"),
    "V2": (["anggota", "berapa", "direksi", "gaji"], ["S3", "S4"], (1, 4), "ok"),
    "V3": (["atas", "awas", "direksi", "laku", "siapa"], ["S4", "S3"], (4, 5), "doubtful"),
    "V4": (["apa"], ["S5", "S1", "S3"], (0, 1), "ok"),
    "V5": (["badan", "berapa", "biaya", "hukum", "kesah"], ["S1", "S5", "S3"], (2, 5), "ok"),
    "E": (["berapa", "biaya", "kesah"], ["S5", "S1", "S3"], (0, 3), "ok"),
}


@pytest.mark.parametrize("k", list(SV3B))
def test_sv3b_production_tokenizer_on_schema_units(k):
    ck = production_checker(S_UNITS, acfg(), config.load("retrieval"), dense_off=True)
    assert ck.generic == {"pasal", "persero"}
    q = EDIT_Q if k == "E" else V[k][0]
    tstar, top, (num, den), status = SV3B[k]
    assert sorted(set(ck.tokenize(q)) - ck.generic) == tstar
    a = ck.check(q)
    assert [t["unit_text"] for t in a["top_k"]] == [S_TEXT[u] for u in top] and all(t["source"] == "bm25" for t in a["top_k"])
    assert a["max_cov"] == {"num": num, "den": den} and a["status"] == status
    assert a["reasons"] == (["lexical_overlap"] if status == "doubtful" else [])


def test_sv3b_unit_tokens():
    ck = production_checker(S_UNITS, acfg(), config.load("retrieval"), dense_off=True)
    assert set(ck.tokenize(S_TEXT["S1"])) == {"1", "2", "badan", "dasar", "diri", "hukum", "janji", "pasal", "persero"}
    assert set(ck.tokenize(S_TEXT["S4"])) == {"4", "atas", "awas", "dewan", "direksi", "komisaris", "laku", "pasal"}


# ============================================================================= SV4
PROPOSALU_HASH = "d9700ee165d86f33abafd458fd901def481fa466738751c5644b4edbf0d2a5b2"  # dikunci literal: skema tidak berubah (V3)


def ref_key(prompt_hash, schema_hash, mode, cap, sha, doc):
    return sha256_hex(canonical_json(["d", "meta", "muse-spark-1.3-contributor", "low", prompt_hash, schema_hash, sha, doc, mode, cap]))


def hp(name: str, d: Path | None = None) -> str:
    return file_sha((d or pm.PROMPT_DIR) / name)


def keys(env) -> set[str]:
    return {p.stem for p in env.ps.index_dir.glob("*.json")} if env.ps.index_dir.exists() else set()


def test_sv4_keys_per_family_mode(tmp_path):
    assert pm.schema_hash("unanswerable") == PROPOSALU_HASH and pm.schema_hash("literal") == OLD_PROPOSALD_HASH
    cap = Capture([vc("V1"), vc("V2")], [])
    env = mku(tmp_path, default=cap)
    env.ps.prompt_provider = None  # lookup produksi `prompt_for` untuk semua mode
    akta_out = [{"query": "Apa nomor NPWP?", "doc_id": ADOC, "alasan_kode": "data_tidak_dimuat", "alasan_teks": "x"}]
    cap._r = responder(akta_out, [])
    gen_ok(env, family="akta", doc_id=ADOC)
    k_akta = ref_key(hp("v2.md"), PROPOSALU_HASH, "unanswerable", 3, "ha1", ADOC)
    assert keys(env) == {k_akta}
    cap._r = responder([vc("V1"), vc("V2")], [])
    gen_ok(env, ("literal", "parafrase", "unanswerable"))
    want_u = {ref_key(hp("v1.md"), OLD_PROPOSALD_HASH, m, 20, "hu1", UDOC) for m in ("literal", "parafrase")}
    k_uupt = ref_key(hp("v3.md"), PROPOSALU_HASH, "unanswerable", 3, "hu1", UDOC)
    assert keys(env) == {k_akta, k_uupt} | want_u and env.tr.calls == 4
    # templat: akta v2, uupt v3, ber-span v1
    tpl = {v: (pm.PROMPT_DIR / f"{v}.md").read_text(encoding="utf-8").rstrip() for v in ("v1", "v2", "v3")}
    assert cap.inputs[0].startswith(tpl["v2"] + "\n") and "\nMODE: unanswerable\n" in cap.inputs[0]
    by_mode = {re.search(r"\nMODE: (\w+)\n", t).group(1): t for t in cap.inputs[1:]}
    assert by_mode["unanswerable"].startswith(tpl["v3"] + "\n") and not by_mode["unanswerable"].startswith(tpl["v2"])
    assert by_mode["literal"].startswith(tpl["v1"] + "\n") and by_mode["parafrase"].startswith(tpl["v1"] + "\n")
    rec = json.loads((env.ps.index_dir / f"{k_uupt}.json").read_text(encoding="utf-8"))
    assert rec["run"]["prompt_version"] == "v3" and rec["family"] == "uupt"


def fixture_prompts(tmp: Path, mutate) -> Path:
    d = tmp / "prompts_d"
    d.mkdir(parents=True, exist_ok=True)
    for f in ("v1.md", "v2.md", "v3.md"):
        shutil.copyfile(pm.PROMPT_DIR / f, d / f)
    meta = json.loads((pm.PROMPT_DIR / "versions.json").read_text(encoding="utf-8"))
    mutate(meta)
    (d / "versions.json").write_text(json.dumps(meta, indent=2), encoding="utf-8", newline="\n")
    return d


@pytest.mark.parametrize("case,mutate", [
    ("a", lambda m: m.pop("by_family_mode")),
    ("b", lambda m: m.__setitem__("by_family_mode", {"uupt": {"unanswerable": "v1"}})),
    ("c", lambda m: m.__setitem__("by_family_mode", {"uupt": {"unanswerable": "v9"}})),
])
def test_sv4_lookup_failures_503_no_call(tmp_path, case, mutate):
    d = fixture_prompts(tmp_path, mutate)
    with pytest.raises(ConfigInvalid):
        pm.prompt_for("uupt", "unanswerable", d)
    env = mku(tmp_path, lit_out=[])
    env.ps.prompt_provider, env.ps.prompt_dir = None, d
    r = gen(env)
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
    assert env.tr.calls == 0 and Ledger(env.runs).spent() == 0 and keys(env) == set()
    r = gen(env, ("literal", "unanswerable"))  # gagal sebelum mode mana pun dipanggil
    assert r.status_code == 503 and env.tr.calls == 0
    if case == "a":  # akta tetap lewat by_mode; uupt literal tetap lewat current (kunci lama)
        env.tr.default = responder([{"query": "Apa NPWP?", "doc_id": ADOC, "alasan_kode": "data_tidak_dimuat", "alasan_teks": "x"}], [])
        gen_ok(env, family="akta", doc_id=ADOC)
        gen_ok(env, ("literal",))
        assert keys(env) == {ref_key(hp("v2.md", d), PROPOSALU_HASH, "unanswerable", 3, "ha1", ADOC),
                             ref_key(hp("v1.md", d), OLD_PROPOSALD_HASH, "literal", 20, "hu1", UDOC)}
        assert pm.prompt_for("akta", "unanswerable", d).version == "v2" and pm.prompt_for("uupt", "literal", d).version == "v1"


def test_sv4d_explicit_akta_entry_same_key(tmp_path):
    d0 = fixture_prompts(tmp_path / "x", lambda m: None)
    d1 = fixture_prompts(tmp_path / "y", lambda m: m["by_family_mode"].__setitem__("akta", {"unanswerable": "v2"}))
    for d in (d0, d1):
        assert pm.prompt_for("akta", "unanswerable", d).prompt_hash == hp("v2.md")
    out = []
    for i, d in enumerate((d0, d1)):
        env = mku(tmp_path, f"k{i}", default=responder([{"query": "Apa NPWP?", "doc_id": ADOC, "alasan_kode": "data_tidak_dimuat",
                                                          "alasan_teks": "x"}], []))
        env.ps.prompt_provider, env.ps.prompt_dir = None, d
        gen_ok(env, family="akta", doc_id=ADOC)
        out.append(keys(env))
    assert out[0] == out[1] == {ref_key(hp("v2.md"), PROPOSALU_HASH, "unanswerable", 3, "ha1", ADOC)}


def test_sv4_prompt_for_order_and_modes_rule(tmp_path):
    assert [pm.prompt_for(f, m).version for f, m in (("akta", "unanswerable"), ("uupt", "unanswerable"), ("uupt", "literal"),
                                                     ("uupt", "parafrase"), ("akta", "literal"))] == ["v2", "v3", "v1", "v1", "v1"]
    # keluarga tanpa entri (bukan akta) tidak jatuh ke by_mode
    with pytest.raises(ConfigInvalid):
        pm.prompt_for("lain", "unanswerable")
    # mode ber-span lewat by_family_mode memakai versi itu (tanpa syarat `modes`)
    d = fixture_prompts(tmp_path, lambda m: m["by_family_mode"]["uupt"].__setitem__("literal", "v2"))
    assert pm.prompt_for("uupt", "literal", d).version == "v2"  # bukan `current` (v1)
    assert pm.prompt_for("uupt", "parafrase", d).version == "v1"
    bad = fixture_prompts(tmp_path / "bad", lambda m: m["versions"]["v3"].pop("modes"))
    with pytest.raises(ConfigInvalid):
        pm.prompt_for("uupt", "unanswerable", bad)
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "versions.json").write_text("{", encoding="utf-8", newline="\n")
    with pytest.raises(ConfigInvalid):
        pm.prompt_for("akta", "unanswerable", tmp_path / "broken")


# ----------------------------------------------------------------------------- Q1 (a1): max_per_call_uupt opsional
def cfg_dir(tmp: Path, extra: str = "") -> Path:
    d = tmp / "cfg"
    d.mkdir(parents=True, exist_ok=True)
    text = (REPO_ROOT / "config" / "proposals.toml").read_text(encoding="utf-8")
    if extra:
        text = text.replace("max_per_call = 3\n", f"max_per_call = 3\n{extra}\n")
        assert extra in text
    (d / "proposals.toml").write_text(text, encoding="utf-8", newline="\n")
    return d


def test_q1_max_per_call_uupt_absent_in_repo_and_default():
    raw = config.load("proposals")["unanswerable"]
    assert "max_per_call_uupt" not in raw  # L2 menambahkannya hanya bila Q1 a1 terpicu
    c = load_absence_config()
    assert c.max_per_call_uupt is None and c.cap_for("uupt") == c.cap_for("akta") == 3


@pytest.mark.parametrize("bad", ["0", "-1", "2.5", "true", '"5"'])
def test_q1_max_per_call_uupt_invalid(tmp_path, bad):
    with pytest.raises(ConfigInvalid):
        load_absence_config(cfg_dir(tmp_path, f"max_per_call_uupt = {bad}"))


def test_q1_max_per_call_uupt_changes_only_uupt_key(tmp_path):
    many = [vc(k) for k in V]
    akta_out = [{"query": f"Apa nomor {i}?", "doc_id": ADOC, "alasan_kode": "data_tidak_dimuat", "alasan_teks": "x"} for i in range(5)]

    def world(sub, cdir):
        cap = Capture(many, [])
        env = mku(tmp_path, sub, default=cap)
        from backend.proposal.service import ProposalService
        ps = ProposalService(runs_dir=env.runs, butir_dir=env.butir, doc_provider=lambda d: env.docs.get(d), clock=lambda: env.epoch,
                             count_tokens=lambda t: len(t) // 3 + 1, config_dir=cdir, checker_provider=env.ps.checker_provider)
        env.app.state.proposals = env.ps = ps
        d_u = gen_ok(env)
        cap._r = responder(akta_out, [])
        d_a = gen_ok(env, family="akta", doc_id=ADOC)
        return env, cap, d_u, d_a

    e0, c0, u0, a0 = world("no", cfg_dir(tmp_path / "no"))
    e1, c1, u1, a1 = world("yes", cfg_dir(tmp_path / "yes", "max_per_call_uupt = 5"))
    k_a = ref_key(hp("v2.md"), PROPOSALU_HASH, "unanswerable", 3, "ha1", ADOC)
    assert keys(e0) == {k_a, ref_key(hp("v3.md"), PROPOSALU_HASH, "unanswerable", 3, "hu1", UDOC)}
    assert keys(e1) == {k_a, ref_key(hp("v3.md"), PROPOSALU_HASH, "unanswerable", 5, "hu1", UDOC)}
    assert (len(u0["proposals"]), len(u1["proposals"])) == (3, 5) and len(a0["proposals"]) == len(a1["proposals"]) == 3
    assert "BATAS JUMLAH USULAN: 5" in c1.inputs[0] and "BATAS JUMLAH USULAN: 3" in c1.inputs[1]
    assert "BATAS JUMLAH USULAN: 3" in c0.inputs[0]


# ============================================================================= SV5
def op_row(i, family="uupt", mode="literal", gold=((0, 5),), **over):
    r = {"id": f"OP{i}", "family": family, "query": f"op{i}", "doc_id": UDOC if family == "uupt" else ADOC,
         "gold_spans": [{"start": s, "end": e} for s, e in gold], "clean_sha256": "hu1" if family == "uupt" else "ha1", "mode": mode,
         "origin": "operator", "review_status": None, "proposal_id": None, "reference_date": None, "scene_checked": False,
         "operator_note": None, "created_at": "2026-10-27T03:18:10Z"}
    r.update(over)
    return r


def write_rows(d: Path, name: str, rows) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(b"".join(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n" for r in rows))
    return p


def test_sv5_item_validator_and_loader(tmp_path):
    ok = op_row(1, mode="tolak", gold=())
    assert ok["reference_date"] is None and item_mode_problem(ok) is None  # (a)
    d = tmp_path / "a"
    write_rows(d, "uupt.v2.jsonl", [op_row(2), ok])
    assert [r["id"] for r in load_items("uupt", d)[0]] == ["OP2", "OP1"]
    assert [r["mode"] for r in Service(runs_dir=tmp_path / "runs", butir_dir=d).items("uupt")] == ["literal", "tolak"]
    d = tmp_path / "b"  # (b) invarian gold tetap
    write_rows(d, "uupt.v2.jsonl", [op_row(2), op_row(1, mode="tolak")])
    with pytest.raises(GridRunError, match=r"mode 'tolak' requires gold_spans = \[\]"):
        load_items("uupt", d)
    k08 = next(ln for ln in (REPO_ROOT / "data/butir/uupt.v1.jsonl").read_text(encoding="utf-8").split("\n") if '"kontrol-K-08"' in ln)
    d = tmp_path / "c"
    d.mkdir()
    (d / "uupt.v2.jsonl").write_bytes((k08 + "\n").encode("utf-8"))
    assert load_items("uupt", d)[0] == [json.loads(k08)] and json.loads(k08)["gold_spans"] == []  # (c) tidak diubah
    d = tmp_path / "d"
    write_rows(d, "uupt.v2.jsonl", [op_row(1, mode="unanswerable", gold=())])
    with pytest.raises(GridRunError):
        load_items("uupt", d)
    d = tmp_path / "e"  # (e) regresi akta
    write_rows(d, "akta.v2.jsonl", [op_row(1, family="akta", mode="tolak", gold=())])
    assert len(load_items("akta", d)[0]) == 1


# ============================================================================= SV6
def test_sv6_approve_and_edit_make_uupt_tolak_items(tmp_path):
    before_repo = repo_snapshot()
    env = mku(tmp_path, u_out=[vc("V2"), vc("V5")])
    v5 = write_rows(env.butir, "uupt.v5.jsonl", [op_row(1), op_row(2, mode="parafrase")])
    g5 = file_sha(v5)
    ids = by_q(gen_ok(env))
    assert env.ps.get(ids["V2"])["absence_check"]["status"] == "ok" and env.ps.get(ids["V5"])["absence_check"]["status"] == "doubtful"
    r = env.decide(ids["V2"], approve())
    assert r.status_code == 200, r.text
    base = {"family": "uupt", "doc_id": UDOC, "clean_sha256": "hu1", "gold_spans": [], "mode": "tolak", "origin": "spark_disetujui",
            "reference_date": None, "scene_checked": False, "created_at": "2026-10-29T10:00:00Z", "operator_note": None}
    assert r.json()["item"] == {**base, "id": f"usulan-{ids['V2']}", "query": V["V2"][0], "review_status": "disetujui",
                                "proposal_id": ids["V2"]}
    v6 = env.butir / "uupt.v6.jsonl"
    g6 = file_sha(v6)
    r = env.decide(ids["V5"], {"decision": "diubah", "edited": {"query": EDIT_Q, "gold_spans": [], "mode": "tolak"}, "operator_note": None})
    assert r.status_code == 200, r.text
    assert r.json()["item"] == {**base, "id": f"usulan-{ids['V5']}", "query": EDIT_Q, "review_status": "diubah", "proposal_id": ids["V5"]}
    a = env.ps.get(ids["V5"])["absence_check"]  # dihitung ulang atas query baru (P6)
    assert (a["status"], a["reasons"], a["max_cov"]) == ("ok", [], {"num": 0, "den": 2})
    assert [t["unit_text"] for t in a["top_k"]] == [S_TEXT["S1"], S_TEXT["S2"], S_TEXT["S3"]]
    v7 = env.butir / "uupt.v7.jsonl"
    assert sorted(p.name for p in env.butir.iterdir()) == ["uupt.v5.jsonl", "uupt.v6.jsonl", "uupt.v7.jsonl"]  # bukan berkas akta
    assert (file_sha(v5), file_sha(v6)) == (g5, g6)
    for p, n in ((v6, 3), (v7, 4)):
        raw = p.read_bytes()
        assert b"\r" not in raw and raw.endswith(b"\n") and len(raw.split(b"\n")[:-1]) == n
        assert all(set(json.loads(ln)) == set(ITEM_KEYS) for ln in raw.split(b"\n")[:-1])
    items = Service(runs_dir=env.runs, butir_dir=env.butir).items("uupt")
    assert items_summary(items)["by_mode"] == {"literal": 1, "parafrase": 1, "tolak": 2}
    assert all(i["doc_id"] == UDOC for i in items)  # Item UU PT membawa doc_id (hanya GridItem yang "")
    assert repo_snapshot() == before_repo


def test_sv4_cli_prompt_lookup_failure_exit_2_no_call(tmp_path, capsys, monkeypatch):
    d = fixture_prompts(tmp_path, lambda m: m.pop("by_family_mode"))
    monkeypatch.setattr(pm, "PROMPT_DIR", d)
    rc = _cli(["unanswerable", "--family", "uupt", "--run"], tmp_path, spent=0, client_factory=no_client)
    assert rc == 2 and "config_invalid" in capsys.readouterr().err and not (tmp_path / "runs").exists()
    rc = _cli(["unanswerable", "--family", "akta", "--doc", "akta-01", "--project-only"], tmp_path, spent=0, client_factory=no_client)
    assert rc == 0 and "prompt v2 " in capsys.readouterr().out


# ============================================================================= SV17 (gerbang murni)
@pytest.mark.parametrize("spent,ok", [(585_376, True), (15_991_941, True), (15_991_942, False)])
def test_sv17_gate_numbers(spent, ok):
    from backend.proposal.gate import GateConfig, evaluate_gate, expected_cost_micros
    g = GateConfig(factor_bp=15700, batch_cap_micros=2_000_000, cumulative_cap_micros=20_000_000, cumulative_pct=80)
    exp = expected_cost_micros(47_329, 2_000, {"input": 100_000, "cached": 0, "output": 200_000})
    assert exp == 5_133  # ceil(5.132,9)
    v = evaluate_gate([exp], spent, g)  # satu panggilan per dokumen UU PT (bukan 5 seperti akta)
    assert (v.expected, v.batas_atas, v.ok) == (5_133, 8_059, ok)
    assert v.reasons == (() if ok else ("cumulative_over_threshold",))
    assert all(isinstance(x, int) and not isinstance(x, bool) for x in (v.expected, v.batas_atas, v.spent))


# ----------------------------------------------------------------------------- W86: N1 (pembulatan) dan S2 (CLI memakai batas per keluarga)
def test_n1_upper_bound_is_ceil_with_fraction_below_half():
    from backend.proposal.gate import upper_bound
    assert upper_bound(1, 12000) == 2  # 1,2 -> ceil 2 (round memberi 1)
    assert upper_bound(1, 10001) == 2 and upper_bound(10, 10000) == 10 and upper_bound(0, 12000) == 0


def _cli_projection(tmp_path, family, extra):
    from backend.proposal.__main__ import main
    cdir = cfg_dir(tmp_path, extra)  # proposals.toml fixture; sisa config disalin dari repo (Service.doc membutuhkannya)
    for f in (REPO_ROOT / "config").glob("*.toml"):
        if f.name != "proposals.toml":
            shutil.copyfile(f, cdir / f.name)
    base = Service(runs_dir=tmp_path / "runs", butir_dir=tmp_path / "butir", config_dir=cdir)
    return base, main(["unanswerable", "--family", family, "--project-only"], base=base, spent=0, client_factory=no_client)


def test_s2_cli_projects_with_max_per_call_uupt(tmp_path, capsys):
    base, rc = _cli_projection(tmp_path, "uupt", "max_per_call_uupt = 5")
    out = capsys.readouterr().out
    assert rc == 0 and "family=uupt max_per_call=5" in out
    prm = pm.prompt_for("uupt", "unanswerable")
    d = base.doc("uupt-40-2007")
    n5 = int(base.tok().count(pm.render_input(prm, d.doc_id, d.text, "unanswerable", 5, d.clean_sha256)))
    assert f"input_tokens={n5} " in out  # hitungan atas render_input(..., 5, ...); baris max_per_call=5 membedakan dari 3


def test_s2_cli_akta_keeps_max_per_call_3_with_uupt_override(tmp_path, capsys):
    base, rc = _cli_projection(tmp_path, "akta", "max_per_call_uupt = 5")
    out = capsys.readouterr().out
    assert rc == 0 and "family=akta max_per_call=3" in out and "max_per_call=5" not in out
    prm = pm.prompt_for("akta", "unanswerable")
    line = next(ln for ln in out.splitlines() if ln.startswith("  "))
    d = base.doc(line.split()[0])
    n3 = int(base.tok().count(pm.render_input(prm, d.doc_id, d.text, "unanswerable", 3, d.clean_sha256)))
    assert f"input_tokens={n3} " in line
