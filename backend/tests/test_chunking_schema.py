"""M3.4: chunker `structure_schema`, selisih batas, kunci/hash skema, grid dengan dan tanpa skema A. Dokumen mainan U
(`docs/scenarios/M1.2.md`, 201 karakter), tokenizer `toy-ws`, encoder palsu. Tanpa jaringan dan tanpa Model API."""

from __future__ import annotations

import copy

import pytest

from backend import config as bc
from backend.chunking import boundary_diff, chunk_document, chunk_schema, chunk_structure, schema_identity
from backend.chunking.model import NO_MARKER_WARNING
from backend.chunking.schema_chunker import SchemaChunkerError, schema_key
from backend.grid.schemas import SchemaBinding, bind_schema_versions, is_approved, pick_active
from backend.grid.expand import expand_grid
from backend.pipeline.grid_run import make_plan, pipeline_config_hash, run_family_grid, schema_report
from backend.pipeline.pipeline import Pipeline, SettingNotAvailable, unavailable_reason
from backend.schema_a.store import SchemaStore

from ._chunk_util import ToyWs, make_doc, u_doc
from .pipeline_fakes import FakeEncoder, toy_config_dir, write_toy_butir

PASAL = r"^###\s+Pasal\s+\d+"
AYAT = r"^\(\d+\)"
PENJ = r"^####\s+Penjelasan Pasal \d+"


def lv(order, name, parent, pattern, unit):
    return {"order": order, "name": name, "parent_order": parent, "marker_pattern": pattern, "is_chunk_unit": unit, "examples": []}


def rec(levels, default, version=1, source="spark", **extra):
    return {"family": "uupt", "schema_version": version, "source": source, **extra,
            "body": {"family": "uupt", "default_chunk_level": default, "levels": levels}}


# A: unit = Pasal (heading ikut potongan); ayat anak Pasal; penjelasan = unit sendiri
SCHEMA_A = rec([lv(1, "pasal", None, PASAL, True), lv(2, "ayat", 1, AYAT, False), lv(3, "penjelasan", None, PENJ, True)], 1)
# B: unit = ayat (hanya batang tubuh yang punya penanda ayat di baris awal); Pasal bukan unit
SCHEMA_B = rec([lv(1, "pasal", None, PASAL, False), lv(2, "ayat", 1, AYAT, True)], 2)


def spans(chunks, section=None):
    return [(c.start, c.end) for c in chunks if section is None or c.section == section]


# ---------- chunker ----------
def test_schema_a_chunks_hand_computed():
    # Batang tubuh U: Pasal 1 = [0,50) (tiga ayat tak dipecah), Pasal 2 = [52,76). Heading Pasal ikut (penandanya heading itu).
    # Penjelasan: dua unit "Penjelasan Pasal": [78,163) dan [164,200). Spasi tepi dipangkas.
    ch = chunk_schema(u_doc(), SCHEMA_A, tokenizer=ToyWs())
    assert spans(ch, "batang_tubuh") == [(0, 50), (52, 76)]
    assert spans(ch, "penjelasan_pasal") == [(78, 163), (164, 200)]
    assert all(NO_MARKER_WARNING not in c.warnings for c in ch)


def test_schema_b_ayat_unit_excludes_heading_unlike_h064():
    # Unit ayat: potongan mulai di "(1)" (offset 12), bukan di heading Pasal (H-064 hanya untuk structure_handwritten).
    # Pasal 2 tak punya ayat -> tak ada potongan; penjelasan tak punya penanda ayat di awal baris -> fallback satu potongan.
    ch = chunk_schema(u_doc(), SCHEMA_B, tokenizer=ToyWs())
    assert spans(ch, "batang_tubuh") == [(12, 24), (25, 37), (38, 50)]
    assert spans(ch, "penjelasan_pasal") == [(78, 200)]
    assert NO_MARKER_WARNING in ch[-1].warnings and NO_MARKER_WARNING not in ch[0].warnings


def test_chunks_verified_offsets_and_scope():
    doc = u_doc()
    ch = chunk_document(doc, {"chunker": "structure_schema"}, tokenizer=ToyWs(), schema_record=SCHEMA_A)
    assert all(doc.text[c.start:c.end] == doc.text[c.start:c.end].strip() for c in ch)
    assert {c.section for c in ch} <= {"batang_tubuh", "penjelasan_pasal"}
    with pytest.raises(ValueError):
        chunk_document(doc, {"chunker": "structure_schema"}, tokenizer=ToyWs())


