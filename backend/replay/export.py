"""Ekspor statis mode putar ulang (H-051): snapshot JSON R1/R3/R4/R5/R6 + W6 tersimpan + antrean Review.

Pakai: `uv run python -m backend.replay.export --out dist-static` -> menulis `dist-static/data/**` (isi `data/` lama diganti).
Frontend statis dibangun terpisah (`npm run build:static` -> `dist-static/`), lalu `--check dist-static` memeriksa ulang isinya.

Semua berkas dihasilkan oleh app replay yang sama (`create_app(replay=True)`) lewat klien in-process, jadi bentuknya
identik dengan respons live. Tanpa jaringan, tanpa panggilan model (W6 `live` selalu false). Isi diperiksa
(`backend/replay/scan.py`) SEBELUM ditulis; bocor -> `SnapshotLeak`, tidak ada berkas yang ditulis. Tidak membaca `.env`.

Tata letak (jalur relatif terhadap `data/`; dipetakan frontend di `frontend/src/lib/staticData.ts`):
  health.json  runs.json  manifest.json
  snapshot/<family>/default.json  snapshot/<family>/<budget>.json
  docs/<family>/<doc_id>/_text.json            DocResponse tanpa setting (teks penuh, chunks null)
  docs/<family>/<doc_id>/<setting_id[:16]>.json     {doc_id, chunks, headers} (teks diambil dari _text.json oleh klien)
  docs/<family>/<doc_id>/schema-v<n>.json           {doc_id, chunks, headers} potongan menurut skema A versi n (bila ada)
  retrieval/<family>/<setting_id[:16]>/<item_id>.json
  answers/<family>/<item_id>/<best[:16]>/<baseline[:16]>/<model_profile>.json
  proposals/<family>.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.replay.scan import Finding, SnapshotLeak, env_secrets, scan_dir, scan_files

SAFE = re.compile(r"^[A-Za-z0-9._\-]+$")
EXPORT_FAMILIES = ("uupt", "akta")


class ExportError(Exception):
    pass


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


def build_files(app: Any, *, families: Iterable[str] = EXPORT_FAMILIES, retrieval: bool = True, answers: bool = True,
                now: datetime | None = None) -> dict[str, bytes]:
    """Kumpulkan semua berkas (jalur relatif `data/` -> byte) dari app replay. Tidak menulis ke disk."""
    from starlette.testclient import TestClient

    if not getattr(app.state, "replay", False):
        raise ExportError("export requires an app created with replay=True")
    client = TestClient(app, raise_server_exceptions=False)
    files: dict[str, bytes] = {}

    def get(url: str, **params: Any) -> Any | None:
        r = client.get(url, params=params or None)
        return r.json() if r.status_code == 200 else None

    health = get("/api/health")
    if health is None:
        raise ExportError("health unavailable")
    files["runs.json"] = dump(get("/api/runs", limit=500) or [])
    grid_cfg = app.state.service.cfg("grid")["budget"]
    budgets = [grid_cfg["default_tokens"], *grid_cfg.get("comparison_tokens", [])]
    profiles = [p["model_profile"] for p in health.get("model_profiles", [])]
    stored_profiles: set[str] = set()

    for fam in families:
        _safe(fam)
        default = get(f"/api/families/{fam}/snapshot")
        if default is None:
            raise ExportError(f"snapshot unavailable for {fam}")
        files[f"snapshot/{fam}/default.json"] = dump(default)
        by_budget = {default["budget_tokens"]: default}
        for b in budgets:
            if b not in by_budget:
                snap = get(f"/api/families/{fam}/snapshot", budget_tokens=b)
                if snap is not None:
                    by_budget[b] = snap
        for b, snap in by_budget.items():
            files[f"snapshot/{fam}/{int(b)}.json"] = dump(snap)

        settings = default["settings"]
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

        if retrieval:
            for s in usable:
                for it in default["items"]:
                    r = get(f"/api/families/{fam}/retrieval", setting_id=s["setting_id"], item_id=it["id"])
                    if r is not None:
                        files[f"retrieval/{fam}/{sid(s['setting_id'])}/{_safe(it['id'])}.json"] = dump(r)

        if answers:
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

        q = get(f"/api/families/{fam}/proposals")
        if q is not None:
            files[f"proposals/{fam}.json"] = dump(q)

    # Pilihan model di versi statis: hanya profil yang punya jawaban tersimpan dicantumkan (H-053); profil dev tidak diekspos.
    static_health = {**health, "replay": True, "static": True,
                     "model_profiles": [{**p, "available": True} for p in health.get("model_profiles", []) if p["model_profile"] in stored_profiles]}
    files["health.json"] = dump(static_health)
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    files["manifest.json"] = dump({
        "static": True, "generated_at": ts, "config_hash": health.get("config_hash"),
        "files": {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())}})
    return files


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
                  answers: bool = True, now: datetime | None = None) -> dict[str, Any]:
    """Bangun, periksa, lalu tulis. Bocor -> `SnapshotLeak` dan tidak ada yang ditulis."""
    files = build_files(app, retrieval=retrieval, answers=answers, now=now)
    findings = scan_files(files, secrets=secrets, base_urls=base_urls)
    if findings:
        raise SnapshotLeak(findings)
    data = write_files(Path(out_dir), files)
    return {"data_dir": str(data), "n_files": len(files), "bytes": sum(len(v) for v in files.values())}


def source_date(environ: Mapping[str, str]) -> datetime | None:
    """`SOURCE_DATE_EPOCH` (detik UTC) membuat `generated_at` tetap, jadi dua ekspor identik byte."""
    v = (environ.get("SOURCE_DATE_EPOCH") or "").strip()
    return datetime.fromtimestamp(int(v), timezone.utc) if v.isdigit() else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export the replay mode as a static snapshot (H-051). No model calls.")
    ap.add_argument("--out", type=Path, help="output directory (e.g. dist-static); data goes to <out>/data")
    ap.add_argument("--no-retrieval", action="store_true", help="skip per-item retrieval files (R5)")
    ap.add_argument("--no-answers", action="store_true", help="skip stored W6 answers")
    ap.add_argument("--check", type=Path, help="only scan an existing <dir>/data for keys, local paths, hosts")
    args = ap.parse_args(argv)
    keys, urls = env_secrets(os.environ)  # lingkungan proses; .env tidak dibaca di sini
    now = source_date(os.environ)
    if args.check:
        findings: list[Finding] = scan_dir(args.check / "data", secrets=keys, base_urls=urls)
        print(f"snapshot check: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1 if findings else 0
    if not args.out:
        ap.error("--out is required")
    from backend.api.app import create_app

    app = create_app(replay=True)
    try:
        info = export_static(args.out, app, secrets=keys, base_urls=urls, retrieval=not args.no_retrieval, answers=not args.no_answers, now=now)
    except SnapshotLeak as exc:
        print(f"export refused, nothing written: {exc}", file=sys.stderr)
        return 1
    print(f"exported {info['n_files']} files ({info['bytes']} bytes) to {info['data_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
