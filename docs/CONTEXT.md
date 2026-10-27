# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-062..H-074.

diperbarui: 2026-10-27 09:05 UTC, sesi orkestrasi berlapis (L2#3) di mesin otoritatif

## Status

- M0 **selesai** (M0.1 klien Spark + RunRecord, M0.2 korpus terukur). Perubahan Tier 1 sesudahnya: proyeksi biaya panggilan gagal (H-063) dan per upaya timeout (H-071), `f6e2912`, `8b32031`, `e157544`.
- M1 **kode dan review selesai** (status per slice di `docs/MILESTONES.md`): chunker v2 (H-062, H-064), grid UU PT v2 `23b606e` (`runs/grid/a822c0c1….json`, 12 setting jalan, 24 menunggu header B/skema A). Sisa: screenshot ulang pada grid v2.
- M2: M2.1 usulan D + U6 (`79b970a`; 13 usulan live menunggu operator), M2.2 C + U3, M2.3 verifier + 2×2 (`ae372db`) ter-review. M2.4 dan M2.5 stretch.
- M3: header B backend + sumbu grid (`e1244aa`, `1a9bacf`; H-069, H-074), skema A backend + U5 editor (`496624b`, `7e090d1`) ter-review. Batch B per Pasal dilanjutkan; deret U2 (WIP) dalam review; M3.4 chunker skema sedang ditulis.
- M4: lima akta sintetis sedang ditulis dari `data/akta/BRIEF.md` (I-46); M4.3 backend profil sedang ditulis (skenario disetujui, H-068).
- Belanja Model API kumulatif sebelum sesi ini 73.554 micro-USD (dari RunRecord); Baseten 1.702. Plafon sementara 15.000.000 / 10.000.000.
- Uji terima awal sesi (HEAD `76256fd`): `uv run pytest -q` 862 passed, `npm test` 103 passed, `tsc` bersih, secret scan 0.

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

Lihat `docs/ISSUES.md` "Menunggu operator" (I-35 sampai I-40) dan `_kerja/orkestrasi/keputusan-skenario-1.md`.

## Menunggu operator

1. Review 13 usulan butir D di U6 (H-006, H-011).
2. Persetujuan/koreksi skema A v1 UU PT `runs/schemas/uupt/v1.json` (H-074, H-037).
3. Review lima akta sintetis setelah ditulis (addendum 2 gerbang 4, H-041).
4. Draf teks hint H-073 setelah review independen (isu menyusul di `docs/ISSUES.md`).
5. Tier 4 domain review kasus verifier M2.3 dan skema A M3.3.
6. Pemicu 31 Okt H-017 dinilai 31 Okt malam WIB.

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
