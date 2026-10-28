"""M3.2-effort-sweep S19(l)/S8(o) (pemeriksa Tier 1 A, S-2): pemanggil Ledger di luar `SparkClient`/`make_gate` dijaga NILAI, bukan
pemindaian teks. Ledger berisi rekaman off-pin sehingga mutan `model_cfg={}` (semua rekaman dianggap on-pin) mengubah hasil."""

import json
import re

from fastapi.testclient import TestClient

from backend.api.app import Service, create_app
from backend.schema_a import compare_a
from backend.tokenizer import get_tokenizer

from .h101_helpers import budget_b
from .m25_fakes import env_m25
from .spark_fakes import Clock, FakeTransport, Resp, body_ok, env_ok, model_cfg
from .sweep_helpers import CONTRIB, OPEN, syn
from .test_schema_a_compare import Run, body_for


def seed(runs, baseten=False):
    syn(runs, "b", "meta", CONTRIB, "low", 526_265)
    syn(runs, "d", "meta", CONTRIB, "low", 21_342)
    syn(runs, "b", "meta", CONTRIB, "high", 11_000_000, rid="off-meta-b")  # off-pin: bukan pool utama
    if baseten:
        syn(runs, "b", "baseten", OPEN, "low", 15_460_483)
        syn(runs, "b", "baseten", OPEN, "xhigh", 26_990_441, rid="off-bt-b")


def budget_g():
    from .h101_helpers import GATE
    from .spark_fakes import budget_cfg
    return {**budget_cfg(), "batch_gate": dict(GATE)}


def test_compare_a_gate_spent_excludes_off_pin(tmp_path):
    r = Run(tmp_path, default=Resp(200, body_ok(body_for("uupt"))))
    seed(r.runs, baseten=True)
    assert r("--model-profile", "baseten_open", "--family", "uupt", "--project-only") == 0
    gate_line = next(ln for ln in r.lines if ln.startswith("gate [batch_gate]"))
    m = re.search(r"spent=(\d+)", gate_line)
    on_pin_default = 526_265 + 21_342 + 15_460_483  # tanpa tabel plafon: semua rekaman on-pin
    assert int(m.group(1)) == on_pin_default


def test_headers_router_prerun_ignores_off_pin_role_spend(tmp_path):
    from .test_header_b_api import respond
    tr = FakeTransport(Clock(), default=respond)
    s = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "runs")
    seed(s.runs_dir)
    app = create_app(s, env=env_ok(), model_config=model_cfg(), budget_config=budget_g(), replay=False, spark_transport=tr.transport)
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.post("/api/families/uupt/headers/run", json={"doc_id": "uupt-40-2007", "granularity": "ayat", "sample": 1})
    # belanja peran b on-pin 526.265 (< cap 1.000.000); off-pin 11.000.000 TIDAK dihitung -> tidak 402
    assert resp.status_code == 200, resp.text


def test_proposal_cli_cumulative_spent_excludes_off_pin(tmp_path, capsys):
    from backend.proposal.__main__ import main
    runs = tmp_path / "runs"
    seed(runs)
    rc = main(["unanswerable", "--family", "uupt", "--project-only"], base=Service(runs_dir=runs, butir_dir=tmp_path / "butir"),
              model_cfg=model_cfg(), budget_cfg=budget_g())
    out = capsys.readouterr().out
    assert rc == 0
    assert f"cumulative_spent={526_265 + 21_342}" in out  # pool default `meta` (baseten berplafon = pool lain, off-pin keluar)


def test_header_b_cli_fakes_reject_model_cfg_none_or_empty():
    """Fake `_Ledger` di test_header_b_w22/test_h082_schema_cli menegaskan `model_cfg` berisi profil (mutan `{}` tertangkap di sana)."""
    from . import test_h082_schema_cli as a, test_header_b_w22 as b
    import pytest
    for mod in (a, b):
        led = mod._Ledger(1, 2, []) if mod is b else mod._Ledger(1, 2)
        with pytest.raises(AssertionError):
            led.spent_pool("meta", {}, "b", model_cfg={})
        led.spent_pool("meta", {}, "b", model_cfg={"sentinel": 1, **model_cfg()})
