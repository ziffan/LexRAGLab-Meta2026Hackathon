import { ChunksVsGold } from "./components/ChunksVsGold";

export function App() {
  return (
    <div className="app">
      <header className="app-header">
        <span className="brand">LexRAGLab</span>
        <span className="family">Family: Company Law (UU 40/2007)</span>
      </header>
      <main>
        <ChunksVsGold />
      </main>
      <footer className="app-footer">Research demo. Not legal advice.</footer>
    </div>
  );
}
