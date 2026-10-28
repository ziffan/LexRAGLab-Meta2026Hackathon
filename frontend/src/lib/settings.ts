import type { GridPoint, ItemMetrics, QualityWithCounts, Retrieval, RetrievalMode, Setting, Snapshot, SplitKey, SplitName } from "../types";

export const TRANSFER_LABEL = "transfer test, no profile selection";
export const DEGENERATE_LABEL = "no structure recognized";
export const DEGENERATE_NOTE = `Structure (handwritten parser) points: ${DEGENERATE_LABEL} (one chunk per deed). They stay in the grid.`;

/** Grid akta (H-091): satu blok `all`, tanpa kontrol split. */
export const isTransferGrid = (snap: Snapshot): boolean => snap.grid?.all !== undefined;
/** Kunci blok grid yang dipakai: `all` untuk akta, selain itu split pilihan pengguna. */
export const gridKey = (snap: Snapshot, split: SplitName): SplitKey => (isTransferGrid(snap) ? "all" : split);
export const hasDegenerate = (snap: Snapshot): boolean => (snap.grid?.all?.points ?? []).some((p) => !!p.label);

export const MODES: RetrievalMode[] = ["dense", "bm25", "hybrid"];

/** Setting yang bisa ditampilkan: anggaran snapshot, bukan yang dilewati grid (header B, skema A belum ada di M1). */
export function availableSettings(snap: Snapshot): Setting[] {
  const skipped = new Set(snap.grid?.skipped.map((s) => s.setting_id) ?? []);
  return snap.settings.filter(
    (s) => s.budget_tokens === snap.budget_tokens && !skipped.has(s.setting_id) && (snap.grid !== null || (!s.header_b && s.chunker !== "structure_schema")),
  );
}

/** Kunci identitas setting tanpa anggaran dan tanpa mode retrieval. */
const chunkerKey = (s: Setting): string => [s.chunker, s.chunk_size_tokens, s.overlap_tokens, s.schema_version, s.header_b].join("|");
export const settingKeyNoBudget = (s: Setting): string => `${chunkerKey(s)}|${s.retrieval_mode}`;

/** Setting padanan di snapshot baru (anggaran lain). */
export function matchSetting(settings: Setting[], prev: Setting | undefined): Setting | undefined {
  if (!prev) return undefined;
  return settings.find((s) => settingKeyNoBudget(s) === settingKeyNoBudget(prev));
}

/** Tiga mode retrieval untuk chunker dan parameter yang sama (M1.3). */
export function siblingModes(snap: Snapshot, s: Setting): Setting[] {
  const avail = availableSettings(snap);
  return MODES.map((m) => avail.find((x) => chunkerKey(x) === chunkerKey(s) && x.retrieval_mode === m)).filter((x): x is Setting => !!x);
}

/** Kembaran header B (UX-04 (a), putusan operator 12): setting yang sama (chunker, parameter, mode, anggaran) dengan header B
 * dibalik, hanya bila tersedia di snapshot. Bukan frontier per mode; hanya membaca metrik per butir yang sudah tersimpan. */
export function headerTwin(snap: Snapshot, s: Setting): Setting | undefined {
  return availableSettings(snap).find((x) => x.setting_id !== s.setting_id && x.header_b !== s.header_b && x.chunker === s.chunker
    && x.chunk_size_tokens === s.chunk_size_tokens && x.overlap_tokens === s.overlap_tokens && x.schema_version === s.schema_version
    && x.retrieval_mode === s.retrieval_mode && x.budget_tokens === s.budget_tokens);
}

/** Pembanding ukuran tetap: mode retrieval yang sama bila ada. */
export function fixedFor(snap: Snapshot, primary: Setting | undefined): Setting | undefined {
  const fixed = availableSettings(snap).filter((s) => s.chunker === "fixed_size" && !s.header_b);
  return fixed.find((s) => s.retrieval_mode === primary?.retrieval_mode) ?? fixed[0];
}

/** Dari query string: ?setting=<chunker>/<mode> atau setting_id penuh. */
export function resolveSettingParam(settings: Setting[], v: string | null): Setting | undefined {
  if (!v) return undefined;
  const byId = settings.find((s) => s.setting_id === v);
  if (byId) return byId;
  const [ch, mode] = v.split("/");
  return settings.find((s) => s.chunker === ch && (mode === undefined || s.retrieval_mode === mode) && !s.header_b);
}

export const settingParam = (s: Setting): string => `${s.chunker}/${s.retrieval_mode}`;

export function metricsFor(snap: Snapshot, settingId: string): ItemMetrics[] {
  return snap.metrics.filter((m) => m.setting_id === settingId);
}

export function pointOf(snap: Snapshot, settingId: string, split: SplitKey): GridPoint | undefined {
  return snap.grid?.[split]?.points.find((p) => p.setting_id === settingId);
}

export function frontierIds(snap: Snapshot, split: SplitKey): Set<string> {
  return new Set(snap.grid?.[split]?.frontier?.point_ids ?? []);
}

export function qualityOf(snap: Snapshot, settingId: string): QualityWithCounts | undefined {
  return snap.quality.find((q) => q.setting_id === settingId);
}

/** Peringkat retrieval per chunk_id dari R5. */
export function rankMap(r: Retrieval): Map<string, number> {
  const m = new Map<string, number>();
  r.retrieved_chunk_ids.forEach((id, i) => m.set(id, r.ranks[i] ?? i + 1));
  return m;
}

/** Recall@K mentah dari metrik per butir: butir ber-gold yang semua bagian gold-nya ada di K teratas, dan butir ber-gold total. */
export function recallAtKCounts(metrics: ItemMetrics[]): { full: number; partial: number; withGold: number } {
  const g = metrics.filter((m) => m.parts_total > 0);
  return {
    full: g.filter((m) => m.parts_hit === m.parts_total).length,
    partial: g.filter((m) => m.parts_hit > 0 && m.parts_hit < m.parts_total).length,
    withGold: g.length,
  };
}
