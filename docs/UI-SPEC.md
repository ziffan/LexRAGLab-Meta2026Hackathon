# UI-SPEC — satu halaman tiga panel dan layar Review

Tujuan: menetapkan setiap komponen layar, datanya, interaksinya, keadaannya, label Inggrisnya, dan adegan video yang memakainya, sebagai sumber tunggal mockup dan frontend.
Sumber keputusan: H-004, H-005, H-006, H-009, H-012, H-014, H-015, H-017, H-018, H-020, H-023, H-028, H-031, H-037, H-046, H-047, H-050, H-051, H-053, H-054, H-055, H-073.

## 1. Aturan umum

- Label, tombol, tooltip, dan pesan UI **HARUS** bahasa Inggris (H-018). Teks hukum tetap bahasa Indonesia, tanpa diterjemahkan.
- Enum data tetap seperti di `docs/DATA-CONTRACTS.md` (mis. `jawab`, `tolak`). UI **HARUS** memetakannya ke label Inggris lewat tabel di bagian 6.
- Angka token **HARUS** diberi label "local tokenizer" (H-014). Biaya **HARUS** berasal dari `usage` Spark, bukan tokenizer lokal.
- Hitungan ditampilkan mentah ("7 of 12"), bukan persen, tanpa klaim signifikansi (H-005, `docs/VIDEO.md`).
- Angka yang dilaporkan sebagai hasil **HARUS** dari split held-out. Angka tune boleh tampil, dengan label "tune".
- Setiap panel punya tiga keadaan wajib: loading, empty, error. Teksnya di bagian 5.
- Frontend tidak memanggil Model API langsung. Semua lewat backend (`docs/API.md`).
- Resolusi rekam 1920×1080 dengan zoom browser 125–150% (`docs/VIDEO.md`). Tata letak **HARUS** tetap terbaca di lebar efektif 1280–1536 px (turunan: 1920 dibagi zoom 1,5 dan 1,25; pilihan desain).
- Tanpa emoji. Kontras teks minimal 4,5:1 (pilihan desain: ambang WCAG AA untuk teks normal). Semua kontrol adalah tombol/elemen form asli dengan label yang bisa dibaca screen reader.
- Penjelasan istilah lewat hint dan panel About / Glossary (bagian 9, H-073); teksnya bukan literal di komponen.

## 2. Tata letak

```
+----------------------------------------------------------------------------------+
| U0 Header: LexRAGLab | Family [UU PT|Deed] | Profile | Model | Run cost | REPLAY    |
+--------------------------+-----------------------------+-------------------------+
| U1 Chunks vs gold        | U2 Setting space            | U3 End-to-end evidence  |
|  item picker             |  Pareto frontier            |  Best profile | Baseline|
|  document with chunk     |  (span recall vs tokens)    |  status, answer,        |
|  boundaries, gold span   |  series: header B on / off  |  citations + checks     |
|                          |  budget picker, split toggle|  cost                   |
+--------------------------+-----------------------------+-------------------------+
| U4 Per-item results (table, filter by origin / mode / split)                     |
+------------------------------------------+---------------------------------------+
| U5 Structure schema (A): v1 Spark vs v2  | U7 Export profile                     |
|    operator correction, boundary diff    | U8 Run log & cost                     |
+------------------------------------------+---------------------------------------+
| U9 Footer: item provenance line · Disclaimer "Research demo. Not legal advice."  |
+----------------------------------------------------------------------------------+
```

Layar terpisah: **U6 Review** (`/review`), untuk operator memeriksa usulan D. Tidak tampil di halaman utama kecuali lewat tautan "Review proposals" di U0.

State bersama (dipegang satu store di frontend, `useReducer` + context, H-023): `family`, `selectedSettingId`, `selectedItemId`, `budget`, `split` (`tune`/`held_out`), `filters` (origin, mode), `replay` (bool). Klik titik di U2 mengubah `selectedSettingId`; U1, U3, U4 ikut berubah.

## 3. Komponen

### U0 — Header

| Aspek | Isi |
|---|---|
| Data | `Profile` aktif (§11), `RunRecord` agregat (§12), daftar keluarga dari `GET /api/families` |
| Tampil | Nama app "LexRAGLab"; pemilih keluarga; nama setting terpilih (mis. "structure · hybrid · header on"); model ID dari `RunRecord` (`muse-spark-1.3-contributor`, H-028); total biaya run tersimpan; lencana "REPLAY" saat mode putar ulang; tautan "Review proposals ({n} pending)" |
| Interaksi | Ganti keluarga → semua panel memuat ulang untuk keluarga itu. Klik lencana biaya → gulir ke U8 |
| Loading / empty / error | Skeleton teks / "No family loaded" / "Backend unreachable. Showing replay data if available." |
| Label | `Family`, `Company Law (UU 40/2007)` (nilai `family` = `uupt`), `Deed (synthetic)` (`akta`), `Selected setting`, `Model`, `Run cost`, `REPLAY`, `Review proposals` |
| Adegan video | Semua adegan (bingkai tetap) |

### U1 — Chunks vs gold

