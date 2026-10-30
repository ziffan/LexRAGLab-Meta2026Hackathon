// M5.1-N1 (N-1, N-3): header "loading…" saat /api/health tertunda (bukan n/a), satu request health bersama,
// Run live dengan alasan jujur saat ketersediaan model belum diketahui, RunLog tanpa agregat sementara "latest N runs only".
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import evidenceSrc from "../components/Evidence.tsx?raw";
import { blankState } from "../state";
import type { Health, RunRecord } from "../types";

const mock = vi.hoisted(() => ({ state: null as unknown }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { fetchHealth } from "../api";
import { HEALTH_LOADING, Header, settleBuildInfo, useBuildInfo } from "../components/Header";
import { RunLogView } from "../components/RunLog";
import { CHECKING_REASON, runLiveState } from "../lib/evidence";
import { STATIC_DISABLED, setStaticMode } from "../lib/staticData";

const H = { status: "ok", replay: false, model: "muse-x", config_hash: "h", model_profiles: [], main_results_spent_usd_micros: 561_741 } as unknown as Health;
const cost = (html: string) => html.match(/Run cost \(main results\): <strong[^>]*>([^<]*)</)?.[1];
const model = (html: string) => html.match(/Model: <strong[^>]*>([^<]*)</)?.[1];

afterEach(() => {
  setStaticMode(false);
  vi.unstubAllGlobals();
});

describe("Header saat health tertunda (F1)", () => {
  it("pending -> loading… untuk Model dan Run cost; selesai -> angka; tidak terbaca -> n/a; default prop -> n/a", () => {
    mock.state = blankState();
    const p = renderToStaticMarkup(<Header build={{ model: null, costMicros: null, pending: true }} />);
    expect(cost(p)).toBe(HEALTH_LOADING);
    expect(model(p)).toBe(HEALTH_LOADING);
    expect(HEALTH_LOADING).toBe("loading…");
    expect(cost(renderToStaticMarkup(<Header build={{ model: "muse-x", costMicros: 561_741, pending: false }} />))).toBe("$0.561741");
    expect(cost(renderToStaticMarkup(<Header build={{ model: null, costMicros: null, pending: false }} />))).toBe("n/a");
    expect(cost(renderToStaticMarkup(<Header />))).toBe("n/a");
  });
  it("useBuildInfo mulai pending (render pertama sebelum health = loading…, bukan n/a)", () => {
    mock.state = blankState();
    function Probe() {
      return <Header build={useBuildInfo()} />;
    }
    expect(cost(renderToStaticMarkup(<Probe />))).toBe(HEALTH_LOADING);
  });
  it("settleBuildInfo: resolve -> nilai + pending false; reject -> null + pending false", async () => {
    await expect(settleBuildInfo(Promise.resolve(H))).resolves.toEqual({ model: "muse-x", costMicros: 561_741, pending: false });
    await expect(settleBuildInfo(Promise.reject(new Error("down")))).resolves.toEqual({ model: null, costMicros: null, pending: false });
  });
});

describe("fetchHealth berbagi request in-flight (F2)", () => {
  it("3 pemanggil saat tertunda -> 1 fetch; setelah resolve -> fetch baru; setelah reject -> fetch baru", async () => {
    const pending: Array<(r: Response) => void> = [];
    const calls: string[] = [];
    vi.stubGlobal("fetch", (url: string) => {
      calls.push(url);
      return new Promise<Response>((res) => pending.push(res));
    });
    const a = fetchHealth(), b = fetchHealth(), c = fetchHealth();
    expect(calls).toEqual(["/api/health"]);
    await vi.waitFor(() => expect(pending).toHaveLength(1));
    pending[0](new Response(JSON.stringify(H), { status: 200 }));
    const got = await Promise.all([a, b, c]);
    expect(got.map((h) => h.model)).toEqual(["muse-x", "muse-x", "muse-x"]);
    const d = fetchHealth();
    expect(calls).toHaveLength(2);
    await vi.waitFor(() => expect(pending).toHaveLength(2));
    pending[1](new Response(JSON.stringify({ error: { code: "x", message: "boom" } }), { status: 500 }));
    await expect(d).rejects.toThrow("boom");
    const e = fetchHealth();
    expect(calls).toHaveLength(3);
    await vi.waitFor(() => expect(pending).toHaveLength(3));
    pending[2](new Response(JSON.stringify(H), { status: 200 }));
    await expect(e).resolves.toMatchObject({ model: "muse-x" });
  });
});

describe("Run live saat health tertunda (F3)", () => {
  const prof = { model_profile: "meta", model: "m", available: true };
  it("pending -> nonaktif dengan alasan checking, juga bila backendUp masih false", () => {
    expect(runLiveState(true, false, null, true)).toEqual({ enabled: false, reason: CHECKING_REASON });
    expect(runLiveState(true, true, prof as never, true)).toEqual({ enabled: false, reason: CHECKING_REASON });
    expect(CHECKING_REASON).toBe("Checking model availability…");
  });
  it("tanpa pending perilaku lama; statis menang atas pending", () => {
    expect(runLiveState(true, true, prof as never)).toMatchObject({ enabled: true });
    expect(runLiveState(true, false, null)).toEqual({ enabled: false, reason: STATIC_DISABLED });
    setStaticMode(true);
    expect(runLiveState(true, false, null, true)).toEqual({ enabled: false, reason: STATIC_DISABLED });
  });
  it("Evidence mengoper pending = !healthDone", () => {
    expect(evidenceSrc).toMatch(/runLiveState\([^;]*,\s*!healthDone\)/);
  });
});

describe("RunLog sebelum health selesai (F4, N-3)", () => {
  const run = { run_id: "r1", kind: "spark_c", created_at: "2026-10-30T00:00:00Z", model: "m", effort: "low", prompt_version: "v1",
    usage_input_tokens: 1, usage_cached_tokens: 0, usage_output_tokens: 1, cost_usd_micros: 5, latency_ms: 1, status: "ok" } as unknown as RunRecord;
  const view = (totalsPending: boolean) => renderToStaticMarkup(
    <RunLogView runs={[run]} totals={null} totalsPending={totalsPending} role="all" onRole={() => undefined} selected={null} onSelect={() => undefined} />);
  it("pending -> teks loading, tanpa label sementara 'latest N runs only'", () => {
    const h = view(true);
    expect(h).toContain("Loading per-role totals for all stored runs");
    expect(h).not.toContain("runs only");
  });
  it("selesai tanpa totals (health gagal) -> label lama 'latest N runs only' tetap jujur", () => {
    expect(view(false)).toContain("Per role (latest 1 runs only");
  });
});
