// W14: panel potongan akta menurut skema (R4 schema_version): keadaan kosong, pemilih versi, pemetaan statis.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { blankState, type State } from "../state";
import { resolveStatic } from "../lib/staticData";
import { mkSnapshot } from "./fixtures";

const mock = vi.hoisted(() => ({ state: null as unknown as State, ready: null as unknown }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});
// SSR tidak menjalankan efek: state dokumen (status idle) diganti hasil siap supaya cabang ready ikut dirender.
vi.mock("react", async (orig) => {
  const real = await orig<typeof import("react")>();
  return {
    ...real,
    useState: ((init: unknown) => {
      const isIdleDoc = typeof init === "object" && init !== null && (init as { status?: string }).status === "idle";
      return real.useState(isIdleDoc && mock.ready ? mock.ready : init);
    }) as typeof real.useState,
  };
});
import { ChunksVsGold, SchemaDocView } from "../components/ChunksVsGold";

describe("SchemaDocView", () => {
  it("shows the empty state when the family has no schema", () => {
    const snap = mkSnapshot({ family: "akta", settings: [], grid: null, items: [], metrics: [], schemas: [] });
    expect(renderToStaticMarkup(<SchemaDocView snap={snap} />)).toContain("No schema for this family yet");
  });
  it("lists stored schema versions and deed documents", () => {
    const snap = mkSnapshot({ family: "akta", settings: [], grid: null, items: [], metrics: [],
      schemas: [{ schema_version: 1 }, { schema_version: 2 }] as never, corpus: [{ doc_id: "akta-01" }, { doc_id: "akta-02" }] as never });
    const h = renderToStaticMarkup(<SchemaDocView snap={snap} />);
    expect(h).toContain("Schema version");
    expect(h).toContain(">v1<");
    expect(h).toContain(">v2<");
    expect(h).toContain(">akta-02<");
    expect(h).not.toContain("No schema for this family yet");
  });
});

describe("static mapping of schema_version", () => {
  it("maps R4 schema_version to the stable schema file", () => {
    expect(resolveStatic("/api/families/akta/docs/akta-01?schema_version=2")).toEqual({
      kind: "doc", text: "data/docs/akta/akta-01/_text.json", setting: "data/docs/akta/akta-01/schema-v2.json" });
    expect(resolveStatic("/api/families/akta/docs/akta-01")).toMatchObject({ setting: null });
    expect(resolveStatic("/api/families/akta/docs/akta-01?schema_version=x").kind).toBe("unknown");
  });
});

describe("SchemaDocView ready-state", () => {
  const snap = mkSnapshot({ family: "akta", settings: [], grid: null, items: [], metrics: [],
    schemas: [{ schema_version: 1 }] as never, corpus: [{ doc_id: "akta-01" }] as never });
  it("renders each chunk by code point slice (astral char counts as one)", () => {
    // Titik kode 0..6; indeks UTF-16 berbeda dari titik kode.
    mock.ready = { status: "ready", data: { doc_id: "akta-01", text: "A\u{1F600}B\u{1F600}C\u{1F600}D", headers: null, chunks: [
      { chunk_id: "c1", address: "Akta 01 › Pasal 1", start: 0, end: 3, tokens_local: 4 },
      { chunk_id: "c2", address: "Akta 01 › Pasal 2", start: 3, end: 7, tokens_local: 5 },
    ] } };
    try {
      const h = renderToStaticMarkup(<SchemaDocView snap={snap} />);
      expect(h).toContain(">A\u{1F600}B</div>");
      expect(h).toContain(">\u{1F600}C\u{1F600}D</div>");
      expect(h).toContain("Akta 01 › Pasal 1");
      expect(h).toContain("4 tokens (local tokenizer)");
      expect(h).toContain("5 tokens (local tokenizer)");
      expect(h).not.toContain("Loading chunks");
    } finally {
      mock.ready = null;
    }
  });
});

describe("ChunksVsGold routing", () => {
  const ready = (snapshot: ReturnType<typeof mkSnapshot>) => {
    mock.state = { ...blankState(), snapshot: { status: "ready", data: snapshot } };
  };
  it("akta family goes to the schema view (no item selector)", () => {
    ready(mkSnapshot({ family: "akta", settings: [], grid: null, items: [], metrics: [], schemas: [] }));
    const h = renderToStaticMarkup(<ChunksVsGold />);
    expect(h).toContain("No schema for this family yet");
    expect(h).not.toContain("Select an item to see chunk boundaries");
  });
  it("other families keep the item view", () => {
    ready(mkSnapshot());
    const h = renderToStaticMarkup(<ChunksVsGold />);
    expect(h).toContain("Select an item to see chunk boundaries");
    expect(h).not.toContain("No schema for this family yet");
  });
});
