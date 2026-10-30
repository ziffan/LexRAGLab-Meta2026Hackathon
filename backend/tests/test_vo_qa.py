"""Pemeriksa VO Muse Voice Transcribe (H-113; docs/scenarios/M5.3-vo-qa-transcribe.md §8). Sintetis, tanpa jaringan
luar dan tanpa key nyata."""

from __future__ import annotations

import email
import http.client
import http.server
import io
import json
import threading
import urllib.error
import urllib.request
import wave
from pathlib import Path

import numpy as np
import pytest

from backend import config as cfgmod
from backend.spark import store
from backend.spark.errors import ConfigInvalid
from backend.spark.settings import build_settings
from video.qa import audio as au
from video.qa import vo_check as vc
from video.qa.normalize import compare, normalize, numbers

KEY = "sk-test-SECRETKEY-123456"
BASE = "https://voice.example-host.test/v1"
HOST = "voice.example-host.test"
SCENES = ["S0", "D1"]
SCRIPT_MD = """# x

## Storyboard terkunci (30 Okt)

| # | Waktu | Voice over (Inggris) | Disclosure |
|---|---|---|---|
| S0 | 0:00 | Spark went over in 816 of 1,783 calls. | — |
| D1 | 0:25 | It keeps the whole article, about a tenth. | — |

### Alternatif
"""
TRANSCRIPTS = {"S0": "Spark went over in eight sixteen of seventeen eighty three calls.",
               "D1": "It keeps the whole article, about one tenth."}


# ---------- helper ----------