| Aspek | Isi |
|---|---|
| Data | `CorpusDoc` (§2) teks sumber, `Chunk[]` (§3) dari setting terpilih, `Item` (§4) terpilih dengan `gold_spans`, `HeaderB` (§7) bila header on |
| Tampil | Pemilih butir (query teks, asal, mode, split). Teks dokumen dengan batas potongan sebagai garis tipis dan label alamat kanonik dengan bagian (`<peraturan> › Pasal <n> › ayat (<m>)`, atau `<peraturan> › Penjelasan › Pasal <n> › Ayat (<m>)`, `docs/DATA-CONTRACTS.md` §2). Span gold disorot. Potongan yang terambil dalam anggaran diberi tanda "retrieved #rank". Bila gold terbelah dua potongan, kedua batas diberi tanda "gold split". Header B tampil sebagai baris abu di atas potongan |
| Interaksi | Pilih butir. Toggle "Compare with fixed-size" menampilkan dua kolom (setting terpilih vs ukuran tetap pembanding). Klik potongan → detail (alamat, token local tokenizer, rank, skor) |
| Loading / empty / error | Skeleton baris / "Select an item to see chunk boundaries" / "Chunk offsets do not match source text" (offset tidak cocok adalah error, bukan peringatan) |
| Label | `Chunks vs gold`, `Item`, `Gold span`, `Retrieved #`, `Gold split across chunks`, `Context header (B)`, `Compare with fixed-size`, `tokens (local tokenizer)` |
| Adegan video | 0 (ukuran tetap membelah ayat), 1 (pindah ke profil struktur), 3 (potongan akta) |

### U2 — Setting space (Pareto frontier)

| Aspek | Isi |
|---|---|
| Data | `GridPoint[]` dan `Frontier` (§10) per keluarga, split, dan anggaran |
| Tampil | Sumbu X: tokens (local tokenizer) yang dipakai, sampai anggaran. Sumbu Y: span recall. Setiap titik = satu `Setting`. Titik frontier dihubungkan garis. Dua deret warna: header B off, header B on (H-012). Bentuk penanda per chunker (structure-handwritten, structure-schema-A, fixed-size). Tooltip: setting, span recall, token precision, MRR, hitungan "{x} of {y} items fully covered" (`fully_covered_count`) |
| Interaksi | Klik titik → `selectedSettingId`. Pemilih anggaran (default 2.000, pembanding dari konfigurasi). Toggle split `Tune` / `Held-out` (default held-out untuk laporan, tune untuk pemilihan; label jelas). Toggle seri header B (tampilan saja). Frontier dihitung gabungan lintas deret header on/off (satu garis; header B adalah salah satu sumbu setting, H-058), bukan per deret (I-48). Filter asal/mode berbagi state dengan U4 |
| Loading / empty / error | Skeleton sumbu / "No grid run for this family yet" / "Grid run failed: {message}" |
| Akta (H-054, H-091, H-093) | Keluarga Deed tidak punya split: toggle `Tune` / `Held-out` disembunyikan; satu frontier (`grid.all`, 36 titik pada dua anggaran) diberi label "transfer test, no profile selection" dan tidak ada penanda profil terpilih. Setting transfer (`grid.transfer`) dipilih-awal dan disebut di catatan. Titik `structure_handwritten` tetap digambar dan berlabel "no structure recognized" (1 potongan per akta): di tooltip, di detail setting terpilih, dan di catatan di bawah legenda. Banner "Pending operator review" menggantikan isi U2/U4/U7 selama `grid.final` bukan `true` (tanpa angka sementara); banner hilang sendiri saat `grid_run_id` di `config/akta_grid_final.toml` = kunci amplop grid akta tersimpan (diisi operator/L2, UI tidak memutus "final") |
| Catatan potong (H-017) | Kalau header B hanya untuk setting di frontier, deret "header on" hanya punya titik itu, dengan catatan "header B computed for frontier settings only". Kalau frontier akta dipotong, U2 untuk Deed tampil empty dengan "Deed frontier not run (scope cut)" |
| Label | `Setting space`, `Span recall`, `Tokens (local tokenizer)`, `Token budget`, `Tune`, `Held-out`, `Header B off`, `Header B on`, `Frontier`, `Dominated` |
| Adegan video | 1 (frontier UU PT, dua titik disorot), 2 (deret header B on vs off, filter parafrase) |

### U3 — End-to-end evidence (peran C)

