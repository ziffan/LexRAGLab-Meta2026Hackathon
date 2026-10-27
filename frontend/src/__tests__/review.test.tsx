// M2.1 U6 (scenarios/M2.1 S22-S25). Tanpa DOM: pengendali dengan `fetch` palsu + render server untuk atribut dan label.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProposalCard, ReviewList } from "../components/Review";
import {
  ReviewController, canApprove, contextWindow, isEditableTarget, pendingLabel, provenanceLine, utf16ToCodePointRange,
  type FetchLike, type ProposalRecord,
} from "../lib/review";

const DX = "\u{1F600} Pasal 1\n(1) Aaa bbb ccc.\n(2) Ddd eee fff.\nPasal 2\n(1) Aaa bbb ccc.\n(2) Ggg hhh iii.\n";
const cp = (s: string): string[] => Array.from(s);
const slice = (a: number, b: number): string => cp(DX).slice(a, b).join("");

const rec = (id: string, query: string, teks: string, resolved: [number, number] | null, offset: boolean, matches: boolean): ProposalRecord => ({
  proposal_id: id, family: "uupt",
  body: { query, mode: "literal", doc_id: "doc-x", teks_gold: teks, start: null, end: null },
  resolved_span: resolved ? { start: resolved[0], end: resolved[1] } : null,
  validation: { offset_found: offset, text_matches: matches },
  review_status: "usulan", edited: null, operator_note: null, reviewed_at: null, item_id: null, run_id: "r1",
});
const L1 = rec("L1", "QL1", "(2) Ddd eee fff.", [27, 43], true, true);
const L3 = rec("L3", "QL3", "(2) Ggg hhh iii.", [69, 84], true, false);
const L2 = rec("L2", "QL2", "(1) Aaa bbb ccc.", null, false, false);

interface Call { url: string; method: string; body: any }

interface RigOpts { fail?: { status: number; message: string } | null; deferred?: boolean }

function rig(opts: RigOpts = {}) {
  const calls: Call[] = [];
  const gates: Array<() => void> = [];
  const fetchFn: FetchLike = async (url, init) => {
    const method = init?.method ?? "GET";
    if (method === "GET" && url.endsWith("/proposals")) {
      return new Response(JSON.stringify({ proposals: [L1, L3, L2], pending: 3, context_lines: 1 }), { status: 200 });
    }
    if (method === "GET" && url.includes("/docs/")) return new Response(JSON.stringify({ doc_id: "doc-x", text: DX }), { status: 200 });
    calls.push({ url, method, body: JSON.parse(String(init?.body ?? "null")) });
    if (opts.deferred) await new Promise<void>((r) => gates.push(r));
    if (opts.fail) return new Response(JSON.stringify({ error: { code: "x", message: opts.fail.message } }), { status: opts.fail.status });
    return new Response(JSON.stringify({ proposal: {}, item: null }), { status: 200 });
  };
  const ctl = new ReviewController(fetchFn);
  return { ctl, calls, gates };
}

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

async function ready(opts: RigOpts = {}) {
  const r = rig(opts);
  await r.ctl.load();
  return r;
}

const cardProps = (p: ProposalRecord, over: Partial<Parameters<typeof ProposalCard>[0]> = {}) => {
  const noop = () => undefined;
  return {
    proposal: p, context: contextWindow(DX, p.resolved_span?.start ?? 0, p.resolved_span?.end ?? 0, 1), docText: DX, busy: false,
    confirming: false, editing: false, edit: null, note: "", error: "",
    actions: {
      approve: noop, edit: noop, reject: noop, confirmReject: noop, cancelReject: noop, setNote: noop, setEdit: noop,
      addSelection: noop, removeSpan: noop, submitEdit: noop, closeEdit: noop, key: noop,
    },
    ...over,
  };
};

const DISABLED_APPROVE = /<button(?=[^>]*\sdisabled="")[^>]*>Approve<\/button>/;

