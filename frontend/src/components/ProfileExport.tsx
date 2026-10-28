import { useEffect, useRef, useState } from "react";
import { ApiFailure, fetchProfileExport, postProfileImport } from "../api";
import { fixed3, mean2, orNa, xOfY } from "../lib/format";
import { modeLabel, retrievalModeLabel } from "../lib/labels";
import { DEGENERATE_NOTE, TRANSFER_LABEL, hasDegenerate } from "../lib/settings";
import { STATIC_DISABLED, isStatic } from "../lib/staticData";
import { useStore } from "../state";
import type { ImportResult, Profile, Report, Snapshot, TransferSetting } from "../types";
import { Hint } from "./Hint";
import { EmptyBlock, ErrorBlock, LoadingBlock, PendingReview, isPendingReview } from "./Shell";

// U7 Export profile (docs/UI-SPEC.md U7; docs/scenarios/M4.3.md S20). Logika di fungsi murni dengan klien suntikan
// (tanpa jaringan di test); `ProfileView` murni (props); `ProfilePanel` menyambung store dan peramban.
// Frontend tidak menulis `profiles/`: profil dari W7 diunduh sebagai berkas di peramban.

export const EMPTY_TEXT = "Select a setting on the frontier to export";
export const BUILDING_TEXT = "Building profile…";
export const REPLAY_TEXT = "Replay mode: profile export and loading are disabled.";
export const CORPUS_MISMATCH_TEXT = "Profile corpus hash does not match loaded corpus";
export const CHUNK_MATCH_TEXT = "chunk hash matches source run";
export const CHUNK_MISMATCH_TEXT = "Chunk hash does not match source run";
export const NOT_JSON_TEXT = "Could not read profile file: it is not a JSON object. Nothing was sent.";

export const STATIC_PROFILE_NOTE = "Static replay: read-only preview of the stored profile. Download JSON saves it in your browser.";
export const STATIC_PROFILE_MISSING = "The static export includes the stored profile of the selected setting only (Company Law: best profile; Deed: transfer setting).";

export const TITLE_UUPT = "Held-out results";
export const TITLE_AKTA = "Transfer results";

export interface U7Client {
  exportProfile(family: string, settingId: string): Promise<Profile>;
  importProfile(profile: unknown): Promise<ImportResult>;
}

export const liveClient: U7Client = {
  exportProfile: (f, s) => fetchProfileExport(f, s),
  importProfile: (p) => postProfileImport(p),
};

export type ExportPhase =
  | { kind: "idle" }
  | { kind: "building" }
  | { kind: "ready"; profile: Profile }
  | { kind: "error"; message: string };

export type LoadPhase =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "match" }
  | { kind: "chunk_mismatch" }
  | { kind: "rejected"; message: string }
  | { kind: "local_error"; message: string }
  | { kind: "error"; message: string };

const messageOf = (e: unknown): { code: string; message: string } =>
  e instanceof ApiFailure ? { code: e.code, message: e.message } : { code: "unknown", message: "Unexpected error." };

/** Alasan tombol nonaktif; urutan: statis, replay, tanpa setting. `null` = boleh jalan. */
export function disabledReason(args: { staticMode: boolean; replay: boolean; settingId: string | null }): string | null {
  if (args.staticMode) return STATIC_DISABLED;
  if (args.replay) return REPLAY_TEXT;
  if (!args.settingId) return EMPTY_TEXT;
  return null;
}

export const profileFileName = (family: string, settingId: string): string => `profile-${family}-${settingId.slice(0, 12)}.json`;

/** Ekspor W7. Tanpa setting: tidak ada permintaan. */
export async function runExport(client: U7Client, family: string, settingId: string | null, set: (p: ExportPhase) => void): Promise<ExportPhase> {
  if (!settingId) {
    const p: ExportPhase = { kind: "idle" };
    set(p);
    return p;
  }
  set({ kind: "building" });
  let out: ExportPhase;
  try {
    const profile = await client.exportProfile(family, settingId);
    out = profile && typeof profile === "object" ? { kind: "ready", profile } : { kind: "error", message: "Could not build profile: unexpected response." };
  } catch (e) {
    out = { kind: "error", message: `Could not build profile: ${messageOf(e).message}` };
  }
  set(out);
  return out;
}

