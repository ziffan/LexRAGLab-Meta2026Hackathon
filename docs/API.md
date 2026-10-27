# API — endpoint FastAPI

Tujuan: menetapkan endpoint backend yang melayani setiap panel `docs/UI-SPEC.md` dan mode putar ulang, dengan bentuk data merujuk `docs/DATA-CONTRACTS.md`.
Sumber keputusan: H-004, H-005, H-006, H-013, H-015, H-016, H-017, H-020, H-031, H-037, H-047, H-050, H-051, H-053, H-054, H-068.

Bentuk ini mengikuti H-020: endpoint baca dilebur menjadi snapshot per keluarga, endpoint tulis satu per aksi.

## 1. Aturan umum

- Backend listen di `127.0.0.1` saja. Tanpa auth (H-013), karena tidak di-deploy publik.
- Semua respons JSON. Galat berbentuk `{"error": {"code": "<code>", "message": "<message>"}}`, tanpa stack trace dan tanpa key.
- `{family}` bernilai `uupt` atau `akta` (H-031).
- Endpoint yang memanggil Spark ditandai **[Spark]**. Endpoint lain tidak pernah memanggil Model API.
- Frontend memegang snapshot (R3) di satu store (H-023) dan menurunkan isi setiap panel darinya. Setelah endpoint tulis berhasil, frontend memuat ulang snapshot keluarga itu.
- Mode putar ulang aktif bila backend dijalankan dengan flag replay di konfigurasi. Dalam replay, backend hanya membaca `runs/` dan `data/` (H-020, direvisi H-050). Semua respons membawa header `X-Replay: true|false`.
- Dalam replay, endpoint [Spark] mengembalikan run tersimpan dengan kunci cache yang sama. Bila tidak ada, galat `409 replay_no_stored_run`. Satu-satunya pengecualian: W6 dengan `live: true` untuk butir `scene_checked` boleh memanggil Spark di mode replay (satu panggilan live adegan 4, `docs/VIDEO.md`).
- Versi live (H-051) adalah ekspor statis mode putar ulang: frontend + snapshot JSON dari R3, R4, R5 yang dibutuhkan adegan, tanpa backend. Endpoint tulis dan panggilan live W6 tidak ada di versi statis; pilihan Glimmer di sana hanya menampilkan hasil yang sudah tersimpan (H-053).
- Endpoint [Spark] menolak dengan `402 budget_exceeded` bila proyeksi melewati `config/budget`.
- Kode galat lain: `400 invalid_request`, `404 not_found`, `409 hash_mismatch`, `409 invalid_transition`, `422 validation_failed`, `422 schema_invalid`, `500 storage_error` (H-068), `502 model_error`, `503 model_unavailable`.

## 2. Endpoint baca

| # | Metode dan jalur | Request | Response | Panel | Slice |
|---|---|---|---|---|---|
| R1 | `GET /api/health` | — | `{status, replay, model, config_hash, model_profiles: [{model_profile, model, available}]}` | U0, U3 | M0.1 |
| R2 | `GET /api/families` | — | `[{family, n_docs, n_items, has_grid}]` | U0 | M0.2 |
| R3 | `GET /api/families/{family}/snapshot` | query `budget_tokens` opsional (default dari `config/grid`) | `FamilySnapshot` (bagian 4) | U0–U9 | M0.2, diperluas tiap slice |
| R4 | `GET /api/families/{family}/docs/{doc_id}` | query `setting_id` opsional | `{doc_id, text, chunks: Chunk[] \| null, headers: HeaderB[] \| null}` (§3, §7) | U1, U6 | M1.1, M3.2 |
| R5 | `GET /api/families/{family}/retrieval` | query `setting_id`, `item_id` | `{retrieved_chunk_ids, ranks, scores, packed_tokens}` | U1 | M1.2 |
| R6 | `GET /api/runs` | query `kind`, `limit` | `RunRecord[]` (§12) | U8 | M0.1 |

R4 dan R5 dipisah dari snapshot karena teks dokumen dan ranking per butir per setting terlalu besar untuk dikirim sekaligus.

## 3. Endpoint tulis

