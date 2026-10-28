"""W22: penguat test H-079 header B. rejected hanya untuk semantic_invalid, larangan maxLength liar, CLI `--smoke`. Tanpa jaringan."""

from types import SimpleNamespace

import pytest

from backend.header_b import prompt as pm
from backend.header_b.caller import make_call, rejected_dir
from backend.header_b.prompt import load_prompt
from backend.header_b.run import HeaderConfigError

from .spark_fakes import Resp, Rig, body_ok
from .test_header_b_core import MAXH, Tok, setup, units
from .test_header_b_h079 import LONG, run


# ---------------------------------------------------------------- rejected hanya untuk semantic_invalid

def _rigs(tmp_path):
    inc = body_ok({"chunk_id": "id1", "header": LONG}, status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    return {
        "http400": Rig(tmp_path / "a", default=Resp(400, {"error": {"message": "x"}})),
        "http401": Rig(tmp_path / "b", default=Resp(401, {"error": {"message": "bad key"}})),
        "http500": Rig(tmp_path / "c", default=Resp(500, {"error": {"message": "boom"}})),
        "schema_missing_header": Rig(tmp_path / "d", default=Resp(200, body_ok({"chunk_id": "id1"}))),
        "schema_extra_key": Rig(tmp_path / "e", default=Resp(200, body_ok({"chunk_id": "id1", "header": LONG, "x": 1}))),
        "not_json": Rig(tmp_path / "f", default=Resp(200, body_ok(text="bukan json"))),
        "incomplete": Rig(tmp_path / "g", default=Resp(200, inc)),
    }


def test_non_semantic_failures_have_no_rejected_output_and_never_reach_save_rejected(tmp_path, monkeypatch):
    from backend.header_b import caller
    saved = []
    real = caller._save_rejected

    def spy(*a, **k):
        saved.append(a)
        return real(*a, **k)

    monkeypatch.setattr(caller, "_save_rejected", spy)
    _r, prompt, prefix = setup(tmp_path / "s")
    kw = make_call(prompt, prefix, units()[0], Tok(), max_header_tokens=MAXH, max_output_tokens=1000, warm_max_output_tokens=777, meta={})
    for name, rig in _rigs(tmp_path).items():
        res = rig.client.call(**kw)
        assert res.output is None and res.rejected_output is None, name
        assert res.record.error is not None and res.record.error["code"] != "semantic_invalid", name
        out = run(rig, prompt, prefix, units()[:1], tmp_path / name, warm=False)
        assert out.outcomes[0].error["code"] != "semantic_invalid", name
        assert not rejected_dir(tmp_path / name / "h", "ayat", prompt).exists(), name
    assert saved == []
    rig, prompt, prefix = setup(tmp_path / "sem", header=LONG)  # kontrol positif: jalur semantik memanggilnya tepat sekali
    run(rig, prompt, prefix, units()[:1], tmp_path / "sem", warm=False)
    assert len(saved) == 1


# ---------------------------------------------------------------- validate_schema menolak maxLength liar

@pytest.mark.parametrize("prop,flag,ok", [("chunk_id", None, False), ("chunk_id", 190, False), ("header", None, False),
                                          ("header", 190, True)])
def test_validate_schema_allows_maxlength_only_on_header_with_flag(monkeypatch, prop, flag, ok):
    real = pm.header_schema

    def stray(n=None):
        sch = real(n)
        sch["properties"][prop]["maxLength"] = 190 if prop == "header" and n else 50
        return sch

    monkeypatch.setattr(pm, "header_schema", stray)
    if ok:
        pm.validate_schema(flag)
    else:
        with pytest.raises(ValueError, match="maxLength"):
            pm.validate_schema(flag)


# ---------------------------------------------------------------- CLI --smoke (_smoke)

class _Caps:
    def __init__(self, role, total):
        self.per_role_micros = {"b": role}
        self.total_micros = total


class _Ledger:
    def __init__(self, role_spent, total_spent, log):
        self.r, self.t, self.log = role_spent, total_spent, log

    def spent(self, role=None):
        self.log.append("ledger")
        return self.r if role == "b" else self.t

    def spent_pool(self, provider, caps, role=None):  # S9 (e): tanpa tabel plafon = belanja total/peran seperti `spent`
        return self.spent(role=role)


def _env(monkeypatch, *, cost=1000, role_cap=10_000, total_cap=10_000, role_spent=0, total_spent=0, status="accepted",
         error_code=None, unit_ok=True):
    from backend.header_b import __main__ as m
    log = []
    p = SimpleNamespace(prompt=load_prompt(MAXH), units=units(), source="ayat",
                        doc=SimpleNamespace(sha256="a" * 64, clean_sha256="c" * 64, loader_rules_version="x"))

    def fake_find(prep, key):
        log.append("find_unit")
        if not unit_ok:
            raise HeaderConfigError("no such unit")
        return prep.units[0]

    def fake_proj(*a, **k):
        log.append("projection")
        z = {"expected": cost, "upper_cached": cost, "upper_no_cache": cost}
        return {"source": "ayat", "units": 1, "calls": 2, "prefix_tokens": 1, "source_tokens_total": 1, "cost_usd_micros": z,
                "time": {"rpm_floor_seconds": 1, "sequential_seconds": 1, "estimated_seconds": 1}, "rpm": 1, "assumed_latency_ms": 1}

    def fake_run(client, prep, unit, **k):
        log.append("send")
        return {"status": status, "error_code": error_code, "unit": unit.key, "run_id": "r1", "header": None}

    def fake_prepare(source, **k):
        log.append("prepare")
        return p

    def fake_client(*a, **k):
        log.append("client")
        return object()

    monkeypatch.setattr(m, "prepare", fake_prepare)
    monkeypatch.setattr(m, "find_unit", fake_find)
    monkeypatch.setattr(m, "smoke_projection", fake_proj)
    monkeypatch.setattr(m, "Ledger", lambda runs: _Ledger(role_spent, total_spent, log))
    monkeypatch.setattr(m, "effective_caps", lambda b, x: _Caps(role_cap, total_cap))
    monkeypatch.setattr(m, "_client", fake_client)
    monkeypatch.setattr(m, "run_smoke", fake_run)
    return m, log


ARGS = ["--smoke", "--granularity", "ayat", "--unit", "id1"]


def test_cli_smoke_requires_known_unit(monkeypatch):
    m, log = _env(monkeypatch)
    assert m.main(["--smoke", "--granularity", "ayat"]) == 2 and "prepare" not in log and "send" not in log
    m, log = _env(monkeypatch, unit_ok=False)
    assert m.main(["--smoke", "--granularity", "ayat", "--unit", "zzz"]) == 2
    assert "send" not in log and "client" not in log and "projection" not in log


@pytest.mark.parametrize("status,code,exit_code", [("accepted", None, 0), ("accepted", "semantic_invalid", 0),
                                                    ("rejected_by_api", "invalid_request", 1),
                                                    ("inconclusive", "invalid_api_key", 4), ("whatever", None, 4)])
def test_cli_smoke_projects_and_checks_budget_before_one_send(monkeypatch, status, code, exit_code):
    m, log = _env(monkeypatch, status=status, error_code=code)
    assert m.main(ARGS) == exit_code
    assert log.index("projection") < log.index("ledger") < log.index("client") < log.index("send")
    assert log.count("send") == 1 and log.count("client") == 1


@pytest.mark.parametrize("kw", [dict(role_spent=9500), dict(total_spent=9500), dict(role_cap=999), dict(total_cap=999)])
def test_cli_smoke_over_cap_sends_nothing_exit_3(monkeypatch, capsys, kw):
    m, log = _env(monkeypatch, **kw)
    assert m.main(ARGS) == 3
    assert "projection" in log and "client" not in log and "send" not in log
    assert "budget_exceeded" in capsys.readouterr().err


def test_cli_smoke_exactly_at_cap_is_allowed(monkeypatch):
    m, log = _env(monkeypatch, role_spent=9000, total_spent=9000)
    assert m.main(ARGS) == 0 and log.count("send") == 1
