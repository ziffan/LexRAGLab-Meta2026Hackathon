// W84 SV16 (scenarios/M2.1-unanswerable-uupt.md; H-095, H-099 V3/Q4): U6 untuk keluarga `uupt`. API palsu, tanpa DOM.
// Fixture "UU Mainan" sintetis (bukan UU 40/2007); bukan butir evaluasi.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProposalCard, ReviewCounters, ReviewList } from "../components/Review";
import { ReviewController, alasanLabel, canApprove, flagLabel, mustRefuseCounts, type FetchLike, type ProposalRecord } from "../lib/review";

const S4 = "Pasal 4 Dewan Komisaris melakukan pengawasan atas Direksi.";
const S1 = "Pasal 1 (1) Perseroan adalah badan hukum.\n(2) Badan hukum didirikan berdasarkan perjanjian.";
const ac = (status: "ok" | "doubtful", reasons: string[], num: number, den: number) => ({
  status, reasons, max_cov: { num, den }, max_cosine: null, config_hash: "h1",
  top_k: [{ source: "bm25" as const, rank: 1, unit_text: S4 }, { source: "bm25" as const, rank: 2, unit_text: S1 }],
});
const R = (id: string, family: string, q: string, kode: string, status: ProposalRecord["review_status"], check: ReturnType<typeof ac>): ProposalRecord => ({
  proposal_id: id, family,
  body: { query: q, mode: "unanswerable", doc_id: family === "uupt" ? "uupt-mainan" : "akta-x", alasan_kode: kode, alasan_teks: "t" },
  resolved_span: null, validation: null, absence_check: check, duplicate_of: null,
  review_status: status, edited: null, operator_note: null, reviewed_at: null, item_id: null, run_id: "r1",
});
const V1 = R("V1", "uupt", "Siapa auditor Perseroan?", "rincian_tidak_diatur", "usulan", ac("ok", [], 0, 1));
const V4 = R("V4", "uupt", "Apa itu Perseroan?", "di_luar_akta", "usulan", ac("doubtful", ["no_distinctive_terms"], 0, 0));
const V3 = R("V3", "uupt", "Siapa yang melakukan pengawasan atas Direksi?", "di_luar_akta", "ditolak", ac("doubtful", ["lexical_overlap"], 3, 3));
const T1 = R("T1", "uupt", "Berapa gaji anggota Direksi?", "rincian_tidak_diatur", "disetujui", ac("ok", [], 1, 3));
const V5 = R("V5", "uupt", "Berapa biaya pengesahan badan hukum Perseroan?", "rincian_tidak_diatur", "usulan", ac("doubtful", ["lexical_overlap"], 2, 4));
const LITU: ProposalRecord = {
  proposal_id: "LITU", family: "uupt", body: { query: "Siapa mengawasi Direksi?", mode: "literal", doc_id: "uupt-mainan", teks_gold: S4, start: null, end: null },
  resolved_span: { start: 0, end: 10 }, validation: { offset_found: true, text_matches: true },
  review_status: "usulan", edited: null, operator_note: null, reviewed_at: null, item_id: null, run_id: "r1",
};
// Rekaman akta yang disetujui: tidak boleh ikut penghitung uupt (penghitung per keluarga).
const AKTA_OK = R("A1", "akta", "Apa nomor NPWP?", "data_tidak_dimuat", "disetujui", ac("ok", [], 0, 3));
const DOC = `${S1}\n${S4}\n`;

function rig(byFamily: Record<string, ProposalRecord[]>, family: string) {
  const urls: string[] = [];
  const fetchFn: FetchLike = async (url, init) => {
    urls.push(url);
    if ((init?.method ?? "GET") === "GET") {
      const m = url.match(/\/api\/families\/([^/]+)\/proposals$/);
      if (m) return new Response(JSON.stringify({ proposals: byFamily[m[1]] ?? [], context_lines: 1, check_config_hash: "h1" }), { status: 200 });
      return new Response(JSON.stringify({ text: DOC }), { status: 200 });
    }
    return new Response(JSON.stringify({ proposal: {}, item: null }), { status: 200 });
  };
  return { ctl: new ReviewController(fetchFn, family), urls };
}

const card = (p: ProposalRecord) => {
  const noop = () => undefined;
  return {
    proposal: p, context: null, docText: DOC, busy: false, confirming: false, editing: false, edit: null, note: "", error: "",
    actions: { approve: noop, edit: noop, reject: noop, confirmReject: noop, cancelReject: noop, setNote: noop, setEdit: noop, addSelection: noop, removeSpan: noop, submitEdit: noop, closeEdit: noop, key: noop },
  };
};
const enabled = (h: string, b: string) => expect(h).toMatch(new RegExp(`<button(?![^>]*\\sdisabled="")[^>]*>${b}</button>`));

