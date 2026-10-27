"""Galat profil (M4.3). `kind` dipetakan router ke kode galat API (docs/API.md 1)."""

from __future__ import annotations

KINDS = ("validation_failed", "not_found", "invalid_request", "hash_mismatch")


class ProfileError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        assert kind in KINDS
        self.kind, self.message = kind, message
