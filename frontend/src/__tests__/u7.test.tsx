// U7 Export profile (M4.3 S20): keadaan, label, pesan. Klien API tiruan, tanpa jaringan dan tanpa DOM.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFailure } from "../api";
import { blankState, type State } from "../state";
import { STATIC_DISABLED, setStaticMode } from "../lib/staticData";
import type { HeldOutBlock, Profile, Report } from "../types";
import { mkSetting, mkSnapshot } from "./fixtures";

const mock = vi.hoisted(() => ({ state: null as unknown as State }));
vi.mock("../state", async (orig) => {
  const real = await orig<typeof import("../state")>();
  return { ...real, useStore: () => ({ state: mock.state, dispatch: () => undefined }) };
});

import {
  CHUNK_MATCH_TEXT, CHUNK_MISMATCH_TEXT, CORPUS_MISMATCH_TEXT, EMPTY_TEXT, BUILDING_TEXT, ProfilePanel, ProfileView, profileFileName,
  runExport, runLoad, type ExportPhase, type LoadPhase, type ProfileViewProps, type U7Client,
} from "../components/ProfileExport";

afterEach(() => setStaticMode(false));

const HELD: HeldOutBlock = { n_items: 5, by_origin: { operator: 3, spark_disetujui: 2 }, mean_span_recall: 0.6, mean_token_precision: null, fully_covered: { covered: 2, total: 4 } };
const mkProfile = (family: string, held: HeldOutBlock | null): Profile => ({
  profile_version: "1", family, setting: mkSetting("SID-1234567890abcdef", "fixed_size"), schema: null,
  corpus_hash: "c0ffee".repeat(10), config_hash: "cfg", chunk_set_hash: "chs", tokenizer: { name: "toy-ws", version: "1" },
  clean_sha256: "x", loader_rules_version: "1", packing: "stop", embedder: null, held_out: held, created_at: "2026-10-27T10:00:00Z",
});
const UUPT = mkProfile("uupt", HELD);
const AKTA = mkProfile("akta", null);

function client(over: Partial<U7Client> = {}) {
  const calls = { exp: [] as unknown[][], imp: [] as unknown[] };
  const c: U7Client = {
    exportProfile: async (f, s) => (calls.exp.push([f, s]), UUPT),
    importProfile: async (p) => (calls.imp.push(p), { ok: true, chunk_set_hash_matches: true }),
    ...over,
  };
  return { c, calls };
}
const noop = () => undefined;
const view = (over: Partial<ProfileViewProps> = {}) =>
  renderToStaticMarkup(
    <ProfileView family="uupt" settingId="SID-1" disabled={null} exportPhase={{ kind: "idle" }} loadPhase={{ kind: "idle" }} report={null}
      onExport={noop} onFile={noop} onDownload={noop} {...over} />,
  );
const stripPreview = (h: string) => h.replace(/<pre[\s\S]*?<\/pre>/g, "");
const exportBtn = (h: string) => /<button[^>]*>Export profile<\/button>/.exec(h)![0];
const loadBtn = (h: string) => /<button[^>]*>Load profile<\/button>/.exec(h)![0];

describe("S20(a) tanpa setting terpilih", () => {
  it("teks kosong, tombol nonaktif, 0 permintaan W7", async () => {
    const { c, calls } = client();
    const r = await runExport(c, "uupt", null, vi.fn());
    expect(r).toEqual({ kind: "idle" });
    expect(calls.exp).toHaveLength(0);
    const h = view({ settingId: null });
    expect(h).toContain(EMPTY_TEXT);
    expect(h).toContain("Select a setting on the frontier to export");
    expect(exportBtn(h)).toContain("disabled");
  });
  it("dengan setting: tombol aktif", () => {
    expect(exportBtn(view())).not.toContain("disabled");
  });
  it("panel terhubung store: snapshot tanpa setting terpilih", () => {
    mock.state = { ...blankState(), snapshot: { status: "ready", data: mkSnapshot({ replay: false }) }, selectedSettingId: null };
    const h = renderToStaticMarkup(<ProfilePanel client={client().c} />);
    expect(h).toContain("Select a setting on the frontier to export");
    expect(exportBtn(h)).toContain("disabled");
  });
});

describe("S20(b) ekspor berjalan", () => {
  it("keadaan building: teks dan W7 dipanggil sekali dengan family + setting", async () => {
    const seen: ExportPhase[] = [];
    const { c, calls } = client();
    const r = await runExport(c, "uupt", "SID-1", (p) => seen.push(p));
    expect(seen[0]).toEqual({ kind: "building" });
    expect(r.kind).toBe("ready");
    expect(calls.exp).toEqual([["uupt", "SID-1"]]);
    const h = view({ exportPhase: { kind: "building" } });
    expect(h).toContain(BUILDING_TEXT);
    expect(h).toContain("Building profile…");
    expect(exportBtn(h)).toContain("disabled");
  });
  it("galat W7 (422/409/tak terjangkau) tampil sebagai pesan, bukan sukses", async () => {
    for (const [code, msg] of [["validation_failed", "No grid result for this setting; run the grid first."], ["hash_mismatch", "boom"], ["unreachable", "Backend unreachable."]]) {
      const { c } = client({ exportProfile: async () => { throw new ApiFailure(code, msg); } });
      const r = await runExport(c, "uupt", "SID-1", noop);
      expect(r.kind).toBe("error");
      const h = view({ exportPhase: r });
      expect(h).toContain(msg);
      expect(h).not.toContain("Profile version");
    }
  });
});

