<!-- Tujuan: terjemahan Indonesia README publik; versi Inggris otoritatif. -->
<!-- Sumber keputusan: H-002, H-004, H-005, H-006, H-007, H-013, H-014, H-016, H-017, H-018, H-028, H-029, H-031, H-032, H-039, H-041, H-043, H-044, H-045, H-047, H-048, H-051, H-053, H-054, H-060, H-078, H-086, H-089, H-090, H-091, H-093, H-097, H-098, H-100, H-101, H-102, H-104, H-110, H-111, H-112, H-113, H-114. -->

# LexRAGLab

English: [README.md](../README.md). Versi bahasa Inggris yang otoritatif; bila berbeda, README Inggris yang berlaku. Angka memakai notasi Inggris (koma pemisah ribuan, titik desimal), sama dengan README Inggris.

Temukan setelan chunking dan retrieval yang memberi LLM klausul yang tepat dari dokumen hukum Indonesia, berdasarkan pengukuran, bukan tebakan.

LexRAGLab adalah lab evaluasi yang mencari setelan chunking dan retrieval untuk satu keluarga dokumen hukum Indonesia; ini bukan aplikasi RAG dan bukan chatbot.

Dibuat untuk Meta Global AI Developer Hackathon (track Indie, tema "Build for Your World") dengan Muse Spark (`muse-spark-1.3-contributor` lewat Meta Model API).

- Video demo: TODO(operator)
- Live replay: TODO(operator): GitHub Pages link, added after the repository is public

> Demo riset. Bukan nasihat hukum.

## Sekilas

