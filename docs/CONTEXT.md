# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-P24.

diperbarui: 2026-10-27 siang WIB, sesi laptop dev (tiga mesin, butir kontrol, grid, skenario M0.1)

## Status

- Toolchain dipin: Python 3.12, `torch 2.11.0+cu128` dari index PyTorch (G-28), FastAPI 0.162.0, openai 3.37.0, sentence-transformers 6.2.0; `uv sync` lalu `uv run pytest -q`. Pin per paket di `pyproject.toml`; alasan di bawah.
- M0.1: **belum mulai — skenario disetujui 27 Okt** (`docs/scenarios/M0.1.md`, putusan O-3 A, O-12 alt. 2, O-17 gugur); kode boleh ditulis. Smoke provider sudah jalan (bukan kode M0.1): Meta Model API OK (strict JSON, cached tokens, effort `low`); OpenRouter diblok guardrail akun (G-29, I-25).
- M0.2: **berjalan** — pemuat korpus, token lokal, kalibrasi endpoint, dan proyeksi biaya selesai di mesin otoritatif dengan review Tier 2 independen. Hash mesin kedua cocok 27 Okt (I-30 ditutup). Sisa: persetujuan metode baseline kalibrasi (I-26).
  - `clean_sha256` UU PT = `c56e4f0f38a4…` (`loader_rules_version` 1); 171 Pasal; 16 usulan baris status (bukan tabel status; `approved_by_operator=false`).
  - Token lokal dokumen 46.583; rasio endpoint/lokal 1,0 di semua bagian; overhead tersembunyi endpoint 165 token. Proyeksi satu dokumen penuh sebagai input: 4.659 micro-USD uncached, 94 cached.
- Skenario Tier 1 di `docs/scenarios/`: M0.1 **disetujui** 27 Okt; M1.2, M1.4, M1.5 masih draft (I-27). Semua, masing-masing dengan laporan pemeriksa independen (`*.pemeriksa.md`, dua putaran). Status semua: draft — menunggu persetujuan operator.
- Butir kontrol: sembilan butir tulisan operator (K-01 sampai K-09, delapan bergold + satu wajib tolak; 4 literal, 5 parafrase) di `data/butir/uupt.v1.jsonl`, disetujui operator 27 Okt. Offset dihitung dari alamat tulisan operator dan dicetak balik ke teks bersih; validator jalur masuk belum ada (dibangun di M1).
- Grid dikunci H-058: `config/grid.toml` v1 (`fixed_size` 512/64 sekaligus baseline C, anggaran 2.000 + 1.000, `packing = stop`, seed 20261026, 36 titik).
- Pending H-P24 (log keputusan operator): Spark Open di Baseten (`meta-models/muse-spark-open-1026`, kredit $100, Chat Completions) vs Glimmer lokal sebagai pembanding C. Discord Baseten mengonfirmasi 27 Okt bahwa inference lewat Baseten memenuhi "verified by partner" untuk bonus open-weight. Sampai operator memutus, H-047 berlaku: Spark Open tidak dipakai, key Baseten tidak dibaca kode.
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

1. Operator (di PC): setujui (atau minta revisi) skenario M1.2, M1.4, M1.5 (I-27); putuskan I-25 (OpenRouter) dan I-26 (baseline kalibrasi). Di clone PC, cek `git config user.email` = alamat noreply (laptop dev sempat commit dengan email global).
2. Kode M0.1 (klien Spark) oleh agen sesuai `docs/scenarios/M0.1.md` (disetujui), review Tier 1. Bisa dijalankan otonom.
3. M1 boleh dimulai: prasyarat butir kontrol dan grid terpenuhi 27 Okt. M1.1 (non-Tier 1) bisa langsung; M1.2, M1.4, M1.5 menunggu butir 1. Validator jalur masuk `data/butir/` dibangun di M1 dan memvalidasi `uupt.v1.jsonl`.
4. Operator, sebelum stretch pembanding C: putuskan H-P24 (Baseten vs Glimmer).
