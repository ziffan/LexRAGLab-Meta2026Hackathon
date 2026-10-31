# VIDEO — rencana video demo

Tujuan: storyboard terkunci, aturan isi, motion graphic, audio, checklist rekaman, daftar run wajib per adegan, jadwal produksi, dan gate unggah untuk video demo.
Sumber keputusan: H-006, H-011, H-017, H-018, H-021, H-028, H-029, H-031, H-039, H-041, H-043, H-045, H-047, H-050, H-053, H-054, H-060, H-098, H-100, H-113, H-114; putusan operator 18, 19, 20 (30 Okt) dan 21 (31 Okt).

Kalau Official Rules menetapkan durasi atau format lain, rules yang menang, dan dokumen ini disesuaikan. Komponen layar per adegan: `docs/UI-SPEC.md` §7.

## Status

**Storyboard dikunci operator 30 Okt (putusan operator 19)** dari usulan agen di repo catatan `docs/riset/2026-10-30-analisis-narasi-video.md` (c983b71) bagian 4, dengan pilihan putusan 18. Alternatif bagian 4.1 tetap terbuka sampai penyuntingan/unggah (operator memilih saat itu). Motion graphic ada di `video/` (lihat `video/README.md`). Storyboard lama (25 Okt) disimpan di bagian "Riwayat" di bawah.

Produksi (putusan operator 20): video dibuat agen lewat pipeline skrip; v1 dirender dari HEAD saat putusan 20, v2 dari main `ca33dadd` (v2 177,08 dtk, takarir dibakar, `.srt` sidecar), v3 31 Okt (177,081 dtk; sama dengan v2 kecuali T1(c) yang kini menampilkan butir must-refuse `usulan-83bb3dc705c43f4c`, Glimmer Abstained; laporan QA `_kerja/video-prod/out/laporan-v3.md`), v4 31 Okt (177,081 dtk; putaran kamera T1(c) saja, 3 MINOR v3 tertutup, 2 MINOR baru; `_kerja/video-prod/out/laporan-v4.md`), v5 dan v6 31 Okt (177,081 dtk; framing D4 dan T1(c), QA v6 LULUS 0 MINOR; `_kerja/video-prod/out/laporan-v6.md`), render final diulang setelah freeze 3 Nov. Unggah, form, dan pilihan alternatif 4.1 tetap operator. Temuan v1 Q1–Q3 diputus A (putusan 21: tanpa kode; D3 footer provenance dari halaman utama, D4 dan D1 di-crop); temuan v2: V2-1 ditangani di v3 (rekam ulang T1(c); QA v3 lulus dengan catatan MINOR, `laporan-v3.md`), V2-2 dibiarkan (putusan operator 31 Okt; batasan dicatat sebagai U3 di `docs/LIMITS.md`), V2-3 dan V2-4 masih terbuka di catatan kerja operator.

Putusan 8 (27 Okt: video milik operator, agen tidak mengunci storyboard) tetap berlaku dalam arti kunci ada di tangan operator; penguncian 30 Okt dilakukan operator sendiri.

## Syarat video (panduan peserta 26 Okt)

| Hal | Asumsi | Dasar |
|---|---|---|
| Durasi | Tiga menit; storyboard 3:00, ekspor akhir paling lama 2:58 | Panduan peserta 26 Okt: "three minute demo video"; dokumen analisis bagian 4 |
| Platform | YouTube unlisted, cadangan Loom; tautan harus bisa diakses | Panduan: "your video link is accessible"; platform tidak ditentukan |
| Bahasa | Narasi Inggris, UI Inggris, teks hukum Indonesia dengan gloss | H-018 |
| Ringkasan tertulis | 100–200 kata, bahasa Inggris | Asumsi; field form belum terlihat |
| Repo | Publik, Apache-2.0 | Panduan: "Repositories must be public"; H-029 |
| Isi | Hanya fitur yang dibangun selama acara; yang dibuat selama acara harus bisa diidentifikasi ("Judges must be able to clearly identify what was created during the Hackathon") | Panduan, aturan "Demo requirements"; gagal menandai = diskualifikasi |
| Tema dan domain | Tema "Build for Your World" (track Indie) dan domain hukum Indonesia jelas bagi juri: kartu judul MG-S dan narasi S1 | H-098; putusan 19 (sebelumnya: "video dan narasi milik operator (putusan 8), tanpa storyboard dari agen") |
| Audio | Belum ada Official Rules soal audio/alat AI pihak ketiga; acuan Participant Guide + waiver | Putusan 18 O9 (operator cek email/akun), H-043 |

4 November disisihkan untuk video, dan kode dibekukan 3 November malam.

## Pesan yang harus sampai

