import { ChunksVsGold } from "./components/ChunksVsGold";
import { EvidencePanel } from "./components/Evidence";
import { Header, Tagline, useBuildInfo } from "./components/Header";
import { Hint } from "./components/Hint";
import { ProfilePanel } from "./components/ProfileExport";
import { PerItem } from "./components/PerItem";
import { ReviewScreen } from "./components/Review";
import { RunLogPanel } from "./components/RunLog";
import { SchemaPanel } from "./components/SchemaPanel";
import { SettingSpace } from "./components/SettingSpace";
import { provenanceLine, reviewHref } from "./lib/review";
import { isStatic } from "./lib/staticData";
import { useStore } from "./state";
import type { Snapshot } from "./types";

/** U9 baris provenance (UX-17, UI-SPEC U9, H-006) dari `items_summary` R3, teks dari `provenanceLine` (lib/review). null bila belum ada. */
export function footerProvenance(s: Snapshot["items_summary"] | null | undefined): string | null {
  return s && s.n_items ? provenanceLine(s.n_items, s.by_origin ?? {}) : null;
}

const reviewView = (): boolean =>
  window.location.pathname === "/review" || (isStatic() && new URLSearchParams(window.location.search).get("view") === "review");

export function App() {
  // U6 adalah layar terpisah (`/review`), bukan panel di halaman utama (docs/UI-SPEC.md).
  const build = useBuildInfo();
  const { state } = useStore();
  if (reviewView()) return <ReviewScreen />;
  const prov = footerProvenance(state.snapshot.status === "ready" ? state.snapshot.data.items_summary : null);
  return (
    <div className="app">
      <Header build={build} />
      <Tagline />
      <nav className="app-nav"><a href={reviewHref(state.family, isStatic())}>Review proposals</a><Hint id="role.d" /></nav>
      <main className="layout">
        <ChunksVsGold />
        <SettingSpace />
        <div className="wide">
          <EvidencePanel />
        </div>
        <div className="wide">
          <PerItem />
        </div>
        <div className="wide">
          <SchemaPanel />
        </div>
        <div className="wide">
          <ProfilePanel />
        </div>
        <div className="wide">
          <RunLogPanel />
        </div>
      </main>
      <footer className="app-footer">{prov && <span data-testid="provenance">{prov}</span>}<span>Research demo. Not legal advice.<Hint id="app.audience" /></span>{build.model && <span>Built with <span className="mono">{build.model}</span></span>}</footer>
    </div>
  );
}
