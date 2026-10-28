"""W62 / S4: grid akta di R3 (`{all}`, H-091), setting + laporan transfer, label degenerate (H-093), penanda final, ekspor statis.

Dua lapis: (1) fungsi murni atas amplop tulisan tangan, angka dikunci dari hitungan tangan; (2) end-to-end lewat `Service`/`create_app`
dengan korpus akta sintetis repo (`data/akta`), butir akta SINTETIS di tmp (bukan butir evaluasi), encoder palsu, skema A akta
sintetis di store tmp. Tanpa Model API, tanpa GPU, tanpa menulis `data/` atau `runs/` repo."""

from __future__ import annotations

import json
import re
import shutil

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api.app import Service, create_app
from backend.api.routers.snapshot import grid_view, report_view
from backend.corpus import load_corpus
from backend.profile.aggregate import DEGENERATE_LABEL, TRANSFER_LABEL, transfer_setting
from backend.schema_a import SchemaStore
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder
from .test_akta_m41 import body as akta_body

SID = lambda c: c * 64  # noqa: E731


# ---------------------------------------------------------------------------------------------- lapis 1: fungsi murni
def _st(sid, chunker, mode, header, budget, ver=None):
    return {"setting_id": sid, "chunker": chunker, "retrieval_mode": mode, "header_b": header, "budget_tokens": budget,
            "schema_version": ver, "chunk_size_tokens": None, "overlap_tokens": None, "family": "x"}


UUPT_ENV = {"split": {"split_version": 1}, "settings_run": [_st(SID("u"), "fixed_size", "hybrid", False, 2000),
                                                           _st(SID("v"), "structure_schema", "bm25", True, 1000)],
            "selections": {"2000": {"setting_id": SID("u")}, "1000": {"setting_id": SID("v")}}}
AKTA_ENV = {"family": "akta", "split": None, "key": "K" * 64, "settings_run": [
    _st(SID("a"), "structure_handwritten", "hybrid", False, 2000), _st(SID("b"), "structure_schema", "hybrid", False, 2000, 3),
    _st(SID("c"), "structure_schema", "bm25", False, 2000, 3), _st(SID("d"), "fixed_size", "hybrid", False, 2000),
    _st(SID("e"), "structure_schema", "bm25", True, 1000, 3), _st(SID("f"), "structure_schema", "bm25", False, 1000, 3)],
    "selections": {}, "quality_comparison": [], "skipped": [{"setting_id": SID("z"), "budget_tokens": 2000, "reason": "r"}],
    "record": {"failed_settings": []}, "quality": [], "metrics": [],
    "points": [{"setting_id": s, "split": None, "budget_tokens": b, "header_b": h}
               for s, b, h in (("a" * 64, 2000, False), ("b" * 64, 2000, False), ("c" * 64, 2000, False), ("d" * 64, 2000, False),
                               ("e" * 64, 1000, True), ("f" * 64, 1000, False))],
    "frontiers": [{"split": None, "budget_tokens": 2000, "point_ids": ["b" * 64], "grid_run_id": "K" * 64},
                  {"split": None, "budget_tokens": 1000, "point_ids": ["f" * 64], "grid_run_id": "K" * 64}]}


def test_transfer_setting_takes_mode_header_budget_from_uupt_selection():
    t = transfer_setting(AKTA_ENV, UUPT_ENV, 2000)  # UU PT: hybrid, header off, 2000 -> akta structure_schema hybrid off 2000 = "b"
    assert t == {"setting_id": SID("b"), "chunker": "structure_schema", "schema_version": 3, "retrieval_mode": "hybrid",
                 "header_b": False, "budget_tokens": 2000, "source_setting_id": SID("u"), "label": "transfer test, no profile selection"}
    t1 = transfer_setting(AKTA_ENV, UUPT_ENV, 1000)  # UU PT: bm25, header ON, 1000 -> "e" (header-on), bukan "f"
    assert t1["setting_id"] == SID("e") and t1["header_b"] is True and t1["retrieval_mode"] == "bm25"
    assert "held" not in json.dumps(t).lower()  # H-078