| Aspek | Isi |
|---|---|
| Data | `AnswerRecord` (§8, keluaran Spark `AnswerC`) untuk butir terpilih × {profil terbaik, profil pembanding} × `model_profile`, `VerifierResult` (§8), `RunRecord` (§12) per panggilan, daftar profil model dan ketersediaannya dari R1 |
| Tampil | Dua kolom "Best profile" dan "Baseline". Per kolom: setting, status (label Inggris), jawaban (teks Indonesia, dengan gloss Inggris singkat bila tersedia dari operator), daftar kutipan berisi alamat + teks + tanda uji: `Exists` (uji 1), `Faithful` (uji 2), `Valid on date` (uji 3, stretch). Biaya panggilan dan token input/cached/output; token input aktual ditampilkan per kolom (dari `usage`), terpisah dari anggaran konteks yang sama untuk kedua kolom (anggaran = teks sumber, label alamat tidak dihitung, H-066). Setiap jawaban diberi label model, kuantisasi, dan effort (H-053) |
| Pemilih model (H-053) | Pemilih `Model` di atas dua kolom: `muse-spark-1.3-contributor` (default) dan `Muse Glimmer (local, open-weight)` (stretch). Ganti model memuat jawaban tersimpan untuk model itu; jawaban kedua model tidak pernah dicampur dalam satu ringkasan 2×2 tanpa label. Bila server Glimmer lokal tidak hidup, pilihan itu nonaktif dengan teks "Local Glimmer server not running". Di replay statis (H-051), pilihan Glimmer hanya menampilkan hasil tersimpan |
| Interaksi | Tombol "Run live" hanya aktif untuk butir `scene_checked`, baik di mode live maupun replay (pengecualian replay di bagian 4 dan `docs/API.md` §1). Tombol "Open evidence detail" membuka tampilan lebar (artboard Evidence) dengan ringkasan 2×2 |
| Ringkasan 2×2 | Per profil: `Answered, supported` · `Answered, unsupported` · `Abstained, correctly` · `Abstained, should have answered`, dalam hitungan mentah |
| Loading / empty / error | "Waiting for Muse Spark…" dengan waktu berjalan / "No end-to-end run for this item" / "Model call failed: {message}. Showing last stored run." |
| Uji 3 dipotong | Kolom `Valid on date` tampil abu dengan "stretch — not run" |
| Alasan `Not run` uji 3 (H-068) | `tidak_dijalankan` tampil sebagai `Not run`, bukan `Revoked`, dengan alasan bila tersedia: stretch mati, tabel belum disetujui, `reference_date` kosong, `reference_date` sebelum `effective_from` (U3-A), uji `Exists` gagal (U5), dokumen di luar tabel atau butir akta (U6). Teks alasan Inggris, bentuk akhir ditetapkan saat implementasi M2.4 |
| Label | `End-to-end evidence`, `Model`, `Quantization`, `Effort`, `Muse Glimmer (local, open-weight)`, `Best profile`, `Baseline`, `Answer`, `Citations`, `Exists`, `Faithful`, `Valid on date`, `Pass`, `Fail`, `Conditional`, `Abstained`, `Insufficient evidence`, `Run live` |
| Adegan video | 4 |

### U4 — Per-item results

| Aspek | Isi |
|---|---|
| Data | `ItemMetrics[]` (§10) untuk setting terpilih dan pembanding, `Item` (§4) |
| Kolom | Item id, query (dipotong), origin, mode, split (Deed: `Transfer`, H-054), span recall, token precision, reciprocal rank, Recall@K, catatan "no gold (must abstain)" |
| Interaksi | Filter origin (`Operator-written` / `Spark-proposed, approved`), mode (`Literal` / `Paraphrase`), split. Klik baris → `selectedItemId`. Baris ringkas di atas tabel: hasil per asal dalam hitungan mentah |
| Panel metrik janji form | Di bawah tabel, tiga angka untuk setting terpilih vs ukuran tetap: `Recall@K`, `Entity preservation`, `Boundary coherence` (US-04). Angka `Recall@K` dihitung atas butir held-out saja (H-065); panel menampilkan label cakupan butir `held-out` atau `tune` sesuai `config/retrieval` `[quality].recall_items`. Penyebut nol tampil `n/a` (H-059) |
| Loading / empty / error | Skeleton baris / "No approved items for this family yet" / "Metrics unavailable: {message}" |
| Label | `Per-item results`, `Origin`, `Mode`, `Split`, `Span recall`, `Token precision`, `Reciprocal rank`, `Recall@K`, `Entity preservation`, `Boundary coherence`, `No gold (must abstain)` |
| Adegan video | 1, 2 (filter parafrase) |

### U5 — Structure schema (peran A)

| Aspek | Isi |
|---|---|
| Data | `SchemaA` (§6) v1 (Spark) dan v2 (koreksi operator) per keluarga, ringkasan selisih batas chunker skema vs parser tulisan tangan (UU PT) |
| Tampil | Dua kolom: "v1 · proposed by Muse Spark" dan "v2 · operator correction". Per level: urutan, nama level, pola penanda, contoh, unit potong default. Baris yang berubah diberi tanda diff (tambah/hapus/ubah). Di UU PT: tabel "boundary differences vs handwritten parser" per bagian (batang tubuh, Penjelasan) |
| Interaksi | Pilih versi aktif untuk chunker. Operator mengedit level di kolom koreksi (editor), lalu `Save as new version` memanggil W9 dan membuat versi baru; versi lama tidak ditimpa (H-037). Galat validasi tampil per field |
| Fallback (H-055) | Bila pemicu 31 Okt H-017 aktif, editor tidak dibangun: koreksi operator masuk sebagai berkas berversi, dan U5 hanya menampilkan diff v1 vs versi koreksi (read-only) |
| Loading / empty / error | Skeleton / "No schema induced for this family yet" / "Schema failed validation: {message}" |
| Label | `Structure schema (A)`, `Proposed by Muse Spark`, `Operator correction`, `Level`, `Marker pattern`, `Example`, `Default chunk unit`, `Changed lines`, `Edit`, `Save as new version`, `Boundary differences vs handwritten parser` |
| Adegan video | 3 |

### U6 — Review proposals (peran D), layar terpisah

