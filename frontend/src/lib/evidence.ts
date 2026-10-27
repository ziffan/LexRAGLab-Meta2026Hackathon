import { ApiFailure, postAnswers, type FetchLike } from "../api";
import type { AnswerRecord, AnswersResponse, Health, ModelProfileInfo, RejectionSummary, RunRecord, Setting, ValidOnDate, VerifierResult } from "../types";
import { NA } from "./format";

// U3 End-to-end evidence (docs/UI-SPEC.md U3, M2.2/M2.3). Logika murni + pemuat W6.

/** Micro-USD integer -> "$0.005848" (enam desimal, tanpa float). null -> "n/a". */
export function formatUsd(micros: number | null | undefined): string {
  if (micros === null || micros === undefined) return NA;
  const neg = micros < 0;
  const m = Math.abs(Math.trunc(micros));
  return `${neg ? "-" : ""}$${Math.floor(m / 1_000_000)}.${String(m % 1_000_000).padStart(6, "0")}`;
}

export const tokenStr = (n: number | null | undefined): string => (n === null || n === undefined ? NA : String(n));

export const STATUS_LABEL: Record<string, string> = { jawab: "Answered", tolak: "Abstained", bukti_tidak_cukup: "Insufficient evidence" };
export const statusLabel = (s: string): string => STATUS_LABEL[s] ?? s;

export const testLabel = (v: "lulus" | "gagal"): string => (v === "lulus" ? "Pass" : "Fail");

export const VALID_LABEL: Record<ValidOnDate, string> = { berlaku: "Valid", dicabut: "Revoked", berlaku_bersyarat: "Conditional", tidak_dijalankan: "Not run" };
export const validLabel = (v: ValidOnDate): string => VALID_LABEL[v] ?? v;

/** Penanda informatif H-066 dengan gloss Inggris; kode tak dikenal ditampilkan apa adanya. */
export const FLAG_LABEL: Record<string, string> = {
  jawab_tanpa_kutipan: "Answered without citations",
  jawab_tanpa_jawaban: "Answered without answer text",
};
export const flagLabel = (f: string): string => FLAG_LABEL[f] ?? f;

/** Label model (H-053). Profil Glimmer lokal diberi nama tetap; selain itu model ID dari data. */
export function modelLabel(p: ModelProfileInfo): string {
  if (/glimmer/i.test(`${p.model_profile} ${p.model ?? ""}`)) return "Muse Glimmer (local, open-weight)";
  return p.model ?? p.model_profile;
}

export const isGlimmer = (p: ModelProfileInfo): boolean => /glimmer/i.test(`${p.model_profile} ${p.model ?? ""}`);

export function profileUnavailableText(p: ModelProfileInfo): string {
  return isGlimmer(p) ? "Local Glimmer server not running" : "Profile not configured";
}

/** Profil model awal: default server (null) bila ada profil tersedia; selain itu null. */
export function defaultProfile(health: Health | null): string | null {
  const ok = health?.model_profiles.find((p) => p.available && !isGlimmer(p));
  return ok?.model_profile ?? null;
}

export interface CitationView {
  alamat: string;
  teks: string;
  exists: string | null;
  faithful: string | null;
  faithfulScore: number | null;
  validOnDate: string;
  validNotRun: boolean;
}

export interface ColumnView {
  slot: "best" | "baseline";
  title: string;
  settingId: string;
  modelProfile: string;
  status: string;
  statusCode: string;
  answer: string | null;
  citations: CitationView[];
  flags: string[];
  budgetTokens: number;
  inputTokens: number | null;
  cachedTokens: number | null;
  outputTokens: number | null;
  costMicros: number | null;
  model: string | null;
  quantization: string | null;
  effort: string | null;
  runStatus: string | null;
}

/** Satu kolom dari jawaban + hasil verifier + run-nya (run dicari lewat `run_id`). */
export function columnView(ans: AnswerRecord, verifier: VerifierResult[], runs: RunRecord[], title: string): ColumnView {
  const run = runs.find((r) => r.run_id === ans.run_id) ?? null;
  const mine = verifier.filter((v) => v.answer_id === ans.answer_id);
  const citations = ans.output.kutipan.map((k, i): CitationView => {
    const v = mine.find((x) => x.citation_index === i);
    return {
      alamat: k.alamat,
      teks: k.teks,
      exists: v ? testLabel(v.exists) : null,
      faithful: v ? testLabel(v.faithful) : null,
      faithfulScore: v?.faithful_score ?? null,
      validOnDate: v ? validLabel(v.valid_on_date) : VALID_LABEL.tidak_dijalankan,
      validNotRun: !v || v.valid_on_date === "tidak_dijalankan",
    };
  });
  return {
    slot: ans.slot,
    title,
    settingId: ans.setting_id,
    modelProfile: ans.model_profile,
    status: statusLabel(ans.output.status),
    statusCode: ans.output.status,
    answer: ans.output.jawaban,
    citations,
    flags: ans.flags,
    budgetTokens: ans.budget_tokens,
    inputTokens: run?.usage_input_tokens ?? null,
    cachedTokens: run?.usage_cached_tokens ?? null,
    outputTokens: run?.usage_output_tokens ?? null,
    costMicros: run?.cost_usd_micros ?? null,
    model: run?.model ?? null,
    quantization: run?.quantization ?? null,
    effort: run?.effort ?? null,
    runStatus: run?.status ?? null,
  };
}