def test_determinism_same_schema_same_chunks_and_hash():
    a1 = chunk_schema(u_doc(), SCHEMA_A, tokenizer=ToyWs())
    a2 = chunk_schema(u_doc(), copy.deepcopy(SCHEMA_A), tokenizer=ToyWs())
    assert [c.to_dict() if hasattr(c, "to_dict") else c for c in a1] == [c.to_dict() if hasattr(c, "to_dict") else c for c in a2]
    assert [c.chunk_id for c in a1] == [c.chunk_id for c in a2] and len({c.chunker_key for c in a1}) == 1
    # hash isi hanya dari `body`: catatan, versi-induk, waktu tidak mengubahnya
    noisy = {**copy.deepcopy(SCHEMA_A), "operator_note": "x", "created_at": "2026-01-01T00:00:00Z", "run_id": "r"}
    assert schema_identity(noisy)["schema_hash"] == schema_identity(SCHEMA_A)["schema_hash"]


def test_chunker_key_changes_with_schema_version_and_content():
    cfg, tok = bc.load("retrieval"), ToyWs()
    base = schema_key(cfg, SCHEMA_A, tok)
    assert schema_key(cfg, copy.deepcopy(SCHEMA_A), tok) == base
    assert schema_key(cfg, {**SCHEMA_A, "schema_version": 2}, tok) != base  # versi
    assert schema_key(cfg, SCHEMA_B, tok) != base  # isi
    edited = copy.deepcopy(SCHEMA_A)
    edited["body"]["levels"][1]["marker_pattern"] = r"^\(\d+\)\s"
    assert schema_key(cfg, edited, tok) != base  # satu pola berubah
    ids_a = {c.chunk_id for c in chunk_schema(u_doc(), SCHEMA_A, tokenizer=tok)}
    ids_e = {c.chunk_id for c in chunk_schema(u_doc(), edited, tokenizer=tok)}
    assert not ids_a & ids_e  # chunk_id memuat chunker_key


def test_bad_schema_raises():
    bad = copy.deepcopy(SCHEMA_A)
    bad["body"]["default_chunk_level"] = 9
    with pytest.raises(SchemaChunkerError):
        chunk_schema(u_doc(), bad, tokenizer=ToyWs())


# ---------- selisih batas ----------
def test_boundary_diff_hand_numbers_schema_a():
    doc, tok = u_doc(), ToyWs()
    hand = chunk_structure(doc, tokenizer=tok)
    d = boundary_diff(doc, hand, chunk_schema(doc, SCHEMA_A, tokenizer=tok))
    # batang tubuh: tangan 4 potongan (start 0,25,38,52; end 24,37,50,76); skema 2 ([0,50),[52,76)) -> sama {0,52,50,76}=4
    bt = d["sections"]["batang_tubuh"]
    assert (bt["same"], bt["hand_only"], bt["schema_only"], bt["n_chunks_hand"], bt["n_chunks_schema"]) == (4, 4, 0, 4, 2)
    assert [(e["edge"], e["offset"]) for e in bt["examples"]["hand_only"]] == [("end", 24), ("start", 25), ("end", 37), ("start", 38)]
    assert bt["examples"]["schema_only"] == []
    # penjelasan: tangan 4 ([78,123),[124,141),[142,163),[164,200)); skema 2 ([78,163),[164,200)) -> sama {78,163,164,200}=4
    pj = d["sections"]["penjelasan_pasal"]
    assert (pj["same"], pj["hand_only"], pj["schema_only"], pj["n_chunks_hand"], pj["n_chunks_schema"]) == (4, 4, 0, 4, 2)
    assert d["total"] == {"same": 8, "hand_only": 8, "schema_only": 0, "n_chunks_hand": 8, "n_chunks_schema": 4}