| Aspek | Isi |
|---|---|
| Data | `ProposalRecord` (§9) yang `review_status`-nya `usulan`, `CorpusDoc` (§2) untuk konteks span |
| Tampil | Antrean usulan dengan penghitung. Per usulan: query, mode (`Literal`/`Paraphrase`), dokumen, teks span disorot di dalam konteks beberapa baris sebelum/sesudah, validasi otomatis ("offset found", "text matches") |
| Interaksi | Tombol `Approve`, `Edit`, `Reject`. `Edit` membuka form query dan pemilih span (seleksi teks di konteks). Catatan operator opsional. Pintasan papan ketik A/E/R dengan konfirmasi untuk Reject |
| Aturan | Tidak ada jalur dari usulan ke evaluasi tanpa keputusan operator (H-006). Usulan dengan validasi span gagal tidak bisa di-Approve, hanya Edit atau Reject |
| Loading / empty / error | Skeleton kartu / "No pending proposals" / "Could not save decision: {message}. Nothing was changed." |
| Keluarga | Pemilih `Family` (label sama dengan U0) di header layar; keluarga dari query `?family=` (`uupt` \| `akta`, lainnya jatuh ke `uupt`). Ganti pilihan memperbarui `?family=` (replaceState) dan memuat ulang antrean; tautan "Review proposals" di U0 membawa keluarga aktif |
| Label | `Review proposals`, `Pending`, `Approve`, `Edit`, `Reject`, `Literal`, `Paraphrase`, `Span`, `Offset found`, `Text matches`, `Operator note` |
| Adegan video | 2 (sekilas, menunjukkan butir parafrase disetujui operator) |

**Kartu usulan `unanswerable` (keluarga `akta`; H-087, H-092; skenario `docs/scenarios/M2.1-unanswerable.md` SU19, P14).** Rekaman `body.mode = "unanswerable"` memakai kartu berbeda; kartu `literal`/`parafrase` tidak berubah.

| Aspek | Isi |
|---|---|
| Tampil | Mode `Unanswerable`, query, dokumen. `Reason`: peta `alasan_kode` (`data_tidak_dimuat` = `Data not included`, `di_luar_akta` = `Outside the deed`, `rincian_tidak_diatur` = `Detail not regulated`) diikuti teks alasan. Lencana `Doubtful` (warna fail/oranye, bukan merah) bila `absence_check.status = doubtful`, dengan `Why flagged:` (`lexical_overlap` = `Shares distinctive terms with the deed`, `dense_similar` = `Semantically close passage`, `no_distinctive_terms` = `No distinctive terms`, `dense_unavailable` = `Semantic check unavailable`). Daftar `Closest passages` dari `absence_check.top_k` (sumber `BM25`/`Dense`, rank, teks unit). Status `ok`: tanpa lencana. Tanpa sorotan span, tanpa baris `Span`, `Offset found`, `Text matches` |
| Lencana lain | `Duplicate of an existing proposal` bila `duplicate_of` tidak null (P14; informasional, tidak memblokir). `Check settings changed` bila `absence_check.config_hash` berbeda dari `check_config_hash` sekarang yang dilaporkan server pada daftar usulan (SU9; tidak tampil bila server tidak melaporkannya) |
| Interaksi | `Approve` tetap aktif walau `Doubtful` (P3; `validation` null tidak memblokir). `Edit` membuka form query saja (tanpa pemilih mode dan span); kiriman W5 `diubah` membawa `edited = {query, gold_spans: [], mode: "tolak"}`. `Reject` dengan konfirmasi seperti biasa |
| Penghitung | Di atas antrean (hanya bila keluarga punya rekaman `unanswerable`): `Pending N`; `Must-refuse approved: n` (status `disetujui`/`diubah` saja) atau `No must-refuse item approved yet` bila 0; daftar per akta (`doc_id`) `{doc_id}: n approved` dengan petunjuk `(target: at least 1)` bila 0 (H-087). Informasional, bukan gerbang |
| Enum | `Item.mode` ∈ {`literal`, `parafrase`, `tolak`}; label UI `tolak` = `Must refuse`. Filter `Mode` di U4 menampilkan `Must refuse` hanya bila ada butir `tolak`. Opsi mode `unanswerable` tidak ada di U6 `uupt` |
| Label | `Unanswerable`, `Must refuse`, `Reason`, `Doubtful`, `Why flagged`, `Closest passages`, `Duplicate of an existing proposal`, `Check settings changed`, `Must-refuse approved`, `No must-refuse item approved yet` |

### U7 — Export profile

| Aspek | Isi |
|---|---|
| Data | `Profile` (§11) dari setting terpilih, metrik held-out |
| Tampil | Pratinjau JSON profil terformat, versi, hash korpus, metrik held-out dalam hitungan mentah |
| Interaksi | `Export profile` mengunduh berkas. `Load profile` memuat berkas; hasil round-trip ditampilkan ("chunk hash matches source run" atau penolakan hash korpus) |
| Loading / empty / error | "Building profile…" / "Select a setting on the frontier to export" / "Profile corpus hash does not match loaded corpus" |
| Akta (H-091, H-093) | Bagian `Transfer results` menyorot `report.setting` berlabel "transfer test, no profile selection": chunker `structure_schema` (skema A akta aktif) + mode retrieval, header B, dan anggaran dari profil terbaik UU PT pada anggaran yang sama. Tabel per butir memuat butir `tolak` ("Must refuse") dengan kolom metrik `n/a`. Catatan label degenerate "no structure recognized" bila grid memuat titik `structure_handwritten` |
| Label | `Export profile`, `Load profile`, `Profile version`, `Corpus hash`, `Held-out results` (UU PT); `Transfer results` (akta, tanpa kata held-out, H-054). Pesan round-trip tidak cocok: `Chunk hash does not match source run` (H-068, M4.3 A19) |
| Adegan video | 5 |

### U8 — Run log & cost

| Aspek | Isi |
|---|---|
| Data | `RunRecord[]` (§12) |
| Tampil | Tabel per panggilan atau run grid: waktu (UTC), peran (A/B/C/D/grid), model, effort, versi prompt, hash konfigurasi, token input / cached / output, biaya, latensi. Baris agregat per peran |
| Interaksi | Filter per peran. Klik baris → detail JSON catatan run |
| Loading / empty / error | Skeleton / "No runs recorded" / "Run log unreadable: {message}" |
| Label | `Run log & cost`, `Role`, `Effort`, `Prompt version`, `Input tokens`, `Cached tokens`, `Output tokens`, `Cost (USD)`, `Latency` |
| Adegan video | 2 (cached tokens dan biaya B) |

