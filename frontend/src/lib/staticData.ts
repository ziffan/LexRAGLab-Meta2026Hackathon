// Mode ekspor statis (H-051, docs/UI-SPEC.md §4): tanpa backend, key, atau panggilan model. Permintaan `/api/...` dipetakan ke
// berkas JSON di `data/` (ditulis `backend/replay/export.py`; tata letak di docstring modul itu). Tulis dan W6 `live` ditolak
// di sini, sebelum jaringan, dengan teks "Static replay: live calls are disabled".

export type RawFetch = (url: string, init?: RequestInit) => Promise<Response>;

export const STATIC_DISABLED = "Static replay: live calls are disabled";
export const SID_LEN = 16; // awalan setting_id di jalur berkas (sama dengan backend/replay/export.py)
const DATA = "data"; // relatif terhadap halaman (base "./"), supaya jalan di sub-jalur GitHub Pages

let staticOn = import.meta.env.VITE_STATIC === "1";
/** Tombol uji: nyalakan/matikan mode statis tanpa membangun ulang. */
export function setStaticMode(v: boolean): void {
  staticOn = v;
}
export const isStatic = (): boolean => staticOn;

const sid = (id: string): string => id.slice(0, SID_LEN);
const enc = encodeURIComponent;

export type StaticTarget =
  | { kind: "file"; path: string }
  | { kind: "doc"; text: string; setting: string | null }
  | { kind: "answer"; path: string }
  | { kind: "blocked" }
  | { kind: "unknown" };

/** Petakan satu permintaan API ke berkas statis. Fungsi murni (diuji tanpa jaringan). */
export function resolveStatic(url: string, init?: RequestInit): StaticTarget {
  const method = (init?.method ?? "GET").toUpperCase();
  const [path, query = ""] = url.split("?");
  const q = new URLSearchParams(query);
  const seg = path.replace(/^\/api\//, "").split("/").map(decodeURIComponent);
  if (method !== "GET") {
    if (method === "POST" && seg[0] === "families" && seg[2] === "answers") {
      let body: { item_id?: string; best_setting_id?: string; baseline_setting_id?: string; model_profile?: string | null; live?: boolean } = {};
      try {
        body = JSON.parse(String(init?.body ?? "{}"));
      } catch {
        return { kind: "unknown" };
      }
      if (body.live) return { kind: "blocked" };
      if (!body.item_id || !body.best_setting_id || !body.baseline_setting_id || !body.model_profile) return { kind: "unknown" };
      return { kind: "answer", path: `${DATA}/answers/${enc(seg[1])}/${enc(body.item_id)}/${sid(body.best_setting_id)}/${sid(body.baseline_setting_id)}/${enc(body.model_profile)}.json` };
    }
    return { kind: "blocked" };
  }
  if (seg[0] === "health" && seg.length === 1) return { kind: "file", path: `${DATA}/health.json` };
  if (seg[0] === "runs" && seg.length === 1) return { kind: "file", path: `${DATA}/runs.json` };
  if (seg[0] === "families" && seg.length === 1) return { kind: "file", path: `${DATA}/families.json` };
  if (seg[0] === "families" && seg.length >= 3) {
    const fam = enc(seg[1]);
    if (seg[2] === "snapshot" && seg.length === 3) {
      const b = q.get("budget_tokens");
      return { kind: "file", path: `${DATA}/snapshot/${fam}/${b && /^\d+$/.test(b) ? b : "default"}.json` };
    }
    if (seg[2] === "proposals" && seg.length === 3) return { kind: "file", path: `${DATA}/proposals/${fam}.json` };
    if (seg[2] === "profiles" && seg[3] === "export" && seg.length === 4) {
      // UX-09: profil tersimpan setting terpilih/transfer (berkas statis, baca-saja); setting lain -> 404 dari berkas yang tak ada
      const s = q.get("setting_id");
      return s ? { kind: "file", path: `${DATA}/profiles/${fam}/${sid(s)}.json` } : { kind: "unknown" };
    }
    if (seg[2] === "docs" && seg.length === 4) {
      const doc = `${DATA}/docs/${fam}/${enc(seg[3])}`;
      const s = q.get("setting_id");
      const v = q.get("schema_version");
      if (v !== null && !/^\d+$/.test(v)) return { kind: "unknown" };
      return { kind: "doc", text: `${doc}/_text.json`, setting: v !== null ? `${doc}/schema-v${v}.json` : s ? `${doc}/${sid(s)}.json` : null };
    }
    if (seg[2] === "retrieval" && seg.length === 3) {
      const s = q.get("setting_id");
      const i = q.get("item_id");
      if (s && i) return { kind: "file", path: `${DATA}/retrieval/${fam}/${sid(s)}/${enc(i)}.json` };
    }
  }
  return { kind: "unknown" };
}

const errorResponse = (status: number, code: string, message: string): Response =>
  new Response(JSON.stringify({ error: { code, message } }), { status, headers: { "Content-Type": "application/json" } });

async function readJson(raw: RawFetch, path: string): Promise<unknown | undefined> {
  let res: Response;
  try {
    res = await raw(path);
  } catch {
    return undefined;
  }
  if (!res.ok) return undefined;
  try {
    return JSON.parse(await res.text()); // server dev dengan fallback SPA mengembalikan HTML: dianggap tidak ada
  } catch {
    return undefined;
  }
}

const jsonResponse = (data: unknown): Response => new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json", "X-Replay": "true" } });

/** Bungkus fetch: di mode statis, tidak ada permintaan `/api` yang lolos ke `raw`; di mode live diteruskan apa adanya. */
export function staticAwareFetch(raw: RawFetch, on: () => boolean = isStatic): RawFetch {
  return async (url, init) => {
    if (!on() || !url.startsWith("/api/")) return raw(url, init);
    const t = resolveStatic(url, init);
    if (t.kind === "blocked") return errorResponse(403, "static_replay", STATIC_DISABLED);
    if (t.kind === "unknown") return errorResponse(404, "not_found", "Not available in the static export.");
    if (t.kind === "doc") {
      const text = (await readJson(raw, t.text)) as Record<string, unknown> | undefined;
      if (!text) return errorResponse(404, "not_found", "Not available in the static export.");
      if (t.setting === null) return jsonResponse(text);
      const part = (await readJson(raw, t.setting)) as Record<string, unknown> | undefined;
      if (!part) return errorResponse(404, "not_found", "Not available in the static export.");
      return jsonResponse({ ...text, chunks: part.chunks ?? null, headers: part.headers ?? null });
    }
    const data = await readJson(raw, t.path);
    if (data === undefined) {
      if (t.kind === "answer") return errorResponse(409, "replay_no_stored_run", "No stored run for this request. Replay mode does not call the Model API.");
      return errorResponse(404, "not_found", "Not available in the static export.");
    }
    return jsonResponse(data);
  };
}
