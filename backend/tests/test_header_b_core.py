"""M3.1 peran B: skema, validasi semantik, urutan/pemanas/cache, granularitas, proyeksi. Tanpa jaringan."""

import json
import re
from types import SimpleNamespace

import pytest

from backend.header_b.caller import load_header, make_call, run_headers
from backend.header_b.project import project_units
from backend.header_b.prompt import HEADER_B_SCHEMA, load_prompt, schema_hash
from backend.header_b.render import WARM_UNIT, DocPrefix, build_prefix, render_input
from backend.header_b.units import Unit, build_units
from backend.spark.schema_check import check_strict, validate_instance
from backend.tokenizer import get_tokenizer

from .spark_fakes import PRICING, Resp, Rig, body_ok

MAXH = 5


class Tok:
    """Tokenizer palsu: satu token per kata."""

    def count(self, text):
        return len(text.split())


def doc_stub():
    return SimpleNamespace(clean_sha256="c" * 64, text="Pasal 1\n(1) Aaa bbb.\n(2) Ccc ddd.\n")


def responder(header="Konteks singkat", override=None):
    def act(tr, request):
        body = json.loads(request.content.decode("utf-8"))
        cid = re.search(r"chunk_id: (\S+)", body["input"]).group(1)
        out = {"chunk_id": cid, "header": header}
        if override:
            out = override(cid)
        return Resp(200, body_ok(out))
    return act


def setup(tmp_path, **kw):
    prompt = load_prompt(MAXH)
    prefix = build_prefix(prompt, doc_stub(), Tok())
    return Rig(tmp_path, default=responder(**kw)), prompt, prefix


def units():
    return [Unit("id1", "UU X › Pasal 1 › ayat (1)", "Aaa bbb.", 2, ("id1",)),
            Unit("id2", "UU X › Pasal 1 › ayat (2)", "Ccc ddd.", 2, ("id2",))]


def run(rig, prompt, prefix, us, tmp_path, gran="ayat", warm=True):
    return run_headers(rig.client, prompt, prefix, us, granularity=gran, tokenizer=Tok(), headers_dir=tmp_path / "h",
                       max_header_tokens=MAXH, max_output_tokens=1000, max_consecutive_errors=3, meta={}, warm=warm)


def test_schema_is_strict_and_matches_contract():
    assert check_strict(HEADER_B_SCHEMA) is None
    assert HEADER_B_SCHEMA["required"] == ["chunk_id", "header"]
    assert validate_instance({"chunk_id": "a", "header": "b"}, HEADER_B_SCHEMA) is None
    assert validate_instance({"chunk_id": "a", "header": "b", "x": 1}, HEADER_B_SCHEMA) is not None
    assert validate_instance({"chunk_id": "a"}, HEADER_B_SCHEMA) is not None


def test_prompt_hash_depends_on_limit_and_is_rendered():
    a, b = load_prompt(40), load_prompt(41)
    assert "{max_header_tokens}" not in a.template and "40 token" in a.template
    assert a.prompt_hash != b.prompt_hash
    assert a.cache_key_for("d" * 64) != a.cache_key_for("e" * 64)


def test_prefix_is_fixed_and_chunk_comes_last(tmp_path):
    prompt = load_prompt(MAXH)
    prefix = build_prefix(prompt, doc_stub(), Tok())
    a, b = render_input(prefix, units()[0]), render_input(prefix, units()[1])
    assert a.startswith(prefix.text) and b.startswith(prefix.text)
    assert a.index("Aaa bbb.") > a.index("</dokumen-") and f"<data-{prefix.nonce}>\nAaa bbb.\n</data-" in a
    assert doc_stub().text in prefix.text


def test_warmup_then_same_cache_key_and_sequential(tmp_path):
    rig, prompt, prefix = setup(tmp_path)
    res = run(rig, prompt, prefix, units(), tmp_path)
    assert res.stopped_reason is None and len(res.outcomes) == 2
    reqs = rig.tr.requests
    assert len(reqs) == 3
    assert "chunk_id: warmup" in reqs[0]["body"]["input"]
    keys = {r["body"]["prompt_cache_key"] for r in reqs}
    assert keys == {prefix.cache_key}
    assert rig.tr.max_active == 1
    assert all(r["body"]["text"]["format"]["strict"] is True for r in reqs)
    assert [o.unit.key for o in res.outcomes] == ["id1", "id2"]
    h = load_header(tmp_path / "h", "ayat", prompt, "id1")
    assert h == {"chunk_id": "id1", "header": "Konteks singkat", "granularity": "ayat", "prompt_version": "v1",
                 "tokens_local": 2, "run_id": res.outcomes[0].run.run_id}


def test_second_run_is_cache_hit_without_calls(tmp_path):
    rig, prompt, prefix = setup(tmp_path)
    run(rig, prompt, prefix, units(), tmp_path)
    n = len(rig.tr.requests)
    res = run(rig, prompt, prefix, units(), tmp_path)
    assert len(rig.tr.requests) == n
    assert [o.run.status for o in res.outcomes] == ["cached", "cached"] and res.warm.status == "cached"


