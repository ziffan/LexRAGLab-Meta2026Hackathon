import { useEffect, useReducer, useState } from "react";
import { fetchSnapshot } from "../api";
import { STATIC_DISABLED, isStatic } from "../lib/staticData";
import { useStore } from "../state";
import {
  DIFF_KIND_LABEL, diffBodies, diffKind, editorReducer, emptyEditor, versionLabel, showValue, submitCorrection,
  type EditorAction, type EditorState, type FieldErrors,
} from "../lib/schemaEdit";
import type { SchemaDiff, SchemaDiffEntry, SchemaRecord, SchemaRejected } from "../types";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "./Shell";

// U5 Structure schema (A) (docs/UI-SPEC.md U5). `SchemaView` dan `SchemaEditor` murni (props); `SchemaPanel` menyambung store.

function VersionLevels({ rec, changedOrders }: { rec: SchemaRecord; changedOrders: Map<number, string> }) {
  return (
    <div className="table-wrap">
      <table className="data schema-levels">
        <caption className="cap">{versionLabel(rec)}{rec.operator_note ? ` · note: ${rec.operator_note}` : ""}</caption>
        <thead>
          <tr>
            <th scope="col">Order</th><th scope="col">Level</th><th scope="col">Marker pattern</th>
            <th scope="col">Example</th><th scope="col">Default chunk unit</th>
          </tr>
        </thead>
        <tbody>
          {rec.body.levels.map((l) => {
            const mark = changedOrders.get(l.order);
            return (
              <tr key={l.order} className={mark ? `diff-${mark}` : undefined}>
                <td>{l.order}{mark && <span className="tag neutral">{DIFF_KIND_LABEL[mark as keyof typeof DIFF_KIND_LABEL]}</span>}</td>
                <td>{l.name}</td>
                <td className="mono">{l.marker_pattern}</td>
                <td className="mono" lang="id">{l.examples.map((e) => <div key={e}>{e}</div>)}</td>
                <td>{l.order === rec.body.default_chunk_level ? "Yes (default)" : l.is_chunk_unit ? "Yes" : "No"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function changedMap(entries: SchemaDiffEntry[], side: "before" | "after"): Map<number, string> {
  const m = new Map<number, string>();
  for (const e of entries) {
    if (e.order === null) continue;
    const k = diffKind(e);
    if (k === "added" && side === "before") continue;
    if (k === "removed" && side === "after") continue;
    m.set(e.order, k);
  }
  return m;
}

export function DiffTable({ entries }: { entries: SchemaDiffEntry[] }) {
  if (entries.length === 0) return <p className="muted">No changed lines between these versions.</p>;
  return (
    <div className="table-wrap">
      <table className="data schema-diff">
        <caption className="cap">Changed lines</caption>
        <thead><tr><th scope="col">Order</th><th scope="col">Field</th><th scope="col">Change</th><th scope="col">Before</th><th scope="col">After</th></tr></thead>
        <tbody>
          {entries.map((e, i) => (
            <tr key={`${e.order}-${e.field}-${i}`}>
              <td>{e.order === null ? "—" : e.order}</td>
              <td>{e.field}</td>
              <td>{DIFF_KIND_LABEL[diffKind(e)]}</td>
              <td className="mono">{showValue(e.before)}</td>
              <td className="mono">{showValue(e.after)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RejectedList({ rejected }: { rejected: SchemaRejected[] }) {
  if (rejected.length === 0) return null;
  return (
    <section aria-label="Rejected output">
      <h3 className="detail-title">Rejected output</h3>
      <p className="note">Spark output that failed validation. Not a version and never used by the chunker.</p>
      <ul className="rejected">
        {rejected.map((r) => (
          <li key={r.run_id}>
            <span className="mono">{r.run_id}</span> · {r.created_at}
            <ul>{r.errors.map((e, i) => <li key={i} className="form-error">{e}</li>)}</ul>
          </li>
        ))}
      </ul>
    </section>
  );
}

function BoundaryDiff({ diff }: { diff: SchemaDiff | null | undefined }) {
  const rows = diff?.boundary_diff ?? [];
  return (
    <section aria-label="Boundary differences vs handwritten parser">
      <h3 className="detail-title">Boundary differences vs handwritten parser</h3>
      {rows.length === 0 ? (
        <p className="muted">No boundary differences reported.</p>
      ) : (
        <ul>{rows.map((r) => <li key={r.doc_id}><span className="mono">{r.doc_id}</span>: schema only {showValue(r.only_schema)}, handwritten only {showValue(r.only_handwritten)}</li>)}</ul>
      )}
    </section>
  );
}

export interface SchemaViewProps {
  schemas: SchemaRecord[];
  rejected: SchemaRejected[];
  diff?: SchemaDiff | null;
  fromVersion: number | null;
  toVersion: number | null;
  onFrom: (v: number) => void;
  onTo: (v: number) => void;
}

export function SchemaView({ schemas, rejected, diff, fromVersion, toVersion, onFrom, onTo }: SchemaViewProps) {
  if (schemas.length === 0 && rejected.length === 0) return <EmptyBlock>No schema induced for this family yet</EmptyBlock>;
  const from = schemas.find((s) => s.schema_version === fromVersion) ?? null;
  const to = schemas.find((s) => s.schema_version === toVersion) ?? null;
  const entries = from && to ? diffBodies(from.body, to.body) : [];
  return (
    <>
      {schemas.length > 0 && (
        <>
          <div className="controls">
            <label className="field">
              <span>Compare version</span>
              <select value={fromVersion ?? ""} onChange={(e) => onFrom(Number(e.target.value))}>
                {schemas.map((s) => <option key={s.schema_version} value={s.schema_version}>{versionLabel(s)}</option>)}
              </select>
            </label>
            <label className="field">
              <span>With version</span>
              <select value={toVersion ?? ""} onChange={(e) => onTo(Number(e.target.value))}>
                {schemas.map((s) => <option key={s.schema_version} value={s.schema_version}>{versionLabel(s)}</option>)}
              </select>
            </label>
          </div>
          <div className="columns two">
            <div className="column">{from && <VersionLevels rec={from} changedOrders={changedMap(entries, "before")} />}</div>
            <div className="column">{to && from?.schema_version !== to.schema_version && <VersionLevels rec={to} changedOrders={changedMap(entries, "after")} />}</div>
          </div>
          {from && to && from.schema_version !== to.schema_version && <DiffTable entries={entries} />}
        </>
      )}
      <BoundaryDiff diff={diff} />
      <RejectedList rejected={rejected} />
    </>
  );
}

function Errs({ list }: { list?: string[] }) {
  if (!list || list.length === 0) return null;
  return <>{list.map((m, i) => <div key={i} className="form-error" role="alert">{m}</div>)}</>;
}

export function SchemaEditor({ state, dispatch, readOnlyReason, onSave }: {
  state: EditorState;
  dispatch: (a: EditorAction) => void;
  readOnlyReason: string | null;
  onSave: () => void;
}) {
  const e: FieldErrors = state.errors;
  return (
    <form className="edit-form schema-editor" aria-label="Edit structure schema" onSubmit={(ev) => { ev.preventDefault(); onSave(); }}>
      <h3 className="detail-title">Edit (operator correction, starts from v{state.parentVersion})</h3>
      {state.levels.map((l, i) => (
        <fieldset key={i} className="level-form">
          <legend>Level {i + 1}</legend>
          <label>Order<input type="text" inputMode="numeric" value={l.order} onChange={(ev) => dispatch({ type: "level", index: i, patch: { order: ev.target.value } })} /></label>
          <Errs list={e.levels[i]?.order} />
          <label>Level<input type="text" value={l.name} onChange={(ev) => dispatch({ type: "level", index: i, patch: { name: ev.target.value } })} /></label>
          <Errs list={e.levels[i]?.name} />
          <label>Marker pattern<input type="text" className="mono" value={l.marker_pattern} onChange={(ev) => dispatch({ type: "level", index: i, patch: { marker_pattern: ev.target.value } })} /></label>
          <Errs list={e.levels[i]?.marker_pattern} />
          <label>Example (one per line)<textarea className="mono" rows={3} value={l.examples} onChange={(ev) => dispatch({ type: "level", index: i, patch: { examples: ev.target.value } })} /></label>
          <Errs list={e.levels[i]?.examples} />
          <label>Parent order (empty = none)<input type="text" inputMode="numeric" value={l.parent_order} onChange={(ev) => dispatch({ type: "level", index: i, patch: { parent_order: ev.target.value } })} /></label>
          <Errs list={e.levels[i]?.parent_order} />
          <label className="check"><input type="checkbox" checked={l.is_chunk_unit} onChange={(ev) => dispatch({ type: "level", index: i, patch: { is_chunk_unit: ev.target.checked } })} />Chunk unit</label>
          <Errs list={e.levels[i]?.level} />
          <button type="button" onClick={() => dispatch({ type: "remove_level", index: i })} aria-label={`Remove level ${i + 1}`}>Remove level</button>
        </fieldset>
      ))}
      <button type="button" onClick={() => dispatch({ type: "add_level" })}>Add level</button>
      <label>Default chunk unit (order)
        <input type="text" inputMode="numeric" value={state.defaultChunkLevel} onChange={(ev) => dispatch({ type: "top", patch: { defaultChunkLevel: ev.target.value } })} />
      </label>
      <Errs list={e.top.default_chunk_level} />
      <label>Schema notes
        <textarea rows={2} value={state.notes} onChange={(ev) => dispatch({ type: "top", patch: { notes: ev.target.value } })} />
      </label>
      <label>Operator note
        <textarea rows={2} maxLength={2000} value={state.operatorNote} onChange={(ev) => dispatch({ type: "top", patch: { operatorNote: ev.target.value } })} />
      </label>
      <Errs list={e.general} />
      <div className="card-actions">
        <button type="submit" disabled={state.busy || readOnlyReason !== null} title={readOnlyReason ?? undefined}>Save as new version</button>
        {readOnlyReason && <span className="note">{readOnlyReason}</span>}
      </div>
    </form>
  );
}

const readOnlyText = (): string => (isStatic() ? STATIC_DISABLED : "Replay mode is read-only; schema corrections are not available.");

export function SchemaPanel() {
  const { state, dispatch: storeDispatch } = useStore();
  const snap = state.snapshot.status === "ready" ? state.snapshot.data : null;
  const schemas = snap?.schemas ?? [];
  const latest = schemas.length > 0 ? schemas[schemas.length - 1] : null;
  const [fromV, setFromV] = useState<number | null>(null);
  const [toV, setToV] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [parentV, setParentV] = useState<number | null>(null);
  const [form, formDispatch] = useReducer(editorReducer, undefined, emptyEditor);
  const [saved, setSaved] = useState<number | null>(null);

  const lastSpark = [...schemas].reverse().find((s) => s.source === "spark") ?? null;
  const lastOp = [...schemas].reverse().find((s) => s.source === "operator") ?? null;
  const selFrom = fromV ?? lastSpark?.schema_version ?? latest?.schema_version ?? null;
  const selTo = toV ?? lastOp?.schema_version ?? selFrom;
  const selParent = parentV ?? latest?.schema_version ?? null;

  useEffect(() => {
    const p = schemas.find((s) => s.schema_version === selParent);
    if (editing && p) formDispatch({ type: "load", parent: p });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, selParent, schemas.length]);

  const save = async () => {
    if (!snap) return;
    const r = await submitCorrection(form, formDispatch);
    if (!r.ok) return;
    setSaved(r.record.schema_version);
    setToV(r.record.schema_version);
    setParentV(r.record.schema_version);
    try {
      const fresh = await fetchSnapshot(snap.family, state.budget);
      storeDispatch({ type: "snapshot_ready", data: fresh });
    } catch {
      /* snapshot dimuat ulang pada kesempatan berikut; versi sudah tersimpan */
    }
  };

  let body;
  if (state.snapshot.status === "idle" || state.snapshot.status === "loading") body = <LoadingBlock text="Loading schema versions…" />;
  else if (state.snapshot.status === "error") body = <ErrorBlock title="Schema failed validation: could not load the family snapshot." message={state.snapshot.message} />;
  else if (snap) {
    body = (
      <>
        <SchemaView schemas={schemas} rejected={snap.schemas_rejected ?? []} diff={snap.schema_diff} fromVersion={selFrom} toVersion={selTo} onFrom={setFromV} onTo={setToV} />
        {schemas.length > 0 && (
          <div className="controls">
            <label className="field">
              <span>Correct from version</span>
              <select value={selParent ?? ""} onChange={(e) => setParentV(Number(e.target.value))}>
                {schemas.map((s) => <option key={s.schema_version} value={s.schema_version}>{versionLabel(s)}</option>)}
              </select>
            </label>
            <button type="button" onClick={() => setEditing((v) => !v)} aria-expanded={editing} disabled={snap?.replay === true} title={snap?.replay ? readOnlyText() : undefined}>{editing ? "Close editor" : "Edit"}</button>
          </div>
        )}
        {saved !== null && <div className="tag ok" role="status">Saved as v{saved}. Earlier versions are unchanged.</div>}
        {editing && schemas.length > 0 && (
          <SchemaEditor state={form} dispatch={formDispatch} readOnlyReason={snap.replay ? readOnlyText() : null} onSave={() => void save()} />
        )}
      </>
    );
  }
  return (
    <section className="panel" aria-labelledby="schema-title" id="schema">
      <h2 id="schema-title">Structure schema (A)</h2>
      {body}
    </section>
  );
}
