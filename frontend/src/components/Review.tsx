import { useEffect, useMemo, useRef, useSyncExternalStore, type KeyboardEvent } from "react";
import {
  ReviewController, canApprove, codePointToUtf16, isEditableTarget, pendingLabel, splitHighlight,
  type ContextView, type EditState, type ProposalRecord, type ReviewState,
} from "../lib/review";
import { modeLabel } from "../lib/labels";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "./Shell";

// U6 Review proposals (docs/UI-SPEC.md U6): layar terpisah `/review`. Komponen menggambar keadaan `ReviewController`.

export interface CardProps {
  proposal: ProposalRecord;
  context: ContextView | null;
  docText: string;
  busy: boolean;
  confirming: boolean;
  editing: boolean;
  edit: EditState | null;
  note: string;
  error: string;
  actions: {
    approve: () => void;
    edit: () => void;
    reject: () => void;
    confirmReject: () => void;
    cancelReject: () => void;
    setNote: (v: string) => void;
    setEdit: (p: Partial<Pick<EditState, "query" | "mode">>) => void;
    addSelection: (s: number, e: number) => void;
    removeSpan: (i: number) => void;
    submitEdit: () => void;
    closeEdit: () => void;
    key: (e: KeyboardEvent<HTMLElement>) => void;
  };
}

const yesNo = (b: boolean): string => (b ? "Yes" : "No");

function EditForm({ p, edit, docText, ctx, busy, a }: { p: ProposalRecord; edit: EditState; docText: string; ctx: ContextView | null; busy: boolean; a: CardProps["actions"] }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  // Konteks yang bisa diseleksi: konteks span bila ada, selain itu 600 karakter pertama dokumen.
  const shown = ctx ?? { text: Array.from(docText).slice(0, 600).join(""), hlStart: 0, hlEnd: 0, ctxStart: 0, ctxEnd: 0 };
  const base = codePointToUtf16(docText, shown.ctxStart);
  const add = () => {
    const el = ref.current;
    if (el) a.addSelection(base + el.selectionStart, base + el.selectionEnd);
  };
  return (
    <form className="edit-form" onSubmit={(e) => { e.preventDefault(); a.submitEdit(); }} aria-label="Edit proposal">
      <label>Query
        <input type="text" value={edit.query} onChange={(e) => a.setEdit({ query: e.target.value })} />
      </label>
      <label>Mode
        <select value={edit.mode} onChange={(e) => a.setEdit({ mode: e.target.value as "literal" | "parafrase" })}>
          <option value="literal">{modeLabel("literal")}</option>
          <option value="parafrase">{modeLabel("parafrase")}</option>
        </select>
      </label>
      <label>Select the span in the context, then add it
        <textarea ref={ref} readOnly rows={6} value={shown.text} aria-label="Context" />
      </label>
      <button type="button" onClick={add}>Add selection as span</button>
      <ul className="spans">
        {edit.spans.map((s, i) => (
          <li key={`${s.start}-${s.end}-${i}`}>
            Span [{s.start}, {s.end}) <button type="button" onClick={() => a.removeSpan(i)} aria-label={`Remove span ${i + 1}`}>Remove</button>
          </li>
        ))}
      </ul>
      {edit.error && <div className="form-error" role="alert">{edit.error}</div>}
      <div className="card-actions">
        <button type="submit" disabled={busy}>Save edit</button>
        <button type="button" onClick={a.closeEdit}>Cancel</button>
      </div>
      <span className="sr-only">{p.proposal_id}</span>
    </form>
  );
}

