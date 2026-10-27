# CONTEXT — keadaan terkini

Tujuan: satu layar tentang di mana proyek berada, diperbarui setiap akhir sesi kerja.
Sumber keputusan: H-017, H-027, H-044, H-052, H-057, H-058, H-062..H-083.

diperbarui: 2026-10-27 16:55 UTC, sesi orkestrasi berlapis (L2#5) di mesin otoritatif; operator pergi sampai besok, gerbang terkumpul di `_kerja/orkestrasi/keputusan-pagi.md`

## Status

- M0 **selesai**. M1 **kode dan review selesai**.
- M2: M2.1–M2.3 ter-review; butir uupt v13 = 20. Mode D `unanswerable` akta (H-087): skenario Tier 1 + pemeriksa (0 BLOCKER) menunggu operator; kode belum. M2.4 stretch (potong). **M2.5 selesai (stretch)**: pembanding C Spark Open (Baseten) + Glimmer lokal, run tersimpan 3 butir demo (`d0b19c8`, `ea72711`).
- M3: skema A UU PT v2 operator; header B v2 lengkap; grid uupt `--with-headers --with-schema` v2 (profil structure_schema v2 dense header off).
- M4: grid akta multi-dokumen S1–S3 di main (`7d2cfef`, Tier 1). Terblok operator: skema A akta v2 (diff + varian G-4 siap), peta unit akta di Pipeline (skenario Tier 1 siap; tanpa ini V5/label C akta tidak berfungsi), I-62..I-65, header B akta ulang. Contoh profil UU PT (`25fc358`); perbaikan ekspor profil skema v2 (`bcf9431`). UI akta: "Pending operator review" tanpa angka sementara.
- M5: ekspor statis ulang (789 berkas data, check 0); README angka dari data. M5.2 menunggu LICENSE/publik/Pages (operator). Video dipisah ke operator.
- Belanja Model API kumulatif 517.455 micro-USD (plafon 20.000.000). Baseten 32.293. Glimmer 0.
- HEAD `bcf9431`: pytest 1190, vitest 250, tsc bersih.

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

Semua di `_kerja/orkestrasi/keputusan-pagi.md` (urut paling memblokir): skema A akta v2 + varian G-4, peta unit akta, I-62..I-65, header B akta, skenario H-087, nilai config M2.5, teks hint pending. Juga Tier 4 M2.3/M3.3, pemicu 31 Okt H-017, LICENSE/push publik/Pages (M5.2).

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
3. Berkas keadaan orkestrasi: `_kerja/orkestrasi/keadaan-L2.md`.
