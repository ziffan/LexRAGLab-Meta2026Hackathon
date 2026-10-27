import type { Chunk, Span } from "../types";

export const CONTEXT_NEIGHBOURS = 1; // jumlah potongan konteks di tiap sisi gold (pilihan tampilan, bukan data)

export const contains = (c: Chunk, s: Span): boolean => c.start <= s.start && s.end <= c.end;
export const overlaps = (c: Chunk, s: Span): boolean => c.start < s.end && s.start < c.end;

/** Span gold yang tidak utuh di satu potongan pun dan menyentuh minimal dua potongan. */
export function splitSpans(chunks: Chunk[], spans: Span[]): Span[] {
  return spans.filter((s) => !chunks.some((c) => contains(c, s)) && chunks.filter((c) => overlaps(c, s)).length >= 2);
}

/** Batas potongan (atas = awal, bawah = akhir) yang jatuh di dalam span gold yang terbelah. */
export function edgeSplit(c: Chunk, split: Span[]): { top: boolean; bottom: boolean } {
  return {
    top: split.some((s) => s.start < c.start && c.start < s.end),
    bottom: split.some((s) => s.start < c.end && c.end < s.end),
  };
}

/** Potongan yang ditampilkan: yang beririsan dengan gold, ditambah satu potongan tetangga di tiap sisi (konteks), berurutan. */
export function visibleChunks(chunks: Chunk[], spans: Span[]): Chunk[] {
  if (spans.length === 0) return [];
  const sorted = [...chunks].sort((a, b) => a.start - b.start || a.end - b.end);
  const hit = sorted.map((c, i) => (spans.some((s) => overlaps(c, s)) ? i : -1)).filter((i) => i >= 0);
  if (hit.length === 0) return [];
  const from = Math.max(0, hit[0] - CONTEXT_NEIGHBOURS);
  const to = Math.min(sorted.length - 1, hit[hit.length - 1] + CONTEXT_NEIGHBOURS);
  return sorted.slice(from, to + 1);
}

export interface Piece {
  text: string;
  gold: boolean;
}

/** Teks potongan dipecah menjadi bagian gold dan non-gold. Offset code point -> indeks UTF-16 ditangani lewat Array.from. */
export function pieces(codePoints: string[], c: Chunk, spans: Span[]): Piece[] {
  const marks: Span[] = spans
    .filter((s) => overlaps(c, s))
    .map((s) => ({ start: Math.max(s.start, c.start), end: Math.min(s.end, c.end) }))
    .sort((a, b) => a.start - b.start);
  const out: Piece[] = [];
  let pos = c.start;
  for (const m of marks) {
    if (m.start > pos) out.push({ text: codePoints.slice(pos, m.start).join(""), gold: false });
    const from = Math.max(m.start, pos);
    if (m.end > from) out.push({ text: codePoints.slice(from, m.end).join(""), gold: true });
    pos = Math.max(pos, m.end);
  }
  if (pos < c.end) out.push({ text: codePoints.slice(pos, c.end).join(""), gold: false });
  return out;
}

/** Offset potongan harus cocok dengan teks sumber (UI-SPEC U1: galat, bukan peringatan). */
export function offsetsMatch(chunks: Chunk[], textLength: number, cleanSha256: string | undefined): boolean {
  return chunks.every((c) => c.start >= 0 && c.start < c.end && c.end <= textLength && (cleanSha256 === undefined || c.clean_sha256 === cleanSha256));
}
