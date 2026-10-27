// Komponen hint dan panel About / Glossary (H-073, UI-SPEC §9). Render server + logika murni (tanpa DOM, tanpa jaringan).
import { renderToStaticMarkup } from "react-dom/server";
import appSrc from "../App.tsx?raw";
import aboutSrc from "../components/AboutPanel.tsx?raw";
import chunksSrc from "../components/ChunksVsGold.tsx?raw";
import evidenceSrc from "../components/Evidence.tsx?raw";
import headerSrc from "../components/Header.tsx?raw";
import perItemSrc from "../components/PerItem.tsx?raw";
import qualitySrc from "../components/QualityPanel.tsx?raw";
import runlogSrc from "../components/RunLog.tsx?raw";
import schemaSrc from "../components/SchemaPanel.tsx?raw";
import spaceSrc from "../components/SettingSpace.tsx?raw";
import loaderSrc from "../lib/hints.ts?raw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Hint } from "../components/Hint";
import {
  GLOSSARY_PREFIXES, HINT_FILE, allHintIds, dispatchOpen, getHint, getOpenKey, glossaryGroups, isEntryVisible, keyAction,
  markFeatures, openReducer, resetFeatures,
} from "../lib/hints";

afterEach(() => {
  resetFeatures();
  dispatchOpen({ type: "close" });
});


describe("Hint: tertutup default dan aria", () => {
  const html = renderToStaticMarkup(<Hint id="metric.span_recall" />);
  it("pemicu button, tertutup, nama aksesibel About: {title}", () => {
    const title = getHint("metric.span_recall")!.title;
    expect(html).toContain('type="button"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain(`aria-label="About: ${title}"`);
    expect(html).toContain("aria-controls=");
    expect(html).toContain("aria-describedby=");
  });
  it("isi selalu di DOM tetapi tersembunyi secara visual saat tertutup", () => {
    expect(html).toContain("hint-pop sr-only");
    expect(html).toContain(getHint("metric.span_recall")!.body.slice(0, 20));
  });
  it("aria-describedby menunjuk id isi", () => {
    const d = /aria-describedby="([^"]+)"/.exec(html)![1];
    expect(html).toContain(`id="${d}"`);
  });
});

