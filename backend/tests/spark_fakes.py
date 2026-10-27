"""Perlengkapan uji klien Spark (docs/scenarios/M0.1.md "Perlengkapan uji bersama").

Transport palsu di batas HTTP di bawah SDK `openai`, jam dan sleep palsu. Nol jaringan; key palsu
sintetis; tidak membaca `.env` asli."""

from __future__ import annotations

import copy
import json
import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2

from backend.spark import RunRecord, SparkClient, store
from backend.spark.runrecord import kind_for_role, utc_iso

K = "ZXQJ7K2M4F8A91C3E5B7Q9W2LP"
K2 = "OR7H3N8V1D5S2Y6T0U4B9GCXEA"
BASE = "https://fake-host.invalid/v1"
HOST = "fake-host.invalid"

SCHEMA_X = {
    "type": "object",
    "additionalProperties": False,
    "required": ["jawaban", "kutipan", "status"],
    "properties": {
        "jawaban": {"type": "string"},
        "kutipan": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string"},
    },
}
OUT_OK = {"jawaban": "x", "kutipan": [], "status": "tolak"}
USAGE1 = {"input_tokens": 3247, "input_tokens_details": {"cached_tokens": 0},
          "output_tokens": 445, "output_tokens_details": {"reasoning_tokens": 370}}
USAGE2 = {"input_tokens": 3247, "input_tokens_details": {"cached_tokens": 3185},
          "output_tokens": 452, "output_tokens_details": {"reasoning_tokens": 377}}
PRICING = {"input_per_mtok_micros": 100000, "cached_per_mtok_micros": 2000, "output_per_mtok_micros": 200000}


