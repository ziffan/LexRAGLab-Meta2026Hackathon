"""H-077: `report_view` (R3 `report`) untuk akta dan kasus null. Tanpa jaringan; masukan sintetis."""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.api.routers.snapshot import report_view

SID = "S" * 64


def _m(item_id, gold, cov, rt, gt, rank, parts=(1, 1)):
    return {"item_id": item_id, "setting_id": SID, "split": None, "gold_chars": gold, "covered_gold_chars": cov,
            "retrieved_tokens": rt, "gold_tokens_retrieved": gt, "rank": rank, "parts_total": parts[0], "parts_hit": parts[1],
            "retrieved_chunk_ids": ["c1"]}


ITEMS = [{"id": f"a{i}", "origin": "operator", "mode": "literal" if i % 2 else "parafrase"} for i in range(1, 4)]
ENV = {"metrics": [_m("a1", 10, 10, 20, 10, 1), _m("a2", 10, 5, 20, 4, 2, (2, 1)), _m("a3", 0, 0, 20, 0, None, (0, 0)),
                   {**_m("x", 1, 1, 1, 1, 1), "setting_id": "other"}]}


def test_akta_report_is_transfer_report_without_heldout_word():
    r = report_view("akta", ITEMS, ENV, {"setting_id": SID})
    assert r["title"] == "Transfer results" and [x["item_id"] for x in r["rows"]] == ["a1", "a2", "a3"]
    assert {x["split"] for x in r["rows"]} == {"Transfer"}
    assert r["rows"][2]["note"] == "no gold (must abstain)" and r["rows"][2]["span_recall"] is None
    assert not re.search(r"held[- ]?out", json.dumps(r), re.I)  # A15
    assert not re.search(r"best|selected", json.dumps(r), re.I)  # tanpa klaim profil terpilih


def test_null_without_grid_selection_or_rows_and_unknown_item():
    assert report_view("uupt", ITEMS, None, {"setting_id": SID}) is None
    assert report_view("uupt", ITEMS, ENV, None) is None
    assert report_view("uupt", ITEMS, ENV, {"setting_id": "absent"}) is None
    assert report_view("akta", ITEMS[:1], ENV, {"setting_id": SID}) is None  # butir tak dikenal: null, bukan 500


# ---- kontrak bentuk lintas sisi: berkas ini juga dibaca vitest (frontend/src/__tests__/report.test.ts) ----
FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "__tests__" / "report.fixture.json"


def contract_report() -> dict:
    env = {"metrics": [{**m, "split": sp} for m, sp in zip(ENV["metrics"][:3], ("held_out", "held_out", "held_out"))]
           + [{**_m("t1", 5, 5, 10, 5, 1), "split": "tune"}]}
    items = ITEMS + [{"id": "t1", "origin": "spark_disetujui", "mode": "literal"}]
    return {"uupt": report_view("uupt", items, env, {"setting_id": SID}),
            "akta": report_view("akta", ITEMS, ENV, {"setting_id": SID})}


def test_report_matches_shared_contract_fixture():
    got = contract_report()
    if not FIXTURE.exists():  # pembuatan awal; selanjutnya berkas adalah kontrak (ubah sengaja bila bentuk berubah)
        FIXTURE.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == got
