"""M0.1 S7-S12: key tidak bocor (T1, T7), galat jelas tanpa stack trace, higiene env dan repo, /api/health."""

import logging
import subprocess

import pytest
from fastapi.testclient import TestClient

from backend import config as cfg
from backend.app import create_app
from backend.spark import ConfigInvalid
from backend.tests.spark_fakes import (
    BASE,
    HOST,
    K2,
    K,
    Resp,
    Rig,
    Timeout,
    budget_cfg,
    call_args,
    env_ok,
    model_cfg,
    scan_exception,
    scan_result,
    scan_runs_dir,
    scan_text,
)

REPO = cfg.REPO_ROOT


def _all_clean(rig, res, caplog, capsys, with_k2=False):
    out = capsys.readouterr()
    assert scan_runs_dir(rig.runs, with_k2) == []
    assert scan_text(caplog.text, with_k2) == []
    assert scan_text(out.out + out.err, with_k2) == []
    assert scan_result(res, with_k2) == []
    assert scan_text(repr(rig.client) + str(rig.client) + repr(rig.client._s), with_k2) == []


def test_S07_401_with_reflected_key(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    body = {"error": {"message": f"Incorrect API key provided: {K}. You can find your key at https://x.invalid"}}
    rig = Rig(tmp_path, script=[Resp(401, body)])
    res = rig.client.call(**call_args(0))
    r = res.record
    assert rig.tr.calls == 1 and rig.clock.sleeps == []
    assert r.status == "error" and r.error["code"] == "invalid_api_key"
    assert "invalid api key" in r.error["message"].lower()
    assert "You can find" not in r.error["message"] and K not in r.error["message"]
    assert "Traceback" not in r.error["message"] and 'File "' not in r.error["message"] and "\n" not in r.error["message"]
    assert r.cost_usd_micros is None and r.usage_input_tokens is None and res.output is None
    assert not list((rig.runs / "spark" / "c").glob("*.json"))
    _all_clean(rig, res, caplog, capsys)


@pytest.mark.parametrize("kind", ["httpx", "builtin"])
def test_S08_timeout_exception_message_carries_headers(tmp_path, caplog, capsys, kind):
    caplog.set_level(logging.DEBUG)
    msg = f"POST {BASE}/responses timed out; headers={{'Authorization': 'Bearer {K}'}}"
    rig = Rig(tmp_path, script=[Timeout(msg, kind), Timeout(msg, kind)])
    res = rig.client.call(**call_args(0))
    r = res.record
    assert rig.tr.calls == 2
    assert all(q["timeout"]["read"] == 120 for q in rig.tr.requests)
    assert r.status == "error" and r.error["code"] == "timeout"
    assert "timeout" in r.error["message"] and "120" in r.error["message"]
    assert r.cost_usd_micros is None
    _all_clean(rig, res, caplog, capsys)


@pytest.mark.parametrize("label,status,body,text,profile,code,must,mustnot", [
    ("a_400", 400, {"error": {"message": f"Invalid effort 'max' for model; key {K}"}}, None, "meta",
     "invalid_request", "Invalid effort 'max'", K),
    ("b_404_guardrail", 404, {"error": {"message": "No endpoints found",
                                        "metadata": {"ineligibility_reasons": ["Paid model training violation (guardrail)"]}}},
     None, "openrouter_dev", "model_unavailable", "guardrail", "model not found"),
    ("c_500", 500, None, None, "meta", "model_error", "500", K),
    ("d_503", 503, None, None, "meta", "model_unavailable", "503", K),
    ("e_422_html", 422, None, "<html>Bad gateway</html>", "meta", "invalid_request", "422", "<html>"),
])
def test_S09_other_http_statuses(tmp_path, caplog, capsys, label, status, body, text, profile, code, must, mustnot):
    caplog.set_level(logging.DEBUG)
    rig = Rig(tmp_path, profile=profile, script=[Resp(status, body, text=text)])
    res = rig.client.call(**call_args(0))
    r = res.record
    assert rig.tr.calls == 1 and rig.clock.sleeps == []
    assert r.status == "error" and r.error["code"] == code
    assert must in r.error["message"] and mustnot not in r.error["message"]
    assert "JSONDecodeError" not in r.error["message"]
    assert not list((rig.runs / "spark" / "c").glob("*.json"))
    _all_clean(rig, res, caplog, capsys, with_k2=True)


def test_S10_success_path_no_leak(tmp_path, caplog, capsys, monkeypatch):
    monkeypatch.setenv("OPENAI_LOG", "debug")
    logging.getLogger().setLevel(logging.DEBUG)
    for name in ("openai", "httpx", "httpx2", "httpcore", "openai._base_client"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    caplog.set_level(logging.DEBUG)
    rig = Rig(tmp_path)
    res = rig.client.call(**call_args(0))
    assert res.record.status == "ok"
    _all_clean(rig, res, caplog, capsys)
    assert rig.tr.requests[0]["headers"]["authorization"] == "Bearer " + K  # satu-satunya tempat boleh
    for q in rig.tr.requests:
        assert K not in str(q["body"])


def test_S10_exceptions_do_not_leak(tmp_path):
    m = model_cfg()
    del m["pricing"]["meta"]
    with pytest.raises(ConfigInvalid) as ei:
        Rig(tmp_path, model=m)
    assert scan_exception(ei.value) == []
    with pytest.raises(ConfigInvalid) as ei2:
        Rig(tmp_path, env={"MUSE_API_KEY": K, "MUSE_BASE_URL": "http://" + HOST})
    assert scan_exception(ei2.value) == []


@pytest.mark.parametrize("env", [{}, {"MUSE_API_KEY": ""}, {"MUSE_API_KEY": "   "}, {"MUSE_API_KEY": "\r\n"}])
def test_S11_empty_or_missing_key_is_config_invalid(tmp_path, env):
    e = {"MUSE_BASE_URL": BASE, **env}
    with pytest.raises(ConfigInvalid) as ei:
        Rig(tmp_path, env=e)
    assert "MUSE_API_KEY" in str(ei.value) and K not in str(ei.value)
    assert not (tmp_path / "runs").exists()


def test_S11_crlf_stripped_from_header(tmp_path):
    crlf_key = K + "\r\n"
    rig = Rig(tmp_path, env=env_ok(**{"MUSE_API_KEY": crlf_key}))
    assert rig.client.call(**call_args(0)).record.status == "ok"
    auth = rig.tr.requests[0]["headers"]["authorization"]
    assert auth == "Bearer " + K and "\r" not in auth and "\n" not in auth


def test_S11_keys_not_crossed_between_profiles(tmp_path):
    rig = Rig(tmp_path)
    meta = rig.client
    dev = rig.new_client("openrouter_dev")
    meta.call(**call_args(1))
    dev.call(**call_args(2))
    assert rig.tr.requests[0]["headers"]["authorization"] == "Bearer " + K
    assert rig.tr.requests[1]["headers"]["authorization"] == "Bearer " + K2
    for q in rig.tr.requests:
        other = K2 if q["headers"]["authorization"].endswith(K) else K
        assert other not in str(q["headers"]) and other not in str(q["body"])


def _tracked_files():
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         cwd=REPO, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def test_S12_repo_hygiene_gitignore_env_example():
    lines = [ln.strip() for ln in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert ".env" in lines and ".env.*" in lines and "!.env.example" in lines
    for ln in (REPO / ".env.example").read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        name, value = s.split("=", 1)
        if "KEY" in name or "TOKEN" in name:
            assert value.strip() == "", f"{name} must be empty in .env.example"
        assert K not in value and K2 not in value


def test_S12_no_synthetic_key_in_tracked_files():
    excluded = {"backend/tests/spark_fakes.py", "docs/scenarios/M0.1.md", "docs/scenarios/M0.1.pemeriksa.md"}
    hits = []
    for rel in _tracked_files():
        if rel in excluded or rel.startswith(("_kerja/", ".venv/", "runs/")):
            continue
        p = REPO / rel
        if not p.is_file() or p.stat().st_size > 5_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if K in text or K2 in text:
            hits.append(rel)
    assert hits == []


def test_S12_health_endpoint_no_leak(tmp_path):
    app = create_app(env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE}, runs_dir=tmp_path / "runs",
                     model_config=model_cfg(), budget_config=budget_cfg())
    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    d = resp.json()
    profiles = {p["model_profile"]: p for p in d["model_profiles"]}
    assert profiles["meta"]["available"] is True and profiles["openrouter_dev"]["available"] is False
    assert profiles["meta"]["model"] == "muse-spark-1.3-contributor"
    assert d["status"] == "ok" and d["model"] == "muse-spark-1.3-contributor" and d["config_hash"]
    assert scan_text(resp.text, with_k2=True) == []
