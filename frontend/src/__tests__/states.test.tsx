// Loading / kosong / error di tiga panel utama U1 (Chunks vs gold), U2 (Setting space), U3 (Evidence) (M5.1; UI-SPEC §5), juga di mode statis.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { blankState, type State } from "../state";
import { setStaticMode } from "../lib/staticData";
import { mkSnapshot } from "./fixtures";

const mock = vi.hoisted(() => ({ state: null as unknown as State }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { ChunksVsGold } from "../components/ChunksVsGold";
import { EvidencePanel } from "../components/Evidence";
import { SettingSpace } from "../components/SettingSpace";

const set = (snapshot: State["snapshot"], over: Partial<State> = {}) => {
  mock.state = { ...blankState(), snapshot, ...over };
};
const html = () => [renderToStaticMarkup(<ChunksVsGold />), renderToStaticMarkup(<SettingSpace />), renderToStaticMarkup(<EvidencePanel />)];

afterEach(() => setStaticMode(false));

describe("U1-U3 keadaan global", () => {
  it("loading", () => {
    set({ status: "loading" });
    const [u1, u2, u3] = html();
    expect(u1).toContain("Loading items");
    expect(u2).toContain("Loading grid");
    expect(u3).toContain("Loading end-to-end evidence");
  });
  it("error: pesan tampil, tanpa stack trace", () => {
    set({ status: "error", code: "http_500", message: "kaput" });
    const [u1, u2, u3] = html();
    for (const h of [u1, u2, u3]) {
      expect(h).toContain("kaput");
      expect(h).not.toMatch(/Traceback|at \w+ \(/);
    }
    expect(u2).toContain("Grid run failed");
  });
  it("error tak terjangkau", () => {
    set({ status: "error", code: "unreachable", message: "Backend unreachable." });
    expect(html()[0]).toContain("Backend unreachable.");
    expect(html()[1]).toContain("Backend unreachable.");
  });
  it("kosong: tanpa grid dan tanpa butir terpilih", () => {
    set({ status: "ready", data: mkSnapshot() });
    const [u1, u2, u3] = html();
    expect(u1).toContain("Select an item to see chunk boundaries");
    expect(u2).toContain("No grid run for this family yet");
    expect(u3).toContain("Select an item to see end-to-end evidence.");
  });
  it("mode statis: panel U3 tetap tampil dan Run live nonaktif dengan teks statis", () => {
    setStaticMode(true);
    set({ status: "ready", data: mkSnapshot() });
    expect(html()[2]).toContain("Select an item to see end-to-end evidence.");
  });
});
