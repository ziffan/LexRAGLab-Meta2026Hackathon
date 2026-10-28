# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-062..H-093.

diperbarui: 2026-10-28 UTC, sesi orkestrasi berlapis (L2#6) di mesin otoritatif

## Status

- M0 **selesai**. M1 **selesai**.
- M2: M2.1–M2.3 ter-review; butir uupt v13 = 20; mode D `unanswerable` akta (H-087, H-092) selesai, 15 butir wajib tolak disetujui operator (akta v85 = 84). M2.4 stretch (potong). M2.5 selesai (stretch).
- M3: skema A UU PT v2 operator; header B v2 lengkap; grid uupt `--with-headers --with-schema` v2.
- M4: skema A akta v2 operator varian (b) (H-089); peta unit akta (H-090); header B akta (store `runs/headers/akta`, G-38); **grid akta final** 36 setting `{all}` + setting transfer + label degenerate (H-091, H-093, `014765d`); profil akta transfer (`91aa993`).
- M5: ekspor statis ulang dengan pemilih keluarga (975 berkas, `--check` 0); uji visual Chrome menunggu extension. M5.2 persiapan (`_kerja/orkestrasi/M52-gate-L2-6.md`); LICENSE/publik/Pages milik operator. Video dipisah ke operator.
- Belanja Model API kumulatif 554.785 micro-USD (plafon 20.000.000). Baseten 30.591. Glimmer 0.
- HEAD (worktree bersih L1, 71379c6): pytest 1339, vitest 282, tsc bersih.

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

I-66 (cakupan `tolak` per keluarga), I-68 (hint Recall@K untuk akta), Tier 4 M2.3/M3.3, pemicu 31 Okt H-017 (31 Okt malam WIB), LICENSE/push publik/Pages (M5.2), keputusan histori (email di metadata commit, path lokal di histori lama). Chrome extension untuk uji visual.

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

1. Setelah putusan operator: `correct` skema akta v2 → header B akta → kode peta unit akta → H-087 → S4 + grid akta → laporan transfer + profil akta.
2. Ekspor statis ulang + uji visual; M5.2 gate.
3. Berkas keadaan orkestrasi: `_kerja/orkestrasi/keadaan-L2.md` (L2) dan `_kerja/orkestrasi/keadaan-L1.md` (L1). `_kerja/` di-gitignore dan hanya ada di mesin otoritatif; `keputusan-pagi.md` dibaca operator di PC ini.
4. Melanjutkan di sesi baru: L1 membaca kedua berkas keadaan, menjalankan ulang `uv run pytest -q` (1190 di `be35b4d`) dan `npm test` (250), lalu melahirkan L2 baru dengan brief + addendum 1–3 + putusan-operator-2..8 + jawaban operator atas `keputusan-pagi.md`, dan memasang ulang pengawas 30 menit (cron session-only, mati bersama sesi).
5. Log keputusan operator (repo catatan) sudah memuat salinan H-059..H-088 (terakhir `745f7f0`). Keputusan baru dari `keputusan-pagi.md` disalin dengan cara yang sama.
