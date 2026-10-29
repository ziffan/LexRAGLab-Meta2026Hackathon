"""Pemeriksa potret utama S8 (M3.2-effort-sweep; kenari byte-identik jalur utama). SATU fungsi `potret()` memuat semua item S8;
`diff_items(before, after)` = himpunan item yang berubah. Data sintetis, transport palsu, tanpa jaringan (H-007).

Item: uupt_store_hash, akta_store_hash, headers_listing, grid_listing, schemas_listing (hanya berkas utama, bukan `compare/`),
snapshot_r3 (payload `grid_view` atas amplop utama), answers_main_listing, c_2x2_main, health_model_profiles, health_profiles_golden,
config_hash_main_golden, is_off_pin_table, pool_default_spent, projection_golden, gate_threshold_golden, ratelimit_golden,
w6_accept_golden, request_body_golden (per peran a/b/c/d/measure), runrecord_golden, main_reads_sweep, ledger_caller_model_cfg."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend import config as cfgmod
from backend.api.app import Service, create_app
from backend.api.errors import ApiError
from backend.api.routers import answers as answers_router
from backend.api.routers.snapshot import grid_view
from backend.answer.compare_c import stored_answers
from backend.header_b import compare as hcmp
from backend.header_b.compare_store import snapshot_main
from backend.proposal import gate as gate_mod
from backend.spark import Ledger, SparkClient, effective_caps, ratelimit
from backend.spark import budget as budget_mod
from backend.spark.runrecord import RunRecord
from backend.spark.settings import load_configs

from .m25_fakes import env_m25
from .spark_fakes import OUT_OK, Resp, Rig, body_ok, call_args
from .sweep_helpers import CONTRIB, OPEN, f3

PH = "a" * 64
PH12 = PH[:12]
ROLES = ("a", "b", "c", "d", "measure")
K0 = "k0" + "0" * 62
ITEMS = ("uupt_store_hash", "akta_store_hash", "headers_listing", "grid_listing", "schemas_listing", "snapshot_r3",
         "answers_main_listing", "c_2x2_main", "health_model_profiles", "health_profiles_golden", "config_hash_main_golden",
         "is_off_pin_table", "pool_default_spent", "projection_golden", "gate_threshold_golden", "ratelimit_golden",
         "w6_accept_golden", "request_body_golden", "runrecord_golden", "main_reads_sweep", "ledger_caller_model_cfg")


def sha(x: Any) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def tree(root: Path, *, skip: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    if not root.is_dir():
        return []
    return [(p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(root.rglob("*"))
            if p.is_file() and not any(s in p.relative_to(root).parts for s in skip)]


def put(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def k0_envelope() -> dict[str, Any]:
    pt = lambda sid, rec, tok: {"setting_id": sid, "split": "tune", "budget_tokens": 2000, "mean_span_recall": rec,  # noqa: E731
                                "mean_retrieved_tokens": tok, "dominated": False, "header_b": False}
    return {"key": K0, "family": "uupt", "kind": "grid", "settings_run": [{"setting_id": "s03", "budget_tokens": 2000, "header_b": False,
                                                                        "chunker": "fixed_size"}],
            "points": [pt("s03", 0.25, 200)], "frontiers": [{"split": "tune", "budget_tokens": 2000, "point_ids": ["s03"]}],
            "selections": {"2000": {"setting_id": "s03"}}, "quality_comparison": [], "skipped": [], "quality": [], "metrics": [],
            "record": {"failed_settings": []}}


def seed_main(R: Path) -> None:
    """Fixture S8 (diperluas): store header UU PT dan akta, grid K0 + amplop akta, skema v1/v2, dua jawaban `meta`, ledger F3."""
    for fam_dir, ids in ((R / "headers", ("CH-U1", "CH-U2", "CH-U3")), (R / "headers" / "akta", ("CH-A1", "CH-A2"))):
        for cid in ids:
            put(fam_dir / "pasal" / PH12 / f"{cid}.json", json.dumps({"chunk_id": cid, "header": f"Header {cid}", "granularity": "pasal",
                                                                      "run_id": "r1"}))
    put(R / "grid" / f"{K0}.json", json.dumps(k0_envelope(), sort_keys=True))
    put(R / "grid" / "akta-env.json", json.dumps({"key": "akta-env", "family": "akta"}))
    put(R / "schemas" / "uupt" / "v1.json", json.dumps({"schema_version": 1, "source": "spark"}))
    put(R / "schemas" / "uupt" / "v2.json", json.dumps({"schema_version": 2, "source": "operator"}))
    put(R / "schemas" / "akta" / "v1.json", json.dumps({"schema_version": 1, "source": "spark"}))
    for slot in ("best", "baseline"):
        put(R / "answers" / f"ans-meta-{slot}.json", json.dumps({"answer_id": f"ans-meta-{slot}", "item_id": "I1", "slot": slot,
                                                                 "setting_id": "s03", "model_profile": "meta",
                                                                 "output": {"status": "tolak"}}))
    f3(R)


def sweep_artifacts(R: Path) -> None:
    """Berkas yang ditulis runner sapuan (kecuali B yang dijalankan nyata): grid_compare, skema compare/, jawaban sapuan, laporan."""
    put(R / "grid_compare" / "sweep_meta_medium" / "kx.json", "{}")
    put(R / "grid_compare" / "sweep_meta_medium" / "ref-kx.json", "{}")
    put(R / "schemas" / "uupt" / "compare" / "sweep_meta_high" / "v1.json", "{}")
    put(R / "schemas" / "akta" / "compare" / "sweep_glimmer_low" / "v1.json", "{}")
    put(R / "answers" / "ans-sweep-1.json", json.dumps({"answer_id": "ans-sweep-1", "item_id": "I1", "slot": "best", "setting_id": "s03",
                                                        "model_profile": "sweep_baseten_xhigh", "output": {"status": "tolak"}}))
    put(R / "compare_report" / "c" / "sweep_baseten_xhigh.json", "{}")


def _health(model: dict, budget: dict, runs: Path) -> dict[str, Any]:
    from fastapi.testclient import TestClient
    from backend.tokenizer import get_tokenizer
    s = Service(tokenizer=get_tokenizer(), runs_dir=runs)
    app = create_app(s, env=env_m25(), model_config=model, budget_config=budget, replay=False)
    return TestClient(app, raise_server_exceptions=False).get("/api/health").json()


OLD = ("meta", "openrouter_dev", "baseten_open", "glimmer_local")


def is_off_pin_table(model: dict) -> dict[str, bool]:
    """S4(i): kasus tepi is_off_pin (satu fixture per baris), memanggil `budget.is_off_pin` HIDUP (sabotase h2 terlihat di sini)."""
    def rec(provider, mdl, quant, eff, kind="spark_b"):
        return SimpleNamespace(provider=provider, model=mdl, quantization=quant, effort=eff, kind=kind)
    m2 = json.loads(json.dumps(model))
    m2["profiles"]["twin1"] = {**m2["profiles"]["meta"], "reasoning_effort": "low"}
    m2["profiles"]["twin2"] = {**m2["profiles"]["meta"], "reasoning_effort": "high"}
    cases = {
        "1": (model, rec(None, CONTRIB, None, "medium")), "2": (model, rec("meta", CONTRIB, None, None)),
        "3": (model, rec("meta", "model-lain", None, "medium")), "4": (model, rec("meta", CONTRIB, "Q4", "medium")),
        "5": (model, rec("meta", CONTRIB, None, "medium", "grid")), "6": (model, rec("meta", CONTRIB, None, "medium", "spark_x")),
        "7a": (model, rec("meta", CONTRIB, None, "low")), "7b": (model, rec("meta", CONTRIB, None, "medium")),
        "8a": (m2, rec("meta", CONTRIB, None, "medium")), "8b": (m2, rec("meta", CONTRIB, None, "high")),
        "8c": (m2, rec("meta", CONTRIB, None, "low")), "9a": (model, rec("meta", CONTRIB, None, "low", "spark_d")),
        "9b": (model, rec("meta", CONTRIB, None, "medium", "spark_d")), "9c": (model, rec("lmstudio_local", "meta/muse-glimmer", "Q4_K_M", "high")),
        "9d": (model, rec("lmstudio_local", "meta/muse-glimmer", "Q4_K_M", "medium")),
        "9e": (model, rec("baseten", OPEN, None, "low")), "9f": (model, rec("baseten", OPEN, None, "max"))}
    return {k: bool(budget_mod.is_off_pin(r, m)) for k, (m, r) in cases.items()}


def potret(R: Path, *, model_override: dict | None = None) -> dict[str, Any]:
    """Potret SEMUA item S8 atas direktori runs `R` (ledger F3 harus ada). `model_override` dipakai sabotase (f) (profil sapuan
    digabung ke config utama yang disajikan /api/health)."""
    model, budget = load_configs()
    reads: list[str] = []
    orig_load = cfgmod.load

    def spy(name, *a, **k):
        if name == "sweep":
            reads.append(name)
        return orig_load(name, *a, **k)

    cfgmod.load = spy
    try:
        out: dict[str, Any] = {}
        snap = snapshot_main(R, PH)
        out["uupt_store_hash"], out["akta_store_hash"] = snap["uupt_store_hash"], snap["akta_store_hash"]
        out["headers_listing"] = snap["headers_listing"]
        out["grid_listing"] = tree(R / "grid")
        out["schemas_listing"] = tree(R / "schemas", skip=("compare",))
        env = json.loads((R / "grid" / f"{K0}.json").read_text(encoding="utf-8"))
        gv, metrics, quality = grid_view(env, 2000)
        out["snapshot_r3"] = sha({"grid": gv, "metrics": metrics, "quality": quality})
        meta_files = [(p.name, hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted((R / "answers").glob("*.json"))
                      if json.loads(p.read_text(encoding="utf-8")).get("model_profile") == "meta"]
        out["answers_main_listing"] = meta_files
        st = stored_answers(R / "answers", "meta")
        out["c_2x2_main"] = sorted((k[0], k[1], a["answer_id"]) for k, v in st.items() for a in v)
        h = _health(model_override or model, budget, R)
        out["health_model_profiles"] = [r["model_profile"] for r in h["model_profiles"]]
        out["health_profiles_golden"] = sha([r for r in h["model_profiles"] if r["model_profile"] in OLD])
        c0 = SparkClient("meta", model_config=model, budget_config=budget, env=env_m25(), runs_dir=R, transport=None)
        out["config_hash_main_golden"] = c0.config_hash
        out["is_off_pin_table"] = is_off_pin_table(model)
        caps = effective_caps(budget, {}, model)
        led = Ledger(R)
        out["pool_default_spent"] = led.spent_pool("meta", caps.provider_micros, model_cfg=model)
        proj = c0.project_batch([call_args(1, role="b", est_input=1000, max_output_tokens=1)])
        out["projection_golden"] = sha({k: v for k, v in proj.__dict__.items()})
        out["gate_threshold_golden"] = gate_mod.cumulative_threshold_for("meta", budget, caps.provider_micros)
        ratelimit.reset_registry()
        for prof in OLD:
            ratelimit.get_limiter(prof, "synthetic-key-123456")
        out["ratelimit_golden"] = sorted([k[0], k[1]] for k in ratelimit._registry)
        ratelimit.reset_registry()
        req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(model_config=model)))
        w6: dict[str, Any] = {}
        for name in ("meta", "baseten_open", "glimmer_local", "sweep_baseten_high"):
            try:
                w6[name] = answers_router._profile(req, name)
            except ApiError as exc:
                w6[name] = exc.status
        out["w6_accept_golden"] = w6
        import tempfile
        bodies: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as td:
            for i, role in enumerate(ROLES):
                r = Rig(Path(td) / str(i), profile="meta", model=model, budget=budget, env=env_m25(), default=Resp(200, body_ok(OUT_OK)))
                r.client.call(**call_args(0, role=role, prompt_hash="P1", schema_hash="S1", input="input-x"))
                bodies[role] = sha(r.tr.requests[0]["body"])
        out["request_body_golden"] = bodies
        rr = RunRecord(run_id="x", kind="spark_b", created_at="t", cache_key="k", corpus_hash=None, config_hash="c", clean_sha256=None,
                       loader_rules_version=None, prompt_version=None, prompt_hash=None, model="m", effort="low", tokenizer=None,
                       embedder=None, packing=None, usage_input_tokens=None, usage_cached_tokens=None, usage_output_tokens=None,
                       cost_usd_micros=1, projected_cost_usd_micros=None, latency_ms=0, host="h", device="d", provider="meta",
                       quantization=None, status="ok", error=None)
        out["runrecord_golden"] = list(rr.to_dict())
        gate = hcmp.make_gate("baseten", budget, model, None, R)
        out["ledger_caller_model_cfg"] = [gate([0], 0).spent]  # pool Baseten (make_gate); pool default meta dijaga item lain
        out["main_reads_sweep"] = len(reads)
        return out
    finally:
        cfgmod.load = orig_load


def diff_items(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    assert set(before) == set(ITEMS) == set(after), (set(before) ^ set(ITEMS))
    return {k for k in ITEMS if before[k] != after[k]}
