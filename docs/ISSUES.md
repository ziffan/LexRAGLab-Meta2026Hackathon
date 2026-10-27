# ISSUES — pertanyaan terbuka bernomor

Tujuan: mencatat setiap pertanyaan terbuka dengan rekomendasi, owner, dan batas, supaya tidak ada pilihan yang dikunci diam-diam.
Sumber keputusan: H-044.

Aturan: rekomendasi di sini **bukan** keputusan. Yang dikunci operator dicatat di log keputusan operator, lalu di `docs/DECISIONS.md`, lalu isu dipindah ke "Ditutup" dengan tanggal. ID I-01 sampai I-24 sudah dipakai di catatan perencanaan pra-acara (rujukannya di `docs/DECISIONS.md`); isu baru mulai dari I-25.

## Menunggu operator

| ID | Pertanyaan | Rekomendasi | Owner | Batas |
|---|---|---|---|---|
| I-38 | Run grid UU PT pertama (`runs/grid/b8d0d6ea….json`, 8450e1d): entity preservation `structure_handwritten` 652/901 vs `fixed_size` 896/901. Dugaan: potongan struktur = unit ayat tanpa heading `### Pasal n` (konvensi peta U, M1.2 A4 disetujui), jadi entitas "Pasal n" di heading jatuh di luar semua potongan; heading juga tidak bisa dicocokkan BM25/dense. A4 mengatur peta alamat untuk Recall@K, bukan batas potongan | Alt. 1: potongan ayat pertama tiap Pasal mencakup heading (batas potongan ≠ unit alamat; Recall@K tetap memakai unit A4). Alt. 2: biarkan, entitas heading dikecualikan dari E (EVAL-SPEC §7 diubah). Alt. 3: biarkan apa adanya. Rekomendasi alt. 1. Mengubah angka laporan; grid tanpa LLM murah diulang | Operator | Sebelum run grid yang dilaporkan |
| I-37 | Buku belanja M0.1: panggilan gagal tanpa `usage` (timeout, 5xx, galat koneksi) tercatat dengan `cost_usd_micros` dan `projected_cost_usd_micros` `null`, sehingga belanja = 0 untuk panggilan itu. Server mungkin sudah menagih (timeout setelah generasi), jadi buku bisa undercount sampai sebesar proyeksi per panggilan. Skenario M0.1 S5 hanya mengatur `usage_invalid` (O-3 A). Temuan pemeriksa Tier 1 G1 | Isi `projected_cost_usd_micros` juga pada panggilan gagal tanpa usage, sehingga `cost ?? projected` menghitungnya (konservatif, T6). Alternatif: biarkan 0 (bisa undercount). Perubahan perilaku cost guard, butuh keputusan karena skenario disetujui diam | Operator | Sebelum batch Spark pertama (M2.1/M3.1) |
| I-36 | M1.1 golden sample dan konvensi unit menunggu konfirmasi operator (MILESTONES M1.1: "sampel pasal yang dicek operator"). Usulan agen di `backend/tests/test_chunking_address.py`: Pasal 1, 7, 86 (batang tubuh dan Penjelasan), 102 ayat (1), 142 ayat (2), 153A, satu Pasal tanpa ayat. Tafsir yang diambil: Penjelasan Pasal tanpa "Ayat (n)" = satu unit termasuk heading (69 Pasal; penanda "Huruf x" di Penjelasan bukan unit); `penjelasan_umum` satu unit (6.733 karakter); rincian huruf/angka hanya untuk alamat (`huruf a`, `angka 1`), bukan unit potong | Operator memeriksa batas unit pada sampel itu (screenshot `_kerja/orkestrasi/bukti/M1.1-*.png`) dan mengonfirmasi atau mengganti sampel; konvensi di atas dibiarkan bila tidak ada keberatan. Test sudah ditulis atas usulan, bertanda menunggu konfirmasi | Operator | Sebelum M1.1 ditutup |
| I-35 | `fixed_size` 512/64 dijalankan per rentang `section` (karena `Chunk.section` tunggal). Korpus beku menyelang batang tubuh dan Penjelasan per Pasal, jadi tiap rentang = satu Pasal: hanya 3 Pasal > 512 token yang terpecah, dan tidak ada gold kontrol yang dibelah fixed_size (structure membelah K-02, K-04). Pembanding C (H-036) dan adegan 0 video ("ukuran tetap membelah ayat") kehilangan makna. Spec diam; mengubah angka laporan | Alt. B: jendela tetap atas teks bersih dalam cakupan secara berurutan, melintasi batas Pasal dan section; `Chunk.section` = section posisi awal, `address` rentang `<awal> – <akhir>`; cakupan retrieval tetap filter per section. Alt. A (sekarang): per rentang. Alt. C: jendela atas gabungan rentang satu section (batang tubuh terpisah dari Penjelasan), potongan bisa terdiri dari dua rentang tak bersambung (kontrak `start/end` tunggal berubah). Rekomendasi B (paling mirip praktik RAG naif yang mau dibandingkan). Kode A tetap jalan sampai diputus; grid tanpa LLM murah diulang | Operator | Sebelum run grid yang dilaporkan (M1.4) |

## Ditutup

| ID | Pertanyaan (ringkas) | Penutupan | Tanggal |
|---|---|---|---|
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