Satu kalimat: **"Muse Spark reads a new family of legal documents and finds the chunking and retrieval setting that feeds an LLM the right clauses, measured, not guessed."** (menjadi kalimat S1 dengan sedikit perubahan)

Penonton harus pulang dengan tiga hal:
1. Setting chunking itu bisa diukur, dan hasilnya terlihat sebagai frontier pada anggaran token yang sama.
2. Spark mengerjakan bagian yang tadinya butuh manusia: A, B, C, D.
3. Polanya berpindah ke keluarga dokumen lain.

## Keputusan video (putusan operator 18 dan 19, 30 Okt)

| Butir | Keputusan | Dasar |
|---|---|---|
| Hook | **S0-A**: angka operator yang sudah di README (satu UU lebih dari 300 ribu token; satu berkas uji tuntas sekitar 5,8x jendela 1 juta; sekitar 1/10 naskah peraturan terpakai). "14 juta token" dan "3–10%" tidak dipakai (angka klien, putusan 10 butir 4) | 18 O1 |
| Angka regulasi per pekerjaan | Tidak di video | 18 O2 |
| Titik held-out yang lebih baik dari profil terpilih | Tidak di VO; teks layar "Chosen on tune; held-out shown for reporting" wajib terlihat di D2; jawaban Q&A di dokumen analisis N4 | 18 O4 |
| Tech highlight T1 | Perbandingan model, pasangan effort `low` | 18 O5 |
| Laju gagal header di MG-2 | Hitungan mentah (816 of 1,783; 142 of 1,926); README memuat baris hitungan mentah (`cfbaea04`) | 18 O6 |
| Atribusi Glimmer | "Apache-2.0 per Meta docs" sampai kartu model terverifikasi (`NOTICE` butir 4: kartu HF belum terverifikasi) | 18 O11 |
| Berkas motion graphic | `video/` repo app (ikut repo publik Apache-2.0, wajib lolos secret scan M5.2) | 18 O8 |
| Storyboard | Dikunci sesuai usulan bagian 4; alternatif 4.1 terbuka | 19 butir 1 |
| Voice over | TTS lokal lewat repo `audiobook-maker`; lisensi bobot dan suara harus mengizinkan publikasi; tanpa kloning suara orang nyata; kartu akhir memuat pengungkapan suara sintetis; sampel dengar ke operator sebelum render penuh. Merevisi 18 O7 ("suara operator sendiri"). *Engine direvisi H-114: ElevenLabs `eleven-v4` (OpenRouter), suara `brian`* | 19 butir 2, H-114 |

## Storyboard terkunci (30 Okt)

Total 3:00 (180 detik), 392 kata ucap, rata-rata 131 kata/menit (per adegan 114–144, di bawah plafon 150). Ekspor akhir paling lama 2:58: MG-3 dipotong lebih dulu bila perlu. Jenis: **APP** = rekaman layar app mode replay (5173 + 8000 dari HEAD beku, tanpa key); **MG** = motion graphic HTML di `video/`. Kode sumber angka: lihat dokumen analisis "Singkatan sumber" (RM = README, GRD = grid UU PT `runs/grid/e7ffa7b0…`, GRA = grid akta `runs/grid/86e701f5…`, MEA = `runs/measure/5db7720bc1f5a121.json`, CFG = `config/`, PRO = `runs/proposals/records/`, ANS = jawaban C, AMD = analisis perbandingan model repo catatan).

