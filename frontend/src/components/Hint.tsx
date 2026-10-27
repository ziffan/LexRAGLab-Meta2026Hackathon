import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { dispatchOpen, getHint, isEntryVisible, keyAction, useFeatures, useOpenKey } from "../lib/hints";

// Ikon info + popover (docs/UI-SPEC.md §9.1). Tertutup default; klik, Enter, Spasi membuka; Esc menutup dan mengembalikan
// fokus; klik di luar atau pindah fokus menutup. Isi selalu ada di DOM (tersembunyi secara visual saat tertutup)
// dan dirujuk lewat aria-describedby, jadi pembaca layar mendapat deskripsi tanpa membuka popover.
export function Hint({ id }: { id: string }) {
  const entry = getHint(id);
  const feats = useFeatures();
  const key = useId();
  const open = useOpenKey() === key;
  const wrap = useRef<HTMLSpanElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const [shift, setShift] = useState(0);

  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) dispatchOpen({ type: "close", key });
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("touchstart", away);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("touchstart", away);
    };
  }, [open, key]);
  useEffect(() => () => dispatchOpen({ type: "close", key }), [key]);

  // Jaga popover tetap di viewport (desktop); di layar sempit CSS membuatnya selebar kolom.
  useLayoutEffect(() => {
    if (!open || !pop.current) {
      setShift(0);
      return;
    }
    const r = pop.current.getBoundingClientRect();
    const over = r.right - (window.innerWidth - 8);
    setShift(over > 0 ? -over : r.left < 8 ? 8 - r.left : 0);
  }, [open]);

  if (!entry || !isEntryVisible(entry, feats)) return null;
  const bodyId = `hint-body-${key}`;
  return (
    <span
      className="hint"
      ref={wrap}
      onBlur={(e) => {
        if (!wrap.current?.contains(e.relatedTarget as Node | null)) dispatchOpen({ type: "close", key });
      }}
      onKeyDown={(e) => {
        const a = keyAction(e.key, key);
        if (a?.type === "close" && open) {
          e.stopPropagation();
          dispatchOpen(a);
          btn.current?.focus();
        }
      }}
    >
      <button
        ref={btn}
        type="button"
        className="hint-btn"
        aria-label={`About: ${entry.title}`}
        aria-expanded={open}
        aria-controls={bodyId}
        aria-describedby={bodyId}
        onClick={() => dispatchOpen({ type: "toggle", key })}
      >
        <span aria-hidden="true">i</span>
      </button>
      <div
        id={bodyId}
        ref={pop}
        role="group"
        className={open ? "hint-pop" : "hint-pop sr-only"}
        style={open && shift ? { transform: `translateX(${shift}px)` } : undefined}
      >
        <strong className="hint-title">{entry.title}</strong>
        <p className="hint-body">{entry.body}</p>
      </div>
    </span>
  );
}
