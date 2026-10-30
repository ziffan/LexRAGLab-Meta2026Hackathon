"""Baca WAV dan konversi ke format Muse Voice Transcribe: RIFF/WAVE mono PCM 16-bit 16/24 kHz (spec §3).

Hanya stdlib `wave` + numpy (sudah dipin). Hasil konversi hanya di memori."""

from __future__ import annotations

import io
import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CONVERT_VERSION = "r1"
TARGET_RATES = (24000, 16000)
MAX_SECONDS = 600
MAX_BODY_BYTES = 32 * 1024 * 1024
FIR_TAPS = 129


class AudioError(ValueError):
    """Audio tidak bisa dikirim (format, laju, durasi, ukuran)."""


@dataclass(frozen=True)
class Audio:
    wav_bytes: bytes      # WAV hasil konversi (mono, 16-bit, laju tujuan)
    rate: int
    frames: int
    source_rate: int
    source_channels: int

    @property
    def seconds_ceil(self) -> int:
        return -(-self.frames // self.rate)

    @property
    def seconds(self) -> float:
        return self.frames / self.rate


def _lowpass(cutoff_norm: float, taps: int = FIR_TAPS) -> np.ndarray:
    """FIR windowed-sinc (Blackman), `cutoff_norm` = cutoff / laju asal (0..0.5). Gain DC = 1."""
    n = np.arange(taps) - (taps - 1) / 2
    h = 2 * cutoff_norm * np.sinc(2 * cutoff_norm * n) * np.blackman(taps)
    return h / h.sum()


def resample_int(x: np.ndarray, factor: int) -> np.ndarray:
    """Desimasi bilangan bulat dengan low-pass (cutoff 0,45 x laju tujuan)."""
    if factor == 1:
        return x
    h = _lowpass(0.45 / factor)
    y = np.convolve(x, h, mode="same")
    return y[::factor]


def _target(rate: int) -> tuple[int, int]:
    if rate in TARGET_RATES:
        return rate, 1
    for t in TARGET_RATES:
        if rate % t == 0:
            return t, rate // t
    raise AudioError(f"unsupported sample rate {rate} Hz (need 16000, 24000, or an integer multiple)")


def to_wav_bytes(samples: np.ndarray, rate: int) -> bytes:
    pcm = np.clip(np.round(samples), -32768, 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def load(path: Path) -> Audio:
    try:
        with wave.open(str(path), "rb") as w:
            ch, sw, rate, nframes = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            if w.getcomptype() != "NONE":
                raise AudioError("WAV is not integer PCM")
            raw = w.readframes(nframes)
    except wave.Error as exc:
        raise AudioError(f"not a PCM WAV file: {exc}") from None
    if sw != 2:
        raise AudioError(f"WAV must be 16-bit PCM (got {sw * 8}-bit)")
    if nframes / rate > MAX_SECONDS:
        raise AudioError(f"audio longer than {MAX_SECONDS} s")
    target, factor = _target(rate)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    y = resample_int(x, factor)
    data = to_wav_bytes(y, target)
    if len(data) > MAX_BODY_BYTES:
        raise AudioError("converted audio exceeds 32 MB")
    return Audio(wav_bytes=data, rate=target, frames=len(y), source_rate=rate, source_channels=ch)


def projected_micros(seconds_ceil: int, audio_per_hour_micros: int) -> int:
    """Batas atas: detik dibulatkan ke atas x harga per jam / 3600, dibulatkan ke atas (spec §4)."""
    return -(-seconds_ceil * audio_per_hour_micros // 3600)


def billed_micros(audio_duration_ms: int, audio_per_hour_micros: int) -> int:
    """Tagihan: detik utuh dibulatkan ke bawah (pricing), lalu micro-USD dibulatkan ke atas (spec §4)."""
    return -(-(audio_duration_ms // 1000) * audio_per_hour_micros // 3600)


def rms_db(x: np.ndarray) -> float:
    r = float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0
    return 20 * math.log10(r) if r > 0 else -math.inf
