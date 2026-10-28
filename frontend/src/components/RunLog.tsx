import { useEffect, useState } from "react";
import { fetchDoc, fetchHealth, fetchRuns } from "../api";
import { useStore } from "../state";
import { formatUsd, tokenStr } from "../lib/evidence";
import { truncate } from "../lib/format";
import {
  ROLES, aggregateByRole, filterRuns, granularityLabel, latencyStr, projectionRows, roleLabel, sampleRows, totalsToAggregates, utcStamp,
  type RoleFilter,
} from "../lib/runlog";
import type { HeaderBView, Load, RunRecord, RunTotal } from "../types";
import { Hint } from "./Hint";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "./Shell";

// U8 Run log & cost (docs/UI-SPEC.md U8). `RunLogView` dan `HeaderBPanel` murni; `RunLogPanel` menyambung R6 + snapshot.

export const RUNLOG_PAGE = 20; // UX-14: baris awal tabel U8; "Show more" menambah per halaman

export function RunLogView({ runs, role, onRole, selected, onSelect, totals = null, shown = RUNLOG_PAGE, onMore }: {
  runs: RunRecord[];
  /** R1 `run_totals_by_kind` (semua run, server). null = tidak tersedia: agregat dihitung dari baris terbaru saja dan diberi label. */
  totals?: RunTotal[] | null;
  shown?: number;
  onMore?: () => void;
  role: RoleFilter;
  onRole: (r: RoleFilter) => void;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  if (runs.length === 0) return <EmptyBlock>No runs recorded</EmptyBlock>;
  const rows = filterRuns(runs, role);
  // UX-02 (putusan operator 12): agregat per peran atas semua run dari server; biaya = buku belanja (Ledger.spent per peran).
  const agg = totals ? totalsToAggregates(totals, role) : aggregateByRole(rows);
  const nAll = totals ? totals.reduce((n, t) => n + t.runs, 0) : null;
  const aggCap = totals
    ? `Per role (all ${nAll} stored runs; cost = budget ledger: model usage, plus projected cost of failed attempts)`
    : `Per role (latest ${runs.length} runs only; cost from model usage)`;
  const aggTotal = totals && role === "all" ? agg.reduce((n, a) => n + a.costMicros, 0) : null;
  const detail = rows.find((r) => r.run_id === selected) ?? null;
  return (
    <>
      <div className="controls">
        <label className="field">
          <span>Role</span>
          <select value={role} onChange={(e) => onRole(e.target.value as RoleFilter)}>
            <option value="all">All roles</option>
            {ROLES.map((k) => <option key={k} value={k}>{roleLabel(k)}</option>)}
          </select>
        </label>
      </div>
      <div className="table-wrap">
        <table className="data runlog-agg">
          <caption className="cap">{aggCap}</caption>
          <thead>
            <tr><th scope="col">Role</th><th scope="col">Runs</th><th scope="col">Input tokens</th><th scope="col">Cached tokens</th><th scope="col">Output tokens</th><th scope="col">Cost (USD)</th></tr>
          </thead>
          <tbody>
            {agg.map((a) => (
              <tr key={a.kind}>
                <td>{roleLabel(a.kind)}</td><td>{a.runs}</td><td>{a.inputTokens}</td><td>{a.cachedTokens}</td><td>{a.outputTokens}</td><td>{formatUsd(a.costMicros)}{a.unknownRuns > 0 && <span className="muted"> (incl. {a.unknownRuns} {a.unknownRuns === 1 ? "run" : "runs"} with unknown values counted as 0)</span>}</td>
              </tr>
            ))}
          </tbody>
          {aggTotal !== null && (
            <tfoot>
              <tr><th scope="row">All roles (run cost)</th><td>{nAll}</td><td></td><td></td><td></td><td>{formatUsd(aggTotal)}</td></tr>
            </tfoot>
          )}
        </table>
      </div>
      <div className="table-wrap">
        <table className="data runlog">
          <caption className="cap">{`Latest ${runs.length} runs (UTC)`}</caption>
          <thead>
            <tr>
              <th scope="col">Time (UTC)</th><th scope="col">Role</th><th scope="col">Model</th><th scope="col">Effort</th><th scope="col">Prompt version</th>
              <th scope="col">Input tokens</th><th scope="col">Cached tokens</th><th scope="col">Output tokens</th><th scope="col">Cost (USD)</th><th scope="col">Latency</th><th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, Math.max(shown, rows.findIndex((r) => r.run_id === selected) + 1)).map((r) => (
              <tr key={r.run_id} className={r.run_id === selected ? "sel" : undefined}>
                <td><button type="button" className="addr" onClick={() => onSelect(r.run_id === selected ? null : r.run_id)} aria-expanded={r.run_id === selected}>{utcStamp(r.created_at)}</button></td>
                <td>{roleLabel(r.kind)}</td>
                <td>{r.model ?? "n/a"}</td>
                <td>{r.effort ?? "n/a"}</td>
                <td>{r.prompt_version ?? "n/a"}</td>
                <td>{tokenStr(r.usage_input_tokens)}</td>
                <td>{tokenStr(r.usage_cached_tokens)}</td>
                <td>{tokenStr(r.usage_output_tokens)}</td>
                <td>{formatUsd(r.cost_usd_micros)}</td>
                <td>{latencyStr(r.latency_ms)}</td>
                <td>{r.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > shown && (
        <div className="card-actions">
          <span className="note">{`Showing ${Math.min(shown, rows.length)} of ${rows.length} runs.`}</span>
          {onMore && <button type="button" onClick={onMore}>Show more</button>}
        </div>
      )}
      {detail && <pre className="ctx mono" aria-label="Run record JSON">{JSON.stringify(detail, null, 2)}</pre>}
    </>
  );
}

export function HeaderBPanel({ header, addresses }: { header: HeaderBView | undefined; addresses: Record<string, string> }) {
  const proj = projectionRows(header);
  const samples = sampleRows(header, addresses);
  if (!header || (proj.length === 0 && samples.length === 0)) return <EmptyBlock>No header B projection or samples recorded</EmptyBlock>;
  return (
    <section aria-label="Header B">
      <h3 className="detail-title">Header B: projection and samples</h3>
      {proj.length > 0 && (
        <div className="table-wrap">
          <table className="data header-proj">
            <caption className="cap">Projected cost per granularity (full corpus, from the stored projection)</caption>
            <thead>
              <tr><th scope="col">Granularity</th><th scope="col">Units</th><th scope="col">Calls</th><th scope="col">Expected (USD)</th><th scope="col">Upper, cached (USD)</th><th scope="col">Upper, no cache (USD)</th><th scope="col">Est. time (s)</th></tr>
            </thead>
            <tbody>
              {proj.map((p) => (
                <tr key={p.source}><td>{granularityLabel(p.source)}</td><td>{p.units}</td><td>{p.calls}</td><td>{p.expected}</td><td>{p.upperCached}</td><td>{p.upperNoCache}</td><td>{p.seconds}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {samples.length > 0 && (
        <div className="table-wrap">
          <table className="data header-samples">
            <caption className="cap">Stored header samples ({Object.entries(header.stored_counts).map(([g, n]) => `${granularityLabel(g)}: ${n} stored`).join(", ")})</caption>
            <thead><tr><th scope="col">Granularity</th><th scope="col">Address</th><th scope="col">Header</th><th scope="col">Tokens (local tokenizer)</th></tr></thead>
            <tbody>
              {samples.map((s) => (
                <tr key={`${s.granularity}-${s.chunk_id}`}>
                  <td>{granularityLabel(s.granularity)}</td>
                  <td className="mono" lang="id">{s.address ?? "n/a"}</td>
                  <td lang="id">{truncate(s.header, 240)}</td>
                  <td>{s.tokens_local}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function RunLogPanel() {
  const { state } = useStore();
  const snap = state.snapshot.status === "ready" ? state.snapshot.data : null;
  const [runs, setRuns] = useState<Load<RunRecord[]>>({ status: "loading" });
  const [totals, setTotals] = useState<RunTotal[] | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [role, setRole] = useState<RoleFilter>("all");
  const [shown, setShown] = useState(RUNLOG_PAGE);
  const [selected, setSelected] = useState<string | null>(null);
  const [addresses, setAddresses] = useState<Record<string, string>>({});

  const hash = snap?.config_hash ?? null;
  useEffect(() => {
    let live = true;
    fetchRuns()
      .then((data) => live && setRuns({ status: "ready", data }))
      .catch((e: unknown) => live && setRuns({ status: "error", code: "runs", message: e instanceof Error ? e.message : "Unexpected error." }));
    fetchHealth()
      .then((h) => live && setTotals(Array.isArray(h.run_totals_by_kind) ? h.run_totals_by_kind : null))
      .catch(() => live && setTotals(null));
    return () => {
      live = false;
    };
  }, [hash, attempt]);

  // Alamat sampel header: potongan dari R4 untuk setting struktur tulisan tangan dan ukuran tetap (tanpa header).
  const nSamples = snap?.header_b?.samples.length ?? 0;
  const docId = snap?.corpus[0]?.doc_id;
  const family = snap?.family;
  const structId = snap?.settings.find((s) => s.chunker === "structure_handwritten" && !s.header_b)?.setting_id;
  const fixedId = snap?.settings.find((s) => s.chunker === "fixed_size" && !s.header_b)?.setting_id;
  useEffect(() => {
    if (!family || !docId || nSamples === 0) return;
    let live = true;
    const ids = [structId, fixedId].filter((x): x is string => !!x);
    Promise.all(ids.map((id) => fetchDoc(family, docId, id).catch(() => null))).then((docs) => {
      if (!live) return;
      const m: Record<string, string> = {};
      for (const d of docs) for (const c of d?.chunks ?? []) m[c.chunk_id] = c.address;
      setAddresses(m);
    });
    return () => {
      live = false;
    };
  }, [family, docId, nSamples, structId, fixedId]);

  let body;
  if (runs.status === "loading" || runs.status === "idle") body = <LoadingBlock text="Loading run log…" />;
  else if (runs.status === "error") body = (
      <>
        <ErrorBlock title={`Run log unreadable: ${runs.message}`} />
        <button type="button" onClick={() => { setRuns({ status: "loading" }); setAttempt((n) => n + 1); }}>Retry</button>
      </>
    );
  else body = <RunLogView runs={runs.data} totals={totals} role={role} onRole={(r) => { setRole(r); setShown(RUNLOG_PAGE); }} selected={selected} onSelect={setSelected} shown={shown} onMore={() => setShown((n) => n + 100)} />;
  return (
    <section className="panel" aria-labelledby="runlog-title" id="runlog">
      <div className="panel-head"><h2 id="runlog-title">Run log &amp; cost</h2><Hint id="role.a" /><Hint id="role.b" /><Hint id="role.c" /><Hint id="role.d" /><Hint id="header_b.what" /><Hint id="metric.local_tokenizer" /></div>
      {body}
      {snap ? <HeaderBPanel header={snap.header_b} addresses={addresses} /> : null}
    </section>
  );
}
