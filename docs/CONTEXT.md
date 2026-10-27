# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057.

diperbarui: 2026-10-27 (UTC 26 Okt malam), sesi agen otonom semalam (M0 + draft skenario Tier 1)

## Status

- Toolchain dipin: Python 3.12, `torch 2.11.0+cu128` dari index PyTorch (G-28), FastAPI 0.162.0, openai 3.37.0, sentence-transformers 6.2.0; `uv sync` lalu `uv run pytest -q`. Pin per paket di `pyproject.toml`; alasan di bawah.
- M0.1: **belum mulai — skenario disetujui 27 Okt** (`docs/scenarios/M0.1.md`, putusan O-3 A, O-12 alt. 2, O-17 gugur); kode boleh ditulis. Smoke provider sudah jalan (bukan kode M0.1): Meta Model API OK (strict JSON, cached tokens, effort `low`); OpenRouter diblok guardrail akun (G-29, I-25).
- M0.2: **berjalan** — pemuat korpus, token lokal, kalibrasi endpoint, dan proyeksi biaya selesai di mesin otoritatif dengan review Tier 2 independen. Sisa: hash di mesin kedua, persetujuan metode baseline kalibrasi (I-26).
  - `clean_sha256` UU PT = `c56e4f0f38a4…` (`loader_rules_version` 1); 171 Pasal; 16 usulan baris status (bukan tabel status; `approved_by_operator=false`).
  - Token lokal dokumen 46.583; rasio endpoint/lokal 1,0 di semua bagian; overhead tersembunyi endpoint 165 token. Proyeksi satu dokumen penuh sebagai input: 4.659 micro-USD uncached, 94 cached.
- Draft skenario Tier 1 M0.1, M1.2, M1.4, M1.5 di `docs/scenarios/`, masing-masing dengan laporan pemeriksa independen (`*.pemeriksa.md`, dua putaran). Status semua: draft — menunggu persetujuan operator.
- Lembar kerja butir kontrol: `docs/worksheets/butir-kontrol.md` (peta lokasi + template; bukan butir, H-006).
- Belanja Model API sesi ini: 517 micro-USD (Meta), 0 OpenRouter.
- Verifikasi orkestrator (dijalankan ulang, bukan dari laporan agen): `uv run pytest -q` 90 passed; prefix key `.env` di seluruh histori git = 0; `.env` tidak ter-track. Rasio kalibrasi 1,0 bukan sirkular: enam ukuran endpoint mentah (305–46.748) masing-masing tepat token lokal + 165, jadi tokenizer Muse Spark Open identik dengan tokenizer endpoint.

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

Lihat `docs/ISSUES.md` "Menunggu operator" (I-25 s.d. I-30), dan pertanyaan operator di tiap `docs/scenarios/*.md`.

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

1. Operator: putuskan I-25, I-26; setujui (atau minta revisi) skenario M1.2, M1.4, M1.5 (M0.1 disetujui, I-28 dan I-29 ditutup 27 Okt).
2. Kode M0.1 (klien Spark) oleh agen, review Tier 1.
3. ~~Operator, akhir M0: kunci grid, tulis butir kontrol~~ Selesai 27 Okt: grid H-058 di `config/grid.toml`; sembilan butir kontrol (K-01 sampai K-09, tulisan operator, disetujui) dikonversi ke `Item` di `data/butir/uupt.v1.jsonl`; validator jalur masuk menyusul di M1.
4. M1 tidak dimulai sebelum butir kontrol dan grid ada.
