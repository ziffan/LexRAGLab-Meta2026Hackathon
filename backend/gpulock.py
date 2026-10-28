"""Kunci GPU eksklusif (H-101 P12 / S16, G-26): Glimmer lokal dan encoder bge-m3 tidak boleh memakai GPU bersamaan.

Berkas `runs/locks/gpu.lock` (di luar semua direktori yang di-hash: `runs/headers*`, `runs/grid*`, `runs/schemas`) memuat
`{pid, holder, started_at}`. Dibuat atomik (tulis berkas sementara lalu `os.link`: gagal bila kunci sudah ada, dan isi sudah
lengkap saat terlihat proses lain). Dilepas saat selesai normal, galat, dan `KeyboardInterrupt` (context manager).
Pemegang yang pid-nya tidak hidup = kunci kedaluwarsa: ditolak `gpu_lock_stale` dan TIDAK dihapus otomatis, kecuali
`break_stale=True` (flag `--break-stale-lock`; pemecahan dicatat di `GpuLock.broke_stale`).
`pid_alive` disuntikkan (test memakai palsu); implementasi default tidak memakai `os.kill(pid, 0)` di Windows."""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HOLDERS = ("glimmer-a", "glimmer-b", "glimmer-c", "embedding")
LOCK_RELPATH = Path("locks") / "gpu.lock"


class GpuLockError(Exception):
    code = "gpu_lock_error"


class GpuBusy(GpuLockError):
    code = "gpu_busy"

    def __init__(self, holder: Any, pid: Any) -> None:
        super().__init__(f"gpu_busy: the GPU is held by '{holder}' (pid {pid}); wait until it finishes")
        self.holder, self.pid = holder, pid


class GpuLockStale(GpuLockError):
    code = "gpu_lock_stale"

    def __init__(self, path: Path, holder: Any, pid: Any, why: str) -> None:
        super().__init__(f"gpu_lock_stale: {why} (holder '{holder}', pid {pid}); delete {path} or pass --break-stale-lock")
        self.holder, self.pid, self.path = holder, pid, path


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_pid_alive(pid: int) -> bool:
    """Apakah proses `pid` masih hidup. Windows: `OpenProcess` + `GetExitCodeProcess` (bukan `os.kill`); POSIX: `os.kill(pid, 0)`."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: ada tetapi tak boleh dibuka
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_path(runs_dir: Path) -> Path:
    return Path(runs_dir) / LOCK_RELPATH


def read_lock(path: Path) -> dict[str, Any] | None:
    """Isi kunci, atau None bila tidak ada. Berkas ada tetapi rusak -> `{"_invalid": True}`."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return {"_invalid": True}
    try:
        d = json.loads(raw.decode("utf-8"))
    except ValueError:
        return {"_invalid": True}
    if not isinstance(d, dict) or not isinstance(d.get("pid"), int) or isinstance(d.get("pid"), bool) \
            or not isinstance(d.get("holder"), str):
        return {"_invalid": True}
    return d


def _judge(path: Path, cur: dict[str, Any], pid_alive: Callable[[int], bool] | None) -> GpuLockError:
    if cur.get("_invalid"):
        return GpuLockStale(path, None, None, "the lock file is unreadable")
    if (pid_alive or default_pid_alive)(cur["pid"]):
        return GpuBusy(cur["holder"], cur["pid"])
    return GpuLockStale(path, cur["holder"], cur["pid"], "the holder process is not running")


def check_free(runs_dir: Path, *, pid_alive: Callable[[int], bool] | None = None) -> None:
    """Tolak lebih awal (tanpa mengambil kunci) bila GPU dipegang: `GpuBusy` atau `GpuLockStale`. Tanpa efek samping."""
    path = lock_path(runs_dir)
    cur = read_lock(path)
    if cur is not None:
        raise _judge(path, cur, pid_alive)


@dataclass
class GpuLock:
    path: Path
    holder: str
    pid: int
    started_at: str
    broke_stale: dict[str, Any] | None = None  # pemegang kedaluwarsa yang dipecahkan (`--break-stale-lock`)
    released: bool = field(default=False, repr=False)

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        cur = read_lock(self.path)
        if cur is not None and cur.get("pid") == self.pid and cur.get("started_at") == self.started_at:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

    def __enter__(self) -> "GpuLock":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


def _link_exclusive(path: Path, body: bytes) -> None:
    """Buat `path` secara eksklusif dengan isi lengkap; `FileExistsError` bila sudah ada."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_bytes(body)
    try:
        os.link(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def acquire(runs_dir: Path, holder: str, *, pid: int | None = None, pid_alive: Callable[[int], bool] | None = None,
            break_stale: bool = False, now: Callable[[], str] = utc_now) -> GpuLock:
    """Ambil kunci. Sudah dipegang: pid hidup -> `GpuBusy`; pid mati -> `GpuLockStale` (kecuali `break_stale`)."""
    if holder not in HOLDERS:
        raise ValueError(f"holder must be one of {list(HOLDERS)}")
    path = lock_path(runs_dir)
    me = os.getpid() if pid is None else pid
    started = now()
    body = (json.dumps({"pid": me, "holder": holder, "started_at": started}, sort_keys=True) + "\n").encode("utf-8")
    broke: dict[str, Any] | None = None
    for _ in range(2):
        try:
            _link_exclusive(path, body)
            return GpuLock(path, holder, me, started, broke)
        except FileExistsError:
            cur = read_lock(path)
            if cur is None:
                continue  # dilepas di antara dua langkah; coba lagi
            err = _judge(path, cur, pid_alive)
            if isinstance(err, GpuLockStale) and break_stale:
                broke = {"holder": cur.get("holder"), "pid": cur.get("pid"), "started_at": cur.get("started_at")}
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                continue
            raise err from None
    raise GpuBusy("unknown", None)