def test_boundary_diff_schema_only_edges_schema_b():
    doc, tok = u_doc(), ToyWs()
    d = boundary_diff(doc, chunk_structure(doc, tokenizer=tok), chunk_schema(doc, SCHEMA_B, tokenizer=tok), sections=["batang_tubuh"])
    bt = d["sections"]["batang_tubuh"]
    # tangan: start {0,25,38,52}, end {24,37,50,76}; skema B: start {12,25,38}, end {24,37,50}
    assert (bt["same"], bt["hand_only"], bt["schema_only"]) == (5, 3, 1)
    assert [(e["edge"], e["offset"]) for e in bt["examples"]["schema_only"]] == [("start", 12)]
    assert bt["examples"]["schema_only"][0]["snippet"].startswith("(1) Aaa")
    assert [(e["edge"], e["offset"]) for e in bt["examples"]["hand_only"]] == [("start", 0), ("start", 52), ("end", 76)]
    assert list(d["sections"]) == ["batang_tubuh"]


def test_boundary_diff_examples_capped():
    doc, tok = u_doc(), ToyWs()
    d = boundary_diff(doc, chunk_structure(doc, tokenizer=tok), chunk_schema(doc, SCHEMA_A, tokenizer=tok), n_examples=2)
    assert all(len(v["examples"]["hand_only"]) <= 2 for v in d["sections"].values())


# ---------- skema aktif / disetujui ----------
def test_active_and_approved_interpretation(tmp_path):
    st = SchemaStore(tmp_path)
    st.append("uupt", {"source": "spark", "body": SCHEMA_A["body"]})
    st.append("uupt", {"source": "spark", "body": SCHEMA_B["body"]})
    b = SchemaBinding.from_store(tmp_path, "uupt")
    assert b.active()["schema_version"] == 2 and not is_approved(b.active())
    st.append("uupt", {"source": "operator", "body": SCHEMA_A["body"]})
    b = SchemaBinding.from_store(tmp_path, "uupt")
    assert b.active()["schema_version"] == 3 and is_approved(b.active())  # koreksi operator menang
    assert pick_active([]) is None
    # H-075: hanya source == operator; flag operator_approved tidak punya arti, Spark tak pernah disetujui
    assert not is_approved({"source": "spark", "operator_approved": True})
    assert not is_approved({"source": "spark"}) and is_approved({"source": "operator"})
    assert is_approved({"source": "operator", "operator_approved": False})
    assert not is_approved({}) and not is_approved({"source": "agent"})  # review W19 S-1: hanya "operator" persis
    s = next(x for x in expand_grid(bc.load("grid"), "uupt") if x.chunker == "structure_schema")
    assert s.schema_version is None
    bound = bind_schema_versions([s], b)[0]
    assert bound.schema_version == 3 and bound.setting_id != s.setting_id
    assert bind_schema_versions([s], SchemaBinding("uupt", ()))[0] == s  # tanpa skema: tak berubah


# ---------- grid ----------
@pytest.fixture()
def world(tmp_path):
    doc = u_doc()
    butir = tmp_path / "butir"
    write_toy_butir(butir, doc.clean_sha256)
    return {"doc": doc, "cfg": toy_config_dir(tmp_path / "cfg"), "butir": butir, "runs": tmp_path / "runs", "emb": tmp_path / "emb"}


def grid(w, schemas=None):
    return run_family_grid("uupt", doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"], butir_dir=w["butir"], config_dir=w["cfg"],
                           encoder=FakeEncoder(), embed_cache_dir=w["emb"], schemas=schemas)


def test_grid_skips_structure_schema_without_schema(world):
    res = grid(world)
    env = res.envelope
    assert {s["chunker"] for s in env["settings_run"]} == {"structure_handwritten", "fixed_size"}
    assert any(s["chunker"] == "structure_schema" and "schema A" in s["reason"] for s in env["skipped"])
    assert (env["schemas_used"], env["schema_approved"], env["boundary_diff"]) == ([], None, {})


def test_grid_skips_when_binding_has_no_records(world):
    res = grid(world, SchemaBinding("uupt", ()))
    assert "structure_schema" not in {s["chunker"] for s in res.envelope["settings_run"]}
    assert any(s["chunker"] == "structure_schema" for s in res.envelope["skipped"])


