// U3 End-to-end evidence (M2.2/M2.3). Tanpa DOM dan tanpa jaringan: pemuat dengan fetch palsu + render server.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EvidenceControls, EvidenceView } from "../components/Evidence";
import {
  baselineFor, columnView, defaultProfile, evidenceReducer, formatUsd, loadEvidence, modelLabel, runLiveState, summaryRows,
  type EvidenceAction, type EvidenceState,
} from "../lib/evidence";
import { HEALTH, SETTINGS, mkAnswers, mkSetting } from "./fixtures";

const html = (state: EvidenceState, extra: Partial<Parameters<typeof EvidenceView>[0]> = {}) =>
  renderToStaticMarkup(<EvidenceView state={state} settings={SETTINGS} {...extra} />);

const Q = { family: "uupt", itemId: "item-1", bestSettingId: "S-struct", baselineSettingId: "S-fixed", modelProfile: "meta", live: false };

function rig(status: number, body: unknown) {
  const calls: { url: string; method: string; body: any }[] = [];
  const fetchFn = async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: JSON.parse(String(init?.body ?? "null")) });
    return new Response(JSON.stringify(body), { status });
  };
  const actions: EvidenceAction[] = [];
  return { calls, fetchFn, actions, dispatch: (a: EvidenceAction) => actions.push(a) };
}

describe("format", () => {
  it("micro-USD integer ke USD tanpa float", () => {
    expect(formatUsd(5848)).toBe("$0.005848");
    expect(formatUsd(0)).toBe("$0.000000");
    expect(formatUsd(1_234_567)).toBe("$1.234567");
    expect(formatUsd(null)).toBe("n/a");
  });
});

describe("kolom bukti", () => {
  const d = mkAnswers();
  const best = columnView(d.best, d.verifier, d.runs, "Best profile");
  const base = columnView(d.baseline, d.verifier, d.runs, "Baseline");
  it("token aktual, biaya, model, kuantisasi, effort diambil dari run kolom itu", () => {
    expect([best.inputTokens, base.inputTokens]).toEqual([1111, 2222]);
    expect([best.costMicros, base.costMicros]).toEqual([5848, 12]);
    expect([best.cachedTokens, base.cachedTokens]).toEqual([100, 0]);
    expect([best.outputTokens, base.outputTokens]).toEqual([33, 44]);
    expect(base.model).toBe("muse-glimmer-x");
    expect(base.quantization).toBe("Q4_K_M");
    expect([best.effort, base.effort]).toEqual(["low", "medium"]);
  });
  it("tanda uji per kutipan; uji 3 tidak_dijalankan = Not run", () => {
    expect(best.citations.map((c) => [c.exists, c.faithful, c.faithfulScore, c.validOnDate, c.validNotRun])).toEqual([
      ["Pass", "Pass", 0.987, "Not run", true],
      ["Pass", "Fail", 0.512, "Not run", true],
    ]);
  });
  it("uji 3 berlaku/dicabut/bersyarat dipetakan, bukan Not run", () => {
    const v = [{ ...d.verifier[0], valid_on_date: "dicabut" as const }];
    expect(columnView(d.best, v, d.runs, "x").citations[0].validOnDate).toBe("Revoked");
    expect(columnView(d.best, [{ ...v[0], valid_on_date: "berlaku_bersyarat" }], d.runs, "x").citations[0].validOnDate).toBe("Conditional");
    expect(columnView(d.best, [{ ...v[0], valid_on_date: "berlaku" }], d.runs, "x").citations[0].validNotRun).toBe(false);
  });
  it("run tidak ditemukan: token dan biaya n/a, bukan 0", () => {
    const c = columnView(d.best, d.verifier, [], "x");
    expect([c.inputTokens, c.costMicros]).toEqual([null, null]);
  });
});

