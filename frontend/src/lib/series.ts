// U2: pemisahan titik ke deret header B off/on per chunker (fungsi murni; dipakai SettingSpace dan diuji langsung).

export interface SeriesDef {
  on: boolean;
  label: string;
}

export const SERIES: SeriesDef[] = [
  { on: false, label: "Header B off" },
  { on: true, label: "Header B on" },
];

export interface SeriesGroup<D, C extends string = string> {
  key: string;
  on: boolean;
  chunker: C;
  name: string;
  data: D[];
}

/** Satu kelompok per (deret, chunker) yang tidak kosong; titik masuk deret menurut `headerOn`. */
export function seriesGroups<C extends string, D extends { headerOn: boolean; setting: { chunker: C } }>(dots: D[], chunkers: readonly C[]): SeriesGroup<D, C>[] {
  const out: SeriesGroup<D, C>[] = [];
  for (const ser of SERIES) {
    for (const c of chunkers) {
      const data = dots.filter((d) => d.setting.chunker === c && d.headerOn === ser.on);
      if (data.length === 0) continue;
      out.push({ key: `${ser.on ? "on" : "off"}-${c}`, on: ser.on, chunker: c, name: `${ser.label} · ${c}`, data });
    }
  }
  return out;
}

/** Deret yang disembunyikan (tampilan saja). Default: keduanya tampil. */
export interface SeriesHidden {
  off: boolean;
  on: boolean;
}
export const NONE_HIDDEN: SeriesHidden = { off: false, on: false };
export const toggleSeries = (h: SeriesHidden, on: boolean): SeriesHidden => (on ? { ...h, on: !h.on } : { ...h, off: !h.off });
export const isHidden = (h: SeriesHidden, on: boolean): boolean => (on ? h.on : h.off);
/** Buang kelompok deret yang disembunyikan. Frontier tidak dihitung ulang di sini. */
export const visibleGroups = <G extends { on: boolean }>(groups: G[], h: SeriesHidden): G[] => groups.filter((g) => !isHidden(h, g.on));