def test_different_chunk_id_rejected_and_not_cached(tmp_path):
    rig, prompt, prefix = setup(tmp_path, override=lambda cid: {"chunk_id": "lain", "header": "ok"})
    res = run(rig, prompt, prefix, units(), tmp_path)  # pemanas: chunk_id 'lain' != 'warmup' -> berhenti
    assert res.stopped_reason == "warm_failed" and not res.outcomes
    rig2, prompt, prefix = setup(tmp_path / "b", override=lambda cid: {"chunk_id": cid if cid == "warmup" else "lain", "header": "ok"})
    res = run(rig2, prompt, prefix, units(), tmp_path / "b")
    assert [o.error["code"] for o in res.outcomes] == ["semantic_invalid"] * 2
    assert load_header(tmp_path / "b" / "h", "ayat", prompt, "id1") is None


def test_too_long_header_rejected(tmp_path):
    rig, prompt, prefix = setup(tmp_path, header="satu dua tiga empat lima enam")  # 6 kata > 5
    res = run(rig, prompt, prefix, units(), tmp_path, warm=False)
    assert res.outcomes and all(o.error and o.error["code"] == "semantic_invalid" for o in res.outcomes)
    assert res.stopped_reason is None and not any(o.headers for o in res.outcomes)


def test_consecutive_errors_stop_the_run(tmp_path):
    rig, prompt, prefix = setup(tmp_path, header="satu dua tiga empat lima enam")
    us = [Unit(f"i{n}", "a", "t", 1, (f"i{n}",)) for n in range(6)]
    res = run(rig, prompt, prefix, us, tmp_path, warm=False)
    assert res.stopped_reason == "too_many_errors" and len(res.outcomes) == 3 and len(rig.tr.requests) == 3


def test_pasal_unit_header_is_shared_by_all_member_chunks(tmp_path):
    rig, prompt, prefix = setup(tmp_path)
    u = Unit("p1a", "UU X › Pasal 1", "Aaa bbb. Ccc ddd.", 4, ("p1a", "p1b", "p1c"))
    res = run(rig, prompt, prefix, [u], tmp_path, gran="pasal")
    assert [h["chunk_id"] for h in res.outcomes[0].headers] == ["p1a", "p1b", "p1c"]
    assert len({h["header"] for h in res.outcomes[0].headers}) == 1
    assert len(rig.tr.requests) == 2  # pemanas + satu panggilan untuk Pasal, bukan tiga
    for cid in ("p1a", "p1b", "p1c"):
        assert load_header(tmp_path / "h", "pasal", prompt, cid)["granularity"] == "pasal"


def test_call_args_est_input_covers_prefix(tmp_path):
    prompt = load_prompt(MAXH)
    prefix = build_prefix(prompt, doc_stub(), Tok())
    a = make_call(prompt, prefix, units()[0], Tok(), max_header_tokens=MAXH, max_output_tokens=1000, meta={})
    assert a["est_input"] > prefix.tokens and a["role"] == "b" and a["schema_hash"] == schema_hash()
    w = make_call(prompt, prefix, WARM_UNIT, Tok(), max_header_tokens=MAXH, max_output_tokens=1000, meta={})
    assert w["max_output_tokens"] == 300


def test_projection_hand_computed_micro_usd():
    class Const:
        def count(self, text):
            return 10

    prefix = DocPrefix(text="x", nonce="n", tokens=1000, cache_key="k")
    us = [Unit(f"u{i}", "a", "t", 5, (f"u{i}",)) for i in range(3)]
    pr = {"input": PRICING["input_per_mtok_micros"], "cached": PRICING["cached_per_mtok_micros"],
          "output": PRICING["output_per_mtok_micros"]}
    p = project_units(us, prefix, Const(), pr, rpm=60, expected_output_tokens=450, max_output_tokens=1000,
                      assumed_latency_ms=3000)
    # pemanas: 1010*0.1 + 300*0.2 = 161. expected/panggilan: 10*0.1 + 1000*0.002 + 450*0.2 = 93.
    assert p["cost_usd_micros"] == {"expected": 161 + 3 * 93, "upper_cached": 161 + 3 * 203, "upper_no_cache": 161 + 3 * 301}
    assert p["calls"] == 4 and p["units"] == 3 and p["source_tokens_total"] == 15
    assert p["time"] == {"rpm_floor_seconds": 4, "sequential_seconds": 12, "estimated_seconds": 12}


@pytest.fixture(scope="module")
def real():
    from backend import config
    from backend.corpus import load_corpus
    return load_corpus("uupt-40-2007"), get_tokenizer(), config.load("retrieval"), config.load("grid")


def test_real_corpus_sources(real):
    doc, tok, rc, gc = real
    ay = build_units(doc, "ayat", tokenizer=tok, retrieval_cfg=rc, grid_cfg=gc)
    pa = build_units(doc, "pasal", tokenizer=tok, retrieval_cfg=rc, grid_cfg=gc)
    fx = build_units(doc, "fixed_size", tokenizer=tok, retrieval_cfg=rc, grid_cfg=gc)
    assert all(len(u.chunk_ids) == 1 and u.chunk_ids[0] == u.key for u in ay)
    assert len(ay) == 1070 and len(fx) == 103 and len(pa) < len(ay)
    members = [c for u in pa for c in u.chunk_ids]
    assert sorted(members) == sorted(u.key for u in ay) and len(set(members)) == len(members)
    assert any(len(u.chunk_ids) > 1 for u in pa)
    assert all(u.key == u.chunk_ids[0] for u in pa)
    big = next(u for u in pa if len(u.chunk_ids) > 1)
    assert "Pasal" in big.address and " › ayat" not in big.address.lower()
