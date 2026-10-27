"""Pemeriksa isi snapshot statis (H-051, gate M5.2): tanpa key, tanpa path lokal absolut, tanpa host base URL.

Acuan pola: `_kerja/secretscan.py`. Modul ini TIDAK membaca `.env`; nilai rahasia diberikan pemanggil (CLI memakai
`os.environ`, test memakai key palsu). Temuan tidak pernah memuat nilai yang ditemukan: hanya jalur berkas, jenis, offset.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

MIN_SECRET_LEN = 8
PREFIX_LEN = 12  # awalan nilai key yang dianggap bocor (seperti secretscan)

# Jenis -> pola. Backslash di JSON tampil sebagai `\`, jadi pola path Windows menerima satu atau dua.
PATTERNS: dict[str, re.Pattern[str]] = {
    "api_key_pattern": re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{12,}"),
    "local_path_windows": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:(?:\\\\|\\)[^\s\x22\x27\\]"),
    "local_path_posix": re.compile(r"(?<![A-Za-z0-9_.\-])/(?:home|Users|root)/[A-Za-z0-9_.\-]"),
    "host_url": re.compile(r"https?://[A-Za-z0-9.\-]+(?::\d+)?", re.IGNORECASE),
    "local_host": re.compile(r"(?<![A-Za-z0-9.])(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?![A-Za-z0-9.])"),
}


@dataclass(frozen=True)
class Finding:
    path: str
    kind: str
    offset: int

    def __str__(self) -> str:
        return f"{self.path}: {self.kind} @ {self.offset}"


class SnapshotLeak(Exception):
    """Isi snapshot memuat key, path lokal, atau host. `findings` tanpa nilai yang bocor."""

    def __init__(self, findings: list[Finding]):
        super().__init__(f"{len(findings)} finding(s): " + "; ".join(str(f) for f in findings[:10]))
        self.findings = findings


def env_secrets(environ: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """(nilai key, nilai base URL) dari variabel lingkungan proses. Bukan `.env`."""
    keys, urls = [], []
    for name, value in environ.items():
        v = (value or "").strip().strip('"').strip("'")
        if len(v) < MIN_SECRET_LEN:
            continue
        n = name.upper()
        if "KEY" in n:
            keys.append(v)
        elif n.endswith("BASE_URL") or n.endswith("_URL"):
            urls.append(v)
    return keys, urls


def scan_text(text: str, path: str = "<text>", *, secrets: Iterable[str] = (), base_urls: Iterable[str] = ()) -> list[Finding]:
    out: list[Finding] = []
    for s in secrets:
        s = (s or "").strip()
        if len(s) < MIN_SECRET_LEN:
            continue
        for needle in {s, s[:PREFIX_LEN]}:
            i = text.find(needle)
            if i >= 0:
                out.append(Finding(path, "secret_value", i))
                break
    for u in base_urls:
        u = (u or "").strip().rstrip("/")
        if len(u) >= MIN_SECRET_LEN and (i := text.find(u)) >= 0:
            out.append(Finding(path, "base_url_value", i))
    for kind, pat in PATTERNS.items():
        m = pat.search(text)
        if m:
            out.append(Finding(path, kind, m.start()))
    return out


def scan_files(files: Mapping[str, bytes], *, secrets: Iterable[str] = (), base_urls: Iterable[str] = ()) -> list[Finding]:
    secrets, base_urls = list(secrets), list(base_urls)
    out: list[Finding] = []
    for rel in sorted(files):
        out += scan_text(files[rel].decode("utf-8", "replace"), rel, secrets=secrets, base_urls=base_urls)
    return out


def scan_dir(root: Path, *, secrets: Iterable[str] = (), base_urls: Iterable[str] = (),
             suffixes: tuple[str, ...] = (".json", ".html", ".js", ".css", ".txt", ".md", ".map")) -> list[Finding]:
    """Pindai berkas teks di bawah `root`. Dipakai gate M5.2 atas keluaran akhir (data + bundel)."""
    root = Path(root)
    files = {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and p.suffix in suffixes}
    return scan_files(files, secrets=secrets, base_urls=base_urls)
