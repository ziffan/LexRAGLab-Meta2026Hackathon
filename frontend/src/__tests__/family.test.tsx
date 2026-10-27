// M4.1 pemilih keluarga U0: Family [Company Law (UU 40/2007) | Deed (synthetic)], reducer set_family, dan panel dengan
// snapshot akta tanpa grid (grid null, tanpa setting). Render server (tanpa DOM).
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { blankState, reducer, type State } from "../state";
import { mkSnapshot } from "./fixtures";

const mock = vi.hoisted(() => ({ state: null as unknown as State }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { FAMILY_LABELS, Header } from "../components/Header";
import { SettingSpace } from "../components/SettingSpace";

describe("family picker", () => {
  it("lists both families with UI-SPEC labels and marks the current one", () => {
    mock.state = { ...blankState(), family: "akta" };
    const h = renderToStaticMarkup(<Header />);
    expect(FAMILY_LABELS).toEqual({ uupt: "Company Law (UU 40/2007)", akta: "Deed (synthetic)" });
    expect(h).toContain("Company Law (UU 40/2007)");
    expect(h).toContain("Deed (synthetic)");
    expect(h).toMatch(/<option value="akta" selected="">Deed \(synthetic\)<\/option>/);
    expect(h).toContain('aria-label="Family"');
  });

  it("set_family resets selection and snapshot; same family is a no-op", () => {
    const s0: State = { ...blankState(), budget: 4000, selectedItemId: "i1", selectedSettingId: "s1", compare: true };
    const s1 = reducer(s0, { type: "set_family", value: "akta" });
    expect(s1.family).toBe("akta");
    expect(s1.budget).toBeNull();
    expect(s1.selectedItemId).toBeNull();
    expect(s1.selectedSettingId).toBeNull();
    expect(s1.snapshot).toEqual({ status: "idle" });
    expect(s1.compare).toBe(false);
    expect(reducer(s0, { type: "set_family", value: "uupt" })).toBe(s0);
  });

  it("renders the setting-space panel for an akta snapshot without grid or settings", () => {
    const snap = mkSnapshot({ family: "akta", settings: [], grid: null, items: [], metrics: [] });
    mock.state = { ...blankState(), family: "akta", snapshot: { status: "ready", data: snap } };
    expect(() => renderToStaticMarkup(<SettingSpace />)).not.toThrow();
  });
});
