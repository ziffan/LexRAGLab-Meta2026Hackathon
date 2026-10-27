// Kontrak bentuk `FamilySnapshot.report` (H-077): berkas yang sama diperiksa backend (test_r3_report_view.py).
import { describe, expect, it } from "vitest";
import type { Report } from "../types";
import fixture from "./report.fixture.json";

const REPORT_KEYS = ["by_mode", "by_origin", "family", "rows", "summary", "title"];
const ROW_KEYS = ["fully_covered", "item_id", "mode", "note", "origin", "recall_at_k", "reciprocal_rank", "span_recall", "split", "token_precision"];
const SUMMARY_KEYS = ["fully_covered", "mean_span_recall", "mean_token_precision", "n_items"];
const GROUP_KEYS = ["mean_span_recall", "mean_token_precision", "n_gold", "n_items"];
const COUNT_KEYS = ["denominator", "numerator", "text"];

const uupt: Report = fixture.uupt as Report;
const akta: Report = fixture.akta as Report;
const sorted = (o: object) => Object.keys(o).sort();

describe("bentuk Report = keluaran backend", () => {
  for (const [name, r] of [["uupt", uupt], ["akta", akta]] as const) {
    it(`${name}: kunci persis`, () => {
      expect(sorted(r)).toEqual(REPORT_KEYS);
      expect(sorted(r.summary)).toEqual(SUMMARY_KEYS);
      expect(sorted(r.summary.fully_covered)).toEqual(COUNT_KEYS);
      for (const row of r.rows) {
        expect(sorted(row)).toEqual(ROW_KEYS);
        for (const c of [row.span_recall, row.token_precision]) if (c) expect(sorted(c)).toEqual(COUNT_KEYS);
      }
      for (const g of [...Object.values(r.by_origin), ...Object.values(r.by_mode)]) expect(sorted(g)).toEqual(GROUP_KEYS);
    });
  }
  it("UU PT: judul Held-out results, baris held_out saja; akta: Transfer results tanpa kata held-out", () => {
    expect(uupt.title).toBe("Held-out results");
    expect(uupt.rows.every((r) => r.split === "held_out")).toBe(true);
    expect(akta.title).toBe("Transfer results");
    expect(JSON.stringify(akta)).not.toMatch(/held[- ]?out/i);
    expect(akta.rows.every((r) => r.split === "Transfer")).toBe(true);
  });
  it("hitungan mentah x of y dan nullability", () => {
    const r0 = akta.rows[0];
    expect(r0.span_recall!.text).toBe(`${r0.span_recall!.numerator} of ${r0.span_recall!.denominator}`);
    const none = akta.rows.find((r) => r.note !== null)!;
    expect(none.span_recall).toBeNull();
    expect(none.token_precision).toBeNull();
    expect(none.note).toBe("no gold (must abstain)");
  });
});
