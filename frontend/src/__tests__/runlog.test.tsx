// U8 Run log & cost + panel header B (M3.1): agregat, filter, proyeksi, sampel; keadaan kosong/error.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HeaderBPanel, RunLogView } from "../components/RunLog";
import { aggregateByRole, filterRuns, poolRows, projectionRows, sampleRows, totalsToAggregates } from "../lib/runlog";
import type { HeaderBView, PoolSpend, RunTotal } from "../types";
import { mkRun } from "./fixtures";

const RUNS = [
  mkRun("r1", { kind: "spark_b", created_at: "2026-10-27T06:24:03Z", usage_input_tokens: 47604, usage_cached_tokens: 46907, usage_output_tokens: 427, cost_usd_micros: 249 }),
  mkRun("r2", { kind: "spark_b", created_at: "2026-10-27T06:25:03Z", usage_input_tokens: 100, usage_cached_tokens: 50, usage_output_tokens: 10, cost_usd_micros: 51 }),
  mkRun("r3", { kind: "spark_c", usage_input_tokens: 7, usage_cached_tokens: null, usage_output_tokens: null, cost_usd_micros: null }),
  mkRun("r4", { kind: "grid", model: null, effort: null, prompt_version: null, usage_input_tokens: null, usage_cached_tokens: null, usage_output_tokens: null, cost_usd_micros: null, latency_ms: 12 }),
];

const view = (role: "all" | "spark_b" = "all", selected: string | null = null, runs = RUNS) =>
  renderToStaticMarkup(<RunLogView runs={runs} role={role} onRole={() => undefined} selected={selected} onSelect={() => undefined} />);

describe("agregat dan filter", () => {
  it("jumlah per peran, integer micro-USD, null dihitung 0", () => {
    const a = aggregateByRole(RUNS);
    expect(a.map((x) => x.kind)).toEqual(["spark_b", "spark_c", "grid"]);
    expect(a[0]).toMatchObject({ runs: 2, inputTokens: 47704, cachedTokens: 46957, outputTokens: 437, costMicros: 300 });
    expect(a[1]).toMatchObject({ runs: 1, inputTokens: 7, cachedTokens: 0, costMicros: 0, unknownRuns: 1 });
    expect(a[0].unknownRuns).toBe(0);
  });
  it("baris agregat menandai run dengan nilai tak diketahui", () => {
    const h = view();
    expect(h).toContain("incl. 1 run with unknown values counted as 0");
  });
  it("filter per peran", () => {
    expect(filterRuns(RUNS, "spark_b").map((r) => r.run_id)).toEqual(["r1", "r2"]);
    expect(filterRuns(RUNS, "all")).toHaveLength(4);
  });
});

describe("RunLogView", () => {
  it("kolom dan label Inggris, biaya USD, token, latensi, peran", () => {
    const h = view();
    for (const t of ["Run log", "Role", "Prompt version", "Input tokens", "Cached tokens", "Output tokens", "Cost (USD)", "Latency", "Time (UTC)"]) {
      if (t !== "Run log") expect(h).toContain(t);
    }
    expect(h).toContain("$0.000249");
    expect(h).toContain("47604");
    expect(h).toContain("46907");
    expect(h).toContain("3642 ms");
    expect(h).toContain("2026-10-27 06:24:03Z");
    expect(h).toContain("$0.000300"); // agregat peran B
    expect(h).toContain("n/a");
  });
  it("filter peran menyaring baris", () => {
    const h = view("spark_b");
    expect(h).toContain("2026-10-27 06:25:03Z");
    expect(h).not.toContain("<td>Grid</td>");
  });
  it("klik baris menampilkan detail JSON catatan run", () => {
    const h = view("all", "r1");
    expect(h).toContain("Run record JSON");
    expect(h).toContain("&quot;run_id&quot;: &quot;r1&quot;");
  });
  it("empty", () => {
    expect(view("all", null, [])).toContain("No runs recorded");
  });
});

// UX-02 (putusan operator 12): agregat per peran dari server atas semua run; tabel baris = "Latest N runs".
const TOTALS: RunTotal[] = [
  { kind: "spark_b", runs: 5125, usage_input_tokens: 83148909, usage_cached_tokens: 81729292, usage_output_tokens: 1089622, spend_usd_micros: 526265, unknown_runs: 3202 },
  { kind: "spark_c", runs: 44, usage_input_tokens: 132682, usage_cached_tokens: 16056, usage_output_tokens: 20376, spend_usd_micros: 59231, unknown_runs: 4 },
  { kind: "grid", runs: 11, usage_input_tokens: 0, usage_cached_tokens: 0, usage_output_tokens: 0, spend_usd_micros: 0, unknown_runs: 11 },
];
const viewT = (role: "all" | "spark_b" = "all") =>
  renderToStaticMarkup(<RunLogView runs={RUNS} totals={TOTALS} role={role} onRole={() => undefined} selected={null} onSelect={() => undefined} />);

describe("agregat server (UX-02)", () => {
  it("baris per peran dari totals server, bukan dari baris terbaru; total = buku belanja", () => {
    const a = totalsToAggregates(TOTALS);
    expect(a.map((x) => x.kind)).toEqual(["spark_b", "spark_c", "grid"]);
    expect(a[0]).toMatchObject({ runs: 5125, cachedTokens: 81729292, costMicros: 526265, unknownRuns: 3202 });
    expect(totalsToAggregates(TOTALS, "spark_c").map((x) => x.kind)).toEqual(["spark_c"]);
    const h = viewT();
    expect(h).toContain("Per role (all 5180 stored runs; cost = budget ledger");
    expect(h).toContain("81729292");
    expect(h).toContain("$0.526265");
    expect(h).toContain("All roles (all pools)");
    expect(h).toContain("$0.585496"); // 526265 + 59231 + 0
    expect(h).toContain("Latest 4 runs (UTC)");
    expect(h).not.toContain("$0.000300"); // agregat klien atas 4 baris tidak dipakai
  });
  it("filter peran menyaring agregat server dan menyembunyikan total semua peran", () => {
    const h = viewT("spark_b");
    expect(h).toContain("$0.526265");
    expect(h).not.toContain("$0.059231");
    expect(h).not.toContain("All roles (all pools)");
  });
  it("tanpa totals server: agregat klien diberi label latest N runs only", () => {
    expect(view()).toContain("Per role (latest 4 runs only");
  });
});

