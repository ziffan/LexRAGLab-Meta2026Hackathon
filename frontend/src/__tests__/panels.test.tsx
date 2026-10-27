// Keadaan loading/error/kosong panel U3, U5, U8 lewat store palsu (render server; efek tidak berjalan, tanpa jaringan).
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { blankState, type State } from "../state";
import { mkSchema, mkSnapshot } from "./fixtures";

const mock = vi.hoisted(() => ({ state: null as unknown as State }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { EvidencePanel } from "../components/Evidence";
import { RunLogPanel } from "../components/RunLog";
import { SchemaPanel } from "../components/SchemaPanel";

const set = (snapshot: State["snapshot"], over: Partial<State> = {}) => {
  mock.state = { ...blankState(), snapshot, ...over };
};

describe("panel U3/U5/U8", () => {
  it("loading", () => {
    set({ status: "loading" });
    expect(renderToStaticMarkup(<EvidencePanel />)).toContain("Loading end-to-end evidence");
    expect(renderToStaticMarkup(<SchemaPanel />)).toContain("Loading schema versions");
    expect(renderToStaticMarkup(<RunLogPanel />)).toContain("Loading run log");
  });
  it("error snapshot", () => {
    set({ status: "error", code: "http_500", message: "kaput" });
    expect(renderToStaticMarkup(<EvidencePanel />)).toContain("kaput");
    expect(renderToStaticMarkup(<SchemaPanel />)).toContain("Schema failed validation");
  });
  it("kosong: tanpa butir terpilih, tanpa skema", () => {
    set({ status: "ready", data: mkSnapshot() });
    expect(renderToStaticMarkup(<EvidencePanel />)).toContain("Select an item to see end-to-end evidence.");
    const h = renderToStaticMarkup(<SchemaPanel />);
    expect(h).toContain("Structure schema (A)");
    expect(h).toContain("No schema induced for this family yet");
  });
  it("skema ada: versi, tombol Edit, tanpa editor sebelum diklik", () => {
    set({ status: "ready", data: mkSnapshot({ schemas: [mkSchema(1, "spark")] }) });
    const h = renderToStaticMarkup(<SchemaPanel />);
    expect(h).toContain("v1 · proposed by Muse Spark");
    expect(h).toContain(">Edit<");
    expect(h).not.toContain("Save as new version");
  });
  it("butir scene_checked, backend belum terjangkau (statis/health belum ada): Run live nonaktif", () => {
    const item = { id: "item-1", family: "uupt", query: "q", doc_id: "d", gold_spans: [], clean_sha256: "x", mode: "literal" as const, origin: "operator" as const, scene_checked: true };
    set({ status: "ready", data: mkSnapshot({ items: [item], replay: true }) }, { selectedItemId: "item-1", selectedSettingId: "S-struct" });
    expect(renderToStaticMarkup(<EvidencePanel />)).toMatch(/<button[^>]*disabled[^>]*>Run live<\/button>/);
  });
  it("Edit skema nonaktif di replay", () => {
    set({ status: "ready", data: mkSnapshot({ schemas: [mkSchema(1, "spark")], replay: true }) });
    expect(renderToStaticMarkup(<SchemaPanel />)).toMatch(/<button[^>]*disabled[^>]*>Edit<\/button>/);
  });
  it("butir terpilih: tombol Run live ada dan nonaktif (tanpa scene_checked)", () => {
    const item = { id: "item-1", family: "uupt", query: "q", doc_id: "d", gold_spans: [], clean_sha256: "x", mode: "literal" as const, origin: "operator" as const };
    set({ status: "ready", data: mkSnapshot({ items: [item] }) }, { selectedItemId: "item-1", selectedSettingId: "S-struct" });
    const h = renderToStaticMarkup(<EvidencePanel />);
    expect(h).toMatch(/<button[^>]*disabled[^>]*>Run live<\/button>/);
  });
});
