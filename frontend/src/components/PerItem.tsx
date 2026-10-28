import { useStore } from "../state";
import { truncate, xOfY } from "../lib/format";
import { Hint } from "./Hint";
import { modeLabel, originLabel, settingShort, splitLabel } from "../lib/labels";
import { filterScopeLabel } from "../lib/rows";
import { itemPasses, originSummary, toRow } from "../lib/rows";
import { availableSettings, headerTwin, metricsFor } from "../lib/settings";
import type { Item, ItemMetrics, Setting, Snapshot } from "../types";
import { ModeCompare } from "./ModeCompare";
import { QualityPanel } from "./QualityPanel";
import { EmptyBlock, SnapshotPanel } from "./Shell";

// U4 Per-item results (docs/UI-SPEC.md U4).

export function PerItem() {
  return (
    <SnapshotPanel pendingGate id="u4" title="Per-item results" loadingText="Loading per-item metrics…" errorTitle="Metrics unavailable">
      {(snap) => <Body snap={snap} />}
    </SnapshotPanel>
  );
}

function Body({ snap }: { snap: Snapshot }) {
  const { state, dispatch } = useStore();
  const sel = availableSettings(snap).find((s) => s.setting_id === state.selectedSettingId);
  if (snap.items.length === 0) return <EmptyBlock>No approved items for this family yet</EmptyBlock>;
  if (!sel || !snap.grid) return <EmptyBlock>No grid run for this family yet</EmptyBlock>;

  const transfer = snap.family === "akta"; // filter split disembunyikan untuk akta (H-078)
  const metrics = new Map<string, ItemMetrics>(metricsFor(snap, sel.setting_id).map((m) => [m.item_id, m]));
  const splitOf = (id: string) => metrics.get(id)?.split ?? snap.items.find((i) => i.id === id)?.split;
  const shown = snap.items.filter((i) => itemPasses(i, transfer ? { ...state.filters, split: "all" } : state.filters, splitOf));
  const withGold = shown.filter((i) => i.gold_spans.length > 0);
  const noGold = shown.filter((i) => i.gold_spans.length === 0);
  const summary = originSummary(shown, metrics);
  const f = state.filters;

  return (
    <>
      <p className="note">
        Setting: <strong>{settingShort(sel)}</strong>. Counts are raw, not percentages.
      </p>
      <div className="controls">
        <label className="field">
          <span>Origin<Hint id="role.d" /></span>
          <select value={f.origin} onChange={(e) => dispatch({ type: "set_filters", value: { origin: e.target.value as typeof f.origin } })}>
            <option value="all">All</option>
            <option value="operator">Operator-written</option>
            <option value="spark_disetujui">Spark-proposed, approved</option>
          </select>
        </label>
        <label className="field">
          <span>Mode</span>
          <select value={f.mode} onChange={(e) => dispatch({ type: "set_filters", value: { mode: e.target.value as typeof f.mode } })}>
            <option value="all">All</option>
            <option value="literal">Literal</option>
            <option value="parafrase">Paraphrase</option>
            <option value="tolak">{modeLabel("tolak")}</option>
          </select>
        </label>
        {!transfer && <label className="field">
          <span>Split<Hint id="metric.tune_heldout" /></span>
          <select value={f.split} onChange={(e) => dispatch({ type: "set_filters", value: { split: e.target.value as typeof f.split } })}>
            <option value="all">All</option>
            <option value="tune">Tune</option>
            <option value="held_out">Held-out</option>
          </select>
        </label>}
      </div>

      <p className="note">Summary scope: {filterScopeLabel(f.split, transfer)}.</p>
      <ul className="summary-row" aria-label="Results by origin">
        {summary.length === 0 && <li className="muted">No items match the filters.</li>}
        {summary.map((s) => (
          <li key={s.origin}>
            <strong>{originLabel(s.origin)}</strong>: {s.covered} of {s.total} items fully covered
            {s.noGold > 0 ? `; ${s.noGold} without gold reported below` : ""}
          </li>
        ))}
      </ul>

      {withGold.length === 0 ? (
        <EmptyBlock>No items with gold match the filters.</EmptyBlock>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <caption className="sr-only">Per-item results for the selected setting</caption>
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col">Query</th>
                <th scope="col">Origin</th>
                <th scope="col">Mode</th>
                <th scope="col">Split</th>
                <th scope="col">Span recall<Hint id="metric.span_recall" /></th>
                <th scope="col">Token precision<Hint id="metric.token_precision" /></th>
                <th scope="col">Reciprocal rank<Hint id="metric.mrr" /></th>
                <th scope="col">Recall@K<Hint id={transfer ? "metric.recall_at_k.akta" : "metric.recall_at_k"} /></th>
                <th scope="col">Fully covered</th>
                <th scope="col">Retrieved tokens (local tokenizer)</th>
              </tr>
            </thead>
            <tbody>
              {withGold.map((i) => (
                <ItemRow key={i.id} item={i} m={metrics.get(i.id)} split={splitOf(i.id)} selected={state.selectedItemId === i.id} onSelect={() => dispatch({ type: "select_item", id: i.id })} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {noGold.length > 0 && (
        <>
          <h3 className="detail-title">No gold (must abstain)<Hint id="term.gold_span" /></h3>
          <p className="note">Reported separately and excluded from the gold-based metrics above.</p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col">Query</th>
                  <th scope="col">Origin</th>
                  <th scope="col">Mode</th>
                  <th scope="col">Split</th>
                  <th scope="col">Retrieved tokens (local tokenizer)</th>
                  <th scope="col">Span recall</th>
                </tr>
              </thead>
              <tbody>
                {noGold.map((i) => (
                  <tr key={i.id} className={state.selectedItemId === i.id ? "sel" : ""}>
                    <th scope="row">
                      <button type="button" className="addr" onClick={() => dispatch({ type: "select_item", id: i.id })}>
                        {i.id}
                      </button>
                    </th>
                    <td lang="id">{truncate(i.query, 80)}</td>
                    <td>{originLabel(i.origin)}</td>
                    <td>{modeLabel(i.mode)}</td>
                    <td>{splitLabel(splitOf(i.id))}</td>
                    <td>{metrics.get(i.id)?.retrieved_tokens ?? "n/a"}</td>
                    <td>n/a</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!transfer && <HeaderCompare snap={snap} setting={sel} items={withGold} splitOf={splitOf} selectedItemId={state.selectedItemId} onSelect={(id) => dispatch({ type: "select_item", id })} />}
      <ModeCompare snap={snap} setting={sel} metricsFor={(id) => new Map(metricsFor(snap, id).map((m) => [m.item_id, m]))} />
      <QualityPanel snap={snap} setting={sel} />
    </>
  );
}

function ItemRow({ item, m, split, selected, onSelect }: { item: Item; m: ItemMetrics | undefined; split: string | null | undefined; selected: boolean; onSelect: () => void }) {
  const r = m ? toRow(m) : null;
  return (
    <tr className={selected ? "sel" : ""}>
      <th scope="row">
        <button type="button" className="addr" aria-pressed={selected} onClick={onSelect}>
          {item.id}
        </button>
      </th>
      <td lang="id">{truncate(item.query, 80)}</td>
      <td>{originLabel(item.origin)}</td>
      <td>{modeLabel(item.mode)}</td>
      <td>{splitLabel(split as "tune" | "held_out" | null | undefined)}</td>
      <td>{r?.spanRecall ?? "n/a"}</td>
      <td>{r?.tokenPrecision ?? "n/a"}</td>
      <td>{r?.rank ?? "n/a"}</td>
      <td>{r?.recallAtK ?? "n/a"}</td>
      <td>{r?.fullyCovered ?? "n/a"}</td>
      <td>{r?.retrievedTokens ?? "n/a"}</td>
    </tr>
  );
}

/** UX-04 (a): per butir (mengikuti filter Origin/Mode/Split di atas), setting terpilih dengan header B off vs on. Metrik dari snapshot. */
export function HeaderCompare({ snap, setting, items, splitOf, selectedItemId, onSelect }: {
  snap: Snapshot; setting: Setting; items: Item[]; splitOf: (id: string) => string | null | undefined; selectedItemId: string | null; onSelect: (id: string) => void;
}) {
  const twin = headerTwin(snap, setting);
  if (!twin || items.length === 0) return null;
  const off = setting.header_b ? twin : setting;
  const on = setting.header_b ? setting : twin;
  const mOff = new Map(metricsFor(snap, off.setting_id).map((m) => [m.item_id, m]));
  const mOn = new Map(metricsFor(snap, on.setting_id).map((m) => [m.item_id, m]));
  if (mOn.size === 0 || mOff.size === 0) return null;
  const count = (m: Map<string, ItemMetrics>) => {
    const g = items.map((i) => m.get(i.id)).filter((x): x is ItemMetrics => !!x && x.fully_covered !== null);
    return xOfY(g.filter((x) => x.fully_covered).length, g.length, "items fully covered");
  };
  const cell = (m: ItemMetrics | undefined) => (m ? toRow(m) : null);
  return (
    <section aria-label="Header B off vs on, per item" data-testid="header-compare">
      <h3 className="detail-title">Header B off vs on, per item<Hint id="header_b.what" /></h3>
      <p className="note">
        Same setting ({settingShort(off).replace(/ · header (on|off)$/, "")}), items matching the filters above. Header B off: {count(mOff)}. Header B on: {count(mOn)}.
      </p>
      <div className="table-wrap">
        <table className="data">
          <caption className="sr-only">Header B off and on for the same setting, per item</caption>
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col">Mode</th>
              <th scope="col">Split</th>
              <th scope="col">Span recall, header B off</th>
              <th scope="col">Span recall, header B on</th>
              <th scope="col">Fully covered, off</th>
              <th scope="col">Fully covered, on</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => {
              const a = cell(mOff.get(i.id));
              const b = cell(mOn.get(i.id));
              return (
                <tr key={i.id} className={selectedItemId === i.id ? "sel" : ""}>
                  <th scope="row"><button type="button" className="addr" onClick={() => onSelect(i.id)}>{i.id}</button></th>
                  <td>{modeLabel(i.mode)}</td>
                  <td>{splitLabel(splitOf(i.id) as "tune" | "held_out" | null | undefined)}</td>
                  <td>{a?.spanRecall ?? "n/a"}</td>
                  <td>{b?.spanRecall ?? "n/a"}</td>
                  <td>{a?.fullyCovered ?? "n/a"}</td>
                  <td>{b?.fullyCovered ?? "n/a"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