@pytest.mark.parametrize("akta,uupt,budget", [
    (None, UUPT_ENV, 2000), (AKTA_ENV, None, 2000),
    (AKTA_ENV, UUPT_ENV, 777),  # UU PT tanpa pilihan pada anggaran itu
    ({**AKTA_ENV, "settings_run": AKTA_ENV["settings_run"][:1]}, UUPT_ENV, 2000),  # tak ada padanan structure_schema
    ({**AKTA_ENV, "settings_run": AKTA_ENV["settings_run"] + [_st(SID("g"), "structure_schema", "hybrid", False, 2000, 4)]}, UUPT_ENV, 2000),  # ambigu
])
def test_transfer_setting_is_none_without_exactly_one_match(akta, uupt, budget):
    assert transfer_setting(akta, uupt, budget) is None


def test_grid_view_no_split_shape_labels_and_no_uupt_keys():
    t = transfer_setting(AKTA_ENV, UUPT_ENV, 2000)
    g, _m, _q = grid_view(AKTA_ENV, 2000, None, None, t, True)
    assert set(g) == {"all", "selected", "quality_comparison", "skipped", "grid_run_id", "failed_settings", "header_scope", "transfer", "final"}
    assert set(g["all"]) == {"points", "frontier"} and "tune" not in g and "held_out" not in g
    assert [p["setting_id"] for p in g["all"]["points"]] == [SID(c) for c in "abcd"]  # hanya anggaran 2000
    assert {p["setting_id"][0]: p["label"] for p in g["all"]["points"]} == {"a": DEGENERATE_LABEL, "b": None, "c": None, "d": None}
    assert DEGENERATE_LABEL == "no structure recognized"
    assert g["all"]["frontier"]["point_ids"] == [SID("b")] and g["all"]["frontier"]["split"] is None
    assert g["selected"] is None and g["transfer"] == t and g["final"] is True and g["quality_comparison"] is None
    g1, _, _ = grid_view(AKTA_ENV, 1000, None, None, None, False)
    assert g1["transfer"] is None and g1["final"] is False and [p["label"] for p in g1["all"]["points"]] == [None, None]


def test_grid_view_uupt_shape_unchanged():
    env = {**AKTA_ENV, "family": "uupt", "split": {"split_version": 1}, "selections": {"2000": {"setting_id": SID("b")}},
           "points": [{"setting_id": SID("b"), "split": sp, "budget_tokens": 2000, "header_b": False} for sp in ("tune", "held_out")],
           "frontiers": [{"split": sp, "budget_tokens": 2000, "point_ids": [SID("b")], "grid_run_id": "K"} for sp in ("tune", "held_out")]}
    g, _, _ = grid_view(env, 2000)
    assert set(g) == {"tune", "held_out", "selected", "quality_comparison", "skipped", "grid_run_id", "failed_settings", "header_scope"}
    assert all("label" not in p for p in g["tune"]["points"] + g["held_out"]["points"])


