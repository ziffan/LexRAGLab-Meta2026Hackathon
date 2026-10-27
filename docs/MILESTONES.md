# MILESTONES — milestone, slice, dan status

Tujuan: daftar milestone dan atomic vertical slice dengan kriteria selesai testable, bukti wajib, tier review, dan status terkini.
Sumber keputusan: H-004, H-005, H-006, H-009, H-011, H-012, H-013, H-014, H-015, H-016, H-017, H-018, H-028, H-029, H-031, H-032, H-033, H-037, H-038, H-039, H-040, H-041, H-042, H-043, H-045, H-046, H-047, H-048, H-049, H-050, H-051, H-052, H-053, H-054, H-055, H-056.

Status slice dicatat **di sini**. Kalau bentrok dengan `docs/DECISIONS.md`, keputusan yang menang.

Nilai status: `belum mulai` · `berjalan` · `selesai` (dengan sha + bukti) · `dipotong` (dengan pemicu H-017) · `stretch`.

## Ringkasan

| Milestone | Tanggal | Isi | Slice | Estimasi (jam, sudah × 1,5) | Status |
|---|---|---|---|---|---|
| M0 Fondasi | 26 Okt malam–27 Okt | Official Rules, repo, klien Spark, korpus terukur | 2 | 4 | selesai 27 Okt |
| M1 Grid tanpa LLM, UU PT | 27–29 Okt | Chunker, tiga mode retrieval, metrik, frontier | 5 | 13 | berjalan |
| M2 Spark D dan C | 29–31 Okt | Usulan butir, jawaban ujung ke ujung, verifier | 4 | 10 | berjalan (skenario Tier 1 menunggu operator) |
| M3 Spark B dan A, UU PT | 31 Okt–1 Nov | Header konteks, induksi skema, editor skema | 4 | 11 | belum mulai |
| M4 Transfer ke akta, ekspor | 2 Nov | Skema akta, frontier akta, profil berversi | 3 | 6,5 | belum mulai |
| M5 Demo dan submit | 3–4 Nov | Mode putar ulang dan gate (3 Nov), video (4 Nov) | 3 | 11 | belum mulai |
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
**Status**: berjalan — kode `4e18c57` (+ kunci tokenizer `8450e1d`), review Tier 2 independen boleh dipromosikan (`_kerja/orkestrasi/l3/G3-periksa.md`). Screenshot `_kerja/orkestrasi/bukti/M1.1-*.png`. Belum selesai: golden sample menunggu konfirmasi operator (I-36); fixed_size per section (I-35) dan heading Pasal di luar potongan (I-38) menunggu operator.

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
**Status**: berjalan — kalkulator + BM25 `5b9bb04`, `6c4e19b`; review Tier 1 0 BLOCKER (`l3/G4a-periksa.md`); integrasi `8450e1d`. Sisa: tabel per butir UI (frontend berjalan), review integrasi.

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
**Status**: berjalan — dense bge-m3 GPU + hybrid RRF `bd7a9bf`, `dc8a5c5`; review Tier 2 boleh dipromosikan (`l3/G5-periksa.md`). Sisa: pemilih mode UI.

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
**Status**: berjalan — split/frontier/pemilihan `1aac9e7`, `f970448` (review Tier 1 dua putaran, 0 BLOCKER); run grid UU PT nyata `8450e1d` (`runs/grid/b8d0d6ea….json`, 12 setting dijalankan, 24 dilewati sampai M3; split v1 tune 5 / held-out 4). Sisa: grafik frontier UI, review Tier 1 integrasi, I-35/I-38 sebelum run yang dilaporkan.

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
**Status**: berjalan — metrik `2e90254` (review Tier 1), Recall@K produksi `8450e1d` (S-1); QualityMetrics run nyata di `runs/grid/b8d0d6ea….json`. Sisa: panel UI.

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
**Status**: belum mulai.

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
**Status**: berjalan — backend + W6 + prompt C v1 `a61f7c9`, test review `2e59f6f`; review Tier 2 boleh dipromosikan (`_kerja/orkestrasi/l3/M22-periksa.md`). Bukti live K-02: `runs/spark/records/18b443f5….json` (577) dan `6b318801….json` (506), ulangan cached 0. Sisa: panel bukti U3 (frontend), I-40 (label alamat di luar anggaran).

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
**Status**: belum mulai.

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
**Status**: stretch. Dikerjakan hanya setelah lantai H-017 aman; dipotong lebih dulu daripada lantai. Sejak H-060 pembanding C juga Spark Open di Baseten (profil `baseten_open`); smoke 27 Okt: Responses + strict didukung (G-33), Chat Completions tidak dipakai untuk Baseten.

## M3 — Spark B dan A, UU PT (31 Okt–1 Nov)

### M3.1 — Header B untuk satu dokumen, biaya, dan waktu
**Slice**: Untuk satu dokumen (UU PT), Spark menulis header konteks per potongan dengan dokumen di-cache, lalu layar menampilkan header, token cached, biaya, dan waktu per granularitas (pasal vs ayat).
**Scope file**: `prompts/b`, `backend/` (pemanggil B), `runs/`.
**Di luar scope**: grid.
**Kriteria selesai (testable)**:
- Panggilan kedua dan seterusnya untuk dokumen sama menunjukkan cache hit.
- Proyeksi biaya dan waktu (pada 150 RPM, H-028) seluruh korpus tercatat untuk dua granularitas.
- Sampel header per granularitas tersedia untuk dinilai mutunya oleh operator (H-038).
**Bukti verifikasi yang wajib disetor**: catatan run, proyeksi biaya.
**Tier review**: 2.
**Estimasi**: 1,5 jam.
**Status**: belum mulai.

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
**Status**: belum mulai.

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
**Status**: belum mulai.

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
**Status**: belum mulai.

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
**Status**: belum mulai.

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
**Status**: belum mulai.

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
**Status**: belum mulai.

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
**Status**: belum mulai.

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
**Status**: belum mulai.

### M5.3 — Video (operator)
**Slice**: Video direkam dari mode putar ulang mengikuti storyboard dan jadwal produksi di `docs/VIDEO.md`, dengan butir adegan yang sudah dicocokkan manual ke teks.
**Kriteria selesai (testable)**: gate sebelum unggah di `docs/VIDEO.md` terisi semua, durasi ≤ 3 menit (Participant Guide, H-043), dan angka di video cocok dengan layar.
**Estimasi**: 7 jam. Rinciannya: kunci storyboard 31 Okt, rekaman kasar 2 Nov, produksi 4 Nov.
**Status**: belum mulai.

M5.1 dan M5.2 dikerjakan 3 Nov, dan kode dibekukan 20:00 WIB. 4 Nov untuk video dan submit. Target submit 4 Nov malam WIB, batas resmi 5 Nov 09:00 WIB.

## Kontrak untuk agen eksekutor

Kalau slice dikerjakan oleh agen AI, prompt per slice memuat:
- Pointer ke `docs/MILESTONES.md` dan keputusan terkait. Pointer, bukan salinan.
- Slice, kriteria selesai, scope file, dan larangan file.
- Perintah menulis test-nya juga, dan menyetor bukti, bukan klaim.
- Untuk slice Tier 1, skenario test yang sudah disetujui operator (H-052), bukan dipilih penulis kode.
- Larangan tetap: tidak menulis butir, tabel status, atau koreksi skema; tidak menyalin kode prototipe pra-acara; tidak memasukkan secret.