| # | Waktu | Jenis | Yang tampil | Peran | Angka di layar + sumber | Voice over (Inggris) | Disclosure di layar |
|---|---|---|---|---|---|---|---|
| S0 | 0:00–0:25 | MG-1 | Tiga kartu angka: satu UU > 300K token lawan garis jendela 200K; berkas uji tuntas ≈ 5.8 × jendela 1M; ≈ 1/10 naskah peraturan terpakai. Lalu tiga keluarga dokumen (statute, deed, internal policy) dan gunting "chunk size = ?" | — | 320 ribu, 5,8x, sekitar 10% (RM Why) | I do legal work with AI agents: opinions, due diligence, contracts. In my own files, one statute ran over three hundred thousand tokens. One due diligence file was nearly six times a million-token window. Yet only about a tenth of the regulation text was ever used. So retrieval is a must. But which chunk size? Guessing is opening Pandora's box. | "Operator's measurements of prior engagements (not included in the repository). Context, not output of this app." |
| S1 | 0:25–0:40 | MG-S → APP | Kartu judul (LexRAGLab, Indie track, Build for Your World, Indonesian legal documents, built during the hackathon Oct 26 – Nov 4, 2026), lalu landing app (tagline U0) | — | — | LexRAGLab is an evaluation lab for legal RAG builders. Muse Spark reads a new family of Indonesian legal documents; the lab measures which chunking and retrieval setting feeds the model the right clauses. | Model `muse-spark-1.3-contributor` (label U0) |
| D1 | 0:40–0:55 | APP | U1 butir K-01, setting fixed 512/64 dense: potongan rank 1 mulai di tengah ayat (3), gold kuning (H-083), lencana "Gold split across chunks" bila tampil; lalu profil terpilih: satu potongan = Pasal 102 utuh | — | 151 dari 542 karakter gold lawan 542 dari 542 (GRD; teks layar opsional) | Here is a held-out Company Law question about Article 102. The fixed-size chunk it retrieves starts in the middle of paragraph three. The structure-aware chunk keeps the whole article. | Gloss "ayat = paragraph" |
| D2 | 0:55–1:17 | APP | U2 frontier held-out, anggaran 2.000, dua titik disorot (terpilih, fixed dense); U4 ringkasan held-out; catatan "Chosen on tune; held-out shown for reporting" | Grid (tanpa LLM) | 2.000 dari 46.583 token (CFG, MEA); 6 dari 8 lawan 5 dari 8 (GRD) | The lab runs the grid: chunker, dense, BM25 or hybrid, context header on or off, all at one budget, two thousand tokens out of a forty-seven-thousand-token statute. The setting is chosen on tune items. On eight held-out items it fully covers six; fixed-size covers five at best. | "8 held-out items, raw counts, no significance test" |
| D3 | 1:17–1:30 | APP | `/review` (U6) daftar "Decided", satu kartu usulan parafrase yang disunting operator; footer U9 provenance (dari halaman utama, bukan di `/review`; putusan 21 Q1) | D | 14 disetujui, 2 ditolak (PRO; hanya di VO, putusan 21 Q1); "23 items: 9 operator-written, 14 Spark-proposed and operator-approved" (U9, RM) | Where do the test questions come from? Muse Spark proposes them with exact gold spans, including questions it must refuse. I review every one: for Company Law, fourteen approved, two rejected. | — |
| D4 | 1:30–1:50 | APP | Family = Deed. U5 skema v1 Spark lawan v2 operator (diff `marker_pattern`); U2 akta "transfer test, no profile selection", titik `structure_handwritten` "no structure recognized" | A | 69 dari 69 lawan 0 dari 69 (GRA, RM); fixed dense 64 dari 69 boleh tampil | Notarial deeds have no parser. Muse Spark read sample deeds and proposed their structure; I corrected its marker pattern. On the transfer test, that schema covers all sixty-nine gold items. The statute parser finds no structure and covers none. | "Five synthetic deeds written by an AI agent, reviewed by the operator; fictitious identities" |
| D5 | 1:50–2:10 | APP | U3 dua kolom K-01: kiri terpilih (jawab, kutipan lulus `exists` dan `faithful`), kanan baseline (`Insufficient evidence`), ringkasan 2×2 | C | Tanda verifier (ANS); 2×2: terbaik 2 didukung + 1 abstain benar, baseline 2 abstain benar + 1 seharusnya menjawab (AMD §3.6) | Does a better setting give a better answer? Same model, same budget. From the chosen setting, Muse Spark answers, and its citation passes a deterministic verifier, not an LLM judge. From fixed-size, it reports the evidence is insufficient. | "1 item shown; valid-on-date check not run" |
| T1 | 2:10–2:35 | APP + MG-2 + APP | (a) 2–3 detik U1 panel "Context header (B)" Pasal 102; (b) MG-2: lencana biaya, dua batang header lewat batas 40 token, tiga model "6 of 6 abstained" pada must-refuse; (c) 2 detik U3 pemilih model berpindah ke Glimmer. MG-2 memuat kartu peran (putusan operator 31 Okt). | B (+A, C pembanding) | 816/1.783 dan 142/1.926 (`docs/LIMITS.md` "Effort sweep"); 6 dari 6 per model, 3 butir (`docs/LIMITS.md` "Comparators"); $0.561741 (RM Limits, `docs/LIMITS.md` "Run cost") | Muse Spark writes a context header per chunk, with the statute cached. I ran roles A, B and C on open-weight Muse models. Against the forty-token header limit, Spark Open went over in 816 of 1,783 calls; Muse Spark one point three in 142 of 1,926. On three must-refuse questions, every model abstained every time. | Catatan kaki MG-2: host dan sifat open-weight tiap model, Glimmer "Apache-2.0 per Meta docs", effort per batang, cakupan B pembanding sebagian, run terpisah, prompt dikalibrasi pada muse-spark-1.3, batas dihitung tokenizer lokal, effort run dasar per kolom must-refuse, tanpa perbandingan mutu dan tanpa uji signifikansi |
| I1 | 2:35–3:00 | APP → MG-3 | U7 Export: pratinjau profil JSON dan "Download JSON" (mode statis, G-47); lencana U0 "Run cost (main results) $0.561741" disorot; lalu kartu akhir MG-3 | Ekspor | 561.741 micro-USD (U0, RM Limits; pool eksperimen dilaporkan terpisah) | The output is a versioned profile you drop into your own RAG pipeline; all main results cost fifty-six cents. Muse Glimmer already ran roles A and C, and B on part of the corpus, on my own machine. With tuned prompts, confidential files could stay inside the firm. Next: internal policies. Research demo, not legal advice. | Kartu akhir lengkap (bagian "Kartu akhir" di bawah) |

