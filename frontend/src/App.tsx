import { ChunksVsGold } from "./components/ChunksVsGold";
import { Header } from "./components/Header";
import { PerItem } from "./components/PerItem";
import { SettingSpace } from "./components/SettingSpace";

export function App() {
  return (
    <div className="app">
      <Header />
      <main className="layout">
        <ChunksVsGold />
        <SettingSpace />
        <div className="wide">
          <PerItem />
        </div>
      </main>
      <footer className="app-footer">Research demo. Not legal advice.</footer>
    </div>
  );
}
