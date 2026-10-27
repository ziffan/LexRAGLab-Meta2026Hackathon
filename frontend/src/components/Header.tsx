import { useStore } from "../state";
import { availableSettings } from "../lib/settings";
import { settingShort } from "../lib/labels";

// U0 Header minimal (docs/UI-SPEC.md U0): nama app, keluarga, setting terpilih, lencana REPLAY.
export function Header() {
  const { state } = useStore();
  const snap = state.snapshot.status === "ready" ? state.snapshot.data : null;
  const sel = snap ? availableSettings(snap).find((s) => s.setting_id === state.selectedSettingId) : undefined;
  return (
    <header className="app-header">
      <span className="brand">LexRAGLab</span>
      <span className="family">Family: Company Law (UU 40/2007)</span>
      <span className="family">
        Selected setting: <strong>{sel ? settingShort(sel) : state.snapshot.status === "error" ? "n/a" : "…"}</strong>
      </span>
      {snap?.replay && <span className="tag neutral">REPLAY</span>}
    </header>
  );
}
