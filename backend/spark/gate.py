"""Gerbang angka berlabel laporan (H-057, O-5): hanya record `provider == "meta"` yang boleh jadi angka laporan."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .budget import is_off_pin
from .errors import NotReportable
from .runrecord import RunRecord


def require_reportable(records: Iterable[RunRecord | Mapping[str, Any]],
                       model_config: Mapping[str, Any] | None = None) -> None:
    """Lolos (None) atau `NotReportable`. Tidak mengubah record."""
    flagged_off: set[str] = set()
    if model_config is not None:
        profiles = model_config.get("profiles", {})
        by_provider: dict[str, list[bool]] = {}
        for p in profiles.values():
            by_provider.setdefault(p.get("provider"), []).append(bool(p.get("for_reported_numbers", False)))
        flagged_off = {prov for prov, flags in by_provider.items() if not any(flags)}
    for r in records:
        provider = r.provider if isinstance(r, RunRecord) else r.get("provider")
        if provider == "openrouter":
            raise NotReportable("records from profile openrouter_dev are dev/test only and cannot back "
                                "reported numbers (H-057)")
        if provider != "meta":
            raise NotReportable(f"records with provider '{provider}' are not reportable here (H-057, H-047)")
        if provider in flagged_off:
            raise NotReportable("profile is not marked for_reported_numbers in config/model (H-057)")
        # H-102 P13/S9: dengan `model_config`, rekaman `meta` ber-effort bukan effort efektif jalur utama (off-pin; juga
        # kind `grid` lewat himpunan effort profil) bukan angka laporan. Tanpa `model_config` = perilaku basis persis.
        if model_config is not None and is_off_pin(r, model_config, grid_by_set=True):
            raise NotReportable("record effort is not the main-path effort of its profile in config/model; "
                                "sweep records cannot back reported numbers (H-102)")
