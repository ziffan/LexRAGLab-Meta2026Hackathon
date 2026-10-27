"""Galat klien Spark (M0.1). Pesan tidak pernah memuat key, base URL, atau stack trace."""

from __future__ import annotations

from backend.config import ConfigError


class ConfigInvalid(ConfigError):
    """Konfigurasi, env, atau argumen panggilan tidak sah. Dilempar sebelum jaringan (O-2)."""

    code = "config_invalid"


class BudgetExceeded(Exception):
    """Proyeksi atau belanja melewati cap (T6). Dilempar sebelum panggilan jaringan."""

    code = "budget_exceeded"


class UsageInvalid(ValueError):
    """`usage` dari server rusak atau hilang (S5)."""

    code = "usage_invalid"


class NotReportable(ValueError):
    """Record bukan sumber angka berlabel laporan (H-057, O-5)."""
