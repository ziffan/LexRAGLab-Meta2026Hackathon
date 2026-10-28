"""S9 (d) dengan gerbang NYATA (`make_gate`) atas `Ledger` (RunRecord sintetis `synth`), bukan closure buatan test;
P17 (S-3): `[profiles.*]` tidak boleh memuat `max_header_tokens`/`schema_max_length_chars`."""

import copy

import pytest

from backend.header_b import compare as cmp
from backend.header_b.compare_store import compare_store_dir
from backend.spark import ConfigInvalid, Ledger, load_configs
from backend.spark.settings import build_settings

from .h101_helpers import PROMPT12, SizedTok, rig_for, words
from .h101_run import go
from .spark_fakes import env_ok, model_cfg, synth
from .test_h101_compare_run import sized


def _run(tmp_path, target_after_round1):
    log: list[str] = []
    rig = rig_for(tmp_path / str(target_after_round1), "baseten_open",
                  {"CH-U2": [words(41)], "CH-U3": [words(41)], "CH-U4": [words(41)]}, log=log)
    d = compare_store_dir(rig.runs, "baseten_open")
    real = cmp.make_gate("baseten", rig.budget, rig.model, rig.env, rig.runs)
    calls: list[int] = []

    def gate(expected, floor):
        calls.append(floor)
        if len(calls) == 2:  # sesudah ronde 1: genapkan belanja AKTUAL pool baseten ke target lewat RunRecord sintetis
            cur = Ledger(rig.runs).spent_pool("baseten", {"baseten": 20_000_000})
            assert cur <= target_after_round1
            synth(rig.runs, "b", "baseten", target_after_round1 - cur, run_id=f"top-up-{target_after_round1}")
            assert Ledger(rig.runs).spent_pool("baseten", {"baseten": 20_000_000}) == target_after_round1
        return real(expected, floor)

    s = go(rig, sized(4), d, tokenizer=SizedTok(), gate=gate, max_attempts=8)
    return s, calls, rig, d


def test_s9d_real_gate_over_ledger_round_two_boundary(tmp_path):
    s, calls, rig, _ = _run(tmp_path, 15_828_500)  # + 171.500 = 16.000.000: ronde 2 jalan
    assert calls[:2] == [4 * 31_875 + 75_875, 3 * 31_875 + 75_875]
    assert rig.tr.calls > 5  # ronde 2 benar-benar jalan (belanja aktualnya sendiri membuat gerbang ronde 3 menolak)
    assert len(calls) == 3 and s["stopped"] == "gate_rejected"
    s2, calls2, rig2, d2 = _run(tmp_path, 15_828_501)  # 1 micro-USD lebih: ronde 2 tidak jalan
    assert s2["stopped"] == "gate_rejected" and len(calls2) == 2 and rig2.tr.calls == 5
    assert s2["failed"] == {"uupt-x/pasal": ["CH-U2", "CH-U3", "CH-U4"]} and s2["stored"] == 1
    assert [p.stem for p in (d2 / "pasal" / PROMPT12).glob("*.json")] == ["CH-U1"]


# ---------------------------------------------------------------- P17 (S-3)

@pytest.mark.parametrize("key", ["max_header_tokens", "schema_max_length_chars"])
def test_p17_forbidden_profile_keys_rejected_by_loader_path(key):
    m = model_cfg()
    m["profiles"]["meta"][key] = 1000
    with pytest.raises(ConfigInvalid, match=key):
        build_settings("meta", m, env_ok())
    with pytest.raises(ConfigInvalid, match=key):  # profil lain yang dibangun pun menolak (seluruh config/model)
        build_settings("openrouter_dev", m, env_ok())


def test_p17_unknown_key_ignored_and_real_config_loads():
    m = model_cfg()
    m["profiles"]["meta"]["some_unknown_key"] = "x"
    assert build_settings("meta", m, env_ok()).provider == "meta"
    model, _ = load_configs()
    for name in model["profiles"]:
        assert not {"max_header_tokens", "schema_max_length_chars"} & set(model["profiles"][name]), name
    copy.deepcopy(model)
