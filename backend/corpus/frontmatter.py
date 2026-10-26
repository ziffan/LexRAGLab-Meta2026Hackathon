"""Parser YAML minimal untuk bentuk frontmatter berkas korpus UU PT (tanpa dependensi).

Bentuk yang diterima: `key: nilai`, `key: >-` + baris menjorok (dilipat dengan spasi), `key:` + `  - item`,
`key: []`. Selain itu ditolak (R12).
"""

from __future__ import annotations

import re
from typing import Any

from .errors import CorpusError

_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(?: (.*))?$")
_ITEM = re.compile(r"^  - (.+)$")


def parse_frontmatter(lines: list[tuple[str, int]]) -> dict[str, dict[str, Any]]:
    """`lines` = [(teks, nomor_baris_berkas)]. Hasil: {kunci: {"value": ..., "line": nomor_baris}}."""
    out: dict[str, dict[str, Any]] = {}
    i = 0
    while i < len(lines):
        text, ln = lines[i]
        if text == "":
            i += 1
            continue
        m = _KEY.match(text)
        if not m:
            raise CorpusError("R12", f"frontmatter line {ln} is not a recognised 'key: value' form: {text[:60]!r}")
        key, inline = m.group(1), m.group(2)
        if key in out:
            raise CorpusError("R12", f"frontmatter key {key!r} duplicated at line {ln}")
        i += 1
        if inline is None:  # `key:` lalu daftar `  - item`
            items: list[str] = []
            while i < len(lines) and (im := _ITEM.match(lines[i][0])):
                items.append(im.group(1).strip())
                i += 1
            if not items:
                raise CorpusError("R12", f"frontmatter key {key!r} at line {ln} has no value")
            out[key] = {"value": items, "line": ln}
        elif inline == "[]":
            out[key] = {"value": [], "line": ln}
        elif inline in (">-", ">"):
            parts: list[str] = []
            while i < len(lines) and (lines[i][0].startswith("  ") or lines[i][0] == ""):
                if lines[i][0] != "":
                    parts.append(lines[i][0].strip())
                i += 1
            if not parts:
                raise CorpusError("R12", f"frontmatter key {key!r} at line {ln} has an empty folded block")
            out[key] = {"value": " ".join(parts), "line": ln}
        elif inline.startswith(("|", "[", "{", '"', "'", "&", "*", "!")):
            raise CorpusError("R12", f"frontmatter key {key!r} at line {ln} uses an unsupported YAML form: {inline[:30]!r}")
        else:
            out[key] = {"value": inline.strip(), "line": ln}
    return out
