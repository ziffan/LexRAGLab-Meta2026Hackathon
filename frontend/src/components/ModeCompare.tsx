import { useStore } from "../state";
import { exactStr, mean2, xOfY } from "../lib/format";
import { chunkerLabel, retrievalModeLabel } from "../lib/labels";
import { toRow } from "../lib/rows";
import { gridKey, isTransferGrid, pointOf, siblingModes } from "../lib/settings";
import type { ItemMetrics, Setting, Snapshot } from "../types";
import { EmptyBlock } from "./Shell";

// M1.3: dense / BM25 / hybrid berdampingan untuk chunker yang sama.

export function ModeCompare({ snap, setting, metricsFor }: { snap: Snapshot; setting: Setting; metricsFor: (settingId: string) => Map<string, ItemMetrics> }) {
  const { state } = useStore();
  const modes = siblingModes(snap, setting);
  const item = snap.items.find((i) => i.id === state.selectedItemId);
  const split = state.split;
  const key = gridKey(snap, split);

  return (
    <>
      <h3 className="detail-title">Retrieval modes, same chunker</h3>
      <p className="note">
        {chunkerLabel(setting)}. Dense, BM25 and hybrid use the same chunks and the same token budget.
      </p>
      {item ? (
        <div className="table-wrap">
          <table className="data" aria-label={`Three retrieval modes for item ${item.id}`}>
            <caption className="cap">
              Item <span className="mono">{item.id}</span>
            </caption>
            <thead>
              <tr>
                <th scope="col">Mode</th>
                <th scope="col">Span recall</th>
                <th scope="col">Token precision</th>
                <th scope="col">Reciprocal rank</th>
                <th scope="col">Recall@K</th>
                <th scope="col">Fully covered</th>
                <th scope="col">Retrieved tokens (local tokenizer)</th>
              </tr>
            </thead>
            <tbody>
              {modes.map((s) => {
                const m = metricsFor(s.setting_id).get(item.id);
                const r = m ? toRow(m) : null;
                return (
                  <tr key={s.setting_id} className={s.setting_id === setting.setting_id ? "sel" : ""}>
                    <th scope="row">{retrievalModeLabel(s.retrieval_mode)}</th>
                    <td>{r?.spanRecall ?? "n/a"}</td>
                    <td>{r?.tokenPrecision ?? "n/a"}</td>
                    <td>{r?.rank ?? "n/a"}</td>
                    <td>{r?.recallAtK ?? "n/a"}</td>
                    <td>{r?.fullyCovered ?? "n/a"}</td>
                    <td>{r?.retrievedTokens ?? "n/a"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyBlock>Select an item in the table above to compare the three modes</EmptyBlock>
      )}

      <div className="table-wrap">
        <table className="data" aria-label="Three retrieval modes, aggregate">
          <caption className="cap">{isTransferGrid(snap) ? "All items (transfer test)" : `All items in the ${split === "held_out" ? "held-out" : "tune"} split`}</caption>
          <thead>
            <tr>
              <th scope="col">Mode</th>
              <th scope="col">Items fully covered</th>
              <th scope="col">Span recall (mean)</th>
              <th scope="col">MRR</th>
            </tr>
          </thead>
          <tbody>
            {modes.map((s) => {
              const p = pointOf(snap, s.setting_id, key);
              return (
                <tr key={s.setting_id} className={s.setting_id === setting.setting_id ? "sel" : ""}>
                  <th scope="row">{retrievalModeLabel(s.retrieval_mode)}</th>
                  <td>{p ? xOfY(p.fully_covered_count.covered, p.fully_covered_count.total, "items") : "n/a"}</td>
                  <td title={p ? `exact ${exactStr(p.exact, "mean_span_recall")}` : undefined}>{p ? mean2(p.mean_span_recall) : "n/a"}</td>
                  <td title={p ? `exact ${exactStr(p.exact, "mrr")}` : undefined}>{p ? mean2(p.mrr) : "n/a"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
