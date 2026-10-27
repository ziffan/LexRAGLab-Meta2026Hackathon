"""CLI fallback H-055 (tanpa Spark, tanpa jaringan).

  uv run python -m backend.schema_a correct BERKAS.json [--runs-dir DIR]   simpan koreksi operator sebagai versi baru
  uv run python -m backend.schema_a diff FAMILY DARI KE [--runs-dir DIR]   selisih dua versi (JSON)
  uv run python -m backend.schema_a list FAMILY [--runs-dir DIR]           versi tersimpan

Berkas koreksi: {"family", "parent_version", "operator_note", "schema"}; isi `schema` ditulis operator (H-037)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config
from backend.corpus import load_corpus

from .ops import ParentNotFound, SampleHashMismatch, SchemaInvalid, correct, diff_versions, load_correction_file, parent_samples
from .schema import FAMILIES
from .store import SchemaStore, SchemaStoreError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="backend.schema_a")
    ap.add_argument("--runs-dir", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("correct")
    c.add_argument("file")
    d = sub.add_parser("diff")
    d.add_argument("family", choices=FAMILIES)
    d.add_argument("v_from", type=int)
    d.add_argument("v_to", type=int)
    l = sub.add_parser("list")
    l.add_argument("family", choices=FAMILIES)
    a = ap.parse_args(argv)
    store = SchemaStore(Path(a.runs_dir) if a.runs_dir else config.REPO_ROOT / "runs")
    try:
        if a.cmd == "correct":
            data = load_correction_file(a.file)
            if data["family"] not in FAMILIES:
                raise SchemaInvalid([f"family must be one of {list(FAMILIES)}"])
            parent = store.get(data["family"], data["parent_version"])
            if parent is None:
                raise ParentNotFound(f"no schema version {data['parent_version']} for family {data['family']!r}")
            samples = parent_samples(parent, load_corpus)
            rec = correct(store, family=data["family"], parent_version=data["parent_version"], schema=data["schema"],
                          operator_note=data["operator_note"], samples=samples)
            print(f"saved {rec['family']} v{rec['schema_version']} (parent v{rec['parent_version']}, sample_checked={rec['sample_checked']})")
        elif a.cmd == "diff":
            print(json.dumps(diff_versions(store, a.family, a.v_from, a.v_to), ensure_ascii=False, indent=1))
        else:
            for r in store.list(a.family):
                print(f"v{r['schema_version']} {r['source']} parent={r['parent_version']} {r['created_at']}")
    except SchemaInvalid as exc:
        print("schema_invalid: " + "; ".join(exc.errors[:10]), file=sys.stderr)
        return 2
    except (ParentNotFound, SampleHashMismatch, SchemaStoreError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
