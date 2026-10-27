# DECISIONS — ringkasan keputusan

Tujuan: satu baris per keputusan sebagai pointer; isi lengkap (Context → Decision → Consequences → Alternatives Rejected) ada di log keputusan lengkap operator (catatan perencanaan pra-acara, tidak dipublikasikan).
Sumber keputusan: H-001 sampai H-060.

Aturan: keputusan Locked tidak diubah tanpa revisi formal di log keputusan operator lebih dulu. Kalau dokumen di repo ini bentrok dengan keputusan, keputusan yang menang.

## Locked

| ID | Keputusan | Tanggal |
|---|---|---|
| H-001 | Track Indie | 2026-10-21 |
| H-002 | Nama dan janji form: LexRAGLab, sandbox evaluasi chunking dan retrieval hukum Indonesia, dengan dataset, Recall@K, metrik mutu | 2026-10-21 |
| H-003 | Prototipe pra-acara operator tidak diubah, tidak di-bundle, kodenya tidak disalin | 2026-10-21, diperluas 2026-10-25 |
| H-004 | Penemu setting per keluarga dokumen; Spark peran A dan B inti, C lantai bukti; grid tanpa LLM | 2026-10-25 |
| H-005 | Optimal = span recall dan precision token pada anggaran token tetap, Pareto frontier, pilih di tune lapor di held-out, per butir tanpa klaim signifikansi | 2026-10-25 |
| H-006 | Spark mengusulkan butir (literal dan parafrase wajib), operator memeriksa semua; asal `operator` / `spark_disetujui` | 2026-10-25 |
| H-007 | UU PT penuh (sejak revisi H-031), template akta transfer (hanya sintetis), aturan internal disebut saja | 2026-10-25 |
| H-008 | Obsolete, diganti H-031 | 2026-10-25 |
| H-009 | Status berlaku tiga nilai; tabel milik operator. Basis data direvisi H-031: anotasi konsolidasi UU PT | 2026-10-25 |
| H-010 | Glimmer tidak dipakai; bagian model direvisi H-028; direvisi H-047: Glimmer lokal hanya sebagai pembanding on-prem peran C (stretch) | 2026-10-25 |
| H-011 | UU PT (sejak revisi H-031) 15–20 butir disetujui, akta minimal 5 (H-017), minimal enam kontrol operator; butir adegan dicek manual | 2026-10-25 |
| H-012 | Sumbu grid: chunker × ukuran/overlap × mode retrieval × header B; anggaran default 2.000 token + dua pembanding (*satu sejak H-017*); nilai di konfigurasi (*dikunci H-058*) | 2026-10-25 |
| H-013 | Python 3.12 + FastAPI, React + TypeScript + Vite; tanpa database, auth, vector DB, LangChain | 2026-10-25 |
| H-014 | Tokenizer lokal deterministik (Muse Spark Open, cadangan `o200k`), dikalibrasi sekali terhadap endpoint hitung token | 2026-10-25 |
| H-015 | Split berstrata per asal dan mode, minimal tiga kontrol di held-out, seed tercatat, split lama tidak diacak ulang; porsi held-out 40% (H-049); akta tanpa split (H-054) | 2026-10-25 |
| H-016 | Responses API lewat SDK `openai`, `text.format` `strict: true`; skema tanpa `allOf`/`oneOf`/rekursi | 2026-10-25 |
| H-017 | Garis potong sejak hari pertama: uji 3 stretch, akta 3 dokumen / 5 butir (*direvisi H-039: 5 dokumen*), grid sempit; pemicu 31 Okt untuk B-frontier dan M4.2 | 2026-10-25 |
| H-018 | Narasi video, takarir, dan label UI bahasa Inggris; teks hukum Indonesia dengan gloss; video tiga menit (asumsi; dipastikan Participant Guide, H-043) | 2026-10-25 |
| H-019 | Wonder tidak dipakai; stretch Wonder dihapus (dari I-08) | 2026-10-25 |
| H-020 | API: endpoint baca dilebur menjadi snapshot per keluarga, endpoint tulis satu per aksi; replay membaca `runs/` (*direvisi H-050: `runs/` dan `data/`*) (dari I-17) | 2026-10-25 |
| H-021 | Larangan UI di video hanya untuk UI prototipe pra-acara (dari I-18) | 2026-10-25 |
| H-022 | Konfigurasi TOML, dibaca `tomllib` (dari I-04) | 2026-10-25 |
| H-023 | State frontend `useReducer` + context (dari I-02) | 2026-10-25 |
| H-024 | ~~Embedder `intfloat/multilingual-e5-large`, prefix `query: `/`passage: ` (dari I-13)~~ Obsolete, diganti H-042 | 2026-10-25 |
| H-025 | Embedding `.npy` per `chunk_set_hash` + JSON urutan `chunk_id` (dari I-01) | 2026-10-25 |
| H-026 | Grafik frontier Recharts (dari I-03) | 2026-10-25 |
| H-027 | Mesin GPU otoritatif untuk embedding, grid, dan run Spark; `runs/` dari mesin itu di-commit, mesin kedua hanya membaca; `RunRecord` mencatat host dan device (dari I-21) | 2026-10-25 |
| H-028 | Model API `muse-spark-1.3-contributor`, model ID di `config/model`, satu ID per run; Muse Code tetap Standard; disclosure di README dan video | 2026-10-26 |
| H-029 | Repo submission publik, Apache-2.0, dibuka di gate M5.2 setelah secret scan; korpus tidak dilisensikan ulang; tokenizer tidak di-commit (dari I-12) | 2026-10-26 |
| H-030 | SEOJK termasuk Pasal 42 UU 28/2014, diperlakukan sama dengan POJK (penilaian operator, dari I-10) | 2026-10-26 |
| H-031 | Korpus utama UU 40/2007 konsolidasi operator (*provenance direvisi H-045*) (anotasi UU pengubah, putusan MK); korpus lama dikeluarkan; anotasi dipisah dari teks dan menjadi tabel status; merevisi H-008, H-009 (basis), H-007, H-011 | 2026-10-26 |
| H-032 | Pembanding on-prem (stretch), tidak dicampur dengan Contributor. *Host dan model direvisi H-047: Glimmer lokal, bukan Spark Open lewat OpenRouter* *Direvisi H-060: Spark Open di Baseten ditambahkan untuk peran C* | 2026-10-26 |
| H-033 | Sembilan definisi metrik [usulan] EVAL-SPEC dikunci seperti tertulis (dari I-07); (f) Recall@K diperjelas H-048 | 2026-10-26 |
| H-034 | Seri atau selisih ≤ 1 butir: pilih setting paling sederhana, lalu pemecah §9 (dari I-20); pemecah akhir `setting_id` (H-055) | 2026-10-26 |
| H-035 | Usulan D `diubah` = disetujui; `origin` tetap `spark_disetujui`; isi asli disimpan (dari I-05) | 2026-10-26 |
| H-036 | Pembanding peran C = satu setting `fixed_size` di `config/grid.baseline`, mode dan anggaran sama (dari I-15) | 2026-10-26 |
| H-037 | Koreksi skema A lewat editor di U5, disimpan sebagai `SchemaRecord` versi baru (dari I-06); fallback bila pemicu 31 Okt aktif di H-055 | 2026-10-26 |
| H-038 | Granularitas B diputus dari angka M3.1; otomatis "hanya frontier" bila M2 belum selesai 31 Okt malam (dari H-P13) | 2026-10-26 |
| H-039 | Lima akta pendirian PT sintetis ditulis agen AI (agen pengembang) setelah 23:00 WIB, direview operator; bukan Spark; potong 2 H-017 = 5 dokumen (dari H-P02) | 2026-10-26 |
| H-040 | Blanko akta PPAT dari lampiran yang ditunjuk operator, sebagai kontrol keluarga akta; nomor peraturan dipastikan dari isi (dari I-11). *Dipotong H-056* | 2026-10-26 |
| H-041 | Identitas akta sintetis fiktif, dihindarkan dari kesamaan dengan pihak nyata, tanpa NIK, disclaimer per akta dan README (dari I-09) | 2026-10-26 |
| H-042 | Embedder `BAAI/bge-m3` revisi `5617a9f6`, dense saja, tanpa prefix, `max_seq_length` eksplisit di `config/retrieval` (dari H-P20, menggantikan H-024) | 2026-10-26 |
| H-043 | Participant Guide diperlakukan sebagai Official Rules; tanpa bentrok dengan H-003, H-018, H-029 (menutup H-P05) | 2026-10-26 |
| H-044 | Spec produk pra-acara disalin terseleksi ke repo app sebagai commit berlabel; README "Built before vs during the hackathon"; strategi, nama mesin, rujukan repo private disaring (dari I-16) | 2026-10-26 |
| H-045 | Korpus UU PT: teks UU, Perppu, putusan MK bebas hak cipta (Pasal 42); masuk dengan anotasinya, tidak dilisensikan ulang; konsolidasi tidak resmi disiapkan operator, sampai 30 Desember 2022; merevisi provenance H-031 (dari I-24, menutup I-23); hash acuan `a6b38ee5…` sejak pembekuan ulang 26 Okt malam | 2026-10-26 |
| H-046 | Format korpus = berkas beku apa adanya; pemuat memisahkan anotasi, offset atas teks bersih (`clean_sha256`, `loader_rules_version`); MK hanya Pasal 86 ayat (9); Pasal 142 `berlaku` + `note`; aturan status default; tanggal acuan butir ≥ 30 Des 2022; cakupan retrieval default lewat config; kalimat penutup rincian sah (menutup H-P19) | 2026-10-26 |
| H-047 | Muse Glimmer lokal (LM Studio, endpoint OpenAI-compatible) sebagai pembanding on-prem peran C saja: profil terbaik dan baseline H-036 dijalankan ulang; kuantisasi Q4_K_M, `reasoning_effort` `high` (dipin sebelum run), dan model ID di `config/model` dan `RunRecord`; tidak dicampur dengan Contributor; stretch; Glimmer dan embedding tidak bersamaan (VRAM); Spark Open tidak dikerjakan; klaim bonus open-weight hanya setelah konfirmasi penyelenggara (menutup H-P22, merevisi H-010 dan host H-032) *Direvisi H-060: Spark Open di Baseten juga pembanding C* | 2026-10-26 |
| H-048 | Span gold menandai semua ayat yang dibutuhkan (boleh multi-ayat); sistem memecahnya di batas ayat menjadi bagian-ayat; Recall@K = porsi bagian-ayat yang masing-masing utuh di salah satu potongan top-K (dari I-19, memperjelas H-033 f) | 2026-10-26 |
| H-049 | `held_out_ratio = 0.4` di `config/grid`, per stratum H-015, minimal tiga kontrol di held-out; kontrol ditambahkan ke held-out lebih dulu bila pembulatan kurang (dari I-14) | 2026-10-26 |
| H-050 | Mode putar ulang membaca `runs/` dan `data/`, tanpa panggilan model kecuali satu panggilan live W6 (dari I-22, merevisi kalimat replay H-020) | 2026-10-26 |
| H-051 | Live product = ekspor statis mode putar ulang (frontend + snapshot JSON, tanpa backend, key, atau panggilan model) di GitHub Pages setelah repo publik di gate M5.2; pemeriksaan isi snapshot masuk gate (menutup H-P21) | 2026-10-26 |
| H-052 | Skenario test kesembilan slice Tier 1 disusun agen dengan data sintetis sebelum kode slice, dicek pemeriksa agen independen, disetujui operator; bukan butir evaluasi; ambang verifier M2.3 diusulkan dengan alasan tertulis | 2026-10-26 |
| H-053 | W6 menerima pilihan model dari daftar `config/model` (Contributor, Glimmer lokal); U3 menampilkan pemilih dan label model, kuantisasi, effort; run Glimmer terpisah; pilihan nonaktif bila server lokal mati; di replay statis hanya hasil tersimpan (melengkapi H-047) *Direvisi H-060: daftar W6 + Spark Open Baseten* | 2026-10-26 |
| H-054 | Lima butir akta tidak dibagi tune/held-out; dilaporkan per butir sebagai uji transfer; frontier akta tanpa klaim pemilihan; tidak ada `SplitRecord` akta | 2026-10-26 |
| H-055 | Bila pemicu 31 Okt H-017 aktif, editor skema A turun ke berkas berversi dan U5 hanya menampilkan diff; pemecah seri akhir = `setting_id` terkecil leksikografis | 2026-10-26 |
| H-056 | Blanko PPAT tidak dipakai; keluarga akta hanya lima akta sintetis (menutup H-P23, merevisi H-040) | 2026-10-26 |
| H-057 | OpenRouter hanya untuk dev dan uji: profil `openrouter_dev` (model ID `meta/muse-spark-1.3-contributor`) dan `meta` (`muse-spark-1.3-contributor`) di `config/model`; `RunRecord` mencatat `provider`; run OpenRouter tidak dipakai untuk angka yang dilaporkan, run final lewat Meta Model API (H-027, H-028); tetap Responses API + `strict: true` (H-016), bila OpenRouter tidak mendukung jalur itu berhenti, tidak turun ke Chat Completions; pengecualian "tanpa key kedua" AGENTS.md hanya untuk dev. *Dikonfirmasi operator di sesi 26 Okt malam; dicatat agen di sini; operator menyalin ke log keputusan operator 27 Okt* | 2026-10-27 |
| H-058 | Nilai grid H-012 di `config/grid` v1: `fixed_size` 512/64 (satu ukuran, sekaligus baseline C H-036), anggaran 2.000 + pembanding 1.000, `packing = stop`, `held_out_ratio = 0.4`, seed 20261026, urutan sederhana H-034; 36 titik UU PT. Ditetapkan setelah butir kontrol ditulis, sebelum run apa pun | 2026-10-27 |
| H-059 | Kontrak `DATA-CONTRACTS` §10 untuk penyebut nol dan akta: (1) M1.4 A12 alt. (b): `split = null` untuk akta di `ItemMetrics`, `GridPoint`, `Frontier`; "transfer" hanya label laporan (H-054); (2) M1.5 A5 alt. N1: penyebut nol (E, Bnd, agregat Recall@K tanpa butir ber-gold) → `null`, UI "n/a"; `QualityMetrics` `number \| null`; (3) default "Dipilih" skenario M1.2 berlaku, termasuk A7b (`GridPoint.mean_token_precision` `null` bila semua butir null) dan A3 (truncate `r ≤ 0`: potongan tidak masuk, pengemasan berhenti). Skenario M1.2, M1.4, M1.5 disetujui. *Dikonfirmasi operator sesi 27 Okt (lewat orkestrator); dicatat agen di sini; operator menyalin ke log keputusan operator* | 2026-10-27 |
| H-060 | Pembanding C (stretch, M2.5) = Glimmer lokal (H-047) **dan** Spark Open di Baseten (`meta-models/muse-spark-open-1026`), masing-masing run terpisah, tidak dicampur dengan Contributor; hasil utama tetap Contributor (H-028). Hanya peran C; A, B, D, verifier, penilai tetap Contributor. VRAM bergantian tetap (H-047). Jalur Baseten: Responses API + `strict: true` lebih dulu; hanya bila tidak didukung, pengecualian H-016: Chat Completions `response_format` json_schema + validasi skema sisi klien (seperti Glimmer); hasil smoke dicatat G-33. Key `BASETEN_API_KEY` diizinkan. Klaim bonus open-weight hanya setelah run tersimpan ada (sumber verifikasi partner: Discord Baseten 27 Okt). Merevisi H-047 ("Spark Open tidak dikerjakan"), H-053 (daftar model W6), H-032 (host); menutup H-P24. *Dikonfirmasi operator sesi 27 Okt (lewat orkestrator); dicatat agen; operator menyalin ke log keputusan operator. AGENTS.md belum diperbarui (I-32)* | 2026-10-27 |

