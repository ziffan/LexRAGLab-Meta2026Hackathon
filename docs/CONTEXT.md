# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-062..H-112.

diperbarui: 2026-10-30 UTC (L1 tutup sesi sore: putusan operator 16-19, M5.1 Tier 4 ditutup, N-1, storyboard dikunci, MG `video/`, VO TTS), sesi orkestrasi berlapis di mesin otoritatif

## Status

- **30 Okt (H-113, L2-vo-qa, cabang worktree, belum merge):** pemeriksa VO `python -m video.qa.vo_check` (spec `docs/scenarios/M5.3-vo-qa-transcribe.md` rev 4): Muse Voice Transcribe `muse-voice-transcribe-1.0` ($0.18/jam = 50 micro-USD/detik), profil `meta_voice` di `config/model` (ditolak SparkClient, tidak tampil di R1), store terpisah `runs/voice_qa/`, gerbang < 50.000 micro-USD. Dry-run VO tempo-1.12: 9 berkas, 178,01 s, proyeksi 9.100 micro-USD. Belum ada panggilan berbayar (menunggu VO final + izin L1). Konsekuensi: `config_hash` jalur utama berubah (`5ae11b9f…` -> `6d2089b9…`) karena `config/model` berubah; record Spark lama membawa hash lama, perilaku identik; golden S19 di-rebase hanya string hash (commit terpisah, perlu restu L1).
- **30 Okt (putusan operator 18/19):** storyboard video dikunci (hook S0-A; alternatif 4.1 terbuka sampai sunting); `docs/VIDEO.md` diperbarui; motion graphic di `video/` (MG-1 25 dtk, MG-S 4 dtk, MG-2 20 dtk, MG-3 8 dtk; tabel angka -> sumber `video/README.md`); VO = TTS lokal (L2-tts). Menunggu operator: URL repo + engine TTS di MG-3.
- **30 Okt:** putusan operator 16 (sisir docs kelas b diterapkan, `app-docs` catatan diarsip) dan 17 (Tier 4 M5.1 ditutup; N-1 diperbaiki, merge `0f544b74`, pytest 1855, vitest 330; health hangat ±0,1 s). Backend 8000 dan frontend 5173 menyala dari HEAD tanpa key. Berikutnya: operator memilih/mengunci adegan video; gate M5.2.
- **Menunggu operator (tutup sesi 30 Okt):** (1) dengar VO `electra` (audiobook-maker `out/lexraglab-video/vo/`), pilih tempo 1,12 (2:58) atau asli (3:20, naskah perlu dipangkas); (2) rekaman layar sesuai checklist `docs/VIDEO.md` (G-47, G-48); (3) gate M5.2: rewrite histori H-096, repo publik, URL repo di MG-3 (TODO), Pages + cek statis UX-09, NOTICE catatan VoxCPM2, rujukan `_kerja/` di scenarios (butir 25), form submit; (4) 31 Okt pemicu H-017 = lapor status. Rekaman ±2 Nov, freeze 3 Nov, submit 4 Nov.
- **Sapuan effort selesai** dalam lingkup H-111/H-112, di-merge ke `main` `42d83fc7` (29 Okt): Contributor `low`..`xhigh` (A, B, C + grid); Spark Open dan Glimmer sampai `medium` (A, B, C + grid; Spark Open `high`/`xhigh` dan Glimmer `high` hanya A dan C; B Spark Open `high`/`xhigh`, B Glimmer `high`, dan Glimmer `xhigh` tidak dijalankan, H-110/H-111). Cakupan sebagian B Spark Open `medium` (UU PT `pasal` 334/343, `fixed_size` 87/103, `structure_schema` 321/343, akta 120/123; H-112). Laporan S7 `_kerja/orkestrasi/sweep/laporan-effort.md`; README Limits dan G-42..G-46 diperbarui (L2-pascasapuan). Belanja per pool (`pool_spend`, aturan R1): default 561.741 (= header/README), Baseten H-101 15.513.750, sapuan 32.951.385 dari plafon 75M (Contributor 1.634.019, Spark Open 31.317.366, Glimmer 0); total semua pool 49.026.876; Baseten lintas pool 46.831.116. Hasil utama tetap Contributor `low`.
- M0, M1 **selesai** (screenshot M1.1/M1.4 pada chunker v2 dan grid `e7ffa7b0…` disetor L2#9, `_kerja/orkestrasi/bukti/M1.1-v2-*`, `M1.4-v2-*`). M2: M2.1–M2.3 selesai (Tier 4 M2.3 dikonfirmasi operator 28 Okt); butir uupt v16 = 23 (3 `tolak`, H-099, faa343d); akta v85 = 84 (15 `tolak`). M2.4 stretch (potong). M2.5 selesai (stretch).
- M3 selesai, M3.1–M3.4 (status MILESTONES dicocokkan L2#8/W93; Tier 4 M3.3 dikonfirmasi operator 28 Okt): skema A UU PT v2 operator; header B v2; grid uupt v2.
- M4 selesai (Tier 4 M4.1 dikonfirmasi operator 28 Okt, preseden M3.3: I-51 + koreksi v2 H-088/H-089 sebagai domain review): skema A akta v2 (H-089), peta unit (H-090), header B akta (`runs/headers/akta`, G-38), grid akta final 36 setting `{all}` (`014765d`), profil akta transfer (`91aa993`), README hasil akta.
- M5.1: uji visual Chrome statis + live (375/768/1440) lolos setelah fix proxy keep-alive (`b79e37b`, G-39); bukti `_kerja/orkestrasi/bukti/M51-*`. Status tetap "berjalan" setelah dicocokkan (L2#8, W90): kriteria kode terpenuhi; sisa = adegan video dikunci operator (putusan 8) + Tier 4 UX review operator, lalu screenshot per adegan (agen).
- M5.1 L2#10 (putusan operator 12): perbaikan UX review UX-01..23 selesai (tagline dan hint 1.5.0 final, disetujui operator 28 Okt); `Run cost` = buku belanja `Ledger.spent` 615.008 di header, README, U8 (direvisi H-104: lihat baris Biaya) (R1 `ledger_spent_usd_micros`, `run_totals_by_kind`); U3 biaya panggilan asal untuk jawaban cache (W6 `origin_runs`); profil UU PT/akta ikut ekspor statis. Ringkasan per UX: `docs/UI-SPEC.md` §10.5.
- M5.2 persiapan: LICENSE + NOTICE Apache-2.0 (H-097, copyright Ziffany Firdinal), README tema Build for Your World / Indie (H-098) + kalimat anti-RAG dan new-work-only, motivasi PRD = korpus aturan (angka LO dari laporan operator, anonim), hint 1.5.0 final (L2#10), dist-static dibangun ulang dari `84c6513` (kemudian dari `432dd76f`, lihat baris Ekspor statis ulang). Rencana rewrite histori `_kerja/orkestrasi/M52-rewrite-histori-rencana.md` (H-096, belum dijalankan). Repo masih private.
- `tolak` UU PT selesai (H-099): prompt D v3 268dd67, kode Tier 1 f2b5417, run D b709ac3 (4.992 micro-USD), 3 butir disetujui operator, split v3, grid ulang tanpa Spark (pilihan profil tidak berubah), profil + ekspor statis ulang (faa343d). Jawaban C untuk 3 butir `tolak` UU PT (`f52f6a7`, best `d7a9dd24` + baseline `ed489a1e`): Contributor 6/6 abstain (4 `tolak`, 2 `bukti_tidak_cukup`; 1.964 micro-USD), Spark Open Baseten 6/6 (5 + 1; 22.676 micro-USD), Glimmer lokal 6/6 (4 + 2; 0); sel 2×2 18/18 `abstained_correct`.
- Biaya (H-104 butir 3, L2#11, 29 Okt): header U0 dan README = `Run cost (main results)` = buku belanja pool default (R1 `main_results_spent_usd_micros`) 561.741 micro-USD; eksperimen per pool terpisah (R1 `pool_spend`, tabel U8 "Spend by budget pool", README Limits): Baseten 15.513.750 (A 93.751, B 15.366.732, C 53.267); pool sapuan H-102 dirangkai (`cost_fields` meneruskan `off_pin`), angka per 29 Okt di baris sapuan di atas; README memuat angka pool sapuan dan diuji `test_readme_cost_figures_match_stored_runs`.
- Ekspor statis ulang bersih dari `432dd76f` (L2-pascasapuan, 29 Okt): `rm -rf dist-static`, export + `npm run build:static` + `--check` 0 temuan; `dist-static/data` 1.097 berkas, `dist-static` 1.119 berkas; scan nilai `*KEY*` `.env` di dist-static 0. pytest 1840, vitest 321. (Sebelumnya: HEAD `84c6513`, pytest 1402, vitest 287, `dist-static` 1.122 berkas.)

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

- M5.1: Tier 4 UX review + kunci adegan video (putusan 8); setelah itu agen menyetor screenshot per adegan.
- README Limits teks pembanding + sapuan (L2-pascasapuan, commit `ab47ba00`): menunggu tinjauan L1/operator.
- Pemicu 31 Okt H-017 (31 Okt malam WIB).
- Gate M5.2 (setelah sapuan selesai, H-108): rewrite histori + force push (H-096), repo publik, Pages; butir NOTICE "unverified, pending operator" (kartu Glimmer HF, syarat keluaran Contributor, endpoint Baseten, Official Rules terpisah, versi jurnal Magesh).
- Isian form submit: repo catatan `docs/10-SUBMIT.md` (nama tim, feedback, Most Viral). Video milik operator.
- Keputusan L1 yang bisa dibalik: keterangan "agen L3 (Claude)" di `docs/scenarios` dibiarkan sebagai disclosure.
- Teks tooltip header `Run cost (main results)` (`frontend/src/components/Header.tsx` `RUN_COST_TITLE`) draf L2#11, menunggu L1.

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

1. Sesi baru: L1 membaca `_kerja/orkestrasi/keadaan-L1.md` (RESUME + log) dan `keadaan-L2.md` (bagian L2#8), menjalankan ulang pytest (1840) dan vitest (321) di worktree bersih (`core.longpaths`; test akta v2 tidak lagi butuh salinan `_kerja/`), lalu melahirkan L2 baru bila ada mandat.
2. Gerbang operator: adegan + Tier 4 UX M5.1, gate M5.2 (rewrite histori H-096, publik, Pages), isian submit. Pemicu 31 Okt H-017.
3. Agen (tidak terblok, kecil): opsional test Glimmer di mode statis (belum dikerjakan; tidak ada agen aktif per 29 Okt).
4. Proses per 29 Okt ±17Z: 5173 (frontend), 8000 (backend), 5177 (statis) dan 5175 (tailnet) mati; Glimmer di-unload. Untuk Tier 4/rekaman, nyalakan ulang dari HEAD; 5175 (tailnet) harus memakai `vite.config.ts` >= `b79e37b` (G-39).
