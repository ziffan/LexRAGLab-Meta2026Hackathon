"""H-100 slice A pembanding (O2): `backend.schema_a.compare_a` untuk Spark Open Baseten (Responses + strict) dan Glimmer
lokal (Chat Completions + validasi sisi klien). Nol jaringan: transport palsu, dokumen dan skema sintetis (H-007).

Uji inti G-38 "UU PT byte-identik": identitas run keluarga (SchemaBinding aktif, setting_id grid hasil bind, isi store
utama, R3 snapshot_view) tidak berubah oleh run pembanding; uji kenari membuktikan pemeriksa identitas menggigit."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import config
from backend.grid.expand import expand_grid
from backend.grid.schemas import SchemaBinding, bind_schema_versions
from backend.schema_a import SchemaStore, snapshot_view
from backend.schema_a import compare_a
from backend.spark import store as spark_store

from .m25_fakes import chat_body, env_m25, m25_model_cfg
from .spark_fakes import Clock, FakeTransport, Resp, body_ok

DOC_TEXT = {
    "uupt": "\n".join(["BAB I", "Pasal 1", "Isi satu.", "Pasal 2", "Isi dua.", "BAB II", "Pasal 3", "Isi tiga."]),
    "akta": "\n".join(["PASAL 1", "Nama dan tempat.", "PASAL 2", "Maksud dan tujuan."]),
}
DOC_ID = {"uupt": "uupt-sintetis", "akta": "akta-sintetis"}


def sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def doc(doc_id: str) -> SimpleNamespace:
    fam = "uupt" if doc_id.startswith("uupt") else "akta"
    t = DOC_TEXT[fam]
    return SimpleNamespace(doc_id=doc_id, text=t, clean_sha256=sha(t), sha256=sha("raw" + t), loader_rules_version="1")


class Tok:
    info = SimpleNamespace(name="tok-fake", version="0")

    @staticmethod
    def count(t: str) -> int:
        return len(t.split())


def body_for(family: str, **over) -> dict:
    if family == "uupt":
        b = {"family": "uupt", "default_chunk_level": 2, "notes": None, "levels": [
            {"order": 1, "name": "bab", "marker_pattern": r"^BAB [IVX]+$", "examples": ["BAB I", "BAB II"],
             "parent_order": None, "is_chunk_unit": False},
            {"order": 2, "name": "pasal", "marker_pattern": r"^Pasal \d+$", "examples": ["Pasal 1", "Pasal 3"],
             "parent_order": 1, "is_chunk_unit": True}]}
    else:
        b = {"family": "akta", "default_chunk_level": 1, "notes": None, "levels": [
            {"order": 1, "name": "pasal", "marker_pattern": r"^PASAL \d+$", "examples": ["PASAL 1", "PASAL 2"],
             "parent_order": None, "is_chunk_unit": True}]}
    b.update(over)
    return b


def seed_main_store(runs: Path) -> None:
    """Store utama seperti repo: v1 Spark (Contributor) + v2 koreksi operator per keluarga. Sintetis."""
    st = SchemaStore(runs)
    for fam in ("uupt", "akta"):
        d = doc(DOC_ID[fam])
        st.append(fam, {"source": "spark", "parent_version": None, "body": body_for(fam), "validation": [],
                        "run_id": "0" * 32, "created_at": "2026-10-27T00:00:00Z", "operator_note": None,
                        "sample": [{"doc_id": d.doc_id, "clean_sha256": d.clean_sha256}], "sample_checked": True,
                        "cache_key": "c" * 64})
        st.append(fam, {"source": "operator", "parent_version": 1, "body": body_for(fam, notes="koreksi sintetis"),
                        "validation": [], "run_id": None, "created_at": "2026-10-27T01:00:00Z",
                        "operator_note": "sintetis", "sample": [{"doc_id": d.doc_id, "clean_sha256": d.clean_sha256}],
                        "sample_checked": True, "cache_key": None})


def identity(runs: Path, family: str) -> str:
    """Identitas run keluarga yang dipakai grid/profil/R3 (G-38): skema aktif, setting_id hasil bind, isi store utama,
    snapshot R3, dan byte berkas `v*.json` tingkat atas."""
    sb = SchemaBinding.from_store(runs, family)
    settings = bind_schema_versions(expand_grid(config.load("grid"), family), sb)
    recs, diff = snapshot_view(SchemaStore(runs).list(family))
    d = runs / "schemas" / family
    files = {p.name: sha(p.read_text(encoding="utf-8")) for p in sorted(d.glob("v*.json"))}
    return sha(json.dumps({"active": sb.identity(), "settings": [s.setting_id for s in settings], "records": recs,
                           "diff": diff, "files": files}, sort_keys=True, ensure_ascii=False))


def budget(batch_cap: int = 2_000_000) -> dict:
    return {"version": 1, "dev_total_cap_micros": 10_000_000,
            "per_role_cap_micros": {r: 10_000_000 for r in ("a", "b", "c", "d", "measure")},
            "batch_gate": {"factor_bp": 15700, "batch_cap_micros": batch_cap, "cumulative_cap_micros": 20_000_000,
                           "cumulative_pct": 80}}


def model_a() -> dict:
    m = m25_model_cfg()
    for p in ("glimmer_local", "baseten_open"):
        m["profiles"][p]["roles"] = ["c", "a"]
    return m


class Run:
    def __init__(self, tmp_path: Path, *, script=None, default=None, model=None, budget_cfg=None, probe=None):
        self.runs = tmp_path / "runs"
        if not (self.runs / "schemas").exists():
            seed_main_store(self.runs)
        self.tr = FakeTransport(Clock(), script, default if default is not None else "ok")
        self.model = model or model_a()
        self.budget = budget_cfg or budget()
        self.lines: list[str] = []
        self.probe = probe or (lambda u, m: (True, "Available."))

    def __call__(self, *argv: str) -> int:
        return compare_a.main(list(argv), env=env_m25(), model_config=self.model, budget_config=self.budget,
                              runs_dir=self.runs, transport=self.tr.transport, out=self.lines.append, probe=self.probe,
                              load_doc=doc, tokenizer=Tok())


def responses(fam: str, **over) -> Resp:
    return Resp(200, body_ok(body_for(fam, **over)))


def chats(fam: str, **over) -> Resp:
    return Resp(200, chat_body(body_for(fam, **over)))


# ------------------------------------------------------------- store terpisah + identitas

@pytest.mark.parametrize("profile,mk", [("baseten_open", responses), ("glimmer_local", chats)])
def test_compare_run_saves_to_compare_store_and_family_identity_is_byte_identical(tmp_path, profile, mk):
    r = Run(tmp_path, script=[mk("uupt", notes="pembanding"), mk("akta", notes="pembanding")])
    before = {f: identity(r.runs, f) for f in ("uupt", "akta")}
    main_bytes = {p: p.read_bytes() for p in sorted((r.runs / "schemas").rglob("*.json"))}
    assert r("--model-profile", profile) == 0, r.lines
    assert r.tr.calls == 2
    for fam in ("uupt", "akta"):
        assert identity(r.runs, fam) == before[fam]  # G-38: UU PT (dan akta) byte-identik atas identitas run
        cmp = SchemaStore(r.runs, compare_profile=profile).list(fam)
        assert [c["schema_version"] for c in cmp] == [1] and cmp[0]["model_profile"] == profile
        assert cmp[0]["source"] == "spark" and cmp[0]["body"]["notes"] == "pembanding"
        assert (r.runs / "schemas" / fam / "compare" / profile / "v1.json").is_file()
        assert [x["schema_version"] for x in SchemaStore(r.runs).list(fam)] == [1, 2]  # store utama tak bertambah
    for p, b in main_bytes.items():
        assert p.read_bytes() == b  # berkas store utama tidak disentuh


def test_identity_canary_bites_when_a_record_lands_in_the_main_store(tmp_path):
    """Kenari: bila kode pembanding salah menulis ke store utama, pemeriksa identitas wajib gagal."""
    r = Run(tmp_path)
    before = identity(r.runs, "uupt")
    SchemaStore(r.runs).append("uupt", {"source": "spark", "parent_version": None, "body": body_for("uupt", notes="x"),
                                        "validation": [], "run_id": "1" * 32, "created_at": "2026-10-28T00:00:00Z",
                                        "operator_note": None, "sample": [], "sample_checked": True, "cache_key": "d" * 64})
    assert identity(r.runs, "uupt") != before


def test_compare_store_is_never_active_even_with_higher_versions(tmp_path):
    r = Run(tmp_path, script=[responses("uupt")] * 1)
    assert r("--model-profile", "baseten_open", "--family", "uupt") == 0
    cmp = SchemaStore(r.runs, compare_profile="baseten_open")
    for _ in range(3):  # versi pembanding lebih tinggi dari versi utama
        cmp.append("uupt", {**cmp.list("uupt")[0], "cache_key": None})
    act = SchemaBinding.from_store(r.runs, "uupt").active()
    assert act["schema_version"] == 2 and act["source"] == "operator"


def test_compare_profile_name_is_validated():
    for bad in ("../meta", "a/b", "", "X" * 41, "Meta"):
        with pytest.raises(ValueError):
            SchemaStore(Path("."), compare_profile=bad)


# ------------------------------------------------------------- masukan identik + identitas model

def test_input_is_byte_identical_to_contributor_request_shape(tmp_path):
    r = Run(tmp_path, script=[responses("uupt")])
    assert r("--model-profile", "baseten_open", "--family", "uupt") == 0
    from backend.schema_a import load_prompt, render_input
    want, _ = render_input(load_prompt(), "uupt", [(DOC_ID["uupt"], DOC_TEXT["uupt"])])
    rq = r.tr.requests[0]
    assert rq["path"].endswith("/responses") and rq["body"]["input"] == want
    fmt = rq["body"]["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and fmt["name"] == "SchemaA"
    assert rq["body"]["model"] == "meta-models/muse-spark-open-1026" and rq["body"]["reasoning"]["effort"] == "low"
    assert "tools" not in rq["body"]
    rec = spark_store.load_records(r.runs)[0]
    assert (rec.provider, rec.model, rec.kind, rec.effort, rec.status) == (
        "baseten", "meta-models/muse-spark-open-1026", "spark_a", "low", "ok")


def test_glimmer_uses_chat_completions_on_loopback_with_pinned_effort(tmp_path):
    r = Run(tmp_path, script=[chats("akta")])
    assert r("--model-profile", "glimmer_local", "--family", "akta") == 0
    rq = r.tr.requests[0]
    assert rq["path"].endswith("/chat/completions")
    b = rq["body"]
    assert b["response_format"]["json_schema"]["strict"] is True and b["reasoning_effort"] == "high"
    assert b["max_tokens"] == 16000 and "tools" not in b
    rec = spark_store.load_records(r.runs)[0]
    assert (rec.provider, rec.quantization, rec.effort, rec.cost_usd_micros) == ("lmstudio_local", "Q4_K_M", "high", 0)


def test_rerun_uses_cache_and_adds_no_version(tmp_path):
    r = Run(tmp_path, script=[responses("uupt")])
    assert r("--model-profile", "baseten_open", "--family", "uupt") == 0
    assert r("--model-profile", "baseten_open", "--family", "uupt") == 0
    assert r.tr.calls == 1
    assert len(SchemaStore(r.runs, compare_profile="baseten_open").list("uupt")) == 1


def test_sample_hash_mismatch_stops_before_any_call(tmp_path):
    r = Run(tmp_path)
    p = r.runs / "schemas" / "uupt" / "v1.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["sample"][0]["clean_sha256"] = "f" * 64
    p.write_text(json.dumps(rec), encoding="utf-8")
    assert r("--model-profile", "baseten_open", "--family", "uupt") == 1
    assert r.tr.calls == 0


# ------------------------------------------------------------- ulang dan gagal jujur

def test_semantic_invalid_is_retried_once_then_saved(tmp_path):
    bad = body_for("uupt")
    bad["levels"][1]["examples"] = ["Pasal 99 karangan"]  # tidak ada di sampel
    r = Run(tmp_path, script=[Resp(200, body_ok(bad)), responses("uupt")])
    assert r("--model-profile", "baseten_open", "--family", "uupt") == 0
    assert r.tr.calls == 2
    cmp = SchemaStore(r.runs, compare_profile="baseten_open")
    assert len(cmp.list("uupt")) == 1 and len(cmp.list_rejected("uupt")) == 1
    assert not (r.runs / "schemas" / "uupt" / "rejected").exists()  # rejected juga di store pembanding


def test_two_failures_are_reported_honestly_without_record(tmp_path):
    bad = {**body_for("uupt"), "family": "akta"}  # family salah
    r = Run(tmp_path, script=[Resp(200, body_ok(bad))] * 3)
    assert r("--model-profile", "baseten_open", "--family", "uupt") == 4
    assert r.tr.calls == compare_a.MAX_ATTEMPTS
    assert SchemaStore(r.runs, compare_profile="baseten_open").list("uupt") == []


def test_glimmer_timeout_is_not_retried(tmp_path):
    from .spark_fakes import Timeout
    r = Run(tmp_path, script=[Timeout()])
    assert r("--model-profile", "glimmer_local", "--family", "uupt") == 4
    assert r.tr.calls == 1


# ------------------------------------------------------------- gerbang, profil, mode tanpa jaringan

def test_project_only_makes_no_call_and_writes_nothing(tmp_path):
    r = Run(tmp_path)
    before = sorted(p.relative_to(r.runs).as_posix() for p in r.runs.rglob("*"))
    assert r("--model-profile", "baseten_open", "--project-only") == 0
    assert r.tr.calls == 0
    assert sorted(p.relative_to(r.runs).as_posix() for p in r.runs.rglob("*")) == before
    assert any(l.startswith("gate [batch_gate]") and "ok=True" in l for l in r.lines)


def test_batch_gate_rejection_blocks_before_network(tmp_path):
    r = Run(tmp_path, budget_cfg=budget(batch_cap=1))
    assert r("--model-profile", "baseten_open") == 3
    assert r.tr.calls == 0 and not (r.runs / "spark").exists()


def test_glimmer_server_down_blocks_before_call(tmp_path):
    r = Run(tmp_path, probe=lambda u, m: (False, "Local model server is not running."))
    assert r("--model-profile", "glimmer_local") == 3
    assert r.tr.calls == 0


@pytest.mark.parametrize("profile", ["meta", "openrouter_dev", "b_only", "nope"])
def test_profiles_without_role_a_or_reportable_are_rejected(tmp_path, profile):
    r = Run(tmp_path)
    assert r("--model-profile", profile) == 2
    assert r.tr.calls == 0


def test_profile_with_only_role_c_is_rejected(tmp_path):
    r = Run(tmp_path, model=m25_model_cfg())  # roles ["c"]
    assert r("--model-profile", "baseten_open") == 2


def test_diff_reports_against_contributor_and_operator(tmp_path):
    r = Run(tmp_path, script=[responses("uupt", notes="pembanding")])
    assert r("--model-profile", "baseten_open", "--family", "uupt") == 0
    r.lines.clear()
    assert r("--model-profile", "baseten_open", "--family", "uupt", "--diff") == 0
    rep = json.loads(r.lines[0])[0]
    row = rep["records"][0]
    assert row["vs_contributor"]["version"] == 1 and row["vs_operator"]["version"] == 2
    assert {c["field"] for c in row["vs_contributor"]["changed"]} == {"notes"}
    assert [c["after"] for c in row["vs_operator"]["changed"]] == ["pembanding"]


def test_real_config_profiles_allow_role_a_for_comparators_only():
    m = config.load("model")
    assert "a" in m["profiles"]["baseten_open"]["roles"] and "a" in m["profiles"]["glimmer_local"]["roles"]
    assert "b" not in m["profiles"]["baseten_open"]["roles"]  # B menunggu skenario Tier 1 (H-052, H-100)
    assert "b" not in m["profiles"]["glimmer_local"]["roles"]
    assert not m["profiles"]["meta"].get("roles")


def test_no_key_in_compare_outputs(tmp_path):
    r = Run(tmp_path, script=[responses("uupt"), responses("akta")])
    assert r("--model-profile", "baseten_open") == 0
    key = env_m25()["BASETEN_API_KEY"]
    for p in r.runs.rglob("*"):
        assert key not in p.as_posix()
        if p.is_file():
            assert key not in p.read_text(encoding="utf-8", errors="replace")
    assert all(key not in l for l in r.lines)
