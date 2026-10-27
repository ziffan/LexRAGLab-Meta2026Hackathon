"""Perlengkapan uji M2.5: profil Glimmer lokal dan Baseten Open dalam config uji, badan balasan Chat Completions."""

from __future__ import annotations

import json
from typing import Any

from .spark_fakes import env_ok, model_cfg

GLIMMER_URL = "http://127.0.0.1:8080/v1"
BASETEN_BASE = "https://fake-baseten.invalid/v1"


def m25_model_cfg() -> dict:
    m = model_cfg()
    m["profiles"]["glimmer_local"] = {
        "provider": "lmstudio_local", "api": "chat_completions", "model": "meta/muse-glimmer", "base_url": GLIMMER_URL,
        "quantization": "Q4_K_M", "context_length": 131072, "reasoning_effort": "high", "timeout_s": 900,
        "max_retries": 0, "max_output_tokens": 16000, "for_reported_numbers": False, "roles": ["c"],
        "label": "Glimmer (local)"}
    m["profiles"]["baseten_open"] = {
        "provider": "baseten", "model": "meta-models/muse-spark-open-1026", "base_url_env": "BASETEN_BASE_URL",
        "api_key_env": "BASETEN_API_KEY", "for_reported_numbers": False, "roles": ["c"], "max_output_tokens": 6000,
        "label": "Spark Open (Baseten)"}
    m["profiles"]["b_only"] = {"provider": "baseten", "model": "x", "base_url_env": "BASETEN_BASE_URL",
                               "api_key_env": "BASETEN_API_KEY", "for_reported_numbers": False, "roles": ["b"]}
    m["pricing"]["glimmer_local"] = {"input_per_mtok_micros": 0, "cached_per_mtok_micros": 0, "output_per_mtok_micros": 0}
    m["pricing"]["baseten_open"] = {"input_per_mtok_micros": 1250000, "cached_per_mtok_micros": 150000,
                                    "output_per_mtok_micros": 4250000}
    return m


def env_m25(**over: str) -> dict:
    return env_ok(BASETEN_API_KEY="BT7Q2M9XK4W8L1C5E3A6ZP0RVD", BASETEN_BASE_URL=BASETEN_BASE, **over)


def chat_body(output: Any, *, prompt_tokens: int = 900, completion_tokens: int = 1500, cached: int = 0,
              finish: str = "stop", text: str | None = None) -> dict:
    content = text if text is not None else json.dumps(output)
    return {"id": "chatcmpl-synth", "object": "chat.completion", "model": "meta/muse-glimmer",
            "choices": [{"index": 0, "finish_reason": finish,
                         "message": {"role": "assistant", "content": content, "reasoning_content": "synthetic thinking"}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                      "total_tokens": prompt_tokens + completion_tokens,
                      "prompt_tokens_details": {"cached_tokens": cached}}}