- **Masalah:** tim legal RAG memilih ukuran chunk dengan menebak, dan tidak ada benchmark publik untuk teks hukum Indonesia ([Mengapa](#mengapa)).
- **Dibangun selama hackathon:** seluruh kode ditulis 26 Okt sampai 4 Nov 2026; sebelum acara hanya ada dokumen perencanaan berlabel dan teks peraturan, tanpa kode ([Dibangun sebelum vs selama hackathon](#dibangun-sebelum-vs-selama-hackathon)).
- **Model Meta yang dipakai:** Muse Spark (`muse-spark-1.3-contributor`) menghasilkan hasil utama dalam empat peran; dua model open-weight Meta menjadi comparator; tokenizer Muse Spark Open menghitung token; Muse Voice Transcribe hanya memeriksa narasi video. Pencarian grid dan verifier sitasi tidak memakai LLM ([Model Meta](#model-meta-dan-perannya)).
- **Bukti:** setiap angka berasal dari run tersimpan ([Hasil](#hasil), [RESULTS.md](RESULTS.md) (bahasa Inggris)).
- **Cara menjalankan:** replay tidak butuh API key ([Cara menjalankan](#cara-menjalankan)).
- **Batasan:** n kecil, hitungan mentah, tanpa klaim signifikansi ([Batasan](#batasan), [LIMITS.md](LIMITS.md) (bahasa Inggris)).

## Tema: Build for Your World

Tema hackathon adalah "Bring Meta's models into your domain. Solve a problem you know firsthand, free up time and mental space, and make something possible that wasn't before." (Bawa model Meta ke domain Anda. Selesaikan masalah yang Anda kenal langsung, bebaskan waktu dan ruang pikiran, dan wujudkan sesuatu yang sebelumnya tidak mungkin.) Domain di sini adalah hukum Indonesia.

- **Masalah yang dikenal langsung.** Operator (satu-satunya pengembang proyek) mengerjakan pekerjaan hukum agentic (pendapat hukum, legal due diligence, penyusunan kontrak) yang mengharuskan agen merujuk kumpulan peraturan yang tidak muat dalam satu context window (lihat [Mengapa](#mengapa)).
- **Waktu dan ruang pikiran.** LexRAGLab bertujuan mengganti tebakan ukuran chunk dengan pilihan yang terukur, dan menjaga konteks yang dibutuhkan agen tetap kecil. Ini hipotesis yang diuji evaluasi, bukan penghematan yang sudah terukur.
- **Sesuatu yang sebelumnya tidak mungkin.** Tidak ada benchmark publik yang standar untuk RAG hukum Indonesia, sehingga setelan retrieval untuk teks hukum Indonesia tidak bisa dipilih lewat pengukuran. Muse Spark membaca keluarga dokumen baru, mengusulkan strukturnya dan butir evaluasinya untuk ditinjau operator, dan LexRAGLab menilai setiap setelan terhadap gold span yang telah disetujui.

## Mengapa

Tim legal RAG biasanya memilih ukuran chunk dengan menebak. Pada peraturan Indonesia, tebakan bisa memotong sebuah *ayat* (paragraf dalam pasal) menjadi dua, lalu model mengutip separuh aturan. Tidak ada benchmark publik yang standar untuk RAG hukum Indonesia. LexRAGLab menjadikan chunking keputusan desain yang terukur.

Motivasinya berasal dari praktik: pekerjaan hukum agentic harus merujuk undang-undang dan peraturan pelaksanaannya yang tidak muat dalam satu context window agen, sehingga setelan yang menjaga konteks yang dibutuhkan tetap kecil menjadi penting.

Angka di bawah adalah hasil pengukuran operator atas pekerjaan sebelumnya (tidak disertakan di repositori ini). Angka itu bukan keluaran aplikasi ini, dan tidak ada hasil LexRAGLab yang diturunkan dari angka tersebut.

- Satu undang-undang yang dirujuk untuk satu pendapat hukum berukuran sekitar 320 ribu token, dengan sendirinya sudah melampaui jendela 200 ribu token.
- Dari teks peraturan itu, hanya sekitar 10% yang benar-benar dipakai.
- Seluruh materi per pekerjaan, komposisinya tidak dirinci menjadi peraturan versus dokumen lain: sekitar 1.2 juta token untuk pendapat hukum satu transaksi dan sekitar 5.8 juta untuk satu berkas due diligence lengkap (1.2 sampai 5.8 kali jendela 1 juta token); sekitar 2.2 juta untuk penyusunan kontrak, atau sekitar 2.8 juta bila pustaka klausul disertakan.

Pengukuran operator atas penggunaan agen (sekunder) ada di [DATA.md](DATA.md#operator-measurements-background) (bahasa Inggris).

## Apa ini

Untuk satu keluarga dokumen dengan pola homogen, LexRAGLab menelusuri grid setelan (chunker, ukuran chunk dan overlap, retrieval dense / BM25 / hybrid, context header menyala atau mati) dan melaporkan setelan mana yang memberi bukti emas (gold evidence) terbanyak pada token budget yang tetap.

Keluarannya adalah **versioned setting profile** yang bisa diekspor dan dipakai ulang di pipeline RAG Anda. Profil Hukum Perseroan yang sudah diekspor ada di [`profiles/uupt/`](../profiles/uupt/); memuatnya kembali membangun ulang set chunk yang sama (dicek dengan hash) dan ditolak bila hash korpus berbeda. Proyek ini berhenti pada penemuan setelan; ini bukan produk RAG.

## Model Meta dan perannya

| Model | Akses / host | Peran | Status | Run tersimpan |
|---|---|---|---|---|
| Muse Spark `muse-spark-1.3-contributor` | Meta Model API, Responses API dengan strict structured output, mode Contributor (lihat [Data dan lisensi](#data-dan-lisensi)) | A, B, C, D | Hasil utama (reasoning effort `low`); sapuan effort (`medium`, `high`, `xhigh`) disimpan terpisah | `runs/spark/records/`, `runs/schemas/<family>/` (`v1.json` = usulan Spark, `v2.json` = koreksi operator), `runs/headers/`, `runs/grid/`, `runs/answers/`, `runs/proposals/` |
| Muse Spark Open `meta-models/muse-spark-open-1026` | endpoint hosted di Baseten, Responses API, strict structured output | A, B, C | Comparator, run terpisah, tidak pernah dicampur dengan hasil utama | `runs/schemas/<family>/compare/`, `runs/headers_compare/`, `runs/grid_compare/`, `runs/compare_report/c/` |
| Tokenizer Muse Spark Open (`meta-models/Muse-Spark-Open-816B-A42B`, revisi dipin di `config/tokenizer.toml`) | lokal, dibaca dari cache Hugging Face pengguna, tidak disertakan | tanpa peran: menghitung token untuk setiap setelan dan token budget (tanpa panggilan model) | Dipakai untuk semua penghitungan token ("Built with Muse Spark Open"; fallback `o200k_base`) | `config/tokenizer.toml` |
| Muse Glimmer `meta/muse-glimmer` (Q4_K_M) | lokal di mesin operator, endpoint loopback kompatibel OpenAI, validasi skema di sisi klien; bobot tidak disertakan; Apache-2.0 menurut dokumen Meta (model card belum diverifikasi, lihat `NOTICE`) | A, B, C | Comparator, run terpisah | direktori comparator yang sama |
| Muse Voice Transcribe `muse-voice-transcribe-1.0` | endpoint transkripsi Meta Model API (model ID dipin di `config/voice_qa.toml`) | tidak ada di produk: memeriksa narasi video demo terhadap skripnya | Hanya alat video; bukan bagian produk dan tidak memengaruhi hasil apa pun | `runs/voice_qa/` |

| Peran | Yang dikerjakan model |
|---|---|
| A. Structure induction | Membaca dokumen contoh dari keluarga baru dan mengusulkan skema hierarki datar yang menggerakkan chunker deterministik. Operator mengoreksinya; kedua versi disimpan |
| B. Contextual chunking | Menulis context header untuk setiap chunk dengan dokumen sumber di-cache. Header menyala/mati adalah sumbu grid, dan token header dihitung terhadap budget |
| C. End-to-end check | Menjawab sebuah butir dari profil terbaik dan dari profil baseline, dengan sitasi. Verifier deterministik (bukan LLM) memeriksa bahwa setiap sitasi ada dan setia pada sumber |
| D. Item proposals | Mengusulkan pasangan (query, gold span) dalam mode literal dan paraphrase. Operator meninjau setiap usulan; hanya butir yang disetujui dipakai |

Peran D hanya memakai model Contributor. Pencarian grid sendiri tidak memakai LLM, dan verifier sitasi di peran C bersifat deterministik, bukan model.

Comparator: dua model open-weight menjalankan ulang peran A, B, dan C sebagai run terpisah yang berlabel, bisa dipilih di panel bukti untuk peran C. Untuk peran C keduanya hanya menjawab enam butir (tiga butir demo dan tiga butir must-refuse (wajib menolak) Hukum Perseroan), dan tidak ada klaim umum tentang kualitas kedua model itu. Rincian: [LIMITS.md](LIMITS.md) (bahasa Inggris).

## Dibangun sebelum vs selama hackathon

Hackathon dimulai pada 26 Okt 2026, 23:00 WIB. Commit pertama di repositori ini bertanggal 26 Okt 2026 23:23 WIB, setelah kickoff. Seluruh kode ditulis selama hackathon (26 Okt sampai 4 Nov 2026); tidak ada prototipe pra-acara yang disertakan atau disalin.

Hanya dua hal di repositori ini yang disiapkan sebelum kickoff (didraf 25-26 Okt, di-commit sesudahnya, masing-masing dalam commit berlabel terpisah):

| Dibangun sebelum kickoff (25-26 Okt 2026) | Dibangun selama hackathon |
|---|---|
| Spesifikasi perencanaan di [`docs/`](./), diimpor dalam satu commit berlabel (`docs: import pre-event planning`). Hanya perencanaan: tanpa kode | Seluruh kode, konfigurasi, prompt, butir evaluasi, akta sintetis, run tersimpan, profil, dan live replay |
| Berkas Hukum Perseroan: konsolidasi tidak resmi UU 40/2007, terkonsolidasi per 30 Desember 2022, disiapkan operator dari teks peraturan dan putusan Mahkamah Konstitusi; di-commit terpisah sebagai materi pra-acara (`data: add UU 40/2007 consolidated text`) | Setiap perubahan pada spesifikasi setelah commit impor |

Tema visual UI (token warna, tipografi IBM Plex, pola komponen) mengikuti mockup desain pra-acara milik operator, yang tidak ada di repositori ini; markup-nya tidak disalin dan layout mengikuti `docs/UI-SPEC.md`. Kelima akta sintetis ditulis selama hackathon oleh agen AI (agen pengembangan) dan ditinjau operator.

## Definisi "terbaik"

- Bukti emas (gold evidence) disimpan sebagai **character span** pada dokumen sumber, sehingga satu set butir bisa menilai chunker mana pun. Sebuah gold span menandai setiap *ayat* yang dibutuhkan untuk jawaban; span itu dipecah pada batas *ayat* sebelum Recall@K dihitung.
- Setelan dibandingkan pada **token budget yang tetap**, bukan K yang tetap. Token dihitung dengan satu tokenizer lokal untuk setiap setelan.
- Metrik utama: **span recall** dan **token precision**. Dilaporkan juga: MRR, Recall@K, entity preservation, boundary coherence.
- Hasil ditampilkan sebagai **Pareto frontier** (recall vs token: setelan yang tidak dikalahkan pada kedua sumbu). Setelan dipilih pada split **tune** dan dilaporkan pada split **held-out**, per butir, dengan hitungan mentah dan tanpa klaim signifikansi.
- Butir **must-refuse** (wajib menolak) adalah butir yang jawabannya tidak ada di sumber; keluaran yang benar adalah menolak.

## Hasil

**Hukum Perseroan.** Setelan terpilih (dense retrieval, header off, token budget 2,000) beserta angka held-out-nya ada di profil terekspor `profiles/uupt/d7a9dd244260e256789d10d02bd50b1f125bcd1b8a088f2a8058c2f222c58ebf.json` (field `held_out`) dan di layar laporan aplikasi.

**Keluarga dokumen.**

| Keluarga | Cakupan |
|---|---|
| Hukum Perseroan Indonesia (UU 40/2007), konsolidasi tidak resmi per 30 Desember 2022 | Penuh: grid dan peran A, B, C, D; setelan dipilih pada tune, dilaporkan pada held-out |
| Akta notaris | Transfer: lima akta pendirian sintetis; peran A pada keluarga tanpa parser yang ada; uji transfer, tanpa pemilihan profil |
| Kebijakan internal | Disebut sebagai keluarga berikutnya; tidak ada dokumen yang disertakan |

**Butir evaluasi.** Hukum Perseroan 23 butir (split tune / held-out 13 / 10); akta notaris (sintetis) 84 butir (69 dengan gold span, 15 must-refuse), tanpa split. Rincian menurut asal dan mode: [RESULTS.md](RESULTS.md) (bahasa Inggris).

**Uji transfer akta** (69 butir gold, token budget 2,000; setelan Hukum Perseroan diterapkan pada akta, tidak ada yang dipilih pada akta):

- skema struktur akta v2, dense, header off: 69 dari 69 butir tercakup penuh, mean span recall 1.000.
- fixed-size 512 / 64, dense, header off: 64 dari 69.
- unstructured (satu chunk per akta): 0 dari 69.

Ini uji transfer pada lima dokumen sintetis, bukan hasil utama dan bukan klaim umum. Tabel lengkap, catatan (setelan transfer, unstructured, Recall@K tidak sebanding, n kecil), dan sumber: [RESULTS.md](RESULTS.md) (bahasa Inggris).

## Cara menjalankan

Prasyarat: Python 3.12 dengan [uv](https://docs.astral.sh/uv/), Node.js dengan npm. Salin `.env.example` ke `.env` dan isi nilainya secara lokal; `.env` di-git-ignore dan tidak pernah di-commit. Key hanya dibutuhkan untuk run live: `MUSE_API_KEY` / `MUSE_BASE_URL` untuk Contributor, `BASETEN_*` hanya untuk comparator. Replay tidak butuh key.

```bash
uv sync                                   # backend dependencies
uv run python -m backend.api              # backend, bound to 127.0.0.1:8000 only
cd frontend && npm install && npm run dev # frontend dev server on 127.0.0.1:5173, proxies /api to the backend
```

Mode replay lokal: backend menyajikan setiap layar dari run tersimpan (`runs/`) serta data dokumen dan butir (`data/`) tanpa memanggil Model API.

Ekspor replay statis (tanpa backend, tanpa panggilan model):

```bash
uv run python -m backend.replay.export --out dist-static   # writes dist-static/data from stored runs
cd frontend && npm run build:static                        # builds the static UI into dist-static/
uv run python -m backend.replay.export --check dist-static # scan the snapshot for keys, local paths, hosts
uv run python -m http.server -d dist-static -b 127.0.0.1 8080
```

`dist-static/` adalah keluaran build dan tidak ada di repositori. Live replay yang dipublikasikan (tautan di atas) adalah ekspor statis ini: tanpa backend, tanpa API key, dan tanpa panggilan model.

Test:

```bash
uv run pytest
cd frontend && npm test
```

## Peta repositori

```text
backend:   Python 3.12 + FastAPI
frontend:  React + TypeScript + Vite
model:     muse-spark-1.3-contributor, Responses API (model ID in config/model.toml)
storage:   files only (no database, no vector database)
```

| Direktori | Isi |
|---|---|
| `backend/` | Backend Python: grid search, scoring, klien Model API, ekspor replay, test |
| `frontend/` | UI React + TypeScript |
| `config/` | Setelan berversi (`model.toml`, `tokenizer.toml`, `grid.toml`, `budget.toml`, `sweep.toml`, `voice_qa.toml`, dan lainnya) |
| `data/` | Korpus, akta sintetis, butir evaluasi |
| `runs/` | Run tersimpan; setiap angka yang dilaporkan berasal dari sini |
| `profiles/` | Setting profile yang diekspor |
| `prompts/` | Prompt per peran (`a` sampai `d`) |
| `docs/` | Spesifikasi, keputusan, dan dokumen rincian |
| `video/` | Motion graphics video demo; bukan bagian aplikasi |
| `licenses/` | Teks lisensi font |

## Untuk agen AI dan kontributor

- Baca [`AGENTS.md`](../AGENTS.md) lebih dulu (aturan untuk agen, ditulis dalam bahasa Indonesia). Urutan bacanya: `docs/CONTEXT.md`, `docs/DECISIONS.md`, `docs/ISSUES.md`, `docs/MILESTONES.md`, spec slice yang dikerjakan (terdaftar di bagian "Spec per slice" pada `docs/MILESTONES.md`), `docs/CONVENTIONS.md`, `docs/GOTCHAS.md`; `docs/PRD.md` dan `docs/ARCHITECTURE.md` sebagai referensi.
- Aturan inti dari `AGENTS.md`: agen tidak pernah menulis atau menyetujui butir evaluasi; angka hanya berasal dari run tersimpan dan tidak pernah dikarang; tidak ada model selain `muse-spark-1.3-contributor` kecuali pengecualian yang tercantum di sana (comparator dan pemeriksa video); tanpa database, vector database, LangChain, parser PDF, atau reranker; API key hanya ada di `.env` lokal.
- Dokumen spesifikasi ditulis dalam bahasa Indonesia. ID seperti `H-028` merujuk ke entri di log keputusan operator, yang diringkas di `docs/DECISIONS.md`. Kode keluarga: `uupt` = Hukum Perseroan, `akta` = akta notaris.
- Profil model (utama dan comparator) ada di `config/model.toml`, yang di `AGENTS.md` disebut `config/model`.

## Batasan

- Set butir kecil; hasil per butir dengan hitungan mentah, tanpa klaim signifikansi.
- Konsolidasi hanya mencakup satu undang-undang, per 30 Desember 2022; perubahan sesudahnya tidak tercermin.
- Comparator adalah run terpisah; tidak ada klaim kualitas tentang keduanya. Hasil utama tetap pada `muse-spark-1.3-contributor` dengan reasoning effort `low`.
- Hasil akta bertumpu pada lima dokumen sintetis; tidak ada butir kontrol yang ditulis operator dan tidak ada split held-out untuk akta.
- Hitungan token memakai tokenizer lokal yang dikalibrasi sekali terhadap endpoint token-count API; token yang ditagih bisa berbeda.
- Pemeriksaan sitasi "berlaku pada tanggal" (apakah ketentuan yang dikutip berlaku pada tanggal tertentu) adalah stretch goal dan mungkin tidak ada. Teks hukum Indonesia ditampilkan dalam bahasa Indonesia, dengan gloss singkat bahasa Inggris bila perlu.
- Biaya run (hasil utama): 561,741 micro-USD (ditampilkan sebagai $0.561741), angka yang sama dengan header aplikasi (label di UI: "Run cost (main results)").

Belanja eksperimen per pool (comparator, sapuan effort) dilaporkan terpisah di [LIMITS.md](LIMITS.md) (bahasa Inggris), bersama rincian comparator dan sapuan effort.

## Data dan lisensi

- Teks Hukum Perseroan adalah konsolidasi tidak resmi UU 40/2007 (per 30 Desember 2022), disiapkan operator dari teks peraturan publik dan putusan Mahkamah Konstitusi. Akta bersifat sintetis dan fiktif; tidak ada akta asli, data klien, atau dokumen internal yang disertakan.
- Panggilan Model API memakai `muse-spark-1.3-contributor` (mode Contributor: Meta boleh memakai konten untuk melatih model berikutnya). Ini dapat diterima di sini karena setiap dokumen publik atau sintetis. Untuk keluarga dokumen rahasia, setel model ID Standard di `config/model.toml`.
- Lisensi: Apache-2.0 untuk semua yang dibuat proyek ini (lihat `LICENSE`); atribusi pihak ketiga ada di `NOTICE`.

**Built with Muse Spark Open.** Tokenizer Muse Spark Open menghitung token secara lokal (Muse Model License mensyaratkan notice ini), dan model Muse Spark Open juga menjadi comparator.

Sumber korpus, rincian lisensi lengkap (font, UU 28/2014 Pasal 42, lisensi tokenizer dan Glimmer, lisensi dependensi): [DATA.md](DATA.md) (bahasa Inggris).

## Disclaimer

Demo riset. Bukan nasihat hukum. Jangan mengandalkan keluaran apa pun untuk keputusan hukum.

## Dokumentasi

Dokumen spesifikasi ditulis dalam bahasa Indonesia. Spesifikasi ada di [`docs/`](./): [PRD](PRD.md), [UI-SPEC](UI-SPEC.md), [ARCHITECTURE](ARCHITECTURE.md), [DATA-CONTRACTS](DATA-CONTRACTS.md), [API](API.md), [EVAL-SPEC](EVAL-SPEC.md), [SPARK-ROLES](SPARK-ROLES.md), [SECURITY-COMPLIANCE](SECURITY-COMPLIANCE.md), [MILESTONES](MILESTONES.md), [DECISIONS](DECISIONS.md), [VIDEO](VIDEO.md). Dokumen rincian dalam bahasa Inggris: [LIMITS](LIMITS.md), [RESULTS](RESULTS.md), [DATA](DATA.md). README bahasa Inggris: [README.md](../README.md).
