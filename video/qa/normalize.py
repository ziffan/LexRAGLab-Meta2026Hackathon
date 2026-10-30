"""Normalisasi teks VO + WER + pencocokan angka (spec docs/scenarios/M5.3-vo-qa-transcribe.md §6-§7).

Fungsi murni, tanpa jaringan. Naskah dan transkrip melewati `normalize` yang sama; WER dan urutan angka dihitung
atas token hasil normalisasi."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}
SUFFIX_MULT = {"k": 1000, "m": 1_000_000}
BREAK = "\x00"  # penanda tanda baca: memutus rangkaian angka, dibuang dari token akhir

_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")


def is_number(tok: str) -> bool:
    return bool(_NUM_RE.match(tok))


def canon_number(d: Decimal) -> str:
    """Bulat tanpa nol depan; desimal tanpa nol belakang; tanpa notasi eksponen."""
    if d == d.to_integral_value():
        return str(int(d))
    s = format(d.normalize(), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _pre(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("&", " and ").replace("%", " percent ")
    t = re.sub(r"\b(every|any|no|some)[\s-]+one\b", r"\1one", t)  # "every one" = "everyone": bukan angka
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)                       # 1,783 -> 1783
    t = re.sub(r"\b1\s*/\s*10\b", " 0.1 ", t)                        # 1/10 -> 0.1
    t = re.sub(r"\$\s*(\d+(?:\.\d+)?)", r" \1 dollars ", t)          # $0.56 -> 0.56 dollars
    t = re.sub(r"(?<!\d)\.(?!\d)|(?<=\d)\.(?!\d)|(?<!\d)\.(?=\d)", f" {BREAK} ", t)  # titik bukan desimal
    t = re.sub(r"[,;:!?()\"—–]", f" {BREAK} ", t)
    t = t.replace("-", " ").replace("'", "")
    t = re.sub(r"[^\w.\x00 ]", " ", t)
    return t


def _split_digit_suffix(tok: str) -> list[str]:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]+)", tok)
    if not m:
        return [tok]
    num, suf = m.group(1), m.group(2)
    if suf in SUFFIX_MULT:
        return [canon_number(Decimal(num) * SUFFIX_MULT[suf])]
    if suf == "th" and num == "10":
        return ["10th"]
    return [num, suf]


@dataclass
class _Acc:
    """Akumulator satu rangkaian angka. `parts` = segmen string tergabung (gaya baca berpasangan)."""
    parts: list[str] = field(default_factory=list)
    total: Decimal = Decimal(0)
    cur: Decimal = Decimal(0)
    last: str | None = None  # unit | teen | tens | hundred | scale | digit
    active: bool = False

    def value_str(self) -> str:
        return canon_number(self.total + self.cur)

    def flush_segment(self) -> None:
        if self.active:
            self.parts.append(self.value_str())
        self.total, self.cur, self.last, self.active = Decimal(0), Decimal(0), None, False

    def result(self) -> str | None:
        self.flush_segment()
        if not self.parts:
            return None
        out = "".join(self.parts)
        self.parts = []
        return canon_number(Decimal(out))


def _small_kind(w: str) -> str | None:
    if w in UNITS:
        return "unit"
    if w in TEENS:
        return "teen"
    if w in TENS:
        return "tens"
    return None


def _small_val(w: str) -> int:
    return UNITS.get(w, TEENS.get(w, TENS.get(w, 0)))


def _parse_numbers(tokens: list[str]) -> list[str]:
    """Ganti rangkaian kata/digit angka dengan satu token bilangan per bilangan (§6.4)."""
    out: list[str] = []
    acc = _Acc()
    i, n = 0, len(tokens)

    def emit() -> None:
        r = acc.result()
        if r is not None:
            out.append(r)

    while i < n:
        w = tokens[i]
        nxt = tokens[i + 1] if i + 1 < n else None
        kind = _small_kind(w)
        if w == BREAK:
            emit()
            i += 1
            continue
        if w == "a" and nxt in ("hundred", "thousand", "million", "billion"):
            emit()
            acc.cur, acc.last, acc.active = Decimal(1), "unit", True
            i += 1
            continue
        if w in ("a", "one", "1") and nxt in ("tenth", "10th"):
            emit()
            out.append("0.1")
            i += 2
            continue
        if w in ("tenth", "10th"):
            emit()
            out.append("0.1")
            i += 1
            continue
        if kind is not None or is_number(w):
            v = Decimal(_small_val(w)) if kind else Decimal(w)
            k = kind or "digit"
            if acc.active:
                joinable = (acc.last == "tens" and k == "unit") or acc.last in ("hundred", "scale")
                if acc.last == "scale" and k == "digit":
                    joinable = False
                if not joinable:
                    if k == "digit" or acc.last == "digit":
                        emit()  # dua bilangan digit/kata berdampingan tanpa pola baca berpasangan -> bilangan terpisah
                    else:
                        acc.flush_segment()  # gaya baca berpasangan: gabung string (eight sixteen -> 816)
            acc.cur += v
            acc.last, acc.active = k, True
            i += 1
            continue
        if w == "hundred" and acc.active and acc.last != "scale":
            acc.cur = (acc.cur or Decimal(1)) * 100
            acc.last = "hundred"
            i += 1
            continue
        if w in SCALES:
            if not acc.active:
                acc.cur, acc.active = Decimal(1), True
            acc.total += (acc.cur or Decimal(1)) * SCALES[w]
            acc.cur, acc.last = Decimal(0), "scale"
            i += 1
            continue
        if w == "and" and acc.active and acc.last == "hundred" and nxt is not None and _small_kind(nxt):
            i += 1
            continue
        if w == "point" and acc.active and nxt is not None and (nxt in UNITS or nxt.isdigit()):
            j = i + 1
            digits = ""
            while j < n and (tokens[j] in UNITS or tokens[j].isdigit()):
                digits += str(UNITS[tokens[j]]) if tokens[j] in UNITS else tokens[j]
                j += 1
            base = acc.result() or "0"
            out.append(canon_number(Decimal(f"{base}.{digits}")))
            i = j
            continue
        emit()
        out.append(w)
        i += 1
    emit()
    return out


def _cents(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if i + 1 < len(tokens) and tokens[i + 1] == "cents" and t.isdigit() and int(t) < 100:
            out += [canon_number(Decimal(int(t)) / 100), "dollars"]
            i += 2
            continue
        out.append(t)
        i += 1
    return out


def _join_terms(tokens: list[str], joined_terms: tuple[str, ...]) -> list[str]:
    pairs = {}
    for term in joined_terms:
        m = re.fullmatch(r"([a-z]+)(\d+)", term)
        if m:
            pairs[(m.group(1), m.group(2))] = term
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens) and (tokens[i], tokens[i + 1]) in pairs:
            out.append(pairs[(tokens[i], tokens[i + 1])])
            i += 2
            continue
        out.append(tokens[i])
        i += 1
    return out


def normalize(text: str, joined_terms: tuple[str, ...] = ("bm25",)) -> list[str]:
    raw = _pre(text).split()
    toks: list[str] = []
    for t in raw:
        if t == BREAK:
            toks.append(BREAK)
            continue
        toks += _split_digit_suffix(t) if t[0].isdigit() else [t]
    toks = [t for t in (x.strip(".") if x != BREAK else x for x in toks) if t]
    parsed = _parse_numbers(toks)
    parsed = [t for t in parsed if t != BREAK]
    return _join_terms(_cents(parsed), tuple(joined_terms))


def numbers(tokens: list[str]) -> list[str]:
    return [t for t in tokens if is_number(t)]


@dataclass(frozen=True)
class Op:
    op: str  # "sub" | "del" | "ins"
    ref: str | None
    hyp: str | None


def align(ref: list[str], hyp: list[str]) -> tuple[int, list[Op]]:
    """Levenshtein kata dengan jejak operasi (deterministik: sub > del > ins saat seri)."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j - 1] + c, d[i - 1][j] + 1, d[i][j - 1] + 1)
    ops: list[Op] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            if ref[i - 1] != hyp[j - 1]:
                ops.append(Op("sub", ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(Op("del", ref[i - 1], None))
            i -= 1
        else:
            ops.append(Op("ins", None, hyp[j - 1]))
            j -= 1
    ops.reverse()
    return d[n][m], ops


@dataclass(frozen=True)
class SceneResult:
    scene: str
    verdict: str  # pass | review | fail
    wer_bp: int
    errors: int
    ref_words: int
    numbers_script: list[str]
    numbers_transcript: list[str]
    number_diffs: list[Op]
    word_diffs: list[Op]


def compare(scene: str, script: str, transcript: str, threshold_bp: int,
            joined_terms: tuple[str, ...] = ("bm25",)) -> SceneResult:
    ref, hyp = normalize(script, joined_terms), normalize(transcript, joined_terms)
    errs, ops = align(ref, hyp)
    wer_bp = (errs * 10000 + len(ref) - 1) // len(ref) if ref else (0 if not hyp else 10000)
    ns, nt = numbers(ref), numbers(hyp)
    _, nops = align(ns, nt)
    if ns != nt:
        verdict = "fail"
    elif wer_bp > threshold_bp:
        verdict = "review"
    else:
        verdict = "pass"
    return SceneResult(scene, verdict, wer_bp, errs, len(ref), ns, nt, nops, ops)
