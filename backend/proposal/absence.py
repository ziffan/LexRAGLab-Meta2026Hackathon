"""Pemeriksaan ketiadaan jawaban lokal untuk usulan `unanswerable` (H-087, H-092; scenarios/M2.1-unanswerable P2, P3, P5, P15).

Deterministik, tanpa Model API, tanpa jaringan. Unit cari = potongan chunker `structure_schema` skema A akta aktif (H-088).
Satu fungsi tokenisasi dipakai pemeriksa DAN BM25 produksi (`backend.retrieval.bm25.tokenize`); ranker BM25/dense disuntik.

- `T(q)` = token isi query berbeda-beda (stopword dibuang oleh tokenizer). Token generik = muncul di unit dengan
  `df/N > generic_df_ratio`; `T*(q) = T(q)` tanpa token generik. `cov(q, u) = |T*(q) & T(u)| / |T*(q)|`.
- Himpunan periksa = top-K BM25 + top-K dense (gabungan unit). `max_cov` = pecahan integer `{num, den}`: `num` = irisan
  terbesar atas himpunan periksa, `den = |T*(q)|`; `0/0` didefinisikan 0 dan tidak pernah `lexical_overlap`.
- Alasan (urutan tetap): `lexical_overlap` (`max_cov >= ambang`, inklusif, dibandingkan sebagai pecahan eksak),
  `dense_similar` (cosine maksimum top-K dense >= ambang, inklusif), `no_distinctive_terms` (`T*` kosong),
  `dense_unavailable` (produksi selalu mencoba dense; encoder tidak tersedia). `AbsenceChecker.dense_off=True` hanya seam uji:
  dense sengaja mati, tanpa alasan apa pun dan `max_cosine = null`.
- Status `doubtful` bila ada >= 1 alasan; tidak pernah membuang kandidat (P3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from backend import config as _config
from backend.spark.errors import ConfigInvalid
from backend.spark.store import canonical_json, sha256_hex

REASONS = ("lexical_overlap", "dense_similar", "no_distinctive_terms", "dense_unavailable")
Unit = tuple[str, str]  # (unit_id, teks)
Tokenizer = Callable[[str], list[str]]
Ranker = Callable[[str], list[tuple[str, float]]]  # ranking penuh (unit_id, skor) menurun; seri dipecah unit_id


class DenseUnavailable(Exception):
    """Encoder dense tidak tersedia (model tak ada di cache lokal, tanpa GPU/CPU yang cukup, dll)."""


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _frac(v: Any, name: str) -> Fraction:
    """Pecahan eksak dari angka TOML (desimal dibaca sebagai teks, bukan float biner)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigInvalid(f"config/proposals [unanswerable]: {name} must be a number")
    f = Fraction(str(v))
    if f < 0 or f > 1:
        raise ConfigInvalid(f"config/proposals [unanswerable]: {name} must be between 0 and 1")
    return f


@dataclass(frozen=True)
class AbsenceConfig:
    check_top_k: int
    lexical_coverage_threshold: Fraction
    generic_df_ratio: Fraction
    dense_cosine_threshold: float
    device: str
    max_per_call: int
    projection_expected_output_tokens: int

    def hash_basis(self) -> dict[str, Any]:
        return {"check_top_k": self.check_top_k, "lexical_coverage_threshold": str(self.lexical_coverage_threshold),
                "generic_df_ratio": str(self.generic_df_ratio), "dense_cosine_threshold": self.dense_cosine_threshold}


def load_absence_config(config_dir: Path | None = None, cfg: Mapping[str, Any] | None = None) -> AbsenceConfig:
    """Muat `config/proposals.toml` tabel `[unanswerable]`. Nilai tidak sah -> `ConfigInvalid` (`config_invalid`) saat dimuat."""
    raw = cfg if cfg is not None else _config.load("proposals", config_dir)
    t = raw.get("unanswerable")
    if not isinstance(t, Mapping):
        raise ConfigInvalid("config/proposals: table [unanswerable] is missing")
    k, mx, ex = t.get("check_top_k"), t.get("max_per_call"), t.get("projection_expected_output_tokens")
    if not _is_int(k) or k <= 0:
        raise ConfigInvalid("config/proposals [unanswerable]: check_top_k must be an integer > 0")
    if not _is_int(mx) or mx <= 0:
        raise ConfigInvalid("config/proposals [unanswerable]: max_per_call must be an integer > 0")
    if not _is_int(ex) or ex < 0:
        raise ConfigInvalid("config/proposals [unanswerable]: projection_expected_output_tokens must be an integer >= 0")
    cos = t.get("dense_cosine_threshold")
    if isinstance(cos, bool) or not isinstance(cos, (int, float)) or not (-1 <= cos <= 1):
        raise ConfigInvalid("config/proposals [unanswerable]: dense_cosine_threshold must be a number in [-1, 1]")
    dev = t.get("device")
    if not isinstance(dev, str) or not dev.strip():
        raise ConfigInvalid('config/proposals [unanswerable]: device must be a non-empty string (e.g. "cpu")')
    return AbsenceConfig(int(k), _frac(t.get("lexical_coverage_threshold"), "lexical_coverage_threshold"),
                         _frac(t.get("generic_df_ratio"), "generic_df_ratio"), float(cos), dev.strip(), int(mx), int(ex))


