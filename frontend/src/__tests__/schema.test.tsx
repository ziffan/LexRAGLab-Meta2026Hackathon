// U5 Structure schema (M3.3): diff antar versi, keluaran ditolak, editor koreksi yang mengirim W9 dengan isi form.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SchemaEditor, SchemaView } from "../components/SchemaPanel";
import {
  diffBodies, editorFrom, editorReducer, noErrors, parseSchemaErrors, submitCorrection, toBody, versionLabel,
  type EditorAction, type EditorState,
} from "../lib/schemaEdit";
import { mkSchema } from "./fixtures";

const v1 = mkSchema(1, "spark");

function rig(status: number, body: unknown) {
  const calls: { url: string; method: string; body: any }[] = [];
  const fetchFn = async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: JSON.parse(String(init?.body ?? "null")) });
    return new Response(JSON.stringify(body), { status });
  };
  return { calls, fetchFn };
}

/** Terapkan aksi ke state seperti useReducer. */
function session(parent = v1) {
  let s: EditorState = editorFrom(parent);
  const dispatch = (a: EditorAction) => {
    s = editorReducer(s, a);
  };
  return { get: () => s, dispatch };
}

describe("diff", () => {
  it("level diubah, ditambah, dihapus, dan bidang tingkat atas", () => {
    const b = structuredClone(v1.body);
    b.levels[1].marker_pattern = "^Pasal";
    b.levels.push({ order: 3, name: "ayat", marker_pattern: "^\\(\\d+\\)", examples: ["(1) x"], parent_order: 2, is_chunk_unit: false });
    b.levels.shift();
    b.notes = "n";
    const d = diffBodies(v1.body, b);
    expect(d.map((e) => [e.order, e.field])).toEqual([[1, "level"], [2, "marker_pattern"], [3, "level"], [null, "notes"]]);
    expect(d[0]).toMatchObject({ before: v1.body.levels[0], after: null });
    expect(d[2]).toMatchObject({ before: null });
  });
  it("tanpa selisih = kosong", () => {
    expect(diffBodies(v1.body, structuredClone(v1.body))).toEqual([]);
  });
  it("label versi: Spark vs koreksi operator", () => {
    expect(versionLabel(v1)).toBe("v1 · proposed by Muse Spark");
    expect(versionLabel(mkSchema(2, "operator"))).toBe("v2 · operator correction");
  });
});

describe("SchemaView", () => {
  const v2b = structuredClone(v1.body);
  v2b.levels[1].marker_pattern = "^Pasal";
  const v2 = { ...mkSchema(2, "operator", v2b, "catatan operator"), body: v2b };
  const rejected = [{ run_id: "rej-1", family: "uupt", body: {}, errors: ["level[0] order 1: marker_pattern is empty"], created_at: "2026-10-27T06:00:00Z" }];

  it("v1 Spark berdampingan dengan versi koreksi, baris berubah ditandai, tabel Changed lines", () => {
    const h = renderToStaticMarkup(<SchemaView schemas={[v1, v2]} rejected={[]} diff={null} fromVersion={1} toVersion={2} onFrom={() => undefined} onTo={() => undefined} />);
    expect(h).toContain("v1 · proposed by Muse Spark");
    expect(h).toContain("v2 · operator correction");
    expect(h).toContain("note: catatan operator");
    expect(h).toContain("Changed lines");
    expect(h).toContain("diff-changed");
    expect(h).toContain("Marker pattern");
    expect(h).toContain("Default chunk unit");
    expect(h).toContain("Boundary differences vs handwritten parser");
  });
  it("keluaran Spark ditolak tampil sebagai Rejected output, bukan versi", () => {
    const h = renderToStaticMarkup(<SchemaView schemas={[v1]} rejected={rejected} diff={null} fromVersion={1} toVersion={1} onFrom={() => undefined} onTo={() => undefined} />);
    expect(h).toContain("Rejected output");
    expect(h).toContain("rej-1");
    expect(h).toContain("marker_pattern is empty");
    expect((h.match(/<option/g) ?? []).length).toBe(2); // satu versi di dua pemilih
  });
  it("hanya keluaran ditolak: tidak kosong, tanpa pemilih versi", () => {
    const h = renderToStaticMarkup(<SchemaView schemas={[]} rejected={rejected} diff={null} fromVersion={null} toVersion={null} onFrom={() => undefined} onTo={() => undefined} />);
    expect(h).toContain("Rejected output");
    expect(h).not.toContain("Compare version");
  });
  it("empty", () => {
    const h = renderToStaticMarkup(<SchemaView schemas={[]} rejected={[]} diff={null} fromVersion={null} toVersion={null} onFrom={() => undefined} onTo={() => undefined} />);
    expect(h).toContain("No schema induced for this family yet");
  });
});

