"""H-108 butir 2: flag --skip-cache-guard satu run sapuan. Tanpa jaringan (transport palsu)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.header_b.compare_store import compare_store_dir

from .h101_helpers import make_prepared
from .sweep_b_helpers import args, go_sweep, run_main, sweep_rig
from .test_h101_compare_run import usage_seq

LOW = usage_seq(lambda k: 38_000 if k < 9 else 37_999)


def _report(out: list[str]) -> dict:
    return json.loads(Path(re.search(r"report=(.+)$", out[-1]).group(1)).read_text(encoding="utf-8"))


def test_h108_without_flag_guard_unchanged(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_baseten_high", usage=LOW)
    s = go_sweep(rig, sw, make_prepared(12), compare_store_dir(rig.runs, "sweep_baseten_high"), profile="sweep_baseten_high", gate=None)
    assert s["stopped"] == "cache_ratio_low" and s["cache_guard"] == "active"


def test_h108_flag_bypasses_guard_in_run_compare(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_baseten_high", usage=LOW)
    s = go_sweep(rig, sw, make_prepared(12), compare_store_dir(rig.runs, "sweep_baseten_high"), profile="sweep_baseten_high", gate=None,
                 skip_cache_guard=True)
    assert s["stopped"] is None and s["stored"] == 12 and s["cache_guard"] == "skipped_by_flag"


def test_h108_cli_flag_records_override_in_report(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_baseten_high", usage=LOW)
    out: list[str] = []
    rc = run_main(rig, args("sweep_baseten_high", "--confirm-go", "--skip-cache-guard"), sweep=sw, out=out, prepared=make_prepared(12))
    assert rc == 0
    rep = _report(out)
    assert rep["cache_guard"] == "skipped_by_flag"
    assert rep["cache_guard_override"] == {"flag": "--skip-cache-guard", "reason": "H-108"}


def test_h108_cli_without_flag_no_override_key(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_baseten_high", usage=usage_seq(lambda k: 38_000))
    out: list[str] = []
    assert run_main(rig, args("sweep_baseten_high", "--confirm-go"), sweep=sw, out=out, prepared=make_prepared(12)) == 0
    rep = _report(out)
    assert rep["cache_guard"] == "active" and "cache_guard_override" not in rep


def test_h108_flag_rejected_with_project_only(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_baseten_high")
    assert run_main(rig, args("sweep_baseten_high", "--skip-cache-guard", "--project-only"), sweep=sw) == 2
    assert rig.tr.calls == 0


def test_h108_flag_rejected_for_non_sweep_profile(tmp_path):
    rig, _ = sweep_rig(tmp_path, "sweep_baseten_high")
    assert run_main(rig, args("baseten_open", "--skip-cache-guard"), sweep=None) == 2
    assert rig.tr.calls == 0
