# MILESTONES — milestone, slice, dan status

Tujuan: daftar milestone dan atomic vertical slice dengan kriteria selesai testable, bukti wajib, tier review, dan status terkini.
Sumber keputusan: H-004, H-005, H-006, H-009, H-011, H-012, H-013, H-014, H-015, H-016, H-017, H-018, H-028, H-029, H-031, H-032, H-033, H-037, H-038, H-039, H-040, H-041, H-042, H-043, H-045, H-046, H-047, H-048, H-049, H-050, H-051, H-052, H-053, H-054, H-055, H-056.

Status slice dicatat **di sini**. Kalau bentrok dengan `docs/DECISIONS.md`, keputusan yang menang.

Nilai status: `belum mulai` · `berjalan` · `selesai` (dengan sha + bukti) · `dipotong` (dengan pemicu H-017) · `stretch`.

## Ringkasan

| Milestone | Tanggal | Isi | Slice | Estimasi (jam, sudah × 1,5) | Status |
|---|---|---|---|---|---|
| M0 Fondasi | 26 Okt malam–27 Okt | Official Rules, repo, klien Spark, korpus terukur | 2 | 4 | selesai 27 Okt |
| M1 Grid tanpa LLM, UU PT | 27–29 Okt | Chunker, tiga mode retrieval, metrik, frontier | 5 | 13 | kode + review selesai; screenshot ulang pada grid v2 menunggu pass visual |
| M2 Spark D dan C | 29–31 Okt | Usulan butir, jawaban ujung ke ujung, verifier | 4 | 10 | berjalan (M2.1–M2.3 kode ter-review; review butir D selesai 27 Okt: v12 = 20 butir) |
| M3 Spark B dan A, UU PT | 31 Okt–1 Nov | Header konteks, induksi skema, editor skema | 4 | 11 | berjalan (header B v2 lengkap tiga sumber, grid header-on `82809c6`; skema A v2 menunggu I-60) |
| M4 Transfer ke akta, ekspor | 2 Nov | Skema akta, frontier akta, profil berversi | 3 | 6,5 | berjalan (M4.1 dan M4.3 backend ter-review; akta disetujui operator 27 Okt, induksi A akta belum dijalankan) |
| M5 Demo dan submit | 3–4 Nov | Mode putar ulang dan gate (3 Nov), video (4 Nov) | 3 | 11 | berjalan (M5.1 kode ter-review, tema H-083; video dipisah ke operator, putusan 8) |
| **Jumlah** | | | **21** | **55,5** | |

Acara mulai 26 Okt 2026 23:00 WIB. Commit pertama repo ini dibuat setelah jam itu. Butir kontrol, akta sintetis, dan kode ditulis setelah jam mulai.

Garis potong berlaku sejak hari pertama (H-017):

| Potong | Isi | Kapan |
|---|---|---|
| 1 | M2.4 (uji 3) menjadi stretch; tabel status tidak diperiksa | Sejak hari pertama |
| 2 | Akta 5 dokumen sintetis ditulis agen (H-039), minimal 5 butir | Sejak hari pertama |
| 3 | Grid sempit: satu ukuran pembanding, satu anggaran pembanding | Sejak hari pertama |
| 4 | Header B hanya untuk setting di frontier | Bila M2 belum selesai 31 Okt malam |
| 5 | M4.2 (frontier akta) dipotong | Bila M2 belum selesai 31 Okt malam |

A, B, C, D, dan waktu video tidak dipotong.

Kode dibekukan **3 Nov 20:00 WIB**. 4 Nov hanya untuk video dan submit. Batas resmi 5 Nov 09:00 WIB.

Slice Tier 1: M0.1, M1.2, M1.4, M1.5, M2.1, M2.3, M2.4, M3.2, M4.3. Skenario test-nya disusun agen dengan data sintetis sebelum kode slice, dicek pemeriksa agen independen, dan disetujui operator (H-052, `docs/EVAL-SPEC.md` §11).

Label UI bahasa Inggris sejak M1.1 (H-018). Semua panggilan Model API lewat Responses API (H-016); pembanding stretch Glimmer lokal (H-047, M2.5) lewat Chat Completions ke endpoint lokal. Token anggaran dari tokenizer lokal terkalibrasi (H-014). Split berstrata (H-015).

Dependency:

```text
M0 ──► M1 ──► M2.1 (D) ──► M2.2/M2.3 (C)
         │                     │
         └──► M3.1/M3.2 (B) ───┤
         └──► M3.3/M3.4 (A) ──► M4 (akta) ──► M5
```

M2 dan M3 dikerjakan berurutan, tidak paralel.

## Spec per slice

| Slice | Spec yang wajib dibaca |
|---|---|
| M0.1 | `docs/SPARK-ROLES.md` §1, `docs/DATA-CONTRACTS.md` §12, `docs/SECURITY-COMPLIANCE.md` T1, T6 |
| M0.2 | `docs/DATA-CONTRACTS.md` §2 (termasuk "Aturan pemuat korpus UU PT" dan R1–R13), `docs/EVAL-SPEC.md` §2 |
| M1.1–M1.5 | `docs/EVAL-SPEC.md` §3–§9, `docs/DATA-CONTRACTS.md` §3, §4, §10, `docs/UI-SPEC.md` U1, U2, U4 |
| M2.1 | `docs/SPARK-ROLES.md` §5, `docs/DATA-CONTRACTS.md` §9, `docs/UI-SPEC.md` U6 |
| M2.2–M2.4 | `docs/SPARK-ROLES.md` §4, `docs/EVAL-SPEC.md` §10, `docs/DATA-CONTRACTS.md` §5, §8, `docs/UI-SPEC.md` U3 |
| M2.5 (stretch) | `docs/SPARK-ROLES.md` §7, `docs/API.md` W6, `docs/DATA-CONTRACTS.md` §8, §12, `docs/UI-SPEC.md` U3 |
| M3.1–M3.2 | `docs/SPARK-ROLES.md` §3, `docs/DATA-CONTRACTS.md` §7 |
| M3.3–M3.4, M4.1 | `docs/SPARK-ROLES.md` §2, `docs/DATA-CONTRACTS.md` §6, `docs/UI-SPEC.md` U5 |
| M4.3 | `docs/DATA-CONTRACTS.md` §11, `docs/UI-SPEC.md` U7 |
| M5.1–M5.3 | `docs/UI-SPEC.md` §4–§7, `docs/VIDEO.md`, `docs/SECURITY-COMPLIANCE.md` §4 |

Endpoint per slice: `docs/API.md` kolom Slice.

## Prinsip yang berlaku di semua slice

