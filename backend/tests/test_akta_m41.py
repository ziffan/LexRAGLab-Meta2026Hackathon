"""M4.1: keluarga akta dimuat, R2/R3/R4 akta tanpa grid, chunker skema akta dengan skema sintetis, alamat dari skema,
keterpisahan store skema per keluarga, W2 akta lewat transport palsu, proyeksi biaya induksi A akta.
Tanpa jaringan dan tanpa Model API. Skema sintetis (bukan isi koreksi operator, H-037)."""

from __future__ import annotations

import hashlib
import json
import re

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api.app import Service, create_app
from backend.api.errors import ApiError
from backend.chunking import SchemaChunkerError, chunk_document, chunk_schema, schema_address_fn
from backend.chunking.model import NO_MARKER_WARNING
from backend.corpus import CorpusError, load_corpus
from backend.schema_a import SampleDoc, SchemaStore, load_prompt, make_call
from backend.tokenizer import get_tokenizer

from ._chunk_util import ToyWs
from .spark_fakes import Rig
from .test_schema_a_api import make as make_w2

DEEDS = [f"akta-0{i}" for i in range(1, 6)]
DATA = config.REPO_ROOT / "data" / "akta"
PASAL = r"^Pasal \d+$"


def lv(order, name, parent, pattern, unit, examples):
    return {"order": order, "name": name, "parent_order": parent, "marker_pattern": pattern, "is_chunk_unit": unit, "examples": examples}


def body(default=2, huruf_unit=False, ayat_unit=False):
    """Skema akta sintetis: penanda bagian (ANGGARAN DASAR / PENUTUP) setara Pasal (akar), supaya PENUTUP menghentikan Pasal terakhir;
    Pasal > ayat > huruf."""
    return {"family": "akta", "default_chunk_level": default, "notes": None, "levels": [
        lv(1, "bagian", None, r"^(ANGGARAN DASAR|PENUTUP)$", False, ["ANGGARAN DASAR", "PENUTUP"]),
        lv(2, "Pasal", None, PASAL, True, ["Pasal 1", "Pasal 3"]),
        lv(3, "ayat", 2, r"^\(\d+\)", ayat_unit, ["(2) Untuk mencapai maksud dan tujuan tersebut"]),
        lv(4, "huruf", 3, r"^[a-z]\.", huruf_unit, ["a. perdagangan besar hasil bumi"])]}


def record(b=None, version=1):
    return {"family": "akta", "schema_version": version, "source": "spark", "parent_version": None, "body": b or body()}


def chunks_of(doc, rec):
    return chunk_document(doc, {"chunker": "structure_schema"}, tokenizer=ToyWs(), schema_record=rec)


@pytest.fixture(scope="module")
def docs():
    return {i: load_corpus(i) for i in DEEDS}


# ---------------------------------------------------------------- pemuat
def test_loader_hash_clean_text_and_disclaimer(docs):
    cfg = {d["doc_id"]: d for d in config.load("corpus_akta")["documents"]}
    disclaimer = config.load("corpus_akta")["loader_akta"]["disclaimer"]
    for i, d in docs.items():
        raw = (DATA / f"{i}.txt").read_bytes()
        assert d.family == "akta" and d.sha256 == hashlib.sha256(raw).hexdigest() == cfg[i]["sha256"]
        assert d.clean_sha256 == hashlib.sha256(d.text.encode("utf-8")).hexdigest() and d.char_count == len(d.text)
        assert d.path == f"akta/{i}.txt" and d.loader_rules_version == "akta-1"
        assert "SINTETIS" not in d.text and d.text.endswith("\n") and not d.text.endswith("\n\n") and "\r" not in d.text
        assert d.metadata["disclaimer"] == disclaimer and d.metadata["address_prefix"] == f"Akta 0{i[-1]}"
        assert d.sections == [{"section": "batang_tubuh", "start": 0, "end": len(d.text)}] and d.annotations == []
    assert len({d.clean_sha256 for d in docs.values()}) == 5