export function ProposalCard(props: CardProps) {
  const { proposal: p, context, busy, confirming, editing, edit, note, error, actions: a } = props;
  const ok = canApprove(p);
  const [before, hit, after] = context ? splitHighlight(context) : ["", "", ""];
  return (
    <article className="proposal-card" tabIndex={0} data-proposal-id={p.proposal_id} onKeyDown={a.key} aria-label={`Proposal ${p.body.query}`}>
      <header className="card-head">
        <strong className="card-query">{p.body.query}</strong>
        <span className="tag neutral">{modeLabel(p.body.mode)}</span>
        <span className="muted">{p.body.doc_id}</span>
      </header>
      {context ? (
        <pre className="ctx" aria-label="Span in context">{before}<mark>{hit}</mark>{after}</pre>
      ) : (
        <pre className="ctx unresolved" aria-label="Proposed quote">{p.body.teks_gold}</pre>
      )}
      <dl className="detail">
        <dt>Span</dt>
        <dd>{p.resolved_span ? `[${p.resolved_span.start}, ${p.resolved_span.end})` : "not located"}</dd>
        <dt>Offset found</dt>
        <dd>{yesNo(p.validation.offset_found)}</dd>
        <dt>Text matches</dt>
        <dd>{yesNo(p.validation.text_matches)}</dd>
      </dl>
      {!ok && <div className="note">The span could not be validated. You can edit it or reject the proposal.</div>}
      <label className="note-field">Operator note
        <input type="text" value={note} onChange={(e) => a.setNote(e.target.value)} />
      </label>
      <div className="card-actions">
        <button type="button" onClick={a.approve} disabled={!ok || busy} aria-disabled={!ok || busy}>Approve</button>
        <button type="button" onClick={a.edit} disabled={busy}>Edit</button>
        <button type="button" onClick={a.reject} disabled={busy}>Reject</button>
        <span className="muted">Keys: A approve, E edit, R reject</span>
      </div>
      {confirming && (
        <div className="confirm" role="alertdialog" aria-label="Confirm reject">
          <span>Reject this proposal?</span>
          <button type="button" onClick={a.confirmReject} disabled={busy}>Confirm reject</button>
          <button type="button" onClick={a.cancelReject}>Cancel</button>
        </div>
      )}
      {editing && edit && <EditForm p={p} edit={edit} docText={props.docText} ctx={context} busy={busy} a={a} />}
      {error && <div className="state error" role="alert">{error}</div>}
    </article>
  );
}

export function ReviewList({ state, ctl }: { state: ReviewState; ctl: ReviewController }) {
  if (state.load === "idle" || state.load === "loading") return <LoadingBlock text="Loading proposals…" />;
  if (state.load === "error") return <ErrorBlock title="Could not load proposals." message={state.loadMessage} />;
  if (state.proposals.length === 0) return <EmptyBlock>No pending proposals</EmptyBlock>;
  return (
    <div className="proposal-list">
      {state.proposals.map((p) => {
        const id = p.proposal_id;
        return (
          <ProposalCard
            key={id}
            proposal={p}
            context={ctl.contextFor(p)}
            docText={state.docs[p.body.doc_id] ?? ""}
            busy={state.busyId !== null}
            confirming={state.confirmingId === id}
            editing={state.editingId === id}
            edit={state.editingId === id ? state.edit : null}
            note={state.notes[id] ?? ""}
            error={state.errors[id] ?? ""}
            actions={{
              approve: () => void ctl.approve(id),
              edit: () => ctl.openEdit(id),
              reject: () => ctl.askReject(id),
              confirmReject: () => void ctl.confirmReject(id),
              cancelReject: () => ctl.cancelReject(),
              setNote: (v) => ctl.setNote(id, v),
              setEdit: (patch) => ctl.setEdit(patch),
              addSelection: (s, e) => ctl.addSelection(s, e),
              removeSpan: (i) => ctl.removeSpan(i),
              submitEdit: () => void ctl.submitEdit(),
              closeEdit: () => ctl.closeEdit(),
              key: (e) => {
                const t = e.target as HTMLElement;
                const handled = ctl.onKey(id, {
                  key: e.key, ctrlKey: e.ctrlKey, metaKey: e.metaKey, altKey: e.altKey,
                  editable: isEditableTarget(t.tagName, t.isContentEditable),
                });
                if (handled) e.preventDefault();
              },
            }}
          />
        );
      })}
    </div>
  );
}

export function ReviewScreen() {
  const ctl = useMemo(() => new ReviewController((url, init) => fetch(url, init)), []);
  const state = useSyncExternalStore(ctl.subscribe, ctl.getState, ctl.getState);
  useEffect(() => {
    void ctl.load();
  }, [ctl]);
  return (
    <div className="app review">
      <header className="app-header">
        <span className="brand">LexRAGLab</span>
        <a href="/">Back to overview</a>
      </header>
      <main className="layout">
        <section className="panel wide" aria-labelledby="review-title">
          <h2 id="review-title">{state.load === "ready" ? pendingLabel(state.proposals.length) : "Review proposals"}</h2>
          <ReviewList state={state} ctl={ctl} />
        </section>
      </main>
      <footer className="app-footer">Research demo. Not legal advice.</footer>
    </div>
  );
}
