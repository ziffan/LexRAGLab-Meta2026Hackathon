"""H-101 bagian 1: store pembanding B open-weight, identitas, dan pemeriksa identitas utama. Tanpa jaringan.

- Jalur store: `runs/headers_compare/<profile>/` (UU PT) dan `.../<profile>/akta/` (akta), DI LUAR `runs/headers/` (G-38).
  Penolakan tumpang tindih membandingkan KOMPONEN jalur nyata (`resolve`, symlink diikuti, huruf besar/kecil dilipat bila
  sistem berkas tak peka huruf; penentu disuntikkan), bukan awalan teks.
- `identity.json` per profil (P2): `{profile, provider, model, quantization, effort, prompt_hash, max_header_tokens,
  schema_max_length_chars}`; identitas berbeda ditolak sebelum jaringan.
- Pemeriksa identitas utama (P3): potret sebelum/sesudah (hash isi store UU PT dan akta, daftar (jalur, sha256) seluruh
  `runs/headers`, `runs/grid`, `runs/schemas`) dan galat `main_identity_changed` dengan himpunan item yang berubah.
- Validasi profil pembanding (P11, P18) dan config (P14 `max_attempts`, Q-B10 `projection.<profile>`, P17 kunci terlarang)."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from backend.grid.headers import FAMILY_STORE_SUBDIR, DirHeaderStore, header_store_dir
from backend.spark.errors import ConfigInvalid

COMPARE_DIR = "headers_compare"
IDENTITY_FILE = "identity.json"
IDENTITY_FIELDS = ("profile", "provider", "model", "quantization", "effort", "prompt_hash", "max_header_tokens",
                   "schema_max_length_chars")
FORBIDDEN_PROFILE_KEYS = ("max_header_tokens", "schema_max_length_chars")  # P17: validator tetap, tak boleh per profil
DEFAULT_MAX_ATTEMPTS = 8  # D5 (H-081): dipakai bila profil tak tercantum di `[max_attempts]`
GLIMMER_PROJECTION_KEYS = ("prefill_tokens_per_s", "base_ms", "output_tokens_per_10s")


class CompareError(Exception):
    """Galat pembanding dengan kode mesin (`config_invalid`, `compare_store_overlaps_main`, `compare_identity_mismatch`, ...)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class MainIdentityChanged(CompareError):
    def __init__(self, items: set[str]) -> None:
        super().__init__("main_identity_changed", "the main (Contributor) identity changed: " + ", ".join(sorted(items)))
        self.items = frozenset(items)


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


# ---------------------------------------------------------------- profil
def validate_profile_name(name: Any) -> str:
    """Nama profil aman sebagai komponen jalur: tidak kosong, tanpa `/`, `\\`, `..`."""
    if not isinstance(name, str) or not name.strip() or name != name.strip() or "/" in name or "\\" in name or ".." in name:
        raise CompareError("config_invalid", "profile name must be non-empty and contain no '/', '\\' or '..'")
    return name


def check_forbidden_profile_keys(model_cfg: Mapping[str, Any]) -> None:
    """P17: `max_header_tokens` / `schema_max_length_chars` di tabel `[profiles.*]` = `config_invalid`. Kunci tak dikenal lain
    tetap diabaikan seperti sekarang."""
    profiles = model_cfg.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ConfigInvalid("config/model: [profiles] is missing")
    for name, p in profiles.items():
        if isinstance(p, Mapping):
            for k in FORBIDDEN_PROFILE_KEYS:
                if k in p:
                    raise ConfigInvalid(f"config/model: profile '{name}' must not set '{k}' (the header validator is the "
                                        f"same for every model; set it in config/header_b)")


def comparison_profile(model_cfg: Mapping[str, Any], name: Any) -> Mapping[str, Any]:
    """Profil pembanding B: harus ada, bukan profil bawaan/Contributor, `roles` ada dan memuat "b" (P11, P18, Q-B12)."""
    validate_profile_name(name)
    profiles = model_cfg.get("profiles")
    prof = profiles.get(name) if isinstance(profiles, Mapping) else None
    if not isinstance(prof, Mapping):
        raise CompareError("config_invalid", f"unknown profile '{name}'")
    if name == model_cfg.get("default_profile") or prof.get("for_reported_numbers"):
        raise CompareError("config_invalid", f"profile '{name}' is the Contributor/reported profile; its store is runs/headers")
    roles = prof.get("roles")
    if not isinstance(roles, list):
        raise CompareError("config_invalid", f"profile '{name}' has no 'roles'; it cannot be a comparison profile")
    if "b" not in roles:
        raise CompareError("config_invalid", f"profile '{name}' has no role 'b'")
    return prof


