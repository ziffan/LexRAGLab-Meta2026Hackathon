import { useEffect, useReducer, useRef, useState } from "react";
import { fetchHealth } from "../api";
import { useStore } from "../state";
import {
  SUMMARY_HEADERS, answerProfiles, baselineFor, columnView, modelDetail, profileLabel, defaultProfile, evidenceReducer, flagLabel, formatUsd, isGlimmer, loadEvidence,
  modelLabel, profileUnavailableText, runLiveState, summaryRows, tokenStr, type ColumnView, type EvidenceState,
} from "../lib/evidence";
import { fixed3, orNa } from "../lib/format";
import { settingShort } from "../lib/labels";
import { availableSettings } from "../lib/settings";
import type { AnswersResponse, Health, Setting } from "../types";
import { Hint } from "./Hint";
import { markFeatures } from "../lib/hints";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "./Shell";

// U3 End-to-end evidence (docs/UI-SPEC.md U3). Presentasi murni di `EvidenceView`; `EvidencePanel` menyambung store + W6.

const Tag = ({ kind, children }: { kind: "ok" | "bad" | "gray"; children: string }) => (
  <span className={`tag ev-${kind}`}>{children}</span>
);

function Check({ name, value }: { name: string; value: string | null }) {
  if (value === null) return <Tag kind="gray">{`${name}: Not run`}</Tag>;
  return <Tag kind={value === "Pass" ? "ok" : "bad"}>{`${name}: ${value}`}</Tag>;
}

export function EvidenceColumn({ col, settings, modelName }: { col: ColumnView; settings: Setting[]; modelName?: string }) {
  const setting = settings.find((s) => s.setting_id === col.settingId);
  return (
    <article className="column ev-col" aria-label={col.title}>
      <h3 className="column-title">{col.title}</h3>
      <dl className="detail ev-meta">
        <div><dt>Setting</dt><dd>{setting ? settingShort(setting) : col.settingId}</dd></div>
        <div><dt>Model</dt><dd>{orNa(col.model)}</dd></div>
        <div><dt>Quantization</dt><dd>{orNa(col.quantization)}</dd></div>
        <div><dt>Effort</dt><dd>{orNa(col.effort)}</dd></div>
        <div><dt>Model profile</dt><dd>{modelName && modelName !== col.modelProfile ? `${modelName} (${col.modelProfile})` : col.modelProfile}</dd></div>
        <div><dt>Status</dt><dd><strong data-status={col.statusCode}>{col.status}</strong></dd></div>
      </dl>
      <h4 className="detail-title">Answer</h4>
      {col.answer ? <p className="ev-answer" lang="id">{col.answer}</p> : <p className="muted">No answer text.</p>}
      {col.flags.length > 0 && (
        <p className="note" aria-label="Flags">
          Flags (informational): {col.flags.map((f) => <span key={f} className="tag neutral" title={f}>{flagLabel(f)}</span>)}
        </p>
      )}
      <h4 className="detail-title">Citations<Hint id="verifier.exists" /><Hint id="verifier.faithful" /><Hint id="verifier.valid_on_date" /><Hint id="status.valid" /><Hint id="status.revoked" /><Hint id="status.conditional" /></h4>
      {col.citations.length === 0 ? (
        <p className="muted">No citations.</p>
      ) : (
        <ol className="ev-cites">
          {col.citations.map((c, i) => (
            <li key={`${c.alamat}-${i}`} className="ev-cite">
              <div className="mono ev-addr" lang="id">{c.alamat}</div>
              <blockquote className="ev-quote" lang="id">{c.teks}</blockquote>
              <div className="ev-checks">
                <Check name="Exists" value={c.exists} />
                <Check name="Faithful" value={c.faithful} />
                {c.validNotRun ? (
                  <span className="tag ev-gray" title="Stretch: the validity-on-date check was not run">Valid on date: Not run</span>
                ) : (
                  <span className="tag ev-ok">{`Valid on date: ${c.validOnDate}`}</span>
                )}
                {c.faithfulScore !== null && <span className="muted">faithful_score {fixed3(c.faithfulScore)}</span>}
              </div>
            </li>
          ))}
        </ol>
      )}
      <h4 className="detail-title">Cost and tokens</h4>
      <dl className="detail ev-cost">
        <div><dt>Cost (USD)</dt><dd>{formatUsd(col.costMicros)}</dd></div>
        <div><dt>Actual input tokens (usage)</dt><dd>{tokenStr(col.inputTokens)}</dd></div>
        <div><dt>Cached tokens</dt><dd>{tokenStr(col.cachedTokens)}</dd></div>
        <div><dt>Output tokens</dt><dd>{tokenStr(col.outputTokens)}</dd></div>
        <div><dt>Run</dt><dd>{col.origin ? `${orNa(col.runStatus)}: served from cache; original call ${col.origin.createdAt.replace("T", " ")} (cost and tokens above are from that call)` : orNa(col.runStatus)}</dd></div>
      </dl>
    </article>
  );
}

