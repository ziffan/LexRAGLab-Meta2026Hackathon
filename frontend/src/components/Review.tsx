import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type KeyboardEvent } from "react";
import {
  REVIEW_FAMILIES, DOC_NOUN, ReviewController, alasanLabel, canApprove, checkStale, flagLabel, isUnanswerable, mustRefuseCounts, mustRefuseLabel, codePointToUtf16, isEditableTarget, parseReviewFamily, pendingLabel, reviewSearch, splitHighlight,
  type ContextView, type EditState, type ProposalRecord, type ReviewState,
} from "../lib/review";
import { apiFetch } from "../api";
import { truncate } from "../lib/format";
import { modeLabel } from "../lib/labels";
import { STATIC_DISABLED, isStatic } from "../lib/staticData";
import { FAMILY_LABELS, ReplayBadge } from "./Header";
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
  /** Hash konfigurasi pemeriksaan sekarang (SU9); null bila server tidak melaporkannya. */
  checkConfigHash?: string | null;
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
  const refuse = p.body.mode === "unanswerable";
  return (
    <form className="edit-form" onSubmit={(e) => { e.preventDefault(); a.submitEdit(); }} aria-label="Edit proposal">
      <label>Query
        <input type="text" value={edit.query} onChange={(e) => a.setEdit({ query: e.target.value })} />
      </label>
      {!refuse && <label>Mode
        <select value={edit.mode} onChange={(e) => a.setEdit({ mode: e.target.value as "literal" | "parafrase" })}>
          <option value="literal">{modeLabel("literal")}</option>
          <option value="parafrase">{modeLabel("parafrase")}</option>
        </select>
      </label>}
      {!refuse && <label>Select the span in the context, then add it
        <textarea ref={ref} readOnly rows={6} value={shown.text} aria-label="Context" />
      </label>}
      {!refuse && <button type="button" onClick={add}>Add selection as span</button>}
      {!refuse && <ul className="spans">
        {edit.spans.map((s, i) => (
          <li key={`${s.start}-${s.end}-${i}`}>
            Span [{s.start}, {s.end}) <button type="button" onClick={() => a.removeSpan(i)} aria-label={`Remove span ${i + 1}`}>Remove</button>
          </li>
        ))}
      </ul>}
      {edit.error && <div className="form-error" role="alert">{edit.error}</div>}
      <div className="card-actions">
        <button type="submit" disabled={busy}>Save edit</button>
        <button type="button" onClick={a.closeEdit}>Cancel</button>
      </div>
      <span className="sr-only">{p.proposal_id}</span>
    </form>
  );
}

