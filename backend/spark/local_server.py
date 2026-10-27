"""Cek ketersediaan server model lokal (Glimmer, H-047): `GET <base_url>/models` memuat model ID.

Hanya loopback; base_url lain ditolak tanpa jaringan. Tidak memuat atau mengubah model di server (LM Studio).
Hasil dicache singkat supaya `GET /api/health` yang sering dipanggil tidak membanjiri server."""

from __future__ import annotations

import time
from typing import Any

import httpx2

from .settings import is_loopback_url

PROBE_TIMEOUT_S = 1.5
CACHE_TTL_S = 5.0
_cache: dict[tuple[str, str], tuple[float, tuple[bool, str]]] = {}


def probe_models(base_url: str, model: str, *, timeout: float = PROBE_TIMEOUT_S, transport: Any = None) -> tuple[bool, str]:
    """(tersedia, pesan). Pesan Inggris, tanpa URL penuh."""
    if not is_loopback_url(base_url):
        return False, "Local model server must be on a loopback address (127.0.0.1)."
    try:
        with httpx2.Client(transport=transport, trust_env=False, timeout=timeout) as c:
            r = c.get(base_url.strip().rstrip("/") + "/models")
    except Exception:  # noqa: BLE001 - alasan umum saja
        return False, "Local model server is not running. Start it in LM Studio to enable this model."
    if r.status_code != 200:
        return False, f"Local model server answered HTTP {r.status_code}."
    try:
        ids = [m.get("id") for m in r.json().get("data", []) if isinstance(m, dict)]
    except Exception:  # noqa: BLE001
        return False, "Local model server returned an unreadable model list."
    if model not in ids:
        return False, "The pinned model is not loaded on the local server."
    return True, "Available."


def probe_cached(base_url: str, model: str, *, now: float | None = None, **kw: Any) -> tuple[bool, str]:
    t = time.monotonic() if now is None else now
    key = (base_url, model)
    hit = _cache.get(key)
    if hit is not None and t - hit[0] < CACHE_TTL_S:
        return hit[1]
    res = probe_models(base_url, model, **kw)
    _cache[key] = (t, res)
    return res