describe("editor U5 (H-037)", () => {
  it("mulai dari salinan versi induk, tanpa nilai karangan", () => {
    const s = editorFrom(v1);
    expect(s.parentVersion).toBe(1);
    expect(s.levels.map((l) => l.marker_pattern)).toEqual(["^BAB", "^Pasal\\s+\\d+"]);
    expect(s.levels[1].examples).toBe("Pasal 1\nPasal 2");
    expect(s.operatorNote).toBe("");
    expect(toBody(s).body).toEqual(v1.body);
  });
  it("level baru kosong, bukan default karangan", () => {
    const x = session();
    x.dispatch({ type: "add_level" });
    expect(x.get().levels[2]).toEqual({ order: "", name: "", marker_pattern: "", examples: "", parent_order: "", is_chunk_unit: false });
    expect(toBody(x.get()).body).toBeNull();
    expect(toBody(x.get()).errors.levels[2].order).toEqual(["order must be an integer"]);
  });
  it("Save mengirim W9 dengan isi FORM (bukan default) ke versi induk", async () => {
    const x = session();
    x.dispatch({ type: "level", index: 1, patch: { marker_pattern: "^Pasal EDITAN", examples: "Pasal 1\nPasal 3", name: "pasal-x" } });
    x.dispatch({ type: "level", index: 0, patch: { is_chunk_unit: true, parent_order: "" } });
    x.dispatch({ type: "add_level" });
    x.dispatch({ type: "level", index: 2, patch: { order: "3", name: "ayat", marker_pattern: "^\\(\\d+\\)", examples: "(1) a", parent_order: "2" } });
    x.dispatch({ type: "top", patch: { operatorNote: "catatan saya", defaultChunkLevel: "1", notes: "n-baru" } });
    const r = rig(200, { ...mkSchema(2, "operator"), schema_version: 2 });
    const res = await submitCorrection(x.get(), x.dispatch, r.fetchFn);
    expect(res.ok).toBe(true);
    expect(r.calls).toHaveLength(1);
    expect(r.calls[0].url).toBe("/api/families/uupt/schemas/1/correct");
    expect(r.calls[0].method).toBe("POST");
    const b = r.calls[0].body;
    expect(Object.keys(b).sort()).toEqual(["operator_note", "schema"]);
    expect(b.operator_note).toBe("catatan saya");
    expect(b.schema.default_chunk_level).toBe(1);
    expect(b.schema.notes).toBe("n-baru");
    expect(b.schema.levels[1]).toEqual({ order: 2, name: "pasal-x", marker_pattern: "^Pasal EDITAN", examples: ["Pasal 1", "Pasal 3"], parent_order: 1, is_chunk_unit: true });
    expect(b.schema.levels[2]).toEqual({ order: 3, name: "ayat", marker_pattern: "^\\(\\d+\\)", examples: ["(1) a"], parent_order: 2, is_chunk_unit: false });
    expect(b.schema.levels[0].is_chunk_unit).toBe(true);
    expect(x.get().savedVersion).toBe(2);
  });
  it("versi induk selain 1 dipakai di URL W9", async () => {
    const x = session(mkSchema(3, "operator"));
    const r = rig(200, mkSchema(4, "operator"));
    await submitCorrection(x.get(), x.dispatch, r.fetchFn);
    expect(r.calls[0].url).toBe("/api/families/uupt/schemas/3/correct");
  });
  it("catatan operator kosong dikirim null", async () => {
    const x = session();
    const r = rig(200, mkSchema(2, "operator"));
    await submitCorrection(x.get(), x.dispatch, r.fetchFn);
    expect(r.calls[0].body.operator_note).toBeNull();
  });
  it("hapus level dikirim apa adanya", async () => {
    const x = session();
    x.dispatch({ type: "remove_level", index: 0 });
    const r = rig(200, mkSchema(2, "operator"));
    await submitCorrection(x.get(), x.dispatch, r.fetchFn);
    expect(r.calls[0].body.schema.levels).toHaveLength(1);
    expect(r.calls[0].body.schema.levels[0].name).toBe("pasal");
  });
  it("bilangan tidak sah ditolak lokal per field, tanpa request", async () => {
    const x = session();
    x.dispatch({ type: "level", index: 0, patch: { order: "abc" } });
    const r = rig(200, {});
    const res = await submitCorrection(x.get(), x.dispatch, r.fetchFn);
    expect(res.ok).toBe(false);
    expect(r.calls).toHaveLength(0);
    expect(x.get().errors.levels[0].order).toEqual(["order must be an integer"]);
  });
  it("422 schema_invalid tampil per field", async () => {
    const msg = "level[1] order 2: marker_pattern does not match its own example 'Pasal 1'; level[0] order 1: examples is empty; default_chunk_level 9 is not an existing order; family differs from the requested family";
    const x = session();
    const r = rig(422, { error: { code: "schema_invalid", message: msg } });
    const res = await submitCorrection(x.get(), x.dispatch, r.fetchFn);
    expect(res.ok).toBe(false);
    const e = x.get().errors;
    expect(e.levels[1].marker_pattern).toHaveLength(1);
    expect(e.levels[0].examples).toEqual(["examples is empty"]);
    expect(e.top.default_chunk_level).toHaveLength(1);
    expect(e.general).toEqual(["family differs from the requested family"]);
    expect(x.get().busy).toBe(false);
    const h = renderToStaticMarkup(<SchemaEditor state={x.get()} dispatch={() => undefined} readOnlyReason={null} onSave={() => undefined} />);
    expect(h).toContain("marker_pattern does not match its own example");
    expect(h).toContain("examples is empty");
    expect(h).toContain("default_chunk_level 9 is not an existing order");
  });
  it("galat lain (replay, hash) masuk pesan umum", async () => {
    const x = session();
    const r = rig(400, { error: { code: "invalid_request", message: "Replay mode is read-only" } });
    await submitCorrection(x.get(), x.dispatch, r.fetchFn);
    expect(x.get().errors.general[0]).toContain("Replay mode is read-only");
  });
  it("editor: label Inggris, Save as new version, nonaktif di replay", () => {
    const s = editorFrom(v1);
    const h = renderToStaticMarkup(<SchemaEditor state={s} dispatch={() => undefined} readOnlyReason="Replay mode is read-only; schema corrections are not available." onSave={() => undefined} />);
    for (const t of ["Order", "Level", "Marker pattern", "Example (one per line)", "Parent order", "Chunk unit", "Default chunk unit", "Operator note", "Save as new version", "Add level"]) expect(h).toContain(t);
    expect(h).toMatch(/<button[^>]*disabled[^>]*>Save as new version/);
    expect(h).toContain("^Pasal\\s+\\d+");
  });
  it("parseSchemaErrors: pesan tak dikenal jadi umum", () => {
    expect(parseSchemaErrors("something odd").general).toEqual(["something odd"]);
    expect(noErrors().general).toEqual([]);
  });
});