const PROJ = (cost: number): HeaderBView["projection"] => ({
  created_at: "2026-10-27T06:21:52Z",
  projections: {
    pasal: { source: "pasal", units: 10, calls: 11, cost_usd_micros: { expected: cost, upper_cached: cost + 1, upper_no_cache: cost + 2 }, time: { estimated_seconds: 33 } },
    ayat: { source: "ayat", units: 20, calls: 21, cost_usd_micros: { expected: 5, upper_cached: 6, upper_no_cache: 7 }, time: { estimated_seconds: 66 } },
    fixed_size: { source: "fixed_size", units: 3, calls: 4, cost_usd_micros: { expected: 1, upper_cached: 2, upper_no_cache: 3 }, time: { estimated_seconds: 9 } },
    "pasal:sample": { source: "pasal", units: 1, calls: 1, cost_usd_micros: { expected: 99, upper_cached: 99, upper_no_cache: 99 }, time: { estimated_seconds: 1 } },
  },
});
const HB: HeaderBView = {
  projection: PROJ(76780),
  samples: [
    { chunk_id: "c1", granularity: "pasal", header: "Header pasal uji", tokens_local: 27, prompt_version: "v1", run_id: "r" },
    { chunk_id: "c2", granularity: "fixed_size", header: "Header fixed uji", tokens_local: 28, prompt_version: "v1", run_id: "r" },
    { chunk_id: "c3", granularity: "ayat", header: "Tanpa alamat", tokens_local: 30, prompt_version: "v1", run_id: "r" },
  ],
  stored_counts: { pasal: 344, ayat: 10, fixed_size: 10 },
};

describe("header B (M3.1)", () => {
  it("proyeksi per granularitas pasal/ayat/fixed_size, entri :sample dilewati", () => {
    const rows = projectionRows(HB);
    expect(rows.map((r) => r.source)).toEqual(["pasal", "ayat", "fixed_size"]);
    expect(rows[0]).toMatchObject({ units: 10, calls: 11, expected: "$0.076780", upperCached: "$0.076781", upperNoCache: "$0.076782", seconds: 33 });
  });
  it("sampel header: alamat dari peta R4, tanpa padanan = n/a, token, header", () => {
    const rows = sampleRows(HB, { c1: "UU 40/2007 › Pasal 1", c2: "UU 40/2007 › Pasal 2 › ayat (1)" });
    expect(rows.map((r) => r.address)).toEqual(["UU 40/2007 › Pasal 1", "UU 40/2007 › Pasal 2 › ayat (1)", null]);
    const h = renderToStaticMarkup(<HeaderBPanel header={HB} addresses={{ c1: "UU 40/2007 › Pasal 1" }} />);
    expect(h).toContain("Header pasal uji");
    expect(h).toContain("UU 40/2007 › Pasal 1");
    expect(h).toContain("Tokens (local tokenizer)");
    expect(h).toContain("Fixed-size");
    expect(h).toContain("Pasal: 344 stored");
    expect(h).toContain("$0.076780");
    expect(h).toContain("n/a");
  });
  it("tanpa data header B = empty", () => {
    expect(renderToStaticMarkup(<HeaderBPanel header={undefined} addresses={{}} />)).toContain("No header B projection or samples recorded");
    expect(renderToStaticMarkup(<HeaderBPanel header={{ projection: null, samples: [], stored_counts: {} }} addresses={{}} />)).toContain("No header B projection");
  });
});

// H-104 butir 3: belanja eksperimen per pool, terpisah dari angka header (pool default = hasil utama).
const POOLS: PoolSpend[] = [
  { pool: "default", spend_usd_micros: 561741 },
  { pool: "baseten", spend_usd_micros: 15513750 },
  { pool: "sweep", spend_usd_micros: 0 },
];

describe("belanja per pool (H-104)", () => {
  it("poolRows: urutan server, label per pool, pool default ditandai hasil utama; data rusak dilewati", () => {
    const r = poolRows(POOLS);
    expect(r.map((x) => x.pool)).toEqual(["default", "baseten", "sweep"]);
    expect(r[0]).toMatchObject({ label: "Main results (Contributor, default pool)", costMicros: 561741, main: true });
    expect(r[1]).toMatchObject({ label: "Spark Open comparators (Baseten pool)", main: false });
    expect(poolRows([{ pool: "other", spend_usd_micros: 5 }])[0].label).toBe("other pool");
    expect(poolRows([{ pool: "x", spend_usd_micros: 1.5 }])).toEqual([]);
    expect(poolRows(null)).toEqual([]);
  });
  it("RunLogView menampilkan tabel pool bila ada, tidak tampil tanpa data pool", () => {
    const h = renderToStaticMarkup(<RunLogView runs={RUNS} totals={TOTALS} pools={POOLS} role="all" onRole={() => undefined} selected={null} onSelect={() => undefined} />);
    expect(h).toContain("Spend by budget pool");
    expect(h).toContain("$0.561741");
    expect(h).toContain("$15.513750");
    expect(viewT()).not.toContain("Spend by budget pool");
  });
});
