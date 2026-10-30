"""Pemeriksa voice over video dengan Muse Voice Transcribe (H-113; spec docs/scenarios/M5.3-vo-qa-transcribe.md).

    uv run python -m video.qa.vo_check --vo-dir <direktori VO> --dry-run   # tanpa jaringan, tanpa key, tanpa tulis
    uv run python -m video.qa.vo_check --vo-dir <direktori VO>             # run sah (hanya atas izin L1)

Bukan bagian produk: record dan cache di store terpisah `runs/voice_qa/`, tidak dibaca UI/R1/R6/ekspor replay.
Model ID dan harga dari `config/model` profil `meta_voice`; parameter alat dari `config/voice_qa`. Key hanya dari `.env`.
Keluar: 0 = semua adegan tanpa `fail`/`error`; 1 = ada `fail`/`error`; 2 = galat masukan/gerbang (0 panggilan)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from backend import config as cfgmod
from backend.spark import store
from backend.spark.errors import ConfigInvalid
from backend.spark.runrecord import RunRecord

from . import audio as au
from .normalize import SceneResult, compare

ROLE = "voice_qa"
PROMPT_VERSION = "vo_qa.r1"
ENDPOINT_PATH = "/asr/transcribe"
DEFAULT_STORE = cfgmod.REPO_ROOT / "runs" / "voice_qa"
DEFAULT_REPORT_DIR = cfgmod.REPO_ROOT / "video" / "qa"
VIDEO_MD = cfgmod.REPO_ROOT / "docs" / "VIDEO.md"
VO_COLUMN = "Voice over (Inggris)"
STORYBOARD_HEADING = "## Storyboard terkunci"

# Transport: (url, headers, body, timeout_s) -> (status, body_bytes). Melempar TimeoutError / ConnectionError.
Transport = Callable[[str, Mapping[str, str], bytes, float], tuple[int, bytes]]


class InputError(Exception):
    """Galat masukan/gerbang: keluar 2, tanpa panggilan."""


# ---------- konfigurasi ----------

@dataclass(frozen=True)
class ToolConfig:
    model: str
    provider: str
    audio_per_hour_micros: int
    base_url_env: str
    api_key_env: str
    host: str
    mode: str
    language_bias: list[str]
    keywords: list[str]
    threshold_bp: int
    timeout_s: float
    limit_micros: int
    scenes: list[str]
    joined_terms: tuple[str, ...]
    config_hash: str


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def load_tool_config(model_cfg: Mapping[str, Any], vq: Mapping[str, Any]) -> ToolConfig:
    name = vq.get("profile")
    prof = (model_cfg.get("profiles") or {}).get(name) if isinstance(name, str) else None
    if not isinstance(prof, Mapping) or prof.get("api") != "asr_transcribe":
        raise ConfigInvalid(f"config/voice_qa: profile '{name}' is not an asr_transcribe profile in config/model")
    pricing = (model_cfg.get("pricing") or {}).get(prof.get("pricing", name))
    price = pricing.get("audio_per_hour_micros") if isinstance(pricing, Mapping) else None
    if not _int(price) or price <= 0:
        raise ConfigInvalid(f"config/model: [pricing.{name}] audio_per_hour_micros must be a positive integer")
    for k in ("wer_review_threshold_bp", "limit_micros"):
        if not _int(vq.get(k)) or vq[k] < 0:
            raise ConfigInvalid(f"config/voice_qa: {k} must be a non-negative integer")
    scenes = vq.get("scenes")
    if not isinstance(scenes, list) or not scenes or not all(isinstance(s, str) and re.fullmatch(r"[A-Z]\d", s) for s in scenes):
        raise ConfigInvalid("config/voice_qa: scenes must be a non-empty list of scene IDs like 'S0'")
    for k in ("language_bias", "keywords", "joined_terms"):
        if not isinstance(vq.get(k), list) or not all(isinstance(x, str) for x in vq[k]):
            raise ConfigInvalid(f"config/voice_qa: {k} must be a list of strings")
    if vq.get("mode") not in ("PUSH_TO_TALK", "ENDPOINTING", "DIARIZATION"):
        raise ConfigInvalid("config/voice_qa: mode must be PUSH_TO_TALK, ENDPOINTING or DIARIZATION")
    t = vq.get("timeout_s")
    if not isinstance(t, (int, float)) or isinstance(t, bool) or t <= 0:
        raise ConfigInvalid("config/voice_qa: timeout_s must be > 0")
    host = model_cfg.get("host")
    return ToolConfig(
        model=prof["model"], provider=prof["provider"], audio_per_hour_micros=price,
        base_url_env=prof["base_url_env"], api_key_env=prof["api_key_env"], host=host if isinstance(host, str) else "",
        mode=vq["mode"], language_bias=list(vq["language_bias"]), keywords=list(vq["keywords"]),
        threshold_bp=vq["wer_review_threshold_bp"], timeout_s=float(t), limit_micros=vq["limit_micros"],
        scenes=list(scenes), joined_terms=tuple(vq["joined_terms"]),
        config_hash=cfgmod.config_hash({"model": dict(model_cfg), "voice_qa": dict(vq)}),
    )


def pool_spent(store_root: Path) -> int:
    """Belanja pool `meta_voice` = jumlah `spend_micros()` semua record store terpisah (keputusan biaya; bukan
    `Ledger.spent`, yang khusus tampilan). Record rusak -> ValueError (gagal tertutup)."""
    return sum(r.spend_micros() for r in store.load_records(store_root))


def request_json(tc: ToolConfig) -> dict[str, Any]:
    body: dict[str, Any] = {"model": tc.model, "audioEncoding": "WAV", "mode": tc.mode}
    if tc.language_bias:
        body["languageBias"] = list(tc.language_bias)
    if tc.keywords:
        body["keywords"] = list(tc.keywords)
    return body


# ---------- naskah dan berkas ----------

def parse_script(md_text: str) -> dict[str, str]:
    """Kolom VO tabel "Storyboard terkunci" `docs/VIDEO.md` -> {adegan: teks}."""
    lines = md_text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(STORYBOARD_HEADING))
    except StopIteration:
        raise InputError("docs/VIDEO.md has no 'Storyboard terkunci' section") from None
    header: list[str] | None = None
    out: dict[str, str] = {}
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        if not ln.startswith("|"):
            if header is not None and out:
                break
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if header is None:
            header = cells
            if VO_COLUMN not in header:
                raise InputError(f"storyboard table has no '{VO_COLUMN}' column")
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        if len(cells) != len(header):
            raise InputError(f"storyboard row has {len(cells)} cells, header has {len(header)}")
        sid, text = cells[0], cells[header.index(VO_COLUMN)]
        if sid in out:
            raise InputError(f"storyboard lists scene {sid} twice")
        out[sid] = text
    return out


def select_files(vo_dir: Path, scenes: list[str]) -> tuple[dict[str, Path], list[str]]:
    pat = re.compile(r"^\d{2}-(" + "|".join(map(re.escape, scenes)) + r")\.wav$")
    chosen: dict[str, Path] = {}
    skipped: list[str] = []
    if not vo_dir.is_dir():
        raise InputError("VO directory not found")
    for p in sorted(vo_dir.iterdir()):
        m = pat.match(p.name)
        if not m:
            skipped.append(p.name)
            continue
        if m.group(1) in chosen:
            raise InputError(f"scene {m.group(1)} has two files: {chosen[m.group(1)].name}, {p.name}")
        chosen[m.group(1)] = p
    missing = [s for s in scenes if s not in chosen]
    if missing:
        raise InputError("no VO file for scene(s): " + ", ".join(missing))
    return {s: chosen[s] for s in scenes}, skipped


# ---------- panggilan ----------

def _multipart(req: dict[str, Any], wav: bytes, boundary: str) -> bytes:
    b = boundary.encode()
    parts = [
        b"--" + b + b"\r\n",
        b'Content-Disposition: form-data; name="request"\r\nContent-Type: application/json\r\n\r\n',
        json.dumps(req, separators=(",", ":")).encode("utf-8"), b"\r\n",
        b"--" + b + b"\r\n",
        b'Content-Disposition: form-data; name="audio"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n',
        wav, b"\r\n",
        b"--" + b + b"--\r\n",
    ]
    return b"".join(parts)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """3xx tidak diikuti: header Authorization tidak boleh terkirim ke host lain (L3 S-r2-2)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _opener() -> urllib.request.OpenerDirector:
    # Tanpa proxy dari env, tanpa redirect.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
    if not url.startswith("https://"):
        raise ConnectionError("https required")
    req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with _opener().open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""
    except TimeoutError:
        raise
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise TimeoutError("timeout") from None
        raise ConnectionError("connection failed") from None


