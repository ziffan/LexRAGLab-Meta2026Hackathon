// Format angka tampilan. Hitungan mentah, bukan persen (docs/UI-SPEC.md §1); null -> "n/a" (H-059, H-061).

export const NA = "n/a";

/** "7 of 12" atau "7 of 12 items". Penyebut tidak diketahui -> "n/a". */
export function xOfY(x: number | null | undefined, y: number | null | undefined, unit?: string): string {
  if (x === null || x === undefined || y === null || y === undefined) return NA;
  return `${x} of ${y}${unit ? ` ${unit}` : ""}`;
}

/** Nilai terukur; null/undefined -> "n/a". */
export function orNa<T>(v: T | null | undefined, fmt: (v: T) => string = String): string {
  return v === null || v === undefined ? NA : fmt(v);
}

export const fixed3 = (v: number): string => v.toFixed(3);
export const intStr = (v: number): string => String(Math.round(v));

/** Pecahan eksak dari API ("2/3") bila ada. */
export function exactStr(exact: Record<string, string> | null | undefined, key: string): string {
  const v = exact?.[key];
  return v ? v : NA;
}

/** Potong teks panjang untuk sel tabel. */
export function truncate(s: string, n: number): string {
  const cp = Array.from(s);
  return cp.length <= n ? s : `${cp.slice(0, n).join("")}…`;
}
