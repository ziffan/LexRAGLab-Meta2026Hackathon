"""H-082: CLI `_schema_main` (backend.header_b.__main__). Klien/ledger/run_headers palsu; REPO_ROOT diarahkan ke tmp_path. Tanpa jaringan."""

import json
from types import SimpleNamespace

import pytest

from backend import config
from backend.header_b import __main__ as m
from backend.header_b.caller import store_dir
from backend.header_b.prompt import load_prompt

PROMPT = load_prompt(40, "v2")
KEYS = ["s1", "s2", "s3", "s4"]


class _Caps:
    def __init__(self, role, total):
        self.per_role_micros, self.total_micros = {"b": role}, total


class _Ledger:
    def __init__(self, role_spent, total_spent):
        self.r, self.t = role_spent, total_spent

    def spent(self, role=None):
        return self.r if role == "b" else self.t

    def spent_pool(self, provider, caps, role=None, *, model_cfg=None):  # S9 (e): tanpa tabel plafon = belanja total/peran seperti `spent`
        return self.spent(role=role)


def _env(monkeypatch, tmp_path, *, expected=100, upper=100, role_cap=10_000, total_cap=10_000, role_spent=0, total_spent=0, stored=()):
    log = {"run_headers": [], "client": 0, "project_plans": []}
    units = [SimpleNamespace(key=k, address=k) for k in KEYS]
    p = SimpleNamespace(prompt=PROMPT, units=units, prefix="PFX",
                        doc=SimpleNamespace(sha256="a" * 64, clean_sha256="c" * 64, loader_rules_version="x"))
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    for k in stored:
        d = store_dir(tmp_path / "runs" / "headers", "structure_schema", PROMPT)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{k}.json").write_text(json.dumps({"chunk_id": k, "header": "H", "granularity": "structure_schema",
                                                  "prompt_version": PROMPT.version, "tokens_local": 1, "run_id": "r"}),
                                     encoding="utf-8", newline="\n")

    def fake_project_schema(prep, plan, tok, hc, mc, **k):
        log["project_plans"].append(plan)
        z = {"expected": expected, "upper_cached": upper, "upper_no_cache": upper}
        return {"chunks": plan.total, "already_stored": len(plan.stored), "to_call": len(plan.call),
                "projection": {"source": "x", "units": len(plan.call), "calls": len(plan.call), "prefix_tokens": 1,
                               "source_tokens_total": 1, "cost_usd_micros": z, "rpm": 1, "assumed_latency_ms": 1,
                               "time": {"rpm_floor_seconds": 1, "sequential_seconds": 1, "estimated_seconds": 1}}}

    def fake_run_headers(client, prompt, prefix, units, **k):
        log["run_headers"].append(list(units))
        return SimpleNamespace(outcomes=[], stopped_reason=None)

    def fake_client(*a, **k):
        log["client"] += 1
        return object()

    monkeypatch.setattr(m, "prepare", lambda source, **k: p)
    monkeypatch.setattr(m, "project_schema", fake_project_schema)
    monkeypatch.setattr(m, "run_headers", fake_run_headers)
    monkeypatch.setattr(m, "Ledger", lambda runs: _Ledger(role_spent, total_spent))
    monkeypatch.setattr(m, "effective_caps", lambda b, x: _Caps(role_cap, total_cap))
    monkeypatch.setattr(m, "_client", fake_client)
    return log


def run(sample=0, project_only=False):
    a = SimpleNamespace(sample=sample, project_only=project_only, profile=None, rpm=None)
    tok = SimpleNamespace(info=SimpleNamespace(name="t", version="1"))
    hc = {"max_header_tokens": 1, "max_output_tokens": 1, "max_consecutive_errors": 1, "warm_max_output_tokens": 1,
          "cache_guard_calls": 1, "cache_guard_min_ratio": 0.0}
    return m._schema_main(a, hc, {}, {}, tok, {})


def test_sample_limits_plan_to_first_n_chunks(monkeypatch, tmp_path):  # M8
    log = _env(monkeypatch, tmp_path)
    assert run(sample=2) == 0
    assert [u.key for u in log["project_plans"][0].call] == ["s1", "s2"]
    assert [[u.key for u in us] for us in log["run_headers"]] == [["s1", "s2"]]


def test_budget_gate_uses_upper_cached_not_expected(monkeypatch, tmp_path, capsys):  # M9
    log = _env(monkeypatch, tmp_path, expected=5_000, upper=20_000, role_cap=10_000, total_cap=10_000)
    assert run(sample=2) == 3
    assert log["run_headers"] == [] and log["client"] == 0
    assert "budget_exceeded" in capsys.readouterr().err


def test_budget_gate_total_cap_also_blocks(monkeypatch, tmp_path):
    log = _env(monkeypatch, tmp_path, expected=100, upper=500, role_cap=10_000, total_cap=1_000, total_spent=600)
    assert run(sample=2) == 3
    assert log["run_headers"] == [] and log["client"] == 0


@pytest.mark.parametrize("sample", [0, -1])
def test_live_run_without_sample_exits_2_and_calls_nothing(monkeypatch, tmp_path, sample, capsys):  # M10
    log = _env(monkeypatch, tmp_path)
    assert run(sample=sample) == 2
    assert log["run_headers"] == [] and log["client"] == 0
    assert "--sample" in capsys.readouterr().err


def test_run_headers_gets_only_plan_call_not_stored(monkeypatch, tmp_path):  # M11
    log = _env(monkeypatch, tmp_path, stored=["s2"])
    assert run(sample=4) == 0
    assert [[u.key for u in us] for us in log["run_headers"]] == [["s1", "s3", "s4"]]
    assert log["client"] == 1


def test_all_stored_makes_no_call_and_no_client(monkeypatch, tmp_path):
    log = _env(monkeypatch, tmp_path, stored=KEYS)
    assert run(sample=4) == 0
    assert log["run_headers"] == [] and log["client"] == 0


def test_project_only_writes_projection_and_creates_no_client(monkeypatch, tmp_path):
    log = _env(monkeypatch, tmp_path)
    assert run(sample=0, project_only=True) == 0
    assert log["client"] == 0 and log["run_headers"] == []
    out = tmp_path / "runs" / "headers" / "projection" / f"{m.DEFAULT_DOC}-{'c' * 12}-{PROMPT.prompt_hash[:12]}-structure_schema.json"
    assert out.is_file()
    assert json.loads(out.read_text(encoding="utf-8"))["structure_schema"]["to_call"] == 4