- **Configuration over hardcoding.** Model id, reasoning effort, sumbu grid, anggaran token, ambang fuzzy, dan granularitas B ada di berkas konfigurasi berversi.
- **Setiap hasil bisa diulang.** Setiap run mencatat hash korpus, hash konfigurasi, versi prompt, model, effort, token input/cached/output, biaya, dan latensi. Hasil disimpan per hash dan tidak dijalankan ulang kalau hash sama.
- **Keadilan antar-setting.** Model, effort, instruksi sistem, dan bentuk keluaran sama untuk semua setting yang dibandingkan. Penanda alamat (peraturan › pasal › ayat) diberikan sama di semua chunker, supaya yang dibandingkan isi potongan, bukan siapa yang dapat alamat.
- **Agen tidak menulis butir, tabel status, atau koreksi skema.** Itu milik operator (H-006, H-009).
- **Tanpa** database, auth, vector database, LangChain, parser PDF, dan reranker (H-013).
- **Tidak ada kode prototipe pra-acara yang disalin.** Metodenya hanya acuan (H-003).

Struktur repo, bentuk data, dan verifier sudah dipindah ke `docs/ARCHITECTURE.md` §6, `docs/DATA-CONTRACTS.md`, dan `docs/EVAL-SPEC.md` §10.

---

## M0 — Fondasi (26 Okt malam–27 Okt)

Sebelum slice (operator, sekitar 2 jam):
- Official Rules sudah dibaca dari Participant Guide (H-043). Kalau dokumen legal terpisah muncul dan melarang karya pra-acara sebagai dasar, berhenti dan revisi keputusan dulu. Cek juga durasi video, bahasa, dan field form, lalu sesuaikan `docs/VIDEO.md`.
- Unduh tokenizer H-014 (terima lisensi Muse Spark Open) sebelum M0.2.
- Setelah 23:00 WIB: buat repo submission. Model API memakai `muse-spark-1.3-contributor` (H-028); cek apakah kredit $150 berlaku untuk varian itu. Kalau Muse Code dipakai, akun disetel Standard. API key di `.env` lokal saja.
- Commit pertama repo: `.gitattributes` dan `.editorconfig` menurut `docs/CONVENTIONS.md` bagian "Akhir baris" (G-16). Di mesin Windows, clone dengan `-c core.autocrlf=false`.
- Spec pra-acara diimpor ke `docs/` sebagai commit berlabel, terseleksi dan disaring (H-044).
- Pin versi library. Rilisan yang umurnya baru 2–4 hari per 25 Okt (FastAPI 0.162, openai 3.37, sentence-transformers 6.2, Vite 8.3) dipin ke minor sebelumnya kalau ada masalah. TypeScript 7 adalah lompatan major, jadi cek kompatibilitasnya dengan template Vite sebelum dipakai. `rank-bm25` 0.2.2 sudah tidak aktif sejak 2022, tapi masih dipakai karena kecil dan stabil.

### M0.1 — Klien Spark dan catatan run
**Slice**: Satu panggilan `muse-spark-1.3-contributor` (model ID dari `config/model`, H-028) lewat Responses API (H-016) dengan structured output `strict: true` berhasil, dan catatan run-nya tampil (model, effort, token input/cached/output, biaya, hash prompt).
**Catatan API (riset 25 Okt)**:
- Cached tokens dibaca dari `usage.input_tokens_details.cached_tokens`.
- Dengan `strict: true`, `additionalProperties: false` wajib, semua key masuk `required`, dan field opsional ditulis lewat `anyOf` dengan null. `allOf`/`oneOf` tidak didukung, dan skema rekursif ditolak.
- Nilai effort yang valid diuji dulu, karena `max` tidak konsisten antar halaman docs.
- Request paralel pertama kemungkinan belum kena cache, jadi kirim satu request pemanas, lalu pakai `prompt_cache_key`.
**Scope file**: `backend/` (klien Spark, catatan run), `config/model`, `.env.example`, `.gitignore`.
**Di luar scope**: korpus, chunker, frontend.
**Kriteria selesai (testable)**:
- Given key valid, When panggilan dijalankan, Then keluaran sesuai schema dan catatan run tersimpan.
- Panggilan kedua dengan prefix sama menunjukkan token cached > 0.
- Key salah, timeout, dan rate limit menghasilkan pesan error yang jelas, bukan stack trace. Key tidak pernah tercetak di log.
- Klien membatasi laju di bawah 150 RPM dan menghormati `Retry-After` pada 429 (H-028).
**Bukti verifikasi yang wajib disetor**: output test hijau, contoh catatan run dua panggilan (dengan dan tanpa cache), hasil grep bahwa key tidak ada di repo.
**Tier review**: 1. Penanganan secret dan perhitungan biaya.
**Estimasi**: 2 jam.
**Status**: selesai 2026-10-27 — kode `7d23b7e`, perbaikan review `ff252b4`, `7dee80d` (170 test `-k spark`, S1–S42). Review Tier 1 independen dua putaran: 0 BLOCKER, 28/32 lalu semua mutan non-ekuivalen mati (`_kerja/orkestrasi/l3/G1-periksa.md`, tidak di-commit). Bukti live (Meta, profil `meta`): `runs/spark/records/cc80b58f….json` (input 3.113, cached 0, output 406, 393 micro-USD) dan `0f5378da….json` (cached 3.064, 92 micro-USD). Grep key: secretscan histori + tree 0 (terbukti menggigit). Terbuka untuk operator: I-37 (belanja panggilan gagal tanpa usage), cap per peran a/b/c/d usulan agen di `config/budget`.

