// U6 Review proposals (docs/UI-SPEC.md U6; scenarios/M2.1 S23-S25). Logika tanpa DOM: pengendali yang menerima `fetch`
// suntikan, konversi indeks UTF-16 <-> code point, dan jendela konteks. Komponen hanya menggambar keadaan pengendali.

export interface Span {
  start: number;
  end: number;
}

export interface ProposalBody {
  query: string;
  mode: "literal" | "parafrase";
  doc_id: string;
  teks_gold: string;
  start: number | null;
  end: number | null;
}

export interface ProposalRecord {
  proposal_id: string;
  family: string;
  body: ProposalBody;
  resolved_span: Span | null;
  validation: { offset_found: boolean; text_matches: boolean };
  review_status: "usulan" | "disetujui" | "diubah" | "ditolak";
  edited: { query: string; gold_spans: Span[]; mode: string } | null;
  operator_note: string | null;
  reviewed_at: string | null;
  item_id: string | null;
  run_id: string;
}

export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

/** Kartu boleh di-Approve hanya bila validasi span dari server lolos (U6 "Aturan"). */
export const canApprove = (p: ProposalRecord): boolean => p.validation.text_matches && p.resolved_span !== null;

export const pendingLabel = (n: number): string => `Review proposals (${n} pending)`;

export function provenanceLine(nItems: number, byOrigin: Record<string, number>): string {
  return `${nItems} items: ${byOrigin.operator ?? 0} operator-written, ${byOrigin.spark_disetujui ?? 0} Spark-proposed and operator-approved`;
}

// ---------- indeks ----------
const isHigh = (c: number): boolean => c >= 0xd800 && c <= 0xdbff;
const isLow = (c: number): boolean => c >= 0xdc00 && c <= 0xdfff;

/** Jumlah code point dalam `text[0:i)` (i = indeks UTF-16). */
export function utf16ToCodePoint(text: string, i: number): number {
  let n = 0;
  let k = 0;
  while (k < i && k < text.length) {
    k += isHigh(text.charCodeAt(k)) && k + 1 < text.length && isLow(text.charCodeAt(k + 1)) ? 2 : 1;
    n += 1;
  }
  return n;
}

/** Indeks UTF-16 dari indeks code point `cp`. */
export function codePointToUtf16(text: string, cp: number): number {
  let n = 0;
  let k = 0;
  while (n < cp && k < text.length) {
    k += isHigh(text.charCodeAt(k)) && k + 1 < text.length && isLow(text.charCodeAt(k + 1)) ? 2 : 1;
    n += 1;
  }
  return k;
}

/** Seleksi browser (indeks UTF-16, setengah terbuka) -> `[start, end)` code point (A20). Batas di tengah pasangan
 * surrogate digeser keluar: awal ke awal pasangan, akhir ke akhir pasangan. */
export function utf16ToCodePointRange(text: string, s: number, e: number): [number, number] {
  const mid = (i: number): boolean => i > 0 && i < text.length && isLow(text.charCodeAt(i)) && isHigh(text.charCodeAt(i - 1));
  const a = Math.max(0, Math.min(s, text.length));
  const b = Math.max(0, Math.min(e, text.length));
  const sa = mid(a) ? a - 1 : a;
  const eb = mid(b) ? b + 1 : b;
  return [utf16ToCodePoint(text, sa), utf16ToCodePoint(text, eb)];
}

export interface ContextView {
  text: string;
  /** Sorot relatif terhadap awal konteks, code point, setengah terbuka. */
  hlStart: number;
  hlEnd: number;
  /** Rentang konteks pada dokumen, code point. */
  ctxStart: number;
  ctxEnd: number;
}

/** Konteks kartu (A19): baris yang memuat span ± `k` baris, dipotong di batas dokumen, LF penutup bukan baris. */
export function contextWindow(text: string, start: number, end: number, k: number): ContextView {
  const cps = Array.from(text);
  const lines: [number, number][] = []; // [awal, akhir) tanpa LF
  let ls = 0;
  for (let i = 0; i < cps.length; i++) {
    if (cps[i] === "\n") {
      lines.push([ls, i]);
      ls = i + 1;
    }
  }
  if (ls < cps.length) lines.push([ls, cps.length]);
  if (lines.length === 0) return { text: "", hlStart: 0, hlEnd: 0, ctxStart: 0, ctxEnd: 0 };
  const lineOf = (pos: number): number => {
    for (let i = 0; i < lines.length; i++) if (pos <= lines[i][1]) return i;
    return lines.length - 1;
  };
  const first = Math.max(0, lineOf(start) - k);
  const last = Math.min(lines.length - 1, lineOf(Math.max(start, end - 1)) + k);
  const a = lines[first][0];
  const b = lines[last][1];
  return { text: cps.slice(a, b).join(""), hlStart: start - a, hlEnd: end - a, ctxStart: a, ctxEnd: b };
}

