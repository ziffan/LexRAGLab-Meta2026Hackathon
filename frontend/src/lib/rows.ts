import type { Item, ItemMetrics } from "../types";
import type { Filters } from "../state";
import { NA, orNa, xOfY } from "./format";

// Baris tabel U4 (docs/UI-SPEC.md U4). Hitungan mentah "x of y"; null -> "n/a" (H-059, H-061).

export interface Row {
  id: string;
  spanRecall: string;
  tokenPrecision: string;
  rank: string;
  recallAtK: string;
  fullyCovered: string;
  retrievedTokens: string;
  hasGold: boolean;
}

export function toRow(m: ItemMetrics): Row {
  const hasGold = m.gold_chars > 0 || m.parts_total > 0;
  return {
    id: m.item_id,
    hasGold,
    spanRecall: m.span_recall === null ? NA : xOfY(m.covered_gold_chars, m.gold_chars, "chars"),
    tokenPrecision: m.token_precision === null ? NA : xOfY(m.gold_tokens_retrieved, m.retrieved_tokens, "tokens"),
    rank: m.rank === null || m.reciprocal_rank === null ? NA : `rank ${m.rank} (RR 1/${m.rank})`,
    recallAtK: m.recall_at_k === null ? NA : xOfY(m.parts_hit, m.parts_total, "gold parts"),
    fullyCovered: orNa(m.fully_covered, (v) => (v ? "yes" : "no")),
    retrievedTokens: String(m.retrieved_tokens),
  };
}

export function itemPasses(i: Item, f: Filters, splitOf: (id: string) => string | null | undefined): boolean {
  if (f.origin !== "all" && i.origin !== f.origin) return false;
  if (f.mode !== "all" && i.mode !== f.mode) return false;
  if (f.split !== "all" && splitOf(i.id) !== f.split) return false;
  return true;
}

/** Hasil per asal dalam hitungan mentah: butir bergold yang tertutup penuh di antara butir bergold. */
export function originSummary(items: Item[], metrics: Map<string, ItemMetrics>): { origin: Item["origin"]; covered: number; total: number; noGold: number }[] {
  const out: { origin: Item["origin"]; covered: number; total: number; noGold: number }[] = [];
  for (const origin of ["operator", "spark_disetujui"] as const) {
    const mine = items.filter((i) => i.origin === origin);
    if (mine.length === 0) continue;
    const ms = mine.map((i) => metrics.get(i.id)).filter((m): m is ItemMetrics => !!m);
    const gold = ms.filter((m) => m.fully_covered !== null);
    out.push({ origin, covered: gold.filter((m) => m.fully_covered).length, total: gold.length, noGold: ms.length - gold.length });
  }
  return out;
}

/** Cakupan ringkasan per asal mengikuti filter split aktif. */
export function filterScopeLabel(split: Filters["split"], transfer = false): string {
  if (transfer) return "all items (transfer test)"; // akta: tanpa split, tanpa kata held-out (H-078)
  return split === "all" ? "all items (tune + held-out)" : split === "tune" ? "tune items only" : "held-out items only";
}