def normalize_query(q: str) -> str:
    """Kunci duplikat (SU21): dipangkas, huruf kecil, spasi dalam dilipat."""
    return re.sub(r"\s+", " ", q.strip().lower())


def config_hash_of(cfg: AbsenceConfig) -> str:
    return sha256_hex(canonical_json(cfg.hash_basis()))


@dataclass
class AbsenceChecker:
    """Pemeriksa untuk satu dokumen. `units` urut dokumen; `bm25_rank`/`dense_rank` mengembalikan ranking penuh atau dipotong."""

    units: Sequence[Unit]
    tokenize: Tokenizer
    bm25_rank: Ranker
    dense_rank: Ranker | None
    cfg: AbsenceConfig
    dense_off: bool = False  # seam uji SAJA (dense sengaja mati); produksi tidak pernah mengisinya

    def __post_init__(self) -> None:
        self._text = dict(self.units)
        self._toks = {uid: set(self.tokenize(t)) for uid, t in self.units}
        n = len(self.units)
        df: dict[str, int] = {}
        for ts in self._toks.values():
            for tok in ts:
                df[tok] = df.get(tok, 0) + 1
        r = self.cfg.generic_df_ratio
        # df/N > r  <=>  df * r.denominator > r.numerator * N (pecahan eksak)
        self.generic = frozenset(tok for tok, c in df.items() if n and c * r.denominator > r.numerator * n)

    @property
    def config_hash(self) -> str:
        return config_hash_of(self.cfg)

    def check(self, query: str) -> dict[str, Any]:
        k = self.cfg.check_top_k
        t_star = set(self.tokenize(query)) - self.generic
        bm = [(uid, s) for uid, s in self.bm25_rank(query)][:k]
        top_k = [{"source": "bm25", "rank": i, "unit_text": self._text[uid]} for i, (uid, _s) in enumerate(bm, 1)]
        considered = [uid for uid, _s in bm]
        max_cos: float | None = None
        unavailable = False
        if not self.dense_off:
            if self.dense_rank is None:
                unavailable = True
            else:
                try:
                    dn = [(uid, float(s)) for uid, s in self.dense_rank(query)][:k]
                except Exception:  # noqa: BLE001  encoder hilang/gagal = tidak tersedia, bukan galat 500
                    unavailable = True
                    dn = []
                top_k += [{"source": "dense", "rank": i, "unit_text": self._text[uid]} for i, (uid, _s) in enumerate(dn, 1)]
                considered += [uid for uid, _s in dn]
                if dn:
                    max_cos = round(max(s for _u, s in dn), 6)
        num = max((len(t_star & self._toks[uid]) for uid in considered), default=0) if t_star else 0
        den = len(t_star)
        reasons: list[str] = []
        if den and num * self.cfg.lexical_coverage_threshold.denominator >= self.cfg.lexical_coverage_threshold.numerator * den:
            reasons.append("lexical_overlap")
        if max_cos is not None and max_cos >= self.cfg.dense_cosine_threshold:
            reasons.append("dense_similar")
        if den == 0:
            reasons.append("no_distinctive_terms")
        if unavailable:
            reasons.append("dense_unavailable")
        return {"status": "doubtful" if reasons else "ok", "reasons": reasons, "max_cov": {"num": num, "den": den},
                "max_cosine": max_cos, "top_k": top_k, "config_hash": self.config_hash}


