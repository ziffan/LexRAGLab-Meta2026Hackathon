import { describe, expect, it } from "vitest";
import { NA, orNa, truncate, xOfY } from "../lib/format";
import { modeLabel, originLabel, scopeLabel, splitLabel, settingShort } from "../lib/labels";
import { filterScopeLabel, itemPasses, originSummary, toRow } from "../lib/rows";
import { availableSettings, frontierIds, matchSetting, recallAtKCounts, resolveSettingParam, settingParam, siblingModes } from "../lib/settings";
import { blankState, reducer, type State } from "../state";
import { frontierLine, plottable } from "../components/SettingSpace";
import type { GridPoint, Item, ItemMetrics, Setting, Snapshot } from "../types";

const setting = (id: string, chunker: Setting["chunker"], mode: Setting["retrieval_mode"], budget = 2000, header = false): Setting => ({
  setting_id: id,
  family: "uupt",
  chunker,
  chunk_size_tokens: chunker === "fixed_size" ? 512 : null,
  overlap_tokens: chunker === "fixed_size" ? 64 : null,
  schema_version: null,
  retrieval_mode: mode,
  header_b: header,
  budget_tokens: budget,
});

const point = (id: string, x: number | null, y: number | null, split: "tune" | "held_out" = "held_out"): GridPoint => ({
  setting_id: id,
  split,
  budget_tokens: 2000,
  mean_span_recall: y,
  mean_token_precision: 0.03,
  mrr: 0.5,
  mean_retrieved_tokens: x,
  fully_covered_count: { covered: 2, total: 3 },
  dominated: false,
  n_gold: 3,
  no_gold_count: 0,
  exact: { mean_span_recall: "2/3", mrr: "1/2" },
});

const metric = (over: Partial<ItemMetrics>): ItemMetrics => ({
  item_id: "k1",
  setting_id: "s1",
  split: "held_out",
  gold_chars: 100,
  covered_gold_chars: 80,
  span_recall: 0.8,
  retrieved_tokens: 1700,
  gold_tokens_retrieved: 20,
  token_precision: 0.0117,
  reciprocal_rank: 0.25,
  rank: 4,
  recall_at_k: 0.5,
  parts_hit: 1,
  parts_total: 2,
  fully_covered: false,
  ...over,
});

const S = [setting("a", "structure_handwritten", "dense"), setting("b", "structure_handwritten", "bm25"), setting("c", "structure_handwritten", "hybrid"), setting("d", "fixed_size", "hybrid"), setting("h", "structure_handwritten", "dense", 2000, true), setting("a1", "structure_handwritten", "dense", 1000)];

const snap = (): Snapshot => ({
  family: "uupt",
  budget_tokens: 2000,
  replay: false,
  config_hash: "x",
  corpus: [],
  items: [],
  items_summary: { n_items: 0, by_origin: {}, by_mode: {}, by_split: null, control_in_held_out: null },
  settings: S,
  grid: {
    tune: { points: [], frontier: null },
    held_out: { points: [point("a", 1700, 0.6), point("d", 1900, 1.0), point("b", null, null)], frontier: { split: "held_out", budget_tokens: 2000, point_ids: ["d", "a"], grid_run_id: "g" } },
    selected: { setting_id: "a" },
    quality_comparison: null,
    skipped: [{ setting_id: "h", reason: "header B is available from M3" }],
    grid_run_id: "g",
  },
  metrics: [],
  quality: [],
});

