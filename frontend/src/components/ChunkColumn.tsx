import { useMemo } from "react";
import { useStore } from "../state";
import type { Chunk, DocResponse, Item, Load, Setting } from "../types";
import { edgeSplit, offsetsMatch, pieces, splitSpans, visibleChunks } from "../lib/gold";
import { settingLabel } from "../lib/labels";

interface Props {
  setting: Setting;
  doc: Load<DocResponse>;
  item: Item | null;
  cleanSha256: string | undefined;
  heading: string;
}

export function ChunkColumn({ setting, doc, item, cleanSha256, heading }: Props) {
  return (
    <section className="column" aria-label={heading}>
      <h3 className="column-title">
        {heading}: <span className="muted">{settingLabel(setting)}</span>
      </h3>
      <ColumnBody doc={doc} item={item} cleanSha256={cleanSha256} />
    </section>
  );
}

function ColumnBody({ doc, item, cleanSha256 }: { doc: Load<DocResponse>; item: Item | null; cleanSha256: string | undefined }) {
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
  return <ReadyColumn doc={doc.data} item={item} cleanSha256={cleanSha256} />;
}

function ReadyColumn({ doc, item, cleanSha256 }: { doc: DocResponse; item: Item | null; cleanSha256: string | undefined }) {
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
  const split = splitSpans(chunks, item.gold_spans);
  const shown = visibleChunks(chunks, item.gold_spans);
  return (
    <div>
      <p className="column-meta">
        <span>{chunks.length} chunks in this setting</span>
        {split.length > 0 ? <span className="tag split">Gold split across chunks</span> : <span className="tag ok">Gold span inside one chunk</span>}
      </p>
      <ol className="chunks">
        {shown.map((c) => (
          <ChunkCard
            key={c.chunk_id}
            chunk={c}
            parts={pieces(codePoints, c, item.gold_spans)}
            edges={edgeSplit(c, split)}
            selected={state.selectedChunkId === c.chunk_id}
            onSelect={() => dispatch({ type: "select_chunk", id: c.chunk_id })}
          />
        ))}
      </ol>
    </div>
  );
}

function ChunkCard({ chunk, parts, edges, selected, onSelect }: {
  chunk: Chunk;
  parts: { text: string; gold: boolean }[];
  edges: { top: boolean; bottom: boolean };
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li className={`chunk${selected ? " selected" : ""}`}>
      {edges.top && <div className="split-edge top">Gold split across chunks</div>}
      <div className="chunk-head">
        <button type="button" className="addr" onClick={onSelect} aria-pressed={selected}>
          {chunk.address}
        </button>
        <span className="chunk-stats">
          <span>{chunk.tokens_local} tokens (local tokenizer)</span>
          <span className="rank" title="Retrieval rank appears here from M1.2">Retrieved # —</span>
        </span>
      </div>
      <div className="chunk-text" tabIndex={0} role="region" aria-label={`Text of ${chunk.address}`}>
        {parts.map((p, i) => (p.gold ? <mark key={i} title="Gold span">{p.text}</mark> : <span key={i}>{p.text}</span>))}
      </div>
      {edges.bottom && <div className="split-edge bottom">Gold split across chunks</div>}
    </li>
  );
}
