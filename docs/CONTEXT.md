# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-059, H-060, H-061.

diperbarui: 2026-10-27 sore WIB, sesi orkestrasi berlapis di mesin otoritatif (M0 tutup, M1 dibangun, skenario M2–M4)

## Status

- M0 **selesai**. M0.1 klien Spark (`7d23b7e`, `ff252b4`, `7dee80d`; review Tier 1 dua putaran, 0 BLOCKER); bukti live `runs/spark/records/` (393 uncached, 92 cached micro-USD). M0.2 selesai (`01d9043`, metode kalibrasi disetujui I-26).
- M1 **berjalan**, kode lengkap dan ter-review per modul: M1.1 chunker + panel (`4e18c57`), M1.2 kalkulator + BM25 (`6c4e19b`), M1.3 dense bge-m3 GPU + hybrid (`dc8a5c5`), M1.4 split/frontier (`f970448`), M1.5 metrik (`2e90254`), integrasi pipeline + API tunggal + run grid UU PT nyata (`8450e1d`, `2d89e7a`; `runs/grid/7f7fa8c6….json`, 12 setting jalan, 24 menunggu M3; split v1 tune 5 / held-out 4), frontend U1/U2/U4/mode/panel M1.5 (`1789c4f`). Belum ditutup karena isu operator I-35, I-36, I-38, I-39 (lihat ISSUES) dan review frontend.
- M2.2 kode (W6, prompt C v1) `a61f7c9`, bukti live K-02 1.083 micro-USD; review Tier 2 berjalan. Verifier M2.3 belum ditulis (Tier 1, skenario menunggu).
- Skenario Tier 1 draft + pemeriksa independen dua putaran (0 BLOCKER): M2.1, M2.3, M2.4, M4.3 — lembar keputusan operator `_kerja/orkestrasi/keputusan-skenario-1.md`; M3.2 revisi 2 (lembar 2 menyusul).
- Keputusan baru: H-059 (§10 nullable, skenario M1.x disetujui), H-060 (pembanding C Glimmer + Spark Open Baseten), H-061 (K0-a, GridPoint nullable). Profil `baseten_open` + harga (I-34); smoke Baseten Responses strict OK (G-33).
- Belanja Model API kumulatif 2.085 micro-USD (517 sesi 26 Okt + 1.568 sesi ini, dari RunRecord); Baseten 1.702.
- `uv run pytest -q` 515 passed (mesin otoritatif, `a61f7c9`).

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

1. Operator: putuskan I-35 (fixed_size lintas section), I-38 (heading Pasal di potongan), I-36 (golden sample), I-39, I-40, I-37; setujui skenario M2.1/M2.3/M2.4/M4.3 lewat lembar keputusan.
2. Setelah I-35/I-38: ulang run grid (tanpa LLM, murah), tutup M1.
3. Setelah skenario disetujui: kode Tier 1 M2.1, M2.3 (lalu M2.4 stretch); M3.1 header B (Tier 2) bisa jalan tanpa menunggu; M3.2 setelah lembar 2.
4. Berkas keadaan orkestrasi: `_kerja/orkestrasi/keadaan-L2.md`.