def test_loader_is_deterministic_and_maps_back_to_raw(docs):
    for i, d in docs.items():
        assert load_corpus(i).clean_sha256 == d.clean_sha256
        raw = (DATA / f"{i}.txt").read_bytes().decode("utf-8")
        shift = d.metadata["raw_offset_shift"]
        assert raw[shift:shift + len(d.text) - 1] == d.text[:-1]  # offset mentah = offset bersih + shift
        assert raw[:shift].strip() == d.metadata["disclaimer"]
        raw_lines = raw.split("\n")
        for off, ln in d.line_map:
            assert raw_lines[ln - 1] == d.text[off:d.text.index("\n", off)]
        assert d.line_map[0][1] == 3 and [o for o, _ in d.line_map] == sorted(o for o, _ in d.line_map)


def test_loader_rejections(tmp_path):
    raw = (DATA / "akta-01.txt").read_bytes()

    def put(name, data):
        p = tmp_path / name
        p.write_bytes(data)
        return p

    with pytest.raises(CorpusError) as e:
        load_corpus("akta-01", path=put("a.txt", raw.replace(b"Pasal 1", b"Pasal 9", 1)))
    assert e.value.code == "R2" and "expected" in str(e.value)
    with pytest.raises(CorpusError) as e:
        load_corpus("akta-01", path=put("b.txt", raw.replace(b"\n", b"\r\n")))
    assert e.value.code == "R3"
    with pytest.raises(CorpusError) as e:
        load_corpus("akta-01", path=put("c.txt", b"\xef\xbb\xbf" + raw))
    assert e.value.code == "R4"
    with pytest.raises(CorpusError) as e:
        load_corpus("akta-01", path=put("d.txt", b""))
    assert e.value.code == "R1"
    with pytest.raises(CorpusError) as e:
        load_corpus("akta-01", path=tmp_path / "tidak-ada.txt")
    assert e.value.code == "R1"
    with pytest.raises(CorpusError) as e:
        load_corpus("akta-01", path=put("e.txt", b"\n".join(raw.split(b"\n")[2:])), verify_hash=False)
    assert e.value.code == "R12" and "disclaimer" in str(e.value)
    with pytest.raises(CorpusError) as e:
        load_corpus("akta-01", path=put("f.txt", raw.split(b"\n")[0] + b"\n\n\n"), verify_hash=False)
    assert e.value.code == "R12"
    with pytest.raises(CorpusError) as e:
        load_corpus("akta-99")
    assert e.value.code == "R1" and "not listed" in str(e.value)


def test_uupt_loading_is_unchanged_by_deed_config():
    d = load_corpus()
    assert d.doc_id == "uupt-40-2007" and d.family == "uupt" and d.loader_rules_version == "1"
    # corpus.toml ikut hash config run grid: akta sengaja di berkas lain agar kunci run UU PT tersimpan tak berubah
    assert {x["family"] for x in config.load("corpus")["documents"]} == {"uupt"}


# ---------------------------------------------------------------- R2 / R3 / R4
@pytest.fixture()
def client(tmp_path):
    # butir kosong di tmp: test ini mengunci perilaku "tanpa butir akta", lepas dari data/butir repo (akta v2+ sudah ada, db3d192)
    (tmp_path / "butir_kosong").mkdir()
    svc = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "runs", butir_dir=tmp_path / "butir_kosong")
    return TestClient(create_app(svc), raise_server_exceptions=False), svc


def test_r2_families_lists_deed(client, tmp_path, docs):
    c, _ = client
    r = c.get("/api/families")
    assert r.status_code == 200
    by = {x["family"]: x for x in r.json()}
    assert set(by) == {"uupt", "akta"}
    assert by["akta"] == {"family": "akta", "n_docs": 5, "n_items": 0, "has_grid": False}
    assert by["uupt"]["n_docs"] == 1 and by["uupt"]["n_items"] >= 0
    butir = tmp_path / "butir"
    butir.mkdir()
    rows = [{"id": i, "family": "akta", "origin": "operator", "mode": "literal", "doc_id": "akta-01", "query": "q", "gold_spans": [],
             "clean_sha256": docs["akta-01"].clean_sha256} for i in ("a", "b")]  # sejak W62 R2 akta menghitung rencana grid: baris harus sah
    (butir / "akta.v1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
    c2 = TestClient(create_app(Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "r2", butir_dir=butir)))
    assert {x["family"]: x["n_items"] for x in c2.get("/api/families").json()}["akta"] == 2


