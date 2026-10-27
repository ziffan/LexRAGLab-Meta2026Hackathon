// W61 perbaikan: label `tolak` = "Must refuse" di semua tampilan butir (PerItem, ChunksVsGold, ProfileExport); filter selalu menawarkan opsi.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { blankState, type State } from "../state";
import type { Grid, Item, Report } from "../types";
import { mkSnapshot, SETTINGS } from "./fixtures";

const mock = vi.hoisted(() => ({ state: null as unknown as State }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { ChunksVsGold } from "../components/ChunksVsGold";
import { PerItem } from "../components/PerItem";
import { ReportTable } from "../components/ProfileExport";
import { modeLabel } from "../lib/labels";

const ITEM = (id: string, mode: Item["mode"], gold: boolean): Item => ({
  id, family: "uupt", query: `q-${id}`, doc_id: "uupt-40-2007", gold_spans: gold ? [{ start: 0, end: 5 }] : [], clean_sha256: "x", mode, origin: "operator",
});
const GRID = { tune: { points: [] }, held_out: { points: [] }, selected: null, quality_comparison: null, skipped: [], grid_run_id: "g" } as unknown as Grid;

describe("label tolak", () => {
  it("modeLabel", () => {
    expect(modeLabel("tolak")).toBe("Must refuse");
    expect(modeLabel("literal")).toBe("Literal");
    expect(modeLabel("parafrase")).toBe("Paraphrase");
  });

  it("PerItem: opsi filter Must refuse selalu ada, juga tanpa butir tolak; baris tolak berlabel", () => {
    const withGrid = (items: Item[]) => {
      mock.state = { ...blankState(), selectedSettingId: SETTINGS[0].setting_id, snapshot: { status: "ready", data: mkSnapshot({ items, grid: GRID }) } };
      return renderToStaticMarkup(<PerItem />);
    };
    const none = withGrid([ITEM("a", "literal", true)]);
    expect(none).toContain('<option value="tolak">Must refuse</option>');
    const some = withGrid([ITEM("a", "literal", true), ITEM("b", "tolak", false)]);
    expect(some).toContain('<option value="tolak">Must refuse</option>');
    expect(some).toContain("<td>Must refuse</td>");
    expect(some).not.toContain("<td>tolak</td>");
  });

  it("ChunksVsGold: butir tolak berlabel di daftar pilihan", () => {
    mock.state = { ...blankState(), snapshot: { status: "ready", data: mkSnapshot({ items: [ITEM("b", "tolak", false)] }) } };
    const h = renderToStaticMarkup(<ChunksVsGold />);
    expect(h).toContain("b · Must refuse");
    expect(h).not.toContain("tolak</option>");
  });

  it("ProfileExport ReportTable: mode tolak berlabel", () => {
    const report = {
      family: "akta", title: "Transfer results", rows: [
        { item_id: "r1", split: "n/a", origin: "spark_disetujui", mode: "tolak", span_recall: null, token_precision: null, reciprocal_rank: null, recall_at_k: null, fully_covered: null, note: null },
        { item_id: "r2", split: "n/a", origin: "operator", mode: "literal", span_recall: null, token_precision: null, reciprocal_rank: null, recall_at_k: null, fully_covered: null, note: null },
      ],
      summary: { n_items: 2, mean_span_recall: null, mean_token_precision: null, fully_covered: { numerator: 0, denominator: 0, text: "0/0" } },
      by_origin: {}, by_mode: {},
    } as unknown as Report;
    const h = renderToStaticMarkup(<ReportTable report={report} />);
    expect(h).toContain("<td>Must refuse</td>");
    expect(h).toContain("<td>Literal</td>");
    expect(h).not.toContain("<td>tolak</td>");
  });
});