describe("jawaban dari cache: biaya panggilan asal (UX-03)", () => {
  const d = mkAnswers();
  // Kunci cache unik per kolom: origin best tidak boleh terbaca untuk baseline.
  const paid = d.runs.map((r) => ({ ...r, cache_key: `ck-${r.run_id}` }));
  const runs = paid.map((r) => ({ ...r, status: "replay" as const, run_id: `${r.run_id}-rp`, cost_usd_micros: null,
    usage_input_tokens: null, usage_cached_tokens: null, usage_output_tokens: null, latency_ms: 0 }));
  const best = { ...d.best, run_id: `${d.best.run_id}-rp` };
  const origin = paid.find((x) => x.run_id === d.best.run_id)!;
  it("run replay + origin cache_key sama: biaya dan token dari panggilan asal, ditandai", () => {
    const c = columnView(best, d.verifier, runs, "Best profile", [origin]);
    expect([c.costMicros, c.inputTokens, c.cachedTokens, c.outputTokens]).toEqual([origin.cost_usd_micros, origin.usage_input_tokens, origin.usage_cached_tokens, origin.usage_output_tokens]);
    expect(c.runStatus).toBe("replay");
    expect(c.origin).toEqual({ runId: origin.run_id, createdAt: origin.created_at });
  });
  it("tanpa origin, atau origin cache_key lain / bukan ok: tetap n/a, tanpa tanda", () => {
    expect(columnView(best, d.verifier, runs, "x").costMicros).toBeNull();
    expect(columnView(best, d.verifier, runs, "x", [{ ...origin, cache_key: "lain" }]).origin).toBeNull();
    expect(columnView(best, d.verifier, runs, "x", [{ ...origin, status: "error" }]).costMicros).toBeNull();
  });
  it("origin dipilih per cache_key: baseline tidak mengambil origin best", () => {
    const base = { ...d.baseline, run_id: `${d.baseline.run_id}-rp` };
    expect(columnView(base, d.verifier, runs, "x", [origin]).costMicros).toBeNull();
  });
  it("run sendiri (ok) tidak memakai origin", () => {
    const c = columnView(d.best, d.verifier, d.runs, "x", [{ ...origin, cache_key: "k", cost_usd_micros: 999999 }]);
    expect(c.costMicros).toBe(5848);
    expect(c.origin).toBeNull();
  });
  it("EvidenceView menulis label served from cache", () => {
    const data = { ...d, best, runs, origin_runs: [origin] };
    const h = html({ status: "ready", data });
    expect(h).toContain("served from cache; original call");
    expect(h).toContain(formatUsd(origin.cost_usd_micros));
  });
});

describe("EvidenceView", () => {
  const ready: EvidenceState = { status: "ready", data: mkAnswers() };
  it("dua kolom, status Inggris, tanda uji, skor, flags, jawaban Indonesia", () => {
    const h = html(ready);
    expect(h).toContain("Best profile");
    expect(h).toContain("Baseline");
    expect(h).toContain("Answered");
    expect(h).toContain("Insufficient evidence");
    expect(h).toContain("Exists: Pass");
    expect(h).toContain("Faithful: Pass");
    expect(h).toContain("Faithful: Fail");
    expect(h).toContain("Valid on date: Not run");
    expect(h).toContain("faithful_score 0.987");
    expect(h).toContain("Answered without citations");
    expect(h).toContain("Jawaban uji.");
    expect(h).toContain("UU 40/2007 › Pasal 1 › ayat (1)");
  });
  it("token input aktual per kolom terpisah dari anggaran konteks yang sama", () => {
    const h = html(ready);
    expect(h).toContain("Context budget: 2000 tokens (local tokenizer)");
    expect(h).toContain("Actual input tokens (usage)</dt><dd>1111");
    expect(h).toContain("Actual input tokens (usage)</dt><dd>2222");
    expect(h).toContain("Cached tokens</dt><dd>100");
    expect(h).toContain("Output tokens</dt><dd>33");
    expect(h).toContain("Cost (USD)</dt><dd>$0.005848");
    expect(h).toContain("Cost (USD)</dt><dd>$0.000012");
  });
  it("label model, kuantisasi, effort per kolom (H-053)", () => {
    const h = html(ready);
    expect(h).toContain("Quantization</dt><dd>Q4_K_M");
    expect(h).toContain("Effort</dt><dd>medium");
    expect(h).toContain("muse-spark-1.3-contributor");
  });
  it("ringkasan 2x2 per setting x slot x model_profile, tidak dijumlahkan", () => {
    expect(summaryRows(mkAnswers().summary)).toHaveLength(3);
    const h = html(ready);
    for (const t of ["Answered, supported", "Answered, unsupported", "Abstained, correctly", "Abstained, should have answered", "glimmer_local"]) expect(h).toContain(t);
    const body = h.slice(h.indexOf("<tbody>"));
    expect((body.match(/<tr>/g) ?? []).length).toBe(3);
  });
  it("loading dengan waktu berjalan", () => {
    expect(html({ status: "loading", live: false, last: null }, { elapsedSeconds: 7 })).toContain("Waiting for Muse Spark… 7s");
  });
  it("empty: replay_no_stored_run", () => {
    expect(html({ status: "empty", last: null })).toContain("No end-to-end run for this item");
  });
  it("error menampilkan pesan dan run terakhir yang tersimpan", () => {
    const h = html({ status: "error", code: "model_error", message: "boom", last: mkAnswers() });
    expect(h).toContain("Model call failed: boom. Showing last stored run.");
    expect(h).toContain("Best profile");
    expect(html({ status: "error", code: "x", message: "boom", last: null })).not.toContain("Showing last stored run");
  });
  it("tanpa butir dan tanpa pembanding", () => {
    expect(html({ status: "idle" }, { noItem: true })).toContain("Select an item");
    expect(html({ status: "idle" }, { noBaseline: true })).toContain("other than the fixed-size baseline");
  });
});