### U9 — Footer

| Aspek | Isi |
|---|---|
| Data | `items_summary` dari R3 (`docs/API.md` §4) |
| Tampil | Baris provenance: "{n} items: {a} operator-written, {b} Spark-proposed and operator-approved" (`docs/VIDEO.md`). Disclaimer tetap: "Research demo. Not legal advice." Model: "Built with muse-spark-1.3 (Contributor)" |
| Keadaan | Selalu tampil, termasuk saat error panel lain |
| Adegan video | 1 atau 5 (baris provenance), 5 (disclaimer) |

## 4. Mode putar ulang dan live

- Mode putar ulang (default saat demo): semua panel dibaca dari `runs/` dan `data/` (H-050) lewat endpoint yang sama, dengan header respons `X-Replay: true`. Lencana "REPLAY" tampil di U0.
- Versi live di GitHub Pages (H-051) adalah ekspor statis mode putar ulang: tanpa backend, tanpa key, tanpa panggilan model. Pemilih `Family` (U0) tampil bila `data/families.json` (R2 terbatas pada UU PT dan keluarga yang punya amplop grid tersimpan, H-091) memuat lebih dari satu keluarga; selain itu hanya label keluarga. Tombol "Run live" dan endpoint tulis (W1–W9) nonaktif dengan teks "Static replay: live calls are disabled".
- Satu panggilan live boleh di adegan 4 (W6, `docs/VIDEO.md`). Tombol "Run live" hanya aktif untuk butir yang ditandai `scene_checked` oleh operator.
- Dengan API diputus, semua adegan tetap bisa diputar (kriteria M5.1).

## 5. Keadaan global

| Keadaan | Kapan | Tampilan |
|---|---|---|
| Loading | Endpoint belum menjawab | Skeleton per panel; panel lain tetap interaktif |
| Empty | Data untuk keluarga atau setting belum ada | Teks empty per komponen (bagian 3) + langkah berikutnya bila relevan |
| Error | Endpoint gagal atau data tidak valid | Banner merah di panel terkait dengan pesan; tidak ada stack trace; data terakhir tetap tampil bila ada |
| Replay | `X-Replay: true` | Lencana "REPLAY" di U0; tombol live nonaktif kecuali butir `scene_checked` |
| Scope cut | Garis potong H-017 terpakai | Komponen terkait tampil abu dengan "not run (scope cut)" atau "stretch — not run" |

## 6. Pemetaan enum ke label

| Field | Nilai data | Label UI |
|---|---|---|
| `Item.origin` | `operator` | Operator-written |
| | `spark_disetujui` | Spark-proposed, approved |
| `Item.mode` | `literal` / `parafrase` | Literal / Paraphrase |
| `SplitRecord.assignments[].split` | `tune` / `held_out` | Tune / Held-out |
| `ProposalRecord.review_status` | `usulan` / `disetujui` / `diubah` / `ditolak` | Pending / Approved / Edited / Rejected |
| `AnswerRecord.output.status` | `jawab` / `tolak` / `bukti_tidak_cukup` | Answered / Abstained / Insufficient evidence |
| `VerifierResult` uji 3 | `berlaku` / `dicabut` / `berlaku_bersyarat` | Valid / Revoked / Conditional |
| Hasil uji | `lulus` / `gagal` / `tidak_dijalankan` | Pass / Fail / Not run |

## 7. Pemetaan ke adegan video

| Adegan (`docs/VIDEO.md`) | Komponen | Keadaan yang harus siap |
|---|---|---|
| 0 Hook | U1 dengan setting ukuran tetap | Butir kontrol yang terbelah, tanda "Gold split across chunks" |
| 1 Frontier UU PT | U1 → U2 (dua titik disorot), U4, U9 provenance | Held-out, anggaran default |
| 2 Header B | U2 deret on/off, U4 filter Paraphrase, U8, U6 sekilas | Run B tersimpan dengan cached tokens |
| 3 Akta | U0 family = Deed, U5 v1/v2, U1 potongan akta | Skema akta v1, v2 |
| 4 Bukti C | U3 dua kolom, ringkasan 2×2; pemilih model bila stretch Glimmer jadi (H-053) | Butir `scene_checked`; run Glimmer tersimpan bila dipakai |
| 5 Ekspor | U7, U9 disclaimer dan provenance | Profil UU PT dan akta |

## 8. Inventaris layar untuk mockup

Mockup menggambar **enam artboard**. Jumlah ini yang diperiksa di uji terima mockup.

| # | Artboard | Isi | Komponen | Interaktif | Adegan |
|---|---|---|---|---|---|
| 1 | `Main` | Halaman utama keluarga UU PT, setting terpilih di frontier, held-out | U0, U1, U2, U3 (ringkas), U4, U5 (ringkas), U7 (tombol), U8 (ringkas), U9 | Ya: klik titik U2 mengubah U1, U3, U4 | 0, 1, 2 |
| 2 | `Review` | Layar Review usulan D | U0, U6 | Ya: Approve/Edit/Reject mengubah kartu | 2 |
| 3 | `Schema` | Keluarga Deed: skema v1 vs v2 (diff) dan potongan akta sintetis menurut skema | U0, U5, U1 | Tidak wajib | 3 |
| 4 | `Evidence` | Detail C: dua kolom, tanda uji, ringkasan 2×2, uji 3 abu (stretch) | U3 lebar | Tidak wajib | 4 |
| 5 | `Export` | Pratinjau profil JSON, laporan held-out, hasil round-trip | U7, U9 | Tidak wajib | 5 |
| 6 | `States` | Loading, empty, error, replay, scope cut untuk U1–U3 | Keadaan bagian 5 | Tidak | — |

