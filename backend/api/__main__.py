"""Jalankan backend: `uv run python -m backend.api [--port 8000]`. Host terkunci 127.0.0.1 (AGENTS.md)."""

from __future__ import annotations

import argparse

import uvicorn

from .app import create_app

HOST = "127.0.0.1"  # tidak dapat dikonfigurasi: backend tidak pernah dibuka ke jaringan


def main() -> None:
    ap = argparse.ArgumentParser(description="LexRAGLab backend (127.0.0.1 only)")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run(create_app(warm_index=True), host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
