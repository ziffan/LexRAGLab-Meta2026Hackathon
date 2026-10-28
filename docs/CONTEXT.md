# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-062..H-099.

diperbarui: 2026-10-28 UTC (session-end L1), sesi orkestrasi berlapis (L2#6 selesai) di mesin otoritatif

## Status

- M0, M1 **selesai**. M2: M2.1–M2.3 selesai (Tier 4 M2.3 dikonfirmasi operator 28 Okt); butir uupt v16 = 23 (3 `tolak`, H-099, faa343d); akta v85 = 84 (15 `tolak`). M2.4 stretch (potong). M2.5 selesai (stretch).
- M3 selesai (Tier 4 M3.3 dikonfirmasi operator 28 Okt): skema A UU PT v2 operator; header B v2; grid uupt v2.
- M4 selesai: skema A akta v2 (H-089), peta unit (H-090), header B akta (`runs/headers/akta`, G-38), grid akta final 36 setting `{all}` (`014765d`), profil akta transfer (`91aa993`), README hasil akta.
- M5.1: uji visual Chrome statis + live (375/768/1440) lolos setelah fix proxy keep-alive (`b79e37b`, G-39); bukti `_kerja/orkestrasi/bukti/M51-*`. Status MILESTONES masih "berjalan": kriteria selesai (sisa lama "adegan 4 / screenshot semua adegan") belum dicocokkan ulang; L2#7 mencocokkan lalu menandai.
- M5.2 persiapan: LICENSE + NOTICE Apache-2.0 (H-097, copyright Ziffany Firdinal), README tema Build for Your World / Indie (H-098) + kalimat anti-RAG dan new-work-only, motivasi PRD = korpus aturan (angka LO dari laporan operator, anonim), hint 1.4.0 final, dist-static dibangun ulang dari `83c370b` (`--check` 0). Rencana rewrite histori `_kerja/orkestrasi/M52-rewrite-histori-rencana.md` (H-096, belum dijalankan). Repo masih private.
- `tolak` UU PT selesai (H-099): prompt D v3 268dd67, kode Tier 1 f2b5417, run D b709ac3 (4.992 micro-USD), 3 butir disetujui operator, split v3, grid ulang tanpa Spark (pilihan profil tidak berubah), profil + ekspor statis ulang (faa343d).
- Belanja Model API kumulatif 554.785 micro-USD (plafon 20.000.000). Baseten 30.591. Glimmer 0.
- HEAD `8d04e18` (di-push): pytest 1345 (worktree bersih L1), vitest 283, tsc bersih, secret scan 0.

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

- Tinjau prompt v3 uupt sebelum run D (H-099 Q4); review kandidat `tolak` UU PT di U6; laporan dampak sebelum grid ulang UU PT (Q7).
- Pemicu 31 Okt H-017 (31 Okt malam WIB).
- Gate M5.2: rewrite histori + force push (H-096), repo publik, Pages; butir NOTICE "unverified, pending operator" (kartu Glimmer HF, syarat keluaran Contributor, endpoint Baseten, Official Rules terpisah, versi jurnal Magesh).
- Isian form submit: repo catatan `docs/10-SUBMIT.md` (nama tim, feedback, Most Viral). Video milik operator.
- Keputusan L1 yang bisa dibalik: keterangan "agen L3 (Claude)" di `docs/scenarios` dibiarkan sebagai disclosure.

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

1. Sesi baru: L1 membaca `_kerja/orkestrasi/keadaan-L1.md` (RESUME + log) dan `keadaan-L2.md`, menjalankan ulang pytest (1345) dan npm (283) di worktree bersih (salin `_kerja/orkestrasi/skemaA-akta-v2-koreksi*.json`, `core.longpaths`), lalu melahirkan L2#7 dengan brief + addendum 1–3 + putusan-operator-2..11 dan memasang pengawas cron.
2. L2#7: kode Tier 1 `tolak` UU PT (H-099) → prompt v3 ke operator → run D (proyeksi ±8.059) → review U6 → laporan dampak → W5 + grid ulang UU PT → ekspor statis ulang.
3. Gate M5.2 bersama operator (rewrite histori, publik, Pages), lalu isian submit. Salin H-099 ke log operator (belum disalin).
4. Frontend 5173 (operator) dan 5175 (tailnet) harus memakai `vite.config.ts` >= `b79e37b` (G-39).