describe("format", () => {
  it("renders raw counts as 'x of y'", () => {
    expect(xOfY(7, 12)).toBe("7 of 12");
    expect(xOfY(0, 3, "items fully covered")).toBe("0 of 3 items fully covered");
  });
  it("renders null and undefined as n/a", () => {
    expect(xOfY(null, 3)).toBe(NA);
    expect(xOfY(2, undefined)).toBe("n/a");
    expect(orNa(null)).toBe("n/a");
    expect(orNa(0.5, (v) => v.toFixed(1))).toBe("0.5");
  });
  it("renders a no-gold item as n/a without fabricating numbers", () => {
    const r = toRow(metric({ gold_chars: 0, covered_gold_chars: 0, span_recall: null, token_precision: null, reciprocal_rank: null, rank: null, recall_at_k: null, parts_hit: 0, parts_total: 0, fully_covered: null, gold_tokens_retrieved: 0 }));
    expect(r.hasGold).toBe(false);
    expect([r.spanRecall, r.tokenPrecision, r.rank, r.recallAtK, r.fullyCovered]).toEqual(["n/a", "n/a", "n/a", "n/a", "n/a"]);
    expect(r.retrievedTokens).toBe("1700");
  });
  it("renders raw counts for a gold item", () => {
    const r = toRow(metric({}));
    expect(r.spanRecall).toBe("80 of 100 chars");
    expect(r.tokenPrecision).toBe("20 of 1700 tokens");
    expect(r.recallAtK).toBe("1 of 2 gold parts");
    expect(r.rank).toBe("rank 4 (RR 1/4)");
    expect(r.fullyCovered).toBe("no");
  });
});

describe("enum labels (UI-SPEC section 6)", () => {
  it("maps origin, mode and split to English labels", () => {
    expect(originLabel("operator")).toBe("Operator-written");
    expect(originLabel("spark_disetujui")).toBe("Spark-proposed, approved");
    expect(modeLabel("literal")).toBe("Literal");
    expect(modeLabel("parafrase")).toBe("Paraphrase");
    expect(splitLabel("tune")).toBe("Tune");
    expect(splitLabel("held_out")).toBe("Held-out");
    expect(splitLabel(null)).toBe("n/a");
  });
  it("names a setting like the header example", () => {
    expect(settingShort(S[2])).toBe("structure · hybrid · header off");
  });
});

describe("filters and summaries", () => {
  const items: Item[] = [
    { id: "i1", split: "held_out", family: "uupt", query: "q", doc_id: "d", gold_spans: [{ start: 0, end: 1 }], clean_sha256: "x", mode: "literal", origin: "operator" },
    { id: "i2", split: "tune", family: "uupt", query: "q", doc_id: "d", gold_spans: [], clean_sha256: "x", mode: "parafrase", origin: "operator" },
  ];
  it("filters by origin, mode and split", () => {
    const f = (o: "all" | "operator", m: "all" | "literal" | "parafrase", sp: "all" | "tune" | "held_out") => items.filter((i) => itemPasses(i, { origin: o, mode: m, split: sp }, (id) => items.find((x) => x.id === id)?.split)).map((i) => i.id);
    expect(f("all", "all", "all")).toEqual(["i1", "i2"]);
    expect(f("all", "parafrase", "all")).toEqual(["i2"]);
    expect(f("operator", "all", "held_out")).toEqual(["i1"]);
  });
  it("summarises per origin as raw counts and separates no-gold items", () => {
    const m = new Map([
      ["i1", metric({ item_id: "i1", fully_covered: true })],
      ["i2", metric({ item_id: "i2", fully_covered: null })],
    ]);
    expect(originSummary(items, m)).toEqual([{ origin: "operator", covered: 1, total: 1, noGold: 1 }]);
  });
  it("counts Recall@K items from per-item parts", () => {
    const c = recallAtKCounts([metric({ parts_hit: 2, parts_total: 2 }), metric({ parts_hit: 1, parts_total: 2 }), metric({ parts_hit: 0, parts_total: 1 }), metric({ parts_hit: 0, parts_total: 0 })]);
    expect(c).toEqual({ full: 1, partial: 1, withGold: 3 });
  });
});

