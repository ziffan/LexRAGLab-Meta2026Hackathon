"""M2.1 Tier 1: tabel per butir difilter per asal, laporan per asal, `items_summary` (S19-S22). Fungsi murni, data sintetis."""

import pytest

from backend.api.errors import ApiError
from backend.proposal.report import ReportError, filter_items, items_summary, origin_report, pending_count

K = {  # id: (origin, mode, split, review_status)
    "K1": ("operator", "literal", "held_out", None), "K2": ("operator", "parafrase", "held_out", None),
    "K3": ("operator", "literal", "tune", None), "K4": ("spark_disetujui", "literal", "held_out", "disetujui"),
    "K5": ("spark_disetujui", "parafrase", "held_out", "disetujui"), "K6": ("spark_disetujui", "parafrase", "held_out", "diubah"),
    "K7": ("spark_disetujui", "literal", "tune", "disetujui"), "K8": ("operator", "literal", "held_out", None),
}
ITEMS = [{"id": k, "origin": o, "mode": m, "split": s, "review_status": r} for k, (o, m, s, r) in K.items()]
M = {  # id: gold_chars, covered, gold_tokens_retrieved, retrieved_tokens
    "K1": (100, 100, 10, 20), "K2": (100, 50, 5, 25), "K3": (80, 0, 0, 40), "K4": (40, 40, 8, 16),
    "K5": (60, 30, 6, 20), "K6": (20, 5, 1, 10), "K7": (50, 50, 25, 50), "K8": (0, 0, 0, 30),
}


def metrics(ids=None):
    return [{"item_id": k, "gold_chars": g, "covered_gold_chars": c, "gold_tokens_retrieved": t, "retrieved_tokens": r}
            for k, (g, c, t, r) in M.items() if ids is None or k in ids]


# ---------------------------------------------------------------- S19
@pytest.mark.parametrize("kw,exp", [
    ({}, "K1 K2 K3 K4 K5 K6 K7 K8"),
    ({"origin": "operator"}, "K1 K2 K3 K8"),
    ({"origin": "spark_disetujui"}, "K4 K5 K6 K7"),
    ({"origin": "operator", "mode": "parafrase"}, "K2"),
    ({"origin": "spark_disetujui", "mode": "parafrase"}, "K5 K6"),
    ({"origin": "spark_disetujui", "mode": "literal", "split": "held_out"}, "K4"),
    ({"mode": "parafrase"}, "K2 K5 K6"),
    ({"origin": "spark_disetujui", "mode": "literal", "split": "tune"}, "K7"),
    ({"origin": "operator", "mode": "parafrase", "split": "tune"}, ""),
])
def test_s19_filters_are_and_and_keep_order(kw, exp):
    assert [i["id"] for i in filter_items(ITEMS, **kw)] == exp.split()


@pytest.mark.parametrize("kw", [{"origin": "diubah"}, {"mode": "campur"}, {"split": "val"}])
def test_s19_unknown_filter_value_is_400(kw):
    with pytest.raises(ApiError) as ei:
        filter_items(ITEMS, **kw)
    assert ei.value.status == 400 and ei.value.code == "invalid_request"


# ---------------------------------------------------------------- S20
def test_s20_report_per_origin_held_out_and_tune():
    r = origin_report(ITEMS, metrics())
    op, sp = r["operator"], r["spark_disetujui"]
    assert (op["n_items"], op["n_with_gold"], op["n_no_gold"], op["n_missing_metrics"]) == (3, 2, 1, 0)
    assert op["mean_span_recall"] == pytest.approx(0.75, abs=1e-9) and op["mean_token_precision"] == pytest.approx(0.35, abs=1e-9)
    assert op["fully_covered"] == {"covered": 1, "total": 2}
    assert (sp["n_items"], sp["n_with_gold"], sp["n_no_gold"]) == (3, 3, 0)
    assert sp["mean_span_recall"] == pytest.approx(0.5833333333, abs=1e-9) and sp["mean_token_precision"] == pytest.approx(0.3, abs=1e-9)
    assert sp["fully_covered"] == {"covered": 1, "total": 3}
    t = origin_report(ITEMS, metrics(), split="tune")
    assert t["operator"] == {"n_items": 1, "n_with_gold": 1, "n_no_gold": 0, "n_missing_metrics": 0, "mean_span_recall": 0.0,
                             "mean_token_precision": 0.0, "fully_covered": {"covered": 0, "total": 1}}
    assert t["spark_disetujui"]["mean_span_recall"] == 1.0 and t["spark_disetujui"]["mean_token_precision"] == pytest.approx(0.5)
    assert t["spark_disetujui"]["fully_covered"] == {"covered": 1, "total": 1}


