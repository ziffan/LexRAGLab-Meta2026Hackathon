# ISSUES — pertanyaan terbuka bernomor

Tujuan: mencatat setiap pertanyaan terbuka dengan rekomendasi, owner, dan batas, supaya tidak ada pilihan yang dikunci diam-diam.
Sumber keputusan: H-044.

Aturan: rekomendasi di sini **bukan** keputusan. Yang dikunci operator dicatat di log keputusan operator, lalu di `docs/DECISIONS.md`, lalu isu dipindah ke "Ditutup" dengan tanggal. ID I-01 sampai I-24 sudah dipakai di catatan perencanaan pra-acara (rujukannya di `docs/DECISIONS.md`); isu baru mulai dari I-25.

## Menunggu operator

| ID | Pertanyaan | Rekomendasi | Owner | Batas |
|---|---|---|---|---|
| I-49 | Review teks hint H-073 (`frontend/src/content/hints.json` 0.2.0, status `draft`; tabel baca `_kerja/orkestrasi/hint-draf-review.md`, termasuk bagian "Perubahan 0.2.0 untuk operator"). Sudah diperiksa pemeriksa independen (1 BLOCKER + 9 SHOULD diperbaiki) | Operator menilai gloss hukum, klaim tujuan (`app.purpose`, `app.audience`), klaim model (`model.*`, termasuk "open-weight"), `status.*`, `verifier.matrix_2x2`; lalu `status` → `final` | Operator | Sebelum video (M5.3) |
| I-51 | Review operator lima akta sintetis `data/akta/akta-01.txt` … `akta-05.txt` (H-039, H-041; addendum 2 gerbang 4) sebelum dipakai di run yang dilaporkan. Ditulis agen dari `data/akta/BRIEF.md`; pemeriksa independen 0 BLOCKER, 2 SHOULD diperbaiki (nama mirip tokoh diganti, hitungan renvoi akta-03). Variasi: Pasal 14/17/20/22/25; tanpa saksi pengenal akta-02, 04; renvoi akta-03; 4 pemegang saham akta-05; total 17.241 token lokal | Operator memeriksa: kemiripan nama/PT/notaris dengan pihak nyata (agen tanpa jaringan), kewajaran hukum, modal dasar terhadap aturan pasca UU 6/2023 (belum diverifikasi agen), alamat rekaan | Operator | Sebelum M4.1 run yang dilaporkan |
| I-54 | Adegan 4 (jawaban C, verifier, 2×2) belum bisa diputar di replay/statis: jawaban tersimpan K-02 dibuat sebelum chunker v2 (`8e94269`, H-062/H-064), sehingga kunci cache tidak cocok (perilaku benar, diagnosa `_kerja/orkestrasi/l3/W11-W6replay-diagnosa-hasil.md`). Belum ada butir `scene_checked = true` di `data/butir/` (H-050) | Operator: (1) tandai butir demo `scene_checked`; (2) putus I-47 dan I-50 (menentukan setting terbaik); lalu agen menjalankan C live prompt v2 untuk butir demo (proyeksi ±1.582 micro-USD per butir, best + baseline) dan mengekspor ulang | Operator | 31 Okt (kunci storyboard) |

## Ditutup

| ID | Pertanyaan (ringkas) | Penutupan | Tanggal |
|---|---|---|---|
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
