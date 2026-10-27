// U2 dua deret header B off/on (M3.2): titik, legenda, titik gagal tidak digambar, klik titik on. Render server (tanpa DOM);
// grafik Recharts butuh ukuran jadi tidak ikut di-render, sehingga titik diuji lewat `plottable` dan label aria grafik.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { blankState, reducer, type State } from "../state";
import { mkSetting, mkSnapshot } from "./fixtures";
import type { GridPoint, Snapshot } from "../types";

const mock = vi.hoisted(() => ({ state: null as unknown as State }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { SettingSpace, failReason, frontierLine, plottable } from "../components/SettingSpace";
import { availableSettings, frontierIds } from "../lib/settings";

const pt = (id: string, x: number | null, y: number | null, header_b?: boolean): GridPoint => ({
  setting_id: id, split: "held_out", budget_tokens: 2000, mean_span_recall: y, mean_token_precision: 0.1, mrr: 0.5, mean_retrieved_tokens: x,
  fully_covered_count: { covered: 1, total: 2 }, dominated: false, n_gold: 2, no_gold_count: 0, exact: null, ...(header_b === undefined ? {} : { header_b }),
});

const SET = [mkSetting("off", "structure_handwritten", "hybrid"), mkSetting("on", "structure_handwritten", "hybrid", true),
  mkSetting("bad", "fixed_size", "hybrid", true), mkSetting("fx", "fixed_size", "hybrid")];

function snap(over: Partial<NonNullable<Snapshot["grid"]>> = {}, sets = SET): Snapshot {
  return mkSnapshot({
    settings: sets,
    grid: {
      tune: { points: [], frontier: null },
      held_out: { points: [pt("off", 1500, 0.6, false), pt("on", 1600, 0.8, true), pt("fx", 1900, 0.5, false)],
        frontier: { split: "held_out", budget_tokens: 2000, point_ids: ["off", "on"], grid_run_id: "g" } },
      selected: { setting_id: "off" }, quality_comparison: null, skipped: [], grid_run_id: "g",
      failed_settings: [], header_scope: null, ...over,
    },
  });
}

const render = (s: Snapshot): string => {
  mock.state = { ...blankState(), snapshot: { status: "ready", data: s }, split: "held_out" };
  return renderToStaticMarkup(<SettingSpace />);
};

describe("U2 two series", () => {
  it("splits dots into off and on series from the point label", () => {
    const sn = snap();
    const { dots } = plottable(sn.grid!.held_out.points, availableSettings(sn), frontierIds(sn, "held_out"));
    expect(dots.filter((d) => !d.headerOn).map((d) => d.setting.setting_id)).toEqual(["off", "fx"]);
    expect(dots.filter((d) => d.headerOn).map((d) => d.setting.setting_id)).toEqual(["on"]);
    expect(frontierLine(dots).map((d) => d.setting.setting_id)).toEqual(["off", "on"]);
  });
  it("falls back to the setting's header_b when the point has no label", () => {
    const sn = snap();
    sn.grid!.held_out.points = [pt("on", 1600, 0.8), pt("off", 1500, 0.6)];
    const { dots } = plottable(sn.grid!.held_out.points, availableSettings(sn), new Set());
    expect(dots.map((d) => d.headerOn)).toEqual([true, false]);
  });
  it("legend names both series; chart label counts header-on points", () => {
    const h = render(snap());
    expect(h).toContain('data-testid="legend-off"');
    expect(h).toMatch(/data-testid="legend-off"[^>]*>.*?Header B off/);
    expect(h).toMatch(/data-testid="legend-on"[^>]*>.*?Header B on<\/li>/);
    expect(h).toContain("1 with header B on");
  });
  it("legend says there are no header-on points when the series is empty", () => {
    const sn = snap();
    sn.grid!.held_out.points = [pt("off", 1500, 0.6, false)];
    expect(render(sn)).toContain("Header B on: no points");
  });
  it("shows the frontier-only note when scope is frontier_only", () => {
    expect(render(snap({ header_scope: "frontier_only" }))).toContain("Header B computed for frontier settings only.");
    expect(render(snap({ header_scope: "all" }))).not.toContain("computed for frontier settings only");
  });
});

describe("U2 failed header-on settings", () => {
  const failed = [{ setting_id: "bad", reason: "header_missing", chunk_id: "abcdef0123456789zz" }];
  it("lists them with reason and does not plot them", () => {
    const sn = snap({ failed_settings: failed });
    const { dots } = plottable(sn.grid!.held_out.points, availableSettings(sn), new Set());
    expect(dots.map((d) => d.setting.setting_id)).not.toContain("bad");
    const h = render(sn);
    expect(h).toContain("Failed header-on settings");
    expect(h).toContain("header missing for a chunk (header_missing)");
    expect(h).toContain("chunk abcdef012345");
    expect(h).toContain("fixed-size · hybrid · header on");
    expect(h).toContain("3 settings"); // off, on, fx: tidak ada titik untuk 'bad'
  });
  it("hides the list when nothing failed or the key is absent", () => {
    expect(render(snap())).not.toContain("Failed header-on settings");
    const sn = snap();
    delete sn.grid!.failed_settings;
    expect(render(sn)).not.toContain("Failed header-on settings");
  });
  it("keeps unknown reason codes visible and tolerates unknown setting ids", () => {
    expect(failReason("something_new")).toBe("something_new");
    const h = render(snap({ failed_settings: [{ setting_id: "zzzzzzzzzzzzzzzzzz", reason: "header_stale", chunk_id: null }] }));
    expect(h).toContain("zzzzzzzzzzzz");
    expect(h).toContain("header_stale");
  });
});

describe("U2 click on a header-on point", () => {
  it("selects the header-on setting in the shared store (U1/U4 follow selectedSettingId)", () => {
    const ready = reducer(blankState(), { type: "snapshot_ready", data: snap() });
    const s = reducer(ready, { type: "select_setting", id: "on" });
    expect(s.selectedSettingId).toBe("on");
    expect(s.selectedChunkId).toBeNull();
  });
  it("the selected header-on setting is shown in the detail block", () => {
    mock.state = { ...blankState(), snapshot: { status: "ready", data: snap() }, split: "held_out", selectedSettingId: "on" };
    const h = renderToStaticMarkup(<SettingSpace />);
    expect(h).toContain("structure · hybrid · header on");
  });
});