def test_r3_snapshot_akta_without_grid(client, docs):
    c, _ = client
    r = c.get("/api/families/akta/snapshot")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["family"] == "akta" and j["grid"] is None and j["items"] == [] and j["split"] is None
    assert len(j["settings"]) == 36 and j["metrics"] == [] and j["schemas"] == []  # grid akta = seluruh config/grid (H-091); belum ada amplop
    assert [d["doc_id"] for d in j["corpus"]] == DEEDS
    for d in j["corpus"]:
        assert d["clean_sha256"] == docs[d["doc_id"]].clean_sha256 and d["family"] == "akta" and "text" not in d
    assert c.get("/api/families/uupt/snapshot").json()["corpus"][0]["doc_id"] == "uupt-40-2007"


def test_r4_doc_akta(client, docs):
    c, _ = client
    r = c.get("/api/families/akta/docs/akta-03")
    assert r.status_code == 200
    assert r.json() == {"doc_id": "akta-03", "text": docs["akta-03"].text, "chunks": None, "headers": None}
    assert c.get("/api/families/akta/docs/akta-03", params={"setting_id": "x" * 64}).status_code == 404  # akta belum punya setting grid
    assert c.get("/api/families/akta/docs/uupt-40-2007").status_code == 404
    assert c.get("/api/families/uupt/docs/akta-01").status_code == 404
    assert c.get("/api/families/akta/docs/akta-77").status_code == 404


# ---------------------------------------------------------------- chunker skema akta
def test_schema_chunks_pasal_unit_addresses_and_determinism(docs):
    for i, d in docs.items():
        a = chunks_of(d, record())
        assert [c.to_dict() for c in a] == [c.to_dict() for c in chunks_of(d, record())]
        nums = re.findall(r"(?m)^Pasal (\d+)$", d.text)
        assert [c.address for c in a] == [f"Akta 0{i[-1]} › Pasal {n}" for n in nums]
        assert all(c.section == "batang_tubuh" and not c.warnings for c in a)
        assert "PENUTUP" not in d.text[a[-1].start:a[-1].end]  # penanda bagian (bukan turunan Pasal) menghentikan potongan
        assert d.text[a[0].start:a[0].end].startswith("Pasal 1")
        assert all("SINTETIS" not in d.text[c.start:c.end] for c in a)


def test_schema_chunks_ayat_and_huruf_addresses(docs):
    d = docs["akta-01"]
    by_ayat = chunks_of(d, record(body(default=3, ayat_unit=True)))
    addr = [c.address for c in by_ayat]
    for n in (1, 2, 3):
        assert f"Akta 01 › Pasal 3 › ayat ({n})" in addr
    assert all(c.address_levels[:2] == [{"level": "peraturan", "label": "Akta 01"}, {"level": "section", "label": "batang_tubuh"}]
               for c in by_ayat)
    two = next(c for c in by_ayat if c.address == "Akta 01 › Pasal 3 › ayat (2)")
    assert d.text[two.start:two.end].startswith("(2) Untuk mencapai maksud")
    assert "a. perdagangan besar hasil bumi" in d.text[two.start:two.end]  # huruf bukan unit: tetap di dalam ayat
    assert two.address_levels[-2:] == [{"level": "pasal", "label": "Pasal 3"}, {"level": "ayat", "label": "ayat (2)"}]
    by_huruf = chunks_of(d, record(body(default=4, huruf_unit=True)))
    h = next(c for c in by_huruf if d.text[c.start:c.end].startswith("a. perdagangan besar"))
    assert h.address == "Akta 01 › Pasal 3 › ayat (2) › huruf a"
    assert [c.address for c in by_huruf if c.address.startswith("Akta 01 › Pasal 3 › ayat (2)")] == [
        f"Akta 01 › Pasal 3 › ayat (2) › huruf {x}" for x in "abc"]


