"""Galat pemuat korpus. `code` = nomor aturan penolakan (R1-R13, docs/DATA-CONTRACTS.md §2)."""

from __future__ import annotations


class CorpusError(Exception):
    """Berkas korpus ditolak. `code` mis. "R2"; `message` bahasa Inggris, menyebut jalur/baris/sebab."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
