"""Uji measure tanpa jaringan (CONVENTIONS: test tidak memanggil Model API)."""
import json

import pytest

from backend import config, measure
from backend.corpus.loader import load_corpus


def test_section_texts_partition_document():
    doc = load_corpus()
    t = measure.section_texts(doc)
    assert sum(len(t[s]) for s in measure.SECTIONS) == len(t["_document"]) == doc.char_count


def test_offline_uses_stored_run_and_never_calls_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network called")
    monkeypatch.setattr(measure, "count_endpoint", boom)
    rec = measure.run(offline=True)  # memakai run tersimpan di runs/measure/
    assert rec["_from_cache"] is True
    rr = rec["run_record"]
    assert rr["provider"] == "meta" and rr["kind"] == "measure" and rr["cost_usd_micros"] == 0
    assert isinstance(rr["cost_usd_micros"], int)
    assert rec["method"]["status"] == "sementara"
    assert "measure" in measure.format_table(rec)


def test_offline_without_stored_run_fails_clearly(monkeypatch):
    monkeypatch.setattr(measure, "REF_TEXT", "<no stored run for this reference>")  # kunci cache lain
    with pytest.raises(measure.MeasureError, match="--offline"):
        measure.run(offline=True)


def test_calibration_recorded_in_config_matches_run():
    cal = config.load("tokenizer")["calibration"]
    rec = json.loads((config.REPO_ROOT / "runs" / "measure" / (cal["run_id"].split("-", 1)[1] + ".json")).read_text(encoding="utf-8"))
    assert cal["mean_section_ratio"] == rec["mean_section_ratio"]
    assert cal["hidden_overhead_tokens"] == rec["method"]["hidden_overhead_tokens"]
    for r in rec["rows"]:
        key = "document" if r["section"] == "_document" else r["section"]
        assert cal["uupt-40-2007"][key] == r["calibration_ratio"]


def test_no_secret_in_stored_run():
    for p in (config.REPO_ROOT / "runs").rglob("*.json"):
        s = p.read_text(encoding="utf-8")
        assert "Bearer" not in s and "sk-" not in s and "Authorization" not in s and "api_key" not in s.lower()


OVERHEAD = 165


def _fake_env(monkeypatch):
    monkeypatch.setattr(measure, "_env", lambda: {"MUSE_BASE_URL": "https://example.invalid/v1", "MUSE_API_KEY": "fake-key-not-real-000"})


def test_difference_method_arithmetic_and_cache(monkeypatch, tmp_path):
    """Endpoint palsu: raw = 1.5 × token lokal + overhead. Metode selisih harus memulihkan 1.5×local."""
    from backend.tokenizer import get_tokenizer
    tok = get_tokenizer()
    calls = []

    def fake(text, model, base, key):
        calls.append(text)
        local = tok.count(text)
        return (local if text == measure.REF_TEXT else (3 * local) // 2) + OVERHEAD, 1

    _fake_env(monkeypatch)
    monkeypatch.setattr(measure, "count_endpoint", fake)
    rec = measure.run(out_dir=tmp_path)
    assert rec["_from_cache"] is False and len(calls) == 7
    assert rec["method"]["hidden_overhead_tokens"] == OVERHEAD
    for r in rec["rows"]:
        assert r["tokens_endpoint"] == (3 * r["tokens_local"]) // 2
    doc = next(r for r in rec["rows"] if r["section"] == "_document")
    # proyeksi: ceil integer, harga input 100000 / cached 2000 micro-USD per 1M token
    t = doc["tokens_endpoint"]
    assert rec["cost_projection"]["uncached_micros"] == -(-t * 100000 // 1_000_000)
    assert rec["cost_projection"]["cached_micros"] == -(-t * 2000 // 1_000_000)
    # run kedua: dari cache, tanpa panggilan
    calls.clear()
    rec2 = measure.run(out_dir=tmp_path)
    assert rec2["_from_cache"] is True and calls == []


def test_projection_rounds_up_not_down(monkeypatch, tmp_path):
    _fake_env(monkeypatch)
    from backend.tokenizer import get_tokenizer
    tok = get_tokenizer()
    # dokumen 46583 token -> 4658.3 -> 4659 (ceil), 93.166 -> 94
    monkeypatch.setattr(measure, "count_endpoint", lambda text, *a: (tok.count(text) + OVERHEAD, 1))
    rec = measure.run(out_dir=tmp_path)
    t = rec["cost_projection"]["input_tokens"]
    assert rec["cost_projection"]["uncached_micros"] * 1_000_000 >= t * 100000
    assert (rec["cost_projection"]["uncached_micros"] - 1) * 1_000_000 < t * 100000


def test_401_message_has_no_key(monkeypatch):
    import io
    import urllib.error

    secret = "fake-secret-key-zz-0123456789"

    def boom(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":"bad key ' + secret.encode() + b'"}'))

    monkeypatch.setattr(measure.urllib.request, "urlopen", boom)
    with pytest.raises(measure.MeasureError) as ei:
        measure.count_endpoint("x", "m", "https://example.invalid/v1", secret)
    assert "invalid API key" in str(ei.value) and secret not in str(ei.value)
    assert ei.value.__cause__ is None


def test_non_https_base_rejected():
    with pytest.raises(measure.MeasureError, match="https"):
        measure.count_endpoint("x", "m", "http://example.invalid/v1", "k")


def test_invalid_json_is_clear_error(monkeypatch):
    import io

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(measure.urllib.request, "urlopen", lambda req, timeout: R(b"not json"))
    with pytest.raises(measure.MeasureError, match="invalid JSON"):
        measure.count_endpoint("x", "m", "https://example.invalid/v1", "k")
