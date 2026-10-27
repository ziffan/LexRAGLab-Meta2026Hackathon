# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-062..H-074.

diperbarui: 2026-10-27 13:05 UTC, sesi orkestrasi berlapis (L2#3) di mesin otoritatif

## Status

- M0 **selesai**. M1 **kode dan review selesai** (screenshot ulang grid v2 tersisa).
- M2: M2.1 D + U6, M2.2 C + U3, M2.3 verifier ter-review. Menunggu review 13 usulan D (H-006). M2.4/M2.5 stretch.
- M3: header B batch Pasal (342/343) dan fixed_size (100/103) selesai (`472ffc8`, `92fbb4c`); U2 deret on/off + toggle (`4d64878`, `294ec6c`); M3.4 chunker skema di grid (`a65e1c2`). Header B v2 (H-079) `cb35b01`; grid `5a9486e`: kembaran header-on masih gagal (I-56, I-57).
- M4: lima akta sintetis (`2c81ef9`, review operator I-51); M4.1 pemuat akta + alamat (`2e33331`); M4.3 backend profil W7/W8 (`f48cbda`) + U7 (`df4a545`, `051615e`), Tier 1; R4 versi skema untuk panel akta.
- M5: M5.1 replay + ekspor statis (`2e33331`, `25eaf4c`), hint + Glossary (`93525a0`), README draf (`585880d`).
- Belanja Model API kumulatif 271.401 micro-USD (RunRecord; termasuk header B v2 H-079 132.115); Baseten 1.702.
- HEAD `051615e` bersih (archive): pytest 1029, vitest 200, tsc bersih; secret scan semua ref 0.

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

Lihat `docs/ISSUES.md` "Menunggu operator": I-49 (teks hint), I-51 (review akta), I-54 (butir demo `scene_checked`; kandidat `_kerja/orkestrasi/kandidat-butir-demo.md`), I-56, I-57 (header-on). Juga: review 13 usulan D di U6, skema A v1 UU PT (H-074), Tier 4 M2.3/M3.3, pemicu 31 Okt H-017, LICENSE/push/Pages.

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