## Pending

| ID | Pertanyaan | Owner | Batas |
|---|---|---|---|
| — | (tidak ada) | | |

## Pilihan spec yang menunggu operator

Pilihan desain yang dibuat suite ini tetapi belum menjadi keputusan H ada di `docs/ISSUES.md` bagian "Menunggu operator". Bila dikunci, dicatat di log keputusan operator dulu, lalu baris baru ditambahkan di sini.

## Obsolete

Bentuk yang sudah obsolete dan **DILARANG** dihidupkan lagi tanpa revisi formal: dua lengan (H-P01), opsi C tiga lengan Self-Route, router C+ (H-P10), asisten "kutipan pasal", butir hanya tulisan tangan (H-P03), korpus lama + satu UU, Glimmer stretch (H-P04; dihidupkan terbatas lewat revisi formal H-047: pembanding C saja); sejak 26 Okt juga korpus lama (H-008, diganti H-031), status dari manifest korpus lama (H-009 basis), semua panggilan Standard (H-010 bagian model, diganti H-028), akta buatan operator (H-P02, diganti H-039), embedder E5-large (H-024, diganti H-042), Spark Open lewat OpenRouter (host H-032, diganti H-047), dan replay yang hanya membaca `runs/` (kalimat H-020, diganti H-050). Daftar lengkap ada di log keputusan operator.

