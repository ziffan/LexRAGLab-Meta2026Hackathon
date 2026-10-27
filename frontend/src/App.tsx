import { ChunksVsGold } from "./components/ChunksVsGold";
import { EvidencePanel } from "./components/Evidence";
import { Header } from "./components/Header";
import { PerItem } from "./components/PerItem";
import { ReviewScreen } from "./components/Review";
import { RunLogPanel } from "./components/RunLog";
import { SchemaPanel } from "./components/SchemaPanel";
import { SettingSpace } from "./components/SettingSpace";

export function App() {
  // U6 adalah layar terpisah (`/review`), bukan panel di halaman utama (docs/UI-SPEC.md).
  if (window.location.pathname === "/review") return <ReviewScreen />;
  return (
    <div className="app">
      <Header />
      <nav className="app-nav"><a href="/review">Review proposals</a></nav>
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
          <RunLogPanel />
        </div>
      </main>
      <footer className="app-footer">Research demo. Not legal advice.</footer>
    </div>
  );
}
