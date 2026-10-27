// W54 SU19 (scenarios/M2.1-unanswerable.md; H-087, H-092): kartu usulan `unanswerable` di U6. API palsu, tanpa DOM.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProposalCard, ReviewCounters, ReviewList } from "../components/Review";
import { ReviewController, canApprove, mustRefuseCounts, mustRefuseLabel, type FetchLike, type ProposalRecord } from "../lib/review";
import { modeLabel } from "../lib/labels";

const ac = (status: "ok" | "doubtful", reasons: string[], hash = "h1") => ({
  status, reasons, max_cov: { num: 1, den: 2 }, max_cosine: 0.4, config_hash: hash,
  top_k: [
    { source: "bm25" as const, rank: 1, unit_text: "Pasal 5 Komisaris diangkat RUPS." },
    { source: "dense" as const, rank: 1, unit_text: "Pasal 7 Direksi mengurus Perseroan." },
  ],
});
const U = (id: string, q: string, status: ProposalRecord["review_status"], check: ReturnType<typeof ac>, over: Partial<ProposalRecord> = {}): ProposalRecord => ({
  proposal_id: id, family: "akta",
  body: { query: q, mode: "unanswerable", doc_id: "akta-x", alasan_kode: "data_tidak_dimuat", alasan_teks: "Alamat tidak dimuat." },
  resolved_span: null, validation: null, absence_check: check, duplicate_of: null,
  review_status: status, edited: null, operator_note: null, reviewed_at: null, item_id: null, run_id: "r1", ...over,
});
const P1 = U("P1", "Di mana alamat Perseroan?", "usulan", ac("doubtful", ["lexical_overlap"]));
const P2 = U("P2", "Siapa komisaris?", "usulan", ac("ok", []));
const P3 = U("P3", "Berapa gaji?", "ditolak", ac("doubtful", ["dense_similar"]));
const P4 = U("P4", "Kapan RUPS?", "disetujui", ac("ok", []));
const LIT: ProposalRecord = {
  proposal_id: "LIT", family: "akta", body: { query: "QLIT", mode: "literal", doc_id: "akta-x", teks_gold: "Pasal 1", start: null, end: null },
  resolved_span: { start: 0, end: 7 }, validation: { offset_found: true, text_matches: true },
  review_status: "usulan", edited: null, operator_note: null, reviewed_at: null, item_id: null, run_id: "r1",
};
const DOC = "Pasal 1 Nama\nPasal 2 Modal\n";

function rig(proposals: ProposalRecord[], extra: Record<string, unknown> = {}) {
  const calls: { url: string; method: string; body: any }[] = [];
  const fetchFn: FetchLike = async (url, init) => {
    const method = init?.method ?? "GET";
    if (method === "GET" && url.endsWith("/proposals")) return new Response(JSON.stringify({ proposals, context_lines: 1, ...extra }), { status: 200 });
    if (method === "GET") return new Response(JSON.stringify({ text: DOC }), { status: 200 });
    calls.push({ url, method, body: JSON.parse(String(init?.body ?? "null")) });
    return new Response(JSON.stringify({ proposal: {}, item: null }), { status: 200 });
  };
  return { ctl: new ReviewController(fetchFn, "akta"), calls };
}

const card = (p: ProposalRecord, over: Record<string, unknown> = {}) => {
  const noop = () => undefined;
  return {
    proposal: p, context: null, docText: DOC, busy: false, confirming: false, editing: false, edit: null, note: "", error: "",
    actions: { approve: noop, edit: noop, reject: noop, confirmReject: noop, cancelReject: noop, setNote: noop, setEdit: noop, addSelection: noop, removeSpan: noop, submitEdit: noop, closeEdit: noop, key: noop },
    ...over,
  };
};

