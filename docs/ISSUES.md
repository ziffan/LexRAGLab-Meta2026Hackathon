# ISSUES — pertanyaan terbuka bernomor

Tujuan: mencatat setiap pertanyaan terbuka dengan rekomendasi, owner, dan batas, supaya tidak ada pilihan yang dikunci diam-diam.
Sumber keputusan: H-044.

Aturan: rekomendasi di sini **bukan** keputusan. Yang dikunci operator dicatat di log keputusan operator, lalu di `docs/DECISIONS.md`, lalu isu dipindah ke "Ditutup" dengan tanggal. ID I-01 sampai I-24 sudah dipakai di catatan perencanaan pra-acara (rujukannya di `docs/DECISIONS.md`); isu baru mulai dari I-25.

## Menunggu operator

| ID | Pertanyaan | Rekomendasi | Owner | Batas |
|---|---|---|---|---|
| I-40 | M2.2 (a61f7c9): penanda alamat tiap potongan di konteks C tidak dihitung dalam anggaran token. Pada anggaran 2.000 yang sama, kolom struktur (41 potongan kecil) membawa 4.148 token input vs pembanding fixed (9 potongan) 3.064, jadi konteks C tidak sebanding dan biaya struktur lebih tinggi. Juga: `AnswerRecord` diberi field `flags` (`jawab_tanpa_kutipan`, `jawab_tanpa_jawaban`) di luar DATA-CONTRACTS §8; potongan fixed lintas unit beralamat rentang (masuk keputusan M2.3 V5) | Biarkan anggaran = teks sumber (sama dengan grid dan metrik M1, label diberikan sama ke semua chunker sesuai prinsip keadilan MILESTONES), dan laporkan token input aktual per kolom di U3; alt.: label ikut anggaran (konteks C berbeda dari yang diukur grid). `flags` masuk §8 sebagai field informatif | Operator | Sebelum run C yang dilaporkan |
| I-39 | Panel M1.5 (QualityMetrics): Recall@K dihitung atas semua butir bergold (tune + held-out); M1.5 A7 membiarkan pemanggil memilih butir, spec diam soal split. Run `b8d0…`: semua butir 0,8125 vs tune saja 0,9 (anggaran 1000). Entity preservation dan boundary coherence tidak bergantung butir | Held-out saja untuk angka yang tampil sebagai hasil (UI-SPEC §1: angka yang dilaporkan dari held-out; tune boleh dengan label "tune"); cakupan jadi parameter `config/retrieval` `[quality].recall_items`, label tampil di panel. Alt.: semua butir dengan label "all items" | Operator | Sebelum panel M1.5 dipakai di video |
| I-38 | Run grid UU PT pertama (`runs/grid/b8d0d6ea….json`, 8450e1d): entity preservation `structure_handwritten` 652/901 vs `fixed_size` 896/901. Dugaan: potongan struktur = unit ayat tanpa heading `### Pasal n` (konvensi peta U, M1.2 A4 disetujui), jadi entitas "Pasal n" di heading jatuh di luar semua potongan; heading juga tidak bisa dicocokkan BM25/dense. A4 mengatur peta alamat untuk Recall@K, bukan batas potongan | Alt. 1: potongan ayat pertama tiap Pasal mencakup heading (batas potongan ≠ unit alamat; Recall@K tetap memakai unit A4). Alt. 2: biarkan, entitas heading dikecualikan dari E (EVAL-SPEC §7 diubah). Alt. 3: biarkan apa adanya. Rekomendasi alt. 1. Mengubah angka laporan; grid tanpa LLM murah diulang | Operator | Sebelum run grid yang dilaporkan |

## Ditutup

| ID | Pertanyaan (ringkas) | Penutupan | Tanggal |
|---|---|---|---|
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