class Scrubber:
    def __init__(self, secrets: list[str]) -> None:
        self._s = sorted({s for s in secrets if s and len(s) >= 4}, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for s in self._s:
            text = text.replace(s, "[redacted]")
        return text


@dataclass
class SceneRun:
    scene: str
    file_name: str
    audio_sha256: str
    script_sha256: str
    seconds: float
    projected_micros: int
    cache_key: str
    cached: bool
    transcript: str | None = None
    record: RunRecord | None = None
    result: SceneResult | None = None


def _record(tc: ToolConfig, key: str, audio_sha: str, *, status: str, cost: int | None, projected: int | None,
            latency_ms: int, error: dict[str, str] | None, now: Callable[[], float]) -> RunRecord:
    return RunRecord(
        run_id=uuid.uuid4().hex, kind=ROLE, created_at=datetime.fromtimestamp(now(), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        cache_key=key, corpus_hash=audio_sha, config_hash=tc.config_hash, clean_sha256=None, loader_rules_version=None,
        prompt_version=PROMPT_VERSION, prompt_hash=None, model=tc.model, effort=None, tokenizer=None, embedder=None,
        packing=None, usage_input_tokens=0, usage_cached_tokens=0, usage_output_tokens=0, cost_usd_micros=cost,
        projected_cost_usd_micros=projected, latency_ms=latency_ms, host=tc.host, device="remote", provider=tc.provider,
        quantization=None, status=status, error=error,
    )


def _api_message(body: bytes) -> str:
    try:
        d = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return ""
    msg = d.get("message") if isinstance(d, dict) else None
    if not isinstance(msg, str) and isinstance(d, dict) and isinstance(d.get("error"), dict):
        msg = d["error"].get("message")
    return msg[:200] if isinstance(msg, str) else ""


def call_one(tc: ToolConfig, sr: SceneRun, wav: bytes, *, url: str, api_key: str, transport: Transport,
             scrub: Scrubber, store_root: Path, now: Callable[[], float] = time.time,
             clock: Callable[[], float] = time.monotonic) -> None:
    boundary = "vo" + uuid.uuid4().hex
    body = _multipart(request_json(tc), wav, boundary)
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json",
               "Content-Type": f"multipart/form-data; boundary={boundary}"}
    t0 = clock()
    err: dict[str, str] | None = None
    cost: int | None = 0
    projected: int | None = None
    transcript: str | None = None
    payload: dict[str, Any] | None = None
    try:
        status, raw = transport(url, headers, body, tc.timeout_s)
    except TimeoutError:
        status, raw = -1, b""
        err, cost, projected = {"code": "timeout", "message": "request timed out"}, None, sr.projected_micros
    except (ConnectionError, OSError):
        status, raw = -1, b""
        err, cost, projected = {"code": "connection_error", "message": "connection failed"}, None, sr.projected_micros
    latency = int(round((clock() - t0) * 1000))
    if err is None and status != 200:
        msg = _api_message(raw)
        err = {"code": f"http_{status}", "message": scrub(f"HTTP {status}" + (f": {msg}" if msg else ""))}
    if err is None:
        try:
            d = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            d = None
        dur = d.get("audioDurationMs") if isinstance(d, dict) else None
        tr = d.get("transcript") if isinstance(d, dict) else None
        if not isinstance(tr, str) or not _int(dur) or dur < 0:
            err, cost, projected = {"code": "usage_invalid", "message": "response without transcript or audioDurationMs"}, None, sr.projected_micros
        else:
            transcript = tr
            cost = au.billed_micros(dur, tc.audio_per_hour_micros)
            payload = {"transcript": tr, "audioDurationMs": dur}
    rec = _record(tc, sr.cache_key, sr.audio_sha256, status="ok" if err is None else "error", cost=cost,
                  projected=projected, latency_ms=latency, error=err, now=now)
    store.save_record(store_root, rec)
    if payload is not None:
        store.cache_write(store_root, ROLE, sr.cache_key, store.canonical_json(payload), rec)
    sr.transcript, sr.record = transcript, rec


# ---------- laporan ----------

def _ops_text(ops) -> str:
    def f(o):
        if o.op == "sub":
            return f"`{o.ref}` -> `{o.hyp}`"
        if o.op == "del":
            return f"missing `{o.ref}`"
        return f"extra `{o.hyp}`"
    return "; ".join(f(o) for o in ops) if ops else "-"


def build_report(tc: ToolConfig, runs: list[SceneRun], generated_at: str) -> tuple[str, dict[str, Any]]:
    total = sum((r.record.spend_micros() if r.record and not r.cached else 0) for r in runs)
    rows = []
    for r in runs:
        res = r.result
        rows.append({
            "scene": r.scene, "file": r.file_name, "audio_sha256": r.audio_sha256, "script_sha256": r.script_sha256,
            "seconds": round(r.seconds, 2), "cached": r.cached, "run_id": r.record.run_id if r.record else None,
            "cost_usd_micros": r.record.spend_micros() if r.record else None,
            "status": r.record.status if r.record else None,
            "error_code": (r.record.error or {}).get("code") if r.record else None,
            "verdict": res.verdict if res else "error",
            "wer_bp": res.wer_bp if res else None,
            "numbers_script": res.numbers_script if res else None,
            "numbers_transcript": res.numbers_transcript if res else None,
            "number_diffs": [o.__dict__ for o in res.number_diffs] if res else None,
            "word_diffs": [o.__dict__ for o in res.word_diffs] if res else None,
            "transcript": r.transcript,
        })
    data = {"generated_at": generated_at, "model": tc.model, "provider": tc.provider, "config_hash": tc.config_hash,
            "wer_review_threshold_bp": tc.threshold_bp, "new_spend_usd_micros": total, "scenes": rows}
    md = [f"# VO check (Muse Voice Transcribe)", "",
          f"Generated {generated_at} UTC. Model `{tc.model}`. Spend this run {total} micro-USD (cached scenes add 0). "
          f"WER review threshold {tc.threshold_bp / 100:.2f}%. Numbers must match exactly.", "",
          "| Scene | File | Verdict | WER | Numbers (script) | Numbers (transcript) | Cached | Cost (micro-USD) |",
          "|---|---|---|---|---|---|---|---|"]
    for row in rows:
        wer = f"{row['wer_bp'] / 10000:.4f}" if row["wer_bp"] is not None else "n/a"
        md.append(f"| {row['scene']} | {row['file']} | {row['verdict']} | {wer} | {row['numbers_script']} | "
                  f"{row['numbers_transcript']} | {'yes' if row['cached'] else 'no'} | {row['cost_usd_micros']} |")
    md.append("")
    for r in runs:
        md.append(f"## {r.scene}")
        if r.result is None:
            md.append(f"Error: {(r.record.error or {}).get('code') if r.record else 'no record'}")
        else:
            md.append(f"- Number differences: {_ops_text(r.result.number_diffs)}")
            md.append(f"- Word differences: {_ops_text(r.result.word_diffs)}")
            md.append(f"- Transcript: {r.transcript}")
        md.append("")
    return "\n".join(md), data


# ---------- alur utama ----------

def run(argv: list[str] | None = None, *, model_cfg: Mapping[str, Any] | None = None,
        vq_cfg: Mapping[str, Any] | None = None, env: Mapping[str, str] | None = None,
        transport: Transport | None = None, store_root: Path | None = None, report_dir: Path | None = None,
        video_md: Path | None = None, out=None, now: Callable[[], float] = time.time) -> int:
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog="python -m video.qa.vo_check", description="VO transcription check (H-113)")
    ap.add_argument("--vo-dir", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--env-file", type=Path, default=cfgmod.REPO_ROOT / ".env")
    a = ap.parse_args(argv)
    p = lambda s="": print(s, file=out)  # noqa: E731
    try:
        model_cfg = model_cfg if model_cfg is not None else cfgmod.load("model")
        vq_cfg = vq_cfg if vq_cfg is not None else cfgmod.load("voice_qa")
        tc = load_tool_config(model_cfg, vq_cfg)
    except (cfgmod.ConfigError, ConfigInvalid) as exc:
        p(f"config_invalid: {exc}")
        return 2
    root = store_root or DEFAULT_STORE
    try:
        scripts = parse_script((video_md or VIDEO_MD).read_text(encoding="utf-8"))
        missing = [s for s in tc.scenes if s not in scripts]
        if missing:
            raise InputError("docs/VIDEO.md has no VO text for scene(s): " + ", ".join(missing))
        files, skipped = select_files(a.vo_dir, tc.scenes)
        req_canon = store.canonical_json(request_json(tc))
        runs: list[SceneRun] = []
        wavs: dict[str, bytes] = {}
        for s, path in files.items():
            raw = path.read_bytes()
            try:
                aud = au.load(path)
            except au.AudioError as exc:
                raise InputError(f"{path.name}: {exc}") from None
            asha = hashlib.sha256(raw).hexdigest()  # byte berkas asli
            key = store.sha256_hex(store.canonical_json([tc.provider, tc.model, req_canon, asha, au.CONVERT_VERSION]))
            cached = store.cache_read(root, ROLE, key) is not None
            runs.append(SceneRun(scene=s, file_name=path.name, audio_sha256=asha,
                                 script_sha256=store.sha256_hex(scripts[s]), seconds=aud.seconds,
                                 projected_micros=au.projected_micros(aud.seconds_ceil, tc.audio_per_hour_micros),
                                 cache_key=key, cached=cached))
            wavs[s] = aud.wav_bytes
    except (InputError, OSError) as exc:
        p(f"input_error: {exc}")
        return 2
    try:
        spent = pool_spent(root)
    except ValueError as exc:
        p(f"config_invalid: {exc}")
        return 2
    proj = sum(r.projected_micros for r in runs if not r.cached)
    gate_ok = spent + proj < tc.limit_micros

    p(f"VO check, model {tc.model} ({'dry run, no network' if a.dry_run else 'live'})")
    p(f"Skipped files: {', '.join(skipped) if skipped else '-'}")
    p("| Scene | File | Seconds | Script sha256 | Script start | Cached | Projected (micro-USD) |")
    p("|---|---|---|---|---|---|---|")
    for r in runs:
        start = " ".join(scripts[r.scene].split()[:6])
        p(f"| {r.scene} | {r.file_name} | {r.seconds:.2f} | {r.script_sha256[:12]} | {start} | "
          f"{'yes' if r.cached else 'no'} | {0 if r.cached else r.projected_micros} |")
    p(f"Total audio {sum(r.seconds for r in runs):.2f} s; projected {proj} micro-USD for {sum(not r.cached for r in runs)} uncached file(s)")
    p(f"Pool meta_voice spent {spent} + projected {proj} = {spent + proj} micro-USD; limit < {tc.limit_micros}: "
      f"{'ok' if gate_ok else 'BLOCKED'}")

    if env is None:
        from dotenv import dotenv_values
        env = {k: v for k, v in dotenv_values(a.env_file).items() if v} if a.env_file.is_file() else {}
    has_key = bool((env.get(tc.api_key_env) or "").strip())
    has_base = bool((env.get(tc.base_url_env) or "").strip())
    p(f"{tc.api_key_env}: {'present' if has_key else 'missing'}; {tc.base_url_env}: {'present' if has_base else 'missing'}")
    if not gate_ok:
        p("budget_exceeded: no calls made")
        return 2
    if a.dry_run:
        p("Dry run: no network calls, no files written.")
        return 0

    uncached = [r for r in runs if not r.cached]
    if uncached:
        if not has_key or not has_base:
            p(f"config_invalid: {tc.api_key_env} and {tc.base_url_env} must be set in .env")
            return 2
        api_key = env[tc.api_key_env].strip()
        base = env[tc.base_url_env].strip().rstrip("/")
        if not base.startswith("https://"):
            p("config_invalid: base URL must use https")
            return 2
        scrub = Scrubber([api_key, base, urlsplit(base).hostname or ""])
        tr = transport or urllib_transport
        for r in uncached:
            call_one(tc, r, wavs[r.scene], url=base + ENDPOINT_PATH, api_key=api_key, transport=tr, scrub=scrub,
                     store_root=root, now=now)
    for r in runs:
        if r.cached:
            r.transcript = json.loads(store.cache_read(root, ROLE, r.cache_key))["transcript"]
            r.record = store.origin_record(root, ROLE, r.cache_key)
        if r.transcript is not None:
            r.result = compare(r.scene, scripts[r.scene], r.transcript, tc.threshold_bp, tc.joined_terms)
    gen = datetime.fromtimestamp(now(), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    md, data = build_report(tc, runs, gen)
    rd = report_dir or DEFAULT_REPORT_DIR
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "vo-report.md").write_text(md + "\n", encoding="utf-8", newline="\n")
    (rd / "vo-report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    bad = [r.scene for r in runs if r.result is None or r.result.verdict == "fail"]
    for r in runs:
        v = r.result.verdict if r.result else f"error ({(r.record.error or {}).get('code') if r.record else '?'})"
        p(f"{r.scene}: {v}" + (f", WER {r.result.wer_bp / 10000:.4f}" if r.result else ""))
    p("Report: video/qa/vo-report.md" if report_dir is None else "Report written.")
    return 1 if bad else 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
