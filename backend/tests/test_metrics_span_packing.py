"""M1.2 Tier 1: pengemasan anggaran, span recall, precision token, MRR (docs/scenarios/M1.2.md)."""

from fractions import Fraction as F

import pytest

from backend.metrics.packing import pack
from backend.metrics.types import RankedChunk
from backend.tests.toy_ws import C1, C2, C3, C4, TOK, T, V, W, rc, run, tk


def test_S1_gold_split_gap_budget_exactly_b():
    c2p = tk(4, 7)
    assert c2p == (12, 23)
    m = run(T, [(6, 20)], [C1, c2p, C3], budget=8, k=2)
    assert (m.gold_chars, m.covered_gold_chars) == (14, 13)
    assert m.span_recall == F(13, 14)
    assert (m.gold_tokens_retrieved, m.retrieved_tokens) == (5, 8)
    assert m.token_precision == F(5, 8)
    assert m.reciprocal_rank == 1 and m.rank == 1
    assert m.recall_at_k == 0
    assert m.fully_covered is False


def test_S1b_overlapping_gold_spans_form_set():
    m = run(T, [(6, 12), (10, 20)], [C1, tk(4, 7), C3], budget=8, k=2)
    assert m.gold_chars == 14
    assert m.span_recall == F(13, 14)
    assert m.token_precision == F(5, 8)


def test_S2_overlapping_chunks():
    A, B, C = (0, 11), (6, 17), (12, 23)
    m = run(T, [(9, 14)], [A, B, C], budget=12, k=3)
    assert m.gold_chars == 5 and m.span_recall == 1
    assert (m.gold_tokens_retrieved, m.retrieved_tokens) == (2, 12)
    assert m.token_precision == F(1, 6)
    assert m.reciprocal_rank == 1
    assert m.recall_at_k == 1
    assert m.fully_covered is True


def test_S2b_budget_11_stops_before_third_chunk():
    A, B, C = (0, 11), (6, 17), (12, 23)
    m = run(T, [(9, 14)], [A, B, C], budget=11, k=3)
    assert m.span_recall == 1
    assert m.retrieved_tokens == 8
    assert m.gold_tokens_retrieved == 2
    assert m.token_precision == F(1, 4)


@pytest.mark.parametrize(
    "rule,span_recall,gold_tok,retrieved,rr,rank",
    [
        ("stop", F(0), 0, 4, F(0), None),
        ("skip", F(1, 4), 1, 6, F(1, 2), 2),
        ("truncate", F(1, 4), 1, 8, F(1, 2), 2),
    ],
)
def test_S3_three_packing_rules(rule, span_recall, gold_tok, retrieved, rr, rank):
    m = run(T, [(21, 29)], [C1, C2, C3, C4], budget=8, packing=rule, k=4)
    assert m.gold_chars == 8
    assert m.span_recall == span_recall
    assert (m.gold_tokens_retrieved, m.retrieved_tokens) == (gold_tok, retrieved)
    assert m.token_precision == F(gold_tok, retrieved)
    assert m.reciprocal_rank == rr and m.rank == rank


def test_S3_truncate_adjusts_end_offset_without_trailing_space():
    p = pack(T, rc(C1, C2, C3, C4), 8, TOK, "truncate")
    assert [(x.start, x.end, x.cost, x.truncated) for x in p] == [(0, 11, 4, False), (12, 23, 4, True)]


def test_S3_skip_pack_skips_repeatedly_and_ranks_in_p():
    p = pack(T, rc(C1, C2, C3, C4), 8, TOK, "skip")
    assert [(x.start, x.end) for x in p] == [C1, C3]
    assert [x.rank_in_c for x in p] == [1, 3]


H = "H1 H2"


def _s4(budget, rule, header):
    c1, c2 = (0, 8), (9, 17)
    return run(T, [(0, 8), (9, 14)], [c1, c2], budget=budget, packing=rule, k=2, header=header)


def test_S4_header_on_stop():
    m = _s4(9, "stop", H)
    assert m.gold_chars == 13
    assert m.span_recall == F(8, 13)
    assert m.token_precision == F(3, 5) and m.retrieved_tokens == 5
    assert m.fully_covered is False


def test_S4_header_on_truncate():
    m = _s4(9, "truncate", H)
    assert m.span_recall == 1
    assert m.token_precision == F(5, 9) and m.retrieved_tokens == 9
    assert m.fully_covered is True


def test_S4_header_off_stop_control():
    m = _s4(9, "stop", "")
    assert m.span_recall == 1
    assert m.token_precision == F(5, 6) and m.retrieved_tokens == 6
    assert m.fully_covered is True