describe("SV16 U6 unanswerable for uupt", () => {
  it("Unanswerable mode is shown for uupt; V1/V4 cards like SU19 (no span highlight, actions enabled)", () => {
    for (const p of [V1, V4]) {
      const h = renderToStaticMarkup(<ProposalCard {...card(p)} />);
      expect(h).toContain(">Unanswerable</span>");
      expect(h).toContain(p.body.query);
      expect(h).not.toContain("<mark>");
      expect(h).not.toContain("Offset found");
      expect(canApprove(p)).toBe(true);
      for (const b of ["Approve", "Edit", "Reject"]) enabled(h, b);
    }
    const h4 = renderToStaticMarkup(<ProposalCard {...card(V4)} />);
    expect(h4).toContain("Doubtful");
    expect(h4).toContain("Why flagged: No distinctive terms");
    expect(renderToStaticMarkup(<ProposalCard {...card(V1)} />)).not.toContain("Doubtful");
  });

  it("Reason di_luar_akta reads 'Outside the statute' for uupt and stays 'Outside the deed' for akta", () => {
    const u = renderToStaticMarkup(<ProposalCard {...card(V4)} />);
    expect(u).toContain("Outside the statute");
    expect(u).not.toContain("deed");
    const a = renderToStaticMarkup(<ProposalCard {...card({ ...V4, family: "akta", body: { ...V4.body, doc_id: "akta-x" } })} />);
    expect(a).toContain("Outside the deed");
    expect(a).not.toContain("statute");
    expect(alasanLabel("di_luar_akta", "uupt")).toBe("Outside the statute");
    expect(alasanLabel("di_luar_akta", "akta")).toBe("Outside the deed");
    expect(alasanLabel("rincian_tidak_diatur", "uupt")).toBe("Detail not regulated");
    expect(alasanLabel("data_tidak_dimuat", "uupt")).toBe("Data not included");
  });

  it("lexical_overlap (V5 variant) reads '... with the statute' for uupt and '... with the deed' for akta", () => {
    const u = renderToStaticMarkup(<ProposalCard {...card(V5)} />);
    expect(u).toContain("Why flagged: Shares distinctive terms with the statute");
    expect(u).not.toContain("deed");
    const a = renderToStaticMarkup(<ProposalCard {...card({ ...V5, family: "akta", body: { ...V5.body, doc_id: "akta-x" } })} />);
    expect(a).toContain("Why flagged: Shares distinctive terms with the deed");
    expect(flagLabel("lexical_overlap", "uupt")).toBe("Shares distinctive terms with the statute");
    for (const f of ["dense_similar", "no_distinctive_terms", "dense_unavailable"]) expect(flagLabel(f, "uupt")).toBe(flagLabel(f, "akta"));
  });

  it("counters: Pending 3, Must-refuse approved: 1 (uupt only), closest passages show UU PT schema units", async () => {
    const { ctl, urls } = rig({ uupt: [V1, V4, V3, LITU, T1], akta: [AKTA_OK, { ...AKTA_OK, proposal_id: "A2" }] }, "uupt");
    await ctl.load();
    expect(urls[0]).toBe("/api/families/uupt/proposals");
    const s = ctl.getState();
    expect(s.proposals.map((p) => p.proposal_id)).toEqual(["V1", "V4", "LITU"]);
    expect(mustRefuseCounts(s.all)).toEqual({ total: 1, perDoc: { "uupt-mainan": 1 } });
    const h = renderToStaticMarkup(<ReviewCounters state={s} />);
    expect(h).toContain("Pending 3");
    expect(h).toContain("Must-refuse approved: 1");
    expect(h).toContain("uupt-mainan: 1 approved");
    expect(h).toContain('aria-label="Must-refuse approved per statute"');
    const ak = rig({ akta: [AKTA_OK] }, "akta");
    await ak.ctl.load();
    expect(renderToStaticMarkup(<ReviewCounters state={ak.ctl.getState()} />)).toContain('aria-label="Must-refuse approved per deed"');
    const list = renderToStaticMarkup(<ReviewList state={s} ctl={ctl} />);
    expect(list).toContain("Closest passages");
    expect(list).toContain(S4);
    expect(list).toContain("Siapa mengawasi Direksi?");
  });
});
