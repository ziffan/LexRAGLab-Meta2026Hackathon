"""CLI `python -m backend.corpus`: tabel per bagian dan berkas keluaran di runs/corpus/ (G2)."""

import json

from backend import config
from backend.corpus import __main__ as cli
from backend.corpus import load_corpus, propose_status_rows


def test_cli_prints_table_and_saves_files(capsys):
    assert cli.main() == 0
    out = capsys.readouterr().out
    doc = load_corpus()
    prop = propose_status_rows(doc)
    for name in ("pembukaan", "penjelasan_umum", "batang_tubuh", "penjelasan_pasal", "pengesahan"):
        assert name in out
    assert doc.sha256 in out and doc.clean_sha256 in out and f"loader_rules_version {doc.loader_rules_version}" in out
    assert f"status proposals     {len(prop['entries'])}" in out
    base = config.REPO_ROOT / "runs" / "corpus" / f"{doc.doc_id}.{doc.clean_sha256[:12]}"
    jpath, tpath = base.parent / (base.name + ".json"), base.parent / (base.name + ".txt")
    payload = json.loads(jpath.read_text(encoding="utf-8"))
    assert payload["corpus_doc"]["clean_sha256"] == doc.clean_sha256
    assert payload["corpus_doc"]["tokens_local"] is None
    assert "text" not in payload["corpus_doc"]
    assert payload["status_proposal"]["approved_by_operator"] is False
    assert tpath.read_text(encoding="utf-8") == "\n".join(payload["table"]) + "\n"
    assert b"\r" not in jpath.read_bytes()
