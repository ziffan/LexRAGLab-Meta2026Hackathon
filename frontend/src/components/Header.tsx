import { useEffect, useState } from "react";
import { fetchFamilies, fetchHealth } from "../api";
import { formatUsd } from "../lib/evidence";
import type { Health } from "../types";
import { useStore } from "../state";
import { availableSettings } from "../lib/settings";
import { settingShort } from "../lib/labels";
import { isStatic } from "../lib/staticData";
import { AboutPanel } from "./AboutPanel";
import tagline from "../content/tagline.json";
import { Hint } from "./Hint";

// Nilai `family` (data) -> label UI (docs/UI-SPEC.md U0).
export const FAMILY_LABELS: Record<string, string> = { uupt: "Company Law (UU 40/2007)", akta: "Deed (synthetic)" };

/** `pending` (M5.1-N1): health belum selesai -> header menampilkan "loading…", bukan "n/a". Default false. */
export interface BuildInfo { model: string | null; costMicros: number | null; pending?: boolean }

/** Tooltip angka biaya U0 (H-104 butir 3). DRAF teks: ditunjukkan ke L1 sebelum final (brief L2#11 K1). */
export const RUN_COST_TITLE =
  "Main results only: budget ledger of the Contributor runs (default pool), cost from model usage plus projected cost of failed attempts. Comparator and effort-sweep spend is shown per pool in the run log.";

/** Teks header saat /api/health belum selesai (M5.1-N1, N-1): jujur "loading", bukan "n/a" (n/a = tidak terbaca). */
export const HEALTH_LOADING = "loading…";

/** Health -> BuildInfo. Biaya hanya dari field server `main_results_spent_usd_micros` (buku belanja pool default = hasil utama
 * Contributor, H-104 butir 3; integer); selain itu null ("n/a"). `ledger_spent_usd_micros` (semua pool) dan `run_cost_usd_micros`
 * (jumlah mentah) tidak dipakai di header. */
export function buildInfoFromHealth(h: Health | null | undefined): BuildInfo {
  const c = h?.main_results_spent_usd_micros;
  return { model: h?.model ?? null, costMicros: typeof c === "number" && Number.isInteger(c) ? c : null };
}

/** Health tertunda -> BuildInfo selesai (`pending: false`): resolve = nilai health, reject = null ("n/a"). Tidak pernah menolak. */
export function settleBuildInfo(p: Promise<Health>): Promise<BuildInfo> {
  return p.then((h) => ({ ...buildInfoFromHealth(h), pending: false }), () => ({ model: null, costMicros: null, pending: false }));
}

/** Model ID dan biaya hasil utama, keduanya dari satu fetch /api/health (`model`, `main_results_spent_usd_micros`). null = belum ada / tidak terbaca. Panggil sekali (App), oper ke Header lewat prop. */
export function useBuildInfo(): BuildInfo {
  const [info, setInfo] = useState<BuildInfo>({ model: null, costMicros: null, pending: true });
  useEffect(() => {
    let live = true;
    void settleBuildInfo(fetchHealth()).then((i) => live && setInfo(i));
    return () => { live = false; };
  }, []);
  return info;
}

/** Keluarga yang tersedia di ekspor statis (H-051): R2 dari `data/families.json`. null = belum terbaca / tidak ada berkasnya. */
export function useStaticFamilies(): string[] | null {
  const [fams, setFams] = useState<string[] | null>(null);
  useEffect(() => {
    if (!isStatic()) return;
    let live = true;
    fetchFamilies()
      .then((l) => live && setFams(l.map((f) => f.family)))
      .catch(() => undefined);
    return () => { live = false; };
  }, []);
  return fams;
}

/** Tagline di bawah header (UX-01). Hanya tampil bila `content/tagline.json` berstatus `final` (teks klaim, butuh persetujuan operator). */
export function Tagline({ content = tagline }: { content?: { status: string; text: string } }) {
  if (content.status !== "final" || !content.text) return null;
  return <p className="tagline" data-testid="tagline">{content.text}</p>;
}

// U0 Header minimal (docs/UI-SPEC.md U0): nama app, keluarga, setting terpilih, lencana REPLAY.
export function Header({ build = { model: null, costMicros: null } }: { build?: BuildInfo }) {
  const { state, dispatch } = useStore();
  const snap = state.snapshot.status === "ready" ? state.snapshot.data : null;
  const sel = snap ? availableSettings(snap).find((s) => s.setting_id === state.selectedSettingId) : undefined;
  const staticFams = useStaticFamilies();
  // Statis: pemilih Family bila ekspor memuat lebih dari satu keluarga (akta ikut bila amplop grid ada, H-091); selain itu label.
  const options = isStatic() ? Object.entries(FAMILY_LABELS).filter(([v]) => staticFams?.includes(v)) : Object.entries(FAMILY_LABELS);
  const picker = !isStatic() || options.length > 1;
  return (
    <header className="app-header">
      {/* UX-22: ikon hint dikelompokkan dengan label pemiliknya supaya tidak jatuh sendirian ke baris baru saat header membungkus. */}
      <span className="hdr-group"><span className="brand">LexRAGLab</span><Hint id="app.purpose" /></span>
      <span className="hdr-group">
      {!picker ? (
        <span className="family">Family: {FAMILY_LABELS[state.family] ?? state.family}</span>
      ) : (
        <label className="family">
          Family:{" "}
          <select aria-label="Family" value={state.family} onChange={(e) => dispatch({ type: "set_family", value: e.target.value })}>
            {options.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
      )}
      {state.family === "akta" && <Hint id="metric.transfer_test" />}
      </span>
      <span className="family">
        Selected setting: <strong>{sel ? settingShort(sel) : state.snapshot.status === "error" ? "n/a" : "…"}</strong>
      </span>
      <span className="hdr-item">Model: <strong className="mono hdr-value">{build.pending ? HEALTH_LOADING : build.model ?? "n/a"}</strong></span>
      <span className="hdr-item" title={RUN_COST_TITLE}>Run cost (main results): <strong className="mono hdr-value" aria-busy={build.pending || undefined}>{build.pending ? HEALTH_LOADING : build.costMicros === null ? "n/a" : formatUsd(build.costMicros)}</strong></span>
      {snap?.replay && <span className="hdr-group"><span className="tag replay">REPLAY</span><Hint id="app.replay" /></span>}
      <AboutPanel />
    </header>
  );
}
