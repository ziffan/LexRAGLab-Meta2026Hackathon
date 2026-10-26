"""Usulan baris status dari anotasi (DATA-CONTRACTS §2 "Usulan baris status", §5).

Hanya USULAN: bukan tabel status dan tidak ditulis ke data/status/ (H-009). Milik operator.
"""

from __future__ import annotations

from typing import Any

from backend import config

from .loader import SEP, CorpusDoc


def propose_status_rows(doc: CorpusDoc) -> dict[str, Any]:
    prefix = doc.metadata["address_prefix"]
    fm = next(a for a in doc.annotations if a["type"] == "frontmatter")
    src = fm["sources"]
    cfg = config.load("corpus")["loader_uupt"]
    base = {"proposed_by": "loader", "approved_by_operator": False}
    entries: list[dict[str, Any]] = []

    perppu = src["perppu"]
    for kind, plist in (("Perubahan", perppu["changed"]), ("Penyisipan", perppu["inserted"])):
        for p in plist:
            entries.append({
                "doc_id": doc.doc_id, "address": f"{prefix}{SEP}Pasal {p}",
                "amended_by": [perppu["label"]], "interpreted_by": [],
                "effective_from": perppu["effective_from"], "status": "berlaku",
                "note": f"{kind} Pasal {p} oleh {perppu['label']}",
                "source": f"frontmatter konsolidasi_dalam_satu_naskah_berdasarkan[0] (sha256 berkas {doc.sha256})",
                **base,
            })

    for fn in (a for a in doc.annotations if a["type"] == "footnote"):
        if fn["kind"] == "mk":
            entries.append({
                "doc_id": doc.doc_id, "address": fn["address"],
                "amended_by": [], "interpreted_by": [src["mk"]["number"]],
                "effective_from": src["mk"]["decision_date"], "status": "berlaku_bersyarat",
                "note": fn["definition"],
                "source": f"Putusan MK {src['mk']['number']}, footnote [^{fn['n']}] (sha256 berkas {doc.sha256})",
                **base,
            })
        else:
            ref = f"{cfg['uu_pengubah_label']} {cfg['uu_pengubah_article']}"
            defn = fn["definition"]
            if defn.startswith(cfg["uu_pengubah_article"]) and ": " in defn:
                defn = defn.split(": ", 1)[1]  # hindari "Pasal 67" ganda
            entries.append({
                "doc_id": doc.doc_id, "address": fn["address"],
                "amended_by": [], "interpreted_by": [],
                "effective_from": src["uu_pengubah"]["effective_from"], "status": "berlaku",
                "note": f"{ref}: {defn}",
                "source": f"{ref}, footnote [^{fn['n']}] (sha256 berkas {doc.sha256})",
                **base,
            })

    sd = doc.metadata["status_default"]
    return {
        "doc_id": doc.doc_id,
        "source": f"{doc.path} sha256 {doc.sha256}; clean_sha256 {doc.clean_sha256}; loader_rules_version {doc.loader_rules_version}",
        "default_rule": {"status": sd["status"], "effective_from": doc.metadata["pengundangan_date"]},
        "entries": entries,
        **base,
    }