def test_report_view_akta_highlights_transfer_setting_only_for_akta():
    items = [{"id": "i1", "origin": "operator", "mode": "literal"}, {"id": "i2", "origin": "operator", "mode": "tolak"}]
    row = {"setting_id": SID("b"), "split": None, "gold_chars": 10, "covered_gold_chars": 10, "retrieved_tokens": 20,
           "gold_tokens_retrieved": 10, "rank": 1, "parts_total": 1, "parts_hit": 1, "retrieved_chunk_ids": ["c"]}
    env = {"metrics": [{**row, "item_id": "i1"}, {**row, "item_id": "i2", "gold_chars": 0, "covered_gold_chars": 0, "gold_tokens_retrieved": 0,
                                                  "rank": None, "parts_total": 0, "parts_hit": 0}]}
    t = transfer_setting(AKTA_ENV, UUPT_ENV, 2000)
    r = report_view("akta", items, env, {"setting_id": SID("b")}, t)
    assert r["setting"] == t and r["title"] == "Transfer results"
    tolak = next(x for x in r["rows"] if x["mode"] == "tolak")  # butir wajib tolak: kolom metrik null (H-092)
    assert tolak["span_recall"] is None and tolak["token_precision"] is None and tolak["reciprocal_rank"] is None
    assert tolak["recall_at_k"] is None and tolak["fully_covered"] is None and tolak["note"] == "no gold (must abstain)"
    assert set(r["by_mode"]) >= {"literal", "parafrase", "tolak"}
    assert not re.search(r"held[- ]?out", json.dumps(r), re.I)
    assert "setting" not in report_view("akta", items, env, {"setting_id": SID("b")})  # tanpa transfer: bentuk lama
    assert "setting" not in report_view("uupt", items, {"metrics": [{**m, "split": "held_out"} for m in env["metrics"]]},
                                        {"setting_id": SID("b")}, t)  # UU PT tak pernah memuat