def test_schema_address_ranges_and_fallback(docs):
    d = docs["akta-01"]
    fn = schema_address_fn(d, record())
    p1 = d.text.index("\nPasal 1\n") + 1
    p3 = d.text.index("\nPasal 3\n") + 1
    a, levels, warns = fn(p1, p3 + 20, "batang_tubuh")
    assert a == "Akta 01 › Pasal 1 – Akta 01 › Pasal 3" and warns == []
    assert levels == [{"level": "peraturan", "label": "Akta 01"}, {"level": "section", "label": "batang_tubuh"}]
    assert fn(p1, p1 + 8, "batang_tubuh")[0] == "Akta 01 › Pasal 1"
    assert fn(0, 10, "batang_tubuh")[0] == "Akta 01 › Batang Tubuh"  # kepala akta: belum ada penanda
    # skema yang tak cocok di mana pun: satu potongan per section dengan peringatan, alamat tingkat bagian
    nomatch = record()
    nomatch["body"]["levels"] = [lv(1, "Klausul", None, r"^KLAUSUL \d+$", True, ["KLAUSUL 1"])]
    nomatch["body"]["default_chunk_level"] = 1
    ch = chunks_of(d, nomatch)
    assert len(ch) == 1 and ch[0].warnings == [NO_MARKER_WARNING] and ch[0].address == "Akta 01 › Batang Tubuh"
    assert (ch[0].start, ch[0].end) == (0, len(d.text) - 1)


def test_schema_chunk_ids_change_with_schema_and_doc(docs):
    a = chunks_of(docs["akta-01"], record())
    b = chunks_of(docs["akta-01"], record(body(default=3, ayat_unit=True)))
    assert not ({c.chunker_key for c in a} & {c.chunker_key for c in b})
    assert {x.chunk_id for x in a}.isdisjoint({x.chunk_id for x in chunks_of(docs["akta-02"], record())})


def test_schema_chunker_rejects_unsafe_pattern(docs):
    bad = record()
    bad["body"]["levels"][1]["marker_pattern"] = r"^(a+)+$"
    with pytest.raises(SchemaChunkerError):
        chunk_schema(docs["akta-01"], bad, tokenizer=ToyWs())


# ---------------------------------------------------------------- store skema per keluarga + W2 akta
def test_schema_store_is_separate_per_family(tmp_path):
    st = SchemaStore(tmp_path / "runs")
    uu = {"source": "spark", "parent_version": None, "body": {"family": "uupt", "levels": [], "default_chunk_level": 1, "notes": None},
          "validation": [], "run_id": None, "created_at": "2026-10-27T00:00:00Z", "operator_note": None, "sample": []}
    ak = {**uu, "body": body()}
    assert st.append("uupt", uu)["schema_version"] == 1
    assert st.append("akta", ak)["schema_version"] == 1  # penomoran versi tidak berbagi
    assert st.append("akta", ak)["schema_version"] == 2
    assert st.versions("uupt") == [1] and st.versions("akta") == [1, 2]
    assert (tmp_path / "runs" / "schemas" / "uupt" / "v1.json").is_file() and (tmp_path / "runs" / "schemas" / "akta" / "v2.json").is_file()
    assert st.get("uupt", 1)["family"] == "uupt" and st.get("akta", 1)["family"] == "akta" and st.get("uupt", 2) is None
    assert [r["family"] for r in st.list("akta")] == ["akta", "akta"]


