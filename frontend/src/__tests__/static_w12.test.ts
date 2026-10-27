// W12: cabang `unknown` GET di mode statis dan jalur `apiFetch` (dipakai Review) tidak pernah menyentuh fetch asli untuk /api.
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../api";
import { ReviewController } from "../lib/review";
import { STATIC_DISABLED, resolveStatic, setStaticMode, staticAwareFetch } from "../lib/staticData";

afterEach(() => {
  setStaticMode(false);
  vi.unstubAllGlobals();
});

describe("unknown GET under /api in static mode", () => {
  it("resolves to unknown and never calls the raw fetch", async () => {
    expect(resolveStatic("/api/x").kind).toBe("unknown");
    expect(resolveStatic("/api/families/uupt/profiles/export?setting_id=s").kind).toBe("unknown");
    const raw = vi.fn(async (_u: string, _i?: RequestInit) => new Response("{}", { status: 200 }));
    const f = staticAwareFetch((u, i) => raw(u, i), () => true);
    for (const u of ["/api/x", "/api/families/uupt/profiles/export?setting_id=s", "/api/families/uupt/retrieval"]) {
      const res = await f(u);
      expect(res.status).toBe(404);
      expect(((await res.json()) as { error: { code: string } }).error.code).toBe("not_found");
    }
    expect(raw).not.toHaveBeenCalled();
  });
});

describe("apiFetch (the Review path) in static mode", () => {
  it("never reaches the global fetch for /api: writes are 403, unknown reads 404", async () => {
    setStaticMode(true);
    const spy = vi.fn(async (_u?: string, _i?: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", spy);
    const w = await apiFetch("/api/proposals/p1/decision", { method: "POST", body: "{}" });
    expect(w.status).toBe(403);
    expect(((await w.json()) as { error: { message: string } }).error.message).toBe(STATIC_DISABLED);
    expect((await apiFetch("/api/x")).status).toBe(404);
    expect(spy).not.toHaveBeenCalled();
  });

  it("reads proposals from data/ only; a ReviewController built on apiFetch cannot save", async () => {
    setStaticMode(true);
    const spy = vi.fn(async (u?: string, _i?: RequestInit) =>
      new Response(JSON.stringify({ proposals: [], pending: 0, context_lines: 3, u }), { status: 200 }));
    vi.stubGlobal("fetch", spy);
    expect((await apiFetch("/api/families/uupt/proposals")).status).toBe(200);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0]).toBe("data/proposals/uupt.json");
    const ctl = new ReviewController(apiFetch);
    const ok = await (ctl as unknown as { send(id: string, b: object): Promise<boolean> }).send("p1", { decision: "ditolak", edited: null, operator_note: null });
    expect(ok).toBe(false);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(ctl.getState().errors["p1"]).toContain(STATIC_DISABLED);
  });

  it("in live mode apiFetch passes /api straight to fetch", async () => {
    const spy = vi.fn(async (_u?: string, _i?: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", spy);
    await apiFetch("/api/x");
    expect(spy).toHaveBeenCalledWith("/api/x", undefined);
  });
});
