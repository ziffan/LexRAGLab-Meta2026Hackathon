// F3 (video v1): live tanpa key. Semua profil tidak tersedia -> <select> U3 tetap bernilai salah satu opsi (bukan ""),
// Run live nonaktif dengan unavailable_reason; replay/available tidak berubah.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EvidenceControls } from "../components/Evidence";
import { runLiveState, selectedProfile } from "../lib/evidence";
import type { Health } from "../types";

const NOKEY = "Model API credentials are not configured.";
const mk = (avail: boolean[]): Health => ({
  status: "ok", replay: false, model: "m", config_hash: "h",
  model_profiles: [
    { model_profile: "meta", model: "muse", available: avail[0], label: "Contributor", effort: "low", roles: [], local: false, unavailable_reason: avail[0] ? null : NOKEY },
    { model_profile: "baseten_open", model: "open", available: avail[1], label: "Spark Open (Baseten)", effort: "low", roles: ["c"], local: false, unavailable_reason: avail[1] ? null : NOKEY },
  ],
} as unknown as Health);

const state = (h: Health, profile: string | null = null) => {
  const sel = selectedProfile(h, profile);
  return { sel, live: runLiveState(true, true, h.model_profiles.find((p) => p.model_profile === sel)) };
};

describe("U3 live tanpa key (F3)", () => {
  it("semua profil unavailable: select bernilai opsi pertama, Run live disabled dengan alasan", () => {
    const h = mk([false, false]);
    const { sel, live } = state(h);
    expect(sel).toBe("meta");
    expect(live).toEqual({ enabled: false, reason: NOKEY });
    const html = renderToStaticMarkup(<EvidenceControls health={h} profile={null} onProfile={() => undefined} runLive={live} onRunLive={() => undefined} busy={false} />);
    expect(html).toMatch(/<option[^>]*value="meta"[^>]*selected|<option[^>]*selected[^>]*value="meta"/);
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Run live<\/button>/);
    expect(html).toContain(NOKEY);
  });
  it("profil terpilih unavailable meski lain tersedia: Run live disabled; default tersedia tetap dipakai", () => {
    const h = mk([false, true]);
    expect(state(h).sel).toBe("baseten_open");
    expect(state(h).live.enabled).toBe(true);
    expect(state(h, "meta").live).toEqual({ enabled: false, reason: NOKEY });
  });
  it("replay/available: perilaku lama (aktif bila scene_checked)", () => {
    const h = mk([true, true]);
    expect(state(h).sel).toBe("meta");
    expect(state(h).live.enabled).toBe(true);
    expect(runLiveState(true, true).enabled).toBe(true);
    expect(selectedProfile(null, null)).toBe("");
  });
});
