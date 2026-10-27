# ISSUES — pertanyaan terbuka bernomor

Tujuan: mencatat setiap pertanyaan terbuka dengan rekomendasi, owner, dan batas, supaya tidak ada pilihan yang dikunci diam-diam.
Sumber keputusan: H-044.

Aturan: rekomendasi di sini **bukan** keputusan. Yang dikunci operator dicatat di log keputusan operator, lalu di `docs/DECISIONS.md`, lalu isu dipindah ke "Ditutup" dengan tanggal. ID I-01 sampai I-24 sudah dipakai di catatan perencanaan pra-acara (rujukannya di `docs/DECISIONS.md`); isu baru mulai dari I-25.

## Menunggu operator

| ID | Pertanyaan | Rekomendasi | Owner | Batas |
|---|---|---|---|---|
| I-66 | Cakupan keluarga `Item.mode = "tolak"` (H-092): enum lintas keluarga, padahal usulan `unanswerable` hanya akta (P13). Bila butir UU PT ber-`tolak` ditulis, strata `SplitRecord` (`origin`, `mode`) dan komposisi held-out UU PT berubah | Sementara (skenario revisi 3): `tolak` hanya sah untuk `akta`, validator menolak `uupt` + `tolak`; tidak mengubah angka apa pun karena belum ada butir semacam itu. Alternatif: semua keluarga, dampak strata dicatat dan penugasan lama tetap per DATA-CONTRACTS §4. Mengubah angka laporan: tidak sekarang | operator | sebelum butir tolak UU PT ditulis (tidak memblokir) |

## Ditutup

