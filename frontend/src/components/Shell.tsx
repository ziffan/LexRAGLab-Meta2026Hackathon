import type { ReactNode } from "react";
import { useStore } from "../state";
import { Hint } from "./Hint";
import { getHint } from "../lib/hints";
import type { Snapshot } from "../types";

// Tiga keadaan wajib per panel (docs/UI-SPEC.md §5): loading, empty, error.

export function LoadingBlock({ text }: { text: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <div className="skeleton" />
      <div className="skeleton" />
      <div className="skeleton short" />
      <span className="muted">{text}</span>
    </div>
  );
}

export function ErrorBlock({ title, message }: { title: string; message?: string }) {
  return (
    <div className="state error" role="alert">
      <strong>{title}</strong>
      {message && <div>{message}</div>}
    </div>
  );
}

export function EmptyBlock({ children }: { children: ReactNode }) {
  return <div className="state empty">{children}</div>;
}

/** Keluarga akta tanpa grid, atau dengan grid yang belum ditandai final: hasil menunggu review operator, bukan angka final
 *  (jangan tampilkan angka sementara). Banner hilang sendiri bila `grid.final === true`, yaitu bila `grid_run_id` di
 *  `config/akta_grid_final.toml` sama dengan kunci amplop grid akta tersimpan; operator/L2 yang mengisinya, UI tidak memutus. */
export const isPendingReview = (snap: Snapshot): boolean => snap.family === "akta" && (snap.grid === null || snap.grid.final !== true);

/** Hint "Tune vs held-out" tidak ditampilkan untuk akta: label held-out dilarang di layar akta (H-078). */
export const HELDOUT_HINT = "metric.tune_heldout";

export function PendingReview() {
  const h = getHint("ui.pending_review");
  return (
    <div className="state pending-review" role="status" data-testid="pending-review">
      <strong>{h?.title ?? "Pending operator review"}</strong>
      <div>{h?.body}</div>
    </div>
  );
}

/** Cangkang panel yang menunggu snapshot. `children` menerima snapshot siap. */
export function SnapshotPanel({ id, title, loadingText, errorTitle, hints = [], pendingGate = false, children }: {
  hints?: string[];
  /** U2/U4: bila keluarga akta belum punya grid, tampilkan banner "Pending operator review" menggantikan isi. */
  pendingGate?: boolean;
  id: string;
  title: string;
  loadingText: string;
  errorTitle: string;
  children: (snap: Snapshot) => ReactNode;
}) {
  const { state } = useStore();
  const s = state.snapshot;
  let body: ReactNode;
  if (s.status === "idle" || s.status === "loading") body = <LoadingBlock text={loadingText} />;
  else if (s.status === "error") {
    body = <ErrorBlock title={s.code === "unreachable" ? "Backend unreachable. Showing replay data if available." : errorTitle} message={s.message} />;
  } else body = pendingGate && isPendingReview(s.data) ? <PendingReview /> : children(s.data);
  return (
    <section className="panel" aria-labelledby={`${id}-title`}>
      <div className="panel-head"><h2 id={`${id}-title`}>{title}</h2>{hints.filter((h) => !(state.family === "akta" && h === HELDOUT_HINT)).map((h) => <Hint key={h} id={h} />)}</div>
      {body}
    </section>
  );
}