## Change log

| Tanggal | Isi |
|---|---|
| 2026-10-25 | Ringkasan dibuat dari log keputusan operator |
| 2026-10-25 | H-019 sampai H-026 ditambahkan dari isu I-01, I-02, I-03, I-04, I-08, I-13, I-17, I-18 |
| 2026-10-26 | H-028 ditambahkan (Contributor untuk Model API) |
| 2026-10-26 | H-029 ditambahkan (repo publik, Apache-2.0; dari I-12) |
| 2026-10-26 | H-030 ditambahkan (SEOJK dan Pasal 42; dari I-10) |
| 2026-10-26 | H-031 ditambahkan (korpus UU PT), H-P19 pending. Baris H-008 dan H-009 di atas sudah direvisi H-031 |
| 2026-10-26 | H-032 ditambahkan (Spark Open lewat OpenRouter) |
| 2026-10-26 | H-033 ditambahkan (definisi metrik, I-07) |
| 2026-10-26 | H-034 ditambahkan (pemecah seri, I-20) |
| 2026-10-26 | H-035 ditambahkan (status diubah, I-05) |
| 2026-10-26 | H-036 ditambahkan (pembanding C, I-15) |
| 2026-10-26 | H-037 ditambahkan (editor skema, I-06) |
| 2026-10-26 | H-038 ditambahkan (granularitas B), H-P13 ditutup |
| 2026-10-26 | H-039 ditambahkan (akta sintetis), H-P02 (akta) ditutup |
| 2026-10-26 | H-040 ditambahkan (blanko PPAT, I-11) |
| 2026-10-26 | H-041 ditambahkan (identitas fiktif, I-09) |
| 2026-10-26 | H-024 dibuka ulang lewat H-P20 |
| 2026-10-26 | Catatan revisi H-007, H-011, H-017; daftar obsolete 26 Okt; selisih H-020 vs API dicatat di I-22 |
| 2026-10-26 | Participant Guide dibaca; pending baru H-P21, H-P22 |
| 2026-10-26 | H-042 ditambahkan (embedder bge-m3), H-P20 ditutup, H-024 obsolete |
| 2026-10-26 | H-043 ditambahkan (Official Rules dari Participant Guide), H-P05 ditutup |
| 2026-10-26 | H-044 ditambahkan (suite pra-acara, I-16) |
| 2026-10-26 | H-045 ditambahkan (korpus UU PT, I-24 dan I-23) |
| 2026-10-26 | H-046 ditambahkan (format korpus dan pemuat), H-P19 ditutup; hash korpus beku ulang di H-045 |
| 2026-10-26 | H-047 ditambahkan (Glimmer lokal pembanding C), H-P22 ditutup; baris H-010 dan H-032 diberi catatan revisi |
| 2026-10-26 | H-048 sampai H-051 ditambahkan (span gold multi-ayat, held-out 40%, replay `runs/` + `data/`, replay statis GitHub Pages); I-19, I-14, I-22 dan H-P21 ditutup |
| 2026-10-26 | H-052 sampai H-055 ditambahkan (skenario Tier 1 diusulkan agen, Glimmer lewat W6/U3, akta tanpa split, fallback editor dan pemecah seri `setting_id`); pending baru H-P23 (blanko PPAT) |
| 2026-10-26 | H-056 ditambahkan (blanko PPAT tidak dipakai), H-P23 ditutup |
| 2026-10-26 | Ringkasan H-001 sampai H-056 diimpor ke repo app sebagai bagian spec pra-acara, disaring (H-044) |
| 2026-10-27 | H-057 ditambahkan (OpenRouter hanya dev/uji, dari mandat operator sesi 26 Okt malam); belum ada di log keputusan operator, disalin operator 27 Okt |
| 2026-10-27 | H-058 ditambahkan (nilai grid H-012), `config/grid.toml` dibuat |
| 2026-10-27 | Pending H-P24 dibuka (kredit Baseten Spark Open diterima; Discord mengonfirmasi verifikasi partner) |
| 2026-10-27 | H-060 ditambahkan (pembanding C: Glimmer lokal dan Spark Open di Baseten), H-P24 ditutup; baris H-032, H-047, H-053 direvisi H-060 |
| 2026-10-27 | H-059 ditambahkan (kontrak §10 nullable: split akta, penyebut nol; skenario M1.2, M1.4, M1.5 disetujui; I-27 ditutup). I-25 (OpenRouter ditinggalkan, dev lewat Meta) dan I-26 (metode selisih dua titik) ditutup operator tanpa keputusan H baru; belum ada di log keputusan operator, disalin operator |
