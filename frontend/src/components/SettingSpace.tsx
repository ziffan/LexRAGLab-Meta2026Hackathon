import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { useStore } from "../state";
import { exactStr, fixed3, intStr, orNa, xOfY } from "../lib/format";
import { chunkerLabel, settingShort, splitLabel } from "../lib/labels";
import { seriesGroups } from "../lib/series";
import { availableSettings, frontierIds, pointOf } from "../lib/settings";
import type { GridPoint, Setting, Snapshot, SplitName } from "../types";
import { EmptyBlock, SnapshotPanel } from "./Shell";

// U2 Setting space (docs/UI-SPEC.md U2). Dua deret: header B off (biru) dan on (oranye, M3.2). Titik header-on yang gagal
// tidak digambar; alasannya tampil di daftar "Failed header-on settings".

const COLOR_OFF = "#1f4e8c";
const COLOR_ON = "#b4540a";
const colorOf = (on: boolean): string => (on ? COLOR_ON : COLOR_OFF);
const COLOR_LINE = "#46515e";

interface Dot {
  x: number;
  y: number;
  point: GridPoint;
  setting: Setting;
  onFrontier: boolean;
  headerOn: boolean;
}

/** Titik yang bisa digambar (x dan y non-null) dan yang tidak (butir bergold tidak ada di split ini, H-061). */
export function plottable(points: GridPoint[], settings: Setting[], frontier: Set<string>): { dots: Dot[]; hidden: number } {
  const bySetting = new Map(settings.map((s) => [s.setting_id, s]));
  const dots: Dot[] = [];
  let hidden = 0;
  for (const p of points) {
    const setting = bySetting.get(p.setting_id);
    if (!setting) continue;
    if (p.mean_retrieved_tokens === null || p.mean_span_recall === null) {
      hidden += 1;
      continue;
    }
    dots.push({ x: p.mean_retrieved_tokens, y: p.mean_span_recall, point: p, setting, onFrontier: frontier.has(p.setting_id), headerOn: p.header_b ?? setting.header_b });
  }
  return { dots, hidden };
}

const FAIL_TEXT: Record<string, string> = {
  header_missing: "header missing for a chunk",
  header_invalid: "header is empty",
  header_stale: "header comes from a different clean text",
  granularity_mismatch: "header granularity does not match",
};
/** Alasan gagal (kode dari RunRecord.failed_settings) dalam bahasa Inggris, dengan kode aslinya. */
export const failReason = (code: string): string => (FAIL_TEXT[code] ? `${FAIL_TEXT[code]} (${code})` : code);

export const frontierLine = (dots: Dot[]): Dot[] => dots.filter((d) => d.onFrontier).sort((a, b) => a.x - b.x || b.y - a.y);

function MarkerShape({ cx, cy, chunker, hollow, selected, on }: { cx: number; cy: number; chunker: Setting["chunker"]; hollow: boolean; selected: boolean; on: boolean }) {
  const color = colorOf(on);
  const fill = hollow ? "#ffffff" : color;
  const common = { fill, stroke: color, strokeWidth: 2 };
  const r = 7;
  return (
    <g>
      {selected && <circle cx={cx} cy={cy} r={r + 6} fill="none" stroke="#b3261e" strokeWidth={2.5} />}
      {chunker === "fixed_size" ? (
        <rect x={cx - r} y={cy - r} width={2 * r} height={2 * r} {...common} />
      ) : chunker === "structure_handwritten" ? (
        <circle cx={cx} cy={cy} r={r} {...common} />
      ) : (
        <polygon points={`${cx},${cy - r - 1} ${cx + r + 1},${cy + r} ${cx - r - 1},${cy + r}`} {...common} />
      )}
    </g>
  );
}

interface TipProps {
  active?: boolean;
  payload?: { payload: Dot }[];
}

function Tip({ active, payload }: TipProps) {
  const d = active ? payload?.[0]?.payload : undefined;
  if (!d || !("point" in d)) return null;
  const p = d.point;
  return (
    <div className="tip">
      <strong>{settingShort(d.setting)}</strong>
      <div>{chunkerLabel(d.setting)}</div>
      <div>Span recall (mean): {exactStr(p.exact, "mean_span_recall")} = {orNa(p.mean_span_recall, fixed3)}</div>
      <div>Token precision (mean): {orNa(p.mean_token_precision, (v) => v.toFixed(4))}</div>
      <div>MRR: {exactStr(p.exact, "mrr")}</div>
      <div>Tokens (local tokenizer), mean: {orNa(p.mean_retrieved_tokens, intStr)}</div>
      <div>{xOfY(p.fully_covered_count.covered, p.fully_covered_count.total, "items fully covered")}</div>
      <div>{d.headerOn ? "Header B on" : "Header B off"}</div>
      <div>{d.onFrontier ? "Frontier" : "Dominated"}</div>
    </div>
  );
}

