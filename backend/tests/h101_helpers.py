"""Pembantu test H-101 (B pembanding open-weight): config uji, unit/dokumen sintetis, model palsu berskrip. Tanpa jaringan."""

from __future__ import annotations

import copy
import dataclasses
import json
import re
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from backend.header_b.compare import Pair, select_pairs
from backend.header_b.prompt import load_prompt
from backend.header_b.render import build_prefix
from backend.header_b.run import Prepared
from backend.header_b.units import Unit

from .m25_fakes import chat_body, env_m25, m25_model_cfg
from .spark_fakes import Resp, Rig, Timeout, body_ok

PROMPT12 = "a" * 12
GATE = {"factor_bp": 15700, "batch_cap_micros": 2_000_000, "cumulative_cap_micros": 20_000_000, "cumulative_pct": 80}
USAGE_BT = {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 80}, "output_tokens": 50,
            "output_tokens_details": {"reasoning_tokens": 10}}


class Tok:
    """Tokenizer uji: satu token per kata (deterministik)."""

    class info:
        name, version = "words", "1"

    def count(self, text: str) -> int:
        return len(text.split())


class SizedTok(Tok):
    """Tokenizer uji berukuran tetap (S7/S8): awalan dokumen 40.000 token, suffix potongan 300 token, selain itu satu per kata."""

    def count(self, text: str) -> int:
        if text.startswith("POTONGAN YANG DIMINTA"):
            return 300
        if "<dokumen-" in text:
            return 40_000
        return len(text.split())


def model_b() -> dict:
    """config/model uji: Baseten dan Glimmer dengan role 'b'; `c_only` tanpa 'b'; `meta` dan `openrouter_dev` tanpa roles."""
    m = m25_model_cfg()
    m["profiles"]["baseten_open"]["roles"] = ["c", "a", "b"]
    m["profiles"]["glimmer_local"]["roles"] = ["c", "a", "b"]
    m["profiles"]["c_only"] = {**m["profiles"]["baseten_open"], "roles": ["c"]}
    m["pricing"]["c_only"] = dict(m["pricing"]["baseten_open"])
    m["effort"]["b"] = "low"
    return m


def budget_b(**over: Any) -> dict:
    b = {"version": 2, "dev_total_cap_micros": 2_000_000,
         "per_role_cap_micros": {"a": 500_000, "b": 1_000_000, "c": 500_000, "d": 250_000, "measure": 500_000},
         "provider_cap_micros": {"baseten": 20_000_000}, "batch_gate": dict(GATE)}
    b.update(over)
    return copy.deepcopy(b)


def hc_b(**over: Any) -> dict:
    h = {"max_header_tokens": 40, "schema_max_length_chars": 190, "max_output_tokens": 1000, "warm_max_output_tokens": 1000,
         "expected_output_tokens": 450, "max_consecutive_errors": 50, "cache_guard_calls": 10,
         "cache_guard_min_ratio": Fraction(4, 5), "granularity": "pasal",
         "max_attempts": {"baseten_open": 8, "glimmer_local": 3},
         "projection": {"doc_rpm": 150, "glimmer_local": {"prefill_tokens_per_s": 650, "base_ms": 4800, "output_tokens_per_10s": 237}}}
    h.update(over)
    return h


def prompt_a():
    """Prompt B nyata dengan hash disetel ke 'aaaaaaaaaaaa...' supaya direktori prompt12 sama dengan fixture skenario."""
    return dataclasses.replace(load_prompt(40), prompt_hash="a" * 64)


def make_prepared(n: int = 4, *, source: str = "pasal", doc_id: str = "uupt-x", prefix: str = "CH-U", sha: str = "c",
                  tok: Tok | None = None) -> Prepared:
    text = "\n".join(f"Pasal {i} isi uji" for i in range(1, n + 1)) + "\n"
    doc = SimpleNamespace(doc_id=doc_id, text=text, clean_sha256=sha * 64, sha256="s" + sha, loader_rules_version="lr-1")
    pr = prompt_a()
    units = [Unit(f"{prefix}{i}", f"Addr {i}", f"Pasal {i} isi uji", 4, (f"{prefix}{i}",)) for i in range(1, n + 1)]
    return Prepared(doc, pr, build_prefix(pr, doc, tok or Tok()), units, source)