Durasi: 25 + 15 + 15 + 22 + 13 + 20 + 20 + 25 + 25 = 180 detik. Kata ucap per adegan: 60, 33, 29, 47, 31, 39, 38, 59, 56 (angka di T1 dihitung sebagaimana diucapkan).

Pemetaan rubrik: Impact (S0, I1), Use of Meta AI Tooling (D3, D4, D5, T1), Technical Depth (D2, T1), Demo (D1–D5 dari app yang berjalan).

### Alternatif terbuka (dokumen analisis bagian 4.1)

Dipilih operator saat penyuntingan/unggah (putusan 19 butir 1). Naskah lengkap di dokumen analisis bagian 4.1.

| Pilihan | Kapan dipakai | Varian MG yang sudah siap |
|---|---|---|
| S0-A (terkunci) | Bawaan | `mg-1-hook.html?hook=A` |
| S0-B, angka terukur di repo | Bila operator tidak ingin memakai pengukuran kerja nyata di video | `?hook=A` diganti `?hook=B` (46.583 token, sorotan Pasal 102); kartu akhir `mg-3-end.html?hook=B`. Catatan: frasa VO "under three hundred" (266 token) tidak tersimpan di run mana pun; operator memutus apakah dipertahankan |
| S0-C, tanpa angka | Bila ada keraguan soal angka klien | `?hook=C`; kartu akhir `?hook=C` (baris problem-size dihapus) |
| S0-D, 15 miliar token cached | Paling dekat ke maksud "dibayar agen" | `?hook=D` (RM "Supporting, secondary") |
| D2-B, jujur soal header-on | Menjawab pertanyaan juri soal titik `dominated` | Rekaman APP, tanpa MG |
| T1-B, sapuan effort | Bila perbandingan antar model dianggap rawan | Tidak dibuat: angka sapuan (978 → 1.913 token output, header 33,3–34,0 token, recall 0,9992) tidak ada di README; perlu baris README dulu agar video = README |
| T1 pasangan `medium` | Menghindari sel Contributor `low` yang mencampur prompt v1/v2 | `mg-2-tech.html?pair=medium` (1.919/2.923 dan 110/1.048, RM Limits) |
| Pembuka langsung app | Bila operator ingin "demo" sejak detik pertama | Rekaman APP (adegan 0 storyboard lama) |

## Motion graphic (`video/`)

| Berkas | Adegan | Durasi |
|---|---|---|
| `video/mg-1-hook.html` | S0 | 25 dtk |
| `video/mg-s-title.html` | Awal S1 | 4 dtk |
| `video/mg-2-tech.html` | T1 (b) | 20 dtk |
| `video/mg-3-end.html` | I1, kartu akhir | 8 dtk (boleh dipotong 2–5 dtk) |

HTML statis tanpa jaringan, 1920x1080, animasi deterministik (`?t=` membekukan frame, `?play=1` real-time), tema H-083, font IBM Plex lokal (OFL 1.1). Tabel angka → sumber, cara render, dan placeholder operator: `video/README.md`. Setiap MG diberi label "Context, not output of this app" (MG-1) atau "From stored runs" (MG-2), supaya aturan "demo hanya fitur yang dibangun selama acara" tidak dilanggar.

## Audio