def test_S5_gold_outside_budget_and_recall_at_k_ignores_budget():
    ch = [C1, C2, C3, C4]
    m1 = run(T, [(15, 20)], ch, budget=8, k=1)
    m2 = run(T, [(15, 20)], ch, budget=8, k=2)
    assert m1.gold_chars == 5 and m1.span_recall == 0 and m1.span_recall is not None
    assert m1.retrieved_tokens == 4 and m1.token_precision == 0
    assert m1.reciprocal_rank == 0 and m1.reciprocal_rank is not None
    assert m1.recall_at_k == 0
    assert m2.recall_at_k == 1
    assert m2.fully_covered is False


def test_S6a_empty_p_precision_null_stop():
    m = run(T, [(0, 5)], [C1, C2], budget=3, packing="stop", k=1)
    assert m.span_recall == 0 and m.retrieved_tokens == 0 and m.gold_tokens_retrieved == 0
    assert m.token_precision is None
    assert m.reciprocal_rank == 0
    assert m.fully_covered is False
    assert m.recall_at_k == 1


def test_S6b_truncate_first_chunk_exceeds_budget():
    m = run(T, [(0, 5)], [C1, C2], budget=3, packing="truncate", k=1)
    assert m.span_recall == 1 and m.gold_tokens_retrieved == 2
    assert m.token_precision == F(2, 3)
    assert m.reciprocal_rank == 1
    assert m.fully_covered is True


def test_S6c_skip_accepts_chunk_that_fits_exactly():
    m = run(T, [(0, 5)], [C1, C4], budget=3, packing="skip", k=1)
    assert m.span_recall == 0
    assert m.token_precision == F(0, 3) and m.token_precision == 0
    assert m.retrieved_tokens == 3
    assert m.reciprocal_rank == 0


def test_S7_item_without_gold():
    m = run(T, [], [C1, C2], budget=8, k=1)
    assert m.gold_chars == 0 and m.covered_gold_chars == 0
    assert m.span_recall is None and m.token_precision is None
    assert m.reciprocal_rank is None and m.recall_at_k is None and m.fully_covered is None
    assert m.gold_tokens_retrieved == 0
    assert m.retrieved_tokens == 4


def test_S8_rank_in_p_gap_and_half_gold_token():
    m = run(T, [(30, 34)], [C1, C2, C3, C4], budget=14, k=4)
    assert m.covered_gold_chars == 3 and m.span_recall == F(3, 4)
    assert m.gold_tokens_retrieved == 1 and m.retrieved_tokens == 14
    assert m.token_precision == F(1, 14)
    assert m.rank == 3 and m.reciprocal_rank == F(1, 3)
    assert m.recall_at_k == 0
    assert m.fully_covered is False


def test_S9_fragment_token_at_chunk_boundary():
    m = run(T, [(6, 10)], [(0, 10)], budget=4, k=1)
    assert TOK.offsets(T[0:10]) == [(0, 2), (3, 5), (6, 8), (9, 10)]
    assert m.span_recall == 1
    assert m.gold_tokens_retrieved == 2 and m.retrieved_tokens == 4
    assert m.token_precision == F(1, 2)


def _s17(budget):
    ranked = [
        RankedChunk(0, 8, "H1 H2"),
        RankedChunk(9, 17, "H1 H2"),
        RankedChunk(27, 29, "H3"),
    ]
    return run(T, [(0, 8), (9, 14), (27, 29)], None, budget=budget, packing="truncate", k=3, ranked=ranked)


@pytest.mark.parametrize("budget", [6, 7], ids=["a_r_negative", "b_r_zero"])
def test_S17_truncate_nonpositive_remainder_stops(budget):
    m = _s17(budget)
    assert m.gold_chars == 15
    assert m.span_recall == F(8, 15)
    assert m.token_precision == F(3, 5)
    assert m.retrieved_tokens == 5
    assert m.rank == 1 and m.reciprocal_rank == 1


def test_S18_gold_token_dedup_by_position_not_text():
    m = run(V, [(6, 8), (12, 14)], [(0, 11), (6, 17)], budget=8, k=2)
    assert m.gold_chars == 4 and m.span_recall == 1
    assert m.gold_tokens_retrieved == 2 and m.retrieved_tokens == 8
    assert m.token_precision == F(1, 4)
    assert m.reciprocal_rank == 1


def test_S21_code_point_offsets_non_ascii_non_bmp():
    assert len(W) == 8
    m = run(W, [(3, 5), (6, 8)], [(0, 5), (6, 8)], budget=3, k=2)
    assert m.gold_chars == 4 and m.span_recall == 1
    assert m.gold_tokens_retrieved == 2 and m.retrieved_tokens == 3
    assert m.token_precision == F(2, 3)
    assert m.reciprocal_rank == 1
