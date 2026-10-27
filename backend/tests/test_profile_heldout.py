"""M4.3 S8, S9, S10, S11, S12: blok `held_out`, penyebut nol, profil akta tanpa split, laporan per butir (fungsi murni)."""

from __future__ import annotations

import dataclasses
import json
import re

import pytest

from backend.profile import ProfileError, export_profile
from backend.profile.aggregate import build_report, held_out_block
from backend.tests import profile_helpers as H

SID = H.P1["setting_id"]
FIVE = {"operator": 3, "spark_disetujui": 1}


def block(metrics, items=None):
    return held_out_block(items if items is not None else H.ITEMS, metrics)


def approx_block(b, **exp):
    for k, v in exp.items():
        if isinstance(v, float):
            assert b[k] == pytest.approx(v, abs=1e-9), k
        else:
            assert b[k] == v, k


def im(i, gold, cov, retr, gtok, rank=None, total=0, hit=0, split="held_out"):
    return H.im(i, split, SID, gold, cov, retr, gtok, rank, total, hit)


# ---------- S8 ----------
def test_s8_block_only_held_out_on_this_setting():
    b = block(H.s8_metrics(SID))
    assert set(b) == {"n_items", "by_origin", "mean_span_recall", "mean_token_precision", "fully_covered"}
    approx_block(b, n_items=4, by_origin=FIVE, mean_span_recall=7 / 12, mean_token_precision=7 / 30,
                 fully_covered={"covered": 1, "total": 3})


def test_s8_service_filters_by_setting_id(tmp_path):
    metrics = H.s8_metrics(SID) + H.distractor(H.P2["setting_id"])
    prof = export_profile(H.make_deps(tmp_path, metrics=metrics), "uupt", SID).profile
    approx_block(prof["held_out"], n_items=4, by_origin=FIVE, mean_span_recall=7 / 12, mean_token_precision=7 / 30,
                 fully_covered={"covered": 1, "total": 3})
    p2 = export_profile(H.make_deps(tmp_path, metrics=metrics), "uupt", H.P2["setting_id"]).profile
    assert p2["held_out"]["mean_span_recall"] == 1.0  # distraktor milik P2 sendiri


# ---------- S9 ----------
def test_s9a_no_gold_in_held_out(tmp_path):
    ms = [im("h4", 0, 0, 7, 0), im("t1", 10, 10, 10, 9, 1, 1, 1, split="tune")]
    b = block(ms)
    assert b == {"n_items": 1, "by_origin": {"operator": 1, "spark_disetujui": 0}, "mean_span_recall": None,
                 "mean_token_precision": None, "fully_covered": {"covered": 0, "total": 0}}
    json.dumps(b, allow_nan=False)
    prof = export_profile(H.make_deps(tmp_path, metrics=[dataclasses.replace(m, setting_id=SID) for m in ms]), "uupt", SID).profile
    assert prof["held_out"] == b


def test_s9b_no_grid_result_422(tmp_path):
    deps = H.make_deps(tmp_path)
    for gm in (lambda fam: None, lambda fam: (H.ITEMS, H.s8_metrics(H.P2["setting_id"]))):  # tanpa grid / tanpa metrik setting ini
        with pytest.raises(ProfileError) as e:
            export_profile(dataclasses.replace(deps, grid_metrics=gm), "uupt", SID)
        assert e.value.kind == "validation_failed" and "grid" in e.value.message
    assert not (tmp_path / "profiles").exists()


def test_s9c_zero_recall_null_precision():
    items = H.ITEMS + [{"id": "h5", "origin": "operator", "mode": "literal"}]
    b = block([im("h5", 6, 0, 0, 0)], items)
    assert b == {"n_items": 1, "by_origin": {"operator": 1, "spark_disetujui": 0}, "mean_span_recall": 0.0,
                 "mean_token_precision": None, "fully_covered": {"covered": 0, "total": 1}}
    assert b["mean_span_recall"] is not None


def test_s9d_precision_only_from_non_null():
    items = H.ITEMS + [{"id": "h5", "origin": "operator", "mode": "literal"}]
    b = block([im("h1", 10, 10, 8, 4, 1, 1, 1), im("h5", 6, 0, 0, 0)], items)
    assert b == {"n_items": 2, "by_origin": {"operator": 2, "spark_disetujui": 0}, "mean_span_recall": 0.5,
                 "mean_token_precision": 0.5, "fully_covered": {"covered": 1, "total": 2}}


# ---------- S10 ----------
def test_s10_akta_profile_no_split(tmp_path):
    deps = H.make_deps(tmp_path)
    res = export_profile(deps, "akta", H.PA1["setting_id"])
    p = res.profile
    assert p["held_out"] is None and p["family"] == "akta" and p["schema"] == H.V1_BODY and p["packing"] == "stop"
    text = res.body.decode("utf-8")
    assert not re.search(r"transfer|\"split\"|\"tune\"", text, re.I)
    assert "held_out\":null" in text  # kunci kontrak ada, nilainya null persis