/** Pecah teks konteks (indeks code point) menjadi sebelum/sorot/sesudah. */
export function splitHighlight(ctx: ContextView): [string, string, string] {
  const cps = Array.from(ctx.text);
  return [cps.slice(0, ctx.hlStart).join(""), cps.slice(ctx.hlStart, ctx.hlEnd).join(""), cps.slice(ctx.hlEnd).join("")];
}

// ---------- pengendali ----------
export interface EditState {
  query: string;
  mode: "literal" | "parafrase";
  spans: Span[];
  error: string | null;
}

export interface ReviewState {
  load: "idle" | "loading" | "ready" | "error";
  loadMessage: string;
  proposals: ProposalRecord[]; // hanya yang masih `usulan`
  docs: Record<string, string>;
  contextLines: number;
  busyId: string | null;
  confirmingId: string | null;
  editingId: string | null;
  edit: EditState | null;
  notes: Record<string, string>;
  errors: Record<string, string>;
}

export interface KeyInfo {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  /** Fokus berada di kolom isian (input, textarea, select, contenteditable). */
  editable?: boolean;
}

export const isEditableTarget = (tag: string | undefined, contentEditable?: boolean): boolean =>
  contentEditable === true || ["INPUT", "TEXTAREA", "SELECT"].includes((tag ?? "").toUpperCase());

const DEFAULT_CONTEXT_LINES = 2;

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { error?: { message?: string } };
    return body?.error?.message ?? res.statusText ?? `HTTP ${res.status}`;
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

export class ReviewController {
  private s: ReviewState;
  private subs = new Set<() => void>();
  private fetchFn: FetchLike;
  private family: string;

  constructor(fetchFn: FetchLike, family = "uupt") {
    this.fetchFn = fetchFn;
    this.family = family;
    this.s = {
      load: "idle", loadMessage: "", proposals: [], docs: {}, contextLines: DEFAULT_CONTEXT_LINES, busyId: null,
      confirmingId: null, editingId: null, edit: null, notes: {}, errors: {},
    };
  }

  getState = (): ReviewState => this.s;

  subscribe = (fn: () => void): (() => void) => {
    this.subs.add(fn);
    return () => this.subs.delete(fn);
  };

  private set(patch: Partial<ReviewState>): void {
    this.s = { ...this.s, ...patch };
    this.subs.forEach((f) => f());
  }

  get pending(): number {
    return this.s.proposals.length;
  }

  async load(): Promise<void> {
    this.set({ load: "loading", loadMessage: "" });
    try {
      const res = await this.fetchFn(`/api/families/${encodeURIComponent(this.family)}/proposals`);
      if (!res.ok) throw new Error(await readError(res));
      const body = (await res.json()) as { proposals: ProposalRecord[]; context_lines?: number };
      const pending = body.proposals.filter((p) => p.review_status === "usulan");
      const docs: Record<string, string> = {};
      for (const id of new Set(pending.map((p) => p.body.doc_id))) {
        const r = await this.fetchFn(`/api/families/${encodeURIComponent(this.family)}/docs/${encodeURIComponent(id)}`);
        if (!r.ok) throw new Error(await readError(r));
        docs[id] = ((await r.json()) as { text: string }).text;
      }
      this.set({ load: "ready", proposals: pending, docs, contextLines: body.context_lines ?? DEFAULT_CONTEXT_LINES });
    } catch (e) {
      this.set({ load: "error", loadMessage: e instanceof Error ? e.message : "Backend unreachable." });
    }
  }

  find(id: string): ProposalRecord | undefined {
    return this.s.proposals.find((p) => p.proposal_id === id);
  }

  contextFor(p: ProposalRecord): ContextView | null {
    const text = this.s.docs[p.body.doc_id];
    if (text === undefined || p.resolved_span === null) return null;
    return contextWindow(text, p.resolved_span.start, p.resolved_span.end, this.s.contextLines);
  }

  setNote(id: string, note: string): void {
    this.set({ notes: { ...this.s.notes, [id]: note } });
  }

  private noteOf(id: string): string | null {
    const n = this.s.notes[id] ?? "";
    return n.trim() === "" ? null : n;
  }

