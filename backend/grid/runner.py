"""Runner grid dengan cache per hash (docs/ARCHITECTURE.md §8). Pipeline disuntik; tanpa jaringan."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from backend.metrics.types import ItemMetrics
from backend.grid.frontier import aggregate_points, compute_frontiers
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
) -> GridRun:
    """family bersplit: `split_record` wajib. akta: `split_record` None, split pada metrik = None (H-054, H-059)."""
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

    cached = cache.get(key)
    if cached is not None:
        metrics = [metrics_from_cache(d) for d in cached]
        hit = True
    else:
        metrics = []
        want = {i.id for i in items}
        for st in settings:
            got = pipeline(st, items)
            if {m.item_id for m in got} != want or len(got) != len(want):
                raise GridError(f"pipeline returned a different item set for setting {st.setting_id}")
            metrics.extend(replace(m, setting_id=st.setting_id, split=split_of[m.item_id]) for m in got)
        metrics.sort(key=lambda m: (m.setting_id, m.item_id))
        cache.put(key, [metrics_to_cache(m) for m in metrics])
        hit = False

    by_id = {s.setting_id: s for s in settings}
    points, frontiers = compute_frontiers(aggregate_points(metrics, by_id), key)
    selections = select_profiles(points, by_id, simplicity, family=family) if family != NO_SPLIT_FAMILY else {}
    return GridRun(key, hit, tuple(metrics), tuple(points), tuple(frontiers), selections)
