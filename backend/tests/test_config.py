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
    m = config.load("model")
    for prof in m["profiles"].values():
        assert prof["model"].endswith("muse-spark-1.3-contributor")