describe("S23 aturan layar Review", () => {
  it("1: Approve nonaktif pada validasi gagal; label dan mode dari server", () => {
    const h1 = renderToStaticMarkup(<ProposalCard {...cardProps(L1)} />);
    const h3 = renderToStaticMarkup(<ProposalCard {...cardProps(L3)} />);
    const h2 = renderToStaticMarkup(<ProposalCard {...cardProps(L2, { context: null })} />);
    expect(h1).not.toMatch(DISABLED_APPROVE);
    expect(h3).toMatch(DISABLED_APPROVE);
    expect(h2).toMatch(DISABLED_APPROVE);
    for (const h of [h1, h3, h2]) {
      expect(h).toContain("Offset found");
      expect(h).toContain("Text matches");
      expect(h).toMatch(/<button[^>]*>Edit<\/button>/);
      expect(h).not.toMatch(/<button(?=[^>]*\sdisabled="")[^>]*>(Edit|Reject)<\/button>/);
      expect(h).toContain("Literal");
    }
    expect(h3).toContain('aria-disabled="true"');
    expect(canApprove(L1)).toBe(true);
    expect(canApprove(L3)).toBe(false);
    expect(canApprove(L2)).toBe(false);
    expect(renderToStaticMarkup(<ProposalCard {...cardProps({ ...L1, body: { ...L1.body, mode: "parafrase" } })} />)).toContain("Paraphrase");
  });

  it("2: pintasan A pada kartu gagal tidak mengirim; pada L1 mengirim satu", async () => {
    const { ctl, calls } = await ready();
    expect(ctl.onKey("L3", { key: "a" })).toBe(true);
    expect(ctl.onKey("L2", { key: "A" })).toBe(true);
    await flush();
    expect(calls).toHaveLength(0);
    ctl.onKey("L1", { key: "a" });
    await flush();
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ url: "/api/proposals/L1/decision", method: "POST", body: { decision: "disetujui", edited: null, operator_note: null } });
  });

  it("3: Reject memakai konfirmasi", async () => {
    const { ctl, calls } = await ready();
    ctl.onKey("L1", { key: "r" });
    expect(ctl.getState().confirmingId).toBe("L1");
    expect(renderToStaticMarkup(<ProposalCard {...cardProps(L1, { confirming: true })} />)).toContain("Confirm reject");
    await flush();
    expect(calls).toHaveLength(0);
    ctl.cancelReject();
    await flush();
    expect(calls).toHaveLength(0);
    expect(ctl.pending).toBe(3);
    ctl.askReject("L1");
    await ctl.confirmReject("L1");
    expect(calls).toHaveLength(1);
    expect(calls[0].body.decision).toBe("ditolak");
  });

  it("4: Edit membuka form tanpa permintaan; span tak sah tidak dikirim", async () => {
    const { ctl, calls } = await ready();
    ctl.openEdit("L2");
    expect(ctl.getState().editingId).toBe("L2");
    expect(await ctl.submitEdit()).toBe(false); // belum ada span
    ctl.addSelection(5, 5); // seleksi kosong (start >= end)
    expect(ctl.getState().edit?.error).toBeTruthy();
    expect(await ctl.submitEdit()).toBe(false);
    ctl.setEdit({ query: "   " });
    ctl.addSelection(28, 44);
    expect(await ctl.submitEdit()).toBe(false);
    expect(ctl.getState().edit?.error).toBe("Enter a query.");
    expect(calls).toHaveLength(0);
  });

  it("5: klik ganda cepat pada Approve = satu permintaan", async () => {
    const { ctl, calls, gates } = await ready({ deferred: true });
    const a = ctl.approve("L1");
    const b = ctl.approve("L1");
    expect(ctl.getState().busyId).toBe("L1");
    expect(renderToStaticMarkup(<ProposalCard {...cardProps(L1, { busy: true })} />)).toMatch(DISABLED_APPROVE);
    await flush();
    gates.forEach((g) => g());
    expect(await a).toBe(true);
    expect(await b).toBe(false);
    expect(calls).toHaveLength(1);
  });

  it("6: sukses menghapus kartu dan menurunkan penghitung; antrean kosong", async () => {
    const { ctl, calls } = await ready();
    expect(pendingLabel(ctl.pending)).toBe("Review proposals (3 pending)");
    await ctl.approve("L1");
    expect(ctl.pending).toBe(2);
    expect(ctl.find("L1")).toBeUndefined();
    ctl.askReject("L3");
    await ctl.confirmReject("L3");
    ctl.askReject("L2");
    await ctl.confirmReject("L2");
    expect(ctl.pending).toBe(0);
    expect(calls).toHaveLength(3);
    expect(renderToStaticMarkup(<ReviewList state={ctl.getState()} ctl={ctl} />)).toContain("No pending proposals");
  });

  it.each([500, 409])("7: galat server %i: pesan, kartu tetap, penghitung tidak berubah", async (status) => {
    const { ctl } = await ready({ fail: { status, message: "Boom." } });
    expect(await ctl.approve("L1")).toBe(false);
    expect(ctl.getState().errors.L1).toBe("Could not save decision: Boom. Nothing was changed.");
    expect(ctl.pending).toBe(3);
    expect(ctl.find("L1")).toBeDefined();
    expect(ctl.getState().busyId).toBeNull();
    const html = renderToStaticMarkup(<ReviewList state={ctl.getState()} ctl={ctl} />);
    expect(html).toContain("Could not save decision: Boom. Nothing was changed.");
  });

  it("8: pintasan tidak menelan ketikan di kolom isian", async () => {
    const { ctl, calls } = await ready();
    expect(isEditableTarget("INPUT")).toBe(true);
    expect(isEditableTarget("textarea")).toBe(true);
    expect(isEditableTarget("DIV", true)).toBe(true);
    expect(isEditableTarget("ARTICLE")).toBe(false);
    for (const k of ["a", "e", "r"]) expect(ctl.onKey("L1", { key: k, editable: true })).toBe(false);
    await flush();
    expect(calls).toHaveLength(0);
    expect(ctl.getState().editingId).toBeNull();
    expect(ctl.getState().confirmingId).toBeNull();
    ctl.openEdit("L1"); // form terbuka: pintasan tidak aktif sampai ditutup
    expect(ctl.onKey("L1", { key: "r" })).toBe(false);
    ctl.closeEdit();
    expect(ctl.onKey("L1", { key: "r" })).toBe(true); // fokus kembali ke kartu
    expect(ctl.onKey("L1", { key: "r", ctrlKey: true })).toBe(false);
  });

  it("9: form Edit pada DX mengirim code point dan catatan operator", async () => {
    const { ctl, calls } = await ready();
    ctl.openEdit("L1");
    ctl.addSelection(28, 44);
    ctl.setNote("L1", "catatan");
    expect(await ctl.submitEdit()).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0].body).toEqual({
      decision: "diubah", edited: { query: "QL1", gold_spans: [{ start: 27, end: 43 }], mode: "literal" }, operator_note: "catatan",
    });
  });

  it("10: E pada kartu membuka form Edit tanpa permintaan", async () => {
    const { ctl, calls } = await ready();
    ctl.onKey("L1", { key: "e" });
    expect(ctl.getState().editingId).toBe("L1");
    await flush();
    expect(calls).toHaveLength(0);
  });

  it("memuat antrean dan teks dokumen; konteks memakai context_lines server", async () => {
    const { ctl } = await ready();
    const s = ctl.getState();
    expect(s.load).toBe("ready");
    expect(s.contextLines).toBe(1);
    expect(s.proposals).toHaveLength(3);
    expect(ctl.contextFor(L1)?.text).toBe(slice(10, 51));
    expect(ctl.contextFor(L2)).toBeNull();
  });
});

