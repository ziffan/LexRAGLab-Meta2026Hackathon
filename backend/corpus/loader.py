"""Pemuat korpus UU PT: baca biner, tolak berkas tak sah, pisahkan anotasi, bentuk teks bersih (H-046).

Aturan: docs/DATA-CONTRACTS.md §2. Tanpa panggilan model, tanpa tokenizer (G3).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend import config as _config

from . import structure
from .akta import akta_entries, load_akta
from .errors import CorpusError
from .frontmatter import parse_frontmatter
from .sources import parse_id_date, parse_sources

SEP = " › "  # U+203A, pemisah alamat kanonik
_BOLD_LINE = re.compile(r"^\*\*([^*].*?)\*\*$")
_MARKER = re.compile(r"\[\^(\d+)\]")
_DEF = re.compile(r"^\[\^(\d+)\]: (\S.*)$")
_PASAL_H = re.compile(r"^### Pasal (\d+[A-Z]?)$")
_DIUNDANGKAN_DATE = re.compile(r"^Pada Tanggal (\d{1,2}) (\S+) (\d{4})$")


@dataclass
class CorpusDoc:
    """`CorpusDoc` DATA-CONTRACTS §2 + teks bersih, peta baris, dan metadata (di luar §2)."""

    doc_id: str
    family: str
    title: str
    path: str
    sha256: str
    clean_sha256: str
    loader_rules_version: str
    char_count: int
    tokens_local: int | None
    tokens_endpoint: int | None
    calibration_ratio: float | None
    sections: list[dict[str, Any]]
    annotations: list[dict[str, Any]]
    text: str = field(repr=False, default="")
    line_map: list[list[int]] = field(repr=False, default_factory=list)  # [offset_awal_baris, nomor_baris_berkas]
    metadata: dict[str, Any] = field(repr=False, default_factory=dict)

    def to_dict(self, include_text: bool = False) -> dict[str, Any]:
        d = asdict(self)
        if not include_text:
            d.pop("text")
        return d


def _line_of(raw_text: str, index: int) -> int:
    return raw_text.count("\n", 0, index) + 1


def read_checked(path: Path, expected_sha256: str | None) -> tuple[str, str]:
    """R1-R4. Kembali (teks, sha256). `expected_sha256=None` melewati pemeriksaan hash (khusus test)."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise CorpusError("R1", f"corpus file not found: {path}") from None
    except OSError as exc:
        raise CorpusError("R1", f"corpus file cannot be read: {path}: {exc}") from None
    if not raw:
        raise CorpusError("R1", f"corpus file is empty: {path}")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CorpusError("R4", f"corpus file starts with a UTF-8 BOM (rejected, G-16): {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorpusError("R1", f"corpus file is not valid UTF-8: {path} (byte offset {exc.start}: {exc.reason})") from None
    if "\r" in text:
        raise CorpusError("R3", f"corpus file contains a carriage return (CRLF checkout? G-16): {path}, first at line {_line_of(text, text.index(chr(13)))}")
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and sha != expected_sha256:
        raise CorpusError("R2", f"corpus file hash not accepted: {path}: got sha256 {sha}, expected {expected_sha256}")
    return text, sha


def _pasal_address(prefix: str, pasal: str, ayat: int | None = None, huruf: str | None = None) -> str:
    parts = [prefix, f"Pasal {pasal}"]
    if ayat is not None:
        parts.append(f"ayat ({ayat})")
        if huruf:
            parts.append(f"huruf {huruf}")
    return SEP.join(parts)


def _check_frontmatter(fm: dict[str, dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    want = list(cfg["frontmatter_keys"])
    missing = [k for k in want if k not in fm]
    extra = [k for k in fm if k not in want]
    if missing or extra:
        raise CorpusError("R12", f"frontmatter keys differ from the frozen file: missing={missing}, unexpected={extra}")
    for k in cfg["frontmatter_must_be_empty"]:
        if fm[k]["value"] != []:
            raise CorpusError("R12", f"frontmatter key {k!r} (line {fm[k]['line']}) must be empty until its content is specified")
    for k in want:
        if k in cfg["frontmatter_must_be_empty"] or k == "konsolidasi_dalam_satu_naskah_berdasarkan":
            continue
        if not isinstance(fm[k]["value"], str) or not fm[k]["value"]:
            raise CorpusError("R12", f"frontmatter key {k!r} (line {fm[k]['line']}) must be a non-empty string")
    src = fm["konsolidasi_dalam_satu_naskah_berdasarkan"]
    if not isinstance(src["value"], list):
        raise CorpusError("R12", f"frontmatter key 'konsolidasi_dalam_satu_naskah_berdasarkan' (line {src['line']}) must be a list")
    return parse_sources(src["value"], src["line"], cfg)


def load_corpus(
    doc_id: str = "uupt-40-2007",
    *,
    path: Path | str | None = None,
    verify_hash: bool = True,
    expected_sha256: str | None = None,
    config_dir: Path | None = None,
) -> CorpusDoc:
    """Muat dan bersihkan satu dokumen UU PT.

    `path` mengganti jalur dari config (untuk uji pada salinan termutasi). `verify_hash=False` khusus test:
    melewati R2 agar aturan struktur R5-R12 bisa diuji. `expected_sha256` mengganti hash dari config.
    """
    cfg_all = _config.load("corpus", config_dir)
    docs = {d["doc_id"]: d for d in cfg_all["documents"]}
    if doc_id not in docs:
        deeds = akta_entries(config_dir)  # keluarga akta: config/corpus_akta.toml (terpisah agar hash config UU PT tak berubah)
        if doc_id in deeds:
            return load_akta(deeds[doc_id], config_dir=config_dir, path=path, verify_hash=verify_hash, expected_sha256=expected_sha256)
        raise CorpusError("R1", f"doc_id {doc_id!r} is not listed in config/corpus.toml")
    entry = docs[doc_id]
    if entry["family"] != "uupt":
        raise CorpusError("R1", f"doc_id {doc_id!r} is family {entry['family']!r}; only 'uupt' is supported by this loader")
    cfg = cfg_all["loader_uupt"]
    file_path = Path(path) if path is not None else _config.REPO_ROOT / entry["path"]
    want_sha = (expected_sha256 or entry["sha256"]) if verify_hash else None
    text, sha = read_checked(file_path, want_sha)
    prefix = entry["address_prefix"]

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    # --- frontmatter
    if not lines or lines[0] != "---":
        raise CorpusError("R12", "frontmatter missing: line 1 must be '---'")
    try:
        fm_end = next(i for i in range(1, len(lines)) if lines[i] == "---")
    except StopIteration:
        raise CorpusError("R12", "frontmatter is not closed by a second '---'") from None
    fm = parse_frontmatter([(lines[i], i + 1) for i in range(1, fm_end)])
    sources = _check_frontmatter(fm, cfg)

    # --- disclaimer editorial
    k = fm_end + 1
    while k < len(lines) and lines[k] == "":
        k += 1
    if k >= len(lines) or lines[k] != cfg["disclaimer"]:
        raise CorpusError("R12", f"editorial disclaimer not found as the first non-empty line after the frontmatter (line {k + 1})")

    # --- pemisah terakhir '---' dan definisi footnote
    sep = max((i for i in range(k + 1, len(lines)) if lines[i] == "---"), default=None)
    if sep is None:
        raise CorpusError("R6", "final '---' separator before the footnote definitions is missing")
    defs: dict[int, tuple[str, int]] = {}
    for i in range(sep + 1, len(lines)):
        if lines[i] == "":
            continue
        dm = _DEF.match(lines[i])
        if not dm:
            raise CorpusError("R6", f"unexpected content after the final '---' at line {i + 1}: {lines[i][:60]!r}")
        n = int(dm.group(1))
        if n in defs:
            raise CorpusError("R6", f"footnote [^{n}] defined twice (line {i + 1})")
        defs[n] = (dm.group(2), i + 1)

    # --- badan: label, penanda footnote, judul
    labels_cfg = {lab["text"]: lab["kind"] for lab in cfg["labels"]}
    out: list[tuple[str, int]] = []  # (teks, nomor baris berkas)
    refs: list[dict[str, Any]] = []
    label_anns: list[dict[str, Any]] = []
    seen_h2 = False
    after_pasal = False
    pasal_idx = -1
    pasal: str | None = None
    in_penj = False
    ayat: int | None = None
    huruf: str | None = None
    for i in range(k + 1, sep):
        t, ln = lines[i], i + 1
        if t == "":
            out.append(("", ln))
            continue
        bold = _BOLD_LINE.match(t)
        if bold and "**" not in bold.group(1):
            inner = bold.group(1)
            if not seen_h2:
                t = inner  # judul naskah: pembungkus ** dibuang
            elif inner in labels_cfg or after_pasal:
                if inner not in labels_cfg:
                    raise CorpusError("R7", f"unknown annotation label at source line {ln}: {inner!r}")
                if not after_pasal:
                    raise CorpusError("R7", f"annotation label at source line {ln} is not the first non-empty line below a '### Pasal' heading: {inner!r}")
                label_anns.append({"kind": labels_cfg[inner], "text": inner, "pasal": pasal, "pasal_idx": pasal_idx, "source_line": ln})
                after_pasal = False
                continue
        if t.startswith("## "):
            seen_h2 = True
        if t.startswith("#"):
            pm = _PASAL_H.match(t)
            after_pasal = bool(pm)
            in_penj = t.startswith("#### Penjelasan Pasal")
            if pm:
                pasal, pasal_idx, ayat, huruf = pm.group(1), len(out), None, None
            elif not in_penj:
                pasal = None
        else:
            after_pasal = False
            if not in_penj:
                am = structure.AYAT.match(t)
                bm = structure.BUTIR.match(t)
                if am:
                    ayat, huruf = int(am.group(1)), None
                elif bm and bm.group(1).isalpha():
                    huruf = bm.group(1)
            if "[^" in t and not _DEF.match(t):  # baris definisi nyasar dibiarkan; R5 menolaknya
                pieces: list[str] = []
                found: list[tuple[int, int]] = []
                shift = 0
                last = 0
                for mm in _MARKER.finditer(t):
                    pieces.append(t[last : mm.start()])
                    found.append((int(mm.group(1)), mm.start() - shift))
                    shift += mm.end() - mm.start()
                    last = mm.end()
                pieces.append(t[last:])
                t = "".join(pieces)
                for n, col in found:
                    if pasal is None or in_penj:
                        raise CorpusError("R6", f"footnote reference [^{n}] at source line {ln} is outside a batang tubuh Pasal")
                    refs.append({"n": n, "out_index": len(out), "col": col, "source_line": ln, "pasal": pasal, "ayat": ayat, "huruf": huruf})
        out.append((t, ln))

    # --- R6: referensi vs definisi vs jumlah
    ref_ns = [r["n"] for r in refs]
    for n in sorted(set(ref_ns) - set(defs)):
        raise CorpusError("R6", f"footnote reference [^{n}] has no definition")
    for n in sorted(set(defs) - set(ref_ns)):
        raise CorpusError("R6", f"footnote definition [^{n}] (line {defs[n][1]}) has no reference in the body")
    if len(ref_ns) != len(set(ref_ns)):
        raise CorpusError("R6", f"a footnote is referenced more than once: {sorted(n for n in set(ref_ns) if ref_ns.count(n) > 1)}")
    if len(defs) != cfg["footnote_count"]:
        raise CorpusError("R6", f"expected {cfg['footnote_count']} footnotes, found {len(defs)}")

    # --- normalisasi (dua baris kosong atau lebih -> satu; pangkas; satu LF)
    nonblank = [i for i, (t, _) in enumerate(out) if t]
    if not nonblank:
        raise CorpusError("R12", "no body text between the disclaimer and the final '---'")
    idxmap: dict[int, int] = {}
    clean: list[tuple[str, int]] = []
    for i in range(nonblank[0], nonblank[-1] + 1):
        t, ln = out[i]
        if t == "" and clean and clean[-1][0] == "":
            continue
        clean.append((t, ln))
        idxmap[i] = len(clean) - 1
    starts: list[int] = []
    pos = 0
    for t, _ in clean:
        starts.append(pos)
        pos += len(t) + 1
    clean_text = "\n".join(t for t, _ in clean) + "\n"
    if len(clean_text) != pos:
        raise CorpusError("R12", "internal error: clean text length mismatch")
    line_map = [[s, ln] for s, (_, ln) in zip(starts, clean)]

    # --- R5: detektor penanda tersisa atas teks bersih
    key_re = re.compile(r"^(" + "|".join(re.escape(x) for x in cfg["frontmatter_keys"]) + r"):")
    for (t, ln), s in zip(clean, starts):
        what, col = None, 0
        if "[^" in t:
            what = "footnote definition line" if re.match(r"^\[\^\d+\]:", t) else "footnote marker '[^'"
            col = t.index("[^")
        elif "**" in t:
            what, col = "bold marker '**'", t.index("**")
        elif t == "---":
            what = "separator line '---'"
        elif key_re.match(t):
            what = "frontmatter key line"
        if what:
            raise CorpusError("R5", f"residual annotation marker in clean text ({what}) at clean offset {s + col}, source line {ln}: {t[:60]!r}")

    # --- struktur (R8-R11), section
    headings = structure.classify_headings(clean)
    structure.validate_structure(clean, headings, cfg)
    sections = structure.build_sections(clean, headings, starts, len(clean_text))

    # --- anotasi + konsistensi silang (R6, R7, R12)
    pasal_set = {h.ref for h in headings if h.kind == "pasal"}
    pasal_start = {h.ref: starts[h.idx] for h in headings if h.kind == "pasal"}
    src_line = fm["konsolidasi_dalam_satu_naskah_berdasarkan"]["line"]
    for p in sources["perppu"]["changed"] + sources["perppu"]["inserted"]:
        if p not in pasal_set:
            raise CorpusError("R12", f"frontmatter (line {src_line}) names Pasal {p}, which does not exist in the file")
    kinds_found = sorted(a["kind"] for a in label_anns)
    if kinds_found != sorted(set(labels_cfg.values())):
        raise CorpusError("R7", f"expected exactly one annotation label of each kind {sorted(set(labels_cfg.values()))}, found {kinds_found}")
    annotations: list[dict[str, Any]] = [
        {"type": "frontmatter", "offset": 0, "source_line": 1, "values": {k_: v["value"] for k_, v in fm.items()}, "sources": sources},
        {"type": "disclaimer", "offset": 0, "source_line": k + 1, "text": lines[k]},
    ]
    ref_by_pasal = {r["pasal"]: r for r in refs}
    for a in label_anns:
        if a["kind"] == "mk" and cfg["mk_number"] not in a["text"]:
            raise CorpusError("R12", f"label {a['text']!r} (line {a['source_line']}) has no matching MK entry in the frontmatter ({sources['mk']['number']})")
        if a["kind"] == "uu_pengubah" and cfg["uu_pengubah_label_needle"] not in a["text"]:
            raise CorpusError("R12", f"label {a['text']!r} (line {a['source_line']}) has no matching {cfg['uu_pengubah_label']} entry in the frontmatter")
        r = ref_by_pasal.get(a["pasal"])
        if r is None:
            raise CorpusError("R6", f"label under Pasal {a['pasal']} (line {a['source_line']}) has no footnote reference in that Pasal")
        needle = sources["mk"]["number"] if a["kind"] == "mk" else cfg["uu_pengubah_footnote_needle"]
        if needle not in defs[r["n"]][0]:
            raise CorpusError("R12", f"footnote [^{r['n']}] (line {defs[r['n']][1]}) does not mention {needle!r} required by its label")
        annotations.append({
            "type": "label", "kind": a["kind"], "text": a["text"],
            "address": _pasal_address(prefix, a["pasal"]), "pasal": a["pasal"],
            "offset": starts[idxmap[a["pasal_idx"]]], "source_line": a["source_line"],
        })
    kind_by_pasal = {a["pasal"]: a["kind"] for a in label_anns}
    for r in sorted(refs, key=lambda x: x["n"]):
        if r["pasal"] not in kind_by_pasal:
            raise CorpusError("R6", f"footnote [^{r['n']}] (line {r['source_line']}) is in Pasal {r['pasal']} which has no annotation label")
        annotations.append({
            "type": "footnote", "n": r["n"], "kind": kind_by_pasal[r["pasal"]],
            "offset": starts[idxmap[r["out_index"]]] + r["col"],
            "address": _pasal_address(prefix, r["pasal"], r["ayat"], r["huruf"]),
            "definition": defs[r["n"]][0], "source_line": r["source_line"], "definition_line": defs[r["n"]][1],
        })

    # --- tanggal pengundangan (aturan status default)
    peng = next(s for s in sections if s["section"] == "pengesahan")
    ptext = clean_text[peng["start"] : peng["end"]].split("\n")
    pdate = None
    for j, t in enumerate(ptext):
        if t.startswith("Diundangkan"):
            nxt = next((x for x in ptext[j + 1 :] if x), "")
            dm2 = _DIUNDANGKAN_DATE.match(nxt)
            if dm2:
                try:
                    pdate = parse_id_date(*dm2.groups())
                except (KeyError, ValueError):
                    pdate = None
            break
    if pdate is None:
        raise CorpusError("R12", "the 'Diundangkan ... Pada Tanggal <tanggal>' lines in PENGESAHAN DAN PENGUNDANGAN were not found or not parseable")

    rel = entry["path"][5:] if entry["path"].startswith("data/") else entry["path"]
    return CorpusDoc(
        doc_id=entry["doc_id"], family=entry["family"], title=entry["title"], path=rel, sha256=sha,
        clean_sha256=hashlib.sha256(clean_text.encode("utf-8")).hexdigest(),
        loader_rules_version=cfg_all["loader_rules_version"], char_count=len(clean_text),
        tokens_local=None, tokens_endpoint=None, calibration_ratio=None,
        sections=sections, annotations=annotations, text=clean_text, line_map=line_map,
        metadata={
            "address_prefix": prefix, "pengundangan_date": pdate, "status_default": cfg_all["status_default"],
            "pasal_count": len(pasal_set), "pasal_start": pasal_start, "address_separator": SEP,
        },
    )
