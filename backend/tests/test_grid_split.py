"""M1.4 split berstrata: S1-S10 (docs/scenarios/M1.4.md)."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from backend.grid.split import (
    SplitError,
    SplitNotApplicable,
    base_partition,
    ensure_split,
    load_latest_split_record,
    load_split_records,
    make_split,
)
from backend.tests.grid_helpers import ids, mk_items

REPO = Path(__file__).resolve().parents[2]
OP, SP = "operator", "spark_disetujui"
LIT, PAR = "literal", "parafrase"


def split(items, seed=7, ratio=0.4, previous=None, family="uupt"):
    return make_split(items, family=family, seed=seed, held_out_ratio=ratio, min_control=3, previous=previous)


def counts(rec, items):
    by = {i.id: (i.origin, i.mode) for i in items}
    c = Counter()
    for a in rec.assignments:
        if a.split == "held_out":
            c[by[a.item_id]] += 1
    return c


def s1_items():
    return mk_items({
        (OP, LIT): ids("u", 1, 5), (OP, PAR): ids("u", 6, 10),
        (SP, LIT): ids("u", 11, 14), (SP, PAR): ids("u", 15, 20),
    })


def test_S01_basic_rounding_per_stratum():
    items = s1_items()
    rec = split(list(reversed(items)))
    c = counts(rec, items)
    assert (c[(OP, LIT)], c[(OP, PAR)], c[(SP, LIT)], c[(SP, PAR)]) == (2, 2, 2, 2)
    assert sum(1 for a in rec.assignments if a.split == "held_out") == 8
    assert sum(1 for a in rec.assignments if a.split == "tune") == 12
    assert rec.split_version == 1 and rec.seed == 7 and rec.held_out_ratio == 0.4
    assert rec.strata == ("origin", "mode") and rec.control_in_held_out == 4
    assert len(rec.assignments) == 20 and len({a.item_id for a in rec.assignments}) == 20
    assert all(a.added_in_version == 1 for a in rec.assignments)


def test_S02_small_strata_no_control_move():
    items = mk_items({(OP, LIT): ids("a", 1, 7), (OP, PAR): ["b1"], (SP, LIT): ["c1", "c2"], (SP, PAR): ids("d", 1, 3)})
    rec = split(items, seed=11)
    c = counts(rec, items)
    assert (c[(OP, LIT)], c[(OP, PAR)], c[(SP, LIT)], c[(SP, PAR)]) == (3, 0, 1, 1)
    assert rec.split_of()["b1"] == "tune"
    assert rec.control_in_held_out == 3


def test_S03_ratio_from_config():
    items = mk_items({(OP, LIT): ids("a", 1, 8), (OP, PAR): ids("b", 1, 8), (SP, LIT): ids("c", 1, 4), (SP, PAR): ids("d", 1, 4)})
    rec = split(items, seed=3, ratio=0.25)
    c = counts(rec, items)
    assert (c[(OP, LIT)], c[(OP, PAR)], c[(SP, LIT)], c[(SP, PAR)]) == (2, 2, 1, 1)
    assert rec.held_out_ratio == 0.25 and rec.control_in_held_out == 4


S4_ITEMS = lambda: mk_items({(OP, LIT): ids("o", 1, 3), (OP, PAR): ["p1", "p2"], (SP, LIT): ids("s", 1, 6), (SP, PAR): ids("t", 1, 9)})


def test_S04_partial_control_move_keeps_spark_unchanged():
    items = S4_ITEMS()
    rec = split(items, seed=5)
    c = counts(rec, items)
    assert sum(c.values()) == 9 and rec.control_in_held_out == 3
    assert (c[(SP, LIT)], c[(SP, PAR)]) == (2, 4)
    assert (c[(OP, LIT)], c[(OP, PAR)]) in {(2, 1), (1, 2)}
    base = base_partition(items, seed=5, held_out_ratio=0.4)
    spark_ids = [i.id for i in items if i.origin == SP]
    assert {i: rec.split_of()[i] for i in spark_ids} == {i: base[i] for i in spark_ids}
    moved = [i.id for i in items if i.origin == OP and base[i.id] != rec.split_of()[i.id]]
    assert len(moved) == 1 and rec.split_of()[moved[0]] == "held_out"


def test_S05_forced_all_control_to_held_out():
    items = mk_items({(OP, LIT): ["o1", "o2"], (OP, PAR): ["p1"], (SP, LIT): ids("s", 1, 5), (SP, PAR): ids("t", 1, 5)})
    rec = split(items, seed=21)
    sp = rec.split_of()
    assert all(sp[i] == "held_out" for i in ("o1", "o2", "p1"))
    c = counts(rec, items)
    assert (c[(SP, LIT)], c[(SP, PAR)]) == (2, 2)
    assert sum(c.values()) == 7 and rec.control_in_held_out == 3
    tune = [i.id for i in items if sp[i.id] == "tune"]
    assert len(tune) == 6 and all(i.startswith(("s", "t")) for i in tune)


@pytest.mark.parametrize("n_ctrl,case", [(2, "A"), (0, "B")])
def test_S06_too_few_control_fails_clearly(n_ctrl, case, tmp_path):
    groups = {(SP, LIT): ids("s", 1, 5), (SP, PAR): ids("t", 1, 5)}
    if n_ctrl == 2:
        groups[(OP, LIT)] = ["o1"]
        groups[(OP, PAR)] = ["o2"]
    else:
        groups[(SP, LIT)] = ids("s", 1, 6)
        groups[(SP, PAR)] = ids("t", 1, 6)
    items = mk_items(groups)
    with pytest.raises(SplitError) as ei:
        ensure_split(items, directory=tmp_path, family="uupt", seed=1, held_out_ratio=0.4, min_control=3)
    assert ei.value.found == n_ctrl and ei.value.needed == 3
    assert str(n_ctrl) in str(ei.value) and "3" in str(ei.value)
    assert list(tmp_path.iterdir()) == []


def test_S07_determinism_and_order_independence():
    items = s1_items()
    a = split(items)
    b = split(list(reversed(items)))
    import random
    shuffled = items[:]
    random.Random(99).shuffle(shuffled)
    c = split(shuffled)
    assert a == b == c
    assert [x.item_id for x in a.assignments] == sorted(x.item_id for x in a.assignments)
    held = set()
    for k in range(1, 21):
        r = split(items, seed=k)
        assert r.seed == k
        sp = r.split_of()
        held.add(frozenset(i for i in ids("u", 15, 20) if sp[i] == "held_out"))
    assert len(held) >= 2


def test_S07_separate_process_hashseed():
    code = (
        "import json;from backend.grid.split import make_split;"
        "from backend.tests.grid_helpers import mk_items, ids;"
        "it=mk_items({('operator','literal'):ids('u',1,5),('operator','parafrase'):ids('u',6,10),"
        "('spark_disetujui','literal'):ids('u',11,14),('spark_disetujui','parafrase'):ids('u',15,20)});"
        "r=make_split(it,family='uupt',seed=7,held_out_ratio=0.4,min_control=3);"
        "print(json.dumps(r.to_dict(),sort_keys=True))"
    )
    outs = []
    for hs in ("1", "12345"):
        env = {**__import__("os").environ, "PYTHONHASHSEED": hs}
        p = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, check=True)
        outs.append(p.stdout)
    assert outs[0] == outs[1]
    assert json.loads(outs[0]) == split(s1_items()).to_dict()


def s8_items():
    return s1_items() + mk_items({(SP, PAR): ["z1"], (SP, LIT): ["z2", "z3"], (OP, LIT): ["z4"]})


def test_S08_new_items_version_bump_cumulative_target():
    v1 = split(s1_items())
    v2 = split(s8_items(), previous=v1)
    assert v2.split_version == 2
    old = {a.item_id: a for a in v2.assignments if a.item_id.startswith("u")}
    assert old == {a.item_id: a for a in v1.assignments}
    sp = v2.split_of()
    assert sp["z1"] == "held_out" and sp["z2"] == sp["z3"] == sp["z4"] == "tune"
    assert all(a.added_in_version == 2 for a in v2.assignments if a.item_id.startswith("z"))
    assert v2.control_in_held_out == 4 and v2.seed == 7 and v2.held_out_ratio == 0.4
    assert sum(1 for a in v2.assignments if a.split == "held_out") == 9


def test_S08_storage_keeps_history(tmp_path):
    ensure_split(s1_items(), directory=tmp_path, family="uupt", seed=7, held_out_ratio=0.4, min_control=3)
    ensure_split(s8_items(), directory=tmp_path, family="uupt", seed=7, held_out_ratio=0.4, min_control=3)
    recs = load_split_records(tmp_path, "uupt")
    assert [r.split_version for r in recs] == [1, 2]
    assert len(recs[0].assignments) == 20


def test_S09_idempotent_and_old_record_wins(tmp_path):
    kw = dict(directory=tmp_path, family="uupt", min_control=3)
    ensure_split(s1_items(), seed=7, held_out_ratio=0.4, **kw)
    v2 = ensure_split(s8_items(), seed=7, held_out_ratio=0.4, **kw)
    again = ensure_split(s8_items(), seed=7, held_out_ratio=0.4, **kw)
    assert again == v2 and again.split_version == 2
    changed = ensure_split(s8_items(), seed=999, held_out_ratio=0.5, **kw)
    assert changed == v2 and changed.seed == 7 and changed.held_out_ratio == 0.4
    assert load_latest_split_record(tmp_path, "uupt") == v2
    assert [r.split_version for r in load_split_records(tmp_path, "uupt")] == [1, 2]


def test_S10_akta_no_split(tmp_path):
    items = mk_items({(OP, LIT): ["k1"], (OP, PAR): ["k2"], (SP, LIT): ["k3", "k4"], (SP, PAR): ["k5"]}, family="akta")
    with pytest.raises(SplitNotApplicable):
        ensure_split(items, directory=tmp_path, family="akta", seed=1, held_out_ratio=0.4, min_control=3)
    assert list(tmp_path.iterdir()) == []
