// Seksi "Roles and models" di panel About (UI-SPEC §9.2/§9.3, hints 1.6.0). Render server; tanpa DOM, tanpa jaringan.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import aboutSrc from "../components/AboutPanel.tsx?raw";
import { RolesSection } from "../components/AboutPanel";
import { GLOSSARY_PREFIXES, HINT_FILE, INTRO_IDS, ROLES_IDS, getHint, rolesEntries } from "../lib/hints";

const html = renderToStaticMarkup(<RolesSection idPrefix="t" />);

describe("seksi Roles and models", () => {
  it("(a) judul dari hints dan caption Roles and models", () => {
    for (const e of rolesEntries()) expect(html).toContain(`>${e.title.replace("&", "&amp;")}</h3>`);
    expect(html).toContain("<caption>Roles and models</caption>");
    expect(rolesEntries().length).toBe(ROLES_IDS.length);
  });
  it("(b) tabel 4 peran x 3 model; D pembanding '—', A/B/C pembanding 'Comparator'", () => {
    const t = getHint("roles.table")!.table!;
    expect(t.columns).toHaveLength(4);
    expect(t.rows).toHaveLength(4);
    expect(html).toContain('<th scope="col">Role</th>');
    for (const r of t.rows) {
      expect(r).toHaveLength(4);
      expect(html).toContain(`<th scope="row">${r[0]}</th>`);
      expect(r[1]).toBe("Main runs");
    }
    for (const r of t.rows.slice(0, 3)) expect(r.slice(2)).toEqual(["Comparator", "Comparator"]);
    expect(t.rows[3][0].startsWith("D.")).toBe(true);
    expect(t.rows[3].slice(2).every((c) => c.includes("—"))).toBe(true);
  });
  it("(c) model.* konsisten dengan H-100", () => {
    for (const e of HINT_FILE.entries.filter((x) => x.id.startsWith("model."))) {
      expect(e.body).not.toContain("role C only");
      expect(e.body).not.toContain("always use Contributor");
    }
    expect(getHint("model.glimmer_local")!.body).toContain("roles A, B, and C");
    expect(getHint("model.spark_open_baseten")!.body).toContain("roles A, B, and C");
  });
  it("(d) role.d memuat mode unanswerable", () => {
    expect(getHint("role.d")!.body).toContain("unanswerable");
  });
  it("(e) tidak ada entri yatim; semua ROLES_IDS ada", () => {
    for (const id of ROLES_IDS) expect(getHint(id), id).toBeDefined();
    const known = (id: string) =>
      (INTRO_IDS as readonly string[]).includes(id) || (ROLES_IDS as readonly string[]).includes(id) ||
      (GLOSSARY_PREFIXES as readonly string[]).includes(id.slice(0, id.indexOf(".")));
    expect(HINT_FILE.entries.filter((e) => !known(e.id)).map((e) => e.id)).toEqual([]);
  });
  it("(f) entri roles.* tanpa digit kecuali muse-spark-1.3", () => {
    for (const e of rolesEntries()) {
      const texts = [e.title, e.body, ...(e.items ?? []).flatMap((i) => [i.title, i.body]), ...(e.table ? [...e.table.columns, ...e.table.rows.flat()] : [])];
      for (const s of texts) expect(s.replaceAll("muse-spark-1.3", ""), e.id).not.toMatch(/\d/);
    }
  });
  it("(g) AboutPanel memakai seksi dan tidak memuat literal 'Main runs'", () => {
    expect(aboutSrc).toContain("<RolesSection");
    expect(aboutSrc).not.toContain("Main runs");
  });
});