# ---------------------------------------------------------------- config pembanding
def validate_compare_cfg(hc: Mapping[str, Any], model_cfg: Mapping[str, Any]) -> None:
    """`[max_attempts]` (P14) dan `[projection.<profile>]` (Q-B10) di config/header_b: integer >= 1, nama profil harus ada di
    config/model; selain itu `config_invalid`."""
    profiles = model_cfg.get("profiles")
    names = set(profiles) if isinstance(profiles, Mapping) else set()
    t = hc.get("max_attempts")
    if t is not None:
        if not isinstance(t, Mapping):
            raise ConfigInvalid("config/header_b: max_attempts must be a table")
        for k, v in t.items():
            if k not in names:
                raise ConfigInvalid(f"config/header_b: max_attempts.{k} is not a profile in config/model")
            if not _is_int(v) or v < 1:
                raise ConfigInvalid(f"config/header_b: max_attempts.{k} must be an integer >= 1")
    fb = hc.get("factor_bp")
    if fb is not None:
        if not isinstance(fb, Mapping):
            raise ConfigInvalid("config/header_b: factor_bp must be a table")
        for k, v in fb.items():
            if k not in names:
                raise ConfigInvalid(f"config/header_b: factor_bp.{k} is not a profile in config/model")
            if not _is_int(v) or v < 10000:
                raise ConfigInvalid(f"config/header_b: factor_bp.{k} must be an integer >= 10000")
    pr = hc.get("projection")
    if pr is not None:
        if not isinstance(pr, Mapping):
            raise ConfigInvalid("config/header_b: projection must be a table")
        for k, v in pr.items():
            if not isinstance(v, Mapping):
                continue  # kunci skalar (mis. doc_rpm) milik proyeksi yang sudah ada
            if k not in names:
                raise ConfigInvalid(f"config/header_b: projection.{k} is not a profile in config/model")
            for key in GLIMMER_PROJECTION_KEYS:
                x = v.get(key)
                if not _is_int(x) or x < 1:
                    raise ConfigInvalid(f"config/header_b: projection.{k}.{key} must be an integer >= 1")


def max_attempts_for(hc: Mapping[str, Any], profile: str) -> int:
    t = hc.get("max_attempts")
    v = t.get(profile) if isinstance(t, Mapping) else None
    return DEFAULT_MAX_ATTEMPTS if v is None else int(v)


def factor_bp_for(hc: Mapping[str, Any], profile: str, gate_factor_bp: int) -> int:
    """H-101 Q-B3: faktor ulang per profil terukur dari pilot dipakai bila lebih besar dari `[batch_gate].factor_bp`."""
    t = hc.get("factor_bp")
    v = t.get(profile) if isinstance(t, Mapping) else None
    return max(int(gate_factor_bp), 0 if v is None else int(v))


def time_params_for(hc: Mapping[str, Any], profile: str) -> dict[str, int] | None:
    pr = hc.get("projection")
    v = pr.get(profile) if isinstance(pr, Mapping) else None
    return {k: int(v[k]) for k in GLIMMER_PROJECTION_KEYS} if isinstance(v, Mapping) else None


# ---------------------------------------------------------------- jalur
def default_casefold() -> bool:
    """Sistem berkas dianggap tak peka huruf di Windows. Pemanggil/test dapat menyuntikkan nilai lain."""
    return os.name == "nt"


def _norm_parts(p: Path, casefold: bool) -> tuple[str, ...]:
    parts = Path(p).resolve(strict=False).parts  # tanpa `..`, symlink/junction diikuti bila ada
    return tuple(x.casefold() for x in parts) if casefold else tuple(parts)


def check_no_overlap(candidate: Path, main_dir: Path, *, casefold: bool | None = None) -> None:
    """Tolak bila `candidate` sama dengan, di dalam, atau membungkus `main_dir`, atas komponen jalur nyata (bukan `startswith` teks)."""
    cf = default_casefold() if casefold is None else casefold
    a, b = _norm_parts(candidate, cf), _norm_parts(main_dir, cf)
    n = min(len(a), len(b))
    if a[:n] == b[:n]:
        raise CompareError("compare_store_overlaps_main", f"comparison store {candidate} overlaps the main header store {main_dir}")


def compare_profile_root(runs_dir: Path, profile: str) -> Path:
    return Path(runs_dir) / COMPARE_DIR / validate_profile_name(profile)


def compare_store_dir(runs_dir: Path, profile: str, family: str = "uupt", *, casefold: bool | None = None) -> Path:
    """Jalur store pembanding per keluarga (sama bentuknya dengan `header_store_dir`: UU PT di akar profil, akta di `akta/`),
    sesudah penolakan tumpang tindih terhadap `runs/headers`."""
    root = compare_profile_root(runs_dir, profile)
    sub = FAMILY_STORE_SUBDIR.get(family)  # UU PT: akar profil; akta: subdir `akta` (sama dengan `header_store_dir`)
    d = root / sub if sub else root
    check_no_overlap(d, Path(runs_dir) / "headers", casefold=casefold)
    return d


