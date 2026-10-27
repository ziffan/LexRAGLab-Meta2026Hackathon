import { useEffect, useId, useRef, useState } from "react";
import { HINT_FILE, glossaryGroups, introEntries, isDraft, useFeatures } from "../lib/hints";

// Panel About / Glossary (docs/UI-SPEC.md §9.2): dialog non-modal. Fokus pindah ke judul saat dibuka;
// Esc menutup dan mengembalikan fokus ke tombol. Isi: tujuan, target, frontier, replay, glosarium (dapat dicari).
export function AboutPanel() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const feats = useFeatures();
  const title = useRef<HTMLHeadingElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const uid = useId();
  const titleId = `about-title-${uid}`;
  const panelId = `about-panel-${uid}`;
  useEffect(() => {
    if (open) title.current?.focus();
  }, [open]);
  const close = () => {
    setOpen(false);
    btn.current?.focus();
  };
  const groups = glossaryGroups(q, feats);
  return (
    <>
      <button ref={btn} type="button" className="about-btn" aria-expanded={open} aria-controls={panelId} onClick={() => (open ? close() : setOpen(true))}>
        About / Glossary
      </button>
      {open && (
        <aside
          id={panelId}
          className="about-panel"
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              close();
            }
          }}
        >
          <div className="about-head">
            <h2 id={titleId} ref={title} tabIndex={-1}>About / Glossary</h2>
            <button type="button" onClick={close}>Close</button>
          </div>
          {isDraft() && <p className="note">Hint text: draft (content v{HINT_FILE.version}, status {HINT_FILE.status})</p>}
          {introEntries().map((e) => (
            <section key={e.id} className="about-sec" aria-labelledby={`${titleId}-${e.id}`}>
              <h3 id={`${titleId}-${e.id}`}>{e.title}</h3>
              <p>{e.body}</p>
            </section>
          ))}
          <h3 className="about-gloss">Glossary</h3>
          <label className="field">
            <span>Search glossary</span>
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
          <div role="status" aria-live="polite" className="sr-only">{groups.reduce((n, g) => n + g.entries.length, 0)} entries shown</div>
          {groups.length === 0 && <p className="muted">No glossary entries match.</p>}
          {groups.map((g) => (
            <section key={g.prefix} aria-labelledby={`${titleId}-g-${g.prefix}`}>
              <h4 id={`${titleId}-g-${g.prefix}`} className="about-group">{g.label}</h4>
              <dl className="about-dl">
                {g.entries.map((e) => (
                  <div key={e.id}>
                    <dt>{e.title}</dt>
                    <dd>{e.body}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </aside>
      )}
    </>
  );
}
