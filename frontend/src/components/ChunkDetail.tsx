import { sectionLabel } from "../lib/labels";
import type { Chunk } from "../types";

export function ChunkDetail({ chunk }: { chunk: Chunk | null }) {
  if (!chunk) return <div className="state empty detail">Click a chunk address to see its details</div>;
  return (
    <dl className="detail" aria-label="Chunk detail">
      <div>
        <dt>Address</dt>
        <dd className="mono">{chunk.address}</dd>
      </div>
      <div>
        <dt>Section</dt>
        <dd>{sectionLabel[chunk.section] ?? chunk.section}</dd>
      </div>
      <div>
        <dt>Offsets</dt>
        <dd className="mono">[{chunk.start}, {chunk.end}) code points</dd>
      </div>
      <div>
        <dt>tokens (local tokenizer)</dt>
        <dd>{chunk.tokens_local}</dd>
      </div>
      <div>
        <dt>Retrieved #</dt>
        <dd className="muted">not run (retrieval arrives in a later slice)</dd>
      </div>
      <div>
        <dt>Warnings</dt>
        <dd>{chunk.warnings.length ? chunk.warnings.join("; ") : "none"}</dd>
      </div>
    </dl>
  );
}
