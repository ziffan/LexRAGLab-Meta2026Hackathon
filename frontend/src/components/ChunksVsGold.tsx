import { useEffect, useMemo, useState } from "react";
import { fetchDocBySchema } from "../api";
import { retrievalKey, useStore } from "../state";
import { availableSettings, fixedFor } from "../lib/settings";
import { Hint } from "./Hint";
import { truncate } from "../lib/format";
import { modeLabel, originLabel, settingLabel } from "../lib/labels";
import { ChunkColumn } from "./ChunkColumn";
import { ChunkDetail } from "./ChunkDetail";
import type { Chunk, DocResponse, Item, Load, Snapshot } from "../types";

/** Keluarga akta (tanpa setting/butir): akta terpotong menurut skema A tersimpan (R4 `schema_version`, M4.1). */
export function SchemaDocView({ snap }: { snap: Snapshot }) {
  const versions = (snap.schemas ?? []).map((r) => r.schema_version);
  const docIds = snap.corpus.map((d) => d.doc_id);
  const [docId, setDocId] = useState<string>(docIds[0] ?? "");
  const [version, setVersion] = useState<number | null>(versions.length ? versions[versions.length - 1] : null);
  const [doc, setDoc] = useState<Load<DocResponse>>({ status: "idle" });
  useEffect(() => {
    if (!docId || version === null) return;
    let live = true;
    setDoc({ status: "loading" });
    fetchDocBySchema(snap.family, docId, version)
      .then((data) => live && setDoc({ status: "ready", data }))
      .catch((e: { code?: string; message?: string }) => live && setDoc({ status: "error", code: e.code ?? "error", message: e.message ?? "Request failed." }));
    return () => {
      live = false;
    };
  }, [snap.family, docId, version]);
  const points = useMemo(() => (doc.status === "ready" ? Array.from(doc.data.text) : []), [doc]);
  if (versions.length === 0) return <div className="state empty">No schema for this family yet</div>;
  return (
    <>
      <div className="controls">
        <label className="field">
          <span>Document</span>
          <select value={docId} onChange={(e) => setDocId(e.target.value)}>
            {docIds.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Schema version</span>
          <select value={version ?? ""} onChange={(e) => setVersion(Number(e.target.value))}>
            {versions.map((v) => <option key={v} value={v}>v{v}</option>)}
          </select>
        </label>
      </div>
      {(doc.status === "idle" || doc.status === "loading") && <div className="state" role="status" aria-live="polite"><span className="muted">Loading chunks…</span></div>}
      {doc.status === "error" && <div className="state error" role="alert"><strong>Could not load chunks</strong><div>{doc.message}</div></div>}
      {doc.status === "ready" && (
        <ol className="chunks">
          {(doc.data.chunks ?? []).map((c) => (
            <li key={c.chunk_id} className="chunk">
              <div className="chunk-head"><span className="addr">{c.address}</span><span className="chunk-stats"><span>{c.tokens_local} tokens (local tokenizer)</span></span></div>
              <div className="chunk-text" lang="id" tabIndex={0} role="region" aria-label={`Text of ${c.address}`}>{points.slice(c.start, c.end).join("")}</div>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}

export function ChunksVsGold() {
  const { state, dispatch } = useStore();
  const snapState = state.snapshot;

  let body;
  if (snapState.status === "idle" || snapState.status === "loading") {
    body = (
      <div className="state" role="status" aria-live="polite">
        <div className="skeleton" />
        <div className="skeleton" />
        <div className="skeleton short" />
        <span className="muted">Loading items…</span>
      </div>
    );
  } else if (snapState.status === "error") {
    body = (
      <div className="state error" role="alert">
        <strong>{snapState.code === "unreachable" ? "Backend unreachable. Showing replay data if available." : "Could not load the family snapshot."}</strong>
        <div>{snapState.message}</div>
      </div>
    );
  } else {
    const snap = snapState.data;
    if (snap.family === "akta") {
      return (
        <section className="panel" aria-labelledby="u1-title">
          <div className="panel-head"><h2 id="u1-title">Chunks vs gold</h2><Hint id="term.pasal" /><Hint id="term.ayat" /></div>
          <SchemaDocView snap={snap} />
        </section>
      );
    }
    const item: Item | null = snap.items.find((i) => i.id === state.selectedItemId) ?? null;
    const settings = availableSettings(snap);
    const primary = settings.find((s) => s.setting_id === state.selectedSettingId) ?? settings[0];
    const fixed = fixedFor(snap, primary);
    const canCompare = !!fixed && primary?.setting_id !== fixed.setting_id;
    const showCompare = state.compare && canCompare && !!fixed;
    const cleanSha = snap.corpus[0]?.clean_sha256;
    const allChunks: Chunk[] = Object.values(state.docs).flatMap((d) => (d.status === "ready" ? d.data.chunks ?? [] : []));
    const selectedChunk = allChunks.find((c) => c.chunk_id === state.selectedChunkId) ?? null;
    const goldChars = item ? item.gold_spans.reduce((n, s) => n + (s.end - s.start), 0) : 0;

    body = (
      <>
        <div className="controls">
          <label className="field">
            <span>Item</span>
            <select value={state.selectedItemId ?? ""} onChange={(e) => dispatch({ type: "select_item", id: e.target.value || null })}>
              <option value="">Select an item…</option>
              {snap.items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.id} · {modeLabel(i.mode)} · {truncate(i.query, 60)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Setting</span>
            <select value={primary?.setting_id ?? ""} onChange={(e) => dispatch({ type: "select_setting", id: e.target.value })}>
              {settings.map((s) => (
                <option key={s.setting_id} value={s.setting_id}>
                  {settingLabel(s)}
                </option>
              ))}
            </select>
          </label>
          <label className="check" title={canCompare ? "" : "Select the structure setting to compare it with fixed-size"}>
            <input type="checkbox" checked={showCompare} disabled={!canCompare} onChange={(e) => dispatch({ type: "set_compare", value: e.target.checked })} />
            <span>Compare with fixed-size</span><Hint id="chunker.fixed_size" />
          </label>
        </div>

        {item ? (
          <div className="item-card">
            <div className="item-query" lang="id">
              {item.query}
            </div>
            <div className="item-meta">
              <span>{originLabel(item.origin)}</span>
              <span>{modeLabel(item.mode)}</span>
              <span>
                Gold span:{" "}
                {item.gold_spans.length === 0
                  ? "none (must abstain)"
                  : `${item.gold_spans.length} span${item.gold_spans.length > 1 ? "s" : ""}, ${goldChars} characters`}
              </span>
              <span className="legend">
                <mark>Gold span</mark> is highlighted below
              </span>
            </div>
          </div>
        ) : (
          <div className="state empty">Select an item to see chunk boundaries</div>
        )}

        {item && primary && (
          <div className={`columns${showCompare ? " two" : ""}`}>
            <ChunkColumn
              heading={showCompare ? "Selected setting" : "Chunks"}
              setting={primary}
              doc={state.docs[primary.setting_id] ?? { status: "idle" }}
              retrieval={state.retrievals[retrievalKey(primary.setting_id, item.id)] ?? { status: "idle" }}
              item={item}
              cleanSha256={cleanSha}
            />
            {showCompare && fixed && (
              <ChunkColumn
                heading="Compare with fixed-size"
                setting={fixed}
                doc={state.docs[fixed.setting_id] ?? { status: "idle" }}
                retrieval={state.retrievals[retrievalKey(fixed.setting_id, item.id)] ?? { status: "idle" }}
                item={item}
                cleanSha256={cleanSha}
              />
            )}
          </div>
        )}

        <h3 className="detail-title">Chunk detail</h3>
        <ChunkDetail chunk={selectedChunk} />
      </>
    );
  }

  return (
    <section className="panel" aria-labelledby="u1-title">
      <div className="panel-head"><h2 id="u1-title">Chunks vs gold</h2><Hint id="term.gold_span" /><Hint id="term.pasal" /><Hint id="term.ayat" /><Hint id="term.penjelasan" /></div>
      {body}
    </section>
  );
}