# ---------- S11 ----------
def test_s11_uupt_report():
    ms = H.s8_metrics(SID)
    r = build_report("uupt", H.ITEMS, ms)
    assert r["title"] == "Held-out results"
    assert [x["item_id"] for x in r["rows"]] == ["h1", "h2", "h3", "h4"] and {x["split"] for x in r["rows"]} == {"held_out"}
    rows = {x["item_id"]: x for x in r["rows"]}
    txt = lambda c: c["text"] if c else None
    assert [txt(rows[i]["span_recall"]) for i in ("h1", "h2", "h3", "h4")] == ["10 of 10", "15 of 20", "0 of 5", None]
    assert [txt(rows[i]["token_precision"]) for i in ("h1", "h2", "h3", "h4")] == ["4 of 8", "2 of 10", "0 of 6", None]
    assert [rows[i]["reciprocal_rank"] for i in ("h1", "h2", "h3", "h4")] == [1.0, 0.5, 0.0, None]
    assert [rows[i]["recall_at_k"] for i in ("h1", "h2", "h3", "h4")] == [1.0, 0.5, 0.0, None]
    assert rows["h4"]["note"] == "no gold (must abstain)" and rows["h1"]["note"] is None
    s = r["summary"]
    assert s["fully_covered"]["text"] == "1 of 3" and s["n_items"] == 4
    g = lambda grp, k: (r[grp][k]["mean_span_recall"], r[grp][k]["mean_token_precision"])
    assert g("by_origin", "operator") == (pytest.approx(0.875), pytest.approx(0.35))
    assert g("by_origin", "spark_disetujui") == (0.0, 0.0)
    assert g("by_mode", "literal") == (1.0, 0.5)
    assert g("by_mode", "parafrase") == (pytest.approx(0.375), pytest.approx(0.1))
    assert "%" not in json.dumps(r)
    assert sum(1 for x in r["by_origin"].values()) == 2 and r["by_origin"]["operator"]["n_items"] == 3  # h1, h2, h4


# ---------- S12 ----------
AK_ITEMS = [{"id": "a1", "origin": "operator", "mode": "literal"}, {"id": "a2", "origin": "operator", "mode": "parafrase"},
            {"id": "a3", "origin": "spark_disetujui", "mode": "literal"}, {"id": "a4", "origin": "operator", "mode": "parafrase"},
            {"id": "a5", "origin": "spark_disetujui", "mode": "parafrase"}]


def ak_metrics():
    a = lambda *x, **k: H.im(x[0], None, H.PA1["setting_id"], *x[1:], **k)
    return [a("a1", 12, 12, 6, 3, 1, 1, 1), a("a2", 10, 4, 8, 1, 2, 2, 1), a("a3", 8, 0, 5, 0, None, 1, 0),
            a("a4", 0, 0, 7, 0), a("a5", 15, 15, 10, 4, 3, 1, 1)]


def test_s12_akta_report_transfer_no_held_out_word():
    r = build_report("akta", AK_ITEMS, ak_metrics())
    assert r["title"] == "Transfer results" and len(r["rows"]) == 5 and {x["split"] for x in r["rows"]} == {"Transfer"}
    rows = {x["item_id"]: x for x in r["rows"]}
    txt = lambda c: c["text"] if c else None
    assert [txt(rows[i]["span_recall"]) for i in ("a1", "a2", "a3", "a4", "a5")] == ["12 of 12", "4 of 10", "0 of 8", None, "15 of 15"]
    assert [txt(rows[i]["token_precision"]) for i in ("a1", "a2", "a3", "a4", "a5")] == ["3 of 6", "1 of 8", "0 of 5", None, "4 of 10"]
    assert rows["a4"]["note"] == "no gold (must abstain)"
    assert rows["a2"]["reciprocal_rank"] == 0.5 and rows["a5"]["reciprocal_rank"] == pytest.approx(1 / 3) and rows["a4"]["reciprocal_rank"] is None
    assert r["summary"]["mean_span_recall"] == pytest.approx(0.6) and r["summary"]["fully_covered"]["text"] == "2 of 4"
    assert (r["by_origin"]["operator"]["mean_span_recall"], r["by_origin"]["spark_disetujui"]["mean_span_recall"]) == (
        pytest.approx(0.7), pytest.approx(0.5))
    assert (r["by_mode"]["literal"]["mean_span_recall"], r["by_mode"]["parafrase"]["mean_span_recall"]) == (
        pytest.approx(0.5), pytest.approx(0.7))
    blob = json.dumps(r)
    assert not re.search(r"held[- ]?out", blob, re.I) and not re.search(r"best|selected profile|%", blob, re.I)


def test_report_unknown_family_and_item():
    with pytest.raises(ValueError):
        build_report("pt", [], [])
    with pytest.raises(KeyError):
        build_report("uupt", [], H.s8_metrics(SID))