### M0.2 — Korpus UU PT termuat dan terukur
Prasyarat terpenuhi: format korpus dan aturan pemuat dikunci di H-046. Aturan pemuat dan uji penolakan R1–R13 ada di `docs/DATA-CONTRACTS.md` §2.
**Slice**: Layar (atau keluaran CLI) menampilkan berkas konsolidasi UU PT per bagian (batang tubuh, Penjelasan) dengan jumlah karakter teks bersih, token terukur dari `/v1/responses/input_tokens` (dikurangi baseline input kosong), token dari tokenizer lokal H-014, rasio kalibrasi keduanya, hash berkas, dan jumlah anotasi yang terurai menjadi baris tabel status.
**Scope file**: `data/uupt/`, `backend/` (pemuat korpus dan pemisah anotasi), `runs/`.
**Di luar scope**: chunker, retrieval.
**Kriteria selesai (testable)**:
- Hash berkas = SHA-256 `a6b38ee5…` (H-045), tercatat di `config/corpus`, diverifikasi setelah commit (LF, tanpa BOM, G-16), di kedua mesin dev.
- Teks bersih tidak memuat penanda anotasi sama sekali, dan setiap anotasi terurai menjadi usulan baris status atau ditolak dengan pesan jelas. Usulan Perppu: Pasal 1, 7, 32, 153, 153A–153J; satu-satunya usulan MK: Pasal 86 ayat (9); Pasal 142 ayat (2) huruf a `berlaku` dengan `note`. Ketentuan lain memakai aturan status default yang dibaca dari `config/corpus` (H-046).
- `CorpusDoc` memuat `clean_sha256` dan `loader_rules_version`; teks bersih dibagi lima `section` (`pembukaan`, `penjelasan_umum`, `batang_tubuh`, `penjelasan_pasal`, `pengesahan`), sehingga batang tubuh dan Penjelasan dibedakan walau nomor pasalnya sama.
- Uji penolakan R1–R13 (`docs/DATA-CONTRACTS.md` §2) hijau, termasuk R9 dengan aturan kalimat penutup rincian dan R13 determinisme `clean_sha256`.
- Berkas yang memuat `\r` atau BOM ditolak dengan pesan jelas. Diuji dengan salinan korpus yang sengaja dikonversi CRLF.
- Token terukur dicatat, dan proyeksi biaya dicatat di catatan run M0.2.
- Rasio kalibrasi tokenizer lokal terhadap endpoint tercatat di `config/`, per bagian dan rata-rata.
- Berkas hilang atau rusak ditolak dengan pesan jelas.
**Bukti verifikasi yang wajib disetor**: tabel per bagian dengan token terukur, hash, jumlah anotasi terurai, dan contoh dua ketentuan yang berubah (teks bersih vs baris status).
**Tier review**: 2.
**Estimasi**: 2 jam.
**Status**: selesai 2026-10-27 — pemuat `bb40dba`, token dan kalibrasi `415b9b8`, status metode dari config `33d7c9d` (+ test mutan di commit penutupan). Metode baseline selisih dua titik disetujui operator 27 Okt (I-26 ditutup, `config/tokenizer` `status = "disetujui"`); run tersimpan `runs/measure/5db7720bc1f5a121.json` tidak ditulis ulang (status saat run `sementara`). Review Tier 2 independen 0 BLOCKER (pemuat dan token: `_kerja/l3/REVIEW-G2.md`, `REVIEW-G3.md`; penutupan: `_kerja/orkestrasi/l3/G2-periksa-hasil.md`, tidak di-commit). Bukti: `uv run pytest -q`; `uv run python -m backend.corpus`; `uv run python -m backend.measure --offline`. Hash diverifikasi di mesin kedua (I-30). Catatan: `[status_default]` `config/corpus` tetap usulan milik operator (H-009), bukan kriteria M0.2.

Operator, di akhir M0: kunci nilai grid H-012 setelah melihat panjang pasal, lalu mulai menulis butir kontrol (H-011) dengan aturan span gold H-048: span menandai semua ayat yang dibutuhkan, boleh multi-ayat, tidak lebih.

## M1 — Grid tanpa LLM, UU PT (27–29 Okt)

Prasyarat: minimal enam butir kontrol tulisan operator, dengan span gold.

### M1.1 — Potongan vs gold
**Slice**: Untuk satu butir, panel menampilkan dokumen dengan batas potongan (struktur tulisan tangan atau ukuran tetap), dan span gold disorot.
**Scope file**: `backend/` (chunker struktur, chunker ukuran tetap, alamat potongan), `frontend/` (panel potongan).
**Di luar scope**: retrieval, metrik.
**Kriteria selesai (testable)**:
- Chunker struktur memberi alamat kanonik dengan bagian (`docs/DATA-CONTRACTS.md` §2). Pada sampel pasal yang dicek operator, batasnya tepat di batas ayat.
- Pasal dengan nomor sama di batang tubuh dan Penjelasan diberi alamat berbeda (`UU 40/2007 › Pasal 86 › ayat (9)` vs `UU 40/2007 › Penjelasan › Pasal 86 › Ayat (9)`), dan diuji (G-20, H-046).
- Kalimat penutup rincian milik ayat, bukan butir terakhir; chunker per huruf diuji pada Pasal 102 ayat (1) (H-046, G-25).
- Bila teks UU pengubah dimasukkan (tidak, menurut H-046), peraturan perubahan dengan `Pasal I` Romawi dikenali (G-13).
- Offset potongan bisa dipetakan balik ke teks sumber tanpa selisih karakter.
- Dokumen tanpa penanda struktur tidak membuat chunker gagal; ia jatuh ke satu potongan per bagian dengan peringatan.
**Bukti verifikasi yang wajib disetor**: test hijau dengan golden sample beberapa pasal, screenshot panel.
**Tier review**: 2. Batas potongan diuji dengan golden sample yang dipilih operator.
**Estimasi**: 3 jam.
**Status**: selesai 2026-10-27 (kriteria kode) — kode `4e18c57`, chunker v2 `8e94269`, `80da6c9` (H-062 fixed_size lintas Pasal/section, H-064 heading Pasal di potongan ayat pertama); golden sample disetujui operator (I-36); review Tier 2 lulus (`_kerja/orkestrasi/l3/G3-periksa.md`, `W2-chunk-periksa-hasil.md`). Screenshot `_kerja/orkestrasi/bukti/M1.1-*.png` dari chunker v1; screenshot ulang v2 di pass visual.

### M1.2 — BM25 dan metrik span pada anggaran
**Slice**: Untuk satu setting, tabel per butir menampilkan span recall, precision token, dan MRR pada anggaran token default, dengan retrieval BM25 + Sastrawi.
**Scope file**: `backend/` (BM25, kalkulator metrik span, pemotong anggaran), `frontend/` (tabel per butir).
**Di luar scope**: dense, hybrid, grid.
**Kriteria selesai (testable)**:
- Token dihitung dengan tokenizer lokal H-014 yang sama untuk semua setting, dan nama serta versinya tercatat di catatan run.
- Potongan diambil berurutan sampai anggaran token habis. Potongan yang melewati anggaran tidak ikut (atau dipotong, sesuai konfigurasi), dan aturannya tercatat.
- Span recall = porsi karakter gold yang tertutup potongan terambil. Precision token = porsi token terambil yang termasuk gold. Keduanya diuji pada kasus buatan dengan jawaban yang dihitung tangan: gold terbelah dua potongan, gold di luar anggaran, potongan tumpang-tindih karena overlap.
- Span gold multi-ayat dipecah di batas ayat sebelum Recall@K; Recall@K = porsi bagian-ayat yang masing-masing utuh di salah satu potongan top-K (H-048). Diuji pada kasus buatan.
- Butir tanpa gold (wajib tolak) tidak membuat kalkulator gagal dan dilaporkan terpisah.
**Bukti verifikasi yang wajib disetor**: test hijau untuk kasus hitung tangan, tabel per butir.
**Tier review**: 1. Kalkulator ini yang menentukan "optimal" (H-005). Skenario test disusun agen sebelum kode, dicek pemeriksa independen, disetujui operator (H-052); penulis kode tidak memilih skenarionya sendiri.
**Estimasi**: 3 jam.
**Status**: selesai 2026-10-27 — kalkulator + BM25 `5b9bb04`, `6c4e19b` (Tier 1 0 BLOCKER, `l3/G4a-periksa.md`); integrasi `8450e1d` (Tier 1 `l3/INTa-periksa.md`); tabel per butir `1789c4f` (review `l3/INTb-periksa.md`). Bukti `bukti/M1.2-table.png`.

