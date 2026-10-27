// Data palsu sintetis untuk test U3/U5/U8. Angka di sini hanya untuk test; UI tidak menanam angka contoh.
import type { AnswerRecord, AnswersResponse, Health, RunRecord, SchemaRecord, Setting, Snapshot, VerifierResult } from "../types";

export const mkSetting = (id: string, chunker: Setting["chunker"], mode: Setting["retrieval_mode"] = "hybrid", header = false): Setting => ({
  setting_id: id, family: "uupt", chunker, chunk_size_tokens: chunker === "fixed_size" ? 256 : null,
  overlap_tokens: chunker === "fixed_size" ? 32 : null, schema_version: null, retrieval_mode: mode, header_b: header, budget_tokens: 2000,
});

export const SETTINGS = [mkSetting("S-struct", "structure_handwritten"), mkSetting("S-fixed", "fixed_size")];

export const mkRun = (id: string, over: Partial<RunRecord> = {}): RunRecord => ({
  run_id: id, kind: "spark_c", created_at: "2026-10-27T06:24:03Z", cache_key: "k", config_hash: "h", prompt_version: "v2",
  model: "muse-spark-1.3-contributor", effort: "low", usage_input_tokens: 1111, usage_cached_tokens: 100, usage_output_tokens: 33,
  cost_usd_micros: 5848, projected_cost_usd_micros: null, latency_ms: 3642, provider: "meta", quantization: null, status: "ok", error: null, ...over,
});

export const mkAnswer = (slot: "best" | "baseline", status: AnswerRecord["output"]["status"], over: Partial<AnswerRecord> = {}): AnswerRecord => ({
  answer_id: `ans-${slot}`, item_id: "item-1", setting_id: slot === "best" ? "S-struct" : "S-fixed", slot, model_profile: "meta",
  context_chunk_ids: ["c1"], budget_tokens: 2000, flags: [], run_id: `run-${slot}`,
  output: { status, jawaban: status === "jawab" ? "Jawaban uji." : null, kutipan: status === "jawab" ? [{ alamat: "UU 40/2007 › Pasal 1 › ayat (1)", teks: "Teks kutipan uji." }, { alamat: "UU 40/2007 › Pasal 2", teks: "Kutipan kedua." }] : [] },
  ...over,
});

export const mkVerifier = (answerId: string, i: number, over: Partial<VerifierResult> = {}): VerifierResult => ({
  answer_id: answerId, citation_index: i, exists: "lulus", faithful: "lulus", faithful_score: null, valid_on_date: "tidak_dijalankan",
  status_table_version: null, matched_chunk_id: null, ...over,
});

export function mkAnswers(): AnswersResponse {
  return {
    best: mkAnswer("best", "jawab", { flags: ["jawab_tanpa_kutipan"] }),
    baseline: mkAnswer("baseline", "bukti_tidak_cukup"),
    verifier: [mkVerifier("ans-best", 0, { faithful: "lulus", faithful_score: 0.987 }), mkVerifier("ans-best", 1, { exists: "lulus", faithful: "gagal", faithful_score: 0.512 })],
    summary: [
      { setting_id: "S-struct", slot: "best", model_profile: "meta", answered_supported: 1, answered_unsupported: 0, abstained_correct: 0, abstained_should_answer: 0, n_items: 1 },
      { setting_id: "S-fixed", slot: "baseline", model_profile: "meta", answered_supported: 0, answered_unsupported: 0, abstained_correct: 0, abstained_should_answer: 1, n_items: 1 },
      { setting_id: "S-struct", slot: "best", model_profile: "glimmer_local", answered_supported: 0, answered_unsupported: 1, abstained_correct: 0, abstained_should_answer: 0, n_items: 1 },
    ],
    runs: [
      mkRun("run-best", { usage_input_tokens: 1111, usage_cached_tokens: 100, usage_output_tokens: 33, cost_usd_micros: 5848, effort: "low" }),
      mkRun("run-baseline", { usage_input_tokens: 2222, usage_cached_tokens: 0, usage_output_tokens: 44, cost_usd_micros: 12, model: "muse-glimmer-x", quantization: "Q4_K_M", effort: "medium", provider: "lmstudio_local" }),
    ],
  };
}

export const HEALTH: Health = {
  status: "ok", replay: true, model: "muse-spark-1.3-contributor", config_hash: "h",
  model_profiles: [
    { model_profile: "meta", model: "muse-spark-1.3-contributor", available: true },
    { model_profile: "glimmer_local", model: "muse-glimmer-x", available: false },
  ],
};

export const mkSchema = (version: number, source: "spark" | "operator", over: Partial<SchemaRecord["body"]> = {}, note: string | null = null): SchemaRecord => ({
  family: "uupt", schema_version: version, source, parent_version: source === "operator" ? 1 : null, validation: [], run_id: "r", created_at: "2026-10-27T06:15:25Z",
  operator_note: note,
  body: {
    family: "uupt", default_chunk_level: 2, notes: null,
    levels: [
      { order: 1, name: "bab", marker_pattern: "^BAB", examples: ["BAB I"], parent_order: null, is_chunk_unit: false },
      { order: 2, name: "pasal", marker_pattern: "^Pasal\\s+\\d+", examples: ["Pasal 1", "Pasal 2"], parent_order: 1, is_chunk_unit: true },
    ],
    ...over,
  },
});

export function mkSnapshot(over: Partial<Snapshot> = {}): Snapshot {
  return {
    family: "uupt", budget_tokens: 2000, replay: true, config_hash: "cfg", corpus: [{ doc_id: "uupt-40-2007", title: "UU", clean_sha256: "x", char_count: 1 }],
    items: [], items_summary: { n_items: 0, by_origin: {}, by_mode: {}, by_split: null, control_in_held_out: null },
    settings: SETTINGS, grid: null, metrics: [], quality: [], ...over,
  };
}