/** Kartu `unanswerable` (H-087, H-092, H-099; SU19, SV16): alasan dan label per keluarga, lencana pemeriksaan, `Closest passages`. Tanpa span dan tanpa validasi span. */
function RefuseDetail({ p, stale }: { p: ProposalRecord; stale: boolean }) {
  const ac = p.absence_check;
  return (
    <div className="refuse-detail">
      <dl className="detail">
        <dt>Reason</dt>
        <dd>{alasanLabel(p.body.alasan_kode, p.family)}{p.body.alasan_teks ? `: ${p.body.alasan_teks}` : ""}</dd>
      </dl>
      <div className="badges">
        {ac?.status === "doubtful" && <span className="tag split">Doubtful</span>}
        {p.duplicate_of != null && <span className="tag neutral">Duplicate of an existing proposal</span>}
        {stale && <span className="tag neutral">Check settings changed</span>}
      </div>
      {ac?.status === "doubtful" && (
        <p className="note">Why flagged: {ac.reasons.map((r) => flagLabel(r, p.family)).join("; ")}</p>
      )}
      {ac && ac.top_k.length > 0 && (
        <div>
          <strong>Closest passages</strong>
          <ol className="closest" aria-label="Closest passages">
            {ac.top_k.map((t, i) => (
              <li key={`${t.source}-${t.rank}-${i}`}>
                <span className="muted">{t.source === "bm25" ? "BM25" : "Dense"} #{t.rank}</span> <span>{t.unit_text}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

export function ProposalCard(props: CardProps) {
  const { proposal: p, context, busy, confirming, editing, edit, note, error, actions: a } = props;
  const ok = canApprove(p);
  const refuse = isUnanswerable(p);
  const [before, hit, after] = context ? splitHighlight(context) : ["", "", ""];
  return (
    <article className="proposal-card" tabIndex={0} data-proposal-id={p.proposal_id} onKeyDown={a.key} aria-label={`Proposal ${p.body.query}`}>
      <header className="card-head">
        <strong className="card-query">{p.body.query}</strong>
        <span className="tag neutral">{modeLabel(p.body.mode)}</span>
        <span className="muted">{p.body.doc_id}</span>
      </header>
      {refuse ? <RefuseDetail p={p} stale={checkStale(p, props.checkConfigHash ?? null)} /> : (
        <>
          {context ? (
            <pre className="ctx" aria-label="Span in context">{before}<mark>{hit}</mark>{after}</pre>
          ) : (
            <pre className="ctx unresolved" aria-label="Proposed quote">{p.body.teks_gold}</pre>
          )}
          <dl className="detail">
            <dt>Span</dt>
            <dd>{p.resolved_span ? `[${p.resolved_span.start}, ${p.resolved_span.end})` : "not located"}</dd>
            <dt>Offset found</dt>
            <dd>{yesNo(p.validation?.offset_found ?? false)}</dd>
            <dt>Text matches</dt>
            <dd>{yesNo(p.validation?.text_matches ?? false)}</dd>
          </dl>
        </>
      )}
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
            busy={state.busyId !== null || isStatic()}
            confirming={state.confirmingId === id}
            editing={state.editingId === id}
            edit={state.editingId === id ? state.edit : null}
            note={state.notes[id] ?? ""}
            error={state.errors[id] ?? ""}
            checkConfigHash={state.checkConfigHash}
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

const DECISION_LABEL: Record<string, string> = { disetujui: "Approved", diubah: "Edited", ditolak: "Rejected" };

/** UX-08 (putusan operator 12): usulan yang sudah diputus operator, baca-saja, di bawah antrean. Tanpa tombol tulis. */
export function DecidedList({ state }: { state: ReviewState }) {
  if (state.load !== "ready") return null;
  const done = state.all.filter((p) => p.review_status !== "usulan")
    .sort((a, b) => (b.reviewed_at ?? "").localeCompare(a.reviewed_at ?? "") || a.proposal_id.localeCompare(b.proposal_id));
  if (done.length === 0) return null;
  return (
    <section aria-label="Decided proposals" data-testid="decided">
      <h3 className="detail-title">Decided ({done.length})</h3>
      <p className="note">Read-only. Operator decisions on Spark proposals; approved and edited proposals became items.</p>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr><th scope="col">Proposal</th><th scope="col">Mode</th><th scope="col">Query</th><th scope="col">Decision</th><th scope="col">Item</th><th scope="col">Reviewed (UTC)</th></tr>
          </thead>
          <tbody>
            {done.map((p) => (
              <tr key={p.proposal_id}>
                <th scope="row" className="mono">{p.proposal_id}</th>
                <td>{modeLabel(p.edited?.mode ?? p.body.mode)}</td>
                <td lang="id">{truncate(p.edited?.query ?? p.body.query ?? "", 100)}</td>
                <td>{DECISION_LABEL[p.review_status] ?? p.review_status}</td>
                <td className="mono">{p.item_id ?? "n/a"}</td>
                <td>{p.reviewed_at ? p.reviewed_at.replace("T", " ") : "n/a"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Penghitung antrean dan butir wajib tolak per akta (H-087); informasional, bukan gerbang. Hanya bila ada rekaman unanswerable. */
export function ReviewCounters({ state }: { state: ReviewState }) {
  const hasRefuse = state.all.some(isUnanswerable) || state.proposals.some(isUnanswerable);
  if (state.load !== "ready" || !hasRefuse) return null;
  const { total, perDoc } = mustRefuseCounts(state.all.length ? state.all : state.proposals);
  const fam = (state.all.find(isUnanswerable) ?? state.proposals.find(isUnanswerable))?.family;
  const noun = DOC_NOUN[fam ?? "akta"] ?? "deed";
  return (
    <div className="review-counters" role="status">
      <span>Pending {state.proposals.length}</span> <span>{mustRefuseLabel(total)}</span>
      <ul className="per-doc" aria-label={`Must-refuse approved per ${noun}`}>
        {Object.entries(perDoc).sort(([x], [y]) => x.localeCompare(y)).map(([doc, n]) => (
          <li key={doc}>{doc}: {n} approved{n === 0 ? " (target: at least 1)" : ""}</li>
        ))}
      </ul>
    </div>
  );
}

export function ReviewFamilyPicker({ family, onChange }: { family: string; onChange: (v: string) => void }) {
  return (
    <label className="family">
      Family:{" "}
      <select aria-label="Family" value={family} onChange={(e) => onChange(e.target.value)}>
        {REVIEW_FAMILIES.map((v) => (
          <option key={v} value={v}>{FAMILY_LABELS[v] ?? v}</option>
        ))}
      </select>
    </label>
  );
}

export function ReviewScreen() {
  const [family, setFamily] = useState(() => parseReviewFamily(window.location.search));
  const ctl = useMemo(() => new ReviewController(apiFetch, family), [family]);
  const state = useSyncExternalStore(ctl.subscribe, ctl.getState, ctl.getState);
  useEffect(() => {
    void ctl.load();
  }, [ctl]);
  const pick = (v: string) => {
    window.history.replaceState(null, "", reviewSearch(window.location.search, v));
    setFamily(v);
  };
  return (
    <div className="app review">
      <header className="app-header">
        <span className="brand">LexRAGLab</span>
        <ReviewFamilyPicker family={family} onChange={pick} />
        <ReplayBadge />
        <a href={isStatic() ? "./" : "/"}>Back to overview</a>
      </header>
      <main className="layout">
        <section className="panel wide" aria-labelledby="review-title">
          <h2 id="review-title">{state.load === "ready" ? pendingLabel(state.proposals.length) : "Review proposals"}</h2>
          {isStatic() && <div className="note" role="note">{STATIC_DISABLED}</div>}
          <ReviewCounters state={state} />
          <ReviewList state={state} ctl={ctl} />
          <DecidedList state={state} />
        </section>
      </main>
      <footer className="app-footer">Research demo. Not legal advice.</footer>
    </div>
  );
}
