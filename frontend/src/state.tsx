import { createContext, useContext, useEffect, useMemo, useReducer, type Dispatch, type ReactNode } from "react";
import { ApiFailure, fetchDoc, fetchRetrieval, fetchSnapshot } from "./api";
import { isStatic } from "./lib/staticData";
import { availableSettings, fixedFor, matchSetting, resolveSettingParam, settingParam } from "./lib/settings";
import type { DocResponse, Item, Load, Retrieval, Snapshot, SplitName } from "./types";

// Satu store untuk seluruh UI (useReducer + context, H-023). Bentuk state mengikuti docs/UI-SPEC.md §2.

export type OriginFilter = "all" | Item["origin"];
export type ModeFilter = "all" | Item["mode"];
export type SplitFilter = "all" | SplitName;

export interface Filters {
  origin: OriginFilter;
  mode: ModeFilter;
  split: SplitFilter;
}

export interface State {
  family: string;
  budget: number | null; // null = default dari konfigurasi (server)
  snapshot: Load<Snapshot>;
  selectedItemId: string | null;
  selectedSettingId: string | null;
  split: SplitName; // split yang digambar di U2
  filters: Filters;
  compare: boolean;
  selectedChunkId: string | null;
  docs: Record<string, Load<DocResponse>>; // kunci: setting_id
  retrievals: Record<string, Load<Retrieval>>; // kunci: setting_id|item_id
  paramSetting: string | null; // ?setting= dari URL, diselesaikan saat snapshot siap
}

export type Action =
  | { type: "snapshot_loading" }
  | { type: "snapshot_error"; code: string; message: string }
  | { type: "snapshot_ready"; data: Snapshot }
  | { type: "set_family"; value: string }
  | { type: "select_item"; id: string | null }
  | { type: "select_setting"; id: string }
  | { type: "set_budget"; value: number }
  | { type: "set_split"; value: SplitName }
  | { type: "set_filters"; value: Partial<Filters> }
  | { type: "set_compare"; value: boolean }
  | { type: "select_chunk"; id: string | null }
  | { type: "doc_loading"; settingId: string }
  | { type: "doc_error"; settingId: string; code: string; message: string }
  | { type: "doc_ready"; settingId: string; data: DocResponse }
  | { type: "retrieval_loading"; key: string }
  | { type: "retrieval_error"; key: string; code: string; message: string }
  | { type: "retrieval_ready"; key: string; data: Retrieval };

export const retrievalKey = (settingId: string, itemId: string): string => `${settingId}|${itemId}`;

export function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "snapshot_loading":
      return { ...s, snapshot: { status: "loading" } };
    case "snapshot_error":
      return { ...s, snapshot: { status: "error", code: a.code, message: a.message } };
    case "snapshot_ready": {
      const avail = availableSettings(a.data);
      const prev = s.snapshot.status === "ready" ? s.snapshot.data.settings.find((x) => x.setting_id === s.selectedSettingId) : undefined;
      const fromParam = s.paramSetting ? resolveSettingParam(avail, s.paramSetting) : undefined;
      const sel = fromParam ?? matchSetting(avail, prev) ?? avail.find((x) => x.setting_id === a.data.grid?.selected?.setting_id) ?? avail[0];
      return { ...s, snapshot: { status: "ready", data: a.data }, selectedSettingId: sel?.setting_id ?? null, paramSetting: null, docs: {}, retrievals: {} };
    }
    case "set_family":
      return a.value === s.family ? s : { ...blankState(), family: a.value };
    case "select_item":
      return { ...s, selectedItemId: a.id, selectedChunkId: null };
    case "select_setting":
      return { ...s, selectedSettingId: a.id, selectedChunkId: null };
    case "set_budget":
      return { ...s, budget: a.value };
    case "set_split":
      return { ...s, split: a.value };
    case "set_filters":
      return { ...s, filters: { ...s.filters, ...a.value } };
    case "set_compare":
      return { ...s, compare: a.value, selectedChunkId: null };
    case "select_chunk":
      return { ...s, selectedChunkId: a.id };
    case "doc_loading":
      return { ...s, docs: { ...s.docs, [a.settingId]: { status: "loading" } } };
    case "doc_error":
      return { ...s, docs: { ...s.docs, [a.settingId]: { status: "error", code: a.code, message: a.message } } };
    case "doc_ready":
      return { ...s, docs: { ...s.docs, [a.settingId]: { status: "ready", data: a.data } } };
    case "retrieval_loading":
      return { ...s, retrievals: { ...s.retrievals, [a.key]: { status: "loading" } } };
    case "retrieval_error":
      return { ...s, retrievals: { ...s.retrievals, [a.key]: { status: "error", code: a.code, message: a.message } } };
    case "retrieval_ready":
      return { ...s, retrievals: { ...s.retrievals, [a.key]: { status: "ready", data: a.data } } };
  }
}

export function blankState(): State {
  return {
    family: "uupt",
    budget: null,
    snapshot: { status: "idle" },
    selectedItemId: null,
    selectedSettingId: null,
    split: "held_out",
    filters: { origin: "all", mode: "all", split: "all" },
    compare: false,
    selectedChunkId: null,
    docs: {},
    retrievals: {},
    paramSetting: null,
  };
}

