from pathlib import Path

import pytest

from backend import config


def test_all_config_files_load_with_version():
    names = sorted(p.stem for p in config.CONFIG_DIR.glob("*.toml"))
    assert names, "config/ is empty"
    for name in names:
        assert "version" in config.load(name)


def test_missing_config_is_clear_error(tmp_path: Path):
    with pytest.raises(config.ConfigError, match="not found"):
        config.load("nope", config_dir=tmp_path)


def test_config_without_version_rejected(tmp_path: Path):
    (tmp_path / "x.toml").write_bytes(b"a = 1\n")
    with pytest.raises(config.ConfigError, match="version"):
        config.load("x", config_dir=tmp_path)


def test_config_hash_is_order_independent():
    assert config.config_hash({"a": {"x": 1, "y": 2}}) == config.config_hash({"a": {"y": 2, "x": 1}})


VOICE_QA_MODEL = "muse-voice-transcribe-1.0"  # H-113: pemeriksa VO video saja


def check_model_ids(m: dict) -> None:
    # H-028: semua profil Contributor, kecuali pembanding (H-060: Spark Open di Baseten; H-047, M2.5: Glimmer lokal),
    # yang memuat peran C, hanya boleh C/A/B (H-100; tidak pernah D, verifier, penilai) dan tidak pernah untuk angka laporan.
    # H-113: tepat satu profil Muse Voice Transcribe, hanya peran `voice_qa`, api `asr_transcribe`, tidak untuk angka laporan.
    comparators = {"meta-models/muse-spark-open-1026", "meta/muse-glimmer"}
    voice = [n for n, p in m["profiles"].items() if p["model"] == VOICE_QA_MODEL]
    assert len(voice) == 1
    for prof in m["profiles"].values():
        if prof["model"] in comparators:
            assert "c" in prof["roles"] and set(prof["roles"]) <= {"a", "b", "c"}
            assert prof["for_reported_numbers"] is False
            continue
        if prof["model"] == VOICE_QA_MODEL:
            assert prof["roles"] == ["voice_qa"] and prof["api"] == "asr_transcribe"
            assert prof["for_reported_numbers"] is False
            continue
        assert prof["model"].endswith("muse-spark-1.3-contributor")
    assert m["profiles"][m["default_profile"]]["model"] == "muse-spark-1.3-contributor"


def test_model_ids_are_contributor_only():
    check_model_ids(config.load("model"))
