// W36 U6 pemilih keluarga: parse ?family=, muat ulang per keluarga, URL, tautan U0. Tanpa DOM.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReviewFamilyPicker } from "../components/Review";
import { FAMILY_LABELS } from "../components/Header";
import { ReviewController, parseReviewFamily, reviewHref, reviewSearch, type FetchLike, type ProposalRecord } from "../lib/review";

const prop = (fam: string, doc: string): ProposalRecord => ({
  proposal_id: `${fam}-1`, family: fam, body: { query: "q", mode: "literal", doc_id: doc, teks_gold: "x", start: null, end: null },
  resolved_span: { start: 0, end: 1 }, validation: { offset_found: true, text_matches: true },
  review_status: "usulan", edited: null, operator_note: null, reviewed_at: null, item_id: null, run_id: "r",
});

function rig() {
  const urls: string[] = [];
  const fetchFn: FetchLike = async (url) => {
    urls.push(url);
    if (url.endsWith("/proposals")) {
      const fam = url.split("/")[3];
      return new Response(JSON.stringify({ proposals: [prop(fam, fam === "akta" ? "akta-01" : "uupt-1")], pending: 1 }), { status: 200 });
    }
    return new Response(JSON.stringify({ text: "x" }), { status: 200 });
  };
  return { urls, fetchFn };
}

describe("U6 family", () => {
  it("defaults to uupt and falls back for unknown values", () => {
    expect(parseReviewFamily("")).toBe("uupt");
    expect(parseReviewFamily("?family=zzz")).toBe("uupt");
    expect(parseReviewFamily("?family=akta")).toBe("akta");
    expect(parseReviewFamily("?family=uupt")).toBe("uupt");
  });

  it("loads akta proposals and the akta doc", async () => {
    const { urls, fetchFn } = rig();
    const ctl = new ReviewController(fetchFn, parseReviewFamily("?family=akta"));
    await ctl.load();
    expect(urls).toEqual(["/api/families/akta/proposals", "/api/families/akta/docs/akta-01"]);
    expect(ctl.getState().docs["akta-01"]).toBe("x");
  });

  it("default controller loads uupt", async () => {
    const { urls, fetchFn } = rig();
    await new ReviewController(fetchFn, parseReviewFamily("")).load();
    expect(urls[0]).toBe("/api/families/uupt/proposals");
  });

  it("changing the pick reloads for the new family and updates the URL", async () => {
    const { urls, fetchFn } = rig();
    await new ReviewController(fetchFn, "uupt").load();
    expect(reviewSearch("?family=uupt", "akta")).toBe("?family=akta");
    expect(reviewSearch("?view=review", "akta")).toBe("?view=review&family=akta");
    await new ReviewController(fetchFn, "akta").load();
    expect(urls.filter((u) => u.endsWith("/proposals"))).toEqual(["/api/families/uupt/proposals", "/api/families/akta/proposals"]);
  });

  it("picker uses the U0 labels and marks current", () => {
    const h = renderToStaticMarkup(<ReviewFamilyPicker family="akta" onChange={() => undefined} />);
    expect(h).toContain(FAMILY_LABELS.uupt);
    expect(h).toMatch(/<option value="akta" selected="">Deed \(synthetic\)<\/option>/);
  });

  it("U0 link carries the active family", () => {
    expect(reviewHref("akta", false)).toBe("/review?family=akta");
    expect(reviewHref("uupt", true)).toBe("?view=review&family=uupt");
  });
});
