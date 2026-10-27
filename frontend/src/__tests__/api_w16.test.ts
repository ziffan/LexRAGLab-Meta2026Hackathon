// W16: URL dan metode klien API tanpa jaringan (fetch suntikan / fetch global yang di-stub).
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchDocBySchema, fetchProfileExport, postProfileImport, type FetchLike } from "../api";

afterEach(() => vi.unstubAllGlobals());

function spy(body: unknown = { ok: true }) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const f: FetchLike = async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify(body), { status: 200 });
  };
  return { f, calls };
}

describe("W7/W8 profil", () => {
  it("fetchProfileExport: GET /api/families/{f}/profiles/export?setting_id= (di-encode)", async () => {
    const { f, calls } = spy({ profile_version: "1" });
    expect(await fetchProfileExport("uupt", "SID a/b#1", f)).toEqual({ profile_version: "1" });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/families/uupt/profiles/export?setting_id=SID%20a%2Fb%231");
    expect(calls[0].init?.method ?? "GET").toBe("GET");
  });
  it("postProfileImport: POST /api/profiles/import dengan badan JSON profil", async () => {
    const { f, calls } = spy({ ok: true, chunk_set_hash_matches: true });
    const profile = { profile_version: "1", family: "uupt" };
    await postProfileImport(profile, f);
    expect(calls[0].url).toBe("/api/profiles/import");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual(profile);
  });
});

describe("R4 schema_version", () => {
  it("fetchDocBySchema: GET /api/families/{f}/docs/{id}?schema_version=n", async () => {
    const { f, calls } = spy({ doc_id: "akta-01", text: "x", chunks: [], headers: null });
    vi.stubGlobal("fetch", (u: string, i?: RequestInit) => f(u, i));
    await fetchDocBySchema("akta", "akta-01", 3);
    expect(calls[0].url).toBe("/api/families/akta/docs/akta-01?schema_version=3");
    expect(calls[0].init?.method ?? "GET").toBe("GET");
  });
});
