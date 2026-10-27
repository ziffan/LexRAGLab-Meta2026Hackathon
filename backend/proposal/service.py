"""Layanan usulan peran D: W4 (`generate`) dan W5 (`decide`), penyimpanan `ProposalRecord`, `Item` baru.

Keputusan penyusun (scenarios/M2.1, A1-A31):
- Mesin status hanya `usulan -> disetujui | diubah | ditolak`; keputusan dicek ulang di bawah kunci (CAS) sehingga dua
  permintaan serentak hanya satu yang lolos (S15).
- `Item` tidak pernah lahir dari W4. Lahir di W5 (`disetujui`/`diubah`) ke berkas versi BARU `data/butir/<family>.v{N+1}.jsonl`
  (v1 milik operator tidak ditulis; versi baru tidak menimpa). Tulis `Item` lalu `ProposalRecord`; bila catatan gagal, berkas versi
  baru dihapus kembali (semua atau tidak sama sekali, S16).
- `ProposalRecord`: satu berkas JSON per usulan di `<runs_dir>/proposals/records/`. Indeks run per kunci cache D di
  `<runs_dir>/proposals/runs/` (kunci = hash dokumen, mode, prompt, skema, model, effort, batas; A28).
- Hash korpus untuk W5 dibaca dari RunRecord asal lewat `run_id` (A12 III).
- Seam uji (A27): `Hooks` (`after_read`, `before_item_write`, `before_record_write`, `before_w4_write`).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from backend import config
from backend.api.errors import ApiError
from backend.spark import BudgetExceeded, ConfigInvalid, SparkClient
from backend.spark.runrecord import utc_iso
from backend.spark.settings import effort_for
from backend.spark.store import canonical_json, sha256_hex

from . import prompt as promptmod
from .prompt import MODES, PROPOSAL_D_SCHEMA, SCHEMA_NAME, PromptD
from .span import span_in_bounds, validate_span

ROLE = "d"
DECISIONS = ("disetujui", "diubah", "ditolak")
BODY_KEYS = {"decision", "edited", "operator_note"}
EDITED_KEYS = {"query", "gold_spans", "mode"}
_ITEM_FILE = re.compile(r"^(\w+)\.v(\d+)\.jsonl$")
ITEM_KEYS = ("id", "family", "query", "doc_id", "gold_spans", "clean_sha256", "mode", "origin", "review_status", "proposal_id",
             "reference_date", "scene_checked", "operator_note", "created_at")
_MAP_ERR = {"timeout": (503, "model_unavailable"), "rate_limited": (503, "model_unavailable"),
            "model_unavailable": (503, "model_unavailable"), "replay_no_stored_run": (409, "replay_no_stored_run")}


@dataclass
class DocInfo:
    doc_id: str
    family: str
    text: str
    clean_sha256: str


@dataclass
class Hooks:
    """Seam uji (A27). Semua opsional; produksi tidak memakainya."""
    after_read: Callable[[], None] | None = None           # W5: sesudah baca status, sebelum kunci tulis
    before_item_write: Callable[[], None] | None = None    # W5: sebelum menulis berkas butir (tmp)
    before_item_commit: Callable[[], None] | None = None   # W5: sesudah catatan ditulis, sebelum rename butir
    before_record_write: Callable[[], None] | None = None  # W5: sebelum menulis ProposalRecord
    before_w4_write: Callable[[], None] | None = None      # W4: sesudah baca, sebelum menulis rekaman baru


def _call(h: Callable[[], None] | None) -> None:
    if h is not None:
        h()


def _retry(fn: Callable[[], None], tries: int = 6) -> None:
    """Retry singkat pada PermissionError Windows (G-34: berkas baru dikunci sesaat)."""
    for i in range(tries):
        try:
            return fn()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))


def _stage(path: Path, data: bytes) -> Path:
    """Tulis ke berkas .tmp (fsync) tanpa mengubah target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return tmp


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = _stage(path, data)
    try:
        _retry(lambda: os.replace(tmp, path))
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _dump(obj: Any, *, indent: int | None = None) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=indent) + "\n").encode("utf-8")


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