const oneOf = <T extends string>(v: string | null, ok: readonly T[], d: T): T => (ok.includes(v as T) ? (v as T) : d);

/** Kondisi awal dari query string, supaya tangkapan layar deterministik:
 *  ?item=<id>&compare=1&setting=<chunker>/<mode>&split=tune|held_out&budget=<n>&origin=&mode=&fsplit= */
function initialState(): State {
  const q = new URLSearchParams(window.location.search);
  const b = Number(q.get("budget"));
  return {
    ...blankState(),
    budget: Number.isInteger(b) && b > 0 ? b : null,
    selectedItemId: q.get("item"),
    paramSetting: q.get("setting"),
    split: oneOf(q.get("split"), ["tune", "held_out"] as const, "held_out"),
    compare: q.get("compare") === "1",
    filters: {
      origin: oneOf(q.get("origin"), ["all", "operator", "spark_disetujui"] as const, "all"),
      mode: oneOf(q.get("mode"), ["all", "literal", "parafrase"] as const, "all"),
      split: oneOf(q.get("fsplit"), ["all", "tune", "held_out"] as const, "all"),
    },
  };
}

interface Store {
  state: State;
  dispatch: Dispatch<Action>;
}
const Ctx = createContext<Store | null>(null);

export function useStore(): Store {
  const v = useContext(Ctx);
  if (!v) throw new Error("StoreProvider missing");
  return v;
}

const asFailure = (e: unknown): ApiFailure => (e instanceof ApiFailure ? e : new ApiFailure("unknown", "Unexpected error."));

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const value = useMemo(() => ({ state, dispatch }), [state]);

  // Muat snapshot (ulang saat anggaran berganti).
  useEffect(() => {
    let live = true;
    dispatch({ type: "snapshot_loading" });
    fetchSnapshot(state.family, state.budget)
      .then((data) => live && dispatch({ type: "snapshot_ready", data }))
      .catch((e: unknown) => {
        if (!live) return;
        const f = asFailure(e);
        dispatch({ type: "snapshot_error", code: f.code, message: f.message });
      });
    return () => {
      live = false;
    };
  }, [state.family, state.budget]);

  const snap = state.snapshot.status === "ready" ? state.snapshot.data : null;
  const primary = snap ? availableSettings(snap).find((s) => s.setting_id === state.selectedSettingId) : undefined;
  const fixed = snap && state.compare ? fixedFor(snap, primary) : undefined;
  const wanted = [primary?.setting_id, fixed?.setting_id].filter((x): x is string => !!x);
  const wantedKey = wanted.join(",");

  // Teks + potongan untuk setting terpilih (dan ukuran tetap bila membandingkan).
  useEffect(() => {
    if (!snap) return;
    const docId = snap.corpus[0]?.doc_id;
    if (!docId) return;
    let live = true;
    for (const id of wanted) {
      if (state.docs[id]) continue;
      dispatch({ type: "doc_loading", settingId: id });
      fetchDoc(state.family, docId, id)
        .then((data) => live && dispatch({ type: "doc_ready", settingId: id, data }))
        .catch((e: unknown) => {
          if (!live) return;
          const f = asFailure(e);
          dispatch({ type: "doc_error", settingId: id, code: f.code, message: f.message });
        });
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap, wantedKey]);

  // Retrieval R5 per (setting, butir) untuk tanda "Retrieved #rank".
  useEffect(() => {
    if (!snap || !state.selectedItemId) return;
    let live = true;
    for (const id of wanted) {
      const key = retrievalKey(id, state.selectedItemId);
      if (state.retrievals[key]) continue;
      dispatch({ type: "retrieval_loading", key });
      fetchRetrieval(state.family, id, state.selectedItemId)
        .then((data) => live && dispatch({ type: "retrieval_ready", key, data }))
        .catch((e: unknown) => {
          if (!live) return;
          const f = asFailure(e);
          dispatch({ type: "retrieval_error", key, code: f.code, message: f.message });
        });
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap, wantedKey, state.selectedItemId]);

  // Cermin state ke URL (tanpa riwayat baru).
  useEffect(() => {
    if (isStatic() && new URLSearchParams(window.location.search).get("view") === "review") return; // layar Review statis tetap di URL-nya
    const q = new URLSearchParams();
    if (state.selectedItemId) q.set("item", state.selectedItemId);
    if (state.compare) q.set("compare", "1");
    if (state.budget) q.set("budget", String(state.budget));
    if (state.split !== "held_out") q.set("split", state.split);
    if (state.filters.origin !== "all") q.set("origin", state.filters.origin);
    if (state.filters.mode !== "all") q.set("mode", state.filters.mode);
    if (state.filters.split !== "all") q.set("fsplit", state.filters.split);
    if (primary) q.set("setting", settingParam(primary));
    else if (state.paramSetting) q.set("setting", state.paramSetting);
    const qs = q.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [state.selectedItemId, state.compare, state.budget, state.split, state.filters, primary, state.paramSetting]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
