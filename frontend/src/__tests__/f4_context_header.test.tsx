// F4 (video v1): U1 menampilkan baris abu "Context header (B)" di atas potongan bila R4 `headers` ada; tidak bila null.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Chunk, DocResponse, Item } from "../types";
import { SETTINGS } from "./fixtures";

vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: real.blankState(), dispatch: () => undefined }) };
});
import { ChunkColumn } from "../components/ChunkColumn";

const SHA = "a".repeat(64);
const text = "Pasal 102 ayat satu. Direksi wajib meminta persetujuan RUPS.";
const chunk: Chunk = {
  chunk_id: "cid-102", doc_id: "d", chunker_key: "k", start: 0, end: text.length, clean_sha256: SHA, section: "s",
  address: "UU 40/2007 › Pasal 102", address_levels: [], tokens_local: 12, warnings: [],
};
const item: Item = { id: "kontrol-K-01", family: "uupt", query: "q", doc_id: "d", gold_spans: [{ start: 0, end: 10 }], clean_sha256: SHA, mode: "literal", origin: "operator" } as Item;
const HDR = "UU No. 40 Tahun 2007, Pasal 102 di Bab Direksi, tentang pengalihan kekayaan Perseroan.";

const render = (headers: DocResponse["headers"]) =>
  renderToStaticMarkup(
    <ChunkColumn setting={SETTINGS[0]} heading="Best" retrieval={{ status: "idle" }} item={item} cleanSha256={SHA}
      doc={{ status: "ready", data: { doc_id: "d", text, chunks: [chunk], headers } }} />,
  );

describe("Context header (B) di U1 (F4)", () => {
  it("header ada: baris berlabel tampil di atas chunk-head", () => {
    const h = render([{ chunk_id: "cid-102", header: HDR, tokens_local: 40 }]);
    expect(h).toContain("Context header (B)");
    expect(h).toContain(HDR);
    expect(h.indexOf("Context header (B)")).toBeLessThan(h.indexOf('class="chunk-head"'));
  });
  it("headers null atau tanpa chunk_id yang cocok: tidak tampil", () => {
    expect(render(null)).not.toContain("Context header (B)");
    expect(render([{ chunk_id: "lain", header: HDR, tokens_local: 40 }])).not.toContain("Context header (B)");
  });
});
