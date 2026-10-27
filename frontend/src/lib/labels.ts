import type { Item, Setting } from "../types";

// Label UI Inggris (H-018, docs/UI-SPEC.md §6). Teks hukum tidak diterjemahkan.
export function settingLabel(s: Setting): string {
  if (s.chunker === "structure_handwritten") return "Structure (handwritten parser)";
  if (s.chunker === "fixed_size") return `Fixed-size (${s.chunk_size_tokens} tokens (local tokenizer), ${s.overlap_tokens} overlap)`;
  return s.chunker;
}

export const modeLabel = (m: Item["mode"]): string => (m === "literal" ? "Literal" : "Paraphrase");
export const originLabel = (o: Item["origin"]): string => (o === "operator" ? "Operator-written" : "Spark-proposed, approved");

export const sectionLabel: Record<string, string> = {
  batang_tubuh: "Articles (batang tubuh)",
  penjelasan_pasal: "Elucidation of articles (Penjelasan)",
  penjelasan_umum: "General elucidation (Penjelasan Umum)",
};