def test_grid_runs_structure_schema_with_schema_and_marks_unapproved(world):
    res = grid(world, SchemaBinding("uupt", (SCHEMA_A,)))
    env = res.envelope
    ran = [s for s in env["settings_run"] if s["chunker"] == "structure_schema"]
    assert len(ran) == 6 and all(s["schema_version"] == 1 for s in ran)  # 3 mode x 2 anggaran, header B off
    assert not any(s["chunker"] == "structure_schema" and not s["header_b"] for s in env["skipped"])
    assert env["schema_approved"] is False
    assert [(u["schema_version"], u["source"], u["schema_approved"]) for u in env["schemas_used"]] == [(1, "spark", False)]
    assert env["schemas_used"][0]["schema_hash"] == schema_identity(SCHEMA_A)["schema_hash"]
    assert env["boundary_diff"]["1"]["total"] == {"same": 8, "hand_only": 8, "schema_only": 0, "n_chunks_hand": 8, "n_chunks_schema": 4}
    assert any(q["setting_id"] == ran[0]["setting_id"] for q in env["quality"])
    assert res.record["cost_usd_micros"] == 0


def test_grid_marks_operator_schema_approved(world):
    res = grid(world, SchemaBinding("uupt", (rec(SCHEMA_A["body"]["levels"], 1, source="operator"),)))
    assert res.envelope["schema_approved"] is True and res.envelope["schemas_used"][0]["schema_approved"] is True


def test_grid_key_changes_with_schema_but_not_without(world):
    base = make_plan("uupt", doc=world["doc"], tokenizer=ToyWs(), butir_dir=world["butir"], runs_dir=world["runs"],
                     config_dir=world["cfg"], create_split=True)
    plans = {n: make_plan("uupt", doc=world["doc"], tokenizer=ToyWs(), butir_dir=world["butir"], runs_dir=world["runs"],
                          config_dir=world["cfg"], create_split=True, schemas=SchemaBinding("uupt", (r,)))
             for n, r in (("a", SCHEMA_A), ("a2", copy.deepcopy(SCHEMA_A)), ("b", rec(SCHEMA_B["body"]["levels"], 2)),
                          ("a_v2", {**SCHEMA_A, "schema_version": 2}))}
    cfgs = {n: bc.load(n, world["cfg"]) for n in ("grid", "retrieval", "tokenizer", "corpus")}
    assert base.config_hash == pipeline_config_hash(cfgs, ToyWs().info)  # tanpa skema: hash tak berubah
    assert plans["a"].key == plans["a2"].key and plans["a"].key != base.key
    assert len({plans["a"].key, plans["b"].key, plans["a_v2"].key}) == 3  # isi dan versi skema membedakan kunci
    # skema tanpa setting structure_schema yang jalan (binding kosong) tidak mengubah hash
    empty = make_plan("uupt", doc=world["doc"], tokenizer=ToyWs(), butir_dir=world["butir"], runs_dir=world["runs"],
                      config_dir=world["cfg"], create_split=True, schemas=SchemaBinding("uupt", ()))
    assert empty.key == base.key


def test_grid_cache_hit_second_run_with_schema(world):
    b = SchemaBinding("uupt", (SCHEMA_A,))
    first, second = grid(world, b), grid(world, b)
    assert not first.cache_hit and second.cache_hit and first.key == second.key


def test_pipeline_cache_key_follows_schema_and_unavailable_reason(world):
    gcfg, rcfg = bc.load("grid", world["cfg"]), bc.load("retrieval", world["cfg"])
    s = next(x for x in expand_grid(gcfg, "uupt") if x.chunker == "structure_schema" and not x.header_b)
    b1, b2 = SchemaBinding("uupt", (SCHEMA_A,)), SchemaBinding("uupt", (SCHEMA_B,))
    p1 = Pipeline(world["doc"], tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg, schemas=b1)
    p2 = Pipeline(world["doc"], tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg, schemas=b2)
    assert p1.params(s) != p2.params(s)
    assert p1.chunk_set(s).chunker_key != p2.chunk_set(s).chunker_key
    assert unavailable_reason(s, schemas=b1) is None and "schema A" in unavailable_reason(s)
    pinned = bind_schema_versions([s], SchemaBinding("uupt", (SCHEMA_A,)))[0]
    assert "version" in unavailable_reason(type(pinned)(**{**pinned.__dict__, "schema_version": 7}), schemas=b1)
    with pytest.raises(SettingNotAvailable):
        Pipeline(world["doc"], tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg).chunk_set(s)


# ---------- W8: penutup mutan selamat W7-M34 ----------
def _key(cfg=None, record=SCHEMA_A, tok=None):
    return schema_key(cfg or bc.load("retrieval"), record, tok or ToyWs())