Aturan isi mockup:
- Angka hasil ditulis placeholder (`[x/y]`, `[$0.00]`, `[n items]`). Bentuk grafik boleh ilustratif dengan label kecil "illustrative".
- Teks pasal tidak dikarang. Pakai penanda struktur (BAB, Pasal, ayat (1)) dengan baris `[corpus text]`.
- Akta hanya sintetis dengan identitas jelas fiktif, tanpa NIK.

## 9. Hints and glossary (H-073)

Hint bersifat opsional: tertutup default, tidak mengubah tata letak, tidak menutup kontrol lain. Status teks: draf sampai operator menyetujui (`_kerja/orkestrasi/hint-draf-review.md`); komponen boleh jalan paralel dengan teks bertanda draf.

### 9.1 Pola

- **Pemicu.** Ikon info kecil (`button type="button"`) tepat di samping label. Nama aksesibel: `About: {title}`. Atribut: `aria-expanded`, `aria-controls` ke popover.
- **Popover.** Judul dan isi dari entri konten. Tertutup default. Terbuka lewat klik atau Enter/Spasi pada pemicu; hover boleh sebagai tambahan, tidak sebagai satu-satunya jalan. Esc menutup dan mengembalikan fokus ke pemicu. Klik di luar atau pindah fokus menutup. Hanya satu popover terbuka pada satu waktu.
- **`aria-describedby`.** Kontrol atau label yang dijelaskan merujuk elemen isi hint (selalu ada di DOM, disembunyikan secara visual saat tertutup, jadi pembaca layar tetap mendapat deskripsi tanpa membuka popover).
- **Posisi.** Tidak keluar viewport; pada lebar 375 px popover melebar penuh kolom dengan gutter. Teks bisa digulir bila panjang. Kontras minimal 4,5:1; target sentuh pemicu minimal 24 px (WCAG 2.2 AA).
- **Fokus.** Pemicu masuk urutan tab di samping label-nya; popover tidak menjebak fokus. Tidak ada animasi yang bergantung pada gerak (hormati `prefers-reduced-motion`).
- **Tanpa emoji**, label UI Inggris (H-018).

### 9.2 Panel About / Glossary

- Tombol `About / Glossary` di U0 (menambah satu label ke U0; tanpa mengubah label lain). Membuka panel sisi (pola tetap: dialog non-modal; fokus dipindah ke judulnya, Esc menutup dan mengembalikan fokus ke tombol).
- Isi, berurutan: (1) tujuan app (`app.purpose`), (2) target pengguna (`app.audience`), (3) cara membaca frontier (`app.read_frontier`), (4) mode putar ulang (`app.replay`), (5) glosarium: seluruh entri bertag `stretch` hanya dirender bila fiturnya dikirim (H-017; lihat §9.3), ditambah seluruh entri `term.*`, `metric.*`, `role.*`, `verifier.*`, `status.*`, `chunker.*`, `retrieval.*`, `header_b.*`, `model.*`, `ui.*`, dikelompokkan menurut awalan id dan bisa dicari (kotak cari memfilter judul dan isi).
- Panel menampilkan `version` dan `status` berkas konten bila `status` bukan `final` (label "Hint text: draft").

### 9.3 Konten

- Satu berkas berversi: `frontend/src/content/hints.json`, bentuk `{version, status, locale, entries[{id, title, body, stretch?}]}`. `stretch: true` menandai entri fitur stretch (H-017): hint tertaut dan entri glosarium hanya dirender bila kontrolnya ada di build (mis. `Valid on date`, `Valid`/`Revoked`/`Conditional`, pemilih model Glimmer/Spark Open dengan run tersimpan); bila fitur dipotong, entri tidak muncul dan test id-hilang tidak memandangnya yatim. `status` bernilai `draft` atau `final`; hanya operator mengubahnya ke `final`. `id` stabil, huruf kecil, `kelompok.nama`.
- Komponen hanya merujuk `id`. Id yang tidak ada di berkas = galat build/test (test: setiap id di tabel 9.4 ada di berkas, tidak ada entri yatim, tidak ada `id` ganda).
- Berkas ikut dibundel di build, sehingga ikut ekspor statis replay (H-051); tidak diambil dari backend dan tidak butuh jaringan.
- Bahasa Inggris. Istilah hukum Indonesia tetap dengan gloss dalam kurung: `Pasal (article)`, `ayat (paragraph)`, `Penjelasan (official elucidation)`.
- **Larangan angka.** Entri tidak memuat angka hasil (recall, token, biaya, hitungan butir) dan tidak memuat nilai konfigurasi yang bisa berubah (anggaran, ambang). Contoh angka hanya dari snapshot run tersimpan, dirender komponen, bukan dari berkas konten. Klaim produk hanya yang ada di `docs/PRD.md`.
- Definisi mengikuti `docs/EVAL-SPEC.md`; perubahan definisi di sana berarti entri terkait ditinjau ulang.

### 9.4 Titik penempatan