export function SummaryTable({ data, settings }: { data: AnswersResponse; settings: Setting[] }) {
  const rows = summaryRows(data.summary);
  if (rows.length === 0) return <p className="muted">No 2x2 summary for this item.</p>;
  return (
    <div className="table-wrap">
      <table className="data ev-summary">
        <caption className="cap">2x2 summary per setting, slot and model profile (raw counts, never summed across rows)</caption>
        <thead>
          <tr>
            <th scope="col">Setting</th><th scope="col">Slot</th><th scope="col">Model profile</th>
            {SUMMARY_HEADERS.map((h) => <th key={h} scope="col">{h}{h === "Abstained, correctly" && <span className="muted sublabel"> (no gold, or gold not in its context)</span>}</th>)}
            <th scope="col">Items</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const s = settings.find((x) => x.setting_id === r.settingId);
            return (
              <tr key={r.key}>
                <td>{s ? settingShort(s) : r.settingId}</td>
                <td>{r.slot === "best" ? "Best profile" : "Baseline"}</td>
                <td>{r.modelProfile}</td>
                {r.counts.map((n, i) => <td key={SUMMARY_HEADERS[i]}>{n}</td>)}
                <td>{r.nItems}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export interface EvidenceViewProps {
  state: EvidenceState;
  settings: Setting[];
  elapsedSeconds?: number;
  noItem?: boolean;
  noBaseline?: boolean;
  /** Kunci `model_profile` -> nama tampilan (dari R1); tanpa ini kunci ditampilkan apa adanya. */
  profileName?: (key: string) => string;
}

/** Badan panel: empty / loading / error / ready, tanpa store. */
export function EvidenceView({ state, settings, elapsedSeconds = 0, noItem = false, noBaseline = false, profileName }: EvidenceViewProps) {
  if (noItem) return <EmptyBlock>Select an item to see end-to-end evidence.</EmptyBlock>;
  if (noBaseline) return <EmptyBlock>Select a setting other than the fixed-size baseline to compare against it.</EmptyBlock>;
  const last = state.status === "loading" || state.status === "error" || state.status === "empty" ? state.last : null;
  let banner = null;
  if (state.status === "loading") banner = <LoadingBlock text={`Waiting for Muse Spark… ${elapsedSeconds}s`} />;
  else if (state.status === "error") banner = <ErrorBlock title={`Model call failed: ${state.message}${last ? ". Showing last stored run." : ""}`} />;
  else if (state.status === "empty") banner = <EmptyBlock>No end-to-end run for this item</EmptyBlock>;
  else if (state.status === "idle") banner = <EmptyBlock>No end-to-end run for this item</EmptyBlock>;
  const data = state.status === "ready" ? state.data : last;
  return (
    <>
      {banner}
      {data && (
        <>
          <p className="note">
            Context budget: {data.best.budget_tokens} tokens (local tokenizer), the same source text for both columns (address labels not counted).
            Actual input tokens come from the model usage and are shown per column.
          </p>
          <div className="columns two">
            <EvidenceColumn col={columnView(data.best, data.verifier, data.runs, "Best profile", data.origin_runs)} settings={settings} modelName={profileName?.(data.best.model_profile)} />
            <EvidenceColumn col={columnView(data.baseline, data.verifier, data.runs, "Baseline", data.origin_runs)} settings={settings} modelName={profileName?.(data.baseline.model_profile)} />
          </div>
          <h3 className="detail-title">2x2 summary<Hint id="verifier.matrix_2x2" /></h3>
          <SummaryTable data={data} settings={settings} />
        </>
      )}
    </>
  );
}

export interface EvidenceControlsProps {
  health: Health | null;
  profile: string | null;
  onProfile: (p: string | null) => void;
  runLive: { enabled: boolean; reason: string };
  onRunLive: () => void;
  busy: boolean;
}

export function EvidenceControls({ health, profile, onProfile, runLive, onRunLive, busy }: EvidenceControlsProps) {
  const profiles = answerProfiles(health);
  const current = profile ?? defaultProfile(health) ?? "";
  return (
    <div className="controls">
      <label className="field">
        <span>Model<Hint id="model.contributor" /><Hint id="model.glimmer_local" /><Hint id="model.spark_open_baseten" /><Hint id="model.comparison_rule" /></span>
        <select value={current} onChange={(e) => onProfile(e.target.value || null)} disabled={profiles.length === 0}>
          {profiles.length === 0 && <option value="">Server default</option>}
          {profiles.map((p) => (
            <option key={p.model_profile} value={p.model_profile} disabled={!p.available}>
              {modelDetail(p)}{p.available ? "" : ` (${profileUnavailableText(p)})`}
            </option>
          ))}
        </select>
      </label>
      {profiles.filter((p) => !p.available && p.unavailable_reason).map((p) => (
        <span key={p.model_profile} className="note">{modelLabel(p)}: {p.unavailable_reason}</span>
      ))}
      {profiles.some((p) => isGlimmer(p) && !p.available && !p.unavailable_reason) && <span className="note">Local Glimmer server not running</span>}
      <button type="button" onClick={onRunLive} disabled={!runLive.enabled || busy} title={runLive.reason}>Run live</button>
      {!runLive.enabled && <span className="note">{runLive.reason}</span>}
    </div>
  );
}

export function EvidencePanel() {
  const { state } = useStore();
  const snap = state.snapshot.status === "ready" ? state.snapshot.data : null;
  const [ev, dispatch] = useReducer(evidenceReducer, { status: "idle" } as EvidenceState);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthDone, setHealthDone] = useState(false);
  const reqId = useRef(0);
  const [profile, setProfile] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    let live = true;
    fetchHealth()
      .then((h) => live && setHealth(h))
      .catch(() => undefined)
      .finally(() => live && setHealthDone(true));
    return () => {
      live = false;
    };
  }, []);

  // Fitur stretch hadir hanya bila datanya ada (UI-SPEC §9.3): validitas-tanggal dari hasil verifier, model dari profil tersedia.
  useEffect(() => {
    const ids: string[] = [];
    if (ev.status === "ready" && ev.data.verifier.some((v) => v.valid_on_date !== "tidak_dijalankan")) {
      ids.push("verifier.valid_on_date");
      for (const v of ev.data.verifier) ids.push(v.valid_on_date === "berlaku" ? "status.valid" : v.valid_on_date === "dicabut" ? "status.revoked" : v.valid_on_date === "berlaku_bersyarat" ? "status.conditional" : "verifier.valid_on_date");
    }
    for (const p of health?.model_profiles ?? []) {
      if (!p.available) continue;
      if (/glimmer/i.test(`${p.model_profile} ${p.model ?? ""}`)) ids.push("model.glimmer_local");
      else if (/spark[-_ ]?open|baseten/i.test(`${p.model_profile} ${p.model ?? ""}`)) ids.push("model.spark_open_baseten");
    }
    if (ids.length) markFeatures(ids);
  }, [ev, health]);

  const settings = snap ? availableSettings(snap) : [];
  const best = settings.find((s) => s.setting_id === state.selectedSettingId);
  const base = baselineFor(settings, best);
  const item = snap?.items.find((i) => i.id === state.selectedItemId);
  const noBaseline = !!best && (!base || base.setting_id === best.setting_id);
  const effProfile = profile ?? defaultProfile(health);

  // Muat jawaban tersimpan (live: false) saat butir, setting, atau model berganti.
  const itemId = item?.id;
  const bestId = best?.setting_id;
  const baseId = base?.setting_id;
  useEffect(() => {
    const id = ++reqId.current;
    if (!snap || !itemId || !bestId || !baseId || bestId === baseId) {
      dispatch({ type: "reset" });
      return;
    }
    if (!healthDone) return; // tunggu profil model supaya tidak memuat dua kali
    void loadEvidence({ family: snap.family, itemId, bestSettingId: bestId, baselineSettingId: baseId, modelProfile: effProfile, live: false }, dispatch, undefined, () => reqId.current === id);
    return () => {
      reqId.current++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap?.family, itemId, bestId, baseId, effProfile, healthDone]);

  const loading = ev.status === "loading";
  useEffect(() => {
    if (!loading) {
      setElapsed(0);
      return;
    }
    const t = setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [loading]);

  const runLive = runLiveState(item?.scene_checked, healthDone && health !== null, health?.model_profiles.find((p) => p.model_profile === effProfile), !healthDone);
  const doLive = () => {
    if (!snap || !itemId || !bestId || !baseId) return;
    const id = ++reqId.current;
    void loadEvidence({ family: snap.family, itemId, bestSettingId: bestId, baselineSettingId: baseId, modelProfile: effProfile, live: true }, dispatch, undefined, () => reqId.current === id);
  };

  let body;
  if (state.snapshot.status === "idle" || state.snapshot.status === "loading") body = <LoadingBlock text="Loading end-to-end evidence…" />;
  else if (state.snapshot.status === "error") body = <ErrorBlock title="Could not load the family snapshot." message={state.snapshot.message} />;
  else {
    body = (
      <>
        <EvidenceControls health={health} profile={profile} onProfile={setProfile} runLive={runLive} onRunLive={doLive} busy={loading} />
        <EvidenceView state={ev} settings={settings} elapsedSeconds={elapsed} noItem={!item} noBaseline={!!item && noBaseline} profileName={(k) => profileLabel(health, k)} />
      </>
    );
  }
  return (
    <section className="panel" aria-labelledby="evidence-title" id="evidence">
      <div className="panel-head"><h2 id="evidence-title">End-to-end evidence</h2><Hint id="role.c" /></div>
      {body}
    </section>
  );
}
