# ISSUES — pertanyaan terbuka bernomor

Tujuan: mencatat setiap pertanyaan terbuka dengan rekomendasi, owner, dan batas, supaya tidak ada pilihan yang dikunci diam-diam.
Sumber keputusan: H-044.

Aturan: rekomendasi di sini **bukan** keputusan. Yang dikunci operator dicatat di log keputusan operator, lalu di `docs/DECISIONS.md`, lalu isu dipindah ke "Ditutup" dengan tanggal. ID I-01 sampai I-24 sudah dipakai di catatan perencanaan pra-acara (rujukannya di `docs/DECISIONS.md`); isu baru mulai dari I-25.

## Menunggu operator

| ID | Pertanyaan | Rekomendasi | Owner | Batas |
|---|---|---|---|---|
| I-25 | Jalur dev OpenRouter (H-057) diblok guardrail akun: model Contributor ditolak 404 "Paid model training violation" (G-29). Aktifkan endpoint training-data di guardrail workspace OpenRouter, atau tinggalkan jalur OpenRouter? | Tinggalkan OpenRouter untuk malam ini (Meta langsung berfungsi dan harganya sama). Bila tetap ingin jalur dev, operator mengubah guardrail di dashboard OpenRouter; agen tidak menyentuh setelan akun | Operator | 27 Okt pagi |
| I-26 | Baseline "input kosong" untuk kalibrasi (G-08, EVAL-SPEC §2, H-014) tidak bisa diukur: endpoint menolak input kosong (G-30). Setujui metode pengganti: selisih terhadap teks acuan pendek (overhead tersembunyi hilang saat dikurangkan)? | Setujui metode selisih dua titik; agen memakainya di G3 dengan tanda `sementara` di `config/tokenizer` dan catatan run sampai disetujui | Operator | 27 Okt pagi |
| I-27 | Draft skenario Tier 1 M1.2, M1.4, M1.5 (M0.1 disetujui 27 Okt) (`docs/scenarios/`) menunggu persetujuan (H-052). Tiap berkas punya daftar "Pertanyaan operator" dengan alternatif dan laporan pemeriksa independen dua putaran | Putuskan pertanyaan per berkas, lalu setujui; kode slice Tier 1 tidak ditulis sebelum itu | Operator | Sebelum kode M0.1 |

## Ditutup

| ID | Pertanyaan (ringkas) | Penutupan | Tanggal |
|---|---|---|---|
| I-28 | AGENTS.md tanpa pengecualian OpenRouter | Operator menambahkan "kecuali key OpenRouter untuk dev dan uji (H-057)" pada "Tanpa key kedua" | 2026-10-27 |
| I-29 | Enum `provider` §12 tanpa `openrouter` | `openrouter` ditambahkan ke DATA-CONTRACTS §12 (putusan O-4 M0.1) | 2026-10-27 |
| I-30 | M0.2 hash di mesin kedua | Mesin kedua (Linux) di `9d13586`: hash mentah `a6b38ee5…` dan `clean_sha256` `c56e4f0f38a4…` cocok (`docs/CONTEXT.md` Lingkungan); laptop dev juga 90 passed | 2026-10-27 |