# ---------------------------------------------------------------------------------------------- lapis 2: end-to-end
@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("w62")
    butir = root / "butir"
    butir.mkdir()
    latest = max((config.REPO_ROOT / "data" / "butir").glob("uupt.v*.jsonl"), key=lambda p: int(re.search(r"v(\d+)", p.name).group(1)))
    shutil.copy(latest, butir / "uupt.v1.jsonl")
    rows = []
    for n, did in enumerate(("akta-01", "akta-02", "akta-03"), 1):
        d = load_corpus(did)
        i = d.text.index("Pasal 1")
        j = d.text.index("Pasal 2")
        for kind, a, b in (("literal", i, i + 90), ("parafrase", j, j + 90)):
            rows.append({"id": f"sint-{n}-{kind}", "family": "akta", "doc_id": did, "origin": "operator", "mode": kind, "clean_sha256": d.clean_sha256,
                         "gold_spans": [{"start": a, "end": b}], "query": d.text[a:b][:60]})
    rows.append({"id": "sint-tolak", "family": "akta", "doc_id": "akta-01", "origin": "operator", "mode": "tolak",
                 "clean_sha256": load_corpus("akta-01").clean_sha256, "gold_spans": [], "query": "Siapa presiden pertama Mars?"})
    (butir / "akta.v1.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
    runs = root / "runs"
    SchemaStore(runs).append("akta", {"source": "spark", "parent_version": None, "body": akta_body(), "validation": [], "run_id": None,
                                      "created_at": "2026-10-27T00:00:00Z", "operator_note": None, "sample": []})
    cfgdir = root / "config"
    shutil.copytree(config.CONFIG_DIR, cfgdir)

    def svc(**kw):
        return Service(tokenizer=get_tokenizer(), runs_dir=runs, butir_dir=butir, encoder=FakeEncoder(), embed_cache_dir=root / "emb", **kw)

    c = TestClient(create_app(svc(config_dir=cfgdir)), raise_server_exceptions=False)
    assert c.post("/api/families/uupt/grid/run", json={}).status_code == 200
    r = c.post("/api/families/akta/grid/run", json={})
    assert r.status_code == 200, r.text
    return {"root": root, "runs": runs, "cfgdir": cfgdir, "client": c, "svc": svc, "key": r.json()["cache_key"], "n_items": len(rows)}


def snap(w, family="akta", **params):
    r = w["client"].get(f"/api/families/{family}/snapshot", params=params or None)
    assert r.status_code == 200, r.text
    return r.json()


def test_r3_akta_grid_is_all_only_with_36_settings_and_degenerate_labels(world):
    d = snap(world)
    assert len(d["settings"]) == 36 and d["split"] is None
    g = d["grid"]
    assert set(g["all"]) == {"points", "frontier"} and "tune" not in g and "held_out" not in g
    assert g["all"]["frontier"]["split"] is None and g["all"]["frontier"]["budget_tokens"] == 2000 and g["all"]["frontier"]["point_ids"]
    assert g["grid_run_id"] == world["key"] and g["selected"] is None  # akta: tanpa pemilihan profil (H-054)
    by_id = {s["setting_id"]: s for s in d["settings"]}
    for p in g["all"]["points"]:
        assert p["split"] is None
        assert p["label"] == (DEGENERATE_LABEL if by_id[p["setting_id"]]["chunker"] == "structure_handwritten" else None)
    assert sum(1 for p in g["all"]["points"] if p["label"]) == 3  # tiga mode retrieval structure_handwritten; titik tidak dibuang (H-093)
    # tanpa header store: 9 titik header-off per anggaran (3 chunker x 3 mode)
    assert len(g["all"]["points"]) == len([s for s in d["settings"] if s["budget_tokens"] == 2000 and not s["header_b"]
                                           and (s["chunker"] != "structure_schema" or s["schema_version"] is not None)])
    d1 = snap(world, budget_tokens=1000)
    assert d1["grid"]["all"]["frontier"]["budget_tokens"] == 1000 and d1["grid"]["grid_run_id"] == world["key"]


def test_r3_akta_transfer_setting_follows_uupt_selection_and_report_rows(world):
    d, u = snap(world), snap(world, "uupt")
    sel = u["grid"]["selected"]["setting_id"]
    us = next(s for s in u["settings"] if s["setting_id"] == sel)
    t = d["grid"]["transfer"]
    want = next(s for s in d["settings"] if s["chunker"] == "structure_schema" and s["retrieval_mode"] == us["retrieval_mode"]
                and s["header_b"] == us["header_b"] and s["budget_tokens"] == 2000)
    assert t["setting_id"] == want["setting_id"] and t["label"] == TRANSFER_LABEL and t["source_setting_id"] == sel
    r = d["report"]
    assert r["setting"] == t and r["title"] == "Transfer results" and len(r["rows"]) == world["n_items"] == r["summary"]["n_items"]
    assert {x["split"] for x in r["rows"]} == {"Transfer"} and set(r["by_mode"]) >= {"literal", "parafrase", "tolak"}
    tolak = next(x for x in r["rows"] if x["item_id"] == "sint-tolak")
    assert tolak["mode"] == "tolak" and tolak["span_recall"] is None and tolak["token_precision"] is None
    assert tolak["reciprocal_rank"] is None and tolak["recall_at_k"] is None and tolak["fully_covered"] is None
    assert all(x["span_recall"] is not None for x in r["rows"] if x["item_id"] != "sint-tolak")
    assert not re.search(r"held[- ]?out", json.dumps({"report": r, "transfer": t}), re.I)
    assert r["by_mode"]["tolak"]["n_items"] == 1 and r["by_mode"]["tolak"]["n_gold"] == 0
    # anggaran 1000: setting transfer dari pilihan UU PT pada 1000
    d1, u1 = snap(world, budget_tokens=1000), snap(world, "uupt", budget_tokens=1000)
    assert d1["grid"]["transfer"]["budget_tokens"] == 1000 and d1["grid"]["transfer"]["source_setting_id"] == u1["grid"]["selected"]["setting_id"]


def test_final_marker_is_bound_to_grid_key(world):
    assert snap(world)["grid"]["final"] is False  # config/akta_grid_final.toml: grid_run_id kosong
    cfg = world["cfgdir"] / "akta_grid_final.toml"

    def final_with(value):
        cfg.write_text(f'version = 1\ngrid_run_id = "{value}"\n', encoding="utf-8", newline="\n")
        c = TestClient(create_app(world["svc"](config_dir=world["cfgdir"])), raise_server_exceptions=False)
        return c.get("/api/families/akta/snapshot").json()["grid"]["final"]

    try:
        assert final_with(world["key"]) is True
        assert final_with("0" * 64) is False  # kunci lain (mis. run akta baru) = belum final
        assert final_with("") is False
        cfg.unlink()  # berkas hilang = belum final, bukan galat
        c = TestClient(create_app(world["svc"](config_dir=world["cfgdir"])), raise_server_exceptions=False)
        assert c.get("/api/families/akta/snapshot").json()["grid"]["final"] is False
    finally:
        cfg.write_text('version = 1\ngrid_run_id = ""\n', encoding="utf-8", newline="\n")
    t = (config.CONFIG_DIR / "akta_grid_final.toml").read_text(encoding="utf-8")
    assert re.search(r'^grid_run_id = ""$', t, re.M)  # config repo: belum final; agen tidak mengisinya


def test_marker_file_does_not_enter_config_hash_or_uupt_key(world):
    d1 = snap(world)
    (world["cfgdir"] / "akta_grid_final.toml").write_text(f'version = 1\ngrid_run_id = "{world["key"]}"\n', encoding="utf-8", newline="\n")
    try:
        c = TestClient(create_app(world["svc"](config_dir=world["cfgdir"])), raise_server_exceptions=False)
        d2 = c.get("/api/families/akta/snapshot").json()
        assert d2["config_hash"] == d1["config_hash"] and d2["grid"]["grid_run_id"] == d1["grid"]["grid_run_id"]
    finally:
        (world["cfgdir"] / "akta_grid_final.toml").write_text('version = 1\ngrid_run_id = ""\n', encoding="utf-8", newline="\n")


def test_uupt_r3_has_no_akta_keys(world):
    u = snap(world, "uupt")
    assert set(u["grid"]) == {"tune", "held_out", "selected", "quality_comparison", "skipped", "grid_run_id", "failed_settings", "header_scope"}
    assert all("label" not in p for p in u["grid"]["tune"]["points"] + u["grid"]["held_out"]["points"])
    assert u["report"]["title"] == "Held-out results" and "setting" not in u["report"]


def test_w1_akta_replay_mode_finds_stored_envelope_without_409(world):
    svc = world["svc"]()
    app = create_app(svc, replay=True)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/families/akta/grid/run", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cached" and r.json()["cache_key"] == world["key"]
    # tanpa amplop (runs kosong): tetap 409 replay_no_stored_run
    empty = Service(tokenizer=get_tokenizer(), runs_dir=world["root"] / "kosong", butir_dir=world["root"] / "butir", encoder=FakeEncoder(),
                    embed_cache_dir=world["root"] / "emb")
    r2 = TestClient(create_app(empty, replay=True), raise_server_exceptions=False).post("/api/families/akta/grid/run", json={})
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "replay_no_stored_run"


def test_static_export_carries_akta_snapshot_and_family_list_only_with_envelope(world, tmp_path):
    from backend.replay.export import build_files
    from backend.replay.scan import scan_files

    app = create_app(world["svc"](), replay=True)
    files = build_files(app, families=("uupt", "akta"), retrieval=False, answers=False)
    fam = json.loads(files["families.json"])
    assert [f["family"] for f in fam] == ["uupt", "akta"] and fam[1]["has_grid"] is True
    akta = json.loads(files["snapshot/akta/default.json"])
    assert set(akta["grid"]["all"]) == {"points", "frontier"} and akta["report"]["setting"]["label"] == TRANSFER_LABEL
    assert any(k.startswith("docs/akta/akta-01/") and not k.endswith("_text.json") for k in files)  # potongan per setting ada
    assert scan_files(files, secrets=[], base_urls=[]) == []
    # tanpa amplop akta: snapshot tetap diekspor, tetapi tidak masuk pemilih keluarga dan tanpa potongan per setting
    bare = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "runs", butir_dir=world["root"] / "butir", encoder=FakeEncoder(),
                   embed_cache_dir=world["root"] / "emb")
    f2 = build_files(create_app(bare, replay=True), families=("uupt", "akta"), retrieval=False, answers=False)
    assert [f["family"] for f in json.loads(f2["families.json"])] == ["uupt"]
    assert json.loads(f2["snapshot/akta/default.json"])["grid"] is None
    assert not [k for k in f2 if k.startswith("docs/akta/") and not k.endswith("_text.json")]