- Voice over: ElevenLabs `eleven-v4` lewat OpenRouter, suara bawaan `brian` (H-114), diperiksa terhadap naskah dengan Muse Voice Transcribe (H-113, `video/qa/vo-report.md`). Semula (putusan 19 butir 2): TTS lokal lewat repo `audiobook-maker` operator, dikerjakan L2-tts. Syarat: lisensi bobot model dan suara mengizinkan publikasi di submission; tanpa kloning suara orang nyata; sampel dengar (S0 dan T1) disetujui operator sebelum render penuh. *Direvisi H-114 (30 Okt): engine = ElevenLabs `eleven-v4` lewat OpenRouter, suara bawaan `brian` (bukan kloning orang nyata), dipilih operator setelah 3 putaran dengar buta (VoxCPM2 terbaik skor 4 "agak seperti robot"; ElevenLabs skor 5); hak pakai: akses berbayar OpenRouter, ditafsirkan operator memenuhi syarat komersial ElevenLabs.* Semula: VoxCPM2 (openbmb/VoxCPM2, Apache-2.0), suara voice design `electra`, laporan L2-tts 30 Okt; terisi di `video/mg-3-end.html`. Durasi VO terukur per adegan (`brian` total 169,61 dtk) dan parameter `?dur` MG: `video/README.md`.
- Pengungkapan: "Narration: synthetic voice (ElevenLabs text-to-speech)." di kartu akhir MG-3 dan di deskripsi video.
- Takarir Inggris dibakar ke video, dari kolom VO storyboard.

## Kartu akhir (MG-3)

1. Tagline (`frontend/src/content/tagline.json`) dan URL repo publik (terisi 30 Okt, putusan operator 20; gate unggah tetap mensyaratkan repo publik, H-029).
2. "Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4, 2026. Pre-event material: planning docs and the statute text only; the UI theme follows the operator's pre-event design mockup (markup not copied)."
3. "Model: muse-spark-1.3-contributor (Contributor mode: Meta may use the content to train future models). Used because every document here is public or synthetic. Confidential documents: use the Standard model ID." (H-028)
4. "Company Law text: unofficial consolidation of UU 40/2007 by the operator, as of 30 Dec 2022." (H-031, H-045)
5. "Notarial deeds: five synthetic deeds written by an AI agent and reviewed by the operator; all identities fictitious." (H-039, H-041)
6. "Comparators: Muse Spark Open (open-weight, Baseten) and Muse Glimmer (open-weight, Q4_K_M, running locally on the operator's machine; Apache-2.0 per Meta docs), labelled with model and reasoning effort, separate runs, never mixed with main results." (H-047, H-060, H-100; putusan 18 O11)
7. "Problem-size figures: the operator's measurements of prior engagements, not output of this app." (mengikuti varian hook)
8. "Built with Muse Spark Open (tokenizer for local token counts)." (README; `NOTICE`, Muse Model License bagian 2)
9. "Narration: synthetic voice (ElevenLabs text-to-speech)." (H-114, merevisi putusan 19 butir 2)
10. "Narration checked against the script with Muse Voice Transcribe (Meta Model API); not part of the app." (H-113; `NOTICE` butir 4; ditambahkan atas permintaan operator 30 Okt malam, F9)
11. "© 2026 Ziffany Firdinal. Code licensed under Apache-2.0." (`NOTICE` "Copyright 2026 Ziffany Firdinal"; Apache-2.0 di `LICENSE`; H-097; F9)
12. "Research demo. Not legal advice."

## Aturan isi

- Angka di video harus sama dengan angka di layar dan README. Pakai hitungan mentah ("7 of 12"), bukan persen, dan tanpa klaim signifikansi.
- Butir yang dipakai di adegan sudah dicocokkan manual ke teks (H-011). Butir adegan: K-01 (`scene_checked: true`).
- Model disebut sebagai `muse-spark-1.3` (varian Contributor). Satu kalimat disclosure (H-028): Contributor dipakai karena korpus publik atau sintetis; dokumen rahasia memakai Standard dengan mengganti model ID. Tidak ada klaim soal Wonder atau model lain. Glimmer hanya disebut bila pembanding H-047 tampil (lihat butir di bawah).
- Tidak ada UI prototipe pra-acara, dan tidak ada kode prototipe itu di layar. App hackathon ini tentu tampil (H-021).
- Disclosure korpus (H-031, H-045, H-039): teks UU PT adalah konsolidasi tidak resmi yang disiapkan operator dari teks peraturan dan putusan MK (sampai 30 Desember 2022), dan akta adalah sintetis yang ditulis agen AI lalu direview operator. Satu baris di layar akhir video dan di README, tidak perlu narasi.
- Bila pembanding Glimmer tampil (H-047, H-053): disebut "Muse Glimmer, open-weight, running locally on the operator's machine", bukan bobot yang sama dengan Spark, dengan label model, kuantisasi, dan effort di U3. Jawabannya tidak dicampur dengan jawaban Contributor tanpa label. Tanpa klaim mutu bahasa Indonesia umum. Klaim bonus open-weight hanya setelah cara verifikasi "own hardware" dikonfirmasi penyelenggara.
- Bila Spark Open (Baseten, H-060) atau sapuan effort (H-102) tampil: disebut open-weight, host Baseten, dengan label model dan effort di layar; tidak dicampur dengan jawaban Contributor tanpa label. Klaim bonus open-weight hanya atas run tersimpan (H-060).
- Untuk akta tidak ada kata "held-out": butir akta adalah uji transfer tanpa split (H-054).
- Tidak ada akta asli, dokumen internal, data klien, atau `.env` atau API key di layar. Terminal yang direkam hanya terminal putar ulang.
- Tidak boleh dipakai (dokumen analisis bagian 2.3): "14 million tokens of regulation", "3 to 10 percent used", "no agent can handle the corpus", "the best profile covers 8 of 8 held-out", model mana pun "more accurate", effort tinggi "useless", klaim bonus open-weight, persen hasil, "UU PDP forbids sending documents abroad".
- Disclaimer tampil di I1 (VO) dan kartu akhir: "Research demo. Not legal advice."

