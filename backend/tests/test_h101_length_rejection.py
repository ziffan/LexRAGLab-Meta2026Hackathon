"""Putusan operator 13 (pemeriksa delta2 SHOULD 1): hanya penolakan PANJANG yang tidak dihitung ke `max_consecutive_errors`
di jalur pembanding; `semantic_invalid` sistemik (chunk_id beda, header kosong) dan galat teknis tetap dihitung."""

import pytest

from backend.header_b.caller import is_length_rejection


@pytest.mark.parametrize("err,want", [
    ({"code": "semantic_invalid", "message": "semantic validation failed: header exceeds 40 tokens"}, True),
    ({"code": "schema_invalid", "message": "output does not match schema: $.header: string longer than maxLength 190"}, True),
    ({"code": "semantic_invalid", "message": "semantic validation failed: chunk_id does not match the requested chunk"}, False),
    ({"code": "semantic_invalid", "message": "semantic validation failed: header is empty"}, False),
    ({"code": "schema_invalid", "message": "output is not valid JSON"}, False),
    ({"code": "timeout", "message": "timeout after 120 s"}, False),
    ({"code": "incomplete", "message": "incomplete (max_output_tokens)"}, False),
    ({}, False),
])
def test_is_length_rejection(err, want):
    assert is_length_rejection(err) is want
