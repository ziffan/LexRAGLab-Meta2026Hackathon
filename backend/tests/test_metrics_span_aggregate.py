"""M1.2 Tier 1: agregat setting (S15) dan catatan run (S16)."""

from fractions import Fraction as F

import pytest

from backend.metrics.aggregate import aggregate, mean_recall_at_k
from backend.metrics.run_record import ensure_single_tokenizer, run_record_parts
from backend.metrics.types import ItemMetrics
from backend.tests.toy_ws import C1, C2, C3, C4, TOK, T, run, tk


def _items():
    return [
        ItemMetrics(gold_chars=14, covered_gold_chars=13, retrieved_tokens=8, gold_tokens_retrieved=5, rank=1),
        ItemMetrics(gold_chars=5, covered_gold_chars=5, retrieved_tokens=12, gold_tokens_retrieved=2, rank=1),
        ItemMetrics(gold_chars=8, covered_gold_chars=0, retrieved_tokens=4, gold_tokens_retrieved=0, rank=None),
        ItemMetrics(gold_chars=5, covered_gold_chars=0, retrieved_tokens=0, gold_tokens_retrieved=0, rank=None),
        ItemMetrics(gold_chars=0, covered_gold_chars=0, retrieved_tokens=20, gold_tokens_retrieved=0),
    ]


def test_S15_aggregate_per_item_mean_and_x_of_y():
    g = aggregate(_items(), setting_id="s", split="tune", budget_tokens=8)
    assert g.mean_span_recall == F(27, 56)
    assert g.mean_token_precision == F(19, 72)
    assert g.mrr == F(1, 2)
    assert g.mean_retrieved_tokens == 6
    assert g.fully_covered_count == {"covered": 1, "total": 4}
    assert g.no_gold_count == 1
    # bukan pooled / bukan /5
    assert g.mean_span_recall != F(9, 16) and g.mean_token_precision != F(7, 24) and g.mrr != F(2, 5)


def test_S15_aggregate_from_computed_items_matches():
    c2p = tk(4, 7)
    i1 = run(T, [(6, 20)], [C1, c2p, C3], budget=8, k=2)
    i2 = run(T, [(9, 14)], [(0, 11), (6, 17), (12, 23)], budget=12, k=3)
    i3 = run(T, [(21, 29)], [C1, C2, C3, C4], budget=8, k=4)
    i4 = run(T, [(0, 5)], [C1, C2], budget=3, k=1)
    i5 = run(T, [], [C1, C2], budget=8, k=1)
    g = aggregate([i1, i2, i3, i4, i5], setting_id="s", split=None, budget_tokens=8)
    assert (g.mean_span_recall, g.mean_token_precision, g.mrr, g.mean_retrieved_tokens) == (
        F(27, 56), F(19, 72), F(1, 2), F(6),
    )
    assert g.fully_covered_count == {"covered": 1, "total": 4} and g.no_gold_count == 1
    assert g.split is None


def test_S15_all_precision_null_gives_null_mean_A7b():
    items = [ItemMetrics(gold_chars=5, covered_gold_chars=0, retrieved_tokens=0, gold_tokens_retrieved=0)]
    g = aggregate(items, setting_id="s", split=None, budget_tokens=3)
    assert g.mean_token_precision is None
    assert g.to_dict()["mean_token_precision"] is None


def test_aggregate_without_gold_items_does_not_fail():
    g = aggregate([ItemMetrics(0, 0, 4, 0)], setting_id="s", split=None, budget_tokens=3)
    assert g.mean_span_recall is None and g.mrr is None
    assert g.fully_covered_count == {"covered": 0, "total": 0}
    assert aggregate([], setting_id="s", split=None, budget_tokens=3).no_gold_count == 0


def test_mean_recall_at_k_skips_null():
    a = ItemMetrics(5, 5, 4, 2, 1, parts_total=2, parts_hit=1)
    b = ItemMetrics(5, 5, 4, 2, 1, parts_total=0, parts_hit=0)  # parts kosong -> null
    c = ItemMetrics(0, 0, 4, 0)
    assert mean_recall_at_k([a, b, c]) == F(1, 2)
    assert mean_recall_at_k([b, c]) is None


def test_item_metrics_to_dict_keeps_integer_counts():
    m = run(T, [(6, 20)], [C1, tk(4, 7), C3], budget=8, k=2)
    d = m.to_dict()
    assert d["gold_chars"] == 14 and d["covered_gold_chars"] == 13
    assert d["retrieved_tokens"] == 8 and d["gold_tokens_retrieved"] == 5
    assert d["span_recall"] == pytest.approx(13 / 14)
    assert d["split"] is None


def test_S16_run_record_parts_tokenizer_and_packing():
    r1 = run_record_parts(TOK.info, "skip")
    r2 = run_record_parts(TOK.info, "truncate")
    assert r1 == {"tokenizer": {"name": "toy-ws", "version": "1"}, "packing": "skip"}
    assert r2["packing"] == "truncate" and r2["tokenizer"] == r1["tokenizer"]
    assert run_record_parts(TOK.info)["packing"] == "stop"  # A11
    with pytest.raises(ValueError):
        run_record_parts(TOK.info, "greedy")
    ensure_single_tokenizer([TOK.info, TOK.info])


def test_S16_different_tokenizers_across_settings_rejected():
    class Other:
        name, version = "toy-ws", "2"

    with pytest.raises(ValueError):
        ensure_single_tokenizer([TOK.info, Other()])