## Checklist rekaman

| # | Butir | Dasar |
|---|---|---|
| 1 | Backend `uv run python -m backend.api --replay` (tanpa key; lencana REPLAY; memakai `server_app` dengan pemanasan), frontend `npm run dev`, keduanya dari HEAD beku. Muat halaman sekali dan tunggu header "Run cost (main results)" terisi (bukan `n/a`) sebelum merekam | G-48 |
| 2 | Jangan menekan Export di mode live. Rekam U7 dari replay statis (`dist-static`, port 5177) yang hanya menampilkan pratinjau dan Download. Bila Export live terlanjur ditekan: `git checkout -- profiles/`, dan jangan `commit -a` saat server menyala | G-47 |
| 3 | Replay tanpa key (`uv run python -m backend.api --replay`): `.env` tanpa nilai key atau tidak ada; lencana `REPLAY` terlihat; tidak ada klik "Run live" | RM Run it |
| 4 | Tidak ada terminal, `.env`, jalur lokal, atau tab lain di layar. Tutup popover hint sebelum klip U3 (menutupi pemilih Model) | Aturan isi; temuan UX N-2 |
| 5 | 1920x1080, zoom browser 125–150%. Rekam per adegan, terpisah. Sorot dan zoom dibuat di editor | Teknis rekaman |
| 6 | Butir K-01; setting fixed 512/64 dense untuk D1 dan profil terpilih `d7a9dd24…` untuk sisanya; split held-out; anggaran 2.000 | GRD, `data/butir/uupt.v16.jsonl` |
| 7 | Jangan merekam lewat tailnet 5175 dengan `vite.config.ts` lebih lama dari `b79e37b` | G-39 |
| 8 | Glimmer tidak perlu dimuat: pemilih model U3 menampilkan run tersimpan | RM Limits |
| 9 | MG direkam dari `video/*.html` (layar penuh 1920x1080 atau render per frame `?t=`); `DATA.repo_url` MG-3 sudah terisi (tidak ada kotak TODO di layar); `?dur` MG sesuai durasi VO | `video/README.md` |
| 10 | Setelah rekaman: `git status` bersih (tidak ada `profiles/` berubah) | G-47 |
| 11 | Gate sebelum unggah di bawah, lalu tonton ulang tanpa suara dan dengan suara | Bagian Gate |

## Run tersimpan wajib per adegan (mode putar ulang)

Rekaman memakai mode putar ulang (M5.1). Adegan hanya bisa direkam bila run di bawah ada di `runs/`.

| Adegan | Run wajib | Endpoint (`docs/API.md`) |
|---|---|---|
| D1 | Potongan setting fixed 512/64 dense dan profil terpilih untuk K-01; retrieval butir itu | R4, R5 |
| D2 | Grid UU PT held-out pada anggaran default; ringkasan butir | R3 (`grid`, `items_summary`) |
| D3 | Usulan D yang diputus (UU PT) dan provenance butir | R3 (`proposals`, `items_summary`) |
| D4 | Skema akta v1 dan v2; grid akta transfer | R3 (`schemas`, `schema_diff`, `grid`) |
| D5 | Jawaban C untuk K-01, dua slot; hasil verifier; ringkasan 2×2 | R3 (`answers`, `answers_summary`) |
| T1 | Header B Pasal 102 (U1); jawaban C pembanding tersimpan untuk pemilih model U3 | R4, R3 (`answers`) |
| I1 | Profil UU PT; header biaya | W7 (statis: pratinjau), R1 |

## Produksi