describe("pemuat W6", () => {
  it("memanggil W6 dengan live:false dan isi permintaan", async () => {
    const r = rig(200, mkAnswers());
    await loadEvidence(Q, r.dispatch, r.fetchFn);
    expect(r.calls).toHaveLength(1);
    expect(r.calls[0].url).toBe("/api/families/uupt/answers");
    expect(r.calls[0].method).toBe("POST");
    expect(r.calls[0].body).toEqual({ item_id: "item-1", best_setting_id: "S-struct", baseline_setting_id: "S-fixed", model_profile: "meta", live: false });
    expect(r.actions.map((a) => a.type)).toEqual(["loading", "ready"]);
  });
  it("Run live mengirim live:true (fetch palsu, tanpa jaringan)", async () => {
    const r = rig(200, mkAnswers());
    await loadEvidence({ ...Q, live: true }, r.dispatch, r.fetchFn);
    expect(r.calls[0].body.live).toBe(true);
    expect(r.actions[0]).toEqual({ type: "loading", live: true });
  });
  it("409 replay_no_stored_run = empty, bukan galat", async () => {
    const r = rig(409, { error: { code: "replay_no_stored_run", message: "none" } });
    await loadEvidence(Q, r.dispatch, r.fetchFn);
    expect(r.actions.map((a) => a.type)).toEqual(["loading", "empty"]);
  });
  it("galat lain = error dengan pesan; tolak (200) adalah hasil sah", async () => {
    const r = rig(502, { error: { code: "model_error", message: "upstream" } });
    await loadEvidence(Q, r.dispatch, r.fetchFn);
    expect(r.actions[1]).toEqual({ type: "error", code: "model_error", message: "upstream" });
    const d = mkAnswers();
    d.best = { ...d.best, output: { status: "tolak", jawaban: null, kutipan: [] } };
    const ok = rig(200, d);
    await loadEvidence(Q, ok.dispatch, ok.fetchFn);
    expect(ok.actions[1].type).toBe("ready");
    expect(html({ status: "ready", data: d })).toContain("Abstained");
  });
  it("reducer menyimpan hasil terakhir saat loading/error", () => {
    const d = mkAnswers();
    let s = evidenceReducer({ status: "idle" }, { type: "ready", data: d });
    s = evidenceReducer(s, { type: "loading", live: true });
    expect(s).toMatchObject({ status: "loading", last: d });
    s = evidenceReducer(s, { type: "error", code: "c", message: "m" });
    expect(s).toMatchObject({ status: "error", last: d });
    expect(evidenceReducer(s, { type: "reset" })).toEqual({ status: "idle" });
  });
});

describe("kontrol", () => {
  it("Run live: aktif hanya scene_checked + backend terjangkau; replay server tidak menonaktifkan", () => {
    expect(runLiveState(true, true).enabled).toBe(true);
    expect(runLiveState(true, false)).toMatchObject({ enabled: false, reason: "Static replay: live calls are disabled" });
    expect(runLiveState(false, true).enabled).toBe(false);
    expect(runLiveState(undefined, true).enabled).toBe(false);
  });
  it("tombol Run live ada tetapi disabled; Glimmer mati dinonaktifkan dengan teks", () => {
    const h = renderToStaticMarkup(
      <EvidenceControls health={HEALTH} profile={null} onProfile={() => undefined} runLive={runLiveState(false, true)} onRunLive={() => undefined} busy={false} />,
    );
    expect(h).toMatch(/<button[^>]*disabled[^>]*>Run live<\/button>/);
    expect(h).toContain("Muse Glimmer (local, open-weight) (Local Glimmer server not running)");
    expect(h).toMatch(/<option[^>]*disabled[^>]*>Muse Glimmer/);
  });
  it("profil default dan label model", () => {
    expect(defaultProfile(HEALTH)).toBe("meta");
    expect(defaultProfile(null)).toBeNull();
    expect(modelLabel(HEALTH.model_profiles[0])).toBe("muse-spark-1.3-contributor");
  });
  it("pembanding = ukuran tetap tanpa header, header-on diabaikan", () => {
    const withHeader = [mkSetting("S-fixed-hdr", "fixed_size", "hybrid", true), ...SETTINGS];
    expect(baselineFor(withHeader, SETTINGS[0])?.setting_id).toBe("S-fixed");
  });
  it("respons kedaluwarsa tidak menimpa yang baru", async () => {
    const actions: EvidenceAction[] = [];
    let current = true;
    const r = rig(200, mkAnswers());
    const p = loadEvidence(Q, (a) => actions.push(a), r.fetchFn, () => current);
    current = false; // permintaan baru menggantikan sebelum respons tiba
    await p;
    expect(actions.map((a) => a.type)).toEqual(["loading"]);
  });
});