export interface SummaryRow {
  key: string;
  settingId: string;
  slot: "best" | "baseline";
  modelProfile: string;
  counts: [number, number, number, number];
  nItems: number;
}

/** Ringkasan 2x2 per (setting_id, slot, model_profile); baris tidak pernah dijumlahkan lintas kunci (H-067 V11). */
export function summaryRows(summary: RejectionSummary[]): SummaryRow[] {
  return summary.map((s) => ({
    key: `${s.setting_id}|${s.slot}|${s.model_profile}`,
    settingId: s.setting_id,
    slot: s.slot,
    modelProfile: s.model_profile,
    counts: [s.answered_supported, s.answered_unsupported, s.abstained_correct, s.abstained_should_answer],
    nItems: s.n_items,
  }));
}

export const SUMMARY_HEADERS = ["Answered, supported", "Answered, unsupported", "Abstained, correctly", "Abstained, should have answered"] as const;

/** Run live: aktif hanya untuk butir `scene_checked` DAN backend terjangkau. Replay server tidak menonaktifkan (H-050, API.md §1); ekspor statis (H-051) atau backend mati menonaktifkan. */
export function runLiveState(sceneChecked: boolean | undefined, backendUp: boolean): { enabled: boolean; reason: string } {
  if (!backendUp) return { enabled: false, reason: "Static replay: live calls are disabled" };
  if (!sceneChecked) return { enabled: false, reason: "Live runs are limited to items marked scene_checked by the operator" };
  return { enabled: true, reason: "Run one live Muse Spark call for this item" };
}

/** Pembanding W6: setting ukuran tetap tanpa header (mode retrieval sama bila ada). */
export function baselineFor(settings: Setting[], best: Setting | undefined): Setting | undefined {
  const fixed = settings.filter((s) => s.chunker === "fixed_size" && !s.header_b);
  return fixed.find((s) => s.retrieval_mode === best?.retrieval_mode) ?? fixed[0];
}

// ---- pemuat W6 ----
export type EvidenceState =
  | { status: "idle" }
  | { status: "loading"; live: boolean; last: AnswersResponse | null }
  | { status: "empty"; last: AnswersResponse | null }
  | { status: "error"; code: string; message: string; last: AnswersResponse | null }
  | { status: "ready"; data: AnswersResponse };

export type EvidenceAction =
  | { type: "reset" }
  | { type: "loading"; live: boolean }
  | { type: "ready"; data: AnswersResponse }
  | { type: "empty" }
  | { type: "error"; code: string; message: string };

const lastOf = (s: EvidenceState): AnswersResponse | null => (s.status === "ready" ? s.data : s.status === "idle" ? null : s.last);

export function evidenceReducer(s: EvidenceState, a: EvidenceAction): EvidenceState {
  switch (a.type) {
    case "reset":
      return { status: "idle" };
    case "loading":
      return { status: "loading", live: a.live, last: lastOf(s) };
    case "ready":
      return { status: "ready", data: a.data };
    case "empty":
      return { status: "empty", last: lastOf(s) };
    case "error":
      return { status: "error", code: a.code, message: a.message, last: lastOf(s) };
  }
}

export interface EvidenceQuery {
  family: string;
  itemId: string;
  bestSettingId: string;
  baselineSettingId: string;
  modelProfile: string | null;
  live: boolean;
}

/** Panggil W6 dan terjemahkan hasilnya ke aksi. `409 replay_no_stored_run` = empty (bukan galat). */
export async function loadEvidence(q: EvidenceQuery, rawDispatch: (a: EvidenceAction) => void, fetchFn?: FetchLike, isCurrent: () => boolean = () => true): Promise<void> {
  // Respons dari permintaan yang sudah digantikan dibuang (tidak menimpa hasil terbaru).
  const dispatch = (a: EvidenceAction) => {
    if (isCurrent()) rawDispatch(a);
  };
  dispatch({ type: "loading", live: q.live });
  try {
    const data = await postAnswers(q.family, {
      item_id: q.itemId,
      best_setting_id: q.bestSettingId,
      baseline_setting_id: q.baselineSettingId,
      model_profile: q.modelProfile,
      live: q.live,
    }, fetchFn);
    dispatch({ type: "ready", data });
  } catch (e) {
    const f = e instanceof ApiFailure ? e : new ApiFailure("unknown", "Unexpected error.");
    if (f.code === "replay_no_stored_run") dispatch({ type: "empty" });
    else dispatch({ type: "error", code: f.code, message: f.message });
  }
}