/** Penjaga permintaan terbaru: hasil permintaan lama (sebelum `bump`, mis. setting berganti) diabaikan. */
export interface RequestGuard {
  /** Mulai permintaan baru; mengembalikan ID-nya dan membuat semua ID sebelumnya basi. */
  begin(): number;
  /** Batalkan semua permintaan yang berjalan (mis. pilihan berganti). */
  invalidate(): void;
  isCurrent(id: number): boolean;
}

export function createRequestGuard(): RequestGuard {
  let latest = 0;
  return {
    begin: () => ++latest,
    invalidate: () => {
      latest += 1;
    },
    isCurrent: (id) => id === latest,
  };
}

/** Ekspor yang hasilnya hanya diterapkan (set dan unduh) bila permintaannya masih yang terbaru. */
export async function runGuardedExport(
  guard: RequestGuard, client: U7Client, family: string, settingId: string | null,
  set: (p: ExportPhase) => void, onReady: (profile: Profile) => void,
): Promise<ExportPhase> {
  const id = guard.begin();
  const out = await runExport(client, family, settingId, (p) => {
    if (guard.isCurrent(id)) set(p);
  });
  if (out.kind === "ready" && guard.isCurrent(id)) onReady(out.profile);
  return out;
}

/** Muat berkas profil lalu round-trip W8. Berkas bukan objek JSON: galat lokal, W8 tidak dipanggil. */
export async function runLoad(client: U7Client, text: string, set: (p: LoadPhase) => void): Promise<LoadPhase> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = undefined;
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    const p: LoadPhase = { kind: "local_error", message: NOT_JSON_TEXT };
    set(p);
    return p;
  }
  set({ kind: "checking" });
  let out: LoadPhase;
  try {
    const r = await client.importProfile(parsed);
    out = r.ok === true && r.chunk_set_hash_matches === true ? { kind: "match" } : { kind: "chunk_mismatch" };
  } catch (e) {
    const { code, message } = messageOf(e);
    if (code === "hash_mismatch") out = { kind: "rejected", message: message.includes(CORPUS_MISMATCH_TEXT) ? message : `${CORPUS_MISMATCH_TEXT}. ${message}` };
    else out = { kind: "error", message: `Could not load profile: ${message}` };
  }
  set(out);
  return out;
}

