import { createContext, useContext, useEffect, useMemo, useReducer, type Dispatch, type ReactNode } from "react";
import { ApiFailure, fetchDoc, fetchSnapshot } from "./api";
import type { DocResponse, Load, Setting, Snapshot } from "./types";

// Satu store untuk seluruh UI (useReducer + context, H-023). Bentuk state mengikuti docs/UI-SPEC.md §2.

export interface State {
  family: string;
  snapshot: Load<Snapshot>;
  selectedItemId: string | null;
  selectedSettingId: string | null;
  compare: boolean;
  selectedChunkId: string | null;
  docs: Record<string, Load<DocResponse>>; // kunci: setting_id
}

type Action =
  | { type: "snapshot_loading" }
  | { type: "snapshot_error"; code: string; message: string }
  | { type: "snapshot_ready"; data: Snapshot }
  | { type: "select_item"; id: string | null }
  | { type: "select_setting"; id: string }
  | { type: "set_compare"; value: boolean }
  | { type: "select_chunk"; id: string | null }
  | { type: "doc_loading"; settingId: string }
  | { type: "doc_error"; settingId: string; code: string; message: string }
  | { type: "doc_ready"; settingId: string; data: DocResponse };

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "snapshot_loading":
      return { ...s, snapshot: { status: "loading" } };
    case "snapshot_error":
      return { ...s, snapshot: { status: "error", code: a.code, message: a.message } };
    case "snapshot_ready": {
      const settings = a.data.settings;
      const keep = settings.find((x) => x.setting_id === s.selectedSettingId);
      return { ...s, snapshot: { status: "ready", data: a.data }, selectedSettingId: (keep ?? settings[0])?.setting_id ?? null };
    }
    case "select_item":
      return { ...s, selectedItemId: a.id, selectedChunkId: null };
    case "select_setting":
      return { ...s, selectedSettingId: a.id, selectedChunkId: null };
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
  }
}

/** Kondisi awal dari query string, supaya tangkapan layar deterministik: ?item=<id>&compare=1&setting=fixed_size. */
function initialState(): State {
  const q = new URLSearchParams(window.location.search);
  return {
    family: "uupt",
    snapshot: { status: "idle" },
    selectedItemId: q.get("item"),
    selectedSettingId: q.get("setting"), // nama chunker sementara; diselesaikan ke setting_id saat snapshot siap
    compare: q.get("compare") === "1",
    selectedChunkId: null,
    docs: {},
  };
}

const FIXED: Setting["chunker"] = "fixed_size";

export function fixedSetting(snap: Snapshot): Setting | undefined {
  return snap.settings.find((x) => x.chunker === FIXED);
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

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const value = useMemo(() => ({ state, dispatch }), [state]);

  // Muat snapshot sekali.
  useEffect(() => {
    let live = true;
    dispatch({ type: "snapshot_loading" });
    fetchSnapshot(state.family)
      .then((data) => {
        if (!live) return;
        // ?setting=<chunker> -> setting_id
        const byName = data.settings.find((x) => x.chunker === state.selectedSettingId);
        dispatch({ type: "snapshot_ready", data });
        if (byName) dispatch({ type: "select_setting", id: byName.setting_id });
      })
      .catch((e: unknown) => {
        if (!live) return;
        const f = e instanceof ApiFailure ? e : new ApiFailure("unknown", "Unexpected error.");
        dispatch({ type: "snapshot_error", code: f.code, message: f.message });
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.family]);

  // Muat teks + potongan untuk setting terpilih (dan setting ukuran tetap bila membandingkan).
  const snap = state.snapshot.status === "ready" ? state.snapshot.data : null;
  const fixedId = snap ? fixedSetting(snap)?.setting_id : undefined;
  const wanted = [state.selectedSettingId, state.compare ? fixedId : undefined].filter(
    (x): x is string => !!x && !!snap?.settings.some((s) => s.setting_id === x),
  );
  const wantedKey = wanted.join(",");
  useEffect(() => {
    if (!snap) return;
    let live = true;
    const docId = snap.corpus[0]?.doc_id;
    if (!docId) return;
    for (const id of wanted) {
      if (state.docs[id]) continue;
      dispatch({ type: "doc_loading", settingId: id });
      fetchDoc(state.family, docId, id)
        .then((data) => live && dispatch({ type: "doc_ready", settingId: id, data }))
        .catch((e: unknown) => {
          if (!live) return;
          const f = e instanceof ApiFailure ? e : new ApiFailure("unknown", "Unexpected error.");
          dispatch({ type: "doc_error", settingId: id, code: f.code, message: f.message });
        });
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap, wantedKey]);

  // Cermin state ke URL (tanpa riwayat baru).
  useEffect(() => {
    const q = new URLSearchParams();
    if (state.selectedItemId) q.set("item", state.selectedItemId);
    if (state.compare) q.set("compare", "1");
    const chosen = snap?.settings.find((x) => x.setting_id === state.selectedSettingId);
    if (chosen && chosen.chunker !== "structure_handwritten") q.set("setting", chosen.chunker);
    const qs = q.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [state.selectedItemId, state.compare, state.selectedSettingId, snap]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
