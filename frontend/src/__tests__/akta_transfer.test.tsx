// W62 / S4: grid akta `{all}` di U2, laporan transfer di U7, label degenerate (H-093), banner "Pending operator review" yang hilang
// lewat data (`grid.final`), dan pemilih Family di ekspor statis. Data sintetis; render server (tanpa DOM), tanpa jaringan.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { blankState, reducer, type State } from "../state";
import { mkSetting, mkSnapshot } from "./fixtures";
import type { GridPoint, Grid, Report, Snapshot, TransferSetting } from "../types";

const mock = vi.hoisted(() => ({ state: null as unknown as State }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { ProfilePanel, ResultsSection, transferText } from "../components/ProfileExport";
import { SettingSpace } from "../components/SettingSpace";
import { isPendingReview } from "../components/Shell";
import { DEGENERATE_LABEL, DEGENERATE_NOTE, TRANSFER_LABEL, frontierIds, gridKey, hasDegenerate, isTransferGrid, pointOf } from "../lib/settings";
import { resolveStatic, staticAwareFetch } from "../lib/staticData";
import { scopeLabel } from "../lib/labels";

const pt = (id: string, label: string | null, rec = 1): GridPoint => ({
  setting_id: id, split: null, budget_tokens: 2000, mean_span_recall: rec, mean_token_precision: 0.5, mrr: 1, mean_retrieved_tokens: 100,
  fully_covered_count: { covered: 2, total: 3 }, dominated: false, header_b: false, n_gold: 3, no_gold_count: 1,
  exact: { mean_span_recall: "1/1", mrr: "1/1" }, label,
});
const T: TransferSetting = { setting_id: "S-schema", chunker: "structure_schema", schema_version: 2, retrieval_mode: "hybrid", header_b: false,
  budget_tokens: 2000, source_setting_id: "U-best", label: TRANSFER_LABEL };
const grid = (over: Partial<Grid> = {}): Grid => ({
  all: { points: [pt("S-hand", DEGENERATE_LABEL, 0.25), pt("S-schema", null), pt("S-fixed", null, 0.5)],
         frontier: { split: null, budget_tokens: 2000, point_ids: ["S-schema"], grid_run_id: "K" } },
  transfer: T, final: false, selected: null, quality_comparison: null, skipped: [], grid_run_id: "K", ...over,
});
const akta = (g: Grid | null, over: Partial<Snapshot> = {}): Snapshot =>
  mkSnapshot({ family: "akta", settings: [mkSetting("S-hand", "structure_handwritten"), { ...mkSetting("S-schema", "structure_schema"), schema_version: 2 }, mkSetting("S-fixed", "fixed_size")],
               grid: g, ...over });
const REPORT: Report = {
  family: "akta", title: "Transfer results", setting: T,
  rows: [
    { item_id: "a1", split: "Transfer", origin: "operator", mode: "literal", span_recall: { numerator: 8, denominator: 8, text: "8 of 8" },
      token_precision: { numerator: 4, denominator: 9, text: "4 of 9" }, reciprocal_rank: 1, recall_at_k: 1, fully_covered: true, note: null },
    { item_id: "t1", split: "Transfer", origin: "operator", mode: "tolak", span_recall: null, token_precision: null, reciprocal_rank: null,
      recall_at_k: null, fully_covered: null, note: "no gold (must abstain)" },
  ],
  summary: { n_items: 2, mean_span_recall: 1, mean_token_precision: 0.44, fully_covered: { numerator: 1, denominator: 1, text: "1 of 1" } },
  by_origin: {}, by_mode: {},
};
const set = (data: Snapshot) => {
  mock.state = { ...blankState(), snapshot: { status: "ready", data }, family: data.family, selectedSettingId: "S-schema" };
};
const heldOut = /held[- ]?out/i;
const noHints = (h: string): string => h.replace(/<span class="hint">[\s\S]*?<\/div><\/span>/g, "");

describe("tipe dan helper grid akta", () => {
  it("grid akta = satu blok `all`; kunci split diabaikan", () => {
    const s = akta(grid());
    expect(isTransferGrid(s)).toBe(true);
    expect(gridKey(s, "tune")).toBe("all");
    expect(gridKey(mkSnapshot(), "tune")).toBe("tune");
    expect(pointOf(s, "S-schema", "all")?.mean_span_recall).toBe(1);
    expect([...frontierIds(s, "all")]).toEqual(["S-schema"]);
    expect(pointOf(s, "S-schema", "held_out")).toBeUndefined(); // tak ada blok held_out di akta: undefined, bukan galat
    expect(hasDegenerate(s)).toBe(true);
    expect(hasDegenerate(akta(grid({ all: { points: [pt("S-schema", null)], frontier: null } })))).toBe(false);
  });
  it("label cakupan Recall@K 'transfer'", () => {
    expect(scopeLabel("transfer")).toBe("all items (transfer test)");
    expect(scopeLabel("transfer")).not.toMatch(heldOut);
  });
  it("snapshot_ready memilih setting transfer bila akta tak punya `selected`", () => {
    const s = reducer(blankState(), { type: "snapshot_ready", data: akta(grid()) });
    expect(s.selectedSettingId).toBe("S-schema");
  });
});

describe("banner Pending operator review hilang lewat data (grid.final)", () => {
  it("akta: tanpa grid atau grid belum final = pending; final = tidak", () => {
    expect(isPendingReview(akta(null))).toBe(true);
    expect(isPendingReview(akta(grid({ final: false })))).toBe(true);
    expect(isPendingReview(akta(grid({ final: undefined })))).toBe(true); // snapshot lama tanpa penanda: tetap pending
    expect(isPendingReview(akta(grid({ final: true })))).toBe(false);
    expect(isPendingReview(mkSnapshot({ grid: null }))).toBe(false); // UU PT tak pernah memakai banner ini
  });
  it("grid belum final: U2 dan U7 menampilkan banner dan tidak ada angka sementara", () => {
    set(akta(grid({ final: false }), { report: REPORT }));
    for (const el of [<SettingSpace key="a" />, <ProfilePanel key="b" />]) {
      const h = renderToStaticMarkup(el);
      expect(h).toContain("Pending operator review");
      expect(h).not.toContain(TRANSFER_LABEL);
      expect(h).not.toContain("8 of 8");
    }
  });
});

describe("U2 akta", () => {
  it("final: satu frontier berlabel transfer, tanpa kontrol split, label degenerate tampil", () => {
    set(akta(grid({ final: true })));
    const h = renderToStaticMarkup(<SettingSpace />);
    expect(h).not.toContain("Pending operator review");
    expect(h).toContain(TRANSFER_LABEL);
    expect(h).toContain('data-testid="transfer-note"');
    expect(h).not.toContain("u2-split"); // radio Tune/Held-out hanya untuk UU PT
    expect(noHints(h)).not.toMatch(heldOut); // hint UU PT "Tune vs held-out" (pop-up tersembunyi) di luar cakupan W62
    expect(h).toContain(DEGENERATE_NOTE);
    expect(DEGENERATE_NOTE).toContain("no structure recognized");
    expect(h).toContain("structure (schema A) · hybrid · header off"); // setting transfer disebut
    expect(h).toContain("3 settings, 1 on the frontier"); // aria-label grafik: 3 titik, 1 frontier
  });
  it("UU PT tetap dua split dan tanpa catatan transfer", () => {
    const u = mkSnapshot({ grid: { tune: { points: [], frontier: null }, held_out: { points: [], frontier: null }, selected: null, quality_comparison: null, skipped: [], grid_run_id: "g" } });
    set(u);
    const h = renderToStaticMarkup(<SettingSpace />);
    expect(h).toContain("u2-split");
    expect(h).not.toContain("transfer-note");
    expect(h).not.toContain(DEGENERATE_NOTE);
  });
});

describe("U7 akta: laporan transfer", () => {
  it("menyorot setting transfer berlabel, memuat butir tolak dengan kolom null, tanpa kata held-out", () => {
    const h = renderToStaticMarkup(<ResultsSection family="akta" profile={null} report={REPORT} degenerate />);
    expect(h).toContain("Transfer results");
    expect(h).toContain('data-testid="transfer-setting"');
    expect(h).toContain(TRANSFER_LABEL);
    expect(h).toContain(transferText(T));
    expect(transferText(T)).toBe("Structure (schema A v2) · Hybrid · header B off · 2000 tokens (local tokenizer)");
    expect(h).toContain("Must refuse"); // butir tolak (H-092)
    expect(h).toContain("no gold (must abstain)");
    expect(h).toMatch(/<td>n\/a<\/td><td>n\/a \(no gold/); // kolom metrik null -> n/a
    expect(h).toContain(DEGENERATE_NOTE);
    expect(h).not.toMatch(heldOut);
  });
  it("tanpa degenerate/setting: tidak ada catatan", () => {
    const h = renderToStaticMarkup(<ResultsSection family="akta" profile={null} report={{ ...REPORT, setting: undefined }} />);
    expect(h).not.toContain("transfer-setting");
    expect(h).not.toContain("degenerate-note");
  });
  it("final: panel U7 menampilkan laporan, bukan banner", () => {
    set(akta(grid({ final: true }), { report: REPORT }));
    const h = renderToStaticMarkup(<ProfilePanel />);
    expect(h).not.toContain("Pending operator review");
    expect(h).toContain("Transfer results");
    expect(h).toContain(TRANSFER_LABEL);
  });
});

describe("ekspor statis: pemilih Family", () => {
  it("R2 dipetakan ke data/families.json dan tidak menyentuh jaringan", async () => {
    expect(resolveStatic("/api/families")).toEqual({ kind: "file", path: "data/families.json" });
    const raw = vi.fn(async (u: string, _i?: RequestInit) => new Response(u === "data/families.json" ? JSON.stringify([{ family: "uupt" }, { family: "akta" }]) : "{}", { status: 200 }));
    const res = await staticAwareFetch((u, i) => raw(u, i), () => true)("/api/families");
    expect(((await res.json()) as { family: string }[]).map((f) => f.family)).toEqual(["uupt", "akta"]);
    expect(raw.mock.calls.map((c) => c[0])).toEqual(["data/families.json"]);
  });
});

describe("akta: tidak ada label held-out di U2/U4 (arahan L2, H-078)", () => {
  it("U2 tanpa hint tune/held-out; U4 tanpa filter Split dan tanpa kata held-out", async () => {
    const { PerItem } = await import("../components/PerItem");
    set(akta(grid({ final: true }), { items: [{ id: "i1", family: "akta", origin: "operator", mode: "literal", split: null, gold_spans: [{ start: 0, end: 5 }], query: "q" } as never] }));
    expect(renderToStaticMarkup(<SettingSpace />)).not.toMatch(heldOut); // hint disaring, bukan teksnya diubah
    const h = renderToStaticMarkup(<PerItem />);
    expect(noHints(h)).not.toMatch(heldOut);
    expect(h).not.toContain("Tune vs held-out");
  });
  it("hint Recall@K akta memakai varian akta (H-094), tanpa kata held-out/tune; UU PT tetap entri lama", async () => {
    const { PerItem } = await import("../components/PerItem");
    const { getHint } = await import("../lib/hints");
    const item = { id: "i1", family: "akta", origin: "operator", mode: "literal", split: null, gold_spans: [{ start: 0, end: 5 }], query: "q" } as never;
    set(akta(grid({ final: true }), { items: [item] }));
    const h = renderToStaticMarkup(<PerItem />);
    const v = getHint("metric.recall_at_k.akta");
    expect(v?.status).toBe("final");
    expect(v?.source).toBe("H-094");
    expect(h).toContain("Recall@K (deeds)");
    expect(h).toContain("Komparisi");
    expect(h).toContain("not comparable with Company Law");
    expect(h).not.toMatch(heldOut); // seluruh keluaran, termasuk pop-up hint
    expect(h).not.toMatch(/tune/i);
    expect(v?.body).not.toMatch(/\d/); // tanpa angka
    set({ ...akta(grid({ final: true }), { items: [{ ...(item as object), family: "uupt", split: "heldout" } as never] }), family: "uupt" });
    const u = renderToStaticMarkup(<PerItem />);
    expect(u).not.toContain("Recall@K (deeds)");
    expect(u).toContain(getHint("metric.recall_at_k")!.body.replace(/&/g, "&amp;"));
  });
  it("filterScopeLabel akta", async () => {
    const { filterScopeLabel } = await import("../lib/rows");
    expect(filterScopeLabel("all", true)).toBe("all items (transfer test)");
    expect(filterScopeLabel("all")).toBe("all items (tune + held-out)");
  });
});

describe("perbaikan W64", () => {
  it("QualityPanel: Recall@K akta (items_scope transfer) dihitung dari semua butir ber-gold", async () => {
    const { QualityPanel } = await import("../components/QualityPanel");
    const m = (id: string, hit: number): never => ({ item_id: id, setting_id: "S-schema", split: null, parts_hit: hit, parts_total: 2 } as never);
    const s = akta(grid({ final: true }), { metrics: [m("a", 2), m("b", 1)], quality: [{ setting_id: "S-schema", entity_preservation: 1, boundary_coherence: 1, recall_at_k: 0.5, k: 5, items_scope: "transfer" } as never] });
    const h = renderToStaticMarkup(<QualityPanel snap={s} setting={s.settings[1]} />);
    expect(h).toContain("1 of 2 items with all gold parts in top 5");
    expect(h).toContain("(+1 partial)");
  });
  it("fsplit di URL diabaikan untuk akta di U4; kata 'split' tidak ada di empty state U2 akta", async () => {
    const { PerItem } = await import("../components/PerItem");
    const it = { id: "i1", family: "akta", origin: "operator", mode: "literal", split: null, gold_spans: [{ start: 0, end: 5 }], query: "q" } as never;
    set(akta(grid({ final: true }), { items: [it] }));
    mock.state = { ...mock.state, filters: { origin: "all", mode: "all", split: "tune" } };
    expect(renderToStaticMarkup(<PerItem />)).toContain("i1");
    set(akta(grid({ final: true, all: { points: [{ ...pt("S-schema", null), mean_span_recall: null }], frontier: null } })));
    const u2 = renderToStaticMarkup(<SettingSpace />);
    expect(u2).toContain("No plottable points: every item here lacks gold.");
    expect(u2).toContain("no gold items (n/a)");
  });
});
