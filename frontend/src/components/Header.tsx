import { useStore } from "../state";
import { availableSettings } from "../lib/settings";
import { settingShort } from "../lib/labels";
import { isStatic } from "../lib/staticData";

// Nilai `family` (data) -> label UI (docs/UI-SPEC.md U0).
export const FAMILY_LABELS: Record<string, string> = { uupt: "Company Law (UU 40/2007)", akta: "Deed (synthetic)" };

// U0 Header minimal (docs/UI-SPEC.md U0): nama app, keluarga, setting terpilih, lencana REPLAY.
export function Header() {
  const { state, dispatch } = useStore();
  const snap = state.snapshot.status === "ready" ? state.snapshot.data : null;
  const sel = snap ? availableSettings(snap).find((s) => s.setting_id === state.selectedSettingId) : undefined;
  return (
    <header className="app-header">
      <span className="brand">LexRAGLab</span>
      {isStatic() ? (
        <span className="family">Family: {FAMILY_LABELS[state.family] ?? state.family}</span>
      ) : (
        <label className="family">
          Family:{" "}
          <select aria-label="Family" value={state.family} onChange={(e) => dispatch({ type: "set_family", value: e.target.value })}>
            {Object.entries(FAMILY_LABELS).map(([v, l]) => (
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
      {snap?.replay && <span className="tag neutral">REPLAY</span>}
    </header>
  );
}