def test_w2_induce_akta_with_fake_client_then_chunks(tmp_path):
    c, tr, _svc = make_w2(tmp_path, body(), docs=[load_corpus("akta-01")])
    r = c.post("/api/families/akta/schemas/induce", json={"sample_doc_ids": ["akta-01"]})
    assert r.status_code == 200, r.text
    rec = r.json()["schema_record"]
    assert rec["family"] == "akta" and rec["schema_version"] == 1 and rec["source"] == "spark" and tr.calls == 1
    assert all(v["matched"] for v in rec["validation"])
    assert (tmp_path / "runs" / "schemas" / "akta" / "v1.json").is_file()
    assert not (tmp_path / "runs" / "schemas" / "uupt").exists()
    # skema -> potongan -> alamat lewat layanan nyata (jalur yang sama dengan R4/grid nanti)
    svc = Service(tokenizer=ToyWs(), runs_dir=tmp_path / "runs")
    ch = svc.schema_chunks(svc.doc("akta-01"), 1)
    assert [x["address"] for x in ch][:3] == ["Akta 01 › Pasal 1", "Akta 01 › Pasal 2", "Akta 01 › Pasal 3"]
    with pytest.raises(ApiError) as e:
        svc.schema_chunks(svc.doc("akta-01"), 2)
    assert e.value.code == "not_found"
    # R3 akta menampilkan skema akta; UU PT tidak
    cl = TestClient(create_app(svc), raise_server_exceptions=False)
    assert [s["schema_version"] for s in cl.get("/api/families/akta/snapshot").json()["schemas"]] == [1]
    assert cl.get("/api/families/uupt/snapshot").json()["schemas"] == []


def test_w2_induce_akta_rejects_example_not_in_sample(tmp_path):
    bad = body()
    bad["levels"][1]["examples"] = ["Pasal 999"]  # tidak ada di sampel
    c, _tr, _ = make_w2(tmp_path, bad, docs=[load_corpus("akta-01")])
    r = c.post("/api/families/akta/schemas/induce", json={"sample_doc_ids": ["akta-01"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "schema_invalid"
    assert not (tmp_path / "runs" / "schemas" / "akta" / "v1.json").exists()
    assert len(SchemaStore(tmp_path / "runs").list_rejected("akta")) == 1


# ---------------------------------------------------------------- proyeksi biaya induksi A akta (tanpa panggilan)
def test_projection_of_induction_a_makes_no_call(tmp_path, docs):
    rig = Rig(tmp_path)
    prompt = load_prompt()
    tok = get_tokenizer()
    out = {}
    for label, ids in (("one", ["akta-01"]), ("all", DEEDS)):
        samples = [SampleDoc(i, docs[i].text, docs[i].clean_sha256) for i in ids]
        meta = {"corpus_hash": "x", "clean_sha256": "y", "loader_rules_version": "akta-1",
                "tokenizer": {"name": tok.info.name, "version": tok.info.version}}
        call = make_call(prompt, "akta", samples, tok.count, meta)
        proj = rig.client.project_batch([call])
        pr = rig.model["pricing"]["meta"]
        want = (call["est_input"] * pr["input_per_mtok_micros"] + call["max_output_tokens"] * pr["output_per_mtok_micros"]) // 1_000_000
        assert proj.verdict == "ok" and proj.total_micros > 0 and abs(proj.total_micros - want) <= 1
        out[label] = (call["est_input"], call["max_output_tokens"], proj.total_micros)
    assert out["all"][0] > out["one"][0] and out["all"][2] > out["one"][2]
    assert rig.tr.calls == 0


# ---------------------------------------------------------------- W12: NIT
def test_schema_address_range_end_exactly_at_next_marker(docs):
    d = docs["akta-01"]
    fn = schema_address_fn(d, record())
    p1 = d.text.index("\nPasal 1\n") + 1
    p2 = d.text.index("\nPasal 2\n") + 1  # end eksklusif tepat di penanda berikutnya: Pasal 2 bukan bagian rentang
    assert fn(p1, p2, "batang_tubuh")[0] == "Akta 01 › Pasal 1"
    assert fn(p1, p2 + 1, "batang_tubuh")[0] == "Akta 01 › Pasal 1 – Akta 01 › Pasal 2"


def test_loader_trims_trailing_blank_lines(tmp_path):
    raw = (DATA / "akta-01.txt").read_bytes()
    base = load_corpus("akta-01")
    padded = tmp_path / "pad.txt"
    padded.write_bytes(raw.rstrip(b"\n") + b"\n\n\n\n")
    d = load_corpus("akta-01", path=padded, verify_hash=False)
    assert d.text == base.text and d.text.endswith("\n") and not d.text.endswith("\n\n")
    assert d.clean_sha256 == base.clean_sha256 and d.char_count == base.char_count and d.sections == base.sections
