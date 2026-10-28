"""H-101 CLI `backend.header_b.compare`: proyeksi tanpa tulis, laporan run di luar direktori yang di-hash. Tanpa Model API."""

import json

import backend.header_b.compare as c

from .h101_helpers import Tok, hc_b, make_prepared, rig_for, words
from .test_h101_compare_store import cli_args, cli_run


def test_cli_project_only_prints_batches_and_glimmer_time_and_writes_nothing(tmp_path):
    lines: list[str] = []
    rig = rig_for(tmp_path, "glimmer_local")

    def run(argv):
        return c.main(argv, env=rig.env, model_config=rig.model, budget_config=rig.budget, header_config=hc_b(), runs_dir=rig.runs,
                      transport=rig.tr.transport, out=lines.append, tokenizer=Tok(), probe=lambda u, m: (True, "ok"),
                      prepare_fn=lambda ids, sources, **k: {"uupt-x": {"pasal": make_prepared(3)}})

    assert run(cli_args("glimmer_local", "--project-only")) == 0
    text = "\n".join(lines)
    assert rig.tr.calls == 0 and not (rig.runs / "headers_compare").exists() and not (rig.runs / "locks").exists()
    assert "to_call=3" in text and "no_reuse=" in text and "reuse unconfirmed" in text and "max_attempts=3" in text
    rb = rig_for(tmp_path / "b", "baseten_open")
    assert cli_run(tmp_path, rb, cli_args("baseten_open", "--project-only")) == 0 and rb.tr.calls == 0
    assert not (rb.runs / "headers_compare").exists()


def test_cli_run_writes_report_outside_hashed_dirs_with_coverage(tmp_path):
    rig = rig_for(tmp_path, "baseten_open", {"CH-U2": [words(41)]})
    assert cli_run(tmp_path, rig, cli_args("baseten_open", "--max-units", "3")) == 1  # CH-U2 gagal jujur setelah 8 ronde
    root = rig.runs / "headers_compare" / "baseten_open"
    (rep,) = list((root / "runs").glob("*.json"))
    r = json.loads(rep.read_text(encoding="utf-8"))
    assert r["failed"] == {"uupt-x/pasal": ["CH-U2"]} and r["attempts"] == {"uupt-x/pasal": 8} and r["stopped"] is None
    assert r["cache_guard"] == "active" and r["coverage"] == {"uupt-x/pasal": {"units": 3, "stored": 2}}
    assert r["main_identity"] == "unchanged" and len(r["batches"]) == 8 and r["batches"][0]["units"] == 3 and r["batches"][1]["units"] == 1
    assert json.loads((root / "identity.json").read_text(encoding="utf-8"))["profile"] == "baseten_open"


def test_cli_rejects_bad_numbers_and_unknown_profile(tmp_path):
    rig = rig_for(tmp_path, "baseten_open")
    assert cli_run(tmp_path, rig, cli_args("baseten_open", "--max-units", "0")) == 2
    assert cli_run(tmp_path, rig, cli_args("meta")) == 2 and rig.tr.calls == 0
    assert cli_run(tmp_path, rig, cli_args("openrouter_dev")) == 2 and rig.tr.calls == 0