def test_chunker_key_covers_tokenizer_scope_impl_version_and_default_level():
    base = _key()
    other_tok = ToyWs()
    other_tok.info = type("I", (), {"name": "toy-ws", "version": "2"})()
    assert _key(tok=other_tok) != base  # versi tokenizer
    renamed = ToyWs()
    renamed.info = type("I", (), {"name": "other-tok", "version": "1"})()
    assert _key(tok=renamed) != base  # nama tokenizer
    cfg = copy.deepcopy(bc.load("retrieval"))
    cfg["scope_sections"] = list(cfg["scope_sections"]) + ["penjelasan_umum"]
    assert _key(cfg) != base  # cakupan section
    v2 = copy.deepcopy(bc.load("retrieval"))
    v2.setdefault("chunking", {})["schema_chunker_version"] = 2
    v3 = copy.deepcopy(v2)
    v3["chunking"]["schema_chunker_version"] = 3
    assert len({base, _key(v2), _key(v3)}) == 3  # versi implementasi mengalir ke kunci (bukan hardcode)
    # skema beda hanya di default_chunk_level (level 1 dan 3 sama-sama unit): hash isi dan kunci berubah
    d3 = copy.deepcopy(SCHEMA_A)
    d3["body"]["default_chunk_level"] = 3
    assert schema_identity(d3)["schema_hash"] != schema_identity(SCHEMA_A)["schema_hash"]
    assert _key(record=d3) != base


@pytest.mark.parametrize("pattern", [r"^(a+)+", r"^(a|aa)+b", r"x*", r"^("])
def test_unsafe_or_broken_marker_pattern_rejected_with_clear_error(pattern):
    # konsisten dengan validasi H-072 (compile_marker): bersarang/alternasi berkuantor, cocok string kosong, gagal kompilasi
    bad = rec([lv(1, "pasal", None, PASAL, True), lv(2, "ayat", 1, pattern, False)], 1)
    with pytest.raises(SchemaChunkerError, match=r"level 2 \(ayat\)"):
        chunk_schema(u_doc(), bad, tokenizer=ToyWs())
    with pytest.raises(SchemaChunkerError):
        chunk_document(u_doc(), {"chunker": "structure_schema"}, tokenizer=ToyWs(), schema_record=bad)


def test_multi_unit_chunk_address_is_range_and_single_unit_is_not():
    from backend.chunking.address_map import RANGE_SEP

    a = {(c.start, c.end): c.address for c in chunk_schema(u_doc(), SCHEMA_A, tokenizer=ToyWs())}
    # [0,50) memuat tiga ayat Pasal 1: rentang ayat (1) .. ayat (3); [52,76) hanya Pasal 2
    first, last = a[(0, 50)].split(RANGE_SEP)
    assert first.endswith("Pasal 1 – ayat (1)") or "ayat (1)" in first
    assert "ayat (3)" in last
    assert RANGE_SEP not in a[(52, 76)] and a[(52, 76)].endswith("Pasal 2")
    pj = a[(78, 163)].split(RANGE_SEP)
    assert len(pj) == 2 and "Ayat (1)" in pj[0] and "Ayat (3)" in pj[1]
    # unit ayat: satu potongan = satu unit, tanpa rentang
    b = {(c.start, c.end): c.address for c in chunk_schema(u_doc(), SCHEMA_B, tokenizer=ToyWs())}
    assert RANGE_SEP not in b[(12, 24)] and b[(12, 24)].endswith("ayat (1)")
    assert RANGE_SEP not in b[(38, 50)] and b[(38, 50)].endswith("ayat (3)")


def test_marker_search_does_not_leak_past_section_end():
    # Section 1 berakhir tepat sebelum "#" milik section 2. Pola "\n#" akan cocok melintasi batas bila pencarian
    # melewati akhir section -> section 1 dianggap punya penanda dan kehilangan potongan fallback-nya.
    text = "Isi satu.\n# Dua\nisi dua"
    doc = make_doc(text, [("batang_tubuh", 0, 10), ("penjelasan_pasal", 10, len(text))])
    schema = rec([lv(1, "judul", None, r"\n#", True)], 1)
    ch = chunk_schema(doc, schema, tokenizer=ToyWs())
    assert [(c.section, c.start, c.end) for c in ch] == [("batang_tubuh", 0, 9), ("penjelasan_pasal", 10, len(text))]
    assert all(NO_MARKER_WARNING in c.warnings for c in ch)


