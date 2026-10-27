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


def test_model_ids_are_contributor_only():
    # H-028: semua profil Contributor, kecuali pembanding peran C (H-060: Spark Open di Baseten),
    # dan Glimmer lokal (H-047, M2.5), yang hanya boleh peran C dan tidak pernah untuk angka yang dilaporkan.
    m = config.load("model")
    comparators = {"meta-models/muse-spark-open-1026", "meta/muse-glimmer"}
    for prof in m["profiles"].values():
        if prof["model"] in comparators:
            assert prof["roles"] == ["c"] and prof["for_reported_numbers"] is False
            continue
        assert prof["model"].endswith("muse-spark-1.3-contributor")
    assert m["profiles"][m["default_profile"]]["model"] == "muse-spark-1.3-contributor"
