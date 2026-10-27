"""Perlengkapan uji M2.1 (docs/scenarios/M2.1.md "Fixture bersama"). Data sintetis; klien Spark palsu (transport palsu di bawah
SDK), jam suntikan, direktori sementara. Tanpa jaringan, tanpa Model API, tanpa tulisan ke `data/butir/` repo."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.api.app import Service, create_app
from backend.proposal.service import DocInfo, Hooks, ProposalService

from .spark_fakes import Clock, FakeTransport, Resp, body_ok, budget_cfg, env_ok, model_cfg

DX_TEXT = ("\U0001F600 Pasal 1\n(1) Aaa bbb ccc.\n(2) Ddd eee fff.\nPasal 2\n(1) Aaa bbb ccc.\n(2) Ggg hhh iii.\n")
assert len(DX_TEXT) == 86
T0 = datetime(2026, 10, 29, 10, 0, 0, tzinfo=timezone.utc).timestamp()


def at(hh: int, mm: int, ss: int = 0) -> float:
    return datetime(2026, 10, 29, hh, mm, ss, tzinfo=timezone.utc).timestamp()


def _u(query: str, mode: str, teks: str, s: int | None, e: int | None, doc: str = "doc-x") -> dict[str, Any]:
    return {"query": query, "mode": mode, "doc_id": doc, "teks_gold": teks, "start": s, "end": e}


T22 = "(2) Ddd eee fff."
T11 = "(1) Aaa bbb ccc."
T25 = "(2) Ggg hhh iii."
LIT = {  # urutan keluaran mentah: L1, L6, L2, L3, L4, L5, L7
    "L1": _u("QL1", "literal", T22, 27, 43), "L6": _u("QL6", "literal", T22, 27, 43, "doc-y"),
    "L2": _u("QL2", "literal", T11, None, None), "L3": _u("QL3", "literal", T25, 69, 84),
    "L4": _u("QL4", "literal", "(3) Zzz yyy.", None, None), "L5": _u("QL5", "literal", T25, 80, 95),
    "L7": _u("QL7", "parafrase", T22, 27, 43),
}
LIT_ORDER = ["L1", "L6", "L2", "L3", "L4", "L5", "L7"]
PAR = {
    "PA1": _u("QP1", "parafrase", T11 + "\n" + T22, None, None), "PA2": _u("QP2", "parafrase", T22, 28, 44),
    "PA3": _u("QP3", "parafrase", "(2) ddd eee fff.", None, None), "PA4": _u("QP4", "parafrase", "", None, None),
    "PA5": _u("QP5", "parafrase", T22, 27, None), "PA6": _u("Ddd eee fff?", "parafrase", T22, 27, 43),
    "PA7": _u("QP7", "parafrase", T22, 30, 30), "PA8": _u("QP8", "parafrase", T22, 43, 27),
}
PAR_ORDER = ["PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PA8"]
# Kuncinya: nama fixture -> (indeks keluaran yang tersimpan, mode). Urutan tersimpan literal: L1 L2 L3 L4 L5 lalu PA1..PA8.
STORED_LIT = ["L1", "L2", "L3", "L4", "L5"]
EXPECT = {  # offset_found, text_matches, resolved_span
    "L1": (True, True, {"start": 27, "end": 43}), "L2": (False, False, None), "L3": (True, False, {"start": 69, "end": 84}),
    "L4": (False, False, None), "L5": (False, False, None),
    "PA1": (True, True, {"start": 10, "end": 43}), "PA2": (True, False, {"start": 28, "end": 44}),
    "PA3": (False, False, None), "PA4": (False, False, None), "PA5": (True, True, {"start": 27, "end": 43}),
    "PA6": (True, True, {"start": 27, "end": 43}), "PA7": (False, False, None), "PA8": (False, False, None),
}


def valid_edit(query: str = "QE", spans: list[tuple[int, int]] | None = None, mode: str = "literal") -> dict[str, Any]:
    return {"query": query, "gold_spans": [{"start": s, "end": e} for s, e in (spans or [(27, 43)])], "mode": mode}


def run_responder(lit: list[dict] | None = None, par: list[dict] | None = None):
    """Balasan terskrip menurut `MODE:` di akhir masukan."""
    lit_out = {"usulan": lit if lit is not None else [LIT[k] for k in LIT_ORDER]}
    par_out = {"usulan": par if par is not None else [PAR[k] for k in PAR_ORDER]}

    def respond(_tr: FakeTransport, request: Any) -> Resp:
        body = json.loads(request.content.decode("utf-8"))
        text = body["input"]
        out = par_out if "\nMODE: parafrase\n" in text else lit_out
        return Resp(200, body_ok(out))

    return respond


class Env:
    """Satu aplikasi uji: klien HTTP, layanan usulan, transport palsu, jam, dokumen mutable, direktori sementara."""

    def __init__(self, tmp_path: Path, *, max_proposals: int = 20, budget: dict | None = None, default: Any = None,
                 script: list[Any] | None = None, with_v1: bool = True, replay: bool = False, hooks: Hooks | None = None,
                 doc_text: str = DX_TEXT, doc_id: str = "doc-x", sha: str = "hx1") -> None:
        self.tmp = tmp_path
        self.runs = tmp_path / "runs"
        self.butir = tmp_path / "butir"
        self.butir.mkdir(parents=True, exist_ok=True)
        self.v1_bytes = b""
        if with_v1:
            ops = [{"id": f"OP{i}", "family": "uupt", "query": f"op{i}", "doc_id": "doc-x", "gold_spans": [{"start": 0, "end": 1}],
                    "clean_sha256": "hx1", "mode": "literal", "origin": "operator", "review_status": None, "proposal_id": None,
                    "reference_date": None, "scene_checked": False, "operator_note": None, "created_at": "2026-10-27T03:18:10Z"}
                   for i in (1, 2)]
            self.v1_bytes = ("".join(json.dumps(o, sort_keys=True, ensure_ascii=False) + "\n" for o in ops)).encode("utf-8")
            (self.butir / "uupt.v1.jsonl").write_bytes(self.v1_bytes)
        self.epoch = T0
        self.docs = {doc_id: DocInfo(doc_id, "uupt", doc_text, sha)}
        self.clock = Clock()
        self.tr = FakeTransport(self.clock, script, default if default is not None else run_responder())
        self.model = model_cfg()
        self.budget = budget or budget_cfg()
        self.prompt_override = None
        self.hooks = hooks or Hooks()
        svc = Service(runs_dir=self.runs, butir_dir=self.butir)
        self.app = create_app(svc, env=env_ok(), model_config=self.model, budget_config=self.budget, replay=replay,
                              spark_transport=self.tr.transport)
        from backend.proposal import prompt as pm
        self.ps = ProposalService(runs_dir=self.runs, butir_dir=self.butir, doc_provider=lambda d: self.docs.get(d),
                                  clock=lambda: self.epoch, prompt_provider=lambda: self.prompt_override or pm.load_prompt(),
                                  count_tokens=lambda t: len(t) // 3 + 1, max_proposals=max_proposals, hooks=self.hooks)
        self.app.state.proposals = self.ps
        self.http = TestClient(self.app, raise_server_exceptions=False)

    # --- W4 / W5
    def gen(self, modes: Any = ("literal", "parafrase"), doc_id: str = "doc-x", **raw: Any):
        body = {"doc_id": doc_id, "modes": list(modes) if isinstance(modes, tuple) else modes}
        body.update(raw)
        return self.http.post("/api/families/uupt/proposals/generate", json=body)

    def gen_ok(self, modes: Any = ("literal", "parafrase"), doc_id: str = "doc-x") -> dict[str, Any]:
        r = self.gen(modes, doc_id=doc_id)
        assert r.status_code == 200, r.text
        return r.json()

    def decide(self, pid: str, body: Any):
        return self.http.post(f"/api/proposals/{pid}/decision", json=body)

    def by_key(self, resp: dict[str, Any]) -> dict[str, str]:
        """Peta nama fixture -> proposal_id dari respons W4 (menurut query unik)."""
        keys = {v["query"]: k for k, v in {**LIT, **PAR}.items() if k != "L6" and k != "L7"}
        return {keys[p["body"]["query"]]: p["proposal_id"] for p in resp["proposals"]}

    def items_on_disk(self) -> list[dict[str, Any]]:
        files = sorted(self.butir.glob("uupt.v*.jsonl"), key=lambda p: int(p.name.split(".v")[1].split(".")[0]))
        if not files:
            return []
        return [json.loads(x) for x in files[-1].read_bytes().decode("utf-8").split("\n") if x.strip()]

    def spark_items(self) -> list[dict[str, Any]]:
        return [i for i in self.items_on_disk() if i["origin"] == "spark_disetujui"]

    def record_bytes(self, pid: str) -> bytes:
        return (self.ps.records_dir / f"{pid}.json").read_bytes()

    def butir_snapshot(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.butir.glob("*"))}
