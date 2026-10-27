import type { ReactNode } from "react";
import { useStore } from "../state";
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

/** Cangkang panel yang menunggu snapshot. `children` menerima snapshot siap. */
export function SnapshotPanel({ id, title, loadingText, errorTitle, children }: {
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
    body = <ErrorBlock title={s.code === "unreachable" ? "Backend unreachable." : errorTitle} message={s.message} />;
  } else body = children(s.data);
  return (
    <section className="panel" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{title}</h2>
      {body}
    </section>
  );
}
