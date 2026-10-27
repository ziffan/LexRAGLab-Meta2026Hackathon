import { ChunksVsGold } from "./components/ChunksVsGold";
import { EvidencePanel } from "./components/Evidence";
import { Header, useBuildInfo } from "./components/Header";
import { Hint } from "./components/Hint";
import { ProfilePanel } from "./components/ProfileExport";
import { PerItem } from "./components/PerItem";
import { ReviewScreen } from "./components/Review";
import { RunLogPanel } from "./components/RunLog";
import { SchemaPanel } from "./components/SchemaPanel";
import { SettingSpace } from "./components/SettingSpace";
import { reviewHref } from "./lib/review";
import { isStatic } from "./lib/staticData";
import { useStore } from "./state";

const reviewView = (): boolean =>
  window.location.pathname === "/review" || (isStatic() && new URLSearchParams(window.location.search).get("view") === "review");

export function App() {
  // U6 adalah layar terpisah (`/review`), bukan panel di halaman utama (docs/UI-SPEC.md).
  const build = useBuildInfo();
  const { state } = useStore();
  if (reviewView()) return <ReviewScreen />;
  return (
    <div className="app">
      <Header build={build} />
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
      <footer className="app-footer"><span>Research demo. Not legal advice.<Hint id="app.audience" /></span>{build.model && <span>Built with <span className="mono">{build.model}</span></span>}</footer>
    </div>
  );
}