| Layar | Label atau elemen | Id hint |
|---|---|---|
| U0 | tombol `About / Glossary` | panel (§9.2) |
| U0 | `Family` | `metric.transfer_test` (untuk nilai Deed), `app.purpose` |
| U0 | `Model`, `Run cost` | `model.comparison_rule`, `metric.local_tokenizer` |
| U0 | lencana `REPLAY` | `app.replay` |
| U0 | `Review proposals` | `role.d` |
| U1 | `Chunks vs gold` | `term.gold_span`, `term.pasal`, `term.ayat`, `term.penjelasan` |
| U1 | `Gold split across chunks` | `ui.gold_split` |
| U1 | `Context header (B)` | `header_b.what` |
| U1 | `Compare with fixed-size`, nama chunker | `chunker.fixed_size`, `chunker.structure_handwritten`, `chunker.structure_schema` |
| U1 | `tokens (local tokenizer)` | `metric.local_tokenizer` |
| U2 | `Setting space` | `app.read_frontier` |
| U2 | `Span recall` | `metric.span_recall` |
| U2 | `Tokens (local tokenizer)` | `metric.local_tokenizer` |
| U2 | `Token budget` | `metric.token_budget` |
| U2 | `Tune` / `Held-out` | `metric.tune_heldout` |
| U2 | `Header B off` / `Header B on` | `header_b.what`, `role.b` |
| U2 | `Frontier` / `Dominated` | `metric.pareto_frontier` |
| U2 | mode retrieval di tooltip titik (hint dibuka lewat panel/pemicu yang bisa dijangkau papan ketik, bukan hover saja; WCAG 1.4.13) | `retrieval.bm25`, `retrieval.dense`, `retrieval.hybrid_rrf` |
| U3 | `End-to-end evidence` | `role.c` |
| U3 | `Model` (pemilih) | `model.contributor`, `model.glimmer_local`, `model.spark_open_baseten`, `model.comparison_rule` |
| U3 | `Exists`, `Faithful`, `Valid on date` | `verifier.exists`, `verifier.faithful`, `verifier.valid_on_date` |
| U3 | ringkasan 2x2 | `verifier.matrix_2x2` |
| U3 | `Valid` / `Revoked` / `Conditional` | `status.valid`, `status.revoked`, `status.conditional` |
| U4 | `Span recall`, `Token precision`, `Reciprocal rank`, `Recall@K` | `metric.span_recall`, `metric.token_precision`, `metric.mrr`, `metric.recall_at_k` |
| U4 | `Entity preservation`, `Boundary coherence` | `metric.entity_preservation`, `metric.boundary_coherence` |
| U4 | `Origin`, `Mode`, `No gold (must abstain)` | `role.d`, `term.gold_span` |
| U4 | `Split` | `metric.tune_heldout` |
| U5 | `Structure schema (A)` | `role.a`, `chunker.structure_schema` |
| U5 | `Boundary differences vs handwritten parser` | `chunker.structure_handwritten` |
| U6 | `Review proposals` | `role.d` |
| U7 | `Held-out results` / `Transfer results` | `metric.tune_heldout` / `metric.transfer_test` |
| U8 | `Role`, `Cached tokens` | `role.a`, `role.b`, `role.c`, `role.d` (satu hint per peran di filter), `header_b.what` |
| U8 | `Cost (USD)` | `metric.local_tokenizer` |
| U9 | disclaimer | `app.audience` |

Catatan: penjelasan Literal vs Paraphrase menjadi bagian isi `role.d`. Bila operator ingin hint terpisah untuk mode, tambah entri `ui.item_mode` (belum ada; pending operator).

### 9.5 Aksesibilitas dan uji

- Seluruh pemicu bisa dijangkau dan dibuka dengan papan ketik saja; Esc menutup; fokus kembali ke pemicu.
- Pembaca layar membaca deskripsi lewat `aria-describedby` tanpa membuka popover.
- Uji komponen (Tier 3): buka/tutup dengan klik, Enter, Spasi, Esc; satu popover pada satu waktu; id hilang = test gagal; tidak ada angka bergaya hasil di berkas konten (pemeriksaan pola digit pada `body` kecuali daftar izin notasi yang ditinjau manual: "2x2", "Check 1/2/3", "muse-spark-1.3", "BM25", "V10-any", "(1), (2)", "1 divided", "(0 if none)").
- Uji visual (Claude in Chrome, H-073): tangkapan layar hint tertutup dan terbuka pada 375, 768, dan 1440 px; konsol tanpa galat; bukti di `_kerja/orkestrasi/bukti/`.
- Ekspor statis replay memuat hint dan panel Glossary berfungsi tanpa backend (kriteria gate H-051).

## 10. Theme (H-083)

Sumber: H-083 (nilai) dan mockup pra-acara operator (acuan token dan pola saja, tidak disalin; H-044). Implementasi: `frontend/src/theme.css` (satu-satunya sumber nilai) dan `frontend/src/styles.css` (hanya `var(--...)`). Komponen tidak memakai hex literal; SVG grafik U2 memakai `var(--...)`. Kontras dikunci oleh `frontend/src/__tests__/contrast.test.ts`.

### 10.1 Token