def body_ok(output: Any = OUT_OK, usage: Any = USAGE1, status: str = "completed", text: str | None = None,
            **extra: Any) -> dict:
    txt = text if text is not None else json.dumps(output)
    b: dict[str, Any] = {
        "id": "resp_synth", "object": "response", "status": status,
        "output": [{"type": "reasoning", "id": "rs_1", "summary": []},
                   {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": txt, "annotations": []}]}],
    }
    if usage is not None:
        b["usage"] = usage
    b.update(extra)
    return b


class Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


@dataclass
class Resp:
    status: int = 200
    json: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    text: str | None = None
    advance: float = 0.0


@dataclass
class Timeout:
    message: str = "timed out"
    kind: str = "httpx"  # "httpx" | "builtin"
    advance: float = 0.0


class FakeTransport:
    """Naskah balasan per request. Habis naskah -> balasan `default` (bawaan: 200 sukses usage S1)."""

    def __init__(self, clock: Clock, script: list[Any] | None = None, default: Any = "ok") -> None:
        self.clock = clock
        self.script = list(script or [])
        self.default = default
        self.requests: list[dict[str, Any]] = []
        self.active = 0
        self.max_active = 0
        self.transport = httpx2.MockTransport(self._handle)

    @property
    def calls(self) -> int:
        return len(self.requests)

    @property
    def starts(self) -> list[float]:
        return [r["t"] for r in self.requests]

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            try:
                body = json.loads(request.content.decode("utf-8")) if request.content else None
            except ValueError:
                body = None
            t = request.extensions.get("timeout") or {}
            self.requests.append({"t": self.clock.t, "method": request.method, "path": request.url.path,
                                  "headers": dict(request.headers), "body": body, "timeout": t,
                                  "input": (body or {}).get("input")})
            action = self.script.pop(0) if self.script else self.default
            if callable(action):
                action = action(self, request)
            if action == "ok":
                action = Resp(200, body_ok())
            if isinstance(action, Timeout):
                self.clock.t += action.advance
                if action.kind == "builtin":
                    raise TimeoutError(action.message)
                raise httpx2.ReadTimeout(action.message)
            assert isinstance(action, Resp), action
            self.clock.t += action.advance
            if action.text is not None:
                return httpx2.Response(action.status, text=action.text, headers=action.headers)
            return httpx2.Response(action.status, json=action.json, headers=action.headers)
        finally:
            self.active -= 1


def model_cfg() -> dict:
    return copy.deepcopy({
        "version": 1, "default_profile": "meta", "host": "authoritative",
        "profiles": {
            "meta": {"provider": "meta", "model": "muse-spark-1.3-contributor", "base_url_env": "MUSE_BASE_URL",
                     "api_key_env": "MUSE_API_KEY", "for_reported_numbers": True},
            "meta2": {"provider": "meta2", "model": "muse-spark-1.3-contributor", "base_url_env": "MUSE_BASE_URL", "pricing": "meta",
                      "api_key_env": "MUSE_API_KEY", "for_reported_numbers": True},
            "openrouter_dev": {"provider": "openrouter", "model": "meta/muse-spark-1.3-contributor",
                               "base_url": "https://fake-openrouter.invalid/api/v1", "pricing": "meta",
                               "api_key_env": "OPENROUTER_API_KEY", "for_reported_numbers": False},
        },
        "effort": {"a": "low", "b": "low", "c": "low", "d": "low", "measure": "low"},
        "pricing": {"meta": dict(PRICING)},
        "limits": {"max_rpm": 140, "timeout_s": 120, "max_retries": 1, "backoff_base_s": 2,
                   "backoff_factor": 2, "max_429_retries": 3, "max_wait_s": 120},
    })


def budget_cfg(total: int = 10_000_000, role: int = 10_000_000, roles: tuple[str, ...] = ("a", "b", "c", "d", "measure")) -> dict:
    return {"version": 1, "dev_total_cap_micros": total, "per_role_cap_micros": {r: role for r in roles}}


def env_ok(**over: str) -> dict:
    e = {"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE, "OPENROUTER_API_KEY": K2}
    e.update(over)
    return e


def call_args(n: int = 0, **over: Any) -> dict:
    a = dict(role="c", prompt_version="c-v1", prompt_hash="PH1", input=f"Pasal 1 (1) Aaa bbb. (2) Ccc. #{n}",
             schema=SCHEMA_X, schema_name="SchemaX", schema_hash="SH1", prompt_cache_key="pck-synth-1",
             max_output_tokens=800, est_input=100,
             meta={"corpus_hash": "CH1", "clean_sha256": "CS1", "loader_rules_version": "LR1",
                   "tokenizer": {"name": "tok-fake", "version": "0"}})
    a.update(over)
    return a


class Rig:
    """Klien + transport + jam + direktori runs/ uji."""

    def __init__(self, tmp_path: Path, *, profile: str = "meta", script: list[Any] | None = None, default: Any = "ok",
                 model: dict | None = None, budget: dict | None = None, env: dict | None = None,
                 clock: Clock | None = None, replay: bool = False, transport: FakeTransport | None = None,
                 logger: logging.Logger | None = None) -> None:
        self.runs = tmp_path / "runs"
        self.clock = clock or Clock()
        self.tr = transport or FakeTransport(self.clock, script, default)
        self.model = model or model_cfg()
        self.budget = budget or budget_cfg()
        self.env = env if env is not None else env_ok()
        self.profile = profile
        self.replay = replay
        self.logger = logger
        self.client = self.new_client()

    def new_client(self, profile: str | None = None, env: dict | None = None) -> SparkClient:
        return SparkClient(profile or self.profile, model_config=self.model, budget_config=self.budget,
                           env=env if env is not None else self.env, runs_dir=self.runs,
                           transport=self.tr.transport, now=self.clock.now, sleep=self.clock.sleep,
                           replay=self.replay, logger=self.logger)


def scan_text(text: str, with_k2: bool = False) -> list[str]:
    needles = [K, K[:8], K[-6:], "Bearer " + K, HOST]
    if with_k2:
        needles += [K2, K2[:8], K2[-6:], "Bearer " + K2]
    return [n for n in needles if n in text]


def scan_runs_dir(runs: Path, with_k2: bool = False) -> list[str]:
    found: list[str] = []
    if not runs.exists():
        return found
    for p in runs.rglob("*"):
        found += scan_text(str(p.relative_to(runs)), with_k2)
        if p.is_file():
            found += scan_text(p.read_text(encoding="utf-8", errors="replace"), with_k2)
    return found


def scan_exception(exc: BaseException, with_k2: bool = False) -> list[str]:
    parts = [str(exc), repr(exc), repr(exc.args), "".join(traceback.format_exception(exc))]
    return [h for p in parts for h in scan_text(p, with_k2)]


def scan_result(res: Any, with_k2: bool = False) -> list[str]:
    return scan_text(res.record.to_json() + repr(res.record) + str(res.record), with_k2)


def synth(runs, role, provider, cost, *, status="ok", run_id=None, projected=None):
    rid = run_id or f"syn-{role}-{provider}-{cost}-{status}"
    rec = RunRecord(run_id=rid, kind=kind_for_role(role), created_at=utc_iso(1000.0), cache_key="k", corpus_hash=None,
                    config_hash="CFG", clean_sha256=None, loader_rules_version=None, prompt_version=None,
                    prompt_hash=None, model="m", effort="low", tokenizer=None, embedder=None, packing=None,
                    usage_input_tokens=None, usage_cached_tokens=None, usage_output_tokens=None,
                    cost_usd_micros=cost, projected_cost_usd_micros=projected, latency_ms=0, host="authoritative",
                    device="remote", provider=provider, quantization=None, status=status, error=None)
    store.save_record(runs, rec)
