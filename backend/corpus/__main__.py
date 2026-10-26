"""CLI: `uv run python -m backend.corpus` -> tabel per bagian, hash, usulan status; simpan ke runs/corpus/."""

from __future__ import annotations

import json
import sys

from backend import config

from .errors import CorpusError
from .loader import SEP, load_corpus
from .status_proposal import propose_status_rows


def build_table(doc, proposal) -> str:
    n_ann: dict[str, int] = {}
    for a in doc.annotations:
        n_ann[a["type"]] = n_ann.get(a["type"], 0) + 1
    rows = []
    for name in ("pembukaan", "penjelasan_umum", "batang_tubuh", "penjelasan_pasal", "pengesahan"):
        rs = [s for s in doc.sections if s["section"] == name]
        rows.append((name, len(rs), sum(s["end"] - s["start"] for s in rs)))
    w = max(len(r[0]) for r in rows)
    lines = [f"{'section'.ljust(w)}  {'ranges':>6}  {'chars':>8}"]
    lines += [f"{n.ljust(w)}  {c:>6}  {ch:>8}" for n, c, ch in rows]
    lines.append(f"{'TOTAL'.ljust(w)}  {sum(r[1] for r in rows):>6}  {sum(r[2] for r in rows):>8}")
    lines += [
        "",
        f"doc_id               {doc.doc_id}",
        f"file sha256          {doc.sha256}",
        f"clean_sha256         {doc.clean_sha256}",
        f"loader_rules_version {doc.loader_rules_version}",
        f"char_count (clean)   {doc.char_count}",
        f"annotations parsed   {len(doc.annotations)} ({', '.join(f'{k}={v}' for k, v in sorted(n_ann.items()))})",
        f"status proposals     {len(proposal['entries'])} (approved_by_operator=false; default_rule effective_from {proposal['default_rule']['effective_from']})",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # G-27
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        doc = load_corpus()
    except CorpusError as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    proposal = propose_status_rows(doc)
    table = build_table(doc, proposal)
    print(table, end="")
    out_dir = config.REPO_ROOT / "runs" / "corpus"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{doc.doc_id}.{doc.clean_sha256[:12]}"
    payload = {"corpus_doc": doc.to_dict(), "status_proposal": proposal, "table": table.splitlines()}
    with open(out_dir / f"{stem}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(out_dir / f"{stem}.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(table)
    print(f"saved runs/corpus/{stem}.json and .txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
