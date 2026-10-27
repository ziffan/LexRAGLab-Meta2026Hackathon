import { Hint } from "./Hint";
import { scopeLabel, settingShort } from "../lib/labels";
import { xOfY, NA } from "../lib/format";
import { availableSettings, metricsFor, qualityOf, recallAtKCounts } from "../lib/settings";
import type { QualityWithCounts, Setting, Snapshot } from "../types";
import { EmptyBlock } from "./Shell";

// Panel metrik janji form (M1.5, US-04): Recall@K, entity preservation, boundary coherence.
// Hitungan mentah dari API; tidak ada persen atau selisih yang dikarang.

interface Col {
  title: string;
  setting: Setting;
  q: QualityWithCounts | undefined;
  recall: string;
}

function recallText(snap: Snapshot, s: Setting, q: QualityWithCounts | undefined): string {
  const scope = q?.items_scope;
  const c = recallAtKCounts(metricsFor(snap, s.setting_id).filter((m) => scope === undefined || scope === "all" || m.split === scope));
  if (c.withGold === 0) return NA;
  const base = xOfY(c.full, c.withGold, `items with all gold parts in top ${q?.k ?? "K"}`);
  return c.partial > 0 ? `${base} (+${c.partial} partial)` : base;
}

function column(snap: Snapshot, title: string, s: Setting): Col {
  const q = qualityOf(snap, s.setting_id);
  return { title, setting: s, q, recall: recallText(snap, s, q) };
}

export function QualityPanel({ snap, setting }: { snap: Snapshot; setting: Setting }) {
  const baselineId = snap.grid?.quality_comparison?.baseline_setting_id;
  const baseline = availableSettings(snap).find((s) => s.setting_id === baselineId);
  const cols: Col[] = [column(snap, "Selected setting", setting)];
  if (baseline && baseline.setting_id !== setting.setting_id) cols.push(column(snap, "Fixed-size baseline", baseline));

  return (
    <>
      <h3 className="detail-title">Quality promised in the form</h3>
      {!cols[0].q ? (
        <EmptyBlock>Quality metrics are not available for this setting</EmptyBlock>
      ) : (
        <div className="table-wrap">
          <table className="data" aria-label="Recall@K, entity preservation and boundary coherence">
            <thead>
              <tr>
                <th scope="col">Metric</th>
                {cols.map((c) => (
                  <th key={c.setting.setting_id} scope="col">
                    {c.title}
                    <div className="muted sub">{settingShort(c.setting)}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">
                  Recall@K (K = {cols[0].q.k})
                  <div className="muted sub">{scopeLabel(cols[0].q.items_scope)}</div>
                </th>
                {cols.map((c) => (
                  <td key={c.setting.setting_id}>{c.recall}</td>
                ))}
              </tr>
              <tr>
                <th scope="row">Entity preservation<Hint id="metric.entity_preservation" /></th>
                {cols.map((c) => (
                  <td key={c.setting.setting_id}>{c.q?.counts ? xOfY(c.q.counts.entity_num, c.q.counts.entity_den, "entities inside one chunk") : NA}</td>
                ))}
              </tr>
              <tr>
                <th scope="row">Boundary coherence<Hint id="metric.boundary_coherence" /></th>
                {cols.map((c) => (
                  <td key={c.setting.setting_id}>{c.q?.counts ? xOfY(c.q.counts.bnd_num, c.q.counts.bnd_den, "boundaries at structure or sentence end") : NA}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {cols.length === 1 && cols[0].q && <p className="note">The selected setting is the fixed-size baseline.</p>}
    </>
  );
}