# ---------------------------------------------------------------- identitas store
def build_identity(profile: str, prof: Mapping[str, Any], model_cfg: Mapping[str, Any], *, prompt_hash: str,
                   max_header_tokens: int, schema_max_length_chars: int | None) -> dict[str, Any]:
    effort = prof.get("reasoning_effort")
    if not isinstance(effort, str) or not effort:
        eff = model_cfg.get("effort")
        effort = eff.get("b") if isinstance(eff, Mapping) else None
    if not isinstance(effort, str) or not effort:
        raise CompareError("config_invalid", "no effort configured for role 'b'")
    q = prof.get("quantization")
    return {"profile": profile, "provider": prof.get("provider"), "model": prof.get("model"),
            "quantization": q if isinstance(q, str) else None, "effort": effort, "prompt_hash": prompt_hash,
            "max_header_tokens": max_header_tokens, "schema_max_length_chars": schema_max_length_chars}


def read_identity(profile_root: Path) -> dict[str, Any] | None:
    """Isi `identity.json`; None bila belum ada; `compare_identity_invalid` bila rusak/bukan objek."""
    p = Path(profile_root) / IDENTITY_FILE
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        raise CompareError("compare_identity_invalid", "identity.json cannot be read") from None
    try:
        d = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise CompareError("compare_identity_invalid", "identity.json is not valid JSON") from None
    if not isinstance(d, dict):
        raise CompareError("compare_identity_invalid", "identity.json is not an object")
    return d


def check_identity(profile_root: Path, identity: Mapping[str, Any]) -> bool:
    """Bandingkan dengan `identity.json`. True = cocok (sudah ada); False = belum ada (belum ditulis). Beda -> galat yang
    menyebut nama dan nilai field (tanpa key/URL). Tidak menulis apa pun."""
    cur = read_identity(profile_root)
    if cur is None:
        return False
    diff = [f"{f}: {cur.get(f)!r} -> {identity.get(f)!r}" for f in IDENTITY_FIELDS if cur.get(f) != identity.get(f)]
    if diff:
        raise CompareError("compare_identity_mismatch",
                           "the store identity differs from the current configuration (" + "; ".join(diff) + "); "
                           "add a new profile in config/model for a different pin instead of changing this one")
    return True


def write_identity(profile_root: Path, identity: Mapping[str, Any]) -> bool:
    """Tulis `identity.json` bila belum ada (atomik, tidak menimpa). True bila ditulis."""
    root = Path(profile_root)
    p = root / IDENTITY_FILE
    if p.exists():
        return False
    root.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(IDENTITY_FILE + ".tmp")
    tmp.write_text(json.dumps({f: identity.get(f) for f in IDENTITY_FIELDS}, sort_keys=True, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, p)
    return True


# ---------------------------------------------------------------- identitas utama (P3)
def tree_listing(root: Path) -> list[tuple[str, str]]:
    """Daftar terurut (jalur relatif POSIX, sha256 byte) seluruh berkas di bawah `root` (kosong bila tak ada)."""
    root = Path(root)
    if not root.is_dir():
        return []
    rows = []
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rows.append((p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()))
    return rows


def snapshot_main(runs_dir: Path, prompt_hash: str, *, extras: Mapping[str, Callable[[], Any]] | None = None) -> dict[str, Any]:
    """Potret identitas utama: hash isi store UU PT dan akta (A10), daftar berkas `runs/headers`, `runs/grid`, `runs/schemas`,
    ditambah `extras` (mis. `pipeline_config_hash` dan kunci amplop grid utama, dihitung pemanggil)."""
    r = Path(runs_dir)
    snap: dict[str, Any] = {
        "uupt_store_hash": DirHeaderStore(header_store_dir(r, "uupt"), prompt_hash, r).content_hash(),
        "akta_store_hash": DirHeaderStore(header_store_dir(r, "akta"), prompt_hash, r).content_hash(),
        "headers_listing": tree_listing(r / "headers"),
        "grid_listing": tree_listing(r / "grid"),
        "schemas_listing": tree_listing(r / "schemas"),
    }
    for k, fn in (extras or {}).items():
        snap[k] = fn()
    return snap


def main_identity_diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> set[str]:
    return {k for k in set(before) | set(after) if before.get(k) != after.get(k)}


def assert_main_identity(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    """Gagal keras `main_identity_changed` (himpunan item tepat di `.items`) bila ada beda."""
    d = main_identity_diff(before, after)
    if d:
        raise MainIdentityChanged(d)
