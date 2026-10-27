# ISSUES — pertanyaan terbuka bernomor

Tujuan: mencatat setiap pertanyaan terbuka dengan rekomendasi, owner, dan batas, supaya tidak ada pilihan yang dikunci diam-diam.
Sumber keputusan: H-044.

Aturan: rekomendasi di sini **bukan** keputusan. Yang dikunci operator dicatat di log keputusan operator, lalu di `docs/DECISIONS.md`, lalu isu dipindah ke "Ditutup" dengan tanggal. ID I-01 sampai I-24 sudah dipakai di catatan perencanaan pra-acara (rujukannya di `docs/DECISIONS.md`); isu baru mulai dari I-25.

## Menunggu operator

| ID | Pertanyaan | Rekomendasi | Owner | Batas |
|---|---|---|---|---|
| I-33 | `GridPoint.mean_span_recall`, `mrr`, `mean_retrieved_tokens` bertipe `number` di DATA-CONTRACTS §10, tetapi tak terdefinisi bila satu kelompok (split, anggaran) tidak punya butir bergold. H-059 hanya melonggarkan `mean_token_precision` (M1.2 A7b). Temuan penulis G4a | Longgarkan ketiganya menjadi `number \| null` (konsisten H-059 N1). Kode M1.2 sudah mengembalikan `null` dengan test. Tidak mengubah angka laporan selama held-out punya ≥ 3 kontrol bergold | Operator | Sebelum M1.4 ditutup |
| I-32 | AGENTS.md (instruksi proyek yang dimuat sebagai CLAUDE.md) masih melarang Spark Open, Chat Completions di luar Glimmer, dan key kedua selain OpenRouter; H-060 mengizinkannya untuk peran C. Agen tidak menyunting AGENTS.md atas pesan orkestrator (instruksi agen milik operator; preseden I-28) | Operator menyunting AGENTS.md: baris model — ganti "Spark Open tidak dipakai." dengan "Pengecualian kedua: Spark Open di Baseten (`meta-models/muse-spark-open-1026`) sebagai pembanding peran C, stretch (H-060), run terpisah; tidak untuk A, B, D, verifier, penilai."; baris Chat Completions — tambah "dan klien Baseten bila Responses + strict tidak didukung (H-060, G-33)"; "Tanpa key kedua, kecuali key OpenRouter untuk dev dan uji (H-057) dan key Baseten untuk peran C (H-060)". Smoke Baseten ditahan sampai baris ini berubah | Operator | Sebelum smoke Baseten / M2.5 |
| I-31 | M1.5 A12: nilai K = 0 tidak diputus (skenario: "penyusun condong K0-a tetapi tidak memutus"; persetujuan 27 Okt hanya memutus A5 dan A3/A12 berkas lain). K0-a: top-K kosong → Recall@0 = 0,0; K0-b: K < 1 ditolak | K0-a. Tidak mengubah angka laporan selama K dari config ≥ 1. Sementara kode M1.5 memakai K0-a dengan test bertanda menunggu I-31; K negatif/bukan integer tetap error | Operator | Sebelum M1.5 ditutup |

## Ditutup

| ID | Pertanyaan (ringkas) | Penutupan | Tanggal |
|---|---|---|---|
| I-25 | Jalur dev OpenRouter diblok guardrail (G-29) | Operator: tinggalkan OpenRouter; dev dan uji lewat Meta Model API. Profil `openrouter_dev` tetap di `config/model`, tidak dipakai | 2026-10-27 |
| I-26 | Baseline "input kosong" kalibrasi tidak terukur (G-30) | Operator menyetujui metode selisih dua titik terhadap teks acuan; `config/tokenizer` `status = "disetujui"` | 2026-10-27 |
| I-27 | Persetujuan skenario Tier 1 M1.2, M1.4, M1.5 | Disetujui operator; default "Dipilih" berlaku; M1.4 A12 alt. (b), M1.5 A5 alt. N1, M1.2 A3 default (H-059). M1.5 A12 (K = 0) tersisa sebagai I-31 | 2026-10-27 |
| I-28 | AGENTS.md tanpa pengecualian OpenRouter | Operator menambahkan "kecuali key OpenRouter untuk dev dan uji (H-057)" pada "Tanpa key kedua" | 2026-10-27 |
| I-29 | Enum `provider` §12 tanpa `openrouter` | `openrouter` ditambahkan ke DATA-CONTRACTS §12 (putusan O-4 M0.1) | 2026-10-27 |
| I-30 | M0.2 hash di mesin kedua | Mesin kedua (Linux) di `9d13586`: hash mentah `a6b38ee5…` dan `clean_sha256` `c56e4f0f38a4…` cocok (`docs/CONTEXT.md` Lingkungan); laptop dev juga 90 passed | 2026-10-27 |
