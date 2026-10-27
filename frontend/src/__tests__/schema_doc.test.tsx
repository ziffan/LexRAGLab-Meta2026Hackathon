// W14: panel potongan akta menurut skema (R4 schema_version): keadaan kosong, pemilih versi, pemetaan statis.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SchemaDocView } from "../components/ChunksVsGold";
import { resolveStatic } from "../lib/staticData";
import { mkSnapshot } from "./fixtures";

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
