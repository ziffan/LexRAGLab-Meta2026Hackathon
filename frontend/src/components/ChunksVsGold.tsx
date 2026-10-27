import { retrievalKey, useStore } from "../state";
import { availableSettings, fixedFor } from "../lib/settings";
import { modeLabel, originLabel, settingLabel } from "../lib/labels";
import { ChunkColumn } from "./ChunkColumn";
import { ChunkDetail } from "./ChunkDetail";
import type { Chunk, Item } from "../types";

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
        <strong>{snapState.code === "unreachable" ? "Backend unreachable." : "Could not load the family snapshot."}</strong>
        <div>{snapState.message}</div>
      </div>
    );
  } else {
    const snap = snapState.data;
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
                  {i.id} · {modeLabel(i.mode)}
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
            <span>Compare with fixed-size</span>
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
      <h2 id="u1-title">Chunks vs gold</h2>
      {body}
    </section>
  );
}
