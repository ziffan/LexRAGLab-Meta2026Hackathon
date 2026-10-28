"""Kunci lintas proses runner sapuan Contributor (H-102 P9, S18 (d)): `runs/locks/model_api_meta.lock`.

Pola `backend/gpulock.py` (`{pid, holder, started_at}`, dibuat atomik lewat `os.link`, kedaluwarsa hanya dihapus lewat
`break_stale=True`). Dua runner sapuan Contributor tidak boleh berjalan bersamaan (RPM Model API bersama, G-19):
yang kedua ditolak `rpm_lock_busy` SEBELUM request apa pun. Jalur utama (backend live) TIDAK mengambil kunci ini
(byte-identik); prosedur operator mencegah live utama berbarengan. `runs/locks/` di luar semua direktori yang di-hash."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend import gpulock

LOCK_RELPATH = Path("locks") / "model_api_meta.lock"
HOLDERS = ("sweep-b", "sweep-a", "sweep-c", "sweep-grid")


class RpmLockError(Exception):
    code = "rpm_lock_error"


class RpmLockBusy(RpmLockError):
    code = "rpm_lock_busy"

    def __init__(self, holder: Any, pid: Any) -> None:
        super().__init__(f"rpm_lock_busy: the Model API rate window is held by '{holder}' (pid {pid}); wait until it finishes")
        self.holder, self.pid = holder, pid


class RpmLockStale(RpmLockError):
    code = "rpm_lock_stale"

    def __init__(self, path: Path, holder: Any, pid: Any, why: str) -> None:
        super().__init__(f"rpm_lock_stale: {why} (holder '{holder}', pid {pid}); delete {path} or pass --break-stale-lock")
        self.holder, self.pid, self.path = holder, pid, path


def lock_path(runs_dir: Path) -> Path:
    return Path(runs_dir) / LOCK_RELPATH


def _judge(path: Path, cur: dict[str, Any], pid_alive: Callable[[int], bool] | None) -> RpmLockError:
    if cur.get("_invalid"):
        return RpmLockStale(path, None, None, "the lock file is unreadable")
    if (pid_alive or gpulock.default_pid_alive)(cur["pid"]):
        return RpmLockBusy(cur["holder"], cur["pid"])
    return RpmLockStale(path, cur["holder"], cur["pid"], "the holder process is not running")


def acquire(runs_dir: Path, holder: str, *, pid: int | None = None, pid_alive: Callable[[int], bool] | None = None,
            break_stale: bool = False, now: Callable[[], str] = gpulock.utc_now) -> gpulock.GpuLock:
    """Ambil kunci. Dipegang: pid hidup -> `RpmLockBusy`; pid mati -> `RpmLockStale` (kecuali `break_stale`).
    Mengembalikan objek berpola `GpuLock` (`release()`, context manager, `broke_stale`)."""
    if holder not in HOLDERS:
        raise ValueError(f"holder must be one of {list(HOLDERS)}")
    path = lock_path(runs_dir)
    me = os.getpid() if pid is None else pid
    started = now()
    body = (json.dumps({"pid": me, "holder": holder, "started_at": started}, sort_keys=True) + "\n").encode("utf-8")
    broke: dict[str, Any] | None = None
    for _ in range(2):
        try:
            gpulock._link_exclusive(path, body)
            return gpulock.GpuLock(path, holder, me, started, broke)
        except FileExistsError:
            cur = gpulock.read_lock(path)
            if cur is None:
                continue
            err = _judge(path, cur, pid_alive)
            if isinstance(err, RpmLockStale) and break_stale:
                broke = {"holder": cur.get("holder"), "pid": cur.get("pid"), "started_at": cur.get("started_at")}
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                continue
            raise err from None
    raise RpmLockBusy("unknown", None)