| Tanggal | Langkah | Jam (operator) |
|---|---|---|
| 30 Okt | Storyboard dikunci (putusan 19); MG di `video/`; VO ElevenLabs `brian` (H-114) lolos pemeriksa H-113 | — |
| 30-31 Okt | v1, v2, v3, v4 dirender agen lewat pipeline skrip (putusan 20), menggantikan rekaman kasar 2 Nov | — |
| 3 Nov | Perbaikan layar bila perlu (M5.1); kode dibekukan 20:00 WIB | (masuk M5.1) |
| 3-4 Nov | Render final dari HEAD beku (agen); tonton ulang penuh di perangkat lain, unggah unlisted, form dan ringkasan 100–200 kata, pilihan 4.1 (operator) | ? (operator) |
| 4 Nov malam | Submit. Batas resmi 5 Nov 09:00 WIB adalah cadangan, bukan target | — |

Total jam operator: diisi operator.

Teknis rekaman:
- Rekam 1920x1080 dengan zoom browser 125–150% supaya teks hukum terbaca.
- Mode putar ulang tanpa API (M5.1).
- Narasi (TTS) dibuat terpisah dari layar per adegan, sehingga bisa diulang tanpa mengulang demo.
- Takarir dibakar ke video, karena penonton mungkin menonton tanpa suara.
- Sorotan dan zoom dibuat di editor, bukan dengan menggerakkan kursor saat rekam.

## Gate sebelum unggah

- [ ] Durasi ≤ 3:00, target ekspor ≤ 2:58 (Participant Guide, H-043).
- [ ] Setiap angka cocok dengan layar dan README (MG: tabel `video/README.md`).
- [ ] Jumlah butir dan asalnya disebut (footer U9 provenance dari halaman utama di D3; putusan 21 Q1).
- [ ] Keempat peran Spark terlihat, dan nama model tampil.
- [ ] Disclaimer tampil.
- [ ] Disclosure tampil di layar akhir video dan di README: Contributor (H-028), konsolidasi UU PT tidak resmi (H-031), akta ditulis agen AI dengan identitas fiktif (H-039, H-041), Glimmer sebagai open-weight lokal dengan "Apache-2.0 per Meta docs" (H-047; putusan 18 O11, menggantikan "atribusi kartu model" sampai kartu model terverifikasi).
- [ ] Pengungkapan suara sintetis di kartu akhir dan deskripsi video; lisensi engine/suara TTS terdokumentasi (putusan 19 butir 2).
- [ ] Tidak ada kotak TODO di MG-3 (URL repo dan engine TTS terisi).
- [ ] README (`README.md` dan `docs/README.id.md`): tautan "Demo video" dan "Live replay" diisi setelah unggah dan Pages (putusan 21 R-b; juga di gate M5.2).
- [ ] Tidak ada secret, akta asli, dokumen internal, atau UI prototipe pra-acara.
- [ ] Ditonton ulang penuh sekali tanpa suara dan sekali dengan suara.

## Riwayat

### Storyboard lama (25 Okt, digantikan storyboard terkunci 30 Okt, putusan operator 19)

Storyboard enam adegan sebelum usulan analisis narasi. Angka ditulis `{…}` karena run belum ada. Disimpan sebagai jejak; tidak dipakai lagi kecuali sebagai alternatif "Pembuka langsung app" (adegan 0).

| # | Waktu | Layar | Beat narasi (Inggris, ringkas) | Peran | Data yang harus siap |
|---|---|---|---|---|---|
| 0 | 0:00–0:20 | Pasal UU PT (misalnya tentang pemberhentian direksi) terbelah di tengah ayat oleh chunker ukuran tetap, span gold disorot kuning (tema H-083) | Legal RAG teams pick a chunk size by guess. In Indonesian regulation, a guess cuts an ayat in half, and the LLM cites half a rule | — | Satu butir kontrol operator yang terbelah oleh ukuran tetap |
| 1 | 0:20–0:55 | Panel potongan berpindah ke profil struktur, lalu frontier UU PT dengan dua titik disorot | Same token budget, `{n}` tokens. Structure-aware profile fully covers the gold for `{x of y}` held-out items, fixed-size for `{…}`. Each dot is a setting; the frontier is what's worth using | Grid (tanpa LLM) | Frontier UU PT, angka held-out, hitungan mentah |
| 2 | 0:55–1:25 | Deret frontier header B on vs off, filter butir parafrase, catatan run dengan token cached | Muse Spark writes a context header for every chunk, with the whole regulation cached. On paraphrased questions, the frontier moves by `{…}`. Cached tokens: `{…}`, cost `{$…}` | B, D | Frontier dua deret, filter asal/mode, catatan run B |
| 3 | 1:25–2:00 | Akta sintetis mentah → skema hasil induksi Spark → koreksi operator (diff v1/v2) → potongan akta | Notarial deeds have no parser. Spark reads a few and proposes the structure: head, body, closing, Pasal. I fix `{n}` lines, and the chunker follows the schema | A | Skema akta v1 dan v2, panel potongan akta |
| 4 | 2:00–2:35 | Panel bukti: jawaban dari profil terbaik vs pembanding, kutipan dengan tanda lulus/gagal; bila stretch Glimmer jadi, pemilih model berpindah ke Glimmer lokal untuk butir yang sama (H-053) | Does a better setting give a better answer? Same model, same budget. Best profile: citation passes. Baseline: `{fails / abstains}`. Checked by a deterministic verifier, not another LLM | C | Satu butir adegan yang dicek manual, ringkasan 2×2 per profil |
| 5 | 2:35–2:50 | Tombol ekspor profil, JSON profil, layar akhir dengan disclaimer | Output: a versioned profile you drop into your own RAG. Next family: internal policies. Research demo, not legal advice | Ekspor | Profil UU PT dan akta, jumlah butir dan asal |