/** Unduh JSON di peramban (Blob + tautan). Tidak menulis ke server. */
export function downloadJson(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const pretty = (p: Profile): string => JSON.stringify(p, null, 2);

function HeldOutSummary({ profile }: { profile: Profile }) {
  const h = profile.held_out;
  if (!h) return null;
  return (
    <dl className="kv">
      <dt>Items</dt><dd>{h.n_items}</dd>
      <dt>Fully covered</dt><dd>{xOfY(h.fully_covered.covered, h.fully_covered.total, "items with gold")}</dd>
      <dt>Mean span recall</dt><dd>{mean2(h.mean_span_recall)}</dd>
      <dt>Mean token precision</dt><dd>{orNa(h.mean_token_precision, fixed3)}</dd>
      <dt>By origin</dt><dd>{Object.entries(h.by_origin).map(([k, v]) => `${k}: ${v}`).join(", ") || "n/a"}</dd>
    </dl>
  );
}

/** Teks setting transfer akta (H-091): chunker structure_schema + mode retrieval + header B + anggaran dari profil terbaik UU PT. */
export function transferText(t: TransferSetting): string {
  return `Structure (schema A${t.schema_version !== null ? ` v${t.schema_version}` : ""}) · ${retrievalModeLabel(t.retrieval_mode)} · header B ${t.header_b ? "on" : "off"} · ${t.budget_tokens} tokens (local tokenizer)`;
}

export function ReportTable({ report }: { report: Report }) {
  return (
    <div className="table-wrap">
      <table className="data">
        <caption className="cap">{report.title}: {xOfY(report.summary.fully_covered.numerator, report.summary.fully_covered.denominator, "items fully covered")}</caption>
        <thead>
          <tr><th scope="col">Item</th><th scope="col">Split</th><th scope="col">Origin</th><th scope="col">Mode</th><th scope="col">Span recall</th><th scope="col">Token precision</th></tr>
        </thead>
        <tbody>
          {report.rows.map((r) => (
            <tr key={r.item_id}>
              <td className="mono">{r.item_id}</td><td>{r.split}</td><td>{r.origin}</td><td>{modeLabel(r.mode)}</td>
              <td>{r.span_recall ? r.span_recall.text : "n/a"}</td>
              <td>{r.token_precision ? r.token_precision.text : "n/a"}{r.note ? ` (${r.note})` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Bagian hasil. UU PT: `Held-out results` setelah ekspor. Akta: `Transfer results`, tanpa kata held-out (H-054, A15). */
export function ResultsSection({ family, profile, report, degenerate = false }: { family: string; profile: Profile | null; report: Report | null; degenerate?: boolean }) {
  const akta = family === "akta";
  if (!akta && !profile) return null;
  return (
    <section className="subpanel" aria-label={akta ? TITLE_AKTA : TITLE_UUPT}>
      <h3>{akta ? TITLE_AKTA : TITLE_UUPT}{akta ? <><span className="tag neutral">Transfer test</span><Hint id="metric.transfer_test" /></> : <Hint id="metric.tune_heldout" />}</h3>
      {!akta && profile && <HeldOutSummary profile={profile} />}
      {akta && report?.setting && (
        <p className="note" data-testid="transfer-setting">
          <span className="tag neutral">{report.setting.label || TRANSFER_LABEL}</span> Reported setting: <strong>{transferText(report.setting)}</strong>. Its retrieval mode, header B and budget come from the best Company Law profile; nothing is chosen from the deeds.
        </p>
      )}
      {akta && degenerate && <p className="note" data-testid="degenerate-note">{DEGENERATE_NOTE}</p>}
      {report ? <ReportTable report={report} /> : akta ? <EmptyBlock>No per-item transfer report is included in this snapshot.</EmptyBlock> : null}
    </section>
  );
}

function LoadResult({ phase }: { phase: LoadPhase }) {
  switch (phase.kind) {
    case "idle":
      return null;
    case "checking":
      return <LoadingBlock text="Checking profile…" />;
    case "match":
      return <div className="tag ok" role="status">Profile loaded: {CHUNK_MATCH_TEXT}.</div>;
    case "chunk_mismatch":
      return <div className="state error" role="alert"><strong>{CHUNK_MISMATCH_TEXT}.</strong> The profile was not reproduced from the loaded corpus.</div>;
    case "rejected":
      return <ErrorBlock title={CORPUS_MISMATCH_TEXT} message={phase.message === CORPUS_MISMATCH_TEXT ? undefined : phase.message} />;
    case "local_error":
    case "error":
      return <ErrorBlock title={phase.message} />;
  }
}

export interface ProfileViewProps {
  family: string;
  settingId: string | null;
  disabled: string | null;
  exportPhase: ExportPhase;
  loadPhase: LoadPhase;
  report: Report | null;
  /** Akta: ada titik structure_handwritten berlabel "no structure recognized" (H-093). */
  degenerate?: boolean;
  onExport: () => void;
  onFile: (file: File) => void;
  onDownload: (profile: Profile) => void;
  /** Statis (UX-09): catatan di atas pratinjau baca-saja, atau alasan tidak ada profil. */
  staticNote?: string | null;
}

export function ProfileView(p: ProfileViewProps) {
  const input = useRef<HTMLInputElement>(null);
  const busy = p.exportPhase.kind === "building" || p.loadPhase.kind === "checking";
  const off = p.disabled !== null || busy;
  return (
    <>
      <div className="controls">
        <button type="button" disabled={off || !p.settingId} title={p.disabled ?? undefined} onClick={p.onExport}>Export profile</button>
        <button type="button" disabled={p.disabled !== null || busy} title={p.disabled ?? undefined} onClick={() => input.current?.click()}>Load profile</button>
        <input
          ref={input}
          type="file"
          accept="application/json,.json"
          hidden
          aria-label="Profile file"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) p.onFile(f);
          }}
        />
        {p.disabled && <span className="note">{p.disabled}</span>}
      </div>
      {p.staticNote && <p className="note" data-testid="static-profile-note">{p.staticNote}</p>}
      {p.exportPhase.kind === "idle" && !p.disabled && !p.settingId && <EmptyBlock>{EMPTY_TEXT}</EmptyBlock>}
      {p.exportPhase.kind === "building" && <LoadingBlock text={BUILDING_TEXT} />}
      {p.exportPhase.kind === "error" && <ErrorBlock title={p.exportPhase.message} />}
      {p.exportPhase.kind === "ready" && (
        <>
          <dl className="kv">
            <dt>Profile version</dt><dd className="mono">{p.exportPhase.profile.profile_version}</dd>
            <dt>Corpus hash</dt><dd className="mono">{p.exportPhase.profile.corpus_hash}</dd>
          </dl>
          <div className="card-actions">
            <button type="button" onClick={() => p.onDownload((p.exportPhase as { profile: Profile }).profile)}>Download JSON</button>
          </div>
          <pre className="mono profile-preview" tabIndex={0} aria-label="Profile JSON preview" style={{ maxHeight: 320, overflow: "auto" }}>{pretty(p.exportPhase.profile)}</pre>
        </>
      )}
      <ResultsSection family={p.family} profile={p.exportPhase.kind === "ready" ? p.exportPhase.profile : null} report={p.report} degenerate={p.degenerate} />
      <LoadResult phase={p.loadPhase} />
    </>
  );
}

export function ProfilePanel({ client = liveClient }: { client?: U7Client }) {
  const { state } = useStore();
  const [exportPhase, setExportPhase] = useState<ExportPhase>({ kind: "idle" });
  const [loadPhase, setLoadPhase] = useState<LoadPhase>({ kind: "idle" });
  const snap: Snapshot | null = state.snapshot.status === "ready" ? state.snapshot.data : null;

  const settingId = snap ? state.selectedSettingId : null;
  // Hasil ekspor milik satu (keluarga, setting); ganti pilihan membuang pratinjau lama.
  const guard = useRef<RequestGuard>(null as unknown as RequestGuard);
  if (!guard.current) guard.current = createRequestGuard();
  useEffect(() => {
    guard.current.invalidate(); // respons ekspor yang masih terbang milik pilihan lama
    setExportPhase({ kind: "idle" });
    setLoadPhase({ kind: "idle" });
  }, [state.family, settingId]);
  const disabled = disabledReason({ staticMode: isStatic(), replay: snap?.replay === true, settingId });
  // UX-09: di ekspor statis, profil tersimpan setting terpilih dibaca otomatis (berkas statis, GET saja) untuk pratinjau + Download JSON.
  const [staticMissing, setStaticMissing] = useState(false);
  useEffect(() => {
    setStaticMissing(false);
    if (!isStatic() || !settingId || state.snapshot.status !== "ready") return;
    const fam = state.family;
    void runGuardedExport(guard.current, client, fam, settingId, (ph) => {
      if (ph.kind === "error") {
        setStaticMissing(true);
        setExportPhase({ kind: "idle" });
      } else setExportPhase(ph);
    }, () => undefined);
  }, [state.family, settingId, state.snapshot.status, client]);
  const staticNote = !isStatic() ? null : staticMissing ? STATIC_PROFILE_MISSING : exportPhase.kind === "ready" ? STATIC_PROFILE_NOTE : null;

  let body;
  if (state.snapshot.status === "idle" || state.snapshot.status === "loading") body = <LoadingBlock text="Loading snapshot…" />;
  else if (state.snapshot.status === "error") body = <ErrorBlock title="Profile export unavailable: could not load the family snapshot." message={state.snapshot.message} />;
  else if (snap && isPendingReview(snap)) body = <PendingReview />;
  else
    body = (
      <ProfileView
        family={state.family}
        settingId={settingId}
        disabled={disabled}
        exportPhase={exportPhase}
        loadPhase={loadPhase}
        report={snap?.report ?? null}
        degenerate={snap ? hasDegenerate(snap) : false}
        staticNote={staticNote}
        onExport={() => {
          const fam = state.family;
          void runGuardedExport(guard.current, client, fam, settingId, setExportPhase, (pr) => {
            if (settingId) downloadJson(profileFileName(fam, settingId), pretty(pr));
          });
        }}
        onFile={(f) => {
          setLoadPhase({ kind: "checking" });
          void f.text().then((t) => runLoad(client, t, setLoadPhase), () => setLoadPhase({ kind: "local_error", message: NOT_JSON_TEXT }));
        }}
        onDownload={(pr) => downloadJson(profileFileName(pr.family, pr.setting.setting_id), pretty(pr))}
      />
    );
  return (
    <section className="panel" aria-labelledby="u7-title" id="export">
      <div className="panel-head"><h2 id="u7-title">Export profile</h2></div>
      {body}
    </section>
  );
}
