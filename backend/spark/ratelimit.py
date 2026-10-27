"""Pembatas laju jendela geser 60 s (T4, G-19, O-10).

Awal-request di jendela mana pun [s, s+60) paling banyak `max_rpm`. Satu pembatas per proses untuk
setiap (profil, key); key hanya masuk sebagai sidik SHA-256 (tidak pernah disimpan mentah)."""

from __future__ import annotations

import hashlib
import threading
from collections import deque
from collections.abc import Callable

WINDOW_S = 60.0
MAX_RPM_EXCLUSIVE = 150  # Contributor 150 RPM (G-19); config wajib di bawahnya.


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._starts: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, max_rpm: int, now: Callable[[], float], sleep: Callable[[float], None]) -> float:
        """Blok (lewat `sleep`) sampai satu awal-request boleh jalan; kembalikan waktu awal."""
        while True:
            with self._lock:
                t = now()
                while self._starts and self._starts[0] + WINDOW_S <= t:
                    self._starts.popleft()
                if len(self._starts) < max_rpm:
                    self._starts.append(t)
                    return t
                wait = self._starts[0] + WINDOW_S - t
            sleep(wait if wait > 0 else 0.0)


_registry: dict[tuple[str, str], SlidingWindowLimiter] = {}
_registry_lock = threading.Lock()


def get_limiter(profile: str, api_key: str) -> SlidingWindowLimiter:
    fp = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    with _registry_lock:
        lim = _registry.get((profile, fp))
        if lim is None:
            lim = _registry[(profile, fp)] = SlidingWindowLimiter()
        return lim


def reset_registry() -> None:
    """Untuk test: kosongkan semua pembatas proses."""
    with _registry_lock:
        _registry.clear()