### M1.3 — Dense dan hybrid
**Slice**: Tabel yang sama menampilkan tiga mode retrieval (dense, BM25, hybrid RRF) berdampingan.
**Scope file**: `backend/` (dense, hybrid, cache embedding), `frontend/` (pemilih mode).
**Di luar scope**: kalkulator metrik (dipakai, tidak diubah).
**Kriteria selesai (testable)**:
- Embedding dihitung sekali per potongan dan disimpan per hash.
- Embedder `BAAI/bge-m3` revisi dipin, dense saja, tanpa prefix (H-042); `max_seq_length` dan jumlah potongan terpotong tercatat di konfigurasi dan `RunRecord` (G-22).
- Hybrid memakai parameter RRF dari konfigurasi.
**Bukti verifikasi yang wajib disetor**: test hijau, tabel tiga mode untuk butir kontrol.
**Tier review**: 2.
**Estimasi**: 2 jam.
**Status**: selesai 2026-10-27 — dense bge-m3 GPU + hybrid RRF `bd7a9bf`, `dc8a5c5` (Tier 2, `l3/G5-periksa.md`); pemilih mode `1789c4f`. Bukti `bukti/M1.3-modes.png`.

### M1.4 — Grid, split, dan Pareto frontier
**Slice**: Run grid menghasilkan frontier span recall vs token untuk UU PT. Klik satu titik mengubah panel potongan dan tabel per butir. Pemilihan profil terbaik memakai set tune, angka yang dilaporkan dari held-out.
**Scope file**: `backend/` (runner grid, split, frontier), `config/grid`, `frontend/` (grafik frontier).
**Di luar scope**: kalkulator metrik, chunker.
**Kriteria selesai (testable)**:
- Split tune/held-out ditetapkan sekali dengan seed tercatat, berstrata per asal dan mode, `held_out_ratio = 0.4` dari `config/grid`, dan minimal tiga butir kontrol ada di held-out (H-015, H-049). Bila pembulatan membuat kontrol di held-out kurang dari tiga, kontrol ditambahkan ke held-out lebih dulu; ini diuji. Butir held-out tidak pernah dipakai untuk memilih.
- Pemilihan profil deterministik: pemecah seri H-034, lalu precision token dan token lebih sedikit, lalu `setting_id` terkecil (H-055). Diuji dengan titik seri buatan.
- Butir yang disetujui setelah split pertama dimasukkan dengan aturan strata yang sama. Split lama tidak diacak ulang.
- Titik yang didominasi tidak masuk frontier. Ini diuji dengan set titik buatan.
- Run kedua dengan hash sama tidak menghitung ulang.
**Bukti verifikasi yang wajib disetor**: test hijau untuk split dan frontier, screenshot frontier, catatan run grid.
**Tier review**: 1. Kebocoran held-out membuat "optimal" palsu.
**Estimasi**: 3 jam.
**Status**: selesai 2026-10-27 (kriteria kode) — split/frontier/pemilihan `1aac9e7`, `f970448` (Tier 1 dua putaran); integrasi `8450e1d` (Tier 1 INTa); grafik frontier `1789c4f` (INTb). Run grid v2 UU PT `23b606e` (`runs/grid/a822c0c1….json`: 12 setting jalan, 24 dilewati sampai header B/skema A; split v1 tune 5 / held-out 4). Bukti `bukti/M1.4-*.png` (v1), `bukti/grid-v2.txt`. Grid diulang dengan header B (M3.2) dan skema A (M3.4).

### M1.5 — Metrik janji form
**Slice**: Untuk setting terpilih, layar menampilkan Recall@K, entity preservation, dan boundary coherence, struktur vs ukuran tetap.
**Scope file**: `backend/` (metrik mutu potongan), `frontend/` (panel metrik).
**Di luar scope**: kalkulator span.
**Kriteria selesai (testable)**:
- Definisi kedua metrik mutu ditulis di repo sebelum kode, dengan metode pra-acara sebagai acuan.
- Diuji pada kasus buatan: nomor pasal terbelah, batas di tengah kalimat.
**Bukti verifikasi yang wajib disetor**: test hijau, panel metrik.
**Tier review**: 1. Metrik yang dijanjikan di form.
**Estimasi**: 2 jam.
**Status**: selesai 2026-10-27 — metrik `2e90254` (Tier 1), Recall@K produksi `8450e1d`, panel `1789c4f`; cakupan held-out (H-065, `165f597`). Bukti `bukti/M1.5-metrics.png`.

## M2 — Spark D dan C (29–31 Okt)

### M2.1 — Usulan butir dan layar periksa (peran D)
**Slice**: Spark mengusulkan pasangan (query, span gold) dalam mode literal dan parafrase. Operator menyetujui, mengubah, atau menolak di layar periksa. Butir yang disetujui masuk evaluasi dengan asal `spark_disetujui`.
**Scope file**: `prompts/d`, `backend/` (usulan, status periksa), `data/butir/`, `frontend/` (layar periksa).
**Di luar scope**: kalkulator metrik, grid.
**Kriteria selesai (testable)**:
- Status butir hanya bisa bergerak `usulan → disetujui | diubah | ditolak`. Tidak ada jalur dari usulan langsung ke evaluasi.
- Span usulan divalidasi: offset ada di dokumen, dan teksnya cocok.
- Tabel per butir bisa difilter per asal, dan hasil dilaporkan per asal.
**Bukti verifikasi yang wajib disetor**: test hijau untuk transisi status, contoh usulan parafrase, screenshot layar periksa.
**Tier review**: 1. Transisi status menentukan butir mana yang sah (H-006).
**Estimasi**: 3 jam.
**Status**: berjalan — kode `79b970a`, `7021427` (Tier 1 lulus, `l3/W2-M21-periksa.md`); run live D 13 usulan UU PT `dd39dcb` (5.696 micro-USD). Bukti `bukti/M2.1-review-1440.jpg`. Menunggu operator: review 13 usulan di U6 (H-006; target H-011 15–20 butir sah). Update L2#5: review usulan UU PT dan akta selesai (operator; uupt v13, akta v70). Mode D `unanswerable` (H-087): skenario Tier 1 `docs/scenarios/M2.1-unanswerable.md` + pemeriksa 3 putaran 0 BLOCKER (`30caf38`), menunggu operator (`_kerja/orkestrasi/keputusan-pagi.md` butir 7); kode belum ditulis. Update L2#6 (28 Okt): mode D `unanswerable` akta (H-087, H-092) `7f993fb` (Tier 1 W60 2 putaran) + U6 `a308dd8`; run 15 kandidat `7fca1a9` (2.711 micro-USD), semua disetujui operator `684eb2b` (akta v85: tolak 15, 3 per akta).

Operator, mulai di sini: periksa usulan sampai UU PT punya 15–20 butir sah (H-011).

