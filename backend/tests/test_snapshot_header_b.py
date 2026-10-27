"""R3 kunci baca-saja `header_b` (U8, M3.1): proyeksi terbaru + sampel header tersimpan; hanya baca berkas."""

from __future__ import annotations

import json

from backend.api.routers.snapshot import HEADER_SAMPLE_PER_GRANULARITY, header_b_view


def _w(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8", newline="\n")


def test_empty_runs_dir(tmp_path):
    assert header_b_view(tmp_path) == {"projection": None, "samples": [], "stored_counts": {"pasal": 0, "ayat": 0, "fixed_size": 0}}


def test_latest_projection_and_capped_samples(tmp_path):
    h = tmp_path / "headers"
    _w(h / "projection" / "old.json", {"created_at": "2026-10-26T00:00:00Z", "projections": {"pasal": {"prompt_hash": "a" * 64}}})
    _w(h / "projection" / "new.json", {"created_at": "2026-10-27T00:00:00Z", "projections": {"pasal": {"prompt_hash": "b" * 64, "cost_usd_micros": {"expected": 1}}}})
    for i in range(HEADER_SAMPLE_PER_GRANULARITY + 3):
        _w(h / "pasal" / ("b" * 12) / f"c{i:02d}.json", {"chunk_id": f"c{i:02d}", "granularity": "pasal", "header": "H", "tokens_local": 5, "prompt_version": "v1", "run_id": "r"})
    _w(h / "pasal" / ("a" * 12) / "stale.json", {"chunk_id": "stale", "granularity": "pasal", "header": "H", "tokens_local": 5})
    (h / "ayat" / ("b" * 12)).mkdir(parents=True)
    (h / "ayat" / ("b" * 12) / "broken.json").write_text("{not json", encoding="utf-8")
    v = header_b_view(tmp_path)
    assert v["projection"]["created_at"] == "2026-10-27T00:00:00Z"
    assert v["stored_counts"] == {"pasal": HEADER_SAMPLE_PER_GRANULARITY + 3, "ayat": 1, "fixed_size": 0}
    assert [s["chunk_id"] for s in v["samples"]] == [f"c{i:02d}" for i in range(HEADER_SAMPLE_PER_GRANULARITY)]
    assert set(v["samples"][0]) == {"chunk_id", "granularity", "header", "tokens_local", "prompt_version", "run_id"}