| # | Metode dan jalur | Request | Response | Panel | Slice |
|---|---|---|---|---|---|
| W1 | `POST /api/families/{family}/grid/run` | `{budget_tokens: int \| null}` | `RunRecord` | U2 | M1.4 |
| W2 | `POST /api/families/{family}/schemas/induce` **[Spark]** | `{sample_doc_ids: string[]}` | `SchemaRecord` v baru + `RunRecord` (§6) | U5 | M3.3, M4.1 |
| W3 | `POST /api/families/{family}/headers/run` **[Spark]** | `{doc_id: string, granularity: "pasal" \| "ayat"}` | `{headers: HeaderB[], runs: RunRecord[], projection_usd_micros}` | U8 | M3.1 |
| W4 | `POST /api/families/{family}/proposals/generate` **[Spark]** | `{doc_id: string, modes: string[]}` | `ProposalRecord[]` (§9) + `RunRecord[]`, satu per mode yang dipanggil (H-068, M2.1 A23) | U6 | M2.1 |
| W5 | `POST /api/proposals/{proposal_id}/decision` | `{decision: "disetujui" \| "diubah" \| "ditolak", edited: object \| null, operator_note: string \| null}` | `ProposalRecord` + `Item` bila lahir | U6 | M2.1 |
| W6 | `POST /api/families/{family}/answers` **[Spark]** | `{item_id, best_setting_id, baseline_setting_id, model_profile: string, live: bool}` | `{best: AnswerRecord, baseline: AnswerRecord, verifier: VerifierResult[], runs: RunRecord[]}` (§8) | U3 | M2.2, M2.3, M2.5 (stretch) |
| W7 | `GET /api/families/{family}/profiles/export` | query `setting_id` | `Profile` (§11), header unduh | U7 | M4.3 |
| W8 | `POST /api/profiles/import` | `Profile` | `{ok: bool, chunk_set_hash_matches: bool}` atau `409 hash_mismatch` | U7 | M4.3 |
| W9 | `POST /api/families/{family}/schemas/{version}/correct` | `{schema: SchemaA, operator_note: string \| null}` | `SchemaRecord` versi baru | U5 | M3.3, M4.1 |

W7 adalah `GET` tetapi dikelompokkan di sini karena menghasilkan berkas keluaran.

## 4. FamilySnapshot

Gabungan kontrak yang sudah ada di `docs/DATA-CONTRACTS.md`. Bukan skema keluaran Spark, jadi aturan `strict` H-016 tidak berlaku. Bidang yang belum punya data bernilai `null` atau daftar kosong, dan frontend menampilkan keadaan "not run" (`docs/UI-SPEC.md` §5).

| Bidang | Isi | Kontrak | Panel |
|---|---|---|---|
| `family`, `budget_tokens`, `replay`, `config_hash` | identitas snapshot | — | U0 |
| `corpus` | dokumen keluarga | `CorpusDoc[]` (§2) | U0, U1 |
| `items` | butir yang disetujui, dengan asal, mode, split | `Item[]` (§4) | U1, U4 |
| `split` | penugasan tune/held-out; `null` untuk akta (H-054) | `SplitRecord` (§4) | U4 |
| `items_summary` | `{n_items, by_origin, by_mode, by_split, control_in_held_out}` | — | U9 |
| `settings` | semua setting grid | `Setting[]` (§10) | U2 |
| `grid` | `{tune: {points, frontier}, held_out: {points, frontier}}` pada `budget_tokens` | `GridPoint[]`, `Frontier` (§10) | U2 |
| `metrics` | per setting × butir, kedua split | `ItemMetrics[]` (§10) | U4 |
| `quality` | per setting | `QualityMetrics` (§10) | U4 |
| `schemas` | semua versi skema keluarga | `SchemaRecord[]` (§6) | U5 |
| `schema_diff` | versi Spark terbaru vs koreksi operator terbaru: `{changed: [{order, field, before, after}], boundary_diff: [{doc_id, only_schema, only_handwritten}]}` | — | U5 |
| `proposals` | semua usulan D | `ProposalRecord[]` (§9) | U6, U0 |
| `answers` | per butir dan per `model_profile` yang sudah dijawab: `{item_id, model_profile, best, baseline, verifier}` | `AnswerRecord`, `VerifierResult` (§8) | U3 |
| `answers_summary` | per setting dan per `model_profile` yang dipakai C | `RejectionSummary` (§8) | U3 |
| `runs_summary` | agregat per `kind`: jumlah run, token input/cached/output, biaya | — | U8, U0 |