describe("SU19 U6 unanswerable", () => {
  it("card P1: mode, query, Reason map, Doubtful badge, Why flagged, Closest passages; no span rows", () => {
    const h = renderToStaticMarkup(<ProposalCard {...card(P1)} />);
    expect(h).toContain("Unanswerable");
    expect(h).toContain("Di mana alamat Perseroan?");
    expect(h).toContain("Reason");
    expect(h).toContain("Data not included");
    expect(h).toContain("Alamat tidak dimuat.");
    expect(h).toContain("Doubtful");
    expect(h).toContain("Why flagged: Shares distinctive terms with the deed");
    expect(h).toContain("Closest passages");
    expect(h).toContain("Pasal 5 Komisaris diangkat RUPS.");
    expect(h).toContain("BM25 #1");
    expect(h).toContain("Dense #1");
    expect(h).not.toContain("<mark>");
    expect(h).not.toContain("Offset found");
    expect(h).not.toContain("Text matches");
    expect(h).not.toContain("could not be validated");
  });

  it("Approve, Edit, Reject stay enabled although doubtful", () => {
    const h = renderToStaticMarkup(<ProposalCard {...card(P1)} />);
    expect(canApprove(P1)).toBe(true);
    for (const b of ["Approve", "Edit", "Reject"]) expect(h).toMatch(new RegExp(`<button(?![^>]*\\sdisabled="")[^>]*>${b}</button>`));
  });

  it("reason and flag maps", () => {
    const m = (k: string, r: string[]) => renderToStaticMarkup(<ProposalCard {...card(U("X", "q", "usulan", ac("doubtful", r), { body: { ...P1.body, alasan_kode: k } }))} />);
    expect(m("di_luar_akta", ["dense_similar"])).toContain("Outside the deed");
    expect(m("di_luar_akta", ["dense_similar"])).toContain("Semantically close passage");
    expect(m("rincian_tidak_diatur", ["no_distinctive_terms"])).toContain("Detail not regulated");
    expect(m("rincian_tidak_diatur", ["no_distinctive_terms"])).toContain("No distinctive terms");
    expect(m("rincian_tidak_diatur", ["dense_unavailable"])).toContain("Semantic check unavailable");
  });

  it("P2 (ok) has no Doubtful badge; literal card keeps span and validation", () => {
    const h = renderToStaticMarkup(<ProposalCard {...card(P2)} />);
    expect(h).not.toContain("Doubtful");
    expect(h).not.toContain("Why flagged");
    const l = renderToStaticMarkup(<ProposalCard {...card(LIT, { context: { text: "Pasal 1", hlStart: 0, hlEnd: 7, ctxStart: 0, ctxEnd: 7 } })} />);
    expect(l).toContain("<mark>Pasal 1</mark>");
    expect(l).toContain("Offset found");
    expect(l).not.toContain("Closest passages");
  });

  it("badges: Duplicate (P14) and Check settings changed (SU9)", () => {
    const d = U("D", "q", "usulan", ac("ok", []), { duplicate_of: "P4" });
    expect(renderToStaticMarkup(<ProposalCard {...card(d)} />)).toContain("Duplicate of an existing proposal");
    expect(renderToStaticMarkup(<ProposalCard {...card(P2)} />)).not.toContain("Duplicate of an existing proposal");
    expect(renderToStaticMarkup(<ProposalCard {...card(P2, { checkConfigHash: "h1" })} />)).not.toContain("Check settings changed");
    expect(renderToStaticMarkup(<ProposalCard {...card(P2, { checkConfigHash: "h2" })} />)).toContain("Check settings changed");
    expect(renderToStaticMarkup(<ProposalCard {...card(P2)} />)).not.toContain("Check settings changed");
  });

  it("queue = usulan only (3 pending); must-refuse approved counts disetujui/diubah only (1)", async () => {
    const { ctl } = rig([P1, P2, P3, P4, LIT], { check_config_hash: "h1" });
    await ctl.load();
    const s = ctl.getState();
    expect(s.proposals.map((p) => p.proposal_id)).toEqual(["P1", "P2", "LIT"]);
    const c = mustRefuseCounts(s.all);
    expect(c.total).toBe(1);
    expect(c.perDoc).toEqual({ "akta-x": 1 });
    const h = renderToStaticMarkup(<ReviewCounters state={s} />);
    expect(h).toContain("Pending 3");
    expect(h).toContain("Must-refuse approved: 1");
    expect(h).toContain("akta-x: 1 approved");
    const list = renderToStaticMarkup(<ReviewList state={s} ctl={ctl} />);
    expect(list).toContain("Pasal 5 Komisaris");
    expect(list).toContain("QLIT");
  });

  it("zero approved shows the informational line; per-deed target hint", async () => {
    expect(mustRefuseLabel(0)).toBe("No must-refuse item approved yet");
    const { ctl } = rig([P1, P3]);
    await ctl.load();
    const h = renderToStaticMarkup(<ReviewCounters state={ctl.getState()} />);
    expect(h).toContain("No must-refuse item approved yet");
    expect(h).toContain("Pending 1");
    expect(h).toContain("target: at least 1");
  });

  it("counters render nothing for a family without unanswerable records", async () => {
    const { ctl } = rig([LIT]);
    await ctl.load();
    expect(renderToStaticMarkup(<ReviewCounters state={ctl.getState()} />)).toBe("");
  });

  it("Approve sends disetujui without edited and updates counter locally", async () => {
    const { ctl, calls } = rig([P1, P4]);
    await ctl.load();
    expect(await ctl.approve("P1")).toBe(true);
    expect(calls[0]).toMatchObject({ url: "/api/proposals/P1/decision", body: { decision: "disetujui", edited: null } });
    expect(mustRefuseCounts(ctl.getState().all).total).toBe(2);
  });

  it("Edit is query-only and sends edited = {query, gold_spans: [], mode: tolak}", async () => {
    const { ctl, calls } = rig([P1]);
    await ctl.load();
    ctl.openEdit("P1");
    expect(ctl.getState().edit?.mode).toBe("tolak");
    const h = renderToStaticMarkup(<ProposalCard {...card(P1, { editing: true, edit: ctl.getState().edit })} />);
    expect(h).toContain('aria-label="Edit proposal"');
    expect(h).not.toContain("Add selection as span");
    expect(h).not.toContain("<select");
    expect(h).not.toContain('aria-label="Context"');
    ctl.setEdit({ query: "Alamat kantor?" });
    expect(await ctl.submitEdit()).toBe(true);
    expect(calls[0].body).toEqual({ decision: "diubah", edited: { query: "Alamat kantor?", gold_spans: [], mode: "tolak" }, operator_note: null });
  });

  it("Edit rejects an empty query locally", async () => {
    const { ctl, calls } = rig([P1]);
    await ctl.load();
    ctl.openEdit("P1");
    ctl.setEdit({ query: "  " });
    expect(await ctl.submitEdit()).toBe(false);
    expect(calls).toHaveLength(0);
    expect(ctl.getState().edit?.error).toBe("Enter a query.");
  });

  it("literal edit still requires a span and never offers the refuse mode", async () => {
    const { ctl } = rig([LIT]);
    await ctl.load();
    ctl.openEdit("LIT");
    expect(await ctl.submitEdit()).toBe(false);
    const h = renderToStaticMarkup(<ProposalCard {...card(LIT, { editing: true, edit: ctl.getState().edit })} />);
    expect(h).not.toContain("Unanswerable</option>");
    expect(h).not.toContain("Must refuse");
  });

  it("save error text is unchanged; labels", async () => {
    expect(modeLabel("tolak")).toBe("Must refuse");
    expect(modeLabel("unanswerable")).toBe("Unanswerable");
    const fetchFn: FetchLike = async (url, init) => {
      if ((init?.method ?? "GET") === "GET") return new Response(JSON.stringify(url.endsWith("/proposals") ? { proposals: [P1] } : { text: DOC }), { status: 200 });
      return new Response(JSON.stringify({ error: { message: "boom" } }), { status: 500 });
    };
    const ctl = new ReviewController(fetchFn, "akta");
    await ctl.load();
    await ctl.approve("P1");
    expect(ctl.getState().errors.P1).toBe("Could not save decision: boom. Nothing was changed.");
    expect(ctl.getState().proposals).toHaveLength(1);
  });
});