describe("Hint: id tak dikenal", () => {
  it("tidak merender apa pun dan memberi peringatan dev, tidak crash", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expect(renderToStaticMarkup(<Hint id="no.such_id" />)).toBe("");
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe("Buka/tutup lewat papan ketik dan satu popover", () => {
  it("Enter dan Spasi membuka-menutup; Esc menutup; tombol lain tidak berbuat apa-apa", () => {
    expect(keyAction("Enter", "a")).toEqual({ type: "toggle", key: "a" });
    expect(keyAction(" ", "a")).toEqual({ type: "toggle", key: "a" });
    expect(keyAction("Escape", "a")).toEqual({ type: "close", key: "a" });
    expect(keyAction("Tab", "a")).toBeNull();
  });
  it("reducer: toggle membuka lalu menutup; membuka b menutup a; close hanya menutup pemiliknya", () => {
    let k = openReducer(null, { type: "toggle", key: "a" });
    expect(k).toBe("a");
    k = openReducer(k, { type: "toggle", key: "b" });
    expect(k).toBe("b");
    expect(openReducer(k, { type: "close", key: "a" })).toBe("b");
    expect(openReducer(k, { type: "close", key: "b" })).toBeNull();
    expect(openReducer(k, { type: "toggle", key: "b" })).toBeNull();
    expect(openReducer(k, { type: "close" })).toBeNull();
  });
  it("store: hanya satu kunci terbuka pada satu waktu", () => {
    dispatchOpen({ type: "toggle", key: "x" });
    dispatchOpen({ type: "toggle", key: "y" });
    expect(getOpenKey()).toBe("y");
  });
});

describe("Glosarium", () => {
  it("tanpa filter: dikelompokkan per awalan, urut sesuai spec, hanya awalan glosarium", () => {
    const g = glossaryGroups("", new Set());
    const prefixes = g.map((x) => x.prefix);
    expect(prefixes.every((p) => (GLOSSARY_PREFIXES as readonly string[]).includes(p))).toBe(true);
    expect(prefixes).toContain("metric");
    expect(prefixes).not.toContain("app");
    for (const grp of g) expect(grp.entries.every((e) => e.id.startsWith(`${grp.prefix}.`))).toBe(true);
  });
  it("filter memeriksa judul dan isi tanpa beda huruf besar", () => {
    const e = getHint("metric.span_recall")!;
    const byTitle = glossaryGroups(e.title.toUpperCase(), new Set()).flatMap((g) => g.entries);
    expect(byTitle.map((x) => x.id)).toContain("metric.span_recall");
    const word = HINT_FILE.entries.find((x) => x.id === "role.b")!.body.split(" ").find((w) => w.length > 8)!;
    expect(glossaryGroups(word, new Set()).flatMap((g) => g.entries).map((x) => x.id)).toContain("role.b");
    expect(glossaryGroups("zzzz-tidak-ada-zzzz", new Set())).toEqual([]);
  });
});

describe("Aturan stretch", () => {
  const stretchIds = HINT_FILE.entries.filter((e) => e.stretch).map((e) => e.id);
  it("ada entri stretch di berkas", () => expect(stretchIds.length).toBeGreaterThan(0));
  it("glosarium: entri stretch tidak muncul tanpa fitur, muncul bila ditandai", () => {
    const ids = (f: ReadonlySet<string>) => glossaryGroups("", f).flatMap((g) => g.entries.map((e) => e.id));
    for (const id of stretchIds) expect(ids(new Set())).not.toContain(id);
    expect(ids(new Set(["status.revoked"]))).toContain("status.revoked");
    expect(ids(new Set(["status.revoked"]))).not.toContain("status.valid");
    expect(isEntryVisible(getHint("status.valid")!, new Set())).toBe(false);
    expect(isEntryVisible(getHint("metric.span_recall")!, new Set())).toBe(true);
  });
  it("Hint stretch tidak dirender sampai fiturnya ditandai", () => {
    expect(renderToStaticMarkup(<Hint id="status.revoked" />)).toBe("");
    markFeatures(["status.revoked"]);
    expect(renderToStaticMarkup(<Hint id="status.revoked" />)).toContain("hint-btn");
  });
});

describe("Hint masuk bundel dan terpasang", () => {
  it("modul pemuat mengimpor JSON secara statis; tidak ada fetch", () => {
    const s = loaderSrc;
    expect(s).toMatch(/import raw from "\.\.\/content\/hints\.json"/);
    expect(s).not.toMatch(/fetch\(/);
    expect(allHintIds().length).toBeGreaterThan(30);
  });
  it("App memuat modul pemuat lewat komponen (Header -> AboutPanel -> lib/hints)", () => {
    expect(appSrc).toContain('./components/Hint"');
    expect(headerSrc).toContain("AboutPanel");
    expect(aboutSrc).toContain("../lib/hints");
  });
  it("setiap id yang dipasang di komponen ada di berkas", () => {
    const files: Record<string, string> = {
      App: appSrc, Header: headerSrc, ChunksVsGold: chunksSrc, SettingSpace: spaceSrc, Evidence: evidenceSrc,
      PerItem: perItemSrc, QualityPanel: qualitySrc, SchemaPanel: schemaSrc, RunLog: runlogSrc,
    };
    const known = new Set(allHintIds());
    for (const [f, code] of Object.entries(files)) for (const m of code.matchAll(/<Hint id="([^"]+)"/g)) expect(known.has(m[1]), `${f}: ${m[1]}`).toBe(true);
    const shell = spaceSrc.match(/hints=\{\[([^\]]+)\]\}/)![1];
    for (const m of shell.matchAll(/"([^"]+)"/g)) expect(known.has(m[1]), m[1]).toBe(true);
  });
});
