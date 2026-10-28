"""S19 (f)(j) + kenari S8 (k)(m): W6 dan /api/health profil yang ada byte-identik dengan golden basis bf769cf, dengan dan tanpa
`config/sweep.toml` (jalur utama tidak membacanya). Pembuatan golden: lihat docstring `s19_w6_health.py`."""

import json
import os
from pathlib import Path

from backend import config as cfgmod

from .s19_w6_health import compute
from .test_answer_api import svc  # noqa: F401

FIX = Path(__file__).parent / "fixtures" / "s19_w6_health_golden.json"
H104_NEW = ("main_results_spent_usd_micros", "pool_spend")  # bidang R1 baru H-104 butir 3: tidak ada di basis bf769cf


def _basis_view(got: dict) -> dict:
    """Hasil sekarang tanpa bidang baru H-104; sisanya harus byte-identik dengan golden (golden tidak diregenerasi)."""
    out = json.loads(json.dumps(got, sort_keys=True))
    for k in H104_NEW:
        out["health"].pop(k, None)
    return out


def _assert_h104_fields(got: dict) -> None:
    h = got["health"]
    assert all(k in h for k in H104_NEW)
    pools = {p["pool"]: p["spend_usd_micros"] for p in (h["pool_spend"] or [])}
    assert "sweep" in pools and "default" in pools  # off_pin selalu diteruskan: pool sweep ada
    assert h["main_results_spent_usd_micros"] == pools["default"]  # rekaman off-pin tidak masuk default
    assert sum(pools.values()) == h["ledger_spent_usd_micros"]


def test_w6_and_health_match_basis_golden_with_and_without_sweep_file(svc, tmp_path, monkeypatch):  # noqa: F811
    got = compute(svc, tmp_path / "a")
    dump = os.environ.get("S19_DUMP")
    if dump:  # mode pembuatan golden (dijalankan di pohon basis)
        Path(dump).write_text(json.dumps(got, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        return
    want = json.loads(FIX.read_text(encoding="utf-8"))
    assert _basis_view(got) == want
    _assert_h104_fields(got)
    reads: list[str] = []
    orig = cfgmod.load
    monkeypatch.setattr(cfgmod, "load", lambda name, *a, **k: (reads.append(name), orig(name, *a, **k))[1])
    again = compute(svc, tmp_path / "b")
    assert _basis_view(again) == want and "sweep" not in reads  # spy pembacaan = 0
    _assert_h104_fields(again)
    assert want["w6"]["sweep_baseten_high"]["status"] == 400 and want["w6"]["meta"]["status"] == 200
