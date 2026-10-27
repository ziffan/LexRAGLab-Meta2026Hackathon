"""Split berstrata (docs/EVAL-SPEC.md §8, H-015, H-049).

Generator acak: `random.Random` (Mersenne Twister) di-seed per stratum dari
sha256(seed:parts); tidak bergantung PYTHONHASHSEED atau urutan masukan.
Pembulatan: `round` atas Fraction eksak per stratum (A2).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Sequence

from backend.grid.types import NO_SPLIT_FAMILY, Assignment, SplitRecord

CONTROL_ORIGIN = "operator"  # enum Item.origin (DATA-CONTRACTS §4)
TUNE = "tune"
HELD_OUT = "held_out"


class SplitError(Exception):
    """Split gagal; `found` dan `needed` terisi untuk kasus kontrol kurang."""

    def __init__(self, message: str, found: int | None = None, needed: int | None = None):
        super().__init__(message)
        self.found = found
        self.needed = needed


class SplitNotApplicable(SplitError):
    """Keluarga tanpa split (akta, H-054)."""


def _rng(*parts: Any) -> random.Random:
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _round_count(ratio: Any, n: int) -> int:
    return round(Fraction(str(ratio)) * n)


def _key(item: Any, strata: Sequence[str]) -> tuple:
    return tuple(getattr(item, k) for k in strata)


def _check(items: Sequence[Any], family: str) -> list[Any]:
    if family == NO_SPLIT_FAMILY:
        raise SplitNotApplicable(f"family {family!r} has no split (H-054)")
    ordered = sorted(items, key=lambda i: i.id)
    ids = [i.id for i in ordered]
    if len(set(ids)) != len(ids):
        raise SplitError("duplicate item ids")
    for i in ordered:
        if i.family != family:
            raise SplitError(f"item {i.id} has family {i.family!r}, expected {family!r}")
    return ordered


def _shuffled_strata(ordered: Sequence[Any], seed: int, strata: Sequence[str]) -> dict[tuple, list[Any]]:
    groups: dict[tuple, list[Any]] = defaultdict(list)
    for it in ordered:
        groups[_key(it, strata)].append(it)
    for key, lst in groups.items():
        _rng(seed, *key).shuffle(lst)
    return groups


def base_partition(
    items: Sequence[Any], *, seed: int, held_out_ratio: Any, strata: Sequence[str] = ("origin", "mode")
) -> dict[str, str]:
    """Pembagian dasar per stratum, sebelum pemindahan kontrol."""
    ordered = sorted(items, key=lambda i: i.id)
    out: dict[str, str] = {}
    for key, lst in _shuffled_strata(ordered, seed, strata).items():
        k = _round_count(held_out_ratio, len(lst))
        for n, it in enumerate(lst):
            out[it.id] = HELD_OUT if n < k else TUNE
    return out


def _create(ordered, family, seed, ratio, min_control, strata) -> SplitRecord:
    found = sum(1 for i in ordered if i.origin == CONTROL_ORIGIN)
    if found < min_control:
        raise SplitError(
            f"split impossible: found {found} control items (origin={CONTROL_ORIGIN}), need {min_control}",
            found=found,
            needed=min_control,
        )
    groups = _shuffled_strata(ordered, seed, strata)
    split: dict[str, str] = {}
    tune_pool: list[Any] = []
    for key in sorted(groups):
        k = _round_count(ratio, len(groups[key]))
        for n, it in enumerate(groups[key]):
            split[it.id] = HELD_OUT if n < k else TUNE
            if n >= k and it.origin == CONTROL_ORIGIN:
                tune_pool.append(it)
    control_held = sum(1 for i in ordered if split[i.id] == HELD_OUT and i.origin == CONTROL_ORIGIN)
    need = min_control - control_held
    for it in tune_pool[: max(0, need)]:
        split[it.id] = HELD_OUT
        control_held += 1
    if control_held < min_control:  # pengaman; tak terjangkau setelah pemeriksaan total di atas
        raise SplitError("control requirement not met", found=control_held, needed=min_control)
    return SplitRecord(
        family=family,
        split_version=1,
        seed=seed,
        held_out_ratio=ratio,
        strata=tuple(strata),
        assignments=tuple(Assignment(i.id, split[i.id], 1) for i in ordered),
        control_in_held_out=control_held,
    )


def _extend(ordered, prev: SplitRecord) -> SplitRecord:
    assigned = prev.split_of()
    new = [i for i in ordered if i.id not in assigned]
    if not new:
        return prev
    version = prev.split_version + 1
    strata = prev.strata
    total: dict[tuple, int] = defaultdict(int)
    held_old: dict[tuple, int] = defaultdict(int)
    new_by: dict[tuple, list[Any]] = defaultdict(list)
    for it in ordered:
        k = _key(it, strata)
        total[k] += 1
        if it.id in assigned:
            if assigned[it.id] == HELD_OUT:
                held_old[k] += 1
        else:
            new_by[k].append(it)
    added: dict[str, str] = {}
    control_added = 0
    for key in sorted(new_by):
        lst = new_by[key]
        target = _round_count(prev.held_out_ratio, total[key])
        need = min(len(lst), max(0, target - held_old[key]))
        _rng(prev.seed, "new", version, *key).shuffle(lst)
        for n, it in enumerate(lst):
            added[it.id] = HELD_OUT if n < need else TUNE
            if n < need and it.origin == CONTROL_ORIGIN:
                control_added += 1
    assignments = list(prev.assignments) + [Assignment(i, s, version) for i, s in added.items()]
    assignments.sort(key=lambda a: a.item_id)
    return SplitRecord(
        family=prev.family,
        split_version=version,
        seed=prev.seed,
        held_out_ratio=prev.held_out_ratio,
        strata=prev.strata,
        assignments=tuple(assignments),
        control_in_held_out=prev.control_in_held_out + control_added,
    )


def make_split(
    items: Iterable[Any],
    *,
    family: str,
    seed: int,
    held_out_ratio: Any,
    min_control: int,
    strata: Sequence[str] = ("origin", "mode"),
    previous: SplitRecord | None = None,
) -> SplitRecord:
    """Fungsi murni. `previous` ada: record lama menang (seed, rasio, assignment tidak berubah)."""
    ordered = _check(list(items), family)
    if previous is not None:
        return _extend(ordered, previous)
    return _create(ordered, family, seed, held_out_ratio, min_control, tuple(strata))


# --- penyimpanan (menerima direktori) ---


def _path(directory: Path, family: str, version: int) -> Path:
    return Path(directory) / f"split_{family}_v{version:04d}.json"


def save_split_record(record: SplitRecord, directory: Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = _path(directory, record.family, record.split_version)
    text = json.dumps(record.to_dict(), sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return path


def load_split_records(directory: Path, family: str) -> list[SplitRecord]:
    out = []
    for p in sorted(Path(directory).glob(f"split_{family}_v*.json")):
        out.append(SplitRecord.from_dict(json.loads(p.read_bytes().decode("utf-8"))))
    return sorted(out, key=lambda r: r.split_version)


def load_latest_split_record(directory: Path, family: str) -> SplitRecord | None:
    recs = load_split_records(directory, family)
    return recs[-1] if recs else None


def ensure_split(
    items: Iterable[Any],
    *,
    directory: Path,
    family: str,
    seed: int,
    held_out_ratio: Any,
    min_control: int,
    strata: Sequence[str] = ("origin", "mode"),
) -> SplitRecord:
    """Muat record terakhir, hitung, simpan hanya bila versi baru. Gagal = tidak ada yang tersimpan."""
    prev = load_latest_split_record(directory, family) if family != NO_SPLIT_FAMILY else None
    rec = make_split(
        items, family=family, seed=seed, held_out_ratio=held_out_ratio,
        min_control=min_control, strata=strata, previous=prev,
    )
    if prev is None or rec.split_version != prev.split_version:
        save_split_record(rec, directory)
    return rec
