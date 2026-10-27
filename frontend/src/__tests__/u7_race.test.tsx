// W16: penjaga race ekspor U7: respons untuk setting lama diabaikan setelah pilihan berganti (logika murni, tanpa DOM).
import { describe, expect, it } from "vitest";
import { createRequestGuard, runGuardedExport, type ExportPhase, type U7Client } from "../components/ProfileExport";
import type { Profile } from "../types";

const prof = (id: string) => ({ profile_version: "1", family: "uupt", setting: { setting_id: id } }) as unknown as Profile;

function deferredClient() {
  const waiting = new Map<string, (p: Profile) => void>();
  const c: U7Client = {
    exportProfile: (_f, s) => new Promise<Profile>((r) => waiting.set(s, r)),
    importProfile: async () => ({ ok: true, chunk_set_hash_matches: true }),
  };
  return { c, resolve: (s: string) => waiting.get(s)!(prof(s)) };
}
const flush = () => new Promise<void>((r) => setTimeout(r, 0));

describe("createRequestGuard", () => {
  it("hanya ID terbaru yang berlaku; invalidate membuat semua basi", () => {
    const g = createRequestGuard();
    const a = g.begin();
    expect(g.isCurrent(a)).toBe(true);
    const b = g.begin();
    expect(g.isCurrent(a)).toBe(false);
    expect(g.isCurrent(b)).toBe(true);
    g.invalidate();
    expect(g.isCurrent(b)).toBe(false);
  });
});

describe("runGuardedExport", () => {
  it("respons lambat setelah pilihan berganti (invalidate): tidak di-set dan tidak diunduh", async () => {
    const g = createRequestGuard();
    const { c, resolve } = deferredClient();
    const phases: ExportPhase[] = [];
    const downloaded: Profile[] = [];
    const p = runGuardedExport(g, c, "uupt", "OLD", (x) => phases.push(x), (pr) => downloaded.push(pr));
    await flush();
    expect(phases.map((x) => x.kind)).toEqual(["building"]);
    g.invalidate(); // pilihan berganti
    resolve("OLD");
    await p;
    expect(phases.map((x) => x.kind)).toEqual(["building"]);
    expect(downloaded).toEqual([]);
  });
  it("dua ekspor tumpang tindih: hanya yang terbaru menulis fase dan mengunduh", async () => {
    const g = createRequestGuard();
    const { c, resolve } = deferredClient();
    const phases: ExportPhase[] = [];
    const downloaded: string[] = [];
    const first = runGuardedExport(g, c, "uupt", "OLD", (x) => phases.push(x), (pr) => downloaded.push(pr.setting.setting_id));
    const second = runGuardedExport(g, c, "uupt", "NEW", (x) => phases.push(x), (pr) => downloaded.push(pr.setting.setting_id));
    await flush();
    resolve("NEW");
    await second;
    resolve("OLD");
    await first;
    const ready = phases.filter((x): x is Extract<ExportPhase, { kind: "ready" }> => x.kind === "ready");
    expect(ready).toHaveLength(1);
    expect(ready[0].profile.setting.setting_id).toBe("NEW");
    expect(phases[phases.length - 1].kind).toBe("ready");
    expect(downloaded).toEqual(["NEW"]);
  });
  it("tanpa gangguan: fase building lalu ready dan unduh sekali; galat juga dijaga", async () => {
    const g = createRequestGuard();
    const { c, resolve } = deferredClient();
    const phases: ExportPhase[] = [];
    const downloaded: Profile[] = [];
    const p = runGuardedExport(g, c, "uupt", "S", (x) => phases.push(x), (pr) => downloaded.push(pr));
    await flush();
    resolve("S");
    await p;
    expect(phases.map((x) => x.kind)).toEqual(["building", "ready"]);
    expect(downloaded).toHaveLength(1);
    const bad: U7Client = { ...c, exportProfile: async () => { throw new Error("x"); } };
    const ph2: ExportPhase[] = [];
    const out = await runGuardedExport(g, bad, "uupt", "S", (x) => ph2.push(x), (pr) => downloaded.push(pr));
    expect(out.kind).toBe("error");
    expect(downloaded).toHaveLength(1);
  });
});

import panelSrc from "../components/ProfileExport.tsx?raw";
describe("ProfilePanel wiring (sumber)", () => {
  it("efek ganti pilihan membatalkan ekspor terbang; onExport memakai runGuardedExport", () => {
    const effect = /useEffect\(\(\) => \{([\s\S]*?)\}, \[state\.family, settingId\]\)/.exec(panelSrc)![1];
    expect(effect).toContain("guard.current.invalidate()");
    expect(panelSrc).toContain("runGuardedExport(guard.current");
  });
});
