"""Pembaca konfigurasi berversi (TOML, tomllib; H-022, docs/ARCHITECTURE.md §7)."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


class ConfigError(Exception):
    """Konfigurasi hilang atau tidak sah."""


def load(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    """Muat `config/<name>.toml`. Setiap berkas wajib punya field `version`."""
    path = (config_dir or CONFIG_DIR) / f"{name}.toml"
    try:
        data = tomllib.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path.name}") from exc
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"config file is not valid UTF-8 TOML: {path.name}: {exc}") from exc
    if "version" not in data:
        raise ConfigError(f"config file has no 'version' field: {path.name}")
    return data


def config_hash(configs: dict[str, dict[str, Any]]) -> str:
    """Hash isi kanonik semua berkas konfigurasi yang dibaca run (ARCHITECTURE §7)."""
    canonical = json.dumps(configs, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
