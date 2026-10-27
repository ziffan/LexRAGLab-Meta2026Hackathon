// M2.5 U3: pemilih model (Contributor, Spark Open Baseten, Glimmer lokal), nonaktif bila server mati, label per jawaban.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EvidenceControls, EvidenceView } from "../components/Evidence";
import { answerProfiles, defaultProfile, modelDetail, modelLabel, profileLabel, runLiveState } from "../lib/evidence";
import type { Health } from "../types";
import { SETTINGS, mkAnswers } from "./fixtures";

const H: Health = {
  status: "ok", replay: false, model: "muse-spark-1.3-contributor", config_hash: "h",
  model_profiles: [
    { model_profile: "meta", model: "muse-spark-1.3-contributor", available: true, label: "Contributor", provider: "meta", quantization: null, effort: "low", roles: [], local: false, unavailable_reason: null },
    { model_profile: "baseten_open", model: "meta-models/muse-spark-open-1026", available: true, label: "Spark Open (Baseten)", provider: "baseten", quantization: null, effort: "low", roles: ["c"], local: false, unavailable_reason: null },
    { model_profile: "glimmer_local", model: "meta/muse-glimmer", available: false, label: "Glimmer (local)", provider: "lmstudio_local", quantization: "Q4_K_M", effort: "high", roles: ["c"], local: true, unavailable_reason: "Local model server is not running. Start it in LM Studio to enable this model." },
    { model_profile: "b_only", model: "x", available: true, label: "B only", roles: ["b"] },
  ],
};

const controls = (health: Health | null) =>
  renderToStaticMarkup(<EvidenceControls health={health} profile={null} onProfile={() => undefined} runLive={runLiveState(true, true)} onRunLive={() => undefined} busy={false} />);

describe("pemilih model U3 (M2.5)", () => {
  it("menampilkan Contributor, Spark Open (Baseten), Glimmer (local) dengan kuantisasi dan effort", () => {
    const h = controls(H);
    expect(h).toContain("Contributor · effort low");
    expect(h).toContain("Spark Open (Baseten) · effort low");
    expect(h).toContain("Glimmer (local) · Q4_K_M · effort high");
  });
  it("profil tanpa peran C tidak muncul di pemilih", () => {
    expect(answerProfiles(H).map((p) => p.model_profile)).toEqual(["meta", "baseten_open", "glimmer_local"]);
    expect(controls(H)).not.toContain("B only");
  });
  it("Glimmer nonaktif bila server mati, dengan pesan jelas; yang lain tetap aktif", () => {
    const h = controls(H);
    expect(h).toMatch(/<option[^>]*disabled[^>]*>Glimmer \(local\)/);
    expect(h).not.toMatch(/<option[^>]*disabled[^>]*>Spark Open/);
    expect(h).not.toMatch(/<option[^>]*disabled[^>]*>Contributor/);
    expect(h).toContain("Local model server is not running. Start it in LM Studio to enable this model.");
  });
  it("Glimmer hidup: tanpa pesan dan opsi aktif", () => {
    const up: Health = { ...H, model_profiles: H.model_profiles.map((p) => (p.model_profile === "glimmer_local" ? { ...p, available: true, unavailable_reason: null } : p)) };
    const h = controls(up);
    expect(h).not.toMatch(/<option[^>]*disabled/);
    expect(h).not.toContain("not running");
  });
  it("profil awal = Contributor (bukan pembanding), meski pembanding tersedia", () => {
    expect(defaultProfile(H)).toBe("meta");
    const onlyCmp: Health = { ...H, model_profiles: H.model_profiles.filter((p) => p.model_profile !== "meta") };
    expect(defaultProfile(onlyCmp)).toBe("baseten_open");
  });
  it("label dan fallback health lama tanpa field baru", () => {
    expect(modelLabel(H.model_profiles[2])).toBe("Glimmer (local)");
    expect(modelDetail({ model_profile: "meta", model: "muse-spark-1.3-contributor", available: true })).toBe("muse-spark-1.3-contributor");
    expect(profileLabel(H, "glimmer_local")).toBe("Glimmer (local)");
    expect(profileLabel(H, "tidak-ada")).toBe("tidak-ada");
    expect(profileLabel(null, "meta")).toBe("meta");
  });
});

describe("label model per jawaban (H-053, H-028)", () => {
  it("kolom menampilkan nama model, kuantisasi, effort, dan profil", () => {
    const h = renderToStaticMarkup(
      <EvidenceView state={{ status: "ready", data: mkAnswers() }} settings={SETTINGS} profileName={(k) => profileLabel(H, k)} />,
    );
    expect(h).toContain("Quantization</dt>");
    expect(h).toContain("Effort</dt>");
    expect(h).toContain("Model profile</dt>");
  });
  it("nama tampilan profil muncul berdampingan dengan kunci profil", () => {
    const data = mkAnswers();
    data.best.model_profile = "glimmer_local";
    const h = renderToStaticMarkup(
      <EvidenceView state={{ status: "ready", data }} settings={SETTINGS} profileName={(k) => profileLabel(H, k)} />,
    );
    expect(h).toContain("Glimmer (local) (glimmer_local)");
  });
});
