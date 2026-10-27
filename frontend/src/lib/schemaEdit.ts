import { ApiFailure, postCorrection, type FetchLike } from "../api";
import type { SchemaBody, SchemaDiffEntry, SchemaLevel, SchemaRecord } from "../types";

// U5 Structure schema (docs/UI-SPEC.md U5, H-037): diff antar versi + editor koreksi (W9).
// Isi koreksi milik operator: form dimulai dari salinan versi induk; level baru kosong (tanpa nilai karangan).

const LEVEL_FIELDS = ["name", "marker_pattern", "examples", "parent_order", "is_chunk_unit"] as const;
const TOP_FIELDS = ["family", "default_chunk_level", "notes"] as const;

/** Selisih a -> b, sama bentuknya dengan `diff_bodies` backend: `[{order, field, before, after}]`. */
export function diffBodies(a: SchemaBody, b: SchemaBody): SchemaDiffEntry[] {
  const la = new Map(a.levels.map((l) => [l.order, l] as const));
  const lb = new Map(b.levels.map((l) => [l.order, l] as const));
  const orders = [...new Set([...la.keys(), ...lb.keys()])].sort((x, y) => x - y);
  const out: SchemaDiffEntry[] = [];
  for (const o of orders) {
    const x = la.get(o);
    const y = lb.get(o);
    if (!x || !y) {
      out.push({ order: o, field: "level", before: x ?? null, after: y ?? null });
      continue;
    }
    for (const f of LEVEL_FIELDS) {
      if (JSON.stringify(x[f]) !== JSON.stringify(y[f])) out.push({ order: o, field: f, before: x[f], after: y[f] });
    }
  }
  for (const f of TOP_FIELDS) {
    if (JSON.stringify(a[f]) !== JSON.stringify(b[f])) out.push({ order: null, field: f, before: a[f], after: b[f] });
  }
  return out;
}

export function diffKind(e: SchemaDiffEntry): "added" | "removed" | "changed" {
  if (e.field === "level") return e.before === null ? "added" : e.after === null ? "removed" : "changed";
  return "changed";
}

export const DIFF_KIND_LABEL = { added: "Added", removed: "Removed", changed: "Changed" } as const;

export function versionLabel(r: SchemaRecord): string {
  return r.source === "spark" ? `v${r.schema_version} · proposed by Muse Spark` : `v${r.schema_version} · operator correction`;
}

