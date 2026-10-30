import { useEffect, useMemo, useRef } from "react";
import { useStore } from "../state";
import type { Chunk, DocResponse, Item, Load, Retrieval, Setting } from "../types";
import { edgeSplit, offsetsMatch, pieces, splitSpans, visibleChunks } from "../lib/gold";
import { settingLabel } from "../lib/labels";
import { rankMap } from "../lib/settings";

interface Props {
  setting: Setting;
  doc: Load<DocResponse>;
  retrieval: Load<Retrieval>;
  item: Item | null;
  cleanSha256: string | undefined;
  heading: string;
}

export function ChunkColumn({ setting, doc, retrieval, item, cleanSha256, heading }: Props) {
  return (
    <section className="column" aria-label={heading}>
      <h3 className="column-title">
        {heading}: <span className="muted">{settingLabel(setting)}</span>
      </h3>
      <ColumnBody doc={doc} retrieval={retrieval} item={item} cleanSha256={cleanSha256} />
    </section>
  );
}

function ColumnBody({ doc, retrieval, item, cleanSha256 }: { doc: Load<DocResponse>; retrieval: Load<Retrieval>; item: Item | null; cleanSha256: string | undefined }) {
  if (doc.status === "idle" || doc.status === "loading") {
    return (
      <div className="state" role="status" aria-live="polite">
        <div className="skeleton" />
        <div className="skeleton" />
        <div className="skeleton short" />
        <span className="muted">Loading chunks…</span>
      </div>
    );
  }
  if (doc.status === "error") {
    const mismatch = doc.code === "validation_failed";
    return (
      <div className="state error" role="alert">
        <strong>{mismatch ? "Chunk offsets do not match source text" : "Could not load chunks"}</strong>
        <div>{doc.message}</div>
      </div>
    );
  }
  return <ReadyColumn doc={doc.data} retrieval={retrieval} item={item} cleanSha256={cleanSha256} />;
}

function ReadyColumn({ doc, retrieval, item, cleanSha256 }: { doc: DocResponse; retrieval: Load<Retrieval>; item: Item | null; cleanSha256: string | undefined }) {
  const { state, dispatch } = useStore();
  const codePoints = useMemo(() => Array.from(doc.text), [doc.text]);
  const chunks = doc.chunks ?? [];
  const ok = doc.chunks !== null && offsetsMatch(chunks, codePoints.length, cleanSha256);
  if (!ok) {
    return (
      <div className="state error" role="alert">
        <strong>Chunk offsets do not match source text</strong>
        <div>The chunk set cannot be mapped back onto the source text, so it is not shown.</div>
      </div>
    );
  }
  if (!item) return <div className="state empty">Select an item to see chunk boundaries</div>;
  if (item.gold_spans.length === 0) {
    return <div className="state empty">No gold (must abstain). This item has no gold span, so there is nothing to highlight.</div>;
  }
  const ranks = retrieval.status === "ready" ? rankMap(retrieval.data) : null;
  const headerOf = new Map((doc.headers ?? []).map((h) => [h.chunk_id, h.header]));
  const split = splitSpans(chunks, item.gold_spans);
  const shown = visibleChunks(chunks, item.gold_spans);
  return (
    <div>
      <p className="column-meta">
        <span>{chunks.length} chunks in this setting</span>
        {split.length > 0 ? <span className="tag split">Gold split across chunks</span> : <span className="tag ok">Gold span inside one chunk</span>}
      </p>
      {retrieval.status === "loading" && (
        <p className="muted" role="status">
          Computing retrieval for this item…
        </p>
      )}
      {retrieval.status === "error" && (
        <p className="state error" role="alert">
          Retrieval unavailable: {retrieval.message}
        </p>
      )}
      <ol className="chunks">
        {shown.map((c) => (
          <ChunkCard
            key={c.chunk_id}
            chunk={c}
            header={headerOf.get(c.chunk_id) ?? null}
            parts={pieces(codePoints, c, item.gold_spans)}
            edges={edgeSplit(c, split)}
            rank={ranks ? (ranks.get(c.chunk_id) ?? null) : undefined}
            selected={state.selectedChunkId === c.chunk_id}
            onSelect={() => dispatch({ type: "select_chunk", id: c.chunk_id })}
          />
        ))}
      </ol>
    </div>
  );
}

function ChunkCard({ chunk, header, parts, edges, rank, selected, onSelect }: {
  chunk: Chunk;
  header: string | null;
  parts: { text: string; gold: boolean }[];
  edges: { top: boolean; bottom: boolean };
  rank: number | null | undefined; // undefined = belum dimuat, null = tidak terambil dalam anggaran
  selected: boolean;
  onSelect: () => void;
}) {
  // UX-15: kotak teks bergulir sendiri; gulir ke awal gold supaya titik belah terlihat tanpa menggulir manual.
  const box = useRef<HTMLDivElement>(null);
  const goldKey = parts.map((p) => (p.gold ? "g" : "t") + p.text.length).join(",");
  useEffect(() => {
    const el = box.current;
    const mark = el?.querySelector("mark");
    if (!el || !(mark instanceof HTMLElement) || el.scrollHeight <= el.clientHeight) return;
    el.scrollTop = Math.max(0, mark.offsetTop - 8);
  }, [goldKey]);
  return (
    <li className={`chunk${selected ? " selected" : ""}`}>
      {edges.top && <div className="split-edge top">Gold split across chunks</div>}
      {header !== null && (
        <div className="chunk-header-b">
          <span className="chunk-header-label">Context header (B)</span> {header}
        </div>
      )}
      <div className="chunk-head">
        <button type="button" className="addr" onClick={onSelect} aria-pressed={selected}>
          {chunk.address}
        </button>
        <span className="chunk-stats">
          <span>{chunk.tokens_local} tokens (local tokenizer)</span>
          {rank !== undefined && <span className={`rank${rank === null ? "" : " hit"}`}>{rank === null ? "Not retrieved" : `Retrieved #${rank}`}</span>}
        </span>
      </div>
      <div ref={box} className="chunk-text" tabIndex={0} role="region" aria-label={`Text of ${chunk.address}`}>
        {parts.map((p, i) => (p.gold ? <mark key={i} title="Gold span">{p.text}</mark> : <span key={i}>{p.text}</span>))}
      </div>
      {edges.bottom && <div className="split-edge bottom">Gold split across chunks</div>}
    </li>
  );
}
