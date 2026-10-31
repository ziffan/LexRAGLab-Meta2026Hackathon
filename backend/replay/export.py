"""Ekspor statis mode putar ulang (H-051): snapshot JSON R1/R3/R4/R5/R6 + W6 tersimpan + antrean Review.

Pakai: `uv run python -m backend.replay.export --out dist-static` -> menulis `dist-static/data/**` (isi `data/` lama diganti).
Frontend statis dibangun terpisah (`npm run build:static` -> `dist-static/`), lalu `--check dist-static` memeriksa ulang isinya.

Gagal-keras (I-69, G-49): setiap respons non-200 dicatat sebagai `Miss`. Ringkasan selalu dicetak (satu baris per jenis berkas yang
gagal, `failed requests: N`, dan `skipped by design: ...` untuk kelas sah). Ada kegagalan di luar kelas sah -> tidak ada berkas
ditulis dan exit 3 (1 = bocor, 2 = argparse). Kelas sah: POST W6 409 `replay_no_stored_run` (jawaban tidak tersimpan) dan GET
docs?setting_id 422 "Setting is not available yet". `--allow-missing` (dev/test): tulis apa adanya, cetak `WARNING`, exit 0.
`--check` tetap hanya pemindai bocor (tidak bisa mendeteksi berkas hilang).

Semua berkas dihasilkan oleh app replay yang sama (`create_app(replay=True)`) lewat klien in-process, jadi bentuknya
identik dengan respons live. Tanpa jaringan, tanpa panggilan model (W6 `live` selalu false). Isi diperiksa
(`backend/replay/scan.py`) SEBELUM ditulis; bocor -> `SnapshotLeak`, tidak ada berkas yang ditulis. Tidak membaca `.env`.

Tata letak (jalur relatif terhadap `data/`; dipetakan frontend di `frontend/src/lib/staticData.ts`):
  health.json  runs.json  families.json  manifest.json
  families.json                                      R2 terbatas pada UU PT dan keluarga yang punya amplop grid tersimpan (pemilih Family, U0)
  snapshot/<family>/default.json  snapshot/<family>/<budget>.json
  docs/<family>/<doc_id>/_text.json            DocResponse tanpa setting (teks penuh, chunks null)
  docs/<family>/<doc_id>/<setting_id[:16]>.json     {doc_id, chunks, headers} (teks diambil dari _text.json oleh klien)
  docs/<family>/<doc_id>/schema-v<n>.json           {doc_id, chunks, headers} potongan menurut skema A versi n (bila ada)
  retrieval/<family>/<setting_id[:16]>/<item_id>.json
  answers/<family>/<item_id>/<best[:16]>/<baseline[:16]>/<model_profile>.json
  proposals/<family>.json
  profiles/<family>/<setting_id[:16]>.json         profil tersimpan setting terpilih/transfer (UX-09), byte-identik dengan `profiles/`
Di root keluaran (disalin byte-identik dari root repo, H-097; lisensi wajib menyertai font OFL yang terbundel):
  LICENSE  NOTICE  licenses/*.txt
Penyalinan hanya menimpa berkas-berkas itu; berkas lain di root keluaran (bundel frontend) tidak disentuh.
Pemindai memeriksanya dengan pengecualian sempit: jenis `host_url` dilewati (teks lisensi memuat URL resmi apache.org / scripts.sil.org).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.api.service import SETTING_UNAVAILABLE_PREFIX
from backend.replay.scan import Finding, SnapshotLeak, env_secrets, scan_dir, scan_files

SAFE = re.compile(r"^[A-Za-z0-9._\-]+$")
EXPORT_FAMILIES = ("uupt", "akta")
REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSE_SKIP_KINDS = ("host_url",)  # teks lisensi sah memuat URL resmi; key, path lokal, dan base URL env tetap diperiksa


class ExportError(Exception):
    pass


@dataclass(frozen=True)
class Miss:
    """Satu respons non-200 selama ekspor. `message` hanya untuk klasifikasi; tidak pernah dicetak."""
    kind: str
    url: str
    status: int
    code: str
    message: str = ""


class ExportIncomplete(ExportError):
    def __init__(self, failed: list[Miss], skipped: list[Miss]):
        self.failed, self.skipped = failed, skipped
        super().__init__(f"{len(failed)} failed request(s)")


def _kind_of(url: str, params: Mapping[str, Any] | None) -> str:
    p = params or {}
    if url == "/api/health":
        return "health.json"
    if url == "/api/runs":
        return "runs.json"
    if url == "/api/families":
        return "families.json"
    if url.endswith("/retrieval"):
        return "retrieval/"
    if "/docs/" in url:
        return "docs/ (setting chunks)" if "setting_id" in p else "docs/ (schema)" if "schema_version" in p else "docs/ (text)"
    if url.endswith("/snapshot"):
        return "snapshot/"
    if url.endswith("/profiles/export"):
        return "profiles/"
    if url.endswith("/proposals"):
        return "proposals/"
    return "other"


def _short_url(url: str, params: Mapping[str, Any] | None) -> str:
    if not params:
        return url
    return url + "?" + "&".join(f"{k}={str(v)[:16]}" for k, v in params.items())


def _record(misses: list[Miss] | None, kind: str, url: str, resp: Any) -> None:
    if misses is None:
        return
    code, msg = "", ""
    try:
        err = (resp.json() or {}).get("error") or {}
        code, msg = str(err.get("code", "")), str(err.get("message", ""))
    except Exception:  # noqa: BLE001 - badan respons bukan JSON galat: kode kosong
        pass
    misses.append(Miss(kind, url, resp.status_code, code, msg))


def is_by_design(m: Miss) -> str | None:
    """Nama kelas sah (bukan kegagalan) atau None. S1: W6 409 replay_no_stored_run. S2: docs?setting_id 422 setting belum tersedia."""
    if m.kind == "answers/" and m.status == 409 and m.code == "replay_no_stored_run":
        return "answers/ 409 replay_no_stored_run"
    if (m.kind == "docs/ (setting chunks)" and m.status == 422 and m.code == "validation_failed"
            and m.message.startswith(SETTING_UNAVAILABLE_PREFIX)):
        return "docs/ (setting chunks) 422 setting_unavailable"
    return None


def split_misses(misses: Iterable[Miss]) -> tuple[list[Miss], list[Miss]]:
    failed: list[Miss] = []
    skipped: list[Miss] = []
    for m in misses:
        (skipped if is_by_design(m) else failed).append(m)
    return failed, skipped


def format_summary(failed: list[Miss], skipped: list[Miss], *, warning: bool = False) -> list[str]:
    """Baris ringkasan. Hanya kind, status, dan url ringkas: tanpa pesan galat mentah atau jalur lokal."""
    pre = "WARNING " if warning else ""
    lines: list[str] = []
    for kind in sorted({m.kind for m in failed}):
        ms = [m for m in failed if m.kind == kind]
        st = ", ".join(f"{s} x{n}" for s, n in sorted(Counter(m.status for m in ms).items()))
        lines.append(f"{pre}{kind}: {len(ms)} ({st})")
        lines += [f"  e.g. {m.url}" for m in ms[:3]]
    lines.append(f"{pre}failed requests: {len(failed)}")
    if skipped:
        cls = ", ".join(f"{name} x{n}" for name, n in sorted(Counter(is_by_design(m) for m in skipped).items()))
        lines.append(f"skipped by design: {cls}")
    return lines


def _safe(part: str) -> str:
    if not isinstance(part, str) or not SAFE.match(part) or part in (".", ".."):
        raise ExportError(f"unsafe path segment {str(part)[:24]!r}")
    return part


SID_LEN = 16  # setting_id 64 hex dipendekkan di jalur berkas (batas MAX_PATH Windows); frontend memakai awalan yang sama


def sid(setting_id: str) -> str:
    return _safe(setting_id)[:SID_LEN]


def dump(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def baseline_id(app: Any, family: str, best_id: str) -> str | None:
    """Pembanding W6 yang sah menurut backend (H-036, `config/grid [baseline]`), bukan tebakan frontend."""
    from backend.pipeline.grid_run import baseline_for

    svc = app.state.service
    all_settings = svc.grid_settings(family)
    best = next((x for x in all_settings if x.setting_id == best_id), None)
    base = baseline_for(all_settings, best, svc.cfg("grid")["baseline"]) if best is not None else None
    return base.setting_id if base is not None else None


def stored_profile(get: Any, profiles_dir: Path, fam: str, snapshot: Mapping[str, Any]) -> tuple[str, bytes] | None:
    """UX-09: (jalur relatif data/, byte) profil tersimpan untuk setting terpilih (UU PT) atau setting transfer (akta), atau None.
    Byte-identik dengan `profiles/<fam>/<setting_id>.json`; hanya bila sama dengan W7 replay sekarang (`get`) selain `created_at`."""
    g = snapshot.get("grid") or {}
    prof_id = (g.get("selected") or {}).get("setting_id") or (g.get("transfer") or {}).get("setting_id")
    if not isinstance(prof_id, str):
        return None
    path = Path(profiles_dir) / _safe(fam) / f"{_safe(prof_id)}.json"
    if not path.is_file():
        return None
    now = get(f"/api/families/{fam}/profiles/export", setting_id=prof_id)
    blob = path.read_bytes()
    try:
        stored = json.loads(blob.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(now, dict) or not isinstance(stored, dict):
        return None
    strip = lambda d: {k: v for k, v in d.items() if k != "created_at"}  # noqa: E731
    return (f"profiles/{fam}/{sid(prof_id)}.json", blob) if strip(stored) == strip(now) else None


def build_files(app: Any, *, families: Iterable[str] = EXPORT_FAMILIES, retrieval: bool = True, answers: bool = True,
                now: datetime | None = None, misses: list[Miss] | None = None) -> dict[str, bytes]:
    """Kumpulkan semua berkas (jalur relatif `data/` -> byte) dari app replay. Tidak menulis ke disk.
    `misses` (opsional): kolektor respons non-200; perilaku build_files tidak berubah."""
    from starlette.testclient import TestClient

    if not getattr(app.state, "replay", False):
        raise ExportError("export requires an app created with replay=True")
    client = TestClient(app, raise_server_exceptions=False)
    files: dict[str, bytes] = {}

    def get(url: str, **params: Any) -> Any | None:
        r = client.get(url, params=params or None)
        if r.status_code != 200:
            _record(misses, _kind_of(url, params), _short_url(url, params), r)
            return None
        return r.json()

    health = get("/api/health")
    if health is None:
        raise ExportError("health unavailable")
    files["runs.json"] = dump(get("/api/runs", limit=500) or [])
    grid_cfg = app.state.service.cfg("grid")["budget"]
    budgets = [grid_cfg["default_tokens"], *grid_cfg.get("comparison_tokens", [])]
    profiles = [p["model_profile"] for p in health.get("model_profiles", [])]
    stored_profiles: set[str] = set()
    with_grid: list[str] = []

    for fam in families:
        _safe(fam)
        default = get(f"/api/families/{fam}/snapshot")
        if default is None:
            raise ExportError(f"snapshot unavailable for {fam}")
        files[f"snapshot/{fam}/default.json"] = dump(default)
        if default.get("grid") is not None:
            with_grid.append(fam)
        by_budget = {default["budget_tokens"]: default}
        for b in budgets:
            if b not in by_budget:
                snap = get(f"/api/families/{fam}/snapshot", budget_tokens=b)
                if snap is not None:
                    by_budget[b] = snap
        for b, snap in by_budget.items():
            files[f"snapshot/{fam}/{int(b)}.json"] = dump(snap)

        # Keluarga tanpa amplop grid tersimpan (akta sebelum run, H-091): hanya teks dokumen; potongan per setting menunggu amplop.
        settings = default["settings"] if default.get("grid") is not None or fam == "uupt" else []
        usable_ids: set[str] = set()
        for doc in default["corpus"]:
            doc_id = _safe(doc["doc_id"])
            text_doc = get(f"/api/families/{fam}/docs/{doc_id}")
            if text_doc is None:
                continue
            files[f"docs/{fam}/{doc_id}/_text.json"] = dump(text_doc)
            for s in settings:
                d = get(f"/api/families/{fam}/docs/{doc_id}", setting_id=s["setting_id"])
                if d is not None:  # 422 = setting belum tersedia: tidak diekspor
                    usable_ids.add(s["setting_id"])
                    files[f"docs/{fam}/{doc_id}/{sid(s['setting_id'])}.json"] = dump({k: d[k] for k in ("doc_id", "chunks", "headers")})
        for sch in default.get("schemas") or []:
            v = int(sch["schema_version"])
            for doc in default["corpus"]:
                d = get(f"/api/families/{fam}/docs/{_safe(doc['doc_id'])}", schema_version=v)
                if d is not None:  # 404/422 = skema tak berlaku untuk dokumen ini: tidak diekspor
                    files[f"docs/{fam}/{doc['doc_id']}/schema-v{v}.json"] = dump({k: d[k] for k in ("doc_id", "chunks", "headers")})
        usable = [s for s in settings if s["setting_id"] in usable_ids]
        if len({sid(s["setting_id"]) for s in usable}) != len(usable):
            raise ExportError("setting_id prefix collision")

        if retrieval and fam == "uupt":  # R5 hanya UU PT
            for s in usable:
                for it in default["items"]:
                    r = get(f"/api/families/{fam}/retrieval", setting_id=s["setting_id"], item_id=it["id"])
                    if r is not None:
                        files[f"retrieval/{fam}/{sid(s['setting_id'])}/{_safe(it['id'])}.json"] = dump(r)

        if answers and fam == "uupt":  # W6 hanya UU PT (API.md section 5)
            for it in default["items"]:
                for best in usable:
                    base_id = baseline_id(app, fam, best["setting_id"])
                    if base_id is None or base_id == best["setting_id"]:
                        continue
                    base = {"setting_id": base_id}
                    for prof in profiles:
                        r = client.post(f"/api/families/{fam}/answers", json={
                            "item_id": it["id"], "best_setting_id": best["setting_id"], "baseline_setting_id": base["setting_id"],
                            "model_profile": prof, "live": False})
                        if r.status_code == 200:
                            stored_profiles.add(prof)
                            key = f"{_safe(it['id'])}/{sid(best['setting_id'])}/{sid(base['setting_id'])}/{_safe(prof)}"
                            files[f"answers/{fam}/{key}.json"] = dump(r.json())
                        else:
                            _record(misses, "answers/", _short_url(f"/api/families/{fam}/answers", {
                                "item_id": it["id"], "best": best["setting_id"], "baseline": base["setting_id"], "model_profile": prof}), r)

        # UX-09 (putusan operator 12, Q-UX-6): profil tersimpan setting terpilih (UU PT) / setting transfer (akta), disalin
        # byte-identik dari `profiles/<fam>/<setting_id>.json` (keluaran W7), hanya bila sama dengan W7 replay sekarang selain
        # `created_at` (profil basi tidak diekspor). Frontend statis: pratinjau baca-saja + Download JSON; tanpa endpoint tulis (H-051).
        runs_dir = getattr(app.state.service, "runs_dir", None)  # layanan palsu di test boleh tanpa runs_dir
        prof = stored_profile(get, Path(runs_dir).parent / "profiles", fam, default) if runs_dir is not None else None
        if prof is not None:
            files[prof[0]] = prof[1]

        q = get(f"/api/families/{fam}/proposals")
        if q is not None:
            files[f"proposals/{fam}.json"] = dump(q)

    # Pilihan model di versi statis: hanya profil yang punya jawaban tersimpan dicantumkan (H-053); profil dev tidak diekspos.
    static_health = {**health, "replay": True, "static": True,
                     "model_profiles": [{**p, "available": True} for p in health.get("model_profiles", []) if p["model_profile"] in stored_profiles]}
    files["health.json"] = dump(static_health)
    r2 = get("/api/families") or []
    files["families.json"] = dump([f for f in r2 if f.get("family") in with_grid or f.get("family") == "uupt"])
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    files["manifest.json"] = dump({
        "static": True, "generated_at": ts, "config_hash": health.get("config_hash"),
        "files": {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())}})
    return files


def collect_license_files(root: Path = REPO_ROOT) -> dict[str, bytes]:
    """`LICENSE`, `NOTICE`, `licenses/*.txt` dari `root` (jalur relatif -> byte mentah). Yang tidak ada dilewati."""
    root = Path(root)
    out: dict[str, bytes] = {}
    for name in ("LICENSE", "NOTICE"):
        if (root / name).is_file():
            out[name] = (root / name).read_bytes()
    lic = root / "licenses"
    if lic.is_dir():
        for p in sorted(lic.glob("*.txt")):
            out[f"licenses/{p.name}"] = p.read_bytes()
    return out


def write_license_files(out_dir: Path, files: Mapping[str, bytes]) -> None:
    for rel, blob in files.items():
        p = Path(out_dir) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            f.write(blob)


def scan_license_files(out_dir: Path, *, secrets: Iterable[str] = (), base_urls: Iterable[str] = ()) -> list[Finding]:
    return scan_files(collect_license_files(out_dir), secrets=secrets, base_urls=base_urls, skip_kinds=LICENSE_SKIP_KINDS)


def write_files(out_dir: Path, files: Mapping[str, bytes]) -> Path:
    data = Path(out_dir) / "data"
    if data.exists():
        shutil.rmtree(data)
    for rel, blob in files.items():
        p = data / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            f.write(blob)
    return data


def export_static(out_dir: Path, app: Any, *, secrets: Iterable[str] = (), base_urls: Iterable[str] = (), retrieval: bool = True,
                  answers: bool = True, now: datetime | None = None, license_root: Path = REPO_ROOT,
                  allow_missing: bool = False) -> dict[str, Any]:
    """Bangun, periksa, lalu tulis (data + salinan lisensi). Bocor -> `SnapshotLeak`; respons non-200 di luar kelas sah ->
    `ExportIncomplete` (kecuali `allow_missing`). Keduanya menolak SEBELUM menulis: tidak ada berkas ditulis."""
    misses: list[Miss] = []
    files = build_files(app, retrieval=retrieval, answers=answers, now=now, misses=misses)
    failed, skipped = split_misses(misses)
    if failed and not allow_missing:
        raise ExportIncomplete(failed, skipped)
    lic = collect_license_files(license_root)
    findings = scan_files(files, secrets=secrets, base_urls=base_urls)
    findings += scan_files(lic, secrets=secrets, base_urls=base_urls, skip_kinds=LICENSE_SKIP_KINDS)
    if findings:
        raise SnapshotLeak(findings)
    data = write_files(Path(out_dir), files)
    write_license_files(Path(out_dir), lic)
    return {"data_dir": str(data), "n_files": len(files), "bytes": sum(len(v) for v in files.values()), "license_files": sorted(lic),
            "failed": len(failed), "skipped": dict(Counter(is_by_design(m) for m in skipped)),
            "summary": format_summary(failed, skipped, warning=bool(failed))}


def source_date(environ: Mapping[str, str]) -> datetime | None:
    """`SOURCE_DATE_EPOCH` (detik UTC) membuat `generated_at` tetap, jadi dua ekspor identik byte."""
    v = (environ.get("SOURCE_DATE_EPOCH") or "").strip()
    return datetime.fromtimestamp(int(v), timezone.utc) if v.isdigit() else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export the replay mode as a static snapshot (H-051). No model calls.")
    ap.add_argument("--out", type=Path, help="output directory (e.g. dist-static); data goes to <out>/data")
    ap.add_argument("--no-retrieval", action="store_true", help="skip per-item retrieval files (R5)")
    ap.add_argument("--no-answers", action="store_true", help="skip stored W6 answers")
    ap.add_argument("--allow-missing", action="store_true", help="write the export even if requests failed (dev/test); prints WARNING, exit 0")
    ap.add_argument("--check", type=Path, help="only scan an existing <dir>/data for keys, local paths, hosts")
    args = ap.parse_args(argv)
    keys, urls = env_secrets(os.environ)  # lingkungan proses; .env tidak dibaca di sini
    now = source_date(os.environ)
    if args.check:
        findings: list[Finding] = scan_dir(args.check / "data", secrets=keys, base_urls=urls)
        findings += scan_license_files(args.check, secrets=keys, base_urls=urls)
        print(f"snapshot check: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1 if findings else 0
    if not args.out:
        ap.error("--out is required")
    from backend.api.app import create_app

    app = create_app(replay=True)
    try:
        info = export_static(args.out, app, secrets=keys, base_urls=urls, retrieval=not args.no_retrieval, answers=not args.no_answers, now=now,
                           allow_missing=args.allow_missing)
    except ExportIncomplete as exc:
        print("\n".join(format_summary(exc.failed, exc.skipped)))
        print("export refused, nothing written: failed requests (use --allow-missing for dev/test)", file=sys.stderr)
        return 3
    except SnapshotLeak as exc:
        print(f"export refused, nothing written: {exc}", file=sys.stderr)
        return 1
    print("\n".join(info.get("summary") or [f"failed requests: {info.get('failed', 0)}"]))
    print(f"exported {info['n_files']} files ({info['bytes']} bytes) to {info['data_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
