"""R1 `GET /api/health` dan R6 `GET /api/runs` (docs/API.md §2). Respons tidak pernah memuat key atau base URL."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from backend.api.errors import ApiError
from backend.spark import ConfigInvalid, Ledger, local_server, store
from backend.spark.budget import pool_spend, provider_caps
from backend.spark.runrecord import KINDS, RunRecord
from backend.spark.settings import API_CHAT, clean_env_value, profile_api

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

router = APIRouter()


def _local_probe(request: Request):
    """Pemeriksa server lokal; tes menggantinya lewat `app.state.local_probe(base_url, model) -> (bool, str)`."""
    return getattr(request.app.state, "local_probe", None) or local_server.probe_cached


def profile_status(request: Request, profile: Mapping[str, Any]) -> tuple[bool, str | None]:
    """(available, alasan bila tidak). Profil lokal: server hidup dan model dimuat; replay statis: hasil tersimpan saja."""
    st = request.app.state
    if profile_api(profile) == API_CHAT:
        if st.replay:
            return True, None  # replay: hanya hasil tersimpan (W6 live=false); tanpa probe jaringan
        ok, msg = _local_probe(request)(profile.get("base_url", ""), profile.get("model", ""))
        return ok, None if ok else msg
    ok = _available(profile, st.env)
    return ok, None if ok else "Model API credentials are not configured."


def _available(profile: Mapping[str, Any], env_map: Mapping[str, str]) -> bool:
    if not clean_env_value(env_map.get(profile.get("api_key_env", ""))):
        return False
    if isinstance(profile.get("base_url"), str) and profile["base_url"]:
        return True
    return bool(clean_env_value(env_map.get(profile.get("base_url_env", ""))))


def grid_records(runs_dir: Path) -> list[RunRecord]:
    """RunRecord run grid dari amplop `runs/grid/<kunci>.json`; amplop tanpa record (belum selesai) atau rusak dilewati."""
    out: list[RunRecord] = []
    d = Path(runs_dir) / "grid"
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            rec = json.loads(p.read_bytes().decode("utf-8")).get("record")
            if rec:
                out.append(RunRecord.from_dict(rec))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return out


def all_records(runs_dir: Path) -> list[RunRecord]:
    """Semua RunRecord tersimpan (records + grid), tanpa limit; dipakai R6 dan R1. ValueError bila record rusak."""
    return store.load_records(runs_dir) + grid_records(runs_dir)


def run_cost_micros(runs_dir: Path) -> int | None:
    """Jumlah `cost_usd_micros` seluruh RunRecord (None = 0). Integer micro-USD. None bila record tidak terbaca."""
    try:
        return sum(int(r.cost_usd_micros or 0) for r in all_records(runs_dir))
    except ValueError:
        return None


def ledger_spent_micros(runs_dir: Path) -> int | None:
    """Buku belanja `Ledger.spent()` (`spend_micros` = cost + projected per record; disebut `cost ?? projected` di H-063) atas
    SEMUA pool. Sejak H-104 butir 3 bukan lagi angka header/README (itu `main_results_spent_usd_micros` = pool default);
    tetap di R1 untuk kompatibilitas dan jumlah U8 semua pool. Integer micro-USD. None bila record tidak terbaca."""
    try:
        return Ledger(runs_dir).spent()
    except (ConfigInvalid, ValueError):
        return None


def run_totals_by_kind(runs_dir: Path) -> list[dict[str, Any]] | None:
    """Agregat per jenis run atas SEMUA RunRecord tersimpan (records + grid, tanpa limit R6), untuk tabel per peran U8.
    `spend_usd_micros` = jumlah `spend_micros()` (buku belanja, sama dengan `Ledger.spent` per peran; grid = 0). Token null = 0;
    `unknown_runs` = run dengan salah satu token atau `cost_usd_micros` null. Urutan = `KINDS`. None bila record tidak terbaca."""
    try:
        records = all_records(runs_dir)
    except ValueError:
        return None
    return _totals(records)


def _totals(records: list[RunRecord]) -> list[dict[str, Any]]:
    acc: dict[str, dict[str, Any]] = {}
    for r in records:
        a = acc.setdefault(r.kind, {"kind": r.kind, "runs": 0, "usage_input_tokens": 0, "usage_cached_tokens": 0,
                                    "usage_output_tokens": 0, "spend_usd_micros": 0, "unknown_runs": 0})
        a["runs"] += 1
        a["usage_input_tokens"] += r.usage_input_tokens or 0
        a["usage_cached_tokens"] += r.usage_cached_tokens or 0
        a["usage_output_tokens"] += r.usage_output_tokens or 0
        a["spend_usd_micros"] += r.spend_micros()
        if any(v is None for v in (r.usage_input_tokens, r.usage_cached_tokens, r.usage_output_tokens, r.cost_usd_micros)):
            a["unknown_runs"] += 1
    return [acc[k] for k in KINDS if k in acc]


def cost_fields(runs_dir: Path, budget_cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Bidang biaya R1 dari SATU pembacaan record (5.000+ berkas; pembacaan terpisah membuat R1 > 4 detik).
    Nilai identik dengan `run_cost_micros`, `ledger_spent_micros` (= `Ledger.spent()`: hanya `records/`), `run_totals_by_kind`.
    H-104 butir 3: `pool_spend` = belanja per pool (aturan `Ledger.spent_pool`, `config/budget` `[provider_cap_micros]`) atas
    `records/`; `main_results_spent_usd_micros` = pool `default` (hasil utama Contributor) = angka header U0 dan README.
    Config budget tak sah -> kedua bidang pool None (bidang lain tetap)."""
    try:
        recs = store.load_records(runs_dir)
    except ValueError:
        return {"run_cost_usd_micros": None, "ledger_spent_usd_micros": None, "main_results_spent_usd_micros": None,
                "pool_spend": None, "run_totals_by_kind": None}
    grid = grid_records(runs_dir)
    allr = recs + grid
    try:
        pools: dict[str, int] | None = pool_spend(recs, provider_caps(budget_cfg or {}))
    except ConfigInvalid:
        pools = None
    return {"run_cost_usd_micros": sum(int(r.cost_usd_micros or 0) for r in allr),
            "ledger_spent_usd_micros": sum(r.spend_micros() for r in recs),
            "main_results_spent_usd_micros": None if pools is None else pools["default"],
            "pool_spend": None if pools is None else [{"pool": k, "spend_usd_micros": v} for k, v in pools.items()],
            "run_totals_by_kind": _totals(allr)}


