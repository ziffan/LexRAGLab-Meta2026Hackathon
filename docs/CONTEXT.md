# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-062..H-083.

diperbarui: 2026-10-27 16:30 UTC, sesi orkestrasi berlapis (L2#4, serah terima) di mesin otoritatif

## Status

- M0 **selesai**. M1 **kode dan review selesai**.
- M2: M2.1–M2.3 ter-review; butir uupt v13 = 20 (operator 9, spark 11; demo K-09/K-01/K-08 `scene_checked`, H-085); C live butir demo `190f5ae`. Mode D `unanswerable` untuk akta (H-087) menunggu skenario Tier 1 (H-052). M2.4/M2.5 stretch (Glimmer siap di LM Studio 127.0.0.1:8080, dikerjakan setelah M4).
- M3: skema A UU PT v2 operator (H-084, `d8aabaa`); header B v2 lengkap (Pasal, fixed_size, schema v2 343/343 `42e4c80`); grid uupt `--with-headers --with-schema` v2 `9086f78`: profil structure_schema v2 dense header off (B1000/B2000; tune 1.0, held-out 0.75).
- M4: akta disetujui (I-51); skema A akta v1 Spark (`344bd9d`), v2 diputus (H-088, berkas koreksi menunggu revisi + konfirmasi operator); butir akta v70 = 69 (operator review, `db3d192`); retrieval per akta (H-086); grid akta multi-dokumen S1–S3 di cabang `wip/l2-4-w38` (`c64e29e`, BELUM review Tier 1).
- M5: replay + ekspor statis ulang (dist-static, 783 berkas, check 0); hint 1.1.0 final; tema H-083; U6 pemilih keluarga. Video dipisah ke operator (putusan 8).
- Belanja Model API kumulatif ±517.455 micro-USD (RunRecord). Baseten 1.702.
- HEAD `a6fa188`: pytest 1107, vitest 237, tsc bersih; secret scan histori 0.

## Pin versi (M0)

| Paket | Pin | Alasan |
|---|---|---|
| Python | 3.12.* | H-013, G-28 (uv bisa memilih 3.14) |
| torch | 2.11.0+cu128 (index eksplisit) | G-28; `cuda.is_available()` = True di RTX 5060 Ti |
| fastapi | 0.162.0 | terbaru (23 Okt), tidak ada masalah saat sync/import |
| openai | 3.37.0 | 3.38.0 rilis 26 Okt (< 24 jam); mundur satu minor sebagai pengaman, belum ada masalah teramati |
| sentence-transformers | 6.2.0 | terbaru (21 Okt), import OK |
| tokenizers / tiktoken | 0.23.3 / 0.14.0 | tokenizer H-014 dan cadangan `o200k` |
| rank-bm25 / sastrawi | 0.2.2 / 1.0.1 | M1.2 (tidak aktif tapi stabil, MILESTONES M0) |

## Menunggu operator

Konfirmasi diff akhir skema A akta v2 (H-088) sebelum `correct`; skenario Tier 1 mode D `unanswerable` (H-087); bentuk `grid` akta di API.md §4 + setting laporan akta (W38 §4); unit akta untuk Recall@K/boundary; cakupan grid akta (semua `config/grid` atau setting transfer saja). Juga Tier 4 M2.3/M3.3, pemicu 31 Okt H-017, LICENSE/push publik/Pages (M5.2).

## Lingkungan

- Mesin GPU otoritatif untuk embedding, grid, dan run Spark; mesin kedua hanya membaca `runs/` (H-027).
- Akhir baris LF di semua mesin (`docs/CONVENTIONS.md` bagian "Akhir baris", G-16).

Tiga mesin, dicek 27 Okt (commit `9d13586`):

| Mesin | Peran | Keadaan |
|---|---|---|
| Desktop Windows, dua GPU | Otoritatif (H-027) | `uv run pytest -q` 90 passed; `clean_sha256` `c56e4f0f38a4…`; `torch.cuda.is_available()` True |
| Linux, tanpa GPU, 24/7 | Mesin kedua, hanya membaca `runs/` (H-027) | Di-fast-forward ke `9d13586`, tree bersih, `git ls-files --eol` semua `lf`. Pemuat (`backend.corpus.loader.load_corpus`, hanya stdlib) dijalankan dengan Python 3.12.14 tanpa `uv sync`: hash mentah `a6b38ee5…` dan `clean_sha256` `c56e4f0f38a4…` cocok dengan `config/` (menutup I-30). Venv proyek belum di-sync (torch tidak dibutuhkan untuk membaca `runs/`) |
| Laptop Windows, tanpa GPU | Dev mobile | Clone disiapkan (autocrlf false, eol lf, exclude lokal alat agen, tree `lf`). uv 0.13.6 + Python 3.12.16, `uv sync --frozen` (torch `2.11.0+cu128`, CUDA False). Tokenizer H-014 (tiga berkas, revisi `0fb02478`, tanpa bobot) diunduh ke cache HF; tanpa itu pemuat jatuh ke `o200k` dan kunci cache `runs/measure/` berbeda (G-32). `uv run pytest -q` 90 passed. Belum ada gitleaks dan ffmpeg |

## Berikutnya

1. Selesaikan batch B per Pasal dan `fixed_size`, lalu grid `--with-headers`.
2. Review dan commit U2, hint, M3.4 (Tier 2), M4.3 (Tier 1), akta (pemeriksa H-041).
3. Pass visual (Claude in Chrome) M1 ulang dan U2/U3/U5/U6/U8.
4. M5.1 replay dan ekspor statis; persiapan M5.2.
5. Berkas keadaan orkestrasi: `_kerja/orkestrasi/keadaan-L2.md`.
