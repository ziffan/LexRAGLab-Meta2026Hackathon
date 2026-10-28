import type { HeaderBView, HeaderSample, RunKind, RunRecord, RunTotal } from "../types";
import { formatUsd } from "./evidence";

// U8 Run log & cost (docs/UI-SPEC.md U8): logika murni. Uang integer micro-USD, waktu UTC.

export const ROLE_LABEL: Record<RunKind, string> = { spark_a: "A", spark_b: "B", spark_c: "C", spark_d: "D", grid: "Grid", measure: "Measure" };
export const ROLES: RunKind[] = ["spark_a", "spark_b", "spark_c", "spark_d", "grid", "measure"];
export type RoleFilter = "all" | RunKind;

export const roleLabel = (k: RunKind): string => ROLE_LABEL[k] ?? k;

export function filterRuns(runs: RunRecord[], role: RoleFilter): RunRecord[] {
  return role === "all" ? runs : runs.filter((r) => r.kind === role);
}

export interface RoleAggregate {
  kind: RunKind;
  runs: number;
  inputTokens: number;
  cachedTokens: number;
  outputTokens: number;
  costMicros: number;
  unknownRuns: number; // run dengan token/biaya null (dihitung 0 di jumlah)
}

/** Baris agregat per peran: jumlah run, token, biaya (integer). Token/biaya null dihitung 0. */
export function aggregateByRole(runs: RunRecord[]): RoleAggregate[] {
  const m = new Map<RunKind, RoleAggregate>();
  for (const r of runs) {
    const a = m.get(r.kind) ?? { kind: r.kind, runs: 0, inputTokens: 0, cachedTokens: 0, outputTokens: 0, costMicros: 0, unknownRuns: 0 };
    a.runs += 1;
    a.inputTokens += r.usage_input_tokens ?? 0;
    a.cachedTokens += r.usage_cached_tokens ?? 0;
    a.outputTokens += r.usage_output_tokens ?? 0;
    a.costMicros += r.cost_usd_micros ?? 0;
    if ([r.usage_input_tokens, r.usage_cached_tokens, r.usage_output_tokens, r.cost_usd_micros].some((v) => v === null)) a.unknownRuns += 1;
    m.set(r.kind, a);
  }
  return ROLES.filter((k) => m.has(k)).map((k) => m.get(k) as RoleAggregate);
}

/** Agregat server (R1 `run_totals_by_kind`, semua run) -> baris tabel per peran; biaya = buku belanja (UX-02). Filter peran ikut. */
export function totalsToAggregates(totals: RunTotal[], role: RoleFilter = "all"): RoleAggregate[] {
  return totals
    .filter((t) => role === "all" || t.kind === role)
    .map((t) => ({ kind: t.kind, runs: t.runs, inputTokens: t.usage_input_tokens, cachedTokens: t.usage_cached_tokens,
      outputTokens: t.usage_output_tokens, costMicros: t.spend_usd_micros, unknownRuns: t.unknown_runs }));
}

/** Waktu UTC ringkas "2026-10-27 06:24:03Z" dari ISO. */
export const utcStamp = (iso: string): string => iso.replace("T", " ");

export const latencyStr = (ms: number | null | undefined): string => (ms === null || ms === undefined ? "n/a" : `${ms} ms`);

export interface ProjectionRow {
  source: string;
  units: number;
  calls: number;
  expected: string;
  upperCached: string;
  upperNoCache: string;
  seconds: number;
}

const SOURCE_ORDER = ["pasal", "ayat", "fixed_size"];

/** Proyeksi header B per granularitas (pasal/ayat/fixed_size); entri ":sample" dilewati. */
export function projectionRows(h: HeaderBView | undefined): ProjectionRow[] {
  const p = h?.projection?.projections;
  if (!p) return [];
  return SOURCE_ORDER.filter((k) => p[k]).map((k) => {
    const e = p[k];
    return {
      source: k,
      units: e.units,
      calls: e.calls,
      expected: formatUsd(e.cost_usd_micros.expected),
      upperCached: formatUsd(e.cost_usd_micros.upper_cached),
      upperNoCache: formatUsd(e.cost_usd_micros.upper_no_cache),
      seconds: e.time.estimated_seconds,
    };
  });
}

export const granularityLabel = (g: string): string => (g === "pasal" ? "Pasal" : g === "ayat" ? "Ayat" : g === "fixed_size" ? "Fixed-size" : g);

export interface SampleRow extends HeaderSample {
  address: string | null;
}

/** Sampel header + alamat dari peta chunk_id -> alamat (R4); tanpa padanan alamat = null. */
export function sampleRows(h: HeaderBView | undefined, addr: Record<string, string>): SampleRow[] {
  return (h?.samples ?? []).map((s) => ({ ...s, address: addr[s.chunk_id] ?? null }));
}