### M2.2 — Jawaban ujung ke ujung (peran C)
**Slice**: Untuk satu butir, Spark menjawab dari top-K profil terbaik dan profil pembanding. Dua kolom tampil berdampingan dengan status, jawaban, kutipan, dan biaya.
**Scope file**: `prompts/c`, `backend/` (perakit konteks, pemanggil C), `frontend/` (panel bukti).
**Di luar scope**: verifier.
**Kriteria selesai (testable)**:
- Konteks kedua kolom memakai anggaran token yang sama dan instruksi yang sama.
- Status `tolak` dan `bukti_tidak_cukup` tampil sebagai keluaran sah, bukan error.
- Hasil disimpan per hash, dan putar ulang tidak memanggil API.
**Bukti verifikasi yang wajib disetor**: test hijau, catatan run, screenshot dua kolom.
**Tier review**: 2.
**Estimasi**: 2 jam.
**Status**: berjalan — backend `a61f7c9`, `2e59f6f` (Tier 2), panel bukti U3 `7e090d1` (Tier 3, `l3/W4-FE-periksa.md`), label alamat di luar anggaran (H-066). Sisa: screenshot dua kolom U3 (pass visual). Bukti live K-02 `runs/spark/records/18b443f5….json`, `6b318801….json`.

### M2.3 — Verifier uji ada dan setia
**Slice**: Setiap kutipan di panel bukti diberi tanda lulus/gagal untuk uji 1 dan 2. Ringkasan 2×2 penolakan tampil per profil.
**Scope file**: `backend/` (verifier), `config/verifier`, `frontend/` (tanda dan ringkasan).
**Di luar scope**: pemanggil C, tabel status.
**Kriteria selesai (testable)**:
- Alamat yang tidak ada → gagal uji 1. Kutipan yang diubah satu kata → gagal atau lolos sesuai ambang fuzzy di konfigurasi.
- Kasus test disusun agen dan disetujui operator (H-052): kutipan persis, parafrase, alamat salah ayat, alamat salah bagian (batang tubuh vs Penjelasan), alamat dari peraturan lain. Ambang fuzzy diusulkan dengan alasan tertulis dan disetujui operator.
**Bukti verifikasi yang wajib disetor**: test hijau untuk kasus operator, screenshot.
**Tier review**: 1, ditambah Tier 4 domain review oleh operator atas kasus test.
**Estimasi**: 3 jam.
**Status**: **selesai** — Tier 4 dikonfirmasi operator 28 Okt (lewat orkestrator; U3 tanda verifier dan ringkasan 2×2 diperiksa di tailnet). verifier + 2×2 + prompt C v2 + label unit `ae372db`, `de4933d` (Tier 1 lulus, `l3/W3-M23-hasil.md`; H-067, H-070). Sisa: Tier 4 domain review operator atas kasus test; screenshot tanda dan ringkasan U3.

### M2.4 — Uji berlaku tiga nilai (stretch, H-017)
**Slice**: Kutipan diberi status `berlaku`, `dicabut`, atau `berlaku_bersyarat` pada tanggal acuan butir.
**Scope file**: `data/status/`, `backend/` (uji 3), `frontend/` (tanda status).
**Di luar scope**: uji 1 dan 2.
**Kriteria selesai (testable)**:
- Butir dengan `reference_date` sebelum 2022-12-30 ditolak saat masuk (H-046); teks lama ketentuan yang diubah tidak ada di berkas, jadi uji 3 hanya menilai bunyi yang berlaku sejak tanggal itu.
- Ketentuan hasil Perppu 2/2022 bernilai sesuai baris tabel yang disetujui operator; Pasal 86 ayat (9) (dimaknai bersyarat oleh putusan MK) menghasilkan `berlaku_bersyarat`; ketentuan tanpa entri memakai aturan default (`berlaku` sejak tanggal pengundangan). Kasusnya diambil dari anotasi konsolidasi.
- Tabel status diberi versi, dan isinya disetujui operator.
**Bukti verifikasi yang wajib disetor**: test hijau dengan kasus dari anotasi konsolidasi, tabel status versi yang disetujui.
**Tier review**: 1, ditambah Tier 4 domain review oleh operator.
**Estimasi**: 2 jam.
**Status**: stretch (H-017, potong 1).

### M2.5 — Pembanding Glimmer lokal pada peran C (stretch, H-047, H-053)
**Slice**: Di U3, pemilih model menampilkan pilihan Contributor dan Glimmer lokal. Memilih Glimmer menjalankan ulang peran C untuk profil terbaik dan baseline H-036 lewat W6, dan setiap jawaban berlabel model, kuantisasi, dan effort.
**Scope file**: `backend/` (klien Glimmer Chat Completions lokal, pemilihan `model_profile` di W6, cek ketersediaan server), `config/model`, `frontend/` (pemilih dan label model di U3).
**Di luar scope**: peran A, B, D, verifier, grid. Glimmer tidak dipakai di sana.
**Kriteria selesai (testable)**:
- Model ID, kuantisasi (`Q4_K_M`), dan `reasoning_effort` (`high`) dibaca dari `config/model`, dipin sebelum run pertama, dan tercatat di `RunRecord`.
- Run Glimmer disimpan terpisah dan tidak pernah digabung dengan run Contributor dalam satu tabel perbandingan atau frontier tanpa label (H-028).
- Bila server lokal mati, pilihan Glimmer nonaktif dengan pesan jelas; run tersimpan tetap tampil. Di replay statis hanya hasil tersimpan.
- Keluaran divalidasi skema di sisi klien; keluaran tidak valid dicatat dan tidak dipakai.
- Run Glimmer tidak dijadwalkan bersamaan dengan embedding di mesin GPU (VRAM, G-26).
**Bukti verifikasi yang wajib disetor**: test hijau, catatan run Glimmer dan Contributor untuk butir yang sama, screenshot U3 dengan label.
**Tier review**: 2.
**Estimasi**: sekitar 3–6 jam (2–4 jam H-047, 1–2 jam W6/U3 H-053); stretch, tidak masuk jumlah Ringkasan.
**Status**: selesai (stretch) 2026-10-27 — kode `d0b19c8` (Tier 2 W47: 0 BLOCKER; SHOULD ditutup penulis; L2 verifikasi pytest 1184, vitest 250, tsc 0): profil `baseten_open` (Responses strict, G-33) dan `glimmer_local` (`meta/muse-glimmer`, Q4_K_M, konteks 131072, effort high; Chat Completions loopback + validasi skema klien, H-047); W6 menerima profil peran `c`; Glimmer live lewat CLI `backend.answer.compare_c` saja (W6 live -> 409 `live_unavailable`, G-26). Run `ea72711`: butir demo K-09/K-01/K-08 best + baseline, konteks persis jawaban Contributor (hash dicocokkan, tanpa embedding): Spark Open 6/6 ok (30.591 micro-USD Baseten), Glimmer 6/6 ok (0). Bukti `_kerja/orkestrasi/bukti/M2.5-U3-glimmer-static-1440.jpg`. Nilai `max_output_tokens`/`timeout_s` usulan agen menunggu operator (keputusan-pagi butir 8).

