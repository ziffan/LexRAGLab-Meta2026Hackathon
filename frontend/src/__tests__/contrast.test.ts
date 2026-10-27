// @ts-ignore node builtin without @types/node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Kontras WCAG 2.x untuk pasangan teks/latar token tema (H-083, docs/UI-SPEC.md "Theme (H-083)"). Nilai dibaca dari src/theme.css.
const css: string = readFileSync("src/theme.css", "utf8");
const tok: Record<string, string> = {};
for (const m of css.matchAll(/--([a-z-]+):\s*(#[0-9A-Fa-f]{6})\s*;/g)) tok[m[1]] = m[2];

const lin = (c: number): number => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
const lum = (hex: string): number => {
  const n = parseInt(hex.slice(1), 16);
  return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
};
export const ratio = (fg: string, bg: string): number => {
  const a = lum(tok[fg]), b = lum(tok[bg]);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
};

const PAIRS: [string, string][] = [
  ["ink", "bg"], ["ink", "surface"], ["muted", "bg"], ["muted", "surface"], ["muted", "panel-head"],
  ["accent", "surface"], ["accent", "bg"], ["accent-hover", "surface"], ["on-accent", "accent"],
  ["pass-text", "pass-bg"], ["fail-text", "fail-bg"], ["notrun-text", "notrun-bg"],
  ["err-text", "err-bg"], ["err-text", "surface"],
  ["head-ink", "head-bg"], ["head-muted", "head-bg"],
  ["replay-ink", "replay-bg"], ["ink", "gold"], ["series-on", "surface"], ["series-off", "surface"],
];

describe("theme contrast (WCAG AA 4.5:1)", () => {
  it("parses all tokens used", () => {
    for (const [a, b] of PAIRS) { expect(tok[a], a).toBeDefined(); expect(tok[b], b).toBeDefined(); }
  });
  for (const [fg, bg] of PAIRS) {
    it(`${fg} on ${bg}`, () => { expect(ratio(fg, bg)).toBeGreaterThanOrEqual(4.5); });
  }
  it("no literal hex outside theme.css in styles.css", () => {
    const styles: string = readFileSync("src/styles.css", "utf8");
    expect(styles).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