def test_boundary_diff_schema_only_examples_ordered_by_offset_and_capped():
    doc, tok = u_doc(), ToyWs()
    cj = rec([lv(1, "cj", None, r"^Cukup jelas\.", True)], 1)
    d = boundary_diff(doc, chunk_structure(doc, tokenizer=tok), chunk_schema(doc, cj, tokenizer=tok))
    pj = d["sections"]["penjelasan_pasal"]
    assert (pj["same"], pj["hand_only"], pj["schema_only"]) == (1, 7, 5)
    assert [(e["edge"], e["offset"]) for e in pj["examples"]["schema_only"]] == [
        ("start", 111), ("end", 150), ("start", 151), ("end", 187), ("start", 188)]
    capped = boundary_diff(doc, chunk_structure(doc, tokenizer=tok), chunk_schema(doc, cj, tokenizer=tok), n_examples=2)
    assert [e["offset"] for e in capped["sections"]["penjelasan_pasal"]["examples"]["schema_only"]] == [111, 150]
    assert capped["sections"]["batang_tubuh"]["schema_only"] == 0


def test_chunk_document_forwards_retrieval_cfg():
    # cakupan hanya batang_tubuh: potongan penjelasan tak boleh muncul; bila cfg tak diteruskan ke chunker, scope default
    # (batang_tubuh + penjelasan_pasal) dipakai dan verify_chunks (scope sempit) menolak.
    cfg = copy.deepcopy(bc.load("retrieval"))
    cfg["scope_sections"] = ["batang_tubuh"]
    ch = chunk_document(u_doc(), {"chunker": "structure_schema"}, tokenizer=ToyWs(), retrieval_cfg=cfg, schema_record=SCHEMA_A)
    assert {c.section for c in ch} == {"batang_tubuh"} and spans(ch) == [(0, 50), (52, 76)]


def test_schema_approved_requires_all_versions(world):
    gcfg, rcfg = bc.load("grid", world["cfg"]), bc.load("retrieval", world["cfg"])
    s = next(x for x in expand_grid(gcfg, "uupt") if x.chunker == "structure_schema" and not x.header_b)
    spark_v1 = rec(SCHEMA_A["body"]["levels"], 1)
    oper_v2 = rec(SCHEMA_B["body"]["levels"], 2, version=2, source="operator")
    b = SchemaBinding("uupt", (spark_v1, oper_v2))
    pipe = Pipeline(world["doc"], tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg, schemas=b)
    pin = lambda v: type(s)(**{**s.__dict__, "schema_version": v})  # noqa: E731
    mixed = schema_report(pipe, [pin(1), pin(2)], b)
    assert [d["schema_approved"] for d in mixed["schemas_used"]] == [False, True]
    assert mixed["schema_approved"] is False  # satu versi belum disetujui -> False (bukan any)
    assert set(mixed["boundary_diff"]) == {"1", "2"}
    assert schema_report(pipe, [pin(2)], b)["schema_approved"] is True


# ---------- H-075: persetujuan skema hanya source == operator; kunci grid tak berubah ----------
def test_h075_spark_never_approved_operator_always_approved(tmp_path):
    st = SchemaStore(tmp_path)
    for _ in range(3):
        st.append("uupt", {"source": "spark", "body": SCHEMA_A["body"]})
    b = SchemaBinding.from_store(tmp_path, "uupt")
    assert all(not is_approved(r) for r in b.records)
    assert b.describe(b.active())["schema_approved"] is False and "operator_approved" not in b.describe(b.active())
    st.append("uupt", {"source": "operator", "body": SCHEMA_A["body"], "operator_note": "v1 disetujui tanpa perubahan"})
    b = SchemaBinding.from_store(tmp_path, "uupt")
    assert is_approved(b.active()) and b.describe(b.active())["schema_approved"] is True
    assert [is_approved(r) for r in b.records] == [False, False, False, True]


def test_h075_identity_unchanged_by_approval_rule(tmp_path):
    """Identitas skema (komponen config_hash) = versi + hash isi + sumber; aturan persetujuan tak ikut."""
    st = SchemaStore(tmp_path)
    st.append("uupt", {"source": "spark", "body": SCHEMA_A["body"]})
    ident = SchemaBinding.from_store(tmp_path, "uupt").identity()
    assert set(ident) == {"family", "schema_version", "schema_hash", "source"} and ident["source"] == "spark"
