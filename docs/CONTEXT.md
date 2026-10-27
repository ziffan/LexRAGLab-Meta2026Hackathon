# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-062..H-083.

diperbarui: 2026-10-27 15:10 UTC, sesi orkestrasi berlapis (L2#4) di mesin otoritatif

## Status

- M0 **selesai**. M1 **kode dan review selesai**.
- M2: M2.1 D + U6, M2.2 C + U3, M2.3 verifier ter-review. Review 13 usulan D **selesai** (operator: 11 diterima, 2 ditolak; butir uupt v12 = 20, H-011 terpenuhi, `878cf2a`). M2.4/M2.5 stretch.
- M3: header B v2 lengkap: Pasal 343/343, fixed_size 103/103, structure_schema 343/343 (H-082, `82809c6`; 4 upaya). Grid uupt v12 `--with-headers --with-schema` (`27ceb240…`) dan grid polos (`901712a1…`), split v2 tune 11 / held-out 9. Header-on tidak masuk frontier tune; di held-out menaikkan recall beberapa setting. Skema A yang dipakai masih v1 Spark; v2 menunggu I-60.
- M4: lima akta sintetis disetujui operator (I-51 ditutup); M4.1 pemuat akta + alamat; M4.3 backend + U7, Tier 1.
- M5: M5.1 replay + ekspor statis, hint 1.0.0 final (I-49 ditutup), tema UI H-083 (`5fc2468`, uji visual 375/768/1440 `_kerja/orkestrasi/bukti/tema-H083-*.png`, console bersih), README + PRD motivasi (putusan 8, `9dda378`). **Video (M5.3) dipisah dan ditangani operator (putusan 8)**: agen tidak menyiapkan bahan video.
- Belanja Model API kumulatif 394.011 micro-USD (RunRecord; H-082 121.725). Baseten 1.702.
- HEAD `9dda378`: pytest 1107, vitest 231, tsc bersih; secret scan histori 0.

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

Lihat `docs/ISSUES.md` "Menunggu operator": I-54 (butir demo `scene_checked`; tidak memblokir app, putusan 8), I-59 (hint `app.purpose` 1.1.0 draft), I-60 (skema A v2: berkas koreksi siap, `correct` belum; premis Penjelasan, chunk_id memaksa B ulang). Juga: Tier 4 M2.3/M3.3, pemicu 31 Okt H-017, LICENSE/push publik/Pages (M5.2).

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