## 5. Aturan per endpoint yang tidak terlihat dari tabel

- **R3** dibangun dari berkas dan cache per hash (`docs/ARCHITECTURE.md` §8). Ia tidak pernah menjalankan grid, chunker, atau Spark. Bila hasil grid belum ada untuk `budget_tokens` itu, `grid` bernilai `null`.
- **W1** tidak memanggil Spark. Hasil disimpan per kunci cache; kunci sama → respons `RunRecord.status = cached`.
- **W2** menyimpan v1 dari Spark. Koreksi operator (v2+) masuk lewat editor U5 dan W9 (H-037).
- **W9** tidak memanggil Spark. Skema divalidasi dengan JSON Schema yang sama dengan keluaran A; gagal → `422 schema_invalid`. Versi baru selalu dibuat, versi lama tidak ditimpa. Isi koreksi berasal dari operator; agen tidak mengisinya.
- **W3** menjalankan satu request pemanas, lalu panggilan per potongan dengan `prompt_cache_key` yang sama. Respons memuat proyeksi biaya korpus untuk granularitas yang diminta.
- **W5** hanya menerima transisi dari `usulan`. Transisi lain → `409 invalid_transition`. Usulan dengan `validation.text_matches = false` tidak boleh `disetujui`; jalurnya `diubah` dengan `edited`. Tafsir (H-068, M2.1 A8 I): `edited` hanya sah bersama `diubah`; `disetujui` + `edited` → `422 validation_failed`.
- **W4/W5 kode galat (H-068, M2.1 A7, A15, A17).** `decision` di luar enum (termasuk `usulan`, huruf besar, `null`, hilang) → `400 invalid_request`. `proposal_id` tak dikenal → `404 not_found`. Kunci tak dikenal, `edited` tidak cocok dengan `decision`, isi `edited` tidak sah, atau `disetujui` pada usulan `text_matches = false` → `422 validation_failed`. Keluaran Spark rusak (tidak sesuai skema `ProposalD`) di W4 → `502 model_error`, tanpa `ProposalRecord`. Kegagalan penyimpanan → `500 storage_error`; status usulan dan jumlah butir tidak berubah.
- **W6** memakai anggaran token dan instruksi yang sama untuk kedua slot. `tolak` dan `bukti_tidak_cukup` adalah respons `200`, bukan galat. Dalam replay, `live: true` hanya diterima untuk butir `scene_checked`; selain itu `409 replay_no_stored_run`.
- **W6** menjalankan uji 3 hanya bila tabel status versi `approved_by_operator = true` ada; selain itu `valid_on_date = tidak_dijalankan`.
- **W6** `model_profile` adalah kunci daftar model di `config/model` (H-053): profil Contributor (default) atau profil Glimmer lokal (stretch, H-047). Profil Glimmer memakai klien Chat Completions ke `127.0.0.1`, prompt dan anggaran yang sama, dan validasi skema di sisi klien. Bila server Glimmer lokal tidak hidup, W6 dengan profil itu mengembalikan `503 model_unavailable` dan R1 melaporkan `available = false`. Jawaban Glimmer disimpan sebagai run terpisah (`AnswerRecord.model_profile`, `RunRecord.provider`, `quantization`, `effort`) dan tidak pernah digabung dengan jawaban Contributor dalam satu tabel perbandingan tanpa label. Glimmer tidak dipakai di endpoint lain.
- **W7/W8** round-trip: memuat profil membangun ulang potongan dan membandingkan `chunk_set_hash`.

## 6. Contoh (placeholder)

`POST /api/proposals/<proposal_id>/decision`

```json
{
  "decision": "diubah",
  "edited": {"query": "<query>", "gold_spans": [{"start": 0, "end": 0}], "mode": "parafrase"},
  "operator_note": null
}
```

Galat replay:

```json
{"error": {"code": "replay_no_stored_run", "message": "No stored run for this request. Replay mode does not call the Model API."}}
```