def _profile_row(request: Request, name: str, p: Mapping[str, Any]) -> dict[str, Any]:
    available, reason = profile_status(request, p)
    st = request.app.state
    effort = p.get("reasoning_effort") or st.model_config.get("effort", {}).get("c")
    return {"model_profile": name, "model": p.get("model"), "available": available,
            "label": p.get("label") or name, "provider": p.get("provider"), "quantization": p.get("quantization"),
            "effort": effort, "roles": list(p.get("roles") or []), "local": profile_api(p) == API_CHAT, "live_via_cli": bool(p.get("live_via_cli")),
            "unavailable_reason": reason}


@router.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    st = request.app.state
    profiles = st.model_config.get("profiles", {})
    default = st.model_config.get("default_profile")
    return {
        "status": "ok",
        "replay": st.replay,
        "model": profiles.get(default, {}).get("model"),
        "config_hash": st.config_hash,
        **cost_fields(st.service.runs_dir, getattr(st, "budget_config", None)),
        "model_profiles": [_profile_row(request, name, p) for name, p in profiles.items()],
    }


@router.get("/api/runs")
def runs_list(request: Request, kind: str | None = None, limit: str | None = None):
    if kind is not None and kind not in KINDS:
        raise ApiError(400, "invalid_request", "kind must be one of: " + ", ".join(KINDS))
    n = DEFAULT_LIMIT
    if limit is not None:
        if not limit.isascii() or not limit.isdigit() or not (1 <= int(limit) <= MAX_LIMIT):
            raise ApiError(400, "invalid_request", f"limit must be an integer between 1 and {MAX_LIMIT}")
        n = int(limit)
    runs = request.app.state.service.runs_dir
    try:
        records = all_records(runs)
    except ValueError:
        raise ApiError(500, "model_error", "stored run records are unreadable") from None
    if kind is not None:
        records = [r for r in records if r.kind == kind]
    records.sort(key=lambda r: (r.created_at, r.run_id), reverse=True)
    return [r.to_dict() for r in records[:n]]
