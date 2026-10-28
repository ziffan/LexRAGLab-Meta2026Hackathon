// Mode ekspor statis (M5.1, H-051): tidak ada fetch ke /api, aksi tulis nonaktif, pemetaan jalur sesuai backend/replay/export.py.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFailure, fetchDoc, fetchHealth, fetchRetrieval, fetchRuns, fetchSnapshot, postAnswers, postCorrection } from "../api";
import { runLiveState } from "../lib/evidence";
import { ReviewController } from "../lib/review";
import { STATIC_DISABLED, resolveStatic, setStaticMode, staticAwareFetch } from "../lib/staticData";

const B = "b".repeat(64);
const S = "s".repeat(64);
const P = "contributor";

const files: Record<string, unknown> = {
  "data/health.json": { status: "ok", replay: true, static: true, model: "m", config_hash: "h", model_profiles: [] },
  "data/runs.json": [],
  "data/snapshot/uupt/default.json": { family: "uupt", replay: true },
  "data/snapshot/uupt/4000.json": { family: "uupt", budget_tokens: 4000 },
  "data/docs/uupt/d1/_text.json": { doc_id: "d1", text: "teks", chunks: null, headers: null },
  [`data/docs/uupt/d1/${B.slice(0, 16)}.json`]: { doc_id: "d1", chunks: [{ chunk_id: "c1" }], headers: null },
  [`data/retrieval/uupt/${B.slice(0, 16)}/it-1.json`]: { retrieved_chunk_ids: ["c1"] },
  [`data/answers/uupt/it-1/${B.slice(0, 16)}/${S.slice(0, 16)}/${P}.json`]: { best: { answer_id: "a" } },
  "data/proposals/uupt.json": { proposals: [], pending: 0, context_lines: 3 },
};

/** Server berkas palsu: mencatat setiap URL yang diminta. */
function fakeRaw() {
  const calls: string[] = [];
  const raw = async (url: string): Promise<Response> => {
    calls.push(url);
    return url in files ? new Response(JSON.stringify(files[url]), { status: 200 }) : new Response("<html>spa</html>", { status: 200 });
  };
  return { raw, calls };
}

afterEach(() => {
  setStaticMode(false);
  vi.unstubAllGlobals();
});

describe("resolveStatic", () => {
  it("maps reads to data files, shortening setting ids", () => {
    expect(resolveStatic("/api/health")).toEqual({ kind: "file", path: "data/health.json" });
    expect(resolveStatic("/api/runs?limit=500")).toEqual({ kind: "file", path: "data/runs.json" });
    expect(resolveStatic("/api/families/uupt/snapshot")).toEqual({ kind: "file", path: "data/snapshot/uupt/default.json" });
    expect(resolveStatic("/api/families/uupt/snapshot?budget_tokens=4000")).toEqual({ kind: "file", path: "data/snapshot/uupt/4000.json" });
    expect(resolveStatic(`/api/families/uupt/retrieval?setting_id=${B}&item_id=it-1`)).toEqual({ kind: "file", path: `data/retrieval/uupt/${B.slice(0, 16)}/it-1.json` });
    expect(resolveStatic("/api/families/uupt/proposals")).toEqual({ kind: "file", path: "data/proposals/uupt.json" });
  });
  it("UX-09: W7 GET reads the stored profile file (read-only); without setting_id it is unknown", () => {
    expect(resolveStatic(`/api/families/akta/profiles/export?setting_id=${B}`)).toEqual({ kind: "file", path: `data/profiles/akta/${B.slice(0, 16)}.json` });
    expect(resolveStatic("/api/families/uupt/profiles/export")).toEqual({ kind: "unknown" });
  });
  it("blocks every write and live W6", () => {
    for (const [u, m] of [["/api/families/uupt/grid/run", "POST"], ["/api/proposals/p1/decision", "POST"], ["/api/families/uupt/schemas/1/correct", "POST"],
      ["/api/profiles/import", "POST"], ["/api/families/uupt/profiles/export?setting_id=x", "POST"]] as const) {
      const t = resolveStatic(u, { method: m });
      expect(["blocked", "unknown"]).toContain(t.kind);
      if (m === "POST") expect(t.kind).toBe("blocked");
    }
    const live = resolveStatic("/api/families/uupt/answers", { method: "POST", body: JSON.stringify({ item_id: "i", best_setting_id: B, baseline_setting_id: S, model_profile: P, live: true }) });
    expect(live.kind).toBe("blocked");
  });
});

