"""M1.2 Tier 1: pemecahan bagian-ayat dan Recall@K (docs/scenarios/M1.2.md S10-S14, S19, S20)."""

from fractions import Fraction as F

from backend.metrics.item import gold_parts
from backend.tests.toy_ws import U, U_UNITS, run


def ru(gold, spans, k=1, budget=10**6):
    return run(U, gold, spans, budget=budget, k=k, units=U_UNITS)


def test_S10_multi_ayat_split_and_recall_at_k():
    assert gold_parts([(12, 50)], U_UNITS) == [(12, 24), (25, 37), (38, 50)]
    C = [(0, 26), (25, 51), (52, 78)]
    assert ru([(12, 50)], C, k=1).recall_at_k == F(1, 3)
    assert ru([(12, 50)], C, k=2).recall_at_k == 1
    m = ru([(12, 50)], C[:1], k=1)
    assert m.gold_chars == 38 and m.span_recall == F(14, 38)
    assert ru([(12, 50)], C[:2], k=2).span_recall == F(38, 38)


def test_S11_part_split_across_two_chunks_not_counted():
    m = ru([(12, 50)], [(0, 20), (20, 51)], k=2)
    assert m.recall_at_k == F(2, 3)
    assert m.span_recall == 1 and m.covered_gold_chars == 38
    assert m.fully_covered is True


def test_S12_penjelasan_ayat_pasal_tanpa_ayat_and_rank_order():
    gold = [(64, 76), (102, 163)]
    assert gold_parts(gold, U_UNITS) == [(64, 76), (102, 123), (124, 141), (142, 163)]
    C = [(142, 164), (52, 102), (102, 142)]  # F3, F1, F2 (urutan peringkat)
    assert ru(gold, C, k=1).recall_at_k == F(1, 4)
    assert ru(gold, C, k=2).recall_at_k == F(2, 4)
    assert ru(gold, C, k=3).recall_at_k == 1
    assert ru(gold, C, k=5).recall_at_k == 1  # K > |C| tanpa galat


def test_S13a_penjelasan_without_ayat_marker_single_part():
    gold = [(188, 200)]
    assert gold_parts(gold, U_UNITS) == [(188, 200)]
    assert ru(gold, [(164, 201)], k=1).recall_at_k == 1
    assert ru(gold, [(170, 195)], k=1).recall_at_k == 0


def test_S13b_pasal_tanpa_ayat_whole_with_heading():
    gold = [(52, 76)]
    assert gold_parts(gold, U_UNITS) == [(52, 76)]
    assert ru(gold, [(52, 102)], k=1).recall_at_k == 1
    assert ru(gold, [(64, 102)], k=1).recall_at_k == 0


def test_S14_overlapping_gold_spans_merged_before_split():
    gold = [(12, 30), (20, 50)]
    assert gold_parts(gold, U_UNITS) == [(12, 24), (25, 37), (38, 50)]
    m = ru(gold, [(0, 26)], k=1)
    assert m.recall_at_k == F(1, 3)
    assert m.gold_chars == 38 and m.span_recall == F(14, 38)


def test_S19_containment_inclusive_at_both_ends():
    gold = [(12, 37)]
    C = [(25, 37), (5, 24)]
    assert ru(gold, C, k=1).recall_at_k == F(1, 2)
    assert ru(gold, C, k=2).recall_at_k == 1


def test_S20a_gold_includes_heading_not_a_part():
    gold = [(0, 50)]
    m = ru(gold, [(12, 51)], k=1)
    assert gold_parts(gold, U_UNITS) == [(12, 24), (25, 37), (38, 50)]
    assert m.recall_at_k == 1
    assert m.gold_chars == 50 and m.span_recall == F(19, 25)


def test_S20b_gold_outside_all_units_recall_at_k_null_without_error():
    m = ru([(51, 52)], [(0, 100)], k=1)
    assert gold_parts([(51, 52)], U_UNITS) == []
    assert m.span_recall == 1 and m.span_recall is not None
    assert m.recall_at_k is None
    assert m.fully_covered is True