| ID | Pertanyaan (ringkas) | Penutupan | Tanggal |
|---|---|---|---|
| I-65 | Recall@K akta selalu null (`recall_items = held_out`) | Operator: (a) keluarga tanpa split, semua butir ber-gold, label "transfer"; UU PT tetap held-out (H-090) | 2026-10-28 |
| I-64 | Cakupan grid akta | Operator: (a) seluruh `config/grid` 36 titik, setting transfer disorot (H-091) | 2026-10-28 |
| I-63 | Unit akta untuk Recall@K dan boundary | Operator: (a) unit = potongan skema A akta aktif; skenario M4.1-akta-unitmap disetujui (H-090) | 2026-10-28 |
| I-62 | Bentuk `grid` akta di R3 + setting laporan transfer | Operator: (a) `{all: {points, frontier}}`, setting = structure_schema skema akta aktif + profil terbaik UU PT (H-091) | 2026-10-28 |
| I-61 | Grid akta: retrieval per akta atau lintas lima akta | Operator: per akta, `doc_id` per butir, grid per dokumen diagregasi per keluarga (H-086) | 2026-10-27 |
| I-59 | Revisi hint `app.purpose` (motivasi, putusan 8) | Operator: 1.1.0 disetujui apa adanya, `status` final; agregat LDD = Engagement A + B (keduanya LDD) (tanpa H) | 2026-10-27 |
| I-54 | Butir demo `scene_checked` dan jawaban C untuk adegan 4 | Operator: K-09, K-01, K-08 sebagai butir demo app (data v13); C live sesudah grid v2 (H-085) | 2026-10-27 |
| I-60 | Skema A UU PT v2: kontrak parent_order, Buku, chunk_id/B ulang, premis Penjelasan | Operator: varian (ii) tanpa Buku, semantik terdekat di DATA-CONTRACTS §6, Penjelasan seperti v1 (section terpisah), B ulang 343 (H-084) | 2026-10-27 |
| I-51 | Review lima akta sintetis `data/akta/akta-01..05.txt` | Operator: kelima akta disetujui (H-039, H-041); boleh dipakai di run yang dilaporkan (putusan operator 7, tanpa H) | 2026-10-27 |
| I-49 | Review teks hint H-073 | Operator: konten hint disetujui; `hints.json` 1.0.0 `final` (putusan operator 6, tanpa H) | 2026-10-27 |
| I-58 | Premis H-080 "input B identik" keliru (input B memuat `chunk_id` dan ALAMAT) | Operator: opsi (c), B dipanggil untuk semua 343 potongan skema, tanpa reuse (H-082) | 2026-10-27 |
| I-57 | Gagal header B v2 vs v1; satu potongan fixed_size | Operator: ulang sampai 8 upaya, lalu gagal jujur tanpa fallback v1 (H-081) | 2026-10-27 |
| I-56 | Potongan structure_schema tanpa header B | Operator: opsi (a) bersyarat, reuse hanya bila rentang dan teks identik; selain itu B sendiri; `reused_from` di identitas store (H-080) | 2026-10-27 |
| I-47 | Header B > 40 token (Pasal 128, 3 potongan fixed_size; semua kembaran header-on gagal) | Operator: opsi B, prompt B v2 + regenerasi, batas tetap 40 (H-079); analisis penyebab `_kerja/orkestrasi/l3/I-47-analisis.md` | 2026-10-27 |
| I-55 | Celah spec U7 dan R4 | Operator: rekomendasi diterima (H-078); API.md R4 diredaksi; teks hint transfer menyusul | 2026-10-27 |
| I-53 | Sumber data laporan held-out (U7) | Operator: rekomendasi diterima, laporan sebagai field `report` di R3 (H-077); kode menyusul | 2026-10-27 |
| I-52 | Konvensi pemuat dan alamat akta | Operator: rekomendasi diterima; DATA-CONTRACTS §2 diredaksi (H-076) | 2026-10-27 |
| I-50 | Tafsir skema A disetujui/aktif | Operator: rekomendasi diterima (H-075); kode `operator_approved` dihapus menyusul | 2026-10-27 |
| I-48 | Frontier U2 per deret header atau gabungan | Operator: gabungan lintas deret on/off; satu kalimat ditambahkan di UI-SPEC U2 (tanpa perubahan kode; konsisten dengan `compute_frontiers`). Dikonfirmasi operator sesi 27 Okt (lewat orkestrator); dicatat agen | 2026-10-27 |
| I-43 | `dense.chunk_set_hash` vs `Profile.chunk_set_hash` | Diselesaikan agen M4.3: fungsi dense diganti nama `embedding_set_hash`, nilai kunci cache embedding tidak berubah (test `test_i43_*`); ARCHITECTURE §8 diselaraskan (`f48cbda`) | 2026-10-27 |
| I-42 | Kunci cache `runs/chunks/` tanpa tokenizer | Diselesaikan agen M4.3: `fixed_key`, `structure_key`, `schema_key` memuat nama + versi tokenizer (test `test_i42_*`); ARCHITECTURE §8 diredaksi `chunker_key` (tanpa keputusan baru) | 2026-10-27 |
| I-46 | Brief operator untuk akta sintetis (H-039) | Operator menyetujui draf apa adanya; disalin ke `data/akta/BRIEF.md` | 2026-10-27 |
| I-41 | Proyeksi retry timeout satu kali | Operator: per upaya yang timeout (H-071) | 2026-10-27 |
| I-44 | Label unit tengah potongan multi-unit di konteks C | Operator: sisipkan label alamat unit di awal setiap unit (H-070) | 2026-10-27 |
| I-45 | Celah kontrak SchemaRecord/W9 (M3.3) | Operator: rekomendasi diterima (H-072) | 2026-10-27 |
| I-38 | Heading Pasal di luar potongan struktur | Operator: alt. 1, potongan ayat pertama mencakup heading; unit alamat A4 tetap (H-064) | 2026-10-27 |
| I-39 | Cakupan butir Recall@K panel M1.5 | Operator: held-out saja untuk angka hasil, tune berlabel; `[quality].recall_items` (H-065) | 2026-10-27 |
| I-40 | Label alamat di luar anggaran konteks C; `flags` | Operator: anggaran = teks sumber, token input aktual per kolom di U3, `flags` informatif di §8 (H-066) | 2026-10-27 |
| I-35 | fixed_size per section ≈ per Pasal | Operator: alt. B, jendela lintas Pasal dan section (H-062); grid diulang setelah I-38 | 2026-10-27 |
| I-36 | Golden sample dan konvensi unit M1.1 | Operator menyetujui sampel (Pasal 1, 7, 86 + Penjelasan, 102 ayat (1), 142 ayat (2), 153A, Pasal 2 tanpa ayat) dan konvensi (Penjelasan tanpa "Ayat (n)" satu unit, Penjelasan Umum satu unit, huruf/angka hanya alamat); tanda menunggu di test dihapus | 2026-10-27 |
| I-37 | Panggilan gagal tanpa usage tercatat 0 di buku belanja | Operator: isi `projected_cost_usd_micros` juga pada panggilan gagal tanpa usage; guard `cost ?? projected` (H-063) | 2026-10-27 |
| I-31 | M1.5 A12 K = 0 | Operator: K0-a, Recall@0 = 0,0 (H-061); tanda menunggu di test M1.5 dihapus | 2026-10-27 |
| I-33 | GridPoint agregat tanpa butir bergold | Operator: `mean_span_recall`, `mrr`, `mean_retrieved_tokens` `number \| null` (H-061) | 2026-10-27 |
| I-34 | Harga Spark Open Baseten belum dipin | Operator: input $1.25, cached $0.15, output $4.25 per 1M (dashboard Baseten, disalin operator 27 Okt) → `[pricing.baseten_open]`; biaya smoke dihitung ulang 1.702 micro-USD | 2026-10-27 |
| I-32 | AGENTS.md belum memuat izin H-060 (Spark Open Baseten peran C, fallback Chat Completions, key Baseten) | Operator menyetujui teks; diterapkan L1 di `e6f9bad` (hanya AGENTS.md) | 2026-10-27 |
| I-25 | Jalur dev OpenRouter diblok guardrail (G-29) | Operator: tinggalkan OpenRouter; dev dan uji lewat Meta Model API. Profil `openrouter_dev` tetap di `config/model`, tidak dipakai | 2026-10-27 |
| I-26 | Baseline "input kosong" kalibrasi tidak terukur (G-30) | Operator menyetujui metode selisih dua titik terhadap teks acuan; `config/tokenizer` `status = "disetujui"` | 2026-10-27 |
| I-27 | Persetujuan skenario Tier 1 M1.2, M1.4, M1.5 | Disetujui operator; default "Dipilih" berlaku; M1.4 A12 alt. (b), M1.5 A5 alt. N1, M1.2 A3 default (H-059). M1.5 A12 (K = 0) tersisa sebagai I-31 | 2026-10-27 |
| I-28 | AGENTS.md tanpa pengecualian OpenRouter | Operator menambahkan "kecuali key OpenRouter untuk dev dan uji (H-057)" pada "Tanpa key kedua" | 2026-10-27 |
| I-29 | Enum `provider` §12 tanpa `openrouter` | `openrouter` ditambahkan ke DATA-CONTRACTS §12 (putusan O-4 M0.1) | 2026-10-27 |
| I-30 | M0.2 hash di mesin kedua | Mesin kedua (Linux) di `9d13586`: hash mentah `a6b38ee5…` dan `clean_sha256` `c56e4f0f38a4…` cocok (`docs/CONTEXT.md` Lingkungan); laptop dev juga 90 passed | 2026-10-27 |