| CSS variable | Nilai | Pemakaian |
|---|---|---|
| `--bg` | `#F3F4F1` | latar halaman, kartu item, blok konteks |
| `--ink` | `#15181C` | teks utama |
| `--surface` | `#FFFFFF` | panel, tombol, input |
| `--line` | `#D3D7DC` | border panel, tabel, pemisah |
| `--line-strong` | `#8A929B` | border kontrol (tombol, select, segmented); non-teks butuh kontras lebih tinggi dari `--line` |
| `--muted` | `#4B535D` | teks sekunder, label |
| `--accent` / `--accent-hover` | `#1D5BA8` / `#123E75` | tautan, fokus, alamat, penanda terpilih, deret header B off; hover tombol |
| `--on-accent` | `#FFFFFF` | teks di atas `--accent` |
| `--panel-head` | `#EEF0F2` | kepala chunk, kepala tabel |
| `--skeleton` | `#E4E7EA` | skeleton loading |
| `--gold` | `#FBE3A6` | sorot span gold, baris terpilih, sel berubah |
| `--head-bg` / `--head-ink` / `--head-muted` | `#15181C` / `#FFFFFF` / `#C9CED4` | header gelap U0: latar, nilai, label |
| `--pass-bg/-line/-text` | `#E3ECF8` / `#B7CBE8` / `#1D4E8F` | chip pass (biru) |
| `--fail-bg/-line/-text` | `#FBEBDD` / `#EDC6A3` / `#8A3F06` | chip fail (oranye), chunk terbelah |
| `--notrun-bg/-line/-text` | `#F1F2F4` / `#D3D7DC` / `#5A616B` | chip not-run, tag netral |
| `--replay-bg` / `--replay-ink` | `#F2B872` / `#15181C` | badge REPLAY |
| `--err-bg/-line/-text` | `#FBE9E7` / `#E3A49B` / `#8C2318` | galat, konfirmasi destruktif, penanda terpilih di grafik |
| `--series-off` / `--series-on` / `--dominated` | `#1D5BA8` / `#A8500C` / `#6B737C` | grafik U2: header B off, header B on, titik dominated (lihat selisih 4, 5) |

Pass/fail memakai biru/oranye, bukan hijau/merah. Mode gelap: tidak ada (UI-SPEC tidak menuntut; tidak ditambah).

### 10.2 Tipografi

| Font | Variable | Dipakai untuk |
|---|---|---|
| IBM Plex Sans 400/500/600 | `--font-sans` | UI: label, tombol, tabel, judul panel, tag |
| IBM Plex Serif 400/600 | `--font-serif` | teks hukum (chunk, konteks usulan, kutipan sitasi), kueri butir, jawaban model, ikon hint |
| IBM Plex Mono 400/500 | `--font-mono` | alamat (`.addr`, `.ev-addr`), hash, ID model dan biaya di header, kelas `.mono` |

Self-host lewat paket `@fontsource/ibm-plex-{sans,serif,mono}` 5.3.0 (versi persis, subset `latin`, hanya bobot di atas), diimpor di `main.tsx`. Alasan dependensi: ekspor statis (H-051) harus jalan tanpa CDN dan tanpa jaringan; `build:static` mengemas berkas woff/woff2 ke `dist-static/assets`. Lisensi font OFL.

### 10.3 Pola komponen

- Header gelap U0 (`--head-bg`): nama app, Family, Selected setting, `Model` (dari `/api/health`), `Run cost` (`run_cost_usd_micros` dari `/api/health`: jumlah `cost_usd_micros` seluruh RunRecord tersimpan, dihitung server tanpa limit; frontend tidak menjumlah, satu fetch health di `App`), badge `REPLAY` (`.tag.replay`). Nilai tidak terbaca ditampilkan "n/a".
- Panel putih (`.panel`): border `--line`, radius 6, padding 16.
- Label uppercase kecil: `.field`, `dt` detail, kepala tabel (0,75rem, letter-spacing 0,04em).
- Chip: pass, fail, not-run (token di atas), bulat, 0,75rem, teks tebal 600.
- Tombol: tinggi minimal 44 px (`button`, `.seg-item`, `select` di `.field`). Pengecualian: tombol hint 24 px dan tombol alamat (`.addr`) tetap kecil (inline di teks).
- Footer: "Research demo. Not legal advice." dan "Built with {model}" (model dari `/api/health`, bukan literal).

### 10.4 Selisih mockup vs UI-SPEC/keputusan (UI-SPEC dan keputusan menang)

| # | Mockup | Yang dipakai |
|---|---|---|
| 1 | Tata letak artboard per layar | `docs/UI-SPEC.md` §2 tetap; hanya tema yang diambil |
| 2 | Isi basi: keluarga POJK, `muse-spark-1.3`, angka `[n]` | tidak dibawa; Model dan Run cost dari data aplikasi |
| 3 | Footer menyebut model literal | "Built with {model}" dari `/api/health`; baris provenance U9 (`items_summary`) belum diimplementasi dan di luar tugas tema |
| 4 | Warna deret header B on (`#A8500C`, ada di mockup, tidak di daftar H-083) | dipakai sebagai `--series-on` (kontras 5,50 di atas putih); perlu konfirmasi operator |
| 5 | Abu titik dominated `#6B737C` (mockup) | `--dominated`; tidak di daftar H-083, perlu konfirmasi operator |
| 6 | Header memuat "Profile" dan "Review proposals ({n} pending)" (UI-SPEC U0) | tidak ditambah (di luar tema); tautan "Review proposals" tetap di bawah header |
| 7 | Kontrol 44 px | tombol hint (24 px, H-073) dan `.addr` dikecualikan agar tidak merusak alur teks |
| 8 | Border panel `#D3D7DC` terlalu terang untuk kontrol (kontras non-teks < 3:1) | kontrol memakai `--line-strong` `#8A929B` (nilai mockup, bukan dari H-083) |
