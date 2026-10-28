# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-062..H-099.

diperbarui: 2026-10-28 UTC (session-end L2#8), sesi orkestrasi berlapis di mesin otoritatif

## Status

- M0, M1 **selesai** (sisa agen: screenshot M1.1/M1.4 pada chunker/grid terkini). M2: M2.1–M2.3 selesai (Tier 4 M2.3 dikonfirmasi operator 28 Okt); butir uupt v16 = 23 (3 `tolak`, H-099, faa343d); akta v85 = 84 (15 `tolak`). M2.4 stretch (potong). M2.5 selesai (stretch).
- M3 selesai, M3.1–M3.4 (status MILESTONES dicocokkan L2#8/W93; Tier 4 M3.3 dikonfirmasi operator 28 Okt): skema A UU PT v2 operator; header B v2; grid uupt v2.
- M4 selesai kecuali Tier 4 domain review M4.1 (belum ada konfirmasi tertulis operator; W93): skema A akta v2 (H-089), peta unit (H-090), header B akta (`runs/headers/akta`, G-38), grid akta final 36 setting `{all}` (`014765d`), profil akta transfer (`91aa993`), README hasil akta.
- M5.1: uji visual Chrome statis + live (375/768/1440) lolos setelah fix proxy keep-alive (`b79e37b`, G-39); bukti `_kerja/orkestrasi/bukti/M51-*`. Status tetap "berjalan" setelah dicocokkan (L2#8, W90): kriteria kode terpenuhi; sisa = adegan video dikunci operator (putusan 8) + Tier 4 UX review operator, lalu screenshot per adegan (agen).
- M5.2 persiapan: LICENSE + NOTICE Apache-2.0 (H-097, copyright Ziffany Firdinal), README tema Build for Your World / Indie (H-098) + kalimat anti-RAG dan new-work-only, motivasi PRD = korpus aturan (angka LO dari laporan operator, anonim), hint 1.4.0 final, dist-static dibangun ulang dari `84c6513` (lihat baris HEAD). Rencana rewrite histori `_kerja/orkestrasi/M52-rewrite-histori-rencana.md` (H-096, belum dijalankan). Repo masih private.
- `tolak` UU PT selesai (H-099): prompt D v3 268dd67, kode Tier 1 f2b5417, run D b709ac3 (4.992 micro-USD), 3 butir disetujui operator, split v3, grid ulang tanpa Spark (pilihan profil tidak berubah), profil + ekspor statis ulang (faa343d). Jawaban C untuk 3 butir `tolak` UU PT (`f52f6a7`, best `d7a9dd24` + baseline `ed489a1e`): Contributor 6/6 abstain (4 `tolak`, 2 `bukti_tidak_cukup`; 1.964 micro-USD), Spark Open Baseten 6/6 (5 + 1; 22.676 micro-USD), Glimmer lokal 6/6 (4 + 2; 0); sel 2×2 18/18 `abstained_correct`.
- Belanja Model API kumulatif (buku belanja, `Ledger.spent`, 28 Okt): 615.008 micro-USD, plafon 20.000.000: Contributor 561.741, Baseten 53.267, Glimmer 0.
- HEAD `84c6513` (kode + data; commit docs session-end L2#8 sesudahnya): pytest 1402, vitest 287, secret scan (tree, histori, dist-static) 0. Ekspor statis dari working tree setelah `84c6513`: `dist-static/data` 1.095 berkas, `dist-static` 1.122 berkas, `--check` 0 temuan.

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

- Tier 4 domain review M4.1 (skema dan potongan akta): konfirmasi tertulis, seperti M2.3/M3.3 (putusan 10 butir 5).
- M5.1: kunci adegan video (putusan 8) + Tier 4 UX review; setelah itu agen menyetor screenshot per adegan.
- Pemicu 31 Okt H-017 (31 Okt malam WIB).
- Gate M5.2: rewrite histori + force push (H-096), repo publik, Pages; butir NOTICE "unverified, pending operator" (kartu Glimmer HF, syarat keluaran Contributor, endpoint Baseten, Official Rules terpisah, versi jurnal Magesh).
- Isian form submit: repo catatan `docs/10-SUBMIT.md` (nama tim, feedback, Most Viral). Video milik operator.
- Keputusan L1 yang bisa dibalik: keterangan "agen L3 (Claude)" di `docs/scenarios` dibiarkan sebagai disclosure.
- Catatan biaya: README memakai buku belanja `Ledger.spent` (`cost ?? projected`, H-063) = 615.008; header snapshot `health.json` menampilkan jumlah mentah `cost_usd_micros` 613.105 (selisih = proyeksi panggilan gagal). Bukan basi; operator memilih angka mana yang dikutip di video.

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

1. Sesi baru: L1 membaca `_kerja/orkestrasi/keadaan-L1.md` (RESUME + log) dan `keadaan-L2.md` (bagian L2#8), menjalankan ulang pytest (1402) dan npm (287) di worktree bersih (`core.longpaths`; test akta v2 tidak lagi butuh salinan `_kerja/`), lalu melahirkan L2 baru bila ada mandat.
2. Gerbang operator: Tier 4 M4.1, adegan + Tier 4 UX M5.1, gate M5.2 (rewrite histori H-096, publik, Pages), isian submit. Pemicu 31 Okt H-017.
3. Agen (tidak terblok, kecil): screenshot M1.1/M1.4 pada chunker/grid terkini; opsional test Glimmer di mode statis.
4. Frontend 5173 (operator) dan 5175 (tailnet) harus memakai `vite.config.ts` >= `b79e37b` (G-39); 5175 perlu >= `f52f6a7` agar jawaban C butir tolak tampil.