describe("S24 seleksi UTF-16 ke code point", () => {
  it.each([
    ["a", 28, 44, [27, 43]], ["b", 0, 2, [0, 1]], ["c", 0, 1, [0, 1]], ["d", 1, 2, [0, 1]], ["e", 0, 87, [0, 86]], ["f", 70, 86, [69, 85]],
  ])("%s: [%i, %i)", (_n, s, e, exp) => {
    expect(DX.length).toBe(87);
    expect(cp(DX)).toHaveLength(86);
    expect(utf16ToCodePointRange(DX, s as number, e as number)).toEqual(exp);
  });
});

describe("S25 konteks kartu (k = 1)", () => {
  it.each([
    ["a", 27, 43, 10, 51, 17, 33], ["b", 0, 1, 0, 26, 0, 1], ["c", 69, 85, 52, 85, 17, 33], ["d", 10, 43, 0, 51, 10, 43],
  ])("%s", (_n, s, e, a, b, hs, he) => {
    const c = contextWindow(DX, s as number, e as number, 1);
    expect(c.text).toBe(slice(a as number, b as number));
    expect([c.hlStart, c.hlEnd]).toEqual([hs, he]);
    expect(cp(c.text).slice(c.hlStart, c.hlEnd).join("")).toBe(slice(s as number, e as number));
  });
});

describe("S22 label", () => {
  it("penghitung dan baris provenance", () => {
    expect(pendingLabel(3)).toBe("Review proposals (3 pending)");
    expect(provenanceLine(8, { operator: 4, spark_disetujui: 4 })).toBe("8 items: 4 operator-written, 4 Spark-proposed and operator-approved");
  });
});
