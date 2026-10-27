import type { DocResponse, Snapshot } from "./types";

export class ApiFailure extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function getJson<T>(url: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url);
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

export function fetchSnapshot(family: string): Promise<Snapshot> {
  return getJson<Snapshot>(`/api/families/${encodeURIComponent(family)}/snapshot`);
}

export function fetchDoc(family: string, docId: string, settingId: string): Promise<DocResponse> {
  return getJson<DocResponse>(
    `/api/families/${encodeURIComponent(family)}/docs/${encodeURIComponent(docId)}?setting_id=${encodeURIComponent(settingId)}`,
  );
}
