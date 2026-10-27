// Pemuat konten hint (docs/UI-SPEC.md §9, H-073). Satu-satunya modul yang mengimpor `hints.json`; impor statis supaya
// ikut bundel dan ekspor statis replay (H-051), tanpa jaringan. Teks bertanda draf sampai operator menyetujui (I-49).
import { useSyncExternalStore } from "react";
import raw from "../content/hints.json";

export interface HintEntry {
  id: string;
  title: string;
  body: string;
  stretch?: boolean;
}

export interface HintFile {
  version: string;
  status: string;
  locale: string;
  entries: HintEntry[];
}

export const HINT_FILE: HintFile = raw as HintFile;
const BY_ID = new Map<string, HintEntry>(HINT_FILE.entries.map((e) => [e.id, e]));

export const hintCount = (): number => BY_ID.size;
export const allHintIds = (): string[] => HINT_FILE.entries.map((e) => e.id);

/** Id tak dikenal -> undefined + peringatan dev; tidak pernah melempar galat. */
export function getHint(id: string): HintEntry | undefined {
  const e = BY_ID.get(id);
  if (!e && import.meta.env?.DEV) console.warn(`[hints] unknown hint id: ${id}`);
  return e;
}

// ---- Fitur stretch (H-017): entri `stretch: true` dirender hanya bila fiturnya ada di data/snapshot. ----
// Komponen yang merender kontrol stretch menandai id entri terkait; tanpa penanda entri tidak muncul.
let features: ReadonlySet<string> = new Set();
const featureListeners = new Set<() => void>();
const emitFeatures = () => featureListeners.forEach((l) => l());

export function markFeatures(ids: readonly string[]): void {
  if (ids.every((i) => features.has(i))) return;
  features = new Set([...features, ...ids]);
  emitFeatures();
}
export function resetFeatures(): void {
  features = new Set();
  emitFeatures();
}
export const getFeatures = (): ReadonlySet<string> => features;
export function useFeatures(): ReadonlySet<string> {
  return useSyncExternalStore(
    (l) => {
      featureListeners.add(l);
      return () => featureListeners.delete(l);
    },
    getFeatures,
    getFeatures,
  );
}

/** Aturan stretch (§9.2/§9.3): entri tanpa tag selalu tampil; entri stretch hanya bila fiturnya ada. */
export const isEntryVisible = (e: HintEntry, feats: ReadonlySet<string>): boolean => !e.stretch || feats.has(e.id);

// ---- Satu popover terbuka pada satu waktu (§9.1) ----
let openKey: string | null = null;
const openListeners = new Set<() => void>();
export type OpenAction = { type: "toggle"; key: string } | { type: "close"; key?: string };

/** Murni: transisi kunci popover terbuka. `close` dengan key hanya menutup bila key itu yang terbuka. */
export function openReducer(cur: string | null, a: OpenAction): string | null {
  if (a.type === "toggle") return cur === a.key ? null : a.key;
  return a.key === undefined || cur === a.key ? null : cur;
}
export function dispatchOpen(a: OpenAction): void {
  const next = openReducer(openKey, a);
  if (next === openKey) return;
  openKey = next;
  openListeners.forEach((l) => l());
}
export const getOpenKey = (): string | null => openKey;
export function useOpenKey(): string | null {
  return useSyncExternalStore(
    (l) => {
      openListeners.add(l);
      return () => openListeners.delete(l);
    },
    getOpenKey,
    getOpenKey,
  );
}

/** Pemicu: Enter/Spasi membuka-menutup, Esc menutup. Selain itu tidak ada aksi. */
export function keyAction(key: string, keyId: string): OpenAction | null {
  if (key === "Enter" || key === " " || key === "Spacebar") return { type: "toggle", key: keyId };
  if (key === "Escape" || key === "Esc") return { type: "close", key: keyId };
  return null;
}

// ---- Panel About / Glossary (§9.2) ----
export const INTRO_IDS = ["app.purpose", "app.audience", "app.read_frontier", "app.replay"] as const;
export const GLOSSARY_PREFIXES = ["term", "metric", "role", "verifier", "status", "chunker", "retrieval", "header_b", "model", "ui"] as const;
export const PREFIX_LABELS: Record<string, string> = {
  term: "Terms", metric: "Metrics", role: "Roles", verifier: "Verifier", status: "Validity status",
  chunker: "Chunkers", retrieval: "Retrieval modes", header_b: "Context header (B)", model: "Models", ui: "Interface",
};

export const prefixOf = (id: string): string => id.slice(0, id.indexOf("."));

export interface GlossaryGroup {
  prefix: string;
  label: string;
  entries: HintEntry[];
}

/** Glosarium dikelompokkan per awalan id; kotak cari memfilter judul dan isi (tanpa pembeda huruf besar). */
export function glossaryGroups(query: string, feats: ReadonlySet<string>): GlossaryGroup[] {
  const q = query.trim().toLowerCase();
  const match = (e: HintEntry) => !q || e.title.toLowerCase().includes(q) || e.body.toLowerCase().includes(q);
  return GLOSSARY_PREFIXES.map((prefix) => ({
    prefix,
    label: PREFIX_LABELS[prefix] ?? prefix,
    entries: HINT_FILE.entries.filter((e) => prefixOf(e.id) === prefix && isEntryVisible(e, feats) && match(e)),
  })).filter((g) => g.entries.length > 0);
}

export const introEntries = (): HintEntry[] => INTRO_IDS.map((id) => BY_ID.get(id)).filter((e): e is HintEntry => !!e);
export const isDraft = (): boolean => HINT_FILE.status !== "final";