describe("static mode never reaches /api", () => {
  it("serves every read from data/ and passes nothing under /api to the network", async () => {
    setStaticMode(true);
    const { raw, calls } = fakeRaw();
    vi.stubGlobal("fetch", (u: string) => raw(u));
    expect((await fetchSnapshot("uupt", null)).family).toBe("uupt");
    expect((await fetchSnapshot("uupt", 4000)).budget_tokens).toBe(4000);
    expect((await fetchHealth()).status).toBe("ok");
    expect(await fetchRuns()).toEqual([]);
    expect((await fetchRetrieval("uupt", B, "it-1")).retrieved_chunk_ids).toEqual(["c1"]);
    const doc = await fetchDoc("uupt", "d1", B);
    expect(doc.text).toBe("teks");
    expect(doc.chunks).toEqual([{ chunk_id: "c1" }]);
    const ans = await postAnswers("uupt", { item_id: "it-1", best_setting_id: B, baseline_setting_id: S, model_profile: P, live: false });
    expect(ans.best.answer_id).toBe("a");
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.filter((u) => u.includes("/api"))).toEqual([]);
    expect(calls.every((u) => u.startsWith("data/"))).toBe(true);
  });

  it("answers with no stored file become replay_no_stored_run (the empty state), not a crash", async () => {
    setStaticMode(true);
    const { raw } = fakeRaw();
    vi.stubGlobal("fetch", (u: string) => raw(u));
    const err = await postAnswers("uupt", { item_id: "none", best_setting_id: B, baseline_setting_id: S, model_profile: P, live: false }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiFailure);
    expect((err as ApiFailure).code).toBe("replay_no_stored_run");
  });

  it("a missing snapshot is a clean not_found (SPA fallback HTML is not mistaken for JSON)", async () => {
    setStaticMode(true);
    const { raw } = fakeRaw();
    vi.stubGlobal("fetch", (u: string) => raw(u));
    const err = await fetchSnapshot("akta", null).catch((e: unknown) => e);
    expect((err as ApiFailure).code).toBe("not_found");
  });
});

describe("write actions are disabled in static mode", () => {
  it("W9, W6 live and the Review decision fail with the static message and never hit the network", async () => {
    setStaticMode(true);
    const spy = vi.fn(async (_u?: string, _i?: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", spy);
    const e1 = await postCorrection("uupt", 1, {}, null).catch((e: unknown) => e);
    expect(e1).toBeInstanceOf(ApiFailure);
    expect((e1 as ApiFailure).code).toBe("static_replay");
    expect((e1 as ApiFailure).message).toBe(STATIC_DISABLED);
    const e2 = await postAnswers("uupt", { item_id: "i", best_setting_id: B, baseline_setting_id: S, model_profile: P, live: true }).catch((e: unknown) => e);
    expect((e2 as ApiFailure).code).toBe("static_replay");
    const wrapped = staticAwareFetch((u, i) => spy(u, i), () => true);
    const res = await wrapped("/api/proposals/p1/decision", { method: "POST", body: "{}" });
    expect(res.status).toBe(403);
    expect(spy).not.toHaveBeenCalled();
  });

  it("the Review controller cannot save a decision (nothing sent, proposal stays)", async () => {
    setStaticMode(true);
    const spy = vi.fn(async (_u?: string, _i?: RequestInit) => new Response("{}", { status: 200 }));
    const ctl = new ReviewController(staticAwareFetch((u, i) => spy(u, i), () => true));
    const ok = await (ctl as unknown as { send(id: string, b: object): Promise<boolean> }).send("p1", { decision: "ditolak", edited: null, operator_note: null });
    expect(ok).toBe(false);
    expect(spy).not.toHaveBeenCalled();
    expect(ctl.getState().errors["p1"]).toContain(STATIC_DISABLED);
  });

  it("Run live is disabled with the static text even for a scene_checked item with a reachable health file", () => {
    setStaticMode(true);
    expect(runLiveState(true, true)).toEqual({ enabled: false, reason: STATIC_DISABLED });
    setStaticMode(false);
    expect(runLiveState(true, true).enabled).toBe(true);
  });
});

describe("live mode is untouched", () => {
  it("passes /api through to fetch when static is off", async () => {
    const spy = vi.fn(async (_u?: string, _i?: RequestInit) => new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", spy);
    await fetchHealth();
    expect(spy).toHaveBeenCalledWith("/api/health", undefined);
  });
});
