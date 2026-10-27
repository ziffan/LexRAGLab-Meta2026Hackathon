"""Klien Spark M0.1: Responses API saja, `strict: true`, berurutan, ber-cache per hash, ber-cost-guard.

Kebijakan galat (O-2): kegagalan sisi provider (401, 400, 404, 429 habis, 5xx, timeout habis,
semantik/skema gagal) dikembalikan sebagai `CallResult` berisi RunRecord `status=error`.
Dilempar hanya: `ConfigInvalid` dan `BudgetExceeded`, keduanya sebelum jaringan.

Key, base URL, dan host tidak pernah masuk log, record, `repr`, atau pesan galat (T1, T7);
pesan galat dibangun dari kode status dan pesan server yang sudah disensor, bukan `str(exc)`."""

from __future__ import annotations

import email.utils
import json
import logging
import re
import time
import uuid
from datetime import timezone
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx2
import openai

from backend import config as cfg

from . import ratelimit, store
from .budget import Caps, Ledger, Projection, effective_caps, evaluate
from .errors import BudgetExceeded, ConfigInvalid, UsageInvalid
from .money import compute_cost_micros
from .runrecord import RunRecord, kind_for_role, utc_iso
from .schema_check import check_schema_name, check_strict, validate_instance
from .settings import Settings, build_settings, effort_for

_SENSOR = "[REDACTED]"
_MAX_MSG = 300
_RA_NUMBER = re.compile(r"[0-9]+(\.[0-9]+)?")

Validator = Callable[[dict], "str | None"]


@dataclass
class CallResult:
    output: str | None  # JSON terkanon (sort_keys, separator tetap) atau None
    record: RunRecord

    @property
    def parsed(self) -> Any:
        return None if self.output is None else json.loads(self.output)


@dataclass
class BatchResult:
    results: list[CallResult | None]  # sejajar dengan masukan; None = tidak dijalankan
    not_run: list[int]
    stopped_reason: str | None  # None | "budget_exceeded"


@dataclass
class _Ctx:
    role: str
    effort: str
    cache_key: str
    prompt_version: str | None
    prompt_hash: str | None
    meta: Mapping[str, Any]
    t0: float
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)


def _fmt_num(v: float) -> str:
    return str(int(v)) if float(v) == int(v) else str(v)