class ProposalService:
    def __init__(self, *, runs_dir: Path, butir_dir: Path, doc_provider: Callable[[str], DocInfo | None],
                 clock: Callable[[], float] = time.time, prompt_provider: Callable[[], PromptD] = promptmod.load_prompt,
                 count_tokens: Callable[[str], int] | None = None, max_proposals: int | None = None,
                 hooks: Hooks | None = None, config_dir: Path | None = None) -> None:
        self.runs_dir = Path(runs_dir)
        self.butir_dir = Path(butir_dir)
        self.doc_provider = doc_provider
        self.clock = clock
        self.prompt_provider = prompt_provider
        self.count_tokens = count_tokens or (lambda t: len(t) // 2 + 1)
        pcfg = config.load("proposals", config_dir)
        self.max_proposals = int(max_proposals if max_proposals is not None else pcfg["max_proposals_per_call"])
        self.context_lines = int(pcfg["context_lines"])
        self.hooks = hooks or Hooks()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ jalur
    @property
    def base(self) -> Path:
        return self.runs_dir / "proposals"

    @property
    def records_dir(self) -> Path:
        return self.base / "records"

    @property
    def index_dir(self) -> Path:
        return self.base / "runs"

    def _now(self) -> str:
        return utc_iso(self.clock())

    # --------------------------------------------------------------- baca/tulis
    def get(self, proposal_id: str) -> dict[str, Any] | None:
        if not isinstance(proposal_id, str) or not re.fullmatch(r"[0-9a-f]{16}", proposal_id):
            return None
        with self._lock:
            try:
                return json.loads((self.records_dir / f"{proposal_id}.json").read_bytes().decode("utf-8"))
            except (OSError, ValueError):
                return None

    def _put(self, rec: dict[str, Any]) -> None:
        _write_atomic(self.records_dir / f"{rec['proposal_id']}.json", _dump(rec, indent=1))

    def _index(self, d_key: str) -> dict[str, Any] | None:
        with self._lock:
            try:
                return json.loads((self.index_dir / f"{d_key}.json").read_bytes().decode("utf-8"))
            except (OSError, ValueError):
                return None

    def _runs(self) -> list[dict[str, Any]]:
        out = []
        with self._lock:
            for p in sorted(self.index_dir.glob("*.json")) if self.index_dir.is_dir() else []:
                try:
                    out.append(json.loads(p.read_bytes().decode("utf-8")))
                except (OSError, ValueError):
                    continue
        return sorted(out, key=lambda x: (x["run"]["created_at"], x["d_key"]))

    def _run_by_id(self, run_id: str) -> dict[str, Any] | None:
        return next((r["run"] for r in self._runs() if r["run"]["run_id"] == run_id), None)

    def list_proposals(self, family: str | None = None) -> list[dict[str, Any]]:
        """Semua `ProposalRecord`, urut run lalu urutan keluaran. Catatan yang hilang dilewati."""
        out = []
        for r in self._runs():
            if family is not None and r.get("family") != family:
                continue
            for pid in r["proposal_ids"]:
                rec = self.get(pid)
                if rec is not None:
                    out.append(rec)
        return out

    # ---------------------------------------------------------------------- W4
    def generate(self, family: str, doc_id: Any, modes: Any, *, profile: str, model_config: Mapping[str, Any],
                 client_factory: Callable[[], SparkClient], replay: bool = False) -> dict[str, Any]:
        if (not isinstance(modes, list) or not modes or any(not isinstance(m, str) for m in modes)
                or any(m not in MODES for m in modes)):
            raise ApiError(400, "invalid_request", f"modes must be a non-empty list drawn from {list(MODES)}.")
        modes = list(dict.fromkeys(modes))
        if not isinstance(doc_id, str):
            raise ApiError(400, "invalid_request", "doc_id must be a string.")
        doc = self.doc_provider(doc_id)
        if doc is None or doc.family != family:
            raise ApiError(404, "not_found", f"Unknown doc_id {doc_id[:60]!r}.")
        prof = (model_config.get("profiles") or {}).get(profile) or {}
        try:
            effort = effort_for(model_config, ROLE)
        except ConfigInvalid as exc:
            raise ApiError(503, "model_unavailable", str(exc)[:300]) from None
        prm = self.prompt_provider()
        promptmod.validate_schema()
        sch = promptmod.schema_hash()
        keys = {m: sha256_hex(canonical_json([ROLE, prof.get("provider"), prof.get("model"), effort, prm.prompt_hash, sch,
                                              doc.clean_sha256, doc.doc_id, m, self.max_proposals])) for m in modes}
        hits = {m: self._index(keys[m]) for m in modes}
        misses = [m for m in modes if hits[m] is None]
        if replay and misses:
            raise ApiError(409, "replay_no_stored_run", "No stored run for this request. Replay mode does not call the Model API.")
        calls: dict[str, dict[str, Any]] = {}
        client: SparkClient | None = None
        try:
            if misses:
                client = client_factory()
            for m in misses:
                text = promptmod.render_input(prm, doc.doc_id, doc.text, m, self.max_proposals, doc.clean_sha256)
                calls[m] = dict(role=ROLE, prompt_version=prm.version, prompt_hash=prm.prompt_hash, input=text,
                                schema=PROPOSAL_D_SCHEMA, schema_name=SCHEMA_NAME, schema_hash=sch,
                                prompt_cache_key=prm.prompt_cache_key, max_output_tokens=prm.max_output_tokens,
                                est_input=int(self.count_tokens(text)),
                                meta={"clean_sha256": doc.clean_sha256, "corpus_hash": doc.clean_sha256})
            if misses:
                proj = client.project_batch([calls[m] for m in misses])  # type: ignore[union-attr]
                if proj.verdict != "ok":
                    raise BudgetExceeded(proj.reason)
        except BudgetExceeded as exc:
            raise ApiError(402, "budget_exceeded", str(exc)[:300]) from None
        except ConfigInvalid as exc:
            raise ApiError(503, "model_unavailable", str(exc)[:300]) from None
        runs: list[dict[str, Any]] = []
        for m in modes:
            idx = hits[m]
            if idx is not None:
                run = dict(idx["run"])
                run["status"] = "replay" if replay else "cached"
                runs.append(run)
                continue
            try:
                res = client.call(**calls[m])  # type: ignore[union-attr]
            except BudgetExceeded as exc:
                raise ApiError(402, "budget_exceeded", str(exc)[:300]) from None
            except ConfigInvalid as exc:
                raise ApiError(503, "model_unavailable", str(exc)[:300]) from None
            if res.output is None:
                err = res.record.error or {"code": "model_error", "message": "call failed"}
                status, code = _MAP_ERR.get(err["code"], (502, "model_error"))
                raise ApiError(status, code, f"{m}: {err['message']}"[:300])
            runs.append(self._store_run(family, doc, m, keys[m], res.record.to_dict(), res.parsed))
        proposals: list[dict[str, Any]] = []  # dari disk: keputusan yang sudah ada tidak ter-reset
        for m in modes:
            idx = hits[m] or self._index(keys[m])
            for pid in idx["proposal_ids"] if idx else []:
                rec = self.get(pid)
                if rec is not None:
                    proposals.append(rec)
        return {"proposals": proposals, "runs": runs}

    def _store_run(self, family: str, doc: DocInfo, mode: str, d_key: str, run: dict[str, Any],
                   out: Mapping[str, Any]) -> dict[str, Any]:
        kept = [u for u in out.get("usulan", []) if u.get("doc_id") == doc.doc_id and u.get("mode") == mode]  # A5
        kept = kept[: self.max_proposals]  # A6: sesudah pembuangan
        recs = []
        for i, u in enumerate(kept):
            chk = validate_span(doc.text, u["teks_gold"], u["start"], u["end"])
            recs.append({"proposal_id": sha256_hex(canonical_json([d_key, i]))[:16], "family": family, "body": dict(u),
                         "resolved_span": chk.resolved_span,
                         "validation": {"offset_found": chk.offset_found, "text_matches": chk.text_matches},
                         "review_status": "usulan", "edited": None, "operator_note": None, "reviewed_at": None,
                         "item_id": None, "run_id": run["run_id"]})
        try:
            _call(self.hooks.before_w4_write)
            with self._lock:
                for r in recs:  # hanya membuat yang belum ada: keputusan tersimpan tidak tertimpa (S15 d)
                    if not (self.records_dir / f"{r['proposal_id']}.json").exists():
                        self._put(r)
                _write_atomic(self.index_dir / f"{d_key}.json",
                              _dump({"d_key": d_key, "family": family, "doc_id": doc.doc_id, "mode": mode, "run": run,
                                     "proposal_ids": [r["proposal_id"] for r in recs]}, indent=1))
        except ApiError:
            raise
        except Exception:  # noqa: BLE001
            raise ApiError(500, "storage_error", "Could not save the proposals.") from None
        return run

    # ---------------------------------------------------------------------- W5
    def decide(self, proposal_id: str, body: Any) -> dict[str, Any]:
        self._plan(proposal_id, body)  # baca dan putuskan tanpa menulis; galat menurut prioritas A26
        _call(self.hooks.after_read)
        with self._lock:
            rec, decision, edited, note, draft = self._plan(proposal_id, body)  # cek ulang di bawah kunci (CAS)
            now = self._now()
            item = {**draft, "operator_note": note, "created_at": now} if draft is not None else None
            new = {**rec, "review_status": decision, "edited": edited, "operator_note": note, "reviewed_at": now,
                   "item_id": item["id"] if item else None}
            staged: tuple[Path, Path] | None = None
            old_bytes = (self.records_dir / f"{proposal_id}.json").read_bytes()
            wrote = False
            try:
                if item is not None:
                    _call(self.hooks.before_item_write)
                    staged = self._stage_item(item)
                _call(self.hooks.before_record_write)
                self._put(new)
                wrote = True
                if staged is not None:
                    _call(self.hooks.before_item_commit)
                    _retry(lambda: os.replace(staged[0], staged[1]))
            except BaseException as exc:  # noqa: BLE001
                if staged is not None:
                    self._unlink(staged[0])
                if wrote:  # catatan sudah berubah tetapi butir gagal: pulihkan catatan lama
                    _write_atomic(self.records_dir / f"{proposal_id}.json", old_bytes)
                if isinstance(exc, ApiError):
                    raise
                raise ApiError(500, "storage_error", "Could not save decision. Nothing was changed.") from None
            return {"proposal": new, "item": item}

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass

    def _plan(self, proposal_id: str, body: Any) -> tuple[dict[str, Any], str, Any, Any, dict[str, Any] | None]:
        """Prioritas galat A26: 404, 400/422 bentuk badan, 409 transisi, 409 hash, 422 isi dan gerbang span."""
        rec = self.get(proposal_id)
        if rec is None:
            raise ApiError(404, "not_found", "Unknown proposal_id.")
        if not isinstance(body, dict):
            raise ApiError(400, "invalid_request", "Request body must be a JSON object.")
        decision = body.get("decision")
        if not isinstance(decision, str) or decision not in DECISIONS:
            raise ApiError(400, "invalid_request", f"decision must be one of {list(DECISIONS)}.")
        if set(body) - BODY_KEYS:
            raise ApiError(422, "validation_failed", "Unknown field in request body.")
        note = body.get("operator_note")
        if note is not None and not isinstance(note, str):
            raise ApiError(422, "validation_failed", "operator_note must be a string or null.")
        edited = body.get("edited")
        if edited is not None and not isinstance(edited, dict):
            raise ApiError(422, "validation_failed", "edited must be an object or null.")
        if rec["review_status"] != "usulan":
            raise ApiError(409, "invalid_transition", "Only proposals in status 'usulan' can be decided.")
        if decision == "ditolak":
            if edited is not None:
                raise ApiError(422, "validation_failed", "edited is only allowed with decision 'diubah'.")
            return rec, decision, None, note, None
        doc = self.doc_provider(rec["body"]["doc_id"])
        run = self._run_by_id(rec["run_id"])
        if doc is None or run is None or run.get("clean_sha256") != doc.clean_sha256:
            raise ApiError(409, "hash_mismatch", "The document text changed since this proposal was made.")
        b = rec["body"]
        if decision == "disetujui":
            if edited is not None:
                raise ApiError(422, "validation_failed", "edited is only allowed with decision 'diubah'.")
            if not rec["validation"]["text_matches"] or rec["resolved_span"] is None:
                raise ApiError(422, "validation_failed", "This proposal failed span validation; edit it or reject it.")
            spans = [dict(rec["resolved_span"])]
            return rec, decision, None, note, self._draft(rec, doc, decision, b["query"], b["mode"], spans)
        spans = self._check_edited(edited, doc)
        assert edited is not None
        return rec, decision, edited, note, self._draft(rec, doc, decision, edited["query"], edited["mode"], spans)

    @staticmethod
    def _check_edited(edited: Any, doc: DocInfo) -> list[dict[str, int]]:
        bad = ApiError(422, "validation_failed", "edited is not valid.")
        if not isinstance(edited, dict) or set(edited) != EDITED_KEYS:
            raise bad
        q, mode, spans = edited["query"], edited["mode"], edited["gold_spans"]
        if not isinstance(q, str) or not q.strip() or not isinstance(mode, str) or mode not in MODES:
            raise bad
        if not isinstance(spans, list) or not spans:
            raise bad
        out = []
        for s in spans:
            if not isinstance(s, dict) or set(s) != {"start", "end"} or not (_is_int(s["start"]) and _is_int(s["end"])):
                raise bad
            if not span_in_bounds(doc.text, s["start"], s["end"]):
                raise bad
            out.append({"start": s["start"], "end": s["end"]})
        return out

    @staticmethod
    def _draft(rec: dict[str, Any], doc: DocInfo, decision: str, query: str, mode: str,
               spans: list[dict[str, int]]) -> dict[str, Any]:
        return {"id": f"usulan-{rec['proposal_id']}", "family": rec["family"], "query": query, "doc_id": doc.doc_id,
                "gold_spans": spans, "clean_sha256": doc.clean_sha256, "mode": mode, "origin": "spark_disetujui",
                "review_status": decision, "proposal_id": rec["proposal_id"], "reference_date": None,
                "scene_checked": False}

    # --------------------------------------------------------------- berkas butir
    def _item_files(self, family: str) -> list[tuple[int, Path]]:
        if not self.butir_dir.is_dir():
            return []
        return sorted((int(m.group(2)), p) for p in self.butir_dir.glob(f"{family}.v*.jsonl")
                      if (m := _ITEM_FILE.match(p.name)))

    def items(self, family: str) -> list[dict[str, Any]]:
        """Butir versi terbaru (baca saja), sama dengan pemuat grid."""
        files = self._item_files(family)
        if not files:
            return []
        text = files[-1][1].read_bytes().decode("utf-8")
        return [json.loads(ln) for ln in text.split("\n") if ln.strip()]

    def _stage_item(self, item: dict[str, Any]) -> tuple[Path, Path]:
        """Berkas versi BARU = isi versi terbaru (byte persis) + satu baris. Versi lama tidak disentuh; v1 tidak ditulis."""
        family = item["family"]
        files = self._item_files(family)
        prev = files[-1][1].read_bytes() if files else b""
        if b"\r" in prev:
            raise OSError("item file contains CR")
        if prev and not prev.endswith(b"\n"):
            prev += b"\n"
        if any(i.get("id") == item["id"] for i in self.items(family)):
            raise ApiError(409, "invalid_transition", "Item already exists.")
        path = self.butir_dir / f"{family}.v{(files[-1][0] + 1) if files else 2}.jsonl"
        if path.exists():
            raise OSError("item file version exists")
        if set(item) != set(ITEM_KEYS):
            raise OSError("item has unexpected keys")
        return _stage(path, prev + _dump(item)), path
