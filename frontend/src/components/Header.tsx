import { useEffect, useState } from "react";
import { fetchFamilies, fetchHealth } from "../api";
import { formatUsd } from "../lib/evidence";
import type { Health } from "../types";
import { useStore } from "../state";
import { availableSettings } from "../lib/settings";
import { settingShort } from "../lib/labels";
import { isStatic } from "../lib/staticData";
import { AboutPanel } from "./AboutPanel";
import { Hint } from "./Hint";

// Nilai `family` (data) -> label UI (docs/UI-SPEC.md U0).
export const FAMILY_LABELS: Record<string, string> = { uupt: "Company Law (UU 40/2007)", akta: "Deed (synthetic)" };

export interface BuildInfo { model: string | null; costMicros: number | null }

/** Health -> BuildInfo. Biaya hanya dari field server `ledger_spent_usd_micros` (buku belanja `Ledger.spent`, putusan operator 12,
 * UX-02; integer); selain itu null ("n/a"). `run_cost_usd_micros` (jumlah mentah) tidak dipakai di layar. */
export function buildInfoFromHealth(h: Health | null | undefined): BuildInfo {
  const c = h?.ledger_spent_usd_micros;
  return { model: h?.model ?? null, costMicros: typeof c === "number" && Number.isInteger(c) ? c : null };
}

/** Model ID dan total biaya run tersimpan, keduanya dari satu fetch /api/health (`model`, `ledger_spent_usd_micros`). null = belum ada / tidak terbaca. Panggil sekali (App), oper ke Header lewat prop. */
export function useBuildInfo(): BuildInfo {
  const [info, setInfo] = useState<BuildInfo>({ model: null, costMicros: null });
  useEffect(() => {
    let live = true;
    fetchHealth()
      .then((h) => live && setInfo(buildInfoFromHealth(h)))
      .catch(() => undefined);
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
      <span className="brand">LexRAGLab</span>
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
      <span className="family">
        Selected setting: <strong>{sel ? settingShort(sel) : state.snapshot.status === "error" ? "n/a" : "…"}</strong>
      </span>
      <span className="hdr-item">Model: <strong className="mono hdr-value">{build.model ?? "n/a"}</strong></span>
      <span className="hdr-item" title="Budget ledger over all stored runs: cost from model usage, plus projected cost of failed attempts">Run cost: <strong className="mono hdr-value">{build.costMicros === null ? "n/a" : formatUsd(build.costMicros)}</strong></span>
      <Hint id="app.purpose" />
      {state.family === "akta" && <Hint id="metric.transfer_test" />}
      {snap?.replay && <><span className="tag replay">REPLAY</span><Hint id="app.replay" /></>}
      <AboutPanel />
    </header>
  );
}