  /** Kirim satu keputusan. Satu permintaan sekali jalan (klik ganda = satu permintaan). */
  private async send(id: string, body: Record<string, unknown>): Promise<boolean> {
    if (this.s.busyId !== null) return false;
    this.set({ busyId: id, errors: { ...this.s.errors, [id]: "" } });
    let msg: string | null = null;
    try {
      const res = await this.fetchFn(`/api/proposals/${encodeURIComponent(id)}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) msg = await readError(res);
    } catch {
      msg = "Backend unreachable.";
    }
    if (msg !== null) {
      this.set({ busyId: null, errors: { ...this.s.errors, [id]: `Could not save decision: ${msg.replace(/\.$/, "")}. Nothing was changed.` } });
      return false;
    }
    const { [id]: _n, ...notes } = this.s.notes;
    this.set({
      busyId: null, proposals: this.s.proposals.filter((p) => p.proposal_id !== id), notes,
      confirmingId: null, editingId: null, edit: null,
    });
    return true;
  }

  approve(id: string): Promise<boolean> {
    const p = this.find(id);
    if (!p || !canApprove(p) || this.s.busyId !== null) return Promise.resolve(false);
    return this.send(id, { decision: "disetujui", edited: null, operator_note: this.noteOf(id) });
  }

  askReject(id: string): void {
    if (this.find(id) && this.s.busyId === null) this.set({ confirmingId: id, editingId: null, edit: null });
  }

  cancelReject(): void {
    this.set({ confirmingId: null });
  }

  confirmReject(id: string): Promise<boolean> {
    if (this.s.confirmingId !== id) return Promise.resolve(false);
    return this.send(id, { decision: "ditolak", edited: null, operator_note: this.noteOf(id) });
  }

  openEdit(id: string): void {
    const p = this.find(id);
    if (!p || this.s.busyId !== null) return;
    this.set({
      editingId: id, confirmingId: null,
      edit: { query: p.body.query, mode: p.body.mode, spans: [], error: null },
    });
  }

  closeEdit(): void {
    this.set({ editingId: null, edit: null });
  }

  setEdit(patch: Partial<Pick<EditState, "query" | "mode">>): void {
    if (this.s.edit) this.set({ edit: { ...this.s.edit, ...patch, error: null } });
  }

  /** Tambah span dari seleksi: indeks UTF-16 pada TEKS DOKUMEN (bukan konteks), diubah ke code point. */
  addSelection(utf16Start: number, utf16End: number): void {
    const id = this.s.editingId;
    const p = id ? this.find(id) : undefined;
    if (!p || !this.s.edit) return;
    const [a, b] = utf16ToCodePointRange(this.s.docs[p.body.doc_id] ?? "", utf16Start, utf16End);
    if (a >= b) {
      this.set({ edit: { ...this.s.edit, error: "Select a span in the context first." } });
      return;
    }
    this.set({ edit: { ...this.s.edit, spans: [...this.s.edit.spans, { start: a, end: b }], error: null } });
  }

  removeSpan(index: number): void {
    if (this.s.edit) this.set({ edit: { ...this.s.edit, spans: this.s.edit.spans.filter((_, i) => i !== index), error: null } });
  }

  /** Validasi lokal lalu kirim `diubah`. Span tak sah atau query kosong: tidak mengirim, pesan lokal. */
  submitEdit(): Promise<boolean> {
    const id = this.s.editingId;
    const p = id ? this.find(id) : undefined;
    const e = this.s.edit;
    if (!id || !p || !e) return Promise.resolve(false);
    const n = Array.from(this.s.docs[p.body.doc_id] ?? "").length;
    let error: string | null = null;
    if (e.query.trim() === "") error = "Enter a query.";
    else if (e.spans.length === 0) error = "Select at least one span.";
    else if (e.spans.some((s) => !(Number.isInteger(s.start) && Number.isInteger(s.end) && s.start >= 0 && s.start < s.end && s.end <= n))) {
      error = "Each span needs 0 <= start < end <= document length.";
    }
    if (error !== null) {
      this.set({ edit: { ...e, error } });
      return Promise.resolve(false);
    }
    return this.send(id, {
      decision: "diubah", edited: { query: e.query, gold_spans: e.spans.map((s) => ({ start: s.start, end: s.end })), mode: e.mode },
      operator_note: this.noteOf(id),
    });
  }

  /** Pintasan A/E/R pada kartu terfokus. Tidak menangani ketikan di kolom isian. Mengembalikan true bila ditangani. */
  onKey(id: string, k: KeyInfo): boolean {
    if (k.editable || k.ctrlKey || k.metaKey || k.altKey) return false;
    if (this.s.confirmingId !== null || this.s.editingId !== null) return false;
    const key = k.key.toLowerCase();
    if (key === "a") void this.approve(id);
    else if (key === "e") this.openEdit(id);
    else if (key === "r") this.askReject(id);
    else return false;
    return true;
  }
}
