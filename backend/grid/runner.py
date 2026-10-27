"""Runner grid dengan cache per hash (docs/ARCHITECTURE.md §8). Pipeline disuntik; tanpa jaringan."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from backend.metrics.types import ItemMetrics
from backend.grid.frontier import aggregate_points, compute_frontiers
from backend.grid.headers import SCOPES, FailedSetting, HeaderError, failed_from_error, twin_key
from backend.grid.select import Selection, select_profiles
from backend.grid.types import (
    Frontier,
    GridItem,
    GridPoint,
    NO_SPLIT_FAMILY,
    metrics_from_cache,
    metrics_to_cache,
    Setting,
    SplitRecord,
    canonical_json,
    item_set_hash,
    sha256_hex,
)

Pipeline = Callable[[Setting, Sequence[GridItem]], list[ItemMetrics]]


class GridError(Exception):
    pass


class GridCache(Protocol):
    def get(self, key: str) -> list[dict[str, Any]] | None: ...
    def put(self, key: str, value: list[dict[str, Any]]) -> None: ...


class MemoryGridCache:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, key: str):
        v = self._d.get(key)
        return json.loads(v) if v is not None else None

    def put(self, key: str, value) -> None:
        self._d[key] = canonical_json(value)


class DirGridCache:
    """`runs/grid/<hash>.json`, tulis atomik."""

    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)

    def get(self, key: str):
        p = self.dir / f"{key}.json"
        if not p.exists():
            return None
        return json.loads(p.read_bytes().decode("utf-8"))

    def put(self, key: str, value) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        p = self.dir / f"{key}.json"
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(canonical_json(value) + "\n")
        os.replace(tmp, p)


def grid_cache_key(clean_sha256: str, config_hash: str, items_hash: str, split_version: int | None) -> str:
    return sha256_hex(canonical_json([clean_sha256, config_hash, items_hash, split_version]))


@dataclass(frozen=True)
class GridRun:
    grid_run_id: str
    cache_hit: bool
    metrics: tuple[ItemMetrics, ...]
    points: tuple[GridPoint, ...]
    frontiers: tuple[Frontier, ...]
    selections: Mapping[int, Selection]  # kosong untuk akta
    failed_settings: tuple[FailedSetting, ...] = ()  # setting header-on yang gagal (H-069); tanpa GridPoint


FAILED_MARK = "_failed_settings"  # elemen penutup nilai cache bila ada setting gagal (bukan ItemMetrics)


def _frontier_twins(off: Sequence[Setting], on: Sequence[Setting], metrics: Sequence[ItemMetrics], key: str,
                    family: str) -> list[Setting]:
    """Kembaran header-on yang boleh dieksekusi (`scope = frontier_only`, A6): hanya kembaran dari setting yang ada di
    frontier TUNE deret off per anggaran. Held-out tidak dibaca (EVAL-SPEC §8 butir 6)."""
    by_id = {s.setting_id: s for s in off}
    points, frontiers = compute_frontiers(aggregate_points(metrics, by_id), key)
    split = None if family == NO_SPLIT_FAMILY else "tune"
    keep = {pid for f in frontiers if f.split == split for pid in f.point_ids}
    wanted = {twin_key(by_id[pid]) for pid in keep}
    return [s for s in on if twin_key(s) in wanted]


def run_grid(
    *,
    settings: Sequence[Setting],
    items: Sequence[GridItem],
    pipeline: Pipeline,
    cache: GridCache,
    clean_sha256: str,
    config_hash: str,
    split_record: SplitRecord | None,
    simplicity: Mapping[str, Any],
    family: str,
    header_scope: str = "all",
) -> GridRun:
    """family bersplit: `split_record` wajib. akta: `split_record` None, split pada metrik = None (H-054, H-059).

    `header_scope` (`config/header_b.scope`, harus ikut `config_hash`, A10): `all` mengeksekusi semua setting;
    `frontier_only` mengeksekusi deret off lebih dulu lalu hanya kembaran header-on dari frontier tune off (H-069).
    `HeaderError` dari pipeline = setting itu gagal: dicatat di `failed_settings`, tanpa metrik, run lanjut."""
    if header_scope not in SCOPES:
        raise GridError(f"header_scope must be one of {list(SCOPES)}, got {header_scope!r}")
    if family != NO_SPLIT_FAMILY:
        if split_record is None:
            raise GridError("a split-bearing family requires a SplitRecord")
        split_of: dict[str, str | None] = dict(split_record.split_of())
        missing = [i.id for i in items if i.id not in split_of]
        if missing:
            raise GridError(f"items without split assignment: {sorted(missing)}")
    else:
        split_of = {i.id: None for i in items}
    version = split_record.split_version if (family != NO_SPLIT_FAMILY and split_record) else None
    key = grid_cache_key(clean_sha256, config_hash, item_set_hash(items), version)

    failed: list[FailedSetting] = []
    cached = cache.get(key)
    if cached is not None:
        metrics = [metrics_from_cache(d) for d in cached if FAILED_MARK not in d]
        failed = [FailedSetting(**f) for d in cached if FAILED_MARK in d for f in d[FAILED_MARK]]
        hit = True
    else:
        metrics = []
        want = {i.id for i in items}

        def execute(st: Setting) -> None:
            try:
                got = pipeline(st, items)
            except HeaderError as err:
                failed.append(failed_from_error(err))
                return
            if {m.item_id for m in got} != want or len(got) != len(want):
                raise GridError(f"pipeline returned a different item set for setting {st.setting_id}")
            metrics.extend(replace(m, setting_id=st.setting_id, split=split_of[m.item_id]) for m in got)

        off = [s for s in settings if not s.header_b]
        on = [s for s in settings if s.header_b]
        for st in off:
            execute(st)
        if on and header_scope == "frontier_only":
            on = _frontier_twins(off, on, metrics, key, family)
        for st in on:
            execute(st)
        metrics.sort(key=lambda m: (m.setting_id, m.item_id))
        value: list[dict[str, Any]] = [metrics_to_cache(m) for m in metrics]
        if failed:
            value.append({FAILED_MARK: [f.to_dict() for f in failed]})
        cache.put(key, value)
        hit = False

    by_id = {s.setting_id: s for s in settings}
    points, frontiers = compute_frontiers(aggregate_points(metrics, by_id), key)
    selections = select_profiles(points, by_id, simplicity, family=family) if family != NO_SPLIT_FAMILY else {}
    return GridRun(key, hit, tuple(metrics), tuple(points), tuple(frontiers), selections, tuple(failed))