## M3 — Spark B dan A, UU PT (31 Okt–1 Nov)

### M3.1 — Header B untuk satu dokumen, biaya, dan waktu
**Slice**: Untuk satu dokumen (UU PT), Spark menulis header konteks per potongan dengan dokumen di-cache, lalu layar menampilkan header, token cached, biaya, dan waktu per granularitas (pasal vs ayat).
**Scope file**: `prompts/b`, `backend/` (pemanggil B), `runs/`.
**Di luar scope**: grid.
**Kriteria selesai (testable)**:
- Panggilan kedua dan seterusnya untuk dokumen sama menunjukkan cache hit.
- Proyeksi biaya dan waktu (pada 150 RPM, H-028) seluruh korpus tercatat untuk dua granularitas.
- Sampel header per granularitas tersedia untuk dinilai mutunya oleh operator (H-038).
- Lingkup tambahan (H-069): B juga dijalankan untuk potongan `fixed_size` dari setting yang lolos `frontier_only`, satu potongan per panggilan, dengan cache dan proyeksi biaya lebih dulu (gerbang belanja addendum 2).
**Bukti verifikasi yang wajib disetor**: catatan run, proyeksi biaya.
**Tier review**: 2.
**Estimasi**: 1,5 jam.
**Status**: berjalan — backend `e1244aa` … `94de71c` (Tier 2); prompt B v2 + rejected + maxLength (H-079) `67d6427` (Tier 1/2, `l3/W21-hb-periksa-hasil.md`), smoke maxLength diterima (G-35). Header v1: Pasal 342/343, fixed_size 100/103 (`472ffc8`, `92fbb4c`); v2: Pasal 343/343, fixed_size 101/103 (`cb35b01`, 132.115 micro-USD). Menunggu operator: I-56, I-57.

Operator: putuskan granularitas B dari angka ini (H-038). Bila M2 belum selesai 31 Okt malam, "hanya frontier" berlaku otomatis.

### M3.2 — Header B sebagai sumbu grid
**Slice**: Frontier UU PT menampilkan dua deret, header on dan off. Token header dihitung dalam anggaran.
**Scope file**: `backend/` (indeks dengan header, runner grid), `frontend/` (deret frontier).
**Di luar scope**: kalkulator metrik (dipakai, tidak diubah).
**Kriteria selesai (testable)**:
- Pada anggaran yang sama, setting dengan header membawa lebih sedikit teks sumber. Ini diuji.
- Span gold tetap diukur pada teks sumber, bukan pada header.
**Bukti verifikasi yang wajib disetor**: test hijau untuk akuntansi anggaran, screenshot dua deret.
**Tier review**: 1. Akuntansi token header menentukan keadilan perbandingan.
**Estimasi**: 2 jam.
**Status**: berjalan — backend `1a9bacf`, `12528f5` (Tier 1); U2 deret + toggle `4d64878`, `294ec6c` (frontier gabungan, I-48 ditutup). Grid v2 `5a9486e` (`runs/grid/334717886e24….json`): 9 kembaran header-on frontier gagal `header_missing` (I-56 potongan skema tanpa header, I-57 satu potongan fixed_size). Screenshot dua deret setelah putusan.

### M3.3 — Induksi skema A untuk UU PT
**Slice**: Spark membaca UU PT dan mengeluarkan skema hierarki. Layar menampilkan skema itu berdampingan dengan koreksi operator, operator mengoreksi lewat editor di layar (H-037), dan versi skema tersimpan.
**Scope file**: `prompts/a`, `backend/` (pemanggil A, penyimpan skema, endpoint koreksi W9), `frontend/` (panel skema dan editor).
**Di luar scope**: chunker.
**Kriteria selesai (testable)**:
- Skema sesuai schema structured output, dan pola setiap level diuji terhadap contoh yang disebut Spark sendiri.
- Koreksi operator lewat editor tersimpan sebagai versi baru, divalidasi sama dengan keluaran Spark, dan tidak menimpa usulan Spark.
- Fallback (H-055): bila pemicu 31 Okt H-017 aktif, editor turun ke berkas berversi (koreksi ditulis operator sebagai berkas, divalidasi sama, disimpan sebagai `SchemaRecord`), dan U5 hanya menampilkan diff antar versi.
**Bukti verifikasi yang wajib disetor**: skema v1 (Spark) dan v2 (koreksi), screenshot.
**Tier review**: 2, ditambah Tier 4 domain review oleh operator.
**Estimasi**: 5,5 jam (3 jam induksi + 2,5 jam editor, H-037).
**Status**: **selesai** — Tier 4 dikonfirmasi operator 28 Okt (lewat orkestrator; koreksi skema v2 H-084 sebagai domain review). backend `496624b`, `1ff71e5`, `f2f18ee` (Tier 2 lulus, `l3/W2-M33-periksa.md`); panel + editor U5 `7e090d1` (Tier 3). Run induksi UU PT `1558986` (`runs/schemas/uupt/v1.json`, 5.700). Menunggu operator: persetujuan/koreksi skema v1 (H-074) + Tier 4 domain review.

### M3.4 — Chunker digerakkan skema
**Slice**: Chunker yang membaca skema A masuk grid. Frontier menampilkannya di samping parser tulisan tangan, dengan selisih batas potongan.
**Scope file**: `backend/` (chunker skema), `config/grid`.
**Di luar scope**: parser tulisan tangan (pembanding, tidak diubah).
**Kriteria selesai (testable)**:
- Skema yang sama selalu menghasilkan potongan yang sama (hash).
- Selisih batas terhadap parser tangan dilaporkan per bagian (batang tubuh, Penjelasan).
**Bukti verifikasi yang wajib disetor**: test hijau, tabel selisih batas, frontier.
**Tier review**: 2.
**Estimasi**: 2 jam.
**Status**: berjalan — chunker skema + integrasi grid `a65e1c2` (Tier 2 lulus, `l3/W7-M34-periksa-hasil.md`), test tambahan `8503367`. Bukti: selisih batas v1 UU PT di envelope `runs/grid/58d1864b….json` (same 686, hand_only 1454, schema_only 0); test hijau. Menunggu operator: skema v1 belum disetujui (H-074), tafsir disetujui/aktif (I-50); frontier dengan skema yang disetujui.

## M4 — Transfer ke akta, ekspor (2 Nov)

Prasyarat: H-039 dan H-041. Lima akta pendirian PT sintetis ditulis agen AI (agen pengembang) di repo submission setelah acara mulai, dari brief operator, lalu direview operator. Blanko PPAT tidak dipakai (H-056). Kerangkanya Pasal 38 UU 2/2014: kepala (judul, nomor, waktu, notaris), badan (komparisi, kedudukan bertindak, isi berupa anggaran dasar "Pasal n" mengikuti Pasal 15 UU 40/2007, saksi pengenal), dan penutup (pembacaan, penandatanganan, saksi akta, perubahan). Jumlah Pasal dan ada tidaknya saksi pengenal divariasikan supaya batas bagian teruji. Identitas fiktif tanpa kesamaan dengan pihak nyata, tanpa NIK, dengan disclaimer (H-041). Brief dan review sekitar 1–2 jam kerja operator, di luar slice.