def test_s20b_metrics_row_for_non_item_is_hard_error():
    rows = metrics() + [{"item_id": "usulan-L2", "gold_chars": 10, "covered_gold_chars": 10, "gold_tokens_retrieved": 1, "retrieved_tokens": 1}]
    with pytest.raises(ReportError):
        origin_report(ITEMS, rows)


def test_s20_accepts_metrics_objects():
    from backend.metrics.types import ItemMetrics
    rows = [ItemMetrics(gold_chars=g, covered_gold_chars=c, retrieved_tokens=r, gold_tokens_retrieved=t, item_id=k)
            for k, (g, c, t, r) in M.items()]
    assert origin_report(ITEMS, rows)["operator"]["mean_span_recall"] == pytest.approx(0.75)


# ---------------------------------------------------------------- S21
def test_s21_origin_without_items_or_without_gold():
    sel = [i for i in ITEMS if i["id"] in ("K1", "K2")]
    r = origin_report(sel, metrics({"K1", "K2"}))
    assert r["operator"]["n_items"] == 2 and r["operator"]["mean_span_recall"] == pytest.approx(0.75)
    assert r["operator"]["fully_covered"] == {"covered": 1, "total": 2}
    assert r["spark_disetujui"] == {"n_items": 0, "n_with_gold": 0, "n_no_gold": 0, "n_missing_metrics": 0, "mean_span_recall": None,
                                    "mean_token_precision": None, "fully_covered": {"covered": 0, "total": 0}}
    sel = [i for i in ITEMS if i["id"] in ("K8", "K4")]
    r = origin_report(sel, metrics({"K8", "K4"}))
    assert (r["operator"]["n_items"], r["operator"]["n_with_gold"], r["operator"]["n_no_gold"]) == (1, 0, 1)
    assert r["operator"]["mean_span_recall"] is None and r["operator"]["mean_token_precision"] is None
    assert r["operator"]["fully_covered"] == {"covered": 0, "total": 0}
    assert r["spark_disetujui"]["mean_span_recall"] == 1.0 and r["spark_disetujui"]["mean_token_precision"] == 0.5
    assert r["spark_disetujui"]["fully_covered"] == {"covered": 1, "total": 1}


def test_s21c_item_without_metrics_row_is_counted_not_zeroed():
    sel = [i for i in ITEMS if i["id"] in ("K1", "K2")]
    op = origin_report(sel, metrics({"K1"}))["operator"]
    assert (op["n_items"], op["n_with_gold"], op["n_no_gold"], op["n_missing_metrics"]) == (2, 1, 0, 1)
    assert op["mean_span_recall"] == 1.0 and op["mean_token_precision"] == 0.5 and op["fully_covered"] == {"covered": 1, "total": 1}


# ---------------------------------------------------------------- S22
def test_s22_items_summary_counts_items_not_proposals():
    s = items_summary(ITEMS)
    assert s == {"n_items": 8, "by_origin": {"operator": 4, "spark_disetujui": 4}, "by_mode": {"literal": 5, "parafrase": 3},
                 "by_split": {"tune": 2, "held_out": 6}, "control_in_held_out": 3}
    props = [{"review_status": x} for x in ["usulan"] * 3 + ["ditolak"] * 2 + ["disetujui", "disetujui", "diubah", "disetujui"]]
    assert pending_count(props) == 3 and s["n_items"] == 8


# ---------------------------------------------------------------- pemasangan di produksi (snapshot)
def test_snapshot_serves_summary_and_origin_report(tmp_path):
    from fastapi.testclient import TestClient

    from backend.api.app import Service, create_app
    from backend.tokenizer import get_tokenizer

    from .pipeline_fakes import FakeEncoder
    from .spark_fakes import budget_cfg, model_cfg

    svc = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "runs", encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
    c = TestClient(create_app(svc, env={}, model_config=model_cfg(), budget_config=budget_cfg()), raise_server_exceptions=False)
    d0 = c.get("/api/families/uupt/snapshot").json()
    assert d0["origin_report"] is None and d0["split"] is None and d0["items_summary"]["by_split"] is None
    assert c.post("/api/families/uupt/grid/run", json={"budget_tokens": None}).status_code == 200
    d = c.get("/api/families/uupt/snapshot").json()
    assert d["items_summary"] == items_summary(d["items"])
    rep = d["origin_report"]
    assert set(rep) == {"operator", "spark_disetujui"}
    held_ops = [i for i in d["items"] if i["origin"] == "operator" and i["split"] == "held_out"]
    assert rep["operator"]["n_items"] == len(held_ops) == d["items_summary"]["control_in_held_out"]
    assert rep["spark_disetujui"]["n_items"] == 0 and rep["spark_disetujui"]["mean_span_recall"] is None
