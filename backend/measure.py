"""M0.2 bagian token: token lokal per bagian, token terukur endpoint, rasio kalibrasi (EVAL-SPEC §2, H-014).

Pakai: uv run python -m backend.measure [--offline]
- Token lokal dari tokenizer H-014.
- Token terukur dari `/v1/responses/input_tokens` (profil `meta` saja; H-027, H-057).
  Endpoint menolak input kosong (G-30), jadi baseline = teks acuan pendek (metode selisih; disetujui operator 27 Okt, I-26 ditutup):
      tokens_endpoint(X) = count(X) - count(ref) + tokens_local(ref)
- Endpoint ini hanya menghitung token (tanpa `usage`); bukan klien Spark M0.1.
- Hasil di-cache per hash di runs/measure/; kunci sama -> tidak memanggil endpoint lagi.
Key tidak pernah dicetak atau ditulis; pesan galat tanpa header.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend import config
from backend.corpus.loader import load_corpus
from backend.tokenizer import get_tokenizer

SECTIONS = ("pembukaan", "penjelasan_umum", "batang_tubuh", "penjelasan_pasal", "pengesahan")
REF_TEXT = "."
METHOD = "difference_vs_reference_text"


def method_status() -> str:
    """Status metode baseline saat ini, dari `config/tokenizer` [calibration].status (I-26).

    Run tersimpan tidak ditulis ulang: `method.status` di record = status pada saat run.
    """
    return str(config.load("tokenizer").get("calibration", {}).get("status", "sementara"))


class MeasureError(Exception):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def section_texts(doc) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in SECTIONS:
        out[name] = "".join(doc.text[s["start"]:s["end"]] for s in doc.sections if s["section"] == name)
    out["_document"] = doc.text
    return out


def _env() -> dict[str, str]:
    from dotenv import dotenv_values

    return {k: v for k, v in dotenv_values(config.REPO_ROOT / ".env").items() if v}


def count_endpoint(text: str, model: str, base: str, key: str) -> tuple[int, int]:
    if not base.startswith("https://"):
        raise MeasureError("base URL must use https")
    body = json.dumps({"model": model, "input": text}).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/responses/input_tokens", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        msg = "invalid API key" if exc.code == 401 else f"HTTP {exc.code}"
        raise MeasureError(f"input_tokens endpoint failed: {msg}") from None
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise MeasureError(f"input_tokens endpoint unreachable: {type(exc).__name__}") from None
    except ValueError:
        raise MeasureError("input_tokens endpoint returned invalid JSON") from None
    ms = int((time.perf_counter() - t0) * 1000)
    if not isinstance(payload, dict) or not isinstance(payload.get("input_tokens"), int):
        raise MeasureError("input_tokens endpoint returned no integer 'input_tokens'")
    return payload["input_tokens"], ms


def run(offline: bool = False, out_dir: Path | None = None) -> dict[str, Any]:
    cfg_model = config.load("model")
    cfg_tok = config.load("tokenizer")
    cfg_corpus = config.load("corpus")
    prof = cfg_model["profiles"]["meta"]
    doc = load_corpus()
    tok = get_tokenizer()
    texts = section_texts(doc)
    local = {k: tok.count(v) for k, v in texts.items()}
    local_ref = tok.count(REF_TEXT)

    cfg_hash = config.config_hash({"model": cfg_model, "corpus": cfg_corpus, "tokenizer": {k: v for k, v in cfg_tok.items() if k != "calibration"}})
    input_hash = hashlib.sha256(json.dumps({k: hashlib.sha256(v.encode()).hexdigest() for k, v in texts.items()}, sort_keys=True).encode()).hexdigest()
    cache_key = hashlib.sha256(json.dumps(
        {"provider": prof["provider"], "model": prof["model"], "endpoint": "responses/input_tokens", "method": METHOD,
         "ref": REF_TEXT, "input_hash": input_hash, "tokenizer": [tok.info.name, tok.info.version]}, sort_keys=True).encode()).hexdigest()
    out_dir = out_dir or (config.REPO_ROOT / "runs" / "measure")
    out_path = out_dir / f"{cache_key[:16]}.json"
    if out_path.exists():
        rec = json.loads(out_path.read_text(encoding="utf-8"))
        rec["_from_cache"] = True
        return rec
    if offline:
        raise MeasureError("no stored measurement for this cache key and --offline given")

    env = _env()
    base, key = env.get(prof["base_url_env"]), env.get(prof["api_key_env"])
    if not base or not key:
        raise MeasureError(f"missing {prof['base_url_env']} or {prof['api_key_env']} in .env")
    raw: dict[str, int] = {}
    latency = 0
    for name in ["_reference", *texts.keys()]:
        n, ms = count_endpoint(REF_TEXT if name == "_reference" else texts[name], prof["model"], base, key)
        raw[name] = n
        latency += ms
    overhead = raw["_reference"] - local_ref

    rows = []
    for name, text in texts.items():
        ep = raw[name] - overhead
        rows.append({"section": name, "chars": len(text), "tokens_local": local[name], "endpoint_raw": raw[name],
                     "tokens_endpoint": ep, "calibration_ratio": round(ep / local[name], 6) if local[name] else None})
    sec_rows = [r for r in rows if r["section"] in SECTIONS]
    mean_ratio = round(sum(r["calibration_ratio"] for r in sec_rows) / len(sec_rows), 6)
    doc_row = next(r for r in rows if r["section"] == "_document")
    price = cfg_model["pricing"]["meta"]
    proj = {
        "basis": "one full clean document as input, Contributor price from config/model",
        "input_tokens": doc_row["tokens_endpoint"],
        "uncached_micros": -(-doc_row["tokens_endpoint"] * price["input_per_mtok_micros"] // 1_000_000),
        "cached_micros": -(-doc_row["tokens_endpoint"] * price["cached_per_mtok_micros"] // 1_000_000),
    }
    rec = {
        "run_record": {
            "run_id": f"measure-{cache_key[:16]}",
            "kind": "measure",
            "created_at": _utc(),
            "cache_key": cache_key,
            "corpus_hash": doc.sha256,
            "config_hash": cfg_hash,
            "clean_sha256": doc.clean_sha256,
            "loader_rules_version": doc.loader_rules_version,
            "prompt_version": None, "prompt_hash": None,
            "model": prof["model"], "effort": None,
            "tokenizer": {"name": tok.info.name, "version": tok.info.version},
            "embedder": None, "packing": None,
            "usage_input_tokens": None, "usage_cached_tokens": None, "usage_output_tokens": None,
            "cost_usd_micros": 0,
            "latency_ms": latency,
            "host": os.environ.get("LEXRAG_HOST_LABEL", "authoritative"),
            "device": "cpu",
            "provider": prof["provider"],
            "quantization": None,
            "status": "ok",
            "error": None,
        },
        "method": {"name": METHOD, "status": method_status(), "reference_text": REF_TEXT,
                   "reference_endpoint_raw": raw["_reference"], "reference_tokens_local": local_ref,
                   "hidden_overhead_tokens": overhead, "issue": "I-26", "gotcha": "G-30"},
        "rows": rows,
        "mean_section_ratio": mean_ratio,
        "cost_projection": proj,
        "n_endpoint_calls": len(raw),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    rec["_from_cache"] = False
    return rec


def format_table(rec: dict[str, Any]) -> str:
    lines = [f"{'section':<17}{'chars':>8}{'tok_local':>11}{'tok_endpoint':>14}{'ratio':>10}"]
    for r in rec["rows"]:
        lines.append(f"{r['section']:<17}{r['chars']:>8}{r['tokens_local']:>11}{r['tokens_endpoint']:>14}{r['calibration_ratio']:>10.4f}")
    m = rec["method"]
    rr = rec["run_record"]
    lines += ["", f"tokenizer            {rr['tokenizer']['name']} ({rr['tokenizer']['version']})",
              f"endpoint             {rr['provider']} {rr['model']} /responses/input_tokens",
              f"method               {m['name']} [at run time: {m['status']}; now: {method_status()}], hidden overhead {m['hidden_overhead_tokens']} tokens",
              f"mean section ratio   {rec['mean_section_ratio']}",
              f"cost projection      full document {rec['cost_projection']['input_tokens']} input tokens: "
              f"{rec['cost_projection']['uncached_micros']} micro-USD uncached, {rec['cost_projection']['cached_micros']} cached",
              f"run_id               {rr['run_id']}  (cost of this run: {rr['cost_usd_micros']} micro-USD)"]
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # G-27
    try:
        rec = run(offline="--offline" in sys.argv)
    except MeasureError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(format_table(rec), end="")
    print("from cache" if rec.get("_from_cache") else "measured now")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