describe("settings and frontier", () => {
  it("hides skipped settings and other budgets", () => {
    expect(availableSettings(snap()).map((s) => s.setting_id)).toEqual(["a", "b", "c", "d"]);
  });
  it("finds the three modes of the same chunker", () => {
    expect(siblingModes(snap(), S[0]).map((s) => s.retrieval_mode)).toEqual(["dense", "bm25", "hybrid"]);
    expect(siblingModes(snap(), S[3]).map((s) => s.retrieval_mode)).toEqual(["hybrid"]);
  });
  it("keeps the equivalent setting when the budget changes", () => {
    expect(matchSetting([S[5], S[3]], S[0])?.setting_id).toBe("a1");
  });
  it("resolves the ?setting= parameter", () => {
    expect(resolveSettingParam(S, "fixed_size/hybrid")?.setting_id).toBe("d");
    expect(resolveSettingParam(S, "d")?.setting_id).toBe("d");
    expect(settingParam(S[0])).toBe("structure_handwritten/dense");
  });
  it("drops points without gold from the plot and joins the frontier left to right", () => {
    const sn = snap();
    const { dots, hidden } = plottable(sn.grid!.held_out!.points, availableSettings(sn), frontierIds(sn, "held_out"));
    expect(hidden).toBe(1);
    expect(dots.map((d) => d.setting.setting_id)).toEqual(["a", "d"]);
    expect(frontierLine(dots).map((d) => d.setting.setting_id)).toEqual(["a", "d"]);
  });
});

describe("store reducer", () => {
  const ready = (): State => reducer(blankState(), { type: "snapshot_ready", data: snap() });
  it("selects the tune-selected setting when the snapshot arrives", () => {
    expect(ready().selectedSettingId).toBe("a");
  });
  it("clicking a frontier point updates the selected setting (M1.4)", () => {
    const s = reducer(ready(), { type: "select_setting", id: "d" });
    expect(s.selectedSettingId).toBe("d");
    expect(s.selectedChunkId).toBeNull();
  });
  it("resolves ?setting= on snapshot arrival", () => {
    const s = reducer({ ...blankState(), paramSetting: "fixed_size/hybrid" }, { type: "snapshot_ready", data: snap() });
    expect(s.selectedSettingId).toBe("d");
  });
  it("keeps the equivalent setting after a budget change", () => {
    const other: Snapshot = { ...snap(), budget_tokens: 1000, grid: null };
    const s = reducer(reducer(ready(), { type: "set_budget", value: 1000 }), { type: "snapshot_ready", data: other });
    expect(s.selectedSettingId).toBe("a1");
  });
  it("updates filters and split independently", () => {
    const s = reducer(reducer(blankState(), { type: "set_filters", value: { mode: "parafrase" } }), { type: "set_split", value: "tune" });
    expect(s.filters).toEqual({ origin: "all", mode: "parafrase", split: "all" });
    expect(s.split).toBe("tune");
  });
});

describe("round 2 additions", () => {
  const mk = (id: string, origin: Item["origin"]): Item => ({ id, split: "tune", family: "uupt", query: "q", doc_id: "d", gold_spans: [{ start: 0, end: 1 }], clean_sha256: "x", mode: "literal", origin });
  it("originSummary counts covered strictly below total and per origin", () => {
    const items = [mk("a", "operator"), mk("b", "operator"), mk("c", "operator"), mk("d", "spark_disetujui")];
    const m = new Map([
      ["a", metric({ item_id: "a", fully_covered: true })],
      ["b", metric({ item_id: "b", fully_covered: false })],
      ["c", metric({ item_id: "c", fully_covered: null })],
      ["d", metric({ item_id: "d", fully_covered: false })],
    ]);
    expect(originSummary(items, m)).toEqual([
      { origin: "operator", covered: 1, total: 2, noGold: 1 },
      { origin: "spark_disetujui", covered: 0, total: 1, noGold: 0 },
    ]);
  });
  it("truncate keeps text at the limit and cuts one past it", () => {
    expect(truncate("abcde", 5)).toBe("abcde");
    expect(truncate("abcdef", 5)).toBe("abcde" + String.fromCharCode(8230));
    expect(truncate("", 0)).toBe("");
  });
  it("labels the item scope from the API value, not a hardcoded split", () => {
    expect(scopeLabel("all")).toBe("all items (tune + held-out)");
    expect(scopeLabel("tune")).toBe("tune items only");
    expect(scopeLabel("held_out")).toBe("held-out items only");
    expect(scopeLabel(undefined)).toBe("item scope not reported");
    expect(filterScopeLabel("held_out")).toBe("held-out items only");
    expect(filterScopeLabel("all")).toBe("all items (tune + held-out)");
  });
});
