"""Penghitung golden S19 (f)(j): W6 `POST /api/families/uupt/answers` dan `/api/health` untuk profil yang ada.

Cara membuat `fixtures/s19_w6_health_golden.json` (H-103 S3 bagian C): berkas ini dan `test_s19_w6_health_golden.py` disalin ke
pohon basis bf769cf (`git archive bf769cf`), lalu `S19_DUMP=<keluaran.json> pytest backend/tests/test_s19_w6_health_golden.py`
dijalankan DI SANA (kode basis, sebelum slice). Test sesudah slice menghitung ulang dengan DAN tanpa `config/sweep.toml` di direktori
config (jalur utama tidak membacanya) dan membandingkan dengan berkas itu. Data sintetis, transport palsu."""

from __future__ import annotations

import json
from typing import Any

from .spark_fakes import Resp, body_ok
from .test_answer_api import JAWAB, URL, body
from .test_m25_w6_cli import make


def compute(svc, tmp_path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    c, tr, s = make(svc, tmp_path / "w6")
    w6: dict[str, Any] = {}
    for name in ("meta", "baseten_open", "glimmer_local", "b_only", "sweep_baseten_high"):
        r = c.post(URL, json=body(svc, model_profile=name, live=(name != "glimmer_local")))
        j = r.json()
        w6[name] = {"status": r.status_code,
                    "keys": sorted(j)[:20],
                    "error": (j.get("error") or {}).get("code"),
                    "profiles": sorted({j[k]["model_profile"] for k in ("best", "baseline") if k in j})}
    out["w6"] = w6
    c2, _, _ = make(svc, tmp_path / "health")
    h = c2.get("/api/health").json()
    out["health"] = json.loads(json.dumps(h, sort_keys=True))
    return out
