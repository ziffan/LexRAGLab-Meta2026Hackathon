import { staticAwareFetch } from "./lib/staticData";
import type { AnswersResponse, DocResponse, Health, ImportResult, Profile, Retrieval, RunRecord, SchemaRecord, Snapshot } from "./types";

export class ApiFailure extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

/** `fetch` yang dapat disuntikkan (test memakai fetch palsu; tanpa jaringan). */
export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

/** Satu-satunya jalur jaringan UI: di ekspor statis (H-051) `/api/...` dibaca dari berkas statis dan tulis ditolak. */
export const apiFetch: FetchLike = (u, i) => staticAwareFetch((x, y) => fetch(x, y))(u, i);

async function requestJson<T>(url: string, init?: RequestInit, fetchFn: FetchLike = (u, i) => fetch(u, i)): Promise<T> {
  let res: Response;
  try {
    res = await staticAwareFetch(fetchFn)(url, init);
  } catch {
    throw new ApiFailure("unreachable", "Backend unreachable.");
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    const e = (body as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiFailure(e?.code ?? `http_${res.status}`, e?.message ?? res.statusText);
  }
  return body as T;
}

const getJson = <T>(url: string): Promise<T> => requestJson<T>(url);
const postJson = <T>(url: string, body: unknown, fetchFn?: FetchLike): Promise<T> =>
  requestJson<T>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, fetchFn);

export function fetchSnapshot(family: string, budget: number | null = null): Promise<Snapshot> {
  const q = budget ? `?budget_tokens=${budget}` : "";
  return getJson<Snapshot>(`/api/families/${encodeURIComponent(family)}/snapshot${q}`);
}

export function fetchRetrieval(family: string, settingId: string, itemId: string): Promise<Retrieval> {
  return getJson<Retrieval>(
    `/api/families/${encodeURIComponent(family)}/retrieval?setting_id=${encodeURIComponent(settingId)}&item_id=${encodeURIComponent(itemId)}`,
  );
}

export function fetchDoc(family: string, docId: string, settingId: string): Promise<DocResponse> {
  return getJson<DocResponse>(
    `/api/families/${encodeURIComponent(family)}/docs/${encodeURIComponent(docId)}?setting_id=${encodeURIComponent(settingId)}`,
  );
}

/** R4 menurut versi skema A tersimpan (keluarga akta; usulan API.md §2). */
export function fetchDocBySchema(family: string, docId: string, schemaVersion: number): Promise<DocResponse> {
  return getJson<DocResponse>(
    `/api/families/${encodeURIComponent(family)}/docs/${encodeURIComponent(docId)}?schema_version=${schemaVersion}`,
  );
}

export function fetchHealth(): Promise<Health> {
  return getJson<Health>("/api/health");
}

export function fetchRuns(limit = 500): Promise<RunRecord[]> {
  return getJson<RunRecord[]>(`/api/runs?limit=${limit}`);
}

export interface AnswersRequest {
  item_id: string;
  best_setting_id: string;
  baseline_setting_id: string;
  model_profile: string | null;
  live: boolean;
}

/** W6. `live: false` hanya membaca run tersimpan. */
export function postAnswers(family: string, req: AnswersRequest, fetchFn?: FetchLike): Promise<AnswersResponse> {
  return postJson<AnswersResponse>(`/api/families/${encodeURIComponent(family)}/answers`, req, fetchFn);
}

/** W9: versi koreksi baru dari versi induk. Isi `schema` berasal dari form operator. */
export function postCorrection(family: string, parentVersion: number, schema: unknown, operatorNote: string | null, fetchFn?: FetchLike): Promise<SchemaRecord> {
  return postJson<SchemaRecord>(`/api/families/${encodeURIComponent(family)}/schemas/${parentVersion}/correct`, { schema, operator_note: operatorNote }, fetchFn);
}

/** W7: profil setting terpilih. Dibaca di browser dan diunduh di sana; frontend tidak menulis `profiles/`. */
export function fetchProfileExport(family: string, settingId: string, fetchFn?: FetchLike): Promise<Profile> {
  return requestJson<Profile>(`/api/families/${encodeURIComponent(family)}/profiles/export?setting_id=${encodeURIComponent(settingId)}`, undefined, fetchFn);
}

/** W8: round-trip profil (tidak menulis apa pun di server). */
export function postProfileImport(profile: unknown, fetchFn?: FetchLike): Promise<ImportResult> {
  return postJson<ImportResult>("/api/profiles/import", profile, fetchFn);
}
