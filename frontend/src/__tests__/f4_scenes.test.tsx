// F4 (putusan operator 12): UX-04 (a) header B off vs on per butir di U4, UX-08 daftar Decided U6, UX-17 provenance U9.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { footerProvenance } from "../App";
import { HeaderCompare } from "../components/PerItem";
import { DecidedList } from "../components/Review";
import { headerTwin } from "../lib/settings";
import type { ProposalRecord, ReviewState } from "../lib/review";
import type { Item, ItemMetrics } from "../types";
import { mkSetting, mkSnapshot } from "./fixtures";

const OFF = mkSetting("S-off", "structure_handwritten", "dense");
const ON = mkSetting("S-on", "structure_handwritten", "dense", true);
const OTHER = mkSetting("S-bm25-on", "structure_handwritten", "bm25", true);
const it1: Item = { id: "p-1", split: "held_out", family: "uupt", query: "q", doc_id: "d", gold_spans: [{ start: 0, end: 10 }], clean_sha256: "x", mode: "parafrase", origin: "spark_disetujui" };
const m = (item: string, setting: string, covered: number, full: boolean): ItemMetrics => ({
  item_id: item, setting_id: setting, split: "held_out", gold_chars: 10, covered_gold_chars: covered, span_recall: covered / 10, retrieved_tokens: 100,
  gold_tokens_retrieved: 5, token_precision: 0.05, reciprocal_rank: 1, rank: 1, recall_at_k: 1, parts_hit: 1, parts_total: 1, fully_covered: full,
});
const GRID = { tune: { points: [], frontier: null }, held_out: { points: [], frontier: null }, selected: { setting_id: "S-off" }, quality_comparison: null, skipped: [], grid_run_id: "g", failed_settings: [], header_scope: null };

describe("UX-04 (a): header B off vs on per item", () => {
  const snap = mkSnapshot({ settings: [OFF, ON, OTHER], items: [it1], grid: GRID, metrics: [m("p-1", "S-off", 4, false), m("p-1", "S-on", 10, true)] });
  it("twin = same chunker, mode, budget, opposite header; never another mode", () => {
    expect(headerTwin(snap, OFF)?.setting_id).toBe("S-on");
    expect(headerTwin(snap, ON)?.setting_id).toBe("S-off");
    expect(headerTwin(snap, OTHER)).toBeUndefined();
  });
  it("renders stored per-item metrics for off and on, whichever side is selected", () => {
    for (const sel of [OFF, ON]) {
      const h = renderToStaticMarkup(<HeaderCompare snap={snap} setting={sel} items={[it1]} splitOf={() => "held_out"} selectedItemId={null} onSelect={() => undefined} />);
      expect(h).toContain("Header B off vs on, per item");
      expect(h).toContain("4 of 10 chars");
      expect(h).toContain("10 of 10 chars");
      expect(h).toContain("Header B off: 0 of 1 items fully covered. Header B on: 1 of 1 items fully covered.");
      expect(h).toContain("Paraphrase");
    }
  });
  it("hidden without a twin or without its metrics", () => {
    const html = (s: typeof snap, sel = OFF) => renderToStaticMarkup(<HeaderCompare snap={s} setting={sel} items={[it1]} splitOf={() => "held_out"} selectedItemId={null} onSelect={() => undefined} />);
    expect(html(snap, OTHER)).toBe("");
    expect(html({ ...snap, metrics: [m("p-1", "S-off", 4, false)] })).toBe("");
  });
});

const prop = (id: string, status: ProposalRecord["review_status"], at: string | null, item: string | null): ProposalRecord => ({
  proposal_id: id, family: "uupt", body: { query: `query ${id}`, mode: "parafrase", doc_id: "d" }, resolved_span: null, validation: null,
  review_status: status, edited: null, operator_note: null, reviewed_at: at, item_id: item, run_id: "r",
});
const rstate = (all: ProposalRecord[]): ReviewState => ({ load: "ready", loadMessage: "", proposals: all.filter((p) => p.review_status === "usulan"), all, checkConfigHash: null,
  docs: {}, contextLines: 2, busyId: null, confirmingId: null, editingId: null, edit: null, notes: {}, errors: {} } as ReviewState);

describe("UX-08: Decided list (read-only)", () => {
  it("lists decided proposals newest first with English decision labels, no write buttons", () => {
    const h = renderToStaticMarkup(<DecidedList state={rstate([prop("a", "disetujui", "2026-10-27T10:00:00Z", "usulan-a"), prop("b", "ditolak", "2026-10-27T11:00:00Z", null), prop("c", "usulan", null, null)])} />);
    expect(h).toContain("Decided (2)");
    expect(h.indexOf(">b<")).toBeLessThan(h.indexOf(">a<"));
    expect(h).toContain("Approved");
    expect(h).toContain("Rejected");
    expect(h).toContain("usulan-a");
    expect(h).not.toContain("query c");
    expect(h).not.toContain("<button");
  });
  it("nothing when no decision yet", () => {
    expect(renderToStaticMarkup(<DecidedList state={rstate([prop("c", "usulan", null, null)])} />)).toBe("");
  });
});

describe("UX-17: footer provenance", () => {
  it("from items_summary", () => {
    expect(footerProvenance({ n_items: 23, by_origin: { operator: 9, spark_disetujui: 14 }, by_mode: {}, by_split: null, control_in_held_out: null }))
      .toBe("23 items: 9 operator-written, 14 Spark-proposed and operator-approved");
    expect(footerProvenance(null)).toBeNull();
    expect(footerProvenance({ n_items: 0, by_origin: {}, by_mode: {}, by_split: null, control_in_held_out: null })).toBeNull();
  });
});
