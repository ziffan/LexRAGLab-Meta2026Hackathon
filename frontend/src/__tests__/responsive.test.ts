// @ts-ignore node builtin without @types/node
import { readFileSync } from "node:fs";
const css: string = readFileSync("src/styles.css", "utf8");
const chart: string = readFileSync("src/components/SettingSpace.tsx", "utf8");
import { describe, expect, it } from "vitest";


describe("responsive guards", () => {
  it("closed hint popover is fully collapsed", () => {
    const rule = css.split("\n").find((l: string) => l.startsWith(".hint-pop.sr-only"))!;
    expect(rule).toContain("width: 1px");
    expect(rule).toContain("overflow: hidden");
    expect(rule).toContain("padding: 0");
  });
  it("chart container shrinks", () => {
    expect(chart).toContain('<ResponsiveContainer width="100%" minWidth={0}');
    expect(css).toMatch(/\.chart \{[^}]*min-width: 0/);
  });
});
