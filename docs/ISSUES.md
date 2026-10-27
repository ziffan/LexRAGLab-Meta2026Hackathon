# ISSUES — pertanyaan terbuka bernomor

Tujuan: mencatat setiap pertanyaan terbuka dengan rekomendasi, owner, dan batas, supaya tidak ada pilihan yang dikunci diam-diam.
Sumber keputusan: H-044.

Aturan: rekomendasi di sini **bukan** keputusan. Yang dikunci operator dicatat di log keputusan operator, lalu di `docs/DECISIONS.md`, lalu isu dipindah ke "Ditutup" dengan tanggal. ID I-01 sampai I-24 sudah dipakai di catatan perencanaan pra-acara (rujukannya di `docs/DECISIONS.md`); isu baru mulai dari I-25.

## Menunggu operator

| ID | Pertanyaan | Rekomendasi | Owner | Batas |
|---|---|---|---|---|
| I-47 | Header B > 40 token (`config/header_b.toml` `max_header_tokens`) setelah 4 upaya: Pasal 128 UU PT (343 unit Pasal, 342 berheader) dan 3 dari 103 potongan `fixed_size`. Grid uji 27 Okt `--with-headers --with-schema` (`runs/grid/58d1864b….json`): **semua 9 kembaran header-on (frontier_only) gagal `header_missing`** — 6 karena Pasal 128 (struktur tangan dan skema), 3 karena satu potongan fixed_size. Deret header-on U2 kosong; M3.2 tidak bisa menunjukkan perbandingan on/off | (a) biarkan gagal (jujur, H-069), tetapi deret on kosong di demo; (b) **Rekomendasi**: naikkan batas validasi (mis. 60) dan panggil ulang hanya 4 unit gagal (±1.000 micro-USD); token header tetap dihitung anggaran (H-004), 4 header lebih panjang dari 40 tercatat; (c) potong header ke 40 token (mengubah keluaran Spark, tidak disarankan); (d) unit tanpa header dikemas tanpa header dan ditandai (mengubah aturan akuntansi M3.2, perlu skenario ulang) | Operator | Sebelum grid `--with-headers` yang dilaporkan |
| I-48 | U2: frontier digambar sebagai satu garis gabungan lintas deret header on/off; spec (UI-SPEC U2, M3.2) diam apakah frontier per deret atau gabungan. Kode `compute_frontiers` mengelompokkan per (family, split, budget) tanpa `header_b`, jadi gabungan konsisten dengan backend | **Rekomendasi**: gabungan (pertanyaan produk "setting mana yang optimal" mencakup header sebagai sumbu, H-058); tambah satu kalimat di UI-SPEC U2. Alternatif: frontier per deret (perlu perubahan backend frontier, mengubah angka laporan) | Operator | Sebelum screenshot U2 untuk video |
| I-49 | Review teks hint H-073 (`frontend/src/content/hints.json` 0.2.0, status `draft`; tabel baca `_kerja/orkestrasi/hint-draf-review.md`, termasuk bagian "Perubahan 0.2.0 untuk operator"). Sudah diperiksa pemeriksa independen (1 BLOCKER + 9 SHOULD diperbaiki) | Operator menilai gloss hukum, klaim tujuan (`app.purpose`, `app.audience`), klaim model (`model.*`, termasuk "open-weight"), `status.*`, `verifier.matrix_2x2`; lalu `status` → `final` | Operator | Sebelum video (M5.3) |
| I-50 | Tafsir skema A "aktif" dan "disetujui" di grid M3.4 (`backend/grid/schemas.py`): aktif = versi `source: operator` tertinggi, else Spark tertinggi; disetujui = `source: operator` atau flag `operator_approved`. Pemeriksa: flag itu tidak ada di `SchemaRecord` (DATA-CONTRACTS §6) dan tidak masuk hash identitas (envelope cache bisa basi); menyimpan koreksi lewat W9 sama dengan menyetujui | **Rekomendasi**: disetujui = hanya versi `source: operator` (koreksi W9 atau berkas H-055); hapus jalur flag `operator_approved`; persetujuan v1 tanpa perubahan = operator menyimpan salinan v1 lewat W9 dengan `operator_note` | Operator | Sebelum grid `--with-schema` yang dilaporkan |
| I-51 | Review operator lima akta sintetis `data/akta/akta-01.txt` … `akta-05.txt` (H-039, H-041; addendum 2 gerbang 4) sebelum dipakai di run yang dilaporkan. Ditulis agen dari `data/akta/BRIEF.md`; pemeriksa independen 0 BLOCKER, 2 SHOULD diperbaiki (nama mirip tokoh diganti, hitungan renvoi akta-03). Variasi: Pasal 14/17/20/22/25; tanpa saksi pengenal akta-02, 04; renvoi akta-03; 4 pemegang saham akta-05; total 17.241 token lokal | Operator memeriksa: kemiripan nama/PT/notaris dengan pihak nyata (agen tanpa jaringan), kewajaran hukum, modal dasar terhadap aturan pasca UU 6/2023 (belum diverifikasi agen), alamat rekaan | Operator | Sebelum M4.1 run yang dilaporkan |
| I-42 | Pemeriksa M4.3 C7: kunci cache `runs/chunks/` (ARCHITECTURE §8) tidak memuat tokenizer; `Chunk[]` dari tokenizer lain bisa tersaji. Kunci chunker sekarang sudah memuat nama + versi tokenizer (`backend/chunking/structure.py` `structure_key`), perlu dipastikan untuk jalur cache `runs/chunks/` | Eksekutor M4.3 memastikan kunci cache = `chunker_key` (memuat tokenizer); bila ARCHITECTURE §8 perlu diubah, itu redaksi spec tanpa keputusan baru | Agen (M4.3) | Sebelum kode M4.3 |
| I-43 | M4.3 A20: `dense.chunk_set_hash` (kunci cache embedding, ARCHITECTURE §8) berbeda dari `Profile.chunk_set_hash` (A2-X, H-068); dua fungsi bernama sama | Ganti nama salah satu di kode M4.3 (mis. `embedding_cache_key`) tanpa mengubah nilai kunci cache embedding yang ada | Agen (M4.3) | Sebelum kode M4.3 |

## Ditutup

| ID | Pertanyaan (ringkas) | Penutupan | Tanggal |
|---|---|---|---|
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
