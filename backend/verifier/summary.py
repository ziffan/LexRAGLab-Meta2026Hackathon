"""Sel 2x2 penolakan (V10-any) dan `RejectionSummary` berkunci (setting_id, slot, model_profile) (V11).

Hitungan mentah (integer), tanpa persen. Murni: tanpa I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from .config import VerifierConfig
from .verify import LULUS, AddressUnit, ChunkSpan, CitationVerdict, Scorer, overlaps, verify_answer_detailed

CELLS = ("answered_supported", "answered_unsupported", "abstained_correct", "abstained_should_answer")
ABSTAIN = ("tolak", "bukti_tidak_cukup")
Gold = Sequence[tuple[int, int]]


@dataclass(frozen=True)
class RejectionSummary:
    setting_id: str
    slot: str
    model_profile: str
    answered_supported: int
    answered_unsupported: int
    abstained_correct: int
    abstained_should_answer: int
    n_items: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hits_gold(c: ChunkSpan, gold: Gold) -> bool:
    return any(overlaps(c.start, c.end, g0, g1) for g0, g1 in gold)


def classify_answer(status: str, verdicts: Sequence[CitationVerdict], chunks: Sequence[ChunkSpan], gold: Gold) -> str:
    """Sel 2x2 (EVAL-SPEC 10). `chunks` = P (konteks); `gold` = G sebagai daftar [start,end)."""
    if status in ABSTAIN:
        return "abstained_should_answer" if any(_hits_gold(c, gold) for c in chunks) else "abstained_correct"
    if status != "jawab":
        raise ValueError(f"unknown answer status {status!r}")
    if not verdicts or not gold:
        return "answered_unsupported"
    if not all(v.result.exists == LULUS and v.result.faithful == LULUS for v in verdicts):
        return "answered_unsupported"
    for v in verdicts:  # V10-any: ada potongan yang beririsan dengan rentang tertaut DAN dengan G
        if v.linked is not None and any(overlaps(c.start, c.end, *v.linked) and _hits_gold(c, gold) for c in chunks):
            return "answered_supported"
    return "answered_unsupported"


def grade_answer(answer_id: str, output: Mapping[str, Any], units: Mapping[str, AddressUnit], chunks: Sequence[ChunkSpan],
                 gold: Gold, cfg: VerifierConfig, *, scorer: Scorer | None = None) -> tuple[list[CitationVerdict], str]:
    verdicts = verify_answer_detailed(answer_id, output, units, chunks, cfg, scorer=scorer)
    return verdicts, classify_answer(output.get("status", ""), verdicts, chunks, gold)


def summarize(entries: Iterable[tuple[str, str, str, str]],
              keys: Iterable[tuple[str, str, str]] = ()) -> list[RejectionSummary]:
    """`entries` = (setting_id, slot, model_profile, sel). Satu ringkasan per kunci; `keys` memastikan kunci tanpa
    jawaban muncul dengan hitungan nol. Urutan keluaran = kunci terurut (deterministik)."""
    counts: dict[tuple[str, str, str], dict[str, int]] = {}
    for k in keys:
        counts.setdefault(tuple(k), dict.fromkeys(CELLS, 0))
    for setting_id, slot, profile, cell in entries:
        if cell not in CELLS:
            raise ValueError(f"unknown cell {cell!r}")
        counts.setdefault((setting_id, slot, profile), dict.fromkeys(CELLS, 0))[cell] += 1
    return [RejectionSummary(k[0], k[1], k[2], c["answered_supported"], c["answered_unsupported"], c["abstained_correct"],
                             c["abstained_should_answer"], sum(c.values())) for k, c in sorted(counts.items())]


def units_from_address_map(amap: Any, text: str) -> dict[str, AddressUnit]:
    """Peta alamat verifier dari `AddressMap` (backend.chunking.address_map): unit dan rincian (huruf/angka)."""
    out: dict[str, AddressUnit] = {}
    for u in amap.units:
        out[u.address] = AddressUnit(u.address, u.start, u.end, text[u.start:u.end])
        for r in u.children:
            out[r.address] = AddressUnit(r.address, r.start, r.end, text[r.start:r.end])
    return out
