// Header U0: Model dan Run cost dari satu fetch /api/health (W29). Tanpa DOM, tanpa jaringan.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import appSrc from "../App.tsx?raw";
import headerSrc from "../components/Header.tsx?raw";
import { blankState } from "../state";

const mock = vi.hoisted(() => ({ state: null as unknown }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { Header, buildInfoFromHealth } from "../components/Header";

const H = { status: "ok", replay: true, model: "muse-x", config_hash: "h", model_profiles: [] };

describe("Run cost di header", () => {
  it("buildInfoFromHealth memakai ledger_spent_usd_micros server apa adanya (integer), bukan jumlah mentah (UX-02)", () => {
    expect(buildInfoFromHealth({ ...H, ledger_spent_usd_micros: 1_234_567, run_cost_usd_micros: 1_000_000 })).toEqual({ model: "muse-x", costMicros: 1_234_567 });
    expect(buildInfoFromHealth({ ...H, ledger_spent_usd_micros: 0 }).costMicros).toBe(0);
    expect(buildInfoFromHealth({ ...H, run_cost_usd_micros: 1_000_000 }).costMicros).toBeNull(); // jumlah mentah tidak pernah dipakai
  });
  it("field tidak ada, null, atau bukan integer -> null", () => {
    for (const v of [undefined, null, 1.5, "7" as unknown as number]) {
      expect(buildInfoFromHealth({ ...H, ledger_spent_usd_micros: v }).costMicros).toBeNull();
    }
    expect(buildInfoFromHealth(null)).toEqual({ model: null, costMicros: null });
  });
  it("Header menampilkan biaya dari prop, n/a bila tak ada", () => {
    mock.state = blankState();
    const ok = renderToStaticMarkup(<Header build={{ model: "muse-x", costMicros: 1_234_567 }} />);
    expect(ok).toContain("Run cost:");
    expect(ok).toContain("$1.234567");
    expect(ok).toContain("muse-x");
    const na = renderToStaticMarkup(<Header build={{ model: null, costMicros: null }} />);
    expect(na).toMatch(/Run cost: <strong[^>]*>n\/a</);
    expect(renderToStaticMarkup(<Header />)).toMatch(/Run cost: <strong[^>]*>n\/a</);
  });
  it("satu fetch: useBuildInfo dipanggil sekali di App, tidak di Header; tanpa fetchRuns / penjumlahan di frontend", () => {
    expect(appSrc.match(/useBuildInfo\(\)/g)).toHaveLength(1);
    expect(headerSrc.match(/useBuildInfo\(\)/g)).toHaveLength(1); // hanya definisinya
    expect(headerSrc).not.toContain("fetchRuns");
    expect(headerSrc).not.toContain("reduce(");
  });
});

describe("Tagline (UX-01) dan header berkelompok (UX-22)", () => {
  it("draf tidak tampil; final tampil apa adanya", async () => {
    const { Tagline } = await import("../components/Header");
    expect(renderToStaticMarkup(<Tagline content={{ status: "draft", text: "x" }} />)).toBe("");
    expect(renderToStaticMarkup(<Tagline />)).toContain("Find the chunking and retrieval setting that feeds an LLM the right clauses of Indonesian legal documents, measured, not guessed."); // disetujui operator 28 Okt (final)
    expect(renderToStaticMarkup(<Tagline content={{ status: "final", text: "Find it." }} />)).toContain("Find it.");
  });
  it("ikon hint app.purpose berada satu kelompok dengan nama app", () => {
    mock.state = blankState();
    const h = renderToStaticMarkup(<Header />);
    expect(h).toMatch(/<span class="hdr-group"><span class="brand">LexRAGLab<\/span><[^>]*hint/);
  });
});