export function SettingSpace() {
  return (
    <SnapshotPanel id="u2" title="Setting space" loadingText="Loading grid…" errorTitle="Grid run failed">
      {(snap) => <Body snap={snap} />}
    </SnapshotPanel>
  );
}

function Body({ snap }: { snap: Snapshot }) {
  const { state, dispatch } = useStore();
  const grid = snap.grid;
  if (!grid) return <EmptyBlock>No grid run for this family yet</EmptyBlock>;

  const split = state.split;
  const settings = availableSettings(snap);
  const budgets = [...new Set(snap.settings.map((s) => s.budget_tokens))].sort((a, b) => a - b);
  const frontier = frontierIds(snap, split);
  const { dots, hidden } = plottable(grid[split].points, settings, frontier);
  const line = frontierLine(dots);
  const selected = state.selectedSettingId;
  const pick = (id: string) => dispatch({ type: "select_setting", id });
  const sel = settings.find((s) => s.setting_id === selected);
  const chunkers: Setting["chunker"][] = ["structure_handwritten", "structure_schema", "fixed_size"];
  const onDots = dots.filter((d) => d.headerOn).length;
  const failed = grid.failed_settings ?? [];
  const byId = new Map(snap.settings.map((s) => [s.setting_id, s]));

  return (
    <>
      <div className="controls">
        <label className="field">
          <span>Token budget</span>
          <select value={snap.budget_tokens} onChange={(e) => dispatch({ type: "set_budget", value: Number(e.target.value) })}>
            {budgets.map((b) => (
              <option key={b} value={b}>
                {b} tokens (local tokenizer)
              </option>
            ))}
          </select>
        </label>
        <fieldset className="seg">
          <legend>Split</legend>
          {(["tune", "held_out"] as SplitName[]).map((sp) => (
            <label key={sp} className={`seg-item${split === sp ? " on" : ""}`}>
              <input type="radio" name="u2-split" checked={split === sp} onChange={() => dispatch({ type: "set_split", value: sp })} />
              {splitLabel(sp)}
            </label>
          ))}
        </fieldset>
      </div>
      <p className="note">
        {split === "held_out" ? (
          <span className="tag ok">held-out</span>
        ) : (
          <span className="tag neutral">tune</span>
        )}{" "}
        {split === "held_out" ? "Reported numbers come from the held-out split." : "Tune split: used to choose the setting, not reported as a result."}
      </p>

      {dots.length === 0 ? (
        <EmptyBlock>No plottable points in this split: every item here lacks gold.</EmptyBlock>
      ) : (
        <div className="chart" role="img" aria-label={`Span recall against tokens (local tokenizer), ${dots.length} settings, ${line.length} on the frontier, ${onDots} with header B on`}>
          <ResponsiveContainer width="100%" height={340}>
            <ScatterChart margin={{ top: 12, right: 20, bottom: 36, left: 16 }}>
              <CartesianGrid stroke="#c5ccd4" />
              <XAxis
                type="number"
                dataKey="x"
                name="Tokens"
                domain={[(min: number) => Math.max(0, Math.floor((min * 0.97) / 50) * 50), (max: number) => Math.ceil((max * 1.02) / 50) * 50]}
                allowDecimals={false}
                tick={{ fill: "#1b2430", fontSize: 12 }}
                label={{ value: "Tokens (local tokenizer), mean retrieved", position: "insideBottom", offset: -20, fill: "#1b2430", fontSize: 13 }}
              />
              <YAxis
                type="number"
                dataKey="y"
                name="Span recall"
                domain={[0, 1]}
                tick={{ fill: "#1b2430", fontSize: 12 }}
                label={{ value: "Span recall", angle: -90, position: "insideLeft", fill: "#1b2430", fontSize: 13 }}
              />
              <Tooltip content={<Tip />} isAnimationActive={false} cursor={{ strokeDasharray: "3 3" }} />
              <Scatter name="Frontier" data={line} line={{ stroke: COLOR_LINE, strokeWidth: 2 }} shape={() => <g />} legendType="none" tooltipType="none" isAnimationActive={false} />
              {seriesGroups(dots, chunkers).map(({ key, chunker: c, name, data }) => {
                return (
                  <Scatter
                    key={key}
                    name={name}
                    data={data}
                    isAnimationActive={false}
                    shape={(p: unknown) => {
                      const { cx, cy, payload } = p as { cx: number; cy: number; payload: Dot };
                      return (
                        <g
                          role="button"
                          tabIndex={0}
                          aria-label={`Select setting ${settingShort(payload.setting)}`}
                          aria-pressed={payload.setting.setting_id === selected}
                          data-testid="point"
                          data-setting={payload.setting.setting_id}
                          data-series={payload.headerOn ? "on" : "off"}
                          style={{ cursor: "pointer" }}
                          onClick={() => pick(payload.setting.setting_id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              pick(payload.setting.setting_id);
                            }
                          }}
                        >
                          <MarkerShape cx={cx} cy={cy} chunker={c} hollow={!payload.onFrontier} selected={payload.setting.setting_id === selected} on={payload.headerOn} />
                        </g>
                      );
                    }}
                  />
                );
              })}
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}

      <ul className="legend-list" aria-label="Legend">
        <li><svg width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill={COLOR_OFF} stroke={COLOR_OFF} strokeWidth="2" /></svg> Structure (handwritten parser)</li>
        <li><svg width="16" height="16" aria-hidden="true"><rect x="2" y="2" width="12" height="12" fill={COLOR_OFF} stroke={COLOR_OFF} strokeWidth="2" /></svg> Fixed-size</li>
        <li><svg width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="#6b7480" stroke="#6b7480" strokeWidth="2" /></svg> Frontier (filled), joined by a line</li>
        <li><svg width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="#fff" stroke="#6b7480" strokeWidth="2" /></svg> Dominated (hollow)</li>
        <li data-testid="legend-off"><span className="swatch" style={{ background: COLOR_OFF }} aria-hidden="true" /> Header B off</li>
        {onDots > 0 ? (
          <li data-testid="legend-on"><span className="swatch" style={{ background: COLOR_ON }} aria-hidden="true" /> Header B on</li>
        ) : (
          <li className="muted" data-testid="legend-on"><span className="swatch none" aria-hidden="true" /> Header B on: no points</li>
        )}
      </ul>
      {grid.header_scope === "frontier_only" && onDots > 0 && <p className="note">Header B computed for frontier settings only.</p>}
      {failed.length > 0 && (
        <section aria-label="Failed header-on settings" data-testid="failed-settings">
          <h3 className="detail-title">Failed header-on settings</h3>
          <p className="note">These settings are not plotted: their header-on run failed.</p>
          <ul className="failed-list">
            {failed.map((f) => {
              const st = byId.get(f.setting_id);
              return (
                <li key={f.setting_id}>
                  <strong>{st ? settingShort(st) : f.setting_id.slice(0, 12)}</strong>: {failReason(f.reason)}
                  {f.chunk_id ? ` (chunk ${f.chunk_id.slice(0, 12)})` : ""}
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {hidden > 0 && <p className="note">{hidden} point{hidden > 1 ? "s" : ""} not plotted: no gold items in this split (n/a).</p>}

      <h3 className="detail-title">Selected setting</h3>
      {sel ? (
        <dl className="detail">
          <div>
            <dt>Setting</dt>
            <dd>{settingShort(sel)}</dd>
          </div>
          {(["held_out", "tune"] as SplitName[]).map((sp) => {
            const p = pointOf(snap, sel.setting_id, sp);
            return (
              <div key={sp}>
                <dt>
                  <span className={`tag ${sp === "held_out" ? "ok" : "neutral"}`}>{sp === "held_out" ? "held-out" : "tune"}</span>
                </dt>
                <dd>
                  {p ? (
                    <>
                      {xOfY(p.fully_covered_count.covered, p.fully_covered_count.total, "items fully covered")}
                      <br />
                      Span recall (mean): {exactStr(p.exact, "mean_span_recall")}
                      <br />
                      MRR: {exactStr(p.exact, "mrr")}
                      <br />
                      {frontierIds(snap, sp).has(sel.setting_id) ? "On the frontier" : "Dominated"}
                    </>
                  ) : (
                    "n/a"
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
      ) : (
        <EmptyBlock>Click a point to select a setting</EmptyBlock>
      )}
    </>
  );
}
