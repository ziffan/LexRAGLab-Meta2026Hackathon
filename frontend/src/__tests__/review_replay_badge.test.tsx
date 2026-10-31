// I-70: lencana REPLAY juga tampil di header layar /review (ReviewScreen), bukan hanya di Header utama. Tanpa DOM, tanpa jaringan.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { blankState } from "../state";

const mock = vi.hoisted(() => ({ state: null as unknown }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { ReviewScreen } from "../components/Review";

const withSnapshot = (replay: boolean | null) => {
  const s = blankState();
  mock.state = replay === null ? s : { ...s, snapshot: { status: "ready", data: { replay } } };
};

const headerOf = (html: string): string => html.match(/<header[^>]*>[\s\S]*?<\/header>/)?.[0] ?? "";

describe("I-70 lencana REPLAY di /review", () => {
  afterEach(() => vi.unstubAllGlobals());
  const render = () => {
    vi.stubGlobal("window", { location: { search: "?view=review" }, history: {} });
    return headerOf(renderToStaticMarkup(<ReviewScreen />));
  };

  it("snapshot replay:true -> header review memuat REPLAY", () => {
    withSnapshot(true);
    const h = render();
    expect(h).toContain("LexRAGLab");
    expect(h).toContain('<span class="tag replay">REPLAY</span>');
  });
  it("snapshot replay:false -> tanpa lencana", () => {
    withSnapshot(false);
    expect(render()).not.toContain("REPLAY");
  });
  it("snapshot belum dimuat -> tanpa lencana", () => {
    withSnapshot(null);
    expect(render()).not.toContain("REPLAY");
  });
});
