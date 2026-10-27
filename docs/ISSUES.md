# ISSUES — pertanyaan terbuka bernomor

Tujuan: mencatat setiap pertanyaan terbuka dengan rekomendasi, owner, dan batas, supaya tidak ada pilihan yang dikunci diam-diam.
Sumber keputusan: H-044.

Aturan: rekomendasi di sini **bukan** keputusan. Yang dikunci operator dicatat di log keputusan operator, lalu di `docs/DECISIONS.md`, lalu isu dipindah ke "Ditutup" dengan tanggal. ID I-01 sampai I-24 sudah dipakai di catatan perencanaan pra-acara (rujukannya di `docs/DECISIONS.md`); isu baru mulai dari I-25.

## Menunggu operator

| ID | Pertanyaan | Rekomendasi | Owner | Batas |
|---|---|---|---|---|
| I-41 | H-063 (f6e2912): panggilan logis yang timeout di dua upaya (retry timeout) diproyeksikan satu kali. Timeout memutus sisi klien; server bisa menagih tiap upaya, jadi buku bisa undercount sampai 2x proyeksi per panggilan logis. Juga: timeout lalu sukses hanya menagih usage upaya kedua. Temuan SHOULD pemeriksa Tier 1 (`_kerja/orkestrasi/l3/W1-H063-periksa.md`) | Proyeksi per upaya yang timeout (konservatif, T6): timeout 2 upaya = 2 × proyeksi; timeout lalu sukses = usage + 1 × proyeksi. Alt.: biarkan satu kali (skenario A1 sekarang). Dampak kecil: harga Contributor rendah, tapi cap bisa terlewati | Operator | Sebelum batch Spark besar (M3.1 penuh) |
| I-42 | Pemeriksa M4.3 C7: kunci cache `runs/chunks/` (ARCHITECTURE §8) tidak memuat tokenizer; `Chunk[]` dari tokenizer lain bisa tersaji. Kunci chunker sekarang sudah memuat nama + versi tokenizer (`backend/chunking/structure.py` `structure_key`), perlu dipastikan untuk jalur cache `runs/chunks/` | Eksekutor M4.3 memastikan kunci cache = `chunker_key` (memuat tokenizer); bila ARCHITECTURE §8 perlu diubah, itu redaksi spec tanpa keputusan baru | Agen (M4.3) | Sebelum kode M4.3 |
| I-43 | M4.3 A20: `dense.chunk_set_hash` (kunci cache embedding, ARCHITECTURE §8) berbeda dari `Profile.chunk_set_hash` (A2-X, H-068); dua fungsi bernama sama | Ganti nama salah satu di kode M4.3 (mis. `embedding_cache_key`) tanpa mengubah nilai kunci cache embedding yang ada | Agen (M4.3) | Sebelum kode M4.3 |
| I-44 | H-067 V5 (i) + H-062: label potongan multi-unit di konteks C hanya memuat alamat unit pertama dan terakhir (`A – B`). Kutipan dari unit tengah potongan `fixed_size` tidak punya alamat unit yang terlihat model, jadi pasti gagal uji 1 (alamat karangan) atau uji 2 (alamat ujung). Setting non-struktural tampak lebih buruk di sel "Answered, unsupported" karena cara memberi label, bukan isi potongan; ini bertentangan dengan prinsip keadilan MILESTONES (penanda alamat sama untuk semua chunker). Dicatat sebagai batas di skenario M2.3 S42 | Perakit konteks menyisipkan label alamat unit di setiap awal unit di dalam potongan multi-unit (label tidak dihitung anggaran, H-066; potongan struktur = satu unit sehingga tidak berubah); prompt C v2 tetap "salin alamat unit". Alt.: biarkan, nyatakan sebagai batas di laporan. Mengubah angka laporan (sel 2×2 kolom pembanding) | Operator | Sebelum run C yang dilaporkan (M2.3) |
| I-45 | M3.3 backend (peran A): (1) `SchemaRecord` diberi field tambahan `created_at`, `operator_note`, `sample`, `sample_checked`, `cache_key` di luar DATA-CONTRACTS §6; (2) induksi Spark dengan sampel berbeda menambah versi `source: spark`, jadi "v1 = Spark, v2+ = koreksi" tidak mutlak; (3) keluaran Spark yang gagal validasi semantik hanya tercatat di `RunRecord` error, isinya tidak disimpan untuk dilihat operator; (4) W9 di mode replay → `400 invalid_request` (API.md belum punya kode); (5) aturan semantik tambahan di luar SPARK-ROLES §2: `order` naik ketat, `parent_order` menunjuk order lebih awal, `default_chunk_level` harus level potong, tolak regex kuantor bersarang | (1) masukkan ke §6 sebagai field sistem informatif; (2) versi dinomori urut, `source` membedakan; (3) simpan keluaran gagal sebagai berkas `rejected` terpisah (bukan `SchemaRecord`) agar U5 bisa menampilkannya; (4) `409 replay_mode` atau tetap 400 dan dicatat di API.md; (5) terima sebagai validasi sistem. Tidak mengubah angka laporan | Operator | Sebelum panggilan A yang dilaporkan |

## Ditutup

| ID | Pertanyaan (ringkas) | Penutupan | Tanggal |
|---|---|---|---|
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