def words(n: int, letters: int | None = None) -> str:
    """`n` kata; bila `letters` diberikan, total huruf (tanpa spasi) tepat `letters` (kata 3-4 huruf)."""
    if letters is None:
        return " ".join(["kata"] * n)
    base, extra = divmod(letters, n)
    return " ".join("x" * (base + (1 if i < extra else 0)) for i in range(n))


def ok_text(cid: str) -> str:
    return f"Header {cid}"


def scripted(behaviours: dict[str, list[Any]] | None = None, *, usage: Any = USAGE_BT, chat_usage: dict | None = None,
             log: list[str] | None = None) -> Callable[[Any, Any], Resp]:
    """Model palsu: per `chunk_id` daftar perilaku per upaya (`str` = teks header; "EMPTY" = header kosong; "RAW:<json>"
    = badan keluaran mentah). Tanpa naskah = header sah `Header <chunk_id>`. Pemanas (`warmup`) selalu sah. Responses dan
    Chat Completions (Glimmer) dilayani dari satu fungsi."""
    seen: dict[str, int] = defaultdict(int)
    counter = {"units": 0}
    beh = behaviours or {}

    def act(tr: Any, request: Any) -> Resp:
        body = json.loads(request.content.decode("utf-8"))
        chat = request.url.path.endswith("/chat/completions")
        text = body["messages"][0]["content"] if chat else body["input"]
        cid = re.search(r"chunk_id: (\S+)", text).group(1)
        if log is not None:
            log.append(cid)
        n = seen[cid]
        seen[cid] += 1
        if cid != "warmup":
            k = counter["units"]
            counter["units"] += 1
        plan = beh.get(cid)
        out: Any = {"chunk_id": cid, "header": ok_text(cid)}
        if cid != "warmup" and plan:
            step = plan[min(n, len(plan) - 1)]
            if step == "TIMEOUT":
                return Timeout(advance=900.0)  # type: ignore[return-value]
            if step == "EMPTY":
                out = {"chunk_id": cid, "header": ""}
            elif isinstance(step, str) and step.startswith("RAW:"):
                out = json.loads(step[4:])
            elif isinstance(step, str):
                out = {"chunk_id": cid, "header": step}
        if chat:
            kw = (chat_usage(counter["units"] - 1) if callable(chat_usage) else chat_usage) or {}
            return Resp(200, chat_body(out, **kw))
        u = usage(k) if callable(usage) and cid != "warmup" else (USAGE_BT if callable(usage) else usage)
        return Resp(200, body_ok(out, usage=u))

    return act


def rig_for(tmp: Path, profile: str, behaviours: dict[str, list[Any]] | None = None, *, budget: dict | None = None,
            model: dict | None = None, usage: Any = USAGE_BT, chat_usage: dict | None = None, log: list[str] | None = None) -> Rig:
    return Rig(tmp, profile=profile, model=model or model_b(), env=env_m25(), budget=budget or budget_b(),
               default=scripted(behaviours, usage=usage, chat_usage=chat_usage, log=log))


def pairs_of(p: Prepared, store_dir: Path, **kw: Any) -> list[Pair]:
    return select_pairs({p.doc.doc_id: {p.source: p}}, store_dir, **kw)


def put_header(headers_dir: Path, gran: str, chunk_id: str, text: str, *, prompt12: str = PROMPT12, run_id: str = "r1") -> None:
    d = Path(headers_dir) / gran / prompt12
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{chunk_id}.json").write_text(json.dumps({"chunk_id": chunk_id, "header": text, "granularity": gran, "run_id": run_id},
                                                   ensure_ascii=False), encoding="utf-8", newline="\n")
