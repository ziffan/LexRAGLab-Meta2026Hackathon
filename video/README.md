# video/ — motion graphic untuk video demo

Aset video, bukan bagian app. Storyboard terkunci: `docs/VIDEO.md` (putusan operator 18 dan 19). Spesifikasi MG: dokumen analisis narasi repo catatan (`docs/riset/2026-10-30-analisis-narasi-video.md`, c983b71) bagian 5.

Setiap berkas HTML berdiri sendiri: CSS dan JS inline, tanpa jaringan (tanpa CDN, tanpa fetch), font IBM Plex dari `video/fonts/` (salinan woff2 dari paket `@fontsource` yang sudah dipakai frontend; SIL OFL 1.1, teks lisensi di `licenses/` akar repo). Kanvas 1920x1080; jendela berukuran lain diskalakan proporsional. Warna dari token `frontend/src/theme.css` (H-083, sorot gold kuning). Label bahasa Inggris (H-018).

## Berkas

| Berkas | Adegan | Durasi | Varian (parameter URL) |
|---|---|---|---|
| `mg-1-hook.html` | S0 hook, 0:00–0:25 | 25 dtk | `?hook=A` (bawaan, terkunci), `B`, `C`, `D` (alternatif 4.1) |
| `mg-s-title.html` | Kartu judul awal S1, 0:25–0:29 | 4 dtk | — |
| `mg-2-tech.html` | T1 tech highlight, di dalam 2:10–2:35 | 20 dtk | `?pair=low` (bawaan, terkunci O5), `?pair=medium` (alternatif 4.1) |
| `mg-3-end.html` | Kartu akhir di I1 | 8 dtk (boleh dipotong 2–5 dtk) | `?hook=A|B|C|D` menyamakan baris "problem-size figures" dengan hook yang dipakai |

Varian T1-B (sapuan effort) dan "Pembuka langsung app" tidak dibuat: T1-B memakai angka laporan sapuan yang tidak ada di README, dan pembuka app adalah rekaman layar, bukan MG.

## Pemutaran dan render

- `?dur=26` meregangkan atau memampatkan seluruh timeline secara linear ke 26 detik, untuk menyamakan MG dengan durasi VO; `?t=` lalu dihitung dalam detik keluaran.
- `?t=12.5` membekukan frame pada detik 12,5. Semua animasi adalah fungsi murni dari `t` (tanpa transisi CSS, tanpa acak), jadi frame yang sama selalu identik.
- Tanpa `?t` (atau `?play=1`): putar real-time dari 0 setelah font dimuat, lalu berhenti di frame terakhir. `?delay=2` menahan frame 0 dua detik sebelum mulai (untuk perekam layar).
- `window.MG = { duration, render(t) }` tersedia untuk render per frame.
- Rekam (a): browser layar penuh 1920x1080 (F11), buka berkas lewat `file://`, rekam dengan OBS atau perekam bawaan. Rekam (b): tangkapan per frame `?t=` dengan langkah 1/30 detik (Chrome headless `--screenshot --window-size=1920,1080`), lalu rangkai dengan ffmpeg 30 fps.
- Screenshot pemeriksaan: Chrome headless `--headless=new --window-size=1920,1080 --screenshot=<png> "file:///.../mg-1-hook.html?t=12.5"`.

## Placeholder operator

| Placeholder | Berkas, field | Diisi dari |
|---|---|---|
| URL repo publik | `mg-3-end.html` `DATA.repo_url` (null = kotak "TODO operator") | Operator, setelah gate M5.2 (H-029) |
| Nama engine TTS | `mg-3-end.html` `DATA.tts_engine`: **terisi "VoxCPM2"** (30 Okt) | Laporan L2-tts lewat L1: VoxCPM2 (openbmb/VoxCPM2, Apache-2.0), suara voice design `electra`, bukan tiruan orang nyata; teks "Narration: synthetic voice (VoxCPM2, local TTS)." |

Kotak TODO berwarna merah supaya tidak terlewat saat rekaman. Jangan merekam MG-3 final sebelum URL repo terisi.

## Durasi VO dan parameter `?dur`

Durasi VO terukur (laporan L2-tts, tempo 1,12; detik): S0 26,09; S1 13,52; D1 13,05; D2 22,97; D3 14,70; D4 17,73; D5 17,84; T1 26,83; I1 25,28; total 178,01 (target ekspor <= 178).

| MG | Bawaan (slot storyboard) | Usulan untuk VO | Catatan |
|---|---|---|---|
| MG-1 | 25 dtk | `?dur=26.1` | S0 seluruhnya MG-1 |
| MG-S | 4 dtk | tetap | Kartu judul di awal S1 (13,52 dtk); sisa S1 rekaman APP |
| MG-2 | 20 dtk | `?dur=22` atau sesuai sisa | T1 26,83 dtk = APP (a) 2–3 dtk + MG-2 + APP (c) 2 dtk; MG-2 mengisi sisanya |
| MG-3 | 8 dtk | tetap, atau dipotong | I1 25,28 dtk = APP U7 Export + MG-3; MG-3 hanya kartu akhir |

Total 178,01 dtk sudah di batas ekspor 2:58; bila edit melewati batas, MG-3 dipotong lebih dulu (storyboard).

## Angka di layar dan sumbernya

RM = `README.md`. Tidak ada angka lain di layar selain yang di tabel ini (durasi dan posisi animasi bukan klaim).

