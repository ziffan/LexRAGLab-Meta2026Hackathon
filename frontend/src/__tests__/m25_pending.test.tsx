// M2.5 lanjutan: Run live Glimmer nonaktif (G-26) dan banner "Pending operator review" untuk akta tanpa grid (U2/U4/U7).
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { blankState, type State } from "../state";
import { mkSnapshot } from "./fixtures";

const mock = vi.hoisted(() => ({ state: null as unknown as State }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import { PerItem } from "../components/PerItem";
import { ProfilePanel } from "../components/ProfileExport";
import { SettingSpace } from "../components/SettingSpace";
import { HINT_FILE, draftIds, getHint } from "../lib/hints";
import { CLI_ONLY_REASON, runLiveState } from "../lib/evidence";

const set = (data: ReturnType<typeof mkSnapshot>) => {
  mock.state = { ...blankState(), snapshot: { status: "ready", data }, family: data.family };
};
const PENDING = "Pending operator review";

describe("Run live Glimmer (G-26)", () => {
  const g = { model_profile: "glimmer_local", model: "meta/muse-glimmer", available: true, live_via_cli: true };
  it("dinonaktifkan dengan pesan Inggris singkat meski butir scene_checked", () => {
    expect(runLiveState(true, true, g)).toEqual({ enabled: false, reason: CLI_ONLY_REASON });
    expect(CLI_ONLY_REASON).toBe("Glimmer runs offline via CLI to avoid GPU contention with embeddings; stored results are shown.");
  });
  it("profil lain tetap aktif", () => {
    expect(runLiveState(true, true, { ...g, live_via_cli: false }).enabled).toBe(true);
    expect(runLiveState(true, true).enabled).toBe(true);
  });
});

describe("akta tanpa grid: Pending operator review", () => {
  it("U2, U4, U7 menampilkan banner dan tidak ada angka sementara", () => {
    set(mkSnapshot({ family: "akta", grid: null }));
    for (const el of [<SettingSpace key="a" />, <PerItem key="b" />, <ProfilePanel key="c" />]) {
      const h = renderToStaticMarkup(el);
      expect(h).toContain(PENDING);
      expect(h).toContain("no interim numbers");
    }
  });
  it("uupt tanpa grid tidak memakai banner ini", () => {
    set(mkSnapshot({ family: "uupt", grid: null }));
    expect(renderToStaticMarkup(<PerItem />)).not.toContain(PENDING);
  });
  it("entri hint baru berstatus draft; versi 1.6.0 (UX-10/23, putusan operator 12)", () => {
    expect(HINT_FILE.version).toBe("1.6.0");
    expect(getHint("ui.pending_review")?.status).toBe("draft");
    expect(draftIds()).toEqual(["ui.pending_review"]);
  });
});