# ---------------------------------------------------------------------------------------------- perbaikan W64
def _put_header(runs, family_sub, prompt12, name="c1"):
    d = runs / "headers" / family_sub / "pasal" / prompt12 if family_sub else runs / "headers" / "pasal" / prompt12
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text("{}", encoding="utf-8", newline="\n")


def test_header_binding_is_per_family_store_and_uupt_unchanged(tmp_path):
    from backend.pipeline.grid_run import load_header_binding

    runs = tmp_path / "runs"
    p12 = load_header_binding(runs_dir=runs).prompt_hash[:12]
    svc = Service(tokenizer=get_tokenizer(), runs_dir=runs, encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
    assert svc.header_binding("akta") is None and svc.header_binding() is None  # tanpa store
    _put_header(runs, "akta", p12)
    hb = svc.header_binding("akta")
    assert hb is not None and hb.store.headers_dir == runs / "headers" / "akta"
    assert svc.header_binding() is None  # store akta tidak membuat binding UU PT (G-38)
    _put_header(runs, "", p12, "u1")
    hu = svc.header_binding()
    assert hu is not None and hu.store.headers_dir == runs / "headers" and svc.header_binding("uupt").identity() == hu.identity()
    assert hb.identity()["store"] != hu.identity()["store"]


def test_akta_header_on_plan_uses_akta_store_identity(world, tmp_path):
    from backend.pipeline.grid_run import load_header_binding

    runs = tmp_path / "runs"
    shutil.copytree(world["runs"], runs)
    p12 = load_header_binding(runs_dir=runs).prompt_hash[:12]
    svc = Service(tokenizer=get_tokenizer(), runs_dir=runs, butir_dir=world["root"] / "butir", encoder=FakeEncoder(), embed_cache_dir=world["root"] / "emb")
    plain, _ = svc.stored_grid("akta")
    _put_header(runs, "akta", p12)
    hplan = svc.plan("akta", headers=svc.header_binding("akta"))  # stored_grid memakai rencana yang sama untuk mencari amplop header-on
    assert hplan.headers is not None and hplan.headers.store.headers_dir == runs / "headers" / "akta"
    assert hplan.key != plain.key and hplan.config_hash != plain.config_hash
    # isi store UU PT tidak mengubah kunci header-on akta
    _put_header(runs, "", p12, "u1")
    assert svc.plan("akta", headers=svc.header_binding("akta")).key == hplan.key
    assert svc.stored_grid("akta")[0].key == plain.key  # tanpa amplop header-on: jatuh ke amplop polos (perilaku lama)


def test_r2_isolates_a_broken_family(tmp_path, world):
    butir = tmp_path / "butir"
    shutil.copytree(world["root"] / "butir", butir)
    (butir / "akta.v1.jsonl").write_text('{"id":"a"}\n', encoding="utf-8", newline="\n")  # butir akta cacat
    svc = Service(tokenizer=get_tokenizer(), runs_dir=world["runs"], butir_dir=butir, encoder=FakeEncoder(), embed_cache_dir=world["root"] / "emb")
    r = TestClient(create_app(svc), raise_server_exceptions=False).get("/api/families")
    assert r.status_code == 200
    by = {x["family"]: x for x in r.json()}
    assert by["uupt"]["has_grid"] is True and "error" not in by["uupt"]
    assert by["akta"]["has_grid"] is False and by["akta"]["n_items"] == 0 and by["akta"]["error"] == "hash_mismatch"