| MG | Teks di layar | Nilai `DATA` | Sumber |
|---|---|---|---|
| MG-1 A, D | "≈ 320K tokens", satu UU | `statute_tokens` 320000 | RM "Why": "about 320 thousand tokens" |
| MG-1 A, D | "200K-token context window" | `statute_window_tokens` 200000 | RM "Why": "more than a 200-thousand-token window on its own" |
| MG-1 A | "≈ 5.8 × a 1M-token context window", berkas uji tuntas | `dd_window_multiple` 5.8 | RM "Why": "about 5.8 million for a full due diligence file (1.2 to 5.8 times a 1-million-token window)" |
| MG-1 A, D | "≈ 1 in 10", "about 10% of the regulation text" | `regulation_used_pct` 10 | RM "Why": "Of the regulation text, only about 10% was actually used" |
| MG-1 D | "≈ 15 billion tokens", "two due diligence engagements, about 120 agent sessions" | `dd_cached_tokens_billion` 15, `dd_engagements` 2, `dd_sessions` 120 | RM "Why", paragraf "Supporting, secondary" |
| MG-1 A | Label "1M" pada enam kotak, "1M-token context window" | jumlah kotak = pembulatan ke atas `dd_window_multiple` | RM "Why": "1-million-token window" |
| MG-1 B | "46,583 tokens", korpus UU PT | `uupt_tokens` 46583 | `runs/measure/5db7720bc1f5a121.json` baris `section = "_document"`, `tokens_local` |
| MG-1 B | Posisi sorotan Pasal 102 (visual, tanpa angka) | `art102_start_char` 141959, `art102_end_char` 143179, `uupt_chars` 213139 | `runs/corpus/uupt-40-2007.c56e4f0f38a4.json` (`batang_tubuh` [141959–143179]); MEA `chars` |
| MG-1 B | "Article 102" | teks `markLabel` | Pasal 102 = gold butir K-01 (`data/butir/uupt.v16.jsonl`); offset di `runs/corpus/uupt-40-2007.c56e4f0f38a4.json` |
| MG-S | "Oct 26 – Nov 4, 2026" | `line3` | RM baris 8 dan "Built before vs during the hackathon" ("26 Oct to 4 Nov 2026") |
| MG-2 | "$0.561741", "Run cost (main results)" | `run_cost_micro_usd` 561741 | RM Limits: "561,741 micro-USD (shown as $0.561741)"; sama dengan header U0 |
| MG-2 | "40-token limit" | `header_limit_tokens` 40 | `config/header_b.toml` `max_header_tokens = 40`; RM Limits "header over 40 tokens" |
| MG-2 low | "816 of 1,783 calls" (Spark Open), "142 of 1,926 calls" (muse-spark-1.3-contributor) | `header_over.low` | RM Limits, sapuan effort: "Contributor 7.4% (142 of 1,926 calls, `low`)", "Spark Open 45.8% (816 of 1,783, `low`)" |
| MG-2 medium | "1,919 of 2,923", "110 of 1,048" | `header_over.medium` | RM Limits: "Spark Open ... 65.7% (1,919 of 2,923, `medium`)", "Contributor ... 10.5% (110 of 1,048, `medium`)" |
| MG-2 | "3 must-refuse questions", "6 of 6 abstained" per model; "4 refused, 2 insufficient evidence" (Contributor), "5 ... 1" (Spark Open), "4 ... 2" (Glimmer) | `must_refuse_items`, `abstain` | RM Limits (comparators): "On the three must-refuse items every answer abstained ... (6 of 6 each; Contributor 4 `tolak` and 2 `bukti_tidak_cukup`, Spark Open 5 and 1, Glimmer 4 and 2)" |
| MG-2 | Effort run dasar peran C: Contributor "low", Spark Open "low", Glimmer "high" | `base_c_effort` | `config/model.toml` `[effort] c = "low"`, `profiles.glimmer_local.reasoning_effort = "high"`; RM "What Muse Spark does" (Glimmer high) |
| MG-2, MG-3 | "1.3" di ID model `muse-spark-1.3-contributor` | `MODELS` | RM baris 8, `config/model.toml` |
| MG-2, MG-3 | "Q4_K_M" (Glimmer) | `MODELS.glimmer.host` | RM "What Muse Spark does" (comparators) |
| MG-3 | "30 Dec 2022", "UU 40/2007", "five synthetic deeds" | teks `LINES` | RM "Document families" dan "Data and licensing" |
| MG-3 | Tagline | `tagline` | `frontend/src/content/tagline.json` (status final) |

Rumusan yang bukan angka: "Apache-2.0 per Meta docs" untuk Glimmer (putusan 18 O11; `NOTICE` butir 4), "Contributor mode: Meta may use the content to train future models" (RM "Data and licensing"), "Built with Muse Spark Open (tokenizer for local token counts)" (RM "Built with Muse Spark Open. Token counts use the Muse Spark Open tokenizer"; `NOTICE`, Muse Model License bagian 2).

Catatan S0-B: naskah VO S0-B menyebut "a single article of under three hundred [tokens]". Angka 266 token itu hasil hitung ulang pemeriksa L3 (dokumen analisis bagian 10), tidak tersimpan di run mana pun, jadi tidak ditampilkan di MG-1 B. Bila S0-B dipilih, operator memutuskan apakah frasa VO itu dipertahankan.