Di adegan 1 atau 5 lama ditampilkan satu baris kecil: `{n} items: {a} operator-written, {b} Spark-proposed and operator-approved` (H-006); di storyboard terkunci baris itu tampil di D3.

Garis potong H-017 untuk storyboard lama:

| Yang dipotong | Akibat ke video |
|---|---|
| Uji 3 berlaku | Adegan 4 hanya menampilkan uji ada dan setia. Status berlaku disebut sebagai pekerjaan berikutnya |
| Frontier akta (M4.2) | Adegan 3 berhenti di potongan akta. Kalimat soal angka akta dihapus |
| Header B hanya untuk setting di frontier | Adegan 2 tetap; narasi menyebut "on the frontier settings" |
| Akta 5 dokumen, lantai 5 butir (potong 2) | Tidak berdampak ke adegan |
| Grid sempit (potong 3) | Tidak berdampak ke adegan; frontier memuat lebih sedikit titik |

Run wajib per adegan lama (digantikan tabel per adegan S0..I1 di atas):

| Adegan | Run wajib | Endpoint (`docs/API.md`) |
|---|---|---|
| 0 | Potongan setting ukuran tetap untuk butir adegan; retrieval butir itu | R4, R5 |
| 1 | Grid UU PT held-out pada anggaran default; potongan profil struktur; ringkasan butir | R3 (`grid`, `items_summary`), R4 |
| 2 | Grid dengan deret header B; run B dengan cached tokens; usulan D yang disetujui (mode parafrase) | R3 (`grid`, `runs_summary`, `proposals`), R6 |
| 3 | Skema akta v1 dan v2; potongan akta menurut skema | R3 (`schemas`, `schema_diff`), R4 |
| 4 | Jawaban C untuk butir `scene_checked`, dua slot; hasil verifier; ringkasan 2×2; bila stretch Glimmer dipakai, run Glimmer untuk butir yang sama | R3 (`answers`, `answers_summary`) |
| 5 | Profil UU PT dan akta; ringkasan butir | W7, R3 (`items_summary`) |

Adegan 1, 2, dan 4 lama tidak boleh hilang. Di storyboard terkunci, perannya dibawa D2, T1, dan D5. Uji 3 berlaku memang tidak dijalankan (D5: "valid-on-date check not run").

### Perubahan lain 30 Okt

- Jadwal produksi lama: 31 Okt kunci storyboard (1 jam), 2 Nov rekaman kasar (1), 4 Nov pagi rekam layar (1,5), 4 Nov siang rekam narasi + edit + takarir (2,5), 4 Nov sore unggah (1); total sekitar 7 jam. "31 Okt kunci storyboard" selesai 30 Okt; "rekam narasi" diganti TTS lokal (putusan 19 butir 2, merevisi putusan 18 O7 "suara operator sendiri"), lalu ElevenLabs `brian` (H-114).
- Target durasi lama "target 2:50" diganti storyboard 3:00 dengan ekspor akhir paling lama 2:58 (dokumen analisis bagian 4).
- Gate disclosure Glimmer: "atribusi kartu model bila tampil" diganti "Apache-2.0 per Meta docs" sampai kartu model terverifikasi (putusan 18 O11).
- Klausa catatan kaki T1 usulan "muse-spark-1.3 low mixes prompt v1/v2" tidak dipasang di MG-2: tidak ada di README (pemeriksa L3, 30 Okt); tetap tercatat di dokumen analisis (AMD §2.4) sebagai jawaban Q&A.
- Teknis rekaman lama "kecuali satu panggilan pendek di adegan 4 (W6) kalau ingin menunjukkan panggilan langsung" tidak dipakai di storyboard terkunci (semua adegan dari replay).