### M4.1 — Skema dan potongan akta
**Slice**: Template akta dimuat. Spark menginduksi skemanya, operator mengoreksi, lalu panel potongan menampilkan akta terpotong menurut skema.
**Scope file**: `data/akta/`, `backend/` (pemakaian ulang A dan chunker skema), `frontend/` (pemilih keluarga).
**Di luar scope**: korpus UU PT.
**Kriteria selesai (testable)**:
- Tidak ada data pribadi nyata di berkas akta. Operator memeriksa.
- Skema akta tersimpan dengan versi, terpisah dari skema UU PT.
**Bukti verifikasi yang wajib disetor**: skema akta v1/v2, screenshot.
**Tier review**: 2, ditambah Tier 4 domain review oleh operator.
**Estimasi**: 2,5 jam.
**Status**: berjalan — pemuat akta, alamat, store skema per keluarga, R2, pemilih keluarga `2e33331` (Tier 2, `l3/W11-M41-periksa-hasil.md`); R4 `schema_version` + tampilan potongan skema akta `df4a545`, `051615e` (Tier 2, `l3/W15-R4-periksa-hasil.md`). Lima akta sintetis `2c81ef9`. Menunggu operator: I-51, I-52, I-55; lalu induksi A akta live (proyeksi 3.408 micro-USD batas atas) → skema v1/v2 + screenshot. Update L2#5: alamat non-Pasal akta dari grup bernama + `schema_address_map` (`fc70679`, Tier 2 L2; belum disambung ke Pipeline). Skema A akta v2: berkas koreksi varian (a)/(b) G-4 teruji lima akta (0 hilang, 0 tumpang tindih), menunggu konfirmasi operator sebelum `correct` (keputusan-pagi butir 1). Peta unit akta di Pipeline: skenario Tier 1 `docs/scenarios/M4.1-akta-unitmap.md` + pemeriksa 2 putaran 0 BLOCKER (`f613bf8`), menunggu operator (butir 2). Update L2#6: skema A akta v2 `source: operator` varian (b) `067809e` (H-089); peta unit akta di Pipeline `7f993fb` (H-090, Tier 1 W59).

### M4.2 — Frontier akta
**Slice**: Butir akta (usulan D disetujui ditambah tulisan operator) dijalankan di grid, dan frontier akta tampil.
**Scope file**: `data/butir/` (akta), `config/grid`.
**Di luar scope**: kode metrik dan grid (dipakai ulang).
**Kriteria selesai (testable)**:
- Minimal lima butir akta disetujui. Butir akta tidak dibagi tune/held-out; semua dilaporkan per butir sebagai uji transfer, dan frontier akta tampil tanpa klaim pemilihan profil (H-054).
- Profil yang diuji di akta adalah profil terbaik UU PT dengan chunker dari skema A akta.
**Bukti verifikasi yang wajib disetor**: frontier akta, tabel per butir.
**Tier review**: 2.
**Estimasi**: 2 jam.
**Status**: berjalan — grid akta multi-dokumen S1–S3 (H-086) `7d2cfef` (Tier 1 W39: 0 BLOCKER; mutan selamat dibunuh `8cf955e`). Terblok operator: I-62 (bentuk `grid` akta, S4), I-63/I-65 (unit dan cakupan Recall@K akta), I-64 (cakupan grid), skema A akta v2 (H-088), header B akta ulang. UI akta menampilkan "Pending operator review" tanpa angka sementara (`d0b19c8`). Update L2#6: **selesai** — header B akta `82ae86f`/`77dab56`/`b811f2d` (store per keluarga, G-38); S4 R3 `{all}` + label degenerate `43f5bc4` (H-091, H-093; W64); grid akta final 36 setting `014765d` (kunci 86e701f5, 84 butir); bukti frontier: R3 akta `grid.all`.

### M4.3 — Ekspor profil dan laporan held-out
**Slice**: Tombol ekspor menghasilkan profil berversi per keluarga. Profil yang dimuat ulang menghasilkan potongan yang identik. Laporan held-out tampil untuk UU PT; laporan akta per butir sebagai uji transfer, tanpa label held-out (H-054).
**Scope file**: `profiles/`, `backend/` (ekspor/impor profil), `frontend/` (tombol ekspor, laporan).
**Di luar scope**: grid.
**Kriteria selesai (testable)**:
- Muat ulang profil → hash potongan sama dengan run asal.
- Profil yang merujuk hash korpus berbeda ditolak dengan pesan jelas.
**Bukti verifikasi yang wajib disetor**: test hijau round-trip, contoh profil UU PT dan akta.
**Tier review**: 1. Profil adalah keluaran yang dijanjikan ke pemakai RAG.
**Estimasi**: 2 jam.
**Status**: berjalan — backend W7/W8 + laporan `f48cbda` (Tier 1, `l3/W7-M43-periksa-hasil.md`, perbaikan W10); U7 panel ekspor/impor `df4a545`, `051615e` (Tier 1 S20, `l3/W15-U7-periksa-hasil.md`). I-42, I-43 ditutup. Sisa: sumber laporan per butir (I-53), setting akta (I-55), contoh profil UU PT dan akta setelah skema/grid final. Update L2#5: contoh profil UU PT `profiles/uupt/d7a9dd24….json` (structure_schema v2 dense B2000; impor ulang `chunk_set_hash_matches: true`, corpus_hash beda ditolak) `25fc358`; perbaikan W7/W8 setting terikat versi skema aktif + W6 replay tidak menulis `runs/answers` `bcf9431` (Tier 1 W52). Profil akta terblok operator (skema akta v2, I-62..I-65). Update L2#6: profil akta setting transfer `91aa993` (round-trip lima akta, W67); laporan transfer akta di R3 `report` (`43f5bc4`).

## M5 — Demo dan submit (3–4 Nov)

