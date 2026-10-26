import pytest

from backend import config, tokenizer


def test_tokenizer_is_deterministic_and_named():
    tok = tokenizer.get_tokenizer()
    text = "Perseroan Terbatas adalah badan hukum."
    assert tok.count(text) == tok.count(text) > 0
    assert tok.info.name and tok.info.version


def test_primary_tokenizer_present_on_dev_machine():
    cfg = config.load("tokenizer")
    sec = cfg[cfg["primary"]]
    path = tokenizer.hf_snapshot_file(sec["hf_repo"], sec["hf_revision"], "tokenizer.json")
    if not path.is_file():
        pytest.skip("H-014 tokenizer not in local HF cache; fallback is used")
    assert path.stat().st_size > 1_000_000
    tok = tokenizer.get_tokenizer()
    assert tok.info.name == cfg["primary"]
    offs = tok.offsets("Pasal 1 ayat (2)")
    assert offs[0][0] == 0 and offs[-1][1] == len("Pasal 1 ayat (2)")