# ----------------------------------------------------------------------------- produksi
def production_checker(units: Sequence[Unit], cfg: AbsenceConfig, retrieval_cfg: Mapping[str, Any], *,
                       dense_factory: Callable[[], Ranker] | None = None, dense_off: bool = False) -> AbsenceChecker:
    """Pemeriksa produksi: `Bm25Retriever` + `tokenize` dari `config/retrieval [bm25]`; dense lewat `dense_factory` (malas: dibuat
    saat pertama dipakai; gagal -> `dense_unavailable`). `dense_factory = None` -> dense tidak tersedia."""
    from backend.retrieval.bm25 import Bm25Retriever, tokenize

    b = retrieval_cfg["bm25"]
    stem, stop = bool(b["stemming"]), bool(b["stopwords"])
    bm = Bm25Retriever(list(units), k1=float(b["k1"]), b=float(b["b"]), stemming=stem, stopwords=stop)
    dense: Ranker | None = None
    if dense_factory is not None:
        state: dict[str, Any] = {}

        def dense(query: str) -> list[tuple[str, float]]:  # type: ignore[misc]
            if "err" in state:  # memo kegagalan: encoder tidak dicoba ulang per kandidat
                raise DenseUnavailable(state["err"])
            if "r" not in state:
                try:
                    state["r"] = dense_factory()
                except Exception as exc:  # noqa: BLE001
                    state["err"] = type(exc).__name__
                    raise DenseUnavailable(state["err"]) from None
            return state["r"](query)

    return AbsenceChecker(units, lambda text: tokenize(text, stemming=stem, stopwords=stop), lambda q: bm.rank(q), dense, cfg, dense_off=dense_off)


def encoder_dense_ranker(units: Sequence[Unit], retrieval_cfg: Mapping[str, Any], *, device: str | None = None,
                         encoder: Any = None, cache_dir: Path | None = None) -> Ranker:
    """Ranker dense bge-m3 lokal (H-042) atas `units`. Gagal membangun encoder/embedding -> `DenseUnavailable`.
    `device="cpu"` untuk menghindari rebutan VRAM dengan Glimmer (H-047)."""
    try:
        from backend.retrieval.dense import embed_chunks, encoder_from_config, rank_dense

        enc = encoder if encoder is not None else encoder_from_config(retrieval_cfg, device)
        emb = embed_chunks(enc, list(units), cache_dir=cache_dir)
    except Exception as exc:  # noqa: BLE001
        raise DenseUnavailable(type(exc).__name__) from None

    def rank(query: str) -> list[tuple[str, float]]:
        return rank_dense(enc, emb, query, cache_dir=cache_dir)

    return rank


def service_checker_provider(base: Any, *, device: str | None = None, encoder: Any = None,
                             cache_dir: Path | None = None) -> Callable[[Any], AbsenceChecker]:
    """Penyedia pemeriksa produksi untuk `ProposalService`: unit cari = potongan `structure_schema` skema A akta AKTIF (H-075,
    H-088) lewat `base` (`backend.api.service.Service`); BM25 dan tokenisasi dari `config/retrieval [bm25]`; dense bge-m3 lokal
    di `device` (CLI `--device cpu`), dibangun malas dan gagal -> `dense_unavailable`. Pemeriksa di-cache per
    (doc_id, clean_sha256, identitas skema)."""
    from backend.api.errors import ApiError
    from backend.chunking import schema_identity

    cache: dict[tuple[Any, ...], AbsenceChecker] = {}

    def provide(doc: Any) -> AbsenceChecker:
        sb = base.schema_binding(doc.family)
        rec = sb.active() if sb is not None else None
        if rec is None:
            raise ApiError(404, "not_found", f"No schema A record for family {doc.family!r}; the search units cannot be built.")
        ident = schema_identity(rec)
        key = (doc.doc_id, doc.clean_sha256, ident["schema_version"], ident["schema_hash"])
        if key not in cache:
            cdoc = base.doc(doc.doc_id)
            units = [(c["chunk_id"], cdoc.text[c["start"]:c["end"]]) for c in base.schema_chunks(cdoc, rec["schema_version"])]
            rcfg = base.cfg("retrieval")
            acfg_ = load_absence_config(base.config_dir)
            dev = device or acfg_.device  # --device menimpa config (H-047)
            cache[key] = production_checker(
                units, acfg_, rcfg,
                dense_factory=lambda: encoder_dense_ranker(units, rcfg, device=dev, encoder=encoder, cache_dir=cache_dir))
        return cache[key]

    return provide