describe("S20(c) sukses UU PT", () => {
  const h = view({ exportPhase: { kind: "ready", profile: UUPT } });
  it("label, tombol, pratinjau terformat, hitungan x of y", () => {
    for (const t of ["Profile version", "Corpus hash", "Held-out results", "Load profile", "Export profile"]) expect(h).toContain(t);
    expect(h).toContain(UUPT.corpus_hash);
    expect(h).toContain("2 of 4");
    expect(h).toContain("n/a"); // mean_token_precision null
    expect(h).toContain("&quot;profile_version&quot;: &quot;1&quot;"); // JSON terformat (indentasi 2)
    expect(h).toMatch(/<pre[^>]*>\{\n {2}&quot;/);
    expect(h).not.toMatch(/\d+(\.\d+)?%/);
  });
  it("tidak ada pratinjau/Held-out sebelum ekspor", () => {
    const b = view();
    expect(b).not.toContain("Held-out results");
    expect(b).not.toContain("Profile version");
  });
  it("nama berkas unduhan", () => {
    expect(profileFileName("uupt", "SID-1234567890abcdef")).toBe("profile-uupt-SID-12345678.json");
  });
});

describe("S20(d)(e)(f) hasil W8", () => {
  const load = async (c: U7Client) => {
    const seen: LoadPhase[] = [];
    const r = await runLoad(c, JSON.stringify(UUPT), (p) => seen.push(p));
    return { r, seen, html: view({ loadPhase: r }) };
  };
  it("(d) ok:true dan hash cocok", async () => {
    const { r, html } = await load(client().c);
    expect(r.kind).toBe("match");
    expect(html).toContain(CHUNK_MATCH_TEXT);
    expect(html).toContain("chunk hash matches source run");
    expect(html).not.toContain(CHUNK_MISMATCH_TEXT);
    expect(html).not.toContain(CORPUS_MISMATCH_TEXT);
  });
  it("(e) 409 hash_mismatch: kalimat korpus, bukan JSON mentah, bukan OK", async () => {
    const msg = `${CORPUS_MISMATCH_TEXT} (profile a1b2c3d4e5f6, loaded 0f9e8d7c6b5a).`;
    const { r, html } = await load(client({ importProfile: async () => { throw new ApiFailure("hash_mismatch", msg); } }).c);
    expect(r.kind).toBe("rejected");
    expect(html).toContain("Profile corpus hash does not match loaded corpus");
    expect(html).toContain("a1b2c3d4e5f6");
    expect(html).not.toContain(CHUNK_MATCH_TEXT);
    expect(html).not.toMatch(/\{"error"|&quot;error&quot;|\bOK\b/);
    expect(html).toContain('role="alert"');
  });
  it("(e) 409 dengan pesan lain tetap memuat kalimat korpus", async () => {
    const { html } = await load(client({ importProfile: async () => { throw new ApiFailure("hash_mismatch", "loader rules differ"); } }).c);
    expect(html).toContain("Profile corpus hash does not match loaded corpus");
    expect(html).toContain("loader rules differ");
  });
  it("(f) ok:false: peringatan tersendiri, bukan teks sukses", async () => {
    for (const res of [{ ok: false, chunk_set_hash_matches: false }, { ok: false, chunk_set_hash_matches: true }, { ok: true, chunk_set_hash_matches: false }]) {
      const { r, html } = await load(client({ importProfile: async () => res }).c);
      expect(r.kind).toBe("chunk_mismatch");
      expect(html).toContain("Chunk hash does not match source run");
      expect(html).not.toContain(CHUNK_MATCH_TEXT);
      expect(html).not.toContain(CORPUS_MISMATCH_TEXT);
    }
  });
  it("galat lain (422/400/tak terjangkau) tampil sebagai pesan galat", async () => {
    const { r, html } = await load(client({ importProfile: async () => { throw new ApiFailure("validation_failed", "bad profile"); } }).c);
    expect(r.kind).toBe("error");
    expect(html).toContain("bad profile");
    expect(html).not.toContain(CHUNK_MATCH_TEXT);
  });
});

describe("S20(g) berkas bukan JSON", () => {
  it.each(["", "not json {", "[1,2]", "42", "null", '"str"'])("galat lokal, 0 permintaan W8: %j", async (txt) => {
    const { c, calls } = client();
    const r = await runLoad(c, txt, noop);
    expect(r.kind).toBe("local_error");
    expect(calls.imp).toHaveLength(0);
    const html = view({ loadPhase: r });
    expect(html).toContain("not a JSON object");
    expect(html).not.toContain(CHUNK_MATCH_TEXT);
  });
  it("objek JSON valid dikirim apa adanya", async () => {
    const { c, calls } = client();
    await runLoad(c, JSON.stringify(UUPT), noop);
    expect(calls.imp).toEqual([UUPT]);
  });
});

describe("S20(h) akta", () => {
  const rep: Report = {
    family: "akta", title: "Transfer results",
    rows: [{ item_id: "a1", split: "Transfer", origin: "operator", mode: "literal", span_recall: { numerator: 12, denominator: 12, text: "12 of 12" }, token_precision: { numerator: 3, denominator: 6, text: "3 of 6" }, reciprocal_rank: 1, recall_at_k: 1, fully_covered: true, note: null }],
    summary: { n_items: 1, mean_span_recall: 1, mean_token_precision: 0.5, fully_covered: { numerator: 1, denominator: 1, text: "1 of 1" } },
    by_origin: {}, by_mode: {},
  };
  it("judul Transfer results, tanpa kata held-out di luar pratinjau JSON", () => {
    for (const phase of [{ kind: "idle" }, { kind: "ready", profile: AKTA }] as ExportPhase[]) {
      for (const report of [null, rep]) {
        const h = stripPreview(view({ family: "akta", exportPhase: phase, report }));
        expect(h).toContain("Transfer results");
        expect(h).toContain("Transfer test");
        expect(h).not.toContain("Held-out results");
        expect(h).not.toMatch(/held[- ]?out/i);
        expect(h).not.toMatch(/\bbest\b|selected profile/i);
      }
    }
  });
  it("laporan snapshot tampil bila ada; kosong berlabel bila tidak", () => {
    expect(view({ family: "akta", report: rep })).toContain("12 of 12");
    expect(view({ family: "akta", report: null })).toContain("No per-item transfer report is included in this snapshot.");
  });
  it("UU PT: judul bukan Transfer results", () => {
    const h = view({ exportPhase: { kind: "ready", profile: UUPT } });
    expect(h).not.toContain("Transfer results");
  });
});

describe("replay dan statis", () => {
  it("statis: tombol nonaktif dengan teks statis", () => {
    setStaticMode(true);
    mock.state = { ...blankState(), snapshot: { status: "ready", data: mkSnapshot({ replay: true }) }, selectedSettingId: "S-struct" };
    const h = renderToStaticMarkup(<ProfilePanel client={client().c} />);
    expect(h).toContain(STATIC_DISABLED);
    expect(h).toContain("Static replay: live calls are disabled");
    expect(exportBtn(h)).toContain("disabled");
    expect(loadBtn(h)).toContain("disabled");
  });
  it("replay (tak statis): tombol nonaktif dengan teks replay", () => {
    mock.state = { ...blankState(), snapshot: { status: "ready", data: mkSnapshot({ replay: true }) }, selectedSettingId: "S-struct" };
    const h = renderToStaticMarkup(<ProfilePanel client={client().c} />);
    expect(h).toContain("Replay mode");
    expect(exportBtn(h)).toContain("disabled");
    expect(loadBtn(h)).toContain("disabled");
  });
  it("live dengan setting: aktif", () => {
    mock.state = { ...blankState(), snapshot: { status: "ready", data: mkSnapshot({ replay: false }) }, selectedSettingId: "S-struct" };
    const h = renderToStaticMarkup(<ProfilePanel client={client().c} />);
    expect(exportBtn(h)).not.toContain("disabled");
    expect(loadBtn(h)).not.toContain("disabled");
  });
});

describe("keadaan snapshot dan hint", () => {
  it("loading dan error snapshot", () => {
    mock.state = { ...blankState(), snapshot: { status: "loading" } };
    expect(renderToStaticMarkup(<ProfilePanel client={client().c} />)).toContain("Loading snapshot");
    mock.state = { ...blankState(), snapshot: { status: "error", code: "http_500", message: "kaput" } };
    expect(renderToStaticMarkup(<ProfilePanel client={client().c} />)).toContain("kaput");
  });
  it("hint metric.tune_heldout hanya di UU PT; akta memakai metric.transfer_test tanpa kata held-out (A15, H-078)", () => {
    expect(view({ exportPhase: { kind: "ready", profile: UUPT } })).toContain("About: Tune vs held-out");
    const akta = stripPreview(view({ family: "akta" }));
    expect(akta).toContain("About: Transfer test");
    expect(akta).not.toContain("Tune vs held-out");
    expect(akta).not.toMatch(/held[- ]?out/i);
  });
  it("teks hint metric.transfer_test sendiri tanpa held-out", async () => {
    const { getHint } = await import("../lib/hints");
    const h = getHint("metric.transfer_test");
    expect(h).toBeTruthy();
    expect(`${h!.title} ${h!.body}`).not.toMatch(/held[- ]?out/i);
  });
});