def parse_retry_after(raw: Any, now_epoch: float) -> float | None:
    """Detik tunggu dari `Retry-After`; None bila tidak ada/tidak valid (T3)."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    if _RA_NUMBER.fullmatch(s):
        return float(s)
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt.tzinfo is None:  # tanpa zona dibaca UTC, bukan zona lokal mesin
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, dt.timestamp() - now_epoch)
    except Exception:
        return None


def _is_timeout(exc: BaseException) -> bool:
    e: BaseException | None = exc
    for _ in range(6):
        if e is None:
            return False
        if isinstance(e, (TimeoutError, openai.APITimeoutError, httpx2.TimeoutException)):
            return True
        e = e.__cause__ or e.__context__
    return False


_SDK_LOGGERS = ("openai", "httpx", "httpx2", "httpcore", "httpcore2")


def _quiet_sdk_loggers() -> None:
    """SDK/httpx mencetak URL (host) dan detail request pada INFO/DEBUG; matikan (T7, S10)."""
    # Logger induk: level CRITICAL dan propagate=False, sehingga logger anak yang dibuat belakangan
    # (level NOTSET) tidak sampai ke handler root.
    for top in _SDK_LOGGERS:
        lg = logging.getLogger(top)
        lg.setLevel(logging.CRITICAL)
        lg.propagate = False
    for name in list(logging.root.manager.loggerDict):
        if name.split(".")[0] in _SDK_LOGGERS:
            lg = logging.getLogger(name)
            lg.disabled = True
            lg.propagate = False


class SparkClient:
    def __init__(self, profile: str, *, model_config: Mapping[str, Any], budget_config: Mapping[str, Any],
                 env: Mapping[str, str], runs_dir: Path, transport: Any = None,
                 now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 logger: logging.Logger | None = None, replay: bool = False) -> None:
        self._profile = profile
        self._model_cfg = model_config
        self._budget_cfg = budget_config
        self._env = dict(env)
        self._runs = Path(runs_dir)
        self._now = now
        self._sleep = sleep
        self._log = logger or logging.getLogger("backend.spark")
        self._replay = bool(replay)
        self._s: Settings = build_settings(profile, model_config, self._env, need_credentials=not self._replay)
        self._config_hash = cfg.config_hash({"model": dict(model_config), "budget": dict(budget_config)})
        self._ledger = Ledger(self._runs)
        host = urlsplit(self._s.base_url).hostname if self._s.base_url else None
        extra = [v.strip() for k, v in self._env.items()
                 if isinstance(v, str) and ("KEY" in k.upper() or "TOKEN" in k.upper()) and len(v.strip()) >= 6]
        secrets = set(self._s.all_secrets) | set(extra)
        if host:
            secrets.add(host)
        self._secrets = sorted(secrets, key=len, reverse=True)
        self._sdk = None
        if not self._replay:
            _quiet_sdk_loggers()
            http_client = httpx2.Client(transport=transport) if transport is not None else None
            self._sdk = openai.OpenAI(api_key=self._s.api_key, base_url=self._s.base_url, max_retries=0,
                                      timeout=self._s.limits.timeout_s, http_client=http_client)
            self._limiter = ratelimit.get_limiter(profile, self._s.api_key)

    def __repr__(self) -> str:
        return f"SparkClient(profile={self._profile!r}, replay={self._replay})"

    __str__ = __repr__

    @property
    def config_hash(self) -> str:
        return self._config_hash

    # ------------------------------------------------------------------ util

    def _sanitize(self, text: Any) -> str:
        s = text if isinstance(text, str) else ""
        for sec in self._secrets:
            s = s.replace(sec, _SENSOR)
        s = " ".join(s.split())
        return s[:_MAX_MSG]

    def _projected(self, est_input: int, max_output_tokens: int) -> int:
        return compute_cost_micros({"input": est_input, "cached": 0, "output": max_output_tokens}, self._s.pricing)

    def _caps(self) -> Caps:
        return effective_caps(self._budget_cfg, self._env)

    def _check_args(self, a: Mapping[str, Any]) -> None:
        for k in ("est_input", "max_output_tokens"):
            v = a.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0 or (k == "max_output_tokens" and v < 1):
                raise ConfigInvalid(f"call argument '{k}' must be a non-negative integer (max_output_tokens >= 1)")
        if not isinstance(a.get("role"), str):
            raise ConfigInvalid("call argument 'role' must be a string")

    def _key_for(self, a: Mapping[str, Any], effort: str) -> str:
        inp = a.get("input")
        input_hash = store.sha256_hex(inp) if isinstance(inp, str) else store.sha256_hex("")
        return store.cache_key_for(self._s.provider, self._s.model, self._s.quantization, effort,
                                   a.get("prompt_hash"), a.get("schema_hash"), input_hash)

    # ------------------------------------------------------------ projection

    def project_batch(self, calls: list[Mapping[str, Any]]) -> Projection:
        """Proyeksi biaya batch tanpa jaringan (T5). Satu peran per batch."""
        if not calls:
            raise ConfigInvalid("batch is empty")
        roles = {c.get("role") for c in calls}
        if len(roles) != 1:
            raise ConfigInvalid("a batch must use exactly one role")
        role = next(iter(roles))
        per: list[int] = []
        seen: set[str] = set()
        for c in calls:
            self._check_args(c)
            effort = effort_for(self._model_cfg, role)
            key = self._key_for(c, effort)
            if key in seen or store.cache_read(self._runs, role, key) is not None:
                per.append(0)
            else:
                per.append(self._projected(c["est_input"], c["max_output_tokens"]))
            seen.add(key)
        caps = self._caps()
        return evaluate(role, caps, per, self._ledger.spent(), self._ledger.spent(role=role))

    def _guard(self, role: str, projected: int) -> None:
        caps = self._caps()
        p = evaluate(role, caps, [projected], self._ledger.spent(), self._ledger.spent(role=role))
        if p.verdict != "ok":
            raise BudgetExceeded(p.reason)

    # ----------------------------------------------------------------- batch

    def run_batch(self, calls: list[Mapping[str, Any]]) -> BatchResult:
        proj = self.project_batch(calls) if not self._replay else None
        if proj is not None and proj.verdict != "ok":
            raise BudgetExceeded(proj.reason)
        results: list[CallResult | None] = [None] * len(calls)
        not_run: list[int] = []
        stopped: str | None = None
        for i, args in enumerate(calls):
            if stopped is not None:
                not_run.append(i)
                continue
            try:
                results[i] = self.call(**args)
            except BudgetExceeded:
                stopped = "budget_exceeded"
                not_run.append(i)
        return BatchResult(results=results, not_run=not_run, stopped_reason=stopped)

    # ------------------------------------------------------------------ call

    def call(self, *, role: str, prompt_version: str | None, prompt_hash: str | None, input: str,
             schema: dict, schema_name: str, schema_hash: str | None, prompt_cache_key: str | None,
             max_output_tokens: int, est_input: int, validator: Validator | None = None,
             meta: Mapping[str, Any] | None = None) -> CallResult:
        t0 = self._now()
        args = {"role": role, "est_input": est_input, "max_output_tokens": max_output_tokens}
        self._check_args(args)
        effort = effort_for(self._model_cfg, role)
        ctx = _Ctx(role=role, effort=effort, prompt_version=prompt_version, prompt_hash=prompt_hash,
                   meta=meta or {}, t0=t0,
                   cache_key=self._key_for({"input": input, "prompt_hash": prompt_hash, "schema_hash": schema_hash}, effort))

        # Pra-validasi sebelum jaringan (O-14, G-03).
        if not isinstance(input, str) or not input.strip():
            return self._fail(ctx, "invalid_request", "input must be a non-empty string")
        bad = check_schema_name(schema_name) or check_strict(schema)
        if bad:
            return self._fail(ctx, "schema_invalid", f"schema rejected before sending: {bad}")

        cached = store.cache_read(self._runs, role, ctx.cache_key)
        if self._replay:
            if cached is None:
                return self._fail(ctx, "replay_no_stored_run",
                                  "No stored run for this request. Replay mode does not call the Model API.",
                                  persist=False)
            reason = self._semantic(cached, validator)
            if reason:
                return self._fail(ctx, "semantic_invalid", reason, persist=False)
            rec = self._record(ctx, status="replay", t_end=self._now())
            return CallResult(cached, rec)
        if cached is not None and not self._semantic(cached, validator):
            rec = self._record(ctx, status="cached", cost=0, t_end=self._now())
            store.save_record(self._runs, rec)
            self._log.info("spark call role=%s status=cached", role)
            return CallResult(cached, rec)

        projected = self._projected(est_input, max_output_tokens)
        self._guard(role, projected)
        return self._network(ctx, projected, input, schema, schema_name, prompt_cache_key,
                             max_output_tokens, validator)

    # --------------------------------------------------------------- network

    def _network(self, ctx: _Ctx, projected: int, input_text: str, schema: dict, schema_name: str,
                 prompt_cache_key: str | None, max_output_tokens: int, validator: Validator | None) -> CallResult:
        lim = self._s.limits
        kwargs: dict[str, Any] = {
            "model": self._s.model,
            "input": input_text,
            "reasoning": {"effort": ctx.effort},
            "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
            "max_output_tokens": max_output_tokens,
            "timeout": lim.timeout_s,
        }
        if prompt_cache_key is not None:
            kwargs["prompt_cache_key"] = prompt_cache_key
        timeouts = 0
        r429 = 0
        attempts = 0
        while True:
            self._limiter.acquire(lim.max_rpm, self._now, self._sleep)
            attempts += 1
            try:
                raw = self._sdk.responses.with_raw_response.create(**kwargs)  # type: ignore[union-attr]
                http = raw.http_response
            except openai.APIStatusError as exc:
                status = exc.status_code
                if status == 429:
                    ra = parse_retry_after(exc.response.headers.get("retry-after"), self._now())
                    wait = ra if ra is not None else lim.backoff_base_s * (lim.backoff_factor ** r429)
                    if r429 >= lim.max_429_retries:
                        return self._fail(ctx, "rate_limited",
                                          f"rate limited (HTTP 429): gave up after {r429} retries")
                    if wait > lim.max_wait_s:
                        return self._fail(ctx, "rate_limited",
                                          f"rate limited (HTTP 429): required wait {_fmt_num(wait)} s "
                                          f"exceeds max_wait_s {_fmt_num(lim.max_wait_s)} s")
                    r429 += 1
                    if wait > 0:
                        self._sleep(wait)
                    continue
                code, msg = self._map_status(status, exc.response)
                return self._fail(ctx, code, msg)
            except Exception as exc:  # noqa: BLE001 - dikelompokkan, pesan tidak memakai str(exc)
                if _is_timeout(exc):
                    if timeouts < lim.max_retries:
                        timeouts += 1
                        continue
                    return self._fail(ctx, "timeout",
                                      f"timeout after {_fmt_num(lim.timeout_s)} s ({attempts} attempts)")
                return self._fail(ctx, "model_unavailable", "connection to the Model API failed")
            return self._interpret(ctx, projected, http, schema, validator)

    def _map_status(self, status: int, response: Any) -> tuple[str, str]:
        msg, reasons = self._server_message(response)
        if status == 401:
            return "invalid_api_key", "invalid API key (HTTP 401)"
        if status == 404:
            if reasons:
                return "model_unavailable", f"HTTP 404: model endpoint unavailable ({reasons})"
            return "model_unavailable", f"HTTP 404: {msg}" if msg else "HTTP 404"
        if status in (502, 503, 504):
            return "model_unavailable", f"HTTP {status}: {msg}" if msg else f"HTTP {status}"
        if status >= 500:
            return "model_error", f"HTTP {status}: {msg}" if msg else f"HTTP {status}"
        return "invalid_request", f"HTTP {status}: {msg}" if msg else f"HTTP {status}"

    def _server_message(self, response: Any) -> tuple[str, str]:
        try:
            d = json.loads(response.text)
        except Exception:  # noqa: BLE001
            return "", ""
        err = d.get("error") if isinstance(d, dict) else None
        msg, reasons = "", ""
        if isinstance(err, dict):
            if isinstance(err.get("message"), str):
                msg = self._sanitize(err["message"])
            md = err.get("metadata")
            rs = md.get("ineligibility_reasons") if isinstance(md, dict) else None
            if isinstance(rs, list):
                reasons = self._sanitize("; ".join(str(x) for x in rs if isinstance(x, str)))
        elif isinstance(err, str):
            msg = self._sanitize(err)
        return msg, reasons

    # ------------------------------------------------------------- interpret

    def _interpret(self, ctx: _Ctx, projected: int, http: Any, schema: dict,
                   validator: Validator | None) -> CallResult:
        try:
            data = http.json()
        except Exception:  # noqa: BLE001
            data = None
        usage = self._parse_usage(data)
        if usage is None:
            return self._fail(ctx, "usage_invalid", "usage missing or invalid in the response", projected=projected)
        cost = compute_cost_micros(usage, self._s.pricing)

        def err(code: str, message: str) -> CallResult:
            return self._fail(ctx, code, message, usage=usage, cost=cost)

        status = data.get("status")
        if status == "incomplete":
            d = data.get("incomplete_details")
            why = self._sanitize(d.get("reason")) if isinstance(d, dict) and isinstance(d.get("reason"), str) else "unknown"
            return err("incomplete", f"response incomplete ({why}); raise max_output_tokens")
        if status is not None and status != "completed":
            return err("model_error", f"response status is '{self._sanitize(str(status))}'")
        text = self._output_text(data)
        if text is None:
            return err("schema_invalid", "response has no output text")
        try:
            out = json.loads(text, parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            return err("schema_invalid", "output text is not valid JSON")
        if not isinstance(out, dict):
            return err("schema_invalid", "output JSON is not an object")
        bad = validate_instance(out, schema)
        if bad:
            return err("schema_invalid", f"output does not match the schema: {bad}")
        canonical = store.canonical_json(out)
        reason = self._semantic(canonical, validator)
        if reason:
            return err("semantic_invalid", reason)
        rec = self._record(ctx, status="ok", usage=usage, cost=cost, t_end=self._now())
        store.cache_write(self._runs, ctx.role, ctx.cache_key, canonical, rec)
        store.save_record(self._runs, rec)
        self._log.info("spark call role=%s status=ok cost_usd_micros=%d", ctx.role, cost)
        return CallResult(canonical, rec)

    @staticmethod
    def _parse_usage(data: Any) -> dict[str, int] | None:
        if not isinstance(data, dict):
            return None
        u = data.get("usage")
        if not isinstance(u, dict):
            return None
        details = u.get("input_tokens_details")
        if details is None:
            cached = 0
        elif isinstance(details, dict):
            cached = details.get("cached_tokens")
            if cached is None:
                cached = 0
        else:
            return None
        cand = {"input": u.get("input_tokens"), "cached": cached, "output": u.get("output_tokens")}
        try:
            from .money import validate_usage
            return validate_usage(cand)
        except UsageInvalid:
            return None

    @staticmethod
    def _output_text(data: Mapping[str, Any]) -> str | None:
        parts: list[str] = []
        for item in data.get("output") or []:
            if isinstance(item, dict) and item.get("type") == "message":
                for c in item.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "output_text" and isinstance(c.get("text"), str):
                        parts.append(c["text"])
        return "".join(parts) if parts else None

    def _semantic(self, canonical: str, validator: Validator | None) -> str | None:
        if validator is None:
            return None
        try:
            res = validator(json.loads(canonical))
        except Exception as exc:  # noqa: BLE001
            return f"semantic validator raised {type(exc).__name__}"
        if isinstance(res, str) and res:
            return "semantic validation failed: " + self._sanitize(res)
        if res is False:
            return "semantic validation failed"
        return None

    # --------------------------------------------------------------- records

    def _record(self, ctx: _Ctx, *, status: str, error: dict | None = None, usage: Mapping[str, int] | None = None,
                cost: int | None = None, projected: int | None = None, t_end: float | None = None) -> RunRecord:
        t_end = self._now() if t_end is None else t_end
        m = ctx.meta
        return RunRecord(
            run_id=ctx.run_id, kind=kind_for_role(ctx.role), created_at=utc_iso(ctx.t0), cache_key=ctx.cache_key,
            corpus_hash=m.get("corpus_hash"), config_hash=self._config_hash,
            clean_sha256=m.get("clean_sha256"), loader_rules_version=m.get("loader_rules_version"),
            prompt_version=ctx.prompt_version, prompt_hash=ctx.prompt_hash,
            model=self._s.model, effort=ctx.effort, tokenizer=m.get("tokenizer"), embedder=None, packing=None,
            usage_input_tokens=usage["input"] if usage else None,
            usage_cached_tokens=usage["cached"] if usage else None,
            usage_output_tokens=usage["output"] if usage else None,
            cost_usd_micros=cost, projected_cost_usd_micros=projected,
            latency_ms=max(0, int(round((t_end - ctx.t0) * 1000))),
            host=self._s.host_label, device=self._s.device, provider=self._s.provider,
            quantization=self._s.quantization, status=status, error=error,
        )

    def _fail(self, ctx: _Ctx, code: str, message: str, *, usage: Mapping[str, int] | None = None,
              cost: int | None = None, projected: int | None = None, persist: bool = True) -> CallResult:
        msg = self._sanitize(message)
        rec = self._record(ctx, status="error", error={"code": code, "message": msg}, usage=usage,
                           cost=cost, projected=projected)
        if persist:
            store.save_record(self._runs, rec)
        self._log.info("spark call role=%s status=error code=%s", ctx.role, code)
        return CallResult(None, rec)


def _reject_constant(name: str) -> Any:
    raise ValueError("non-finite number in JSON")
