// F5 (putusan operator 12): UX-07 galat proxy, UX-13 garis frontier tanpa titik degenerate, UX-14 Show more U8, UX-21 enum U7.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { postAnswers } from "../api";
import { RunLogView, RUNLOG_PAGE } from "../components/RunLog";
import { frontierLine } from "../components/SettingSpace";
import { mkRun } from "./fixtures";

describe("UX-07: 502/503/504 tanpa badan galat API = backend unreachable", () => {
  const req = { item_id: "i", best_setting_id: "a", baseline_setting_id: "b", model_profile: "meta", live: false };
  it("proxy 502 tanpa JSON", async () => {
    const f = async () => new Response("Bad Gateway", { status: 502 });
    await expect(postAnswers("uupt", req, f)).rejects.toMatchObject({ code: "unreachable", message: "Backend unreachable. Showing replay data if available." });
  });
  it("503 dengan badan galat API tetap kode server", async () => {
    const f = async () => new Response(JSON.stringify({ error: { code: "model_unavailable", message: "down" } }), { status: 503 });
    await expect(postAnswers("uupt", req, f)).rejects.toMatchObject({ code: "model_unavailable" });
  });
  it("500 tanpa badan bukan unreachable", async () => {
    const f = async () => new Response("x", { status: 500 });
    await expect(postAnswers("uupt", req, f)).rejects.toMatchObject({ code: "http_500" });
  });
});

describe("UX-13: titik degenerate tidak disambung garis frontier", () => {
  const dot = (x: number, y: number, label: string | null) => ({ x, y, onFrontier: true, headerOn: false, setting: {} as never, point: { label } as never });
  it("garis hanya titik frontier tanpa label", () => {
    const line = frontierLine([dot(0, 0, "no structure recognized"), dot(1500, 0.9, null), dot(1700, 1, null)]);
    expect(line.map((d) => d.x)).toEqual([1500, 1700]);
  });
});

describe("UX-14: U8 menampilkan 20 baris + Show more", () => {
  const runs = Array.from({ length: 45 }, (_, i) => mkRun(`r${i}`, { created_at: `2026-10-27T06:${String(i).padStart(2, "0")}:00Z` }));
  const html = (shown?: number, selected: string | null = null) => renderToStaticMarkup(
    <RunLogView runs={runs} role="all" onRole={() => undefined} selected={selected} onSelect={() => undefined} shown={shown} onMore={() => undefined} />);
  it("bawaan 20 baris, tombol, label latest tetap jumlah semua baris", () => {
    const h = html();
    expect(RUNLOG_PAGE).toBe(20);
    expect((h.match(/aria-expanded=/g) ?? []).length).toBe(20);
    expect(h).toContain("Showing 20 of 45 runs.");
    expect(h).toContain("Show more");
    expect(h).toContain("Latest 45 runs (UTC)");
  });
  it("semua baris: tanpa tombol; baris terpilih di luar halaman tetap terlihat", () => {
    expect(html(100)).not.toContain("Show more");
    expect((html(20, "r30").match(/aria-expanded=/g) ?? []).length).toBe(31);
  });
});

describe("hint 1.5.0 final (UX-10, UX-23; disetujui operator 28 Okt)", () => {
  it("matrix_2x2 menjelaskan Abstained, correctly; entri glosarium label tolak ada", async () => {
    const { HINT_FILE, getHint } = await import("../lib/hints");
    expect(HINT_FILE.version).toBe("1.5.0");
    expect(HINT_FILE.status).toBe("final");
    expect(getHint("verifier.matrix_2x2")?.body).toContain("Abstained, correctly means the model declined");
    expect(getHint("verifier.matrix_2x2")?.status).toBeUndefined();
    expect(getHint("term.abstain_labels")?.title).toBe("Must refuse, No gold, Unanswerable, Abstained");
  });
});