### M5.1 — Mode putar ulang dan layar akhir
**Slice**: Layar akhir berjalan dari run tersimpan (`runs/`) dan data (`data/`) tanpa memanggil API, kecuali satu panggilan pendek yang dipilih untuk live (H-050). Disclaimer tampil. Mode putar ulang diekspor sebagai situs statis (frontend + snapshot JSON, tanpa backend, key, atau panggilan model) untuk GitHub Pages (H-051).
**Scope file**: `frontend/`, `backend/` (mode putar ulang, ekspor snapshot).
**Di luar scope**: logika metrik.
**Kriteria selesai (testable)**:
- Dengan API diputus, semua adegan (enam, `docs/VIDEO.md`) tetap bisa diputar.
- Loading, kosong, dan error tertangani di tiga panel.
- Ekspor statis memutar semua adegan dari berkas statis saja; panggilan live W6 tidak ada di versi statis, dan pilihan Glimmer hanya menampilkan hasil tersimpan.
**Bukti verifikasi yang wajib disetor**: screenshot semua adegan dalam mode putar ulang dan dari ekspor statis yang dibuka lokal.
**Tier review**: 2, ditambah Tier 4 UX review atas alur adegan.
**Estimasi**: 2 jam, ditambah sekitar 2–3 jam ekspor statis (H-051) yang belum masuk jumlah Ringkasan; ekspor statis di bawah lantai H-017 (dipotong lebih dulu daripada A–D dan video).
**Status**: berjalan — middleware replay, ekspor statis + pemindai bocor, build statis `2e33331` (Tier 2, `l3/W11-M51-periksa-hasil.md`), perbaikan `25eaf4c`; hint ikut bundel `93525a0`. Uji visual statis lokal 375/768/1440 tanpa scroll horizontal, console 0 error, 0 request `/api` (`_kerja/orkestrasi/bukti/visual-L2-3.txt`). Sisa: adegan 4 (I-54), screenshot semua adegan setelah data operator. Update L2#5: ekspor statis ulang setelah M2.5 (789 berkas data, `--check` 0 temuan; U3 menampilkan jawaban tersimpan Contributor/Spark Open/Glimmer berlabel). Versi statis hanya keluarga UU PT (tanpa pemilih keluarga); akta di mode live menampilkan "Pending operator review" di U2/U4/U7 (bukti `bukti/akta-pending-{1440.jpg,375.png}`, 375/768 tanpa scroll horizontal, console 0 error). Update L2#6: ekspor statis ulang dari 014765d dengan pemilih keluarga (`data/families.json`, 975 berkas, `--check` 0). Uji visual Chrome menunggu extension tersambung. Uji visual L2#6 (28 Okt, Chrome, iframe 375/768/1440): statis HEAD ae7a318 (uupt, akta lewat pemilih Family, review akta) tanpa scroll horizontal, 0 request /api, tanpa banner pending, console 0 error; live akta dan butir K-08 macet Loading karena proxy dev vite `Connection: close` + uvicorn/h11 Windows memotong respons besar (ECONNRESET), diperbaiki dengan agent keep-alive timeout 3 detik (review W71), lalu live akta dan K-08 di tiga lebar terisi, console 0 error. Bukti `_kerja/orkestrasi/bukti/M51-*.jpg`.

### M5.2 — Gate pra-submit
**Slice**: Daftar periksa pra-submit lulus semua dan tercatat di repo.
**Scope file**: README repo submission, lisensi, `.gitignore`.
**Di luar scope**: fitur baru.
**Kriteria selesai (testable)**:
- Syarat Official Rules (repo, video, bahasa) terpenuhi satu per satu.
- Secret scanning bersih. Tidak ada akta asli, dokumen internal, atau data klien.
- README menyebut jumlah butir sebenarnya beserta asalnya, model, dan batas (n kecil, tanpa klaim signifikansi).
- Tidak ada kode prototipe pra-acara yang disalin.
- Bila tokenizer Muse Spark Open dipakai (H-014), README memuat atribusi "Built with Muse Spark Open" (Muse Model License) dan berkas tokenizer tidak di-commit.
- Disclosure README lengkap: Contributor (H-028), konsolidasi UU PT tidak resmi yang disiapkan sebelum acara sampai 30 Desember 2022 dengan daftar sumber (H-031, H-045), akta ditulis agen AI dan direview operator dengan disclaimer identitas fiktif (H-039, H-041), bagian "Built before vs during the hackathon" (H-044). Bila pembanding Glimmer dipakai (H-047): disebut open-weight yang berjalan di mesin operator, bukan bobot Spark, dengan atribusi kartu model; klaim bonus open-weight hanya setelah cara verifikasi "own hardware" dikonfirmasi penyelenggara.
- `LICENSE` Apache-2.0 terpasang, lalu repo dibuka publik setelah secret scan (H-029).
- Isi snapshot ekspor statis diperiksa: tanpa key, tanpa path lokal. Situs dipasang di GitHub Pages setelah repo publik, dan README memuat tautannya dengan keterangan bahwa versi web adalah replay (H-051).
**Bukti verifikasi yang wajib disetor**: daftar periksa terisi, hasil secret scan.
**Tier review**: Tier 4 security review.
**Estimasi**: 2 jam.
**Status**: berjalan (persiapan) — README draf submission `585880d`; daftar periksa terisi di `_kerja/orkestrasi/l3/W13-M52-siap-hasil.md` (secret scan tree + histori `main` 0; snapshot statis `--check` 0). Menunggu operator/L1: `LICENSE` Apache-2.0 resmi, kutipan Official Rules, review akta (I-51), n final setelah review D, tautan Pages, push/publik (H-029, H-051). Update L2#6: daftar periksa baru `_kerja/orkestrasi/M52-gate-L2-6.md` (secret scan tree + histori + dist-static 0; path lokal di docs dibersihkan); README angka akta final (review W69). Sisa milik operator: LICENSE, publik, Pages, kutipan Official Rules; email pribadi di metadata commit dan path lokal di histori lama (keputusan operator).

### M5.3 — Video (operator)
**Slice**: Video direkam dari mode putar ulang mengikuti storyboard dan jadwal produksi di `docs/VIDEO.md`, dengan butir adegan yang sudah dicocokkan manual ke teks.
**Kriteria selesai (testable)**: gate sebelum unggah di `docs/VIDEO.md` terisi semua, durasi ≤ 3 menit (Participant Guide, H-043), dan angka di video cocok dengan layar.
**Estimasi**: 7 jam. Rinciannya: kunci storyboard 31 Okt, rekaman kasar 2 Nov, produksi 4 Nov.
**Status**: dipisah — video ditangani operator (putusan operator 8, 27 Okt); agen tidak menyiapkan bahan video dan tidak mengunci storyboard.

M5.1 dan M5.2 dikerjakan 3 Nov, dan kode dibekukan 20:00 WIB. 4 Nov untuk video dan submit. Target submit 4 Nov malam WIB, batas resmi 5 Nov 09:00 WIB.

## Kontrak untuk agen eksekutor

Kalau slice dikerjakan oleh agen AI, prompt per slice memuat:
- Pointer ke `docs/MILESTONES.md` dan keputusan terkait. Pointer, bukan salinan.
- Slice, kriteria selesai, scope file, dan larangan file.
- Perintah menulis test-nya juga, dan menyetor bukti, bukan klaim.
- Untuk slice Tier 1, skenario test yang sudah disetujui operator (H-052), bukan dipilih penulis kode.
- Larangan tetap: tidak menulis butir, tabel status, atau koreksi skema; tidak menyalin kode prototipe pra-acara; tidak memasukkan secret.
