import type { Item, RetrievalMode, Setting, SplitName } from "../types";

// Label UI Inggris (H-018, docs/UI-SPEC.md §6). Teks hukum tidak diterjemahkan.
export function chunkerLabel(s: Setting): string {
  if (s.chunker === "structure_handwritten") return "Structure (handwritten parser)";
  if (s.chunker === "fixed_size") return `Fixed-size (${s.chunk_size_tokens} tokens (local tokenizer), ${s.overlap_tokens} overlap)`;
  return "Structure (schema A)";
}

export const retrievalModeLabel = (m: RetrievalMode): string => (m === "dense" ? "Dense" : m === "bm25" ? "BM25" : "Hybrid");

export function settingLabel(s: Setting): string {
  return `${chunkerLabel(s)} · ${retrievalModeLabel(s.retrieval_mode)}${s.header_b ? " · header B on" : ""}`;
}

/** Nama pendek untuk tooltip dan header, mis. "structure · hybrid · header off". */
export function settingShort(s: Setting): string {
  const c = s.chunker === "fixed_size" ? "fixed-size" : s.chunker === "structure_handwritten" ? "structure" : "structure (schema A)";
  return `${c} · ${s.retrieval_mode} · header ${s.header_b ? "on" : "off"}`;
}

export const modeLabel = (m: Item["mode"] | "unanswerable" | (string & {})): string =>
  m === "literal" ? "Literal" : m === "tolak" ? "Must refuse" : m === "unanswerable" ? "Unanswerable" : m === "parafrase" ? "Paraphrase" : m;
export const originLabel = (o: Item["origin"]): string => (o === "operator" ? "Operator-written" : "Spark-proposed, approved");
export const splitLabel = (s: SplitName | null | undefined): string => (s === "tune" ? "Tune" : s === "held_out" ? "Held-out" : "n/a");

export const sectionLabel: Record<string, string> = {
  batang_tubuh: "Articles (batang tubuh)",
  penjelasan_pasal: "Elucidation of articles (Penjelasan)",
  penjelasan_umum: "General elucidation (Penjelasan Umum)",
};

/** Label cakupan butir (I-39): dari `items_scope` API atau filter split aktif; tidak di-hardcode ke satu split. */
export function scopeLabel(scope: string | null | undefined): string {
  if (scope === "all") return "all items (tune + held-out)";
  if (scope === "tune") return "tune items only";
  if (scope === "held_out") return "held-out items only";
  return "item scope not reported";
}
