"""Header B sebagai sumbu grid (M3.2; H-004, H-046, H-066, H-069). Fungsi murni untuk akuntansi, tanpa jaringan.

- `HeaderStore`: pembaca `HeaderB` per `chunk_id` (store M3.1 `runs/headers/<granularity>/<prompt_hash[:12]>/<chunk_id>.json`)
  ditambah pencarian `clean_sha256` run B (`runs/spark/records/<run_id>.json`) untuk validitas (A5).
- `resolve_headers`: header SEMUA potongan setting (bukan hanya `P`) harus ada, sah, berasal dari teks bersih yang sama,
  dan berlabel granularitas yang sama; selain itu galat jelas per jenis (A4, A5, A14).
- `HeaderBinding`: store + granularitas + scope + identitas (hash isi store, `prompt_hash` B, model) untuk `config_hash` (A10).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

SCOPES = ("frontier_only", "all")
FIXED_SIZE = "fixed_size"
STRUCTURE_SCHEMA = "structure_schema"  # H-082: store sendiri; B dipanggil untuk semua potongan skema (tanpa reuse header Pasal)
GRANULARITY_DIRS = ("pasal", "ayat", FIXED_SIZE, STRUCTURE_SCHEMA)
FAMILY_STORE_SUBDIR = {"akta": "akta"}  # W63: store header per keluarga; UU PT tetap di akar `runs/headers/` (tanpa subdir)


def header_store_dir(runs_dir: Path, family: str = "uupt") -> Path:
    """Satu-satunya tempat jalur store header B per keluarga. UU PT: `<runs>/headers`; akta: `<runs>/headers/akta`, supaya
    `DirHeaderStore.content_hash()` UU PT (hash isi direktori, A10) tidak berubah oleh header akta (regresi 82ae86f)."""
    base = Path(runs_dir) / "headers"
    sub = FAMILY_STORE_SUBDIR.get(family)
    return base / sub if sub else base


# ---------- galat ----------
class HeaderError(Exception):
    """Header setting header-on tidak bisa dipakai. Setting itu gagal dan dicatat; run lanjut (A4, H-069)."""

    code = "header_error"

    def __init__(self, message: str, *, setting_id: str, chunk_id: str | None = None) -> None:
        super().__init__(message)
        self.setting_id, self.chunk_id = setting_id, chunk_id


class HeaderMissingError(HeaderError):
    code = "header_missing"


class HeaderInvalidError(HeaderError):
    """Header kosong atau hanya whitespace (token 0): "on" diam-diam sama dengan "off"."""

    code = "header_invalid"


class HeaderStaleError(HeaderError):
    """Run B asal header memakai teks bersih lain (H-046) atau run asal tak ditemukan."""

    code = "header_stale"


class HeaderGranularityError(HeaderError):
    code = "granularity_mismatch"


@dataclass(frozen=True)
class FailedSetting:
    """Satu entri `RunRecord.failed_settings` (DATA-CONTRACTS §12)."""

    setting_id: str
    reason: str
    chunk_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"setting_id": self.setting_id, "reason": self.reason, "chunk_id": self.chunk_id}


def failed_from_error(err: HeaderError) -> FailedSetting:
    return FailedSetting(err.setting_id, err.code, err.chunk_id)


# ---------- store ----------
class HeaderStore(Protocol):
    def get(self, chunk_id: str, granularity: str) -> Mapping[str, Any] | None:
        """Record `HeaderB` (DATA-CONTRACTS §7: chunk_id, header, granularity, run_id, ...) atau None."""

    def run_clean_sha256(self, run_id: str) -> str | None:
        """`clean_sha256` RunRecord run B; None bila run tak ditemukan."""

    def content_hash(self) -> str:
        """Hash isi store (pasangan chunk_id -> teks header). `run_id` tidak ikut (A10)."""


def _pairs_hash(pairs: Iterable[tuple[str, str]]) -> str:
    rows = sorted(pairs)
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


class MemoryHeaderStore:
    """Store dalam memori (test dan pemakai programatik). `requests` mencatat tiap permintaan header (spy)."""

    def __init__(self, records: Mapping[str, Mapping[str, Any]] | None = None, runs: Mapping[str, str] | None = None) -> None:
        self.records: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (records or {}).items()}
        self.runs: dict[str, str] = dict(runs or {})
        self.requests: list[str] = []

    def get(self, chunk_id: str, granularity: str) -> Mapping[str, Any] | None:
        self.requests.append(chunk_id)
        return self.records.get(chunk_id)

    def run_clean_sha256(self, run_id: str) -> str | None:
        return self.runs.get(run_id)

    def content_hash(self) -> str:
        return _pairs_hash((cid, str(r.get("header", ""))) for cid, r in self.records.items())


class DirHeaderStore:
    """Store berkas M3.1: `<headers_dir>/<granularity>/<prompt_hash[:12]>/<chunk_id>.json`. Granularitas yang diminta dicari
    dulu; bila `chunk_id` hanya ada di granularitas lain, record itu dikembalikan apa adanya (berlabel granularitasnya)
    sehingga ketidakcocokan terdeteksi (A14)."""

    def __init__(self, headers_dir: Path, prompt_hash: str, runs_dir: Path) -> None:
        self.headers_dir, self.prompt12, self.runs_dir = Path(headers_dir), prompt_hash[:12], Path(runs_dir)

    def _read(self, gran: str, chunk_id: str) -> dict[str, Any] | None:
        if not chunk_id or any(c in chunk_id for c in "/\\"):
            return None
        try:
            d = json.loads((self.headers_dir / gran / self.prompt12 / f"{chunk_id}.json").read_bytes().decode("utf-8"))
        except (OSError, ValueError):
            return None
        return d if isinstance(d, dict) else None

    def get(self, chunk_id: str, granularity: str) -> Mapping[str, Any] | None:
        for g in (granularity, *[x for x in GRANULARITY_DIRS if x != granularity]):
            d = self._read(g, chunk_id)
            if d is not None:
                return {**d, "granularity": g}
        return None

    def run_clean_sha256(self, run_id: str) -> str | None:
        if not run_id or any(c in run_id for c in "/\\"):
            return None
        try:
            d = json.loads((self.runs_dir / "spark" / "records" / f"{run_id}.json").read_bytes().decode("utf-8"))
        except (OSError, ValueError):
            return None
        v = d.get("clean_sha256") if isinstance(d, dict) else None
        return v if isinstance(v, str) else None

    def content_hash(self) -> str:
        pairs: list[tuple[str, str]] = []
        for g in GRANULARITY_DIRS:
            for p in sorted((self.headers_dir / g / self.prompt12).glob("*.json")):
                try:
                    h = json.loads(p.read_bytes().decode("utf-8")).get("header", "")
                except (OSError, ValueError, AttributeError):
                    h = ""
                pairs.append((f"{g}/{p.stem}", str(h)))
        return _pairs_hash(pairs)


# ---------- binding ----------
@dataclass(frozen=True)
class HeaderBinding:
    store: HeaderStore
    granularity: str  # config/header_b `granularity` (pasal | ayat)
    scope: str = "frontier_only"
    prompt_hash: str = ""
    model: str = ""
    # H-101 (grid pembanding): blok identitas model pembanding (profile, provider, model, quantization, effort). None pada
    # binding utama sehingga `identity()` dan `pipeline_config_hash` utama TIDAK berubah (G-38); terisi hanya di binding pembanding.
    compare: Mapping[str, Any] | None = field(default=None, hash=False, compare=False)
    # H-102 S11: kebijakan cakupan sebagian `(policy, threshold_pct)` HANYA untuk binding pembanding profil sapuan; None = strict persis
    # (binding utama dan profil non-sapuan tidak pernah memakainya). `mask`: chunk_id yang diperlakukan tanpa header (titik rujukan).
    coverage: tuple[str, int] | None = field(default=None, hash=False, compare=False)
    mask: frozenset[str] = field(default=frozenset(), hash=False, compare=False)

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise ValueError(f"header_b.scope must be one of {list(SCOPES)}, got {self.scope!r}")

    def expected_granularity(self, chunker: str) -> str:
        """`fixed_size` dan `structure_schema` memakai store sendiri (H-069, H-082); `structure_handwritten` memakai
        granularitas config."""
        return chunker if chunker in (FIXED_SIZE, STRUCTURE_SCHEMA) else self.granularity

    def identity(self) -> dict[str, str]:
        """Komponen `config_hash` grid (A10): isi store, granularitas, `prompt_hash` B, model, scope. Tanpa `run_id`."""
        d = {"store": self.store.content_hash(), "granularity": self.granularity, "prompt_hash": self.prompt_hash,
             "model": self.model, "scope": self.scope}
        if self.compare is not None:
            d["compare"] = dict(self.compare)  # hanya binding pembanding (H-101)
        return d


# ---------- akuntansi ----------
def covered(headered: int, chunks: int, pct: int) -> bool:
    """S11(a): `headered x 100 >= pct x chunks` (inklusif, tanpa float). Satu-satunya sumber ambang cakupan."""
    return headered * 100 >= pct * chunks


def resolve_headers(chunks: Sequence[Any], store: HeaderStore, *, setting_id: str, granularity: str,
                    clean_sha256: str, coverage: tuple[str, int] | None = None, mask: Iterable[str] = (),
                    report: dict[str, Any] | None = None) -> dict[str, str]:
    """Header tiap potongan (`chunk_id` -> teks, tanpa strip; tokenisasi nanti atas string itu saja).
    Diperiksa untuk SEMUA potongan, berurutan menurut offset awal naik; galat pertama menang.

    `coverage = (policy, pct)` dengan policy `mask_*` (H-102 S11, hanya grid pembanding profil sapuan): potongan yang tak
    punya header di store DILEWATI (tanpa kunci di hasil -> diindeks tanpa header, token header 0) selama
    `headered x 100 >= pct x n` (inklusif); di bawah ambang tetap `HeaderMissingError` (chunk_id pertama yang hilang, urut dokumen).
    `mask`: chunk_id yang dipaksa tanpa header (titik rujukan Contributor). `report` diisi {chunks, headered, coverage_bp, missing}.
    Tanpa `coverage`/`mask` perilaku persis lama."""
    out: dict[str, str] = {}
    runs: dict[Any, str | None] = {}
    lenient = coverage is not None and coverage[0] != "strict"
    forced = set(mask)
    missing: list[str] = []
    for c in sorted(chunks, key=lambda c: (c.start, c.end, c.chunk_id)):
        cid = c.chunk_id
        if cid in forced:
            missing.append(cid)
            continue
        rec = store.get(cid, granularity)
        if rec is None and lenient:
            missing.append(cid)
            continue
        if rec is None:
            raise HeaderMissingError(f"header missing for chunk_id {cid} (setting_id {setting_id})",
                                     setting_id=setting_id, chunk_id=cid)
        if rec.get("granularity") != granularity:
            raise HeaderGranularityError(
                f"header granularity mismatch for chunk_id {cid} (setting_id {setting_id}): store has "
                f"{rec.get('granularity')!r}, config requires {granularity!r}", setting_id=setting_id, chunk_id=cid)
        run_id = rec.get("run_id")
        if run_id not in runs:
            runs[run_id] = store.run_clean_sha256(run_id) if isinstance(run_id, str) else None
        found = runs[run_id]
        if found != clean_sha256:
            raise HeaderStaleError(
                f"header for chunk_id {cid} (setting_id {setting_id}) comes from run B {run_id!r} with clean_sha256 "
                f"{found!r}, but the grid run uses clean_sha256 {clean_sha256!r}", setting_id=setting_id, chunk_id=cid)
        h = rec.get("header")
        if not isinstance(h, str) or not h.strip():
            raise HeaderInvalidError(f"header is empty (0 tokens) for chunk_id {cid} (setting_id {setting_id})",
                                     setting_id=setting_id, chunk_id=cid)
        out[cid] = h
    if (lenient or forced) and report is not None:
        n = len(chunks)
        report.update({"chunks": n, "headered": n - len(missing), "coverage_bp": ((n - len(missing)) * 10000 // n) if n else 0,
                       "missing": list(missing)})
    if missing and not forced:
        assert coverage is not None
        n, pct = len(chunks), coverage[1]
        if not covered(n - len(missing), n, pct):
            raise HeaderMissingError(f"header missing for chunk_id {missing[0]} (setting_id {setting_id}); coverage "
                                     f"{n - len(missing)}/{n} is below {pct}%", setting_id=setting_id, chunk_id=missing[0])
    return out


def index_text(header: str, source: str) -> str:
    """Teks yang diindeks setting header-on (A7): header dulu, lalu teks sumber."""
    return header + "\n" + source


def twin_key(s: Any) -> Any:
    """Setting tanpa `setting_id` dan `header_b`: dua kembaran punya kunci yang sama."""
    return replace(s, setting_id="", header_b=False)


def series_of(points: Iterable[Any], settings: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Partisi titik menurut `Setting.header_b` (tampilan "dua deret"; frontier tetap gabungan, A1)."""
    out: dict[str, list[Any]] = {"off": [], "on": []}
    for p in points:
        out["on" if settings[p.setting_id].header_b else "off"].append(p)
    return out