def wav_file(path: Path, seconds: float, rate: int = 48000, channels: int = 1, freq: float = 440.0,
             sampwidth: int = 2) -> Path:
    n = int(round(seconds * rate))
    t = np.arange(n) / rate
    x = (8000 * np.sin(2 * np.pi * freq * t)).astype("<i2")
    if channels > 1:
        x = np.repeat(x[:, None], channels, axis=1).reshape(-1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(x.tobytes() if sampwidth == 2 else (x // 256 + 128).astype("u1").tobytes())
    return path


def model_cfg() -> dict:
    m = cfgmod.load("model")
    return m


def vq_cfg(**over) -> dict:
    d = {"version": 1, "profile": "meta_voice", "mode": "PUSH_TO_TALK", "language_bias": ["English"], "keywords": [],
         "wer_review_threshold_bp": 1000, "timeout_s": 5, "limit_micros": 50000, "scenes": list(SCENES),
         "joined_terms": ["bm25"]}
    d.update(over)
    return d


class FakeTransport:
    def __init__(self, responses=None, transcripts=None, raise_exc=None):
        self.calls: list[dict] = []
        self.responses = responses or {}
        self.transcripts = transcripts or TRANSCRIPTS
        self.raise_exc = raise_exc

    def __call__(self, url, headers, body, timeout):
        msg = email.message_from_bytes(b"Content-Type: " + headers["Content-Type"].encode() + b"\r\n\r\n" + body)
        parts = {p.get_param("name", header="content-disposition"): p for p in msg.get_payload()}
        req = json.loads(parts["request"].get_payload(decode=True))
        wav_bytes = parts["audio"].get_payload(decode=True)
        with wave.open(io.BytesIO(wav_bytes)) as w:
            fmt = (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes())
        self.calls.append({"url": url, "headers": dict(headers), "request": req, "wav_fmt": fmt,
                           "ctype": {k: v.get_content_type() for k, v in parts.items()}})
        if self.raise_exc is not None:
            raise self.raise_exc
        idx = len(self.calls) - 1
        if idx in self.responses:
            return self.responses[idx]
        scene = SCENES[idx % len(SCENES)]
        dur = int(round(fmt[3] / fmt[2] * 1000))
        return 200, json.dumps({"sessionId": "s", "transcript": self.transcripts[scene], "audioDurationMs": dur,
                                "turns": []}).encode()


class Rig:
    def __init__(self, tmp: Path, secs=(26.09, 13.05), vq=None):
        self.tmp = tmp
        self.vo = tmp / "vo"
        self.vo.mkdir()
        wav_file(self.vo / "01-S0.wav", secs[0])
        wav_file(self.vo / "03-D1.wav", secs[1])
        (self.vo / "01-S0.mp3").write_bytes(b"x")
        wav_file(self.vo / "10-alt-S0-B.wav", 1.0)
        self.md = tmp / "VIDEO.md"
        self.md.write_text(SCRIPT_MD, encoding="utf-8")
        self.store = tmp / "runs" / "voice_qa"
        self.reports = tmp / "reports"
        self.vq = vq or vq_cfg()
        self.out = io.StringIO()

    def run(self, *extra, transport=None, env=None):
        self.out = io.StringIO()
        return vc.run(["--vo-dir", str(self.vo), *extra], model_cfg=model_cfg(), vq_cfg=self.vq,
                      env={"MUSE_API_KEY": KEY, "MUSE_BASE_URL": BASE} if env is None else env,
                      transport=transport, store_root=self.store, report_dir=self.reports, video_md=self.md,
                      out=self.out, now=lambda: 1761800000.0)

    def records(self):
        return store.load_records(self.store)

    def all_text(self) -> str:
        texts = [self.out.getvalue()]
        for p in self.tmp.rglob("*"):
            if p.is_file() and p.suffix in (".json", ".md"):
                texts.append(p.read_text(encoding="utf-8"))
        return "\n".join(texts)


# ---------- V1-V5, V17: normalisasi dan vonis ----------

@pytest.mark.parametrize("text,expected", [
    ("three hundred thousand", ["300000"]), ("300 thousand", ["300000"]), ("forty seven thousand", ["47000"]),
    ("one thousand seven hundred eighty three", ["1783"]), ("three hundred and two", ["302"]),
    ("a million", ["1000000"]), ("million token", ["1000000", "token"]), ("1 million", ["1000000"]),
    ("one point three", ["1.3"]), ("1 point 3", ["1.3"]), ("the point is", ["the", "point", "is"]),
    ("fifty six", ["56"]), ("eight sixteen", ["816"]), ("nineteen twenty six", ["1926"]), ("one forty two", ["142"]),
    ("eight one six", ["816"]), ("300k", ["300000"]), ("5.8x", ["5.8", "x"]), ("1/10", ["0.1"]),
    ("about a tenth", ["about", "0.1"]), ("one tenth", ["0.1"]), ("a 10th", ["0.1"]),
    ("$0.56", ["0.56", "dollars"]), ("fifty-six cents", ["0.56", "dollars"]), ("BM 25", ["bm25"]),
    ("BM twenty five", ["bm25"]), ("BM25", ["bm25"]), ("1,926.", ["1926"]), ("1,783. On three", ["1783", "on", "3"]),
    ("816 1783", ["816", "1783"]), ("eight 16", ["8", "16"]), ("I review every one", ["i", "review", "everyone"]),
    ("A, B and C", ["a", "b", "and", "c"]), ("“Insufficient” — evidence", ["insufficient", "evidence"]),
    ("2.50", ["2.5"]), ("007", ["7"]),
    # tanda baca memutus rangkaian angka (§6.3; L3 kode S2)
    ("the tenth time", ["the", "0.1", "time"]),
    ("eight, sixteen", ["8", "16"]), ("nineteen. Twenty six", ["19", "26"]), ("three; four", ["3", "4"]),
])
def test_v1_normalize(text, expected):
    assert normalize(text) == expected


def test_v5_wer_bp_rounds_up():
    # 1 galat dari 3 kata = 3333,3 bp -> 3334 (dibulatkan ke atas, konservatif)
    assert compare("X", "a b c", "a b z", 10000).wer_bp == 3334


def test_v2_paired_reading_passes():
    r = compare("T1", "in 816 of 1,783 calls", "in eight sixteen of seventeen eighty three calls", 1000)
    assert r.verdict == "pass" and r.wer_bp == 0 and r.numbers_script == ["816", "1783"]


def test_v3_wrong_number_fails_and_lists_diff():
    r = compare("T1", "in 816 of 1,783 calls", "in 816 of 1,738 calls", 1000)
    assert r.verdict == "fail"
    assert [(o.op, o.ref, o.hyp) for o in r.number_diffs] == [("sub", "1783", "1738")]


@pytest.mark.parametrize("hyp", ["in 816 calls", "in 816 of 1,783 calls and 5", "in eight sixteen seventeen eighty three calls"])
def test_v4_missing_extra_or_merged_numbers_fail(hyp):
    assert compare("T1", "in 816 of 1,783 calls", hyp, 10000).verdict == "fail"


def test_v5_word_only_diffs_review_or_pass_at_threshold():
    script = "LexRAGLab is an evaluation lab for legal builders"  # 8 kata
    r = compare("S1", script, "Lex rag lab is an evaluation lab for legal builders", 1000)
    assert r.verdict == "review" and r.numbers_script == r.numbers_transcript == []
    # tepat di ambang: 1 sub dari 10 kata = 1000 bp -> pass
    r2 = compare("X", "a b c d e f g h i j", "a b c d e f g h i z", 1000)
    assert r2.wer_bp == 1000 and r2.verdict == "pass"
    assert compare("X", "a b c d e f g h i j", "a b c d e f g h y z", 1000).verdict == "review"


def test_v16_v17_real_video_md_numbers():
    scripts = vc.parse_script((cfgmod.REPO_ROOT / "docs" / "VIDEO.md").read_text(encoding="utf-8"))
    assert list(scripts) == ["S0", "S1", "D1", "D2", "D3", "D4", "D5", "T1", "I1"]
    assert scripts["S0"].startswith("I do legal work")
    got = {k: numbers(normalize(v)) for k, v in scripts.items()}
    assert got == {"S0": ["1", "300000", "1", "6", "1000000", "0.1"], "S1": [], "D1": ["102", "3"],
                   "D2": ["1", "2000", "47000", "8", "6", "5"], "D3": ["14", "2"], "D4": ["69"], "D5": [],
                   "T1": ["40", "816", "1783", "1.3", "142", "1926", "3"], "I1": ["0.56"]}


# ---------- V6-V11: alur, biaya, cache, gerbang, record ----------

def test_v6_cache_second_run_makes_no_calls(tmp_path):
    rig = Rig(tmp_path)
    t1 = FakeTransport()
    assert rig.run(transport=t1) == 0
    assert len(t1.calls) == 2
    recs = rig.records()
    assert len(recs) == 2 and all(len(r.run_id) == 32 and r.run_id.isalnum() for r in recs)
    rep1 = json.loads((rig.reports / "vo-report.json").read_text(encoding="utf-8"))
    t2 = FakeTransport()
    assert rig.run(transport=t2) == 0
    assert t2.calls == [] and len(rig.records()) == 2
    rep2 = json.loads((rig.reports / "vo-report.json").read_text(encoding="utf-8"))
    assert [s["run_id"] for s in rep2["scenes"]] == [s["run_id"] for s in rep1["scenes"]]
    assert all(s["cached"] for s in rep2["scenes"]) and rep2["new_spend_usd_micros"] == 0
    assert [s["verdict"] for s in rep2["scenes"]] == [s["verdict"] for s in rep1["scenes"]] == ["pass", "pass"]
    # parameter request berubah -> miss
    rig.vq = vq_cfg(keywords=["LexRAGLab"])
    t3 = FakeTransport()
    assert rig.run(transport=t3) == 0 and len(t3.calls) == 2 and t3.calls[0]["request"]["keywords"] == ["LexRAGLab"]


def test_v6_cache_hit_without_origin_record_warns(tmp_path):
    rig = Rig(tmp_path)
    rig.run(transport=FakeTransport())
    for p in (rig.store / "spark" / "records").glob("*.json"):
        p.unlink()
    t = FakeTransport()
    assert rig.run(transport=t) == 0 and t.calls == []
    assert "warning: S0 cache entry has no matching stored run record" in rig.out.getvalue()


def test_v14_oserror_prints_no_absolute_path(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    target = str(rig.vo / "01-S0.wav")

    orig = Path.read_bytes

    def deny(self):
        if self.suffix == ".wav":
            raise PermissionError(13, "denied", target)
        return orig(self)
    monkeypatch.setattr(Path, "read_bytes", deny)
    assert rig.run("--dry-run") == 2
    out = rig.out.getvalue()
    assert "PermissionError (01-S0.wav)" in out and str(tmp_path) not in out


def test_v19_convert_version_change_misses_cache(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.run(transport=FakeTransport())
    monkeypatch.setattr(au, "CONVERT_VERSION", "r2")
    t = FakeTransport()
    rig.run(transport=t)
    assert len(t.calls) == 2


def test_v7_projection_and_billing_integers():
    assert au.projected_micros(27, 180000) == 1350
    assert au.billed_micros(26090, 180000) == 1300
    assert au.billed_micros(999, 180000) == 0
    assert au.projected_micros(1, 7) == 1  # dibulatkan ke atas
    assert au.billed_micros(1000, 7) == 1


def test_v7_cost_recorded_from_audio_duration(tmp_path):
    rig = Rig(tmp_path)
    rig.run("--dry-run", transport=FakeTransport())
    assert "| S0 | 01-S0.wav | 26.09 |" in rig.out.getvalue() and "| 1350 |" in rig.out.getvalue()
    rig.run(transport=FakeTransport())
    costs = sorted(r.cost_usd_micros for r in rig.records())
    assert costs == [650, 1300]  # 13,05 s -> 13 s -> 650; 26,09 s -> 26 s -> 1300


def _seed_spend(root: Path, micros: int) -> None:
    tc = vc.load_tool_config(model_cfg(), vq_cfg())
    rec = vc._record(tc, "k" * 64, "a" * 64, status="ok", cost=micros, projected=None, latency_ms=1, error=None,
                     now=lambda: 0.0)
    store.save_record(root, rec)


@pytest.mark.parametrize("spent,ok", [(50000 - 2050 - 1, True), (50000 - 2050, False)])
def test_v8_gate_strict_limit(tmp_path, spent, ok):
    rig = Rig(tmp_path)  # proyeksi 27 s + 14 s = 1350 + 700 = 2050
    _seed_spend(rig.store, spent)
    t = FakeTransport()
    code = rig.run(transport=t)
    if ok:
        assert code == 0 and len(t.calls) == 2
    else:
        assert code == 2 and t.calls == [] and "budget_exceeded" in rig.out.getvalue()


def test_v8_pool_counts_projected_of_failed_calls(tmp_path):
    rig = Rig(tmp_path)
    tc = vc.load_tool_config(model_cfg(), vq_cfg())
    store.save_record(rig.store, vc._record(tc, "k" * 64, "a" * 64, status="error", cost=None, projected=50000 - 2050,
                                            latency_ms=1, error={"code": "timeout", "message": "x"}, now=lambda: 0.0))
    t = FakeTransport()
    assert rig.run(transport=t) == 2 and t.calls == []


def test_v8_corrupt_pool_record_fails_closed(tmp_path):
    rig = Rig(tmp_path)
    d = rig.store / "spark" / "records"
    d.mkdir(parents=True)
    (d / "bad.json").write_text("{not json", encoding="utf-8")
    t = FakeTransport()
    assert rig.run("--dry-run", transport=t) == 2 and t.calls == []
    assert rig.run(transport=t) == 2 and t.calls == []


def test_v8_projection_alone_at_limit_blocked(tmp_path):
    rig = Rig(tmp_path, vq=vq_cfg(limit_micros=2050))
    t = FakeTransport()
    assert rig.run(transport=t) == 2 and t.calls == []
    assert rig.run("--dry-run", transport=t) == 2


def test_v9_separate_store_main_pools_untouched(tmp_path):
    from backend.api.routers.system import cost_fields
    main_runs = tmp_path / "runs"
    from .spark_fakes import synth
    synth(main_runs, "c", "meta", 1234)
    m, b = cfgmod.load("model"), cfgmod.load("budget")
    before = cost_fields(main_runs, b, model_cfg=m)
    rig = Rig(tmp_path)
    rig.run(transport=FakeTransport())
    recs = rig.records()
    assert {(r.kind, r.provider, r.model) for r in recs} == {("voice_qa", "meta_voice", "muse-voice-transcribe-1.0")}
    assert (rig.store / "spark" / "records").is_dir()
    assert cost_fields(main_runs, b, model_cfg=m) == before
    assert len(store.load_records(main_runs)) == 1
    assert vc.pool_spent(rig.store) == sum(r.cost_usd_micros for r in recs) == 1300 + 650


def test_v10_dry_run_no_network_no_files_no_key(tmp_path):
    rig = Rig(tmp_path)
    before = sorted(p for p in tmp_path.rglob("*"))
    t = FakeTransport(raise_exc=AssertionError("network"))
    assert rig.run("--dry-run", transport=t, env={}) == 0
    assert t.calls == []
    assert sorted(p for p in tmp_path.rglob("*")) == before
    out = rig.out.getvalue()
    assert "projected 2050 micro-USD" in out and "MUSE_API_KEY: missing" in out


def test_v10_live_without_key_refuses(tmp_path):
    rig = Rig(tmp_path)
    t = FakeTransport()
    assert rig.run(transport=t, env={}) == 2 and t.calls == []


def test_v11_plain_http_base_refused(tmp_path):
    rig = Rig(tmp_path)
    t = FakeTransport()
    assert rig.run(transport=t, env={"MUSE_API_KEY": KEY, "MUSE_BASE_URL": "http://voice.example-host.test/v1"}) == 2
    assert t.calls == [] and "https" in rig.out.getvalue()


def test_v11_request_shape_and_no_leak(tmp_path):
    rig = Rig(tmp_path)
    t = FakeTransport()
    rig.run(transport=t)
    c = t.calls[0]
    assert c["url"] == BASE + "/asr/transcribe"
    assert c["headers"]["Authorization"] == f"Bearer {KEY}"
    assert c["request"] == {"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV", "mode": "PUSH_TO_TALK",
                            "languageBias": ["English"]}
    assert c["ctype"] == {"request": "application/json", "audio": "audio/wav"}
    assert c["wav_fmt"][:3] == (1, 2, 24000)
    text = rig.all_text()
    for secret in (KEY, BASE, HOST, str(tmp_path)):
        assert secret not in text


# ---------- V12: konversi audio ----------

def _decode(audio: au.Audio) -> np.ndarray:
    with wave.open(io.BytesIO(audio.wav_bytes)) as w:
        assert (w.getnchannels(), w.getsampwidth()) == (1, 2)
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)


def test_v12_resample_48k_passband_and_stopband(tmp_path):
    a1 = au.load(wav_file(tmp_path / "a.wav", 1.0, freq=1000))
    assert a1.rate == 24000 and a1.frames == 24000 and a1.source_rate == 48000
    ref = 8000 / np.sqrt(2)
    x1 = _decode(a1)[500:-500]
    assert abs(au.rms_db(x1) - 20 * np.log10(ref)) < 1.0
    x2 = _decode(au.load(wav_file(tmp_path / "b.wav", 1.0, freq=20000)))[500:-500]
    assert au.rms_db(x2) - 20 * np.log10(ref) < -40


def test_v12_stereo_mixed_and_native_rates(tmp_path):
    a = au.load(wav_file(tmp_path / "s.wav", 0.5, rate=24000, channels=2))
    assert a.source_channels == 2 and a.rate == 24000 and a.frames == 12000
    assert au.load(wav_file(tmp_path / "r16.wav", 0.5, rate=16000)).rate == 16000
    assert au.load(wav_file(tmp_path / "r32.wav", 0.5, rate=32000)).rate == 16000


@pytest.mark.parametrize("kw", [{"rate": 44100}, {"sampwidth": 1}])
def test_v12_unsupported_formats_rejected(tmp_path, kw):
    with pytest.raises(au.AudioError):
        au.load(wav_file(tmp_path / "x.wav", 0.2, **kw))


def test_v12_non_wav_rejected(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVEjunk")
    with pytest.raises(au.AudioError):
        au.load(p)


# ---------- V13: galat ----------

@pytest.mark.parametrize("status", [400, 429, 500, 302])
def test_v13_http_errors_not_billed_not_cached(tmp_path, status):
    rig = Rig(tmp_path)
    body = json.dumps({"message": f"bad thing with {KEY} at {BASE}"}).encode()
    t = FakeTransport(responses={0: (status, body)})
    assert rig.run(transport=t) == 1
    err = [r for r in rig.records() if r.status == "error"]
    assert len(err) == 1 and err[0].error["code"] == f"http_{status}"
    assert err[0].cost_usd_micros == 0 and err[0].projected_cost_usd_micros is None
    assert KEY not in rig.all_text() and BASE not in rig.all_text()
    t2 = FakeTransport()
    rig.run(transport=t2)
    assert len(t2.calls) == 1  # hanya berkas yang gagal; yang ok dari cache


def test_v13_host_only_message_redacted(tmp_path):
    rig = Rig(tmp_path)
    body = json.dumps({"message": f"upstream {HOST} refused"}).encode()
    rig.run(transport=FakeTransport(responses={0: (503, body)}))
    err = [r for r in rig.records() if r.status == "error"][0]
    assert HOST not in rig.all_text() and "[redacted]" in err.error["message"]


@pytest.mark.parametrize("exc,code", [(TimeoutError("t"), "timeout"), (ConnectionError("c"), "connection_error"),
                                      (http.client.IncompleteRead(b"x"), "connection_error"),
                                      (RuntimeError("boom"), "connection_error")])
def test_v13_timeout_projected(tmp_path, exc, code):
    rig = Rig(tmp_path)
    assert rig.run(transport=FakeTransport(raise_exc=exc)) == 1
    recs = rig.records()
    assert {r.error["code"] for r in recs} == {code}
    assert sorted(r.projected_cost_usd_micros for r in recs) == [700, 1350]
    assert all(r.cost_usd_micros is None for r in recs)
    assert not list((rig.store / "spark" / "voice_qa").glob("*.json"))  # tidak di-cache


@pytest.mark.parametrize("payload", [{"transcript": "x"}, {"transcript": "x", "audioDurationMs": "26000"},
                                     {"audioDurationMs": 1000}, "not json"])
def test_v13_usage_invalid(tmp_path, payload):
    rig = Rig(tmp_path)
    raw = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
    rig.run(transport=FakeTransport(responses={0: (200, raw)}))
    bad = [r for r in rig.records() if r.status == "error"]
    assert len(bad) == 1 and bad[0].error["code"] == "usage_invalid" and bad[0].projected_cost_usd_micros == 1350


# ---------- V14, V19: pemilihan berkas dan batas ----------

def test_v14_selection_skips_and_errors(tmp_path):
    rig = Rig(tmp_path)
    rig.run("--dry-run")
    assert "10-alt-S0-B.wav" in rig.out.getvalue() and "01-S0.mp3" in rig.out.getvalue()
    wav_file(rig.vo / "02-S0.wav", 0.5)
    t = FakeTransport()
    assert rig.run(transport=t) == 2 and t.calls == [] and "two files" in rig.out.getvalue()
    (rig.vo / "02-S0.wav").unlink()
    (rig.vo / "03-D1.wav").unlink()
    assert rig.run(transport=t) == 2 and "D1" in rig.out.getvalue() and t.calls == []


def test_v14_too_long_rejected(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    monkeypatch.setattr(au, "MAX_SECONDS", 20)
    t = FakeTransport()
    assert rig.run(transport=t) == 2 and t.calls == [] and "longer than" in rig.out.getvalue()


def test_v19_body_too_large_rejected(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    monkeypatch.setattr(au, "MAX_BODY_BYTES", 1000)
    t = FakeTransport()
    assert rig.run(transport=t) == 2 and t.calls == [] and "32 MB" in rig.out.getvalue()


# ---------- V15, V18: penjaga produk ----------

def test_v15_spark_client_rejects_voice_profile():
    m = model_cfg()
    env = {"MUSE_API_KEY": KEY, "MUSE_BASE_URL": BASE}
    with pytest.raises(ConfigInvalid, match="does not support"):
        build_settings("meta_voice", m, env)
    m["pricing"]["meta_voice"].update({"input_per_mtok_micros": 1, "cached_per_mtok_micros": 1, "output_per_mtok_micros": 1})
    with pytest.raises(ConfigInvalid, match="does not support"):
        build_settings("meta_voice", m, env)
    build_settings("meta", m, env)  # profil utama tetap jalan


def test_v15_health_hides_voice_profile(tmp_path):
    from fastapi.testclient import TestClient

    from backend.api.app import Service, create_app
    from backend.tokenizer import get_tokenizer

    from .pipeline_fakes import FakeEncoder
    m, b = cfgmod.load("model"), cfgmod.load("budget")
    assert "meta_voice" in m["profiles"]
    svc = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "runs", encoder=FakeEncoder(),
                  embed_cache_dir=tmp_path / "emb")
    app = create_app(svc, env={"MUSE_API_KEY": KEY, "MUSE_BASE_URL": BASE}, model_config=m, budget_config=b)
    h = TestClient(app).get("/api/health").json()
    assert [p["model_profile"] for p in h["model_profiles"]] == ["meta", "openrouter_dev", "baseten_open", "glimmer_local"]
    assert KEY not in json.dumps(h)


def test_v18_narrow_h028_guard_rejects_misconfigured_voice_profile():
    from .test_config import check_model_ids
    m = model_cfg()
    check_model_ids(m)
    for bad in ({"roles": ["voice_qa", "c"]}, {"for_reported_numbers": True}, {"api": "responses"},
                {"model": "muse-voice-transcribe-2.0"}):
        mm = model_cfg()
        mm["profiles"]["meta_voice"].update(bad)
        with pytest.raises(AssertionError):
            check_model_ids(mm)


# ---------- V11 (opener nyata): tanpa redirect, tanpa proxy ----------

def test_v11_real_opener_does_not_follow_redirect_or_use_proxy(monkeypatch):
    seen: list[str] = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            seen.append(self.path + "|" + (self.headers.get("Authorization") or ""))
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:%d/leak" % self.server.server_address[1])
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
        opener = vc._opener()
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/asr/transcribe", data=b"x",
                                     headers={"Authorization": "Bearer k"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as ei:
            opener.open(req, timeout=5)
        assert ei.value.code == 302
        assert seen == ["/asr/transcribe|Bearer k"]  # tidak ada permintaan kedua ke /leak; proxy env diabaikan
    finally:
        srv.shutdown()


def test_v11_transport_requires_https_before_any_connection(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("opener must not be built for http://")
    monkeypatch.setattr(vc, "_opener", boom)
    with pytest.raises(ConnectionError, match="https"):
        vc.urllib_transport("http://127.0.0.1:9/x", {}, b"", 1)


def test_v13_transport_maps_protocol_errors(monkeypatch):
    class Op:
        def open(self, req, timeout):
            raise http.client.IncompleteRead(b"partial")
    monkeypatch.setattr(vc, "_opener", lambda: Op())
    with pytest.raises(ConnectionError):
        vc.urllib_transport("https://127.0.0.1:9/x", {}, b"", 1)