export function showValue(v: unknown): string {
  if (v === null || v === undefined) return "none";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

// ---- editor ----
export interface LevelForm {
  order: string;
  name: string;
  marker_pattern: string;
  examples: string; // satu contoh per baris
  parent_order: string; // "" = null
  is_chunk_unit: boolean;
}

export interface FieldErrors {
  general: string[];
  top: Record<string, string[]>;
  levels: Record<number, Record<string, string[]>>;
}

export const noErrors = (): FieldErrors => ({ general: [], top: {}, levels: {} });
export const hasErrors = (e: FieldErrors): boolean =>
  e.general.length > 0 || Object.keys(e.top).length > 0 || Object.keys(e.levels).length > 0;

export interface EditorState {
  parentVersion: number;
  family: string;
  levels: LevelForm[];
  defaultChunkLevel: string;
  notes: string;
  operatorNote: string;
  busy: boolean;
  errors: FieldErrors;
  savedVersion: number | null;
}

const levelToForm = (l: SchemaLevel): LevelForm => ({
  order: String(l.order),
  name: l.name,
  marker_pattern: l.marker_pattern,
  examples: l.examples.join("\n"),
  parent_order: l.parent_order === null ? "" : String(l.parent_order),
  is_chunk_unit: l.is_chunk_unit,
});

/** Form awal = salinan versi induk. */
export function editorFrom(parent: SchemaRecord): EditorState {
  return {
    parentVersion: parent.schema_version,
    family: parent.body.family,
    levels: parent.body.levels.map(levelToForm),
    defaultChunkLevel: String(parent.body.default_chunk_level),
    notes: parent.body.notes ?? "",
    operatorNote: "",
    busy: false,
    errors: noErrors(),
    savedVersion: null,
  };
}

export const emptyEditor = (): EditorState => ({
  parentVersion: 0, family: "", levels: [], defaultChunkLevel: "", notes: "", operatorNote: "", busy: false, errors: noErrors(), savedVersion: null,
});

export const blankLevel = (): LevelForm => ({ order: "", name: "", marker_pattern: "", examples: "", parent_order: "", is_chunk_unit: false });

export type EditorAction =
  | { type: "load"; parent: SchemaRecord }
  | { type: "level"; index: number; patch: Partial<LevelForm> }
  | { type: "add_level" }
  | { type: "remove_level"; index: number }
  | { type: "top"; patch: Partial<Pick<EditorState, "defaultChunkLevel" | "notes" | "operatorNote">> }
  | { type: "submitting" }
  | { type: "failed"; errors: FieldErrors }
  | { type: "saved"; version: number };

export function editorReducer(s: EditorState, a: EditorAction): EditorState {
  switch (a.type) {
    case "load":
      return editorFrom(a.parent);
    case "level":
      return { ...s, levels: s.levels.map((l, i) => (i === a.index ? { ...l, ...a.patch } : l)), savedVersion: null };
    case "add_level":
      return { ...s, levels: [...s.levels, blankLevel()], savedVersion: null };
    case "remove_level":
      return { ...s, levels: s.levels.filter((_, i) => i !== a.index), errors: noErrors(), savedVersion: null };
    case "top":
      return { ...s, ...a.patch, savedVersion: null };
    case "submitting":
      return { ...s, busy: true, errors: noErrors(), savedVersion: null };
    case "failed":
      return { ...s, busy: false, errors: a.errors };
    case "saved":
      return { ...s, busy: false, errors: noErrors(), savedVersion: a.version };
  }
}

const INT = /^-?\d+$/;

export function parseExamples(text: string): string[] {
  const lines = text.split("\n").map((l) => l.replace(/\r$/, ""));
  while (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** Form -> `SchemaA`. Isi persis dari form; bidang bukan bilangan bulat ditolak lokal per field (tanpa nilai bawaan). */
export function toBody(s: EditorState): { body: SchemaBody | null; errors: FieldErrors } {
  const errors = noErrors();
  const add = (i: number, f: string, m: string) => {
    ((errors.levels[i] ??= {})[f] ??= []).push(m);
  };
  const levels: SchemaLevel[] = s.levels.map((l, i) => {
    let order = 0;
    if (!INT.test(l.order.trim())) add(i, "order", "order must be an integer");
    else order = Number(l.order.trim());
    let parent: number | null = null;
    if (l.parent_order.trim() !== "") {
      if (!INT.test(l.parent_order.trim())) add(i, "parent_order", "parent_order must be an integer or empty");
      else parent = Number(l.parent_order.trim());
    }
    return { order, name: l.name, marker_pattern: l.marker_pattern, examples: parseExamples(l.examples), parent_order: parent, is_chunk_unit: l.is_chunk_unit };
  });
  let dcl = 0;
  if (!INT.test(s.defaultChunkLevel.trim())) errors.top.default_chunk_level = ["default_chunk_level must be an integer"];
  else dcl = Number(s.defaultChunkLevel.trim());
  if (hasErrors(errors)) return { body: null, errors };
  return { body: { family: s.family, levels, default_chunk_level: dcl, notes: s.notes === "" ? null : s.notes }, errors };
}

const FIELD_PARTS = /;\s+(?=level\[\d+\]|default_chunk_level|family differs|levels is empty|more than)/;
const LEVEL_MSG = /^level\[(\d+)\] order (-?\d+): (.*)$/s;

function levelField(msg: string): string {
  if (msg.startsWith("marker_pattern")) return "marker_pattern";
  if (msg.includes("example")) return "examples";
  if (msg.startsWith("parent_order")) return "parent_order";
  if (msg.startsWith("order")) return "order";
  if (msg.startsWith("name")) return "name";
  return "level";
}

/** Pesan `422 schema_invalid` ("; "-dipisah, backend `semantic_check`) -> galat per field bila bisa dikenali. */
export function parseSchemaErrors(message: string): FieldErrors {
  const out = noErrors();
  for (const part of message.split(FIELD_PARTS).map((p) => p.trim()).filter(Boolean)) {
    const m = LEVEL_MSG.exec(part);
    if (m) {
      const idx = Number(m[1]);
      ((out.levels[idx] ??= {})[levelField(m[3])] ??= []).push(m[3]);
    } else if (part.startsWith("default_chunk_level")) {
      (out.top.default_chunk_level ??= []).push(part);
    } else out.general.push(part);
  }
  return out;
}

export type SubmitResult = { ok: true; record: SchemaRecord } | { ok: false };

/** Kirim W9 dengan isi form. Gagal lokal -> tidak ada request. Galat server dimasukkan ke state. */
export async function submitCorrection(s: EditorState, dispatch: (a: EditorAction) => void, fetchFn?: FetchLike): Promise<SubmitResult> {
  const { body, errors } = toBody(s);
  if (!body) {
    dispatch({ type: "failed", errors });
    return { ok: false };
  }
  dispatch({ type: "submitting" });
  try {
    const record = await postCorrection(s.family, s.parentVersion, body, s.operatorNote.trim() === "" ? null : s.operatorNote, fetchFn);
    dispatch({ type: "saved", version: record.schema_version });
    return { ok: true, record };
  } catch (e) {
    const f = e instanceof ApiFailure ? e : new ApiFailure("unknown", "Unexpected error.");
    const errs = f.code === "schema_invalid" ? parseSchemaErrors(f.message) : { ...noErrors(), general: [`Could not save the correction: ${f.message}`] };
    dispatch({ type: "failed", errors: errs });
    return { ok: false };
  }
}
