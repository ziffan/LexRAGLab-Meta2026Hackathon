# SECURITY-COMPLIANCE — threat model, kepatuhan, dan gate pra-submit

Tujuan: menetapkan ancaman yang relevan, kewajiban hukum yang menyentuh data dan lisensi, serta daftar periksa yang harus lulus sebelum submit.
Sumber keputusan: H-003, H-007, H-013, H-016, H-028, H-029, H-030, H-031, H-039, H-040, H-041, H-043, H-044, H-045, H-047, H-051, H-056, H-057, H-060, H-096, H-097, H-100, H-113.

Ruang lingkup: aplikasi lokal satu operator, repo publik saat submit, tanpa layanan yang di-deploy. Penilaian hukum yang terbuka dicatat di `docs/ISSUES.md` dan diputus operator.

## 1. Aset

| Aset | Kenapa penting |
|---|---|
| API key Meta Model API | Kredit terbatas ($150, Participant Guide); bocor = kredit terkuras |
| API key Baseten (H-060) | Kredit Baseten operator terbatas; bocor = kredit terkuras |
| Teks korpus dan akta sintetis | Masuk submission dan terlisensi luas ke Meta |
| Butir, tabel status, koreksi skema | Kunci jawaban; integritasnya menentukan "optimal" |
| Hasil run tersimpan | Dasar angka di layar, README, dan video |

## 2. Threat model ringkas

| # | Ancaman | Vektor | Dampak | Mitigasi | Bukti / slice |
|---|---|---|---|---|---|
| T1 | Secret API bocor | Key di kode, log, `RunRecord`, screenshot, rekaman terminal | Kredit habis, penyalahgunaan | Key hanya di `.env` lokal; `.env` di `.gitignore`; `.env.example` tanpa nilai; key tidak pernah dicetak; galat tanpa header request | M0.1: grep key di repo = 0. M5.2: secret scan |
| T2 | Kebocoran ke repo publik atau situs statis | Commit berkas lokal (`.env`, cache berisi header, catatan pribadi), path lokal operator, histori git, isi snapshot ekspor statis (H-051) | Secret atau data pribadi permanen di histori atau di GitHub Pages | Secret scan atas seluruh histori sebelum repo dibuka; `runs/` hanya berisi keluaran tanpa header HTTP; snapshot statis diperiksa tanpa key dan tanpa path lokal sebelum dipasang; tinjau `git log` sebelum publik | M5.1, M5.2 |
| T3 | Contributor mode di Muse Code, atau isi non-publik terkirim ke model Contributor | Muse Code memakai Contributor secara default dan agennya membaca isi mesin; dokumen rahasia ikut terkirim lewat Model API | Isi di luar korpus publik atau sintetis ikut bahan latih Meta | Model API memakai `muse-spark-1.3-contributor` hanya untuk korpus publik atau sintetis (H-028); tidak ada akta asli atau dokumen internal di repo (H-007); Muse Code disetel Standard | M0: model ID di `config/model` dan setelan akun Muse Code dicatat |
| T4 | Data pribadi di akta | Akta asli, akta "dianonimkan", identitas yang mirip orang nyata, NIK | Pelanggaran UU 27/2022 dan rahasia jabatan notaris | Hanya akta sintetis yang ditulis agen dari brief operator, identitas fiktif tanpa kesamaan dengan pihak nyata, tanpa NIK, dengan disclaimer (H-007, H-039, H-041). Operator memeriksa setiap berkas akta | M4.1 |
| T5 | Injeksi teks korpus ke prompt | Teks dokumen atau akta memuat kalimat bergaya perintah; keluaran D/B memuat instruksi | Keluaran Spark menyimpang; usulan butir tercemar | Teks korpus di blok data yang ditandai dan dinyatakan bukan instruksi (`docs/SPARK-ROLES.md` §1); keluaran hanya lewat JSON Schema strict; validasi semantik; tanpa tool calling; operator memeriksa semua usulan D | M2.1, M3.1, M3.3 |
| T6 | Biaya runaway | Loop retry, B per ayat tanpa ukur, cache tidak kena, batch paralel | Kredit habis, peran inti terpotong | Cost guard per peran dan total (`config/budget`); proyeksi sebelum batch; ukur satu dokumen dulu (M3.1, H-038); cache per hash; panggilan berurutan; retry terbatas | M0.1, M3.1 |
| T7 | Integritas kunci jawaban | Agen menulis butir, mengubah tabel status, atau skema | "Optimal" palsu | Agen dilarang menulis butir, tabel status, dan koreksi skema (`AGENTS.md`); transisi usulan satu jalur; versi tidak ditimpa | M2.1, M3.3 |
| T8 | Backend atau server model lokal terbuka di jaringan | FastAPI atau server LM Studio Glimmer (H-047) listen di semua antarmuka tanpa auth | Pihak lain memicu panggilan Spark atau memakai model lokal | Backend dan endpoint Glimmer di `127.0.0.1` saja (H-013 tanpa auth berlaku karena lokal) | M0.1, M2.5 |
| T9 | Supply chain | Paket salah nama, paket tidak aktif, tokenizer dari sumber tak resmi | Kode jahat di mesin operator | Versi dipin di M0; paket diverifikasi nama dan penerbitnya; tokenizer dari HF resmi (H-014) | M0 |

## 3. Kepatuhan Indonesia dan lisensi

| Rezim | Relevansi | Sikap proyek | Terbuka |
|---|---|---|---|
| UU 27/2022 Pelindungan Data Pribadi | Akta memuat data pribadi | Tidak ada data pribadi nyata di repo mana pun. Akta hanya sintetis (H-007) | — (H-041) |
| UU 2/2014 Jabatan Notaris (rahasia jabatan) | Akta asli terikat rahasia jabatan | Akta asli dan akta asli yang dianonimkan tidak dipakai (H-007). Kerangka akta sintetis mengikuti Pasal 38 UU 2/2014 (H-039) | — |
| UU 28/2014 Hak Cipta, Pasal 42 | Teks peraturan perundang-undangan tidak dilindungi hak cipta (UU 28/2014 Pasal 42) | Korpus UU 40/2007, konsolidasi tidak resmi yang disiapkan operator sampai 30 Desember 2022, dipakai sebagai data publik beserta anotasinya, tidak dilisensikan ulang, dengan daftar sumber perubahan dan pernyataan konsolidasi tidak resmi (H-031, H-045) | — (SEOJK termasuk Pasal 42 menurut penilaian operator, H-030) |
| Template akta pihak ketiga | Blog notaris, template berbayar, buku, blanko PPAT | Tidak dipakai (blanko PPAT dipotong H-056) | — |
| Lisensi submit ke Meta (waiver) | Lisensi non-eksklusif, perpetual, irrevocable, worldwide, royalty-free atas submission, untuk tujuan apa pun | Hanya yang boleh dilisensikan masuk repo. Kode prototipe pra-acara tidak masuk (H-003). Akta asli dan dokumen internal tidak masuk (H-007) | Lisensi OSS: Apache-2.0, repo publik (H-029); tanpa bentrok dengan Participant Guide (H-043) |
| Lisensi dependensi dan tokenizer | Tokenizer Muse Spark Open memakai lisensi Muse, bukan Apache (kartu model HF). Muse Glimmer open-weight Apache-2.0 (H-047) | Tokenizer dan bobot Glimmer tidak di-commit ke repo; diunduh pengguna dari sumber resmi. Atribusi dan sitasi Glimmer mengikuti kartu model | — |

Tidak ada pemrosesan data pribadi nyata, jadi inventaris data pribadi tidak diperlukan. Bila itu berubah, proyek berhenti dan keputusan direvisi.

## 4. Gate pra-submit (M5.2)

Semua butir harus tercentang dan buktinya disimpan di repo sebelum repo dibuka dan form dikirim.

**Rules dan isi**
- [ ] Syarat Official Rules (repo, video, bahasa, karya pra-acara) dipenuhi satu per satu, dengan kutipan klausul Participant Guide (H-043).
- [ ] Commit pertama repo setelah 26 Okt 2026 23:00 WIB; tidak ada kode prototipe pra-acara yang disalin (H-003).
- [ ] README menyebut jumlah butir sebenarnya beserta asalnya, model, dan batas (n kecil, tanpa klaim signifikansi).
- [ ] Setiap angka di README sama dengan layar dan video.

**Secret dan kebocoran**
- [ ] Secret scan atas seluruh histori git bersih; hasilnya disimpan.
- [ ] Rewrite histori H-096 (email pribadi di metadata commit, path lokal) hanya dengan izin eksplisit operator; verifikasi pasca-rewrite bersih.
- [ ] `.env` tidak pernah ter-commit; `.env.example` tanpa nilai.
- [ ] Tidak ada path lokal operator, catatan pribadi, atau header HTTP di `runs/`.
- [ ] Rekaman video tidak menampilkan `.env`, key, atau terminal selain terminal putar ulang.

**Data**
- [ ] Tidak ada akta asli, dokumen internal, atau data klien.
- [ ] Setiap berkas akta sintetis diperiksa operator: identitas fiktif, tanpa NIK.
- [ ] Daftar sumber korpus UU PT (UU pengubah, putusan MK) dan pernyataan konsolidasi tidak resmi tercantum (H-031).
- [ ] Disclaimer identitas fiktif di setiap akta dan README (H-041).
- [ ] Tidak ada key kedua selain `BASETEN_API_KEY` (H-060, H-100; hanya di `.env` lokal, ikut secret scan); pembanding Glimmer berjalan di `127.0.0.1` tanpa key (H-047).
- [ ] Isi snapshot ekspor statis (H-051) diperiksa: tanpa key, tanpa path lokal, tanpa header HTTP; situs dipasang di GitHub Pages hanya setelah repo publik.

**Model dan biaya**
- [ ] Model ID `muse-spark-1.3-contributor` di `config/model` dan di semua `RunRecord` kecuali run pembanding Glimmer H-047 dan Spark Open Baseten H-060/H-100 (yang mencatat model ID, `provider`, kuantisasi, dan `reasoning_effort`); Muse Code, kalau dipakai, di mode Standard.
- [ ] Total biaya dari `RunRecord` tercatat per pool (utama, Baseten H-101, sapuan H-102, pemeriksa VO H-113; H-104 butir 3) dan di dalam kredit masing-masing.

**Penutup**
- [ ] Disclaimer "Research demo. Not legal advice." tampil di app, README, dan video.
- [x] `LICENSE` Apache-2.0 terpasang (teks resmi, disalin verbatim dari paket terpasang; sha256 `c71d239d…0ab4` setelah normalisasi LF) dan `NOTICE` dengan atribusi pihak ketiga; font IBM Plex OFL 1.1 di `licenses/`; README memisahkan lisensi kode dari teks korpus (H-029, H-097). Repo publik tetap izin terpisah.
- [ ] README memuat disclosure: Contributor (H-028), konsolidasi UU PT tidak resmi yang disiapkan sebelum acara sampai 30 Desember 2022 (H-031, H-045), akta ditulis agen AI dan direview operator (H-039), bagian "Built before vs during the hackathon" (H-044), atribusi "Built with Muse Spark Open" bila tokenizer dipakai (H-014), dan bila pembanding Glimmer dipakai: open-weight yang berjalan di mesin operator, bukan bobot Spark, dengan atribusi kartu model (H-047).
- [ ] Klaim bonus open-weight hanya tercantum bila cara verifikasi "own hardware" sudah dikonfirmasi penyelenggara (H-047).
- [ ] README memuat tautan replay statis dan menyebut bahwa versi web adalah replay (H-051).

### Lisensi dependensi runtime frontend (bundel statis; H-097)

Dihitung dari `frontend/package-lock.json`: penutup dependensi produksi `frontend/package.json` (44 paket; `@types/*` hanya tipe, tidak masuk bundel). Lisensi dibaca dari `node_modules/<pkg>/package.json`. **Tidak ada paket non-permissive** (GPL/LGPL/MPL/CC-BY-SA); tidak ada bentrok dengan Apache-2.0.

| Lisensi | Paket |
|---|---|
| MIT | react 19.3.0, react-dom 19.3.0, scheduler, recharts 3.10.1, @reduxjs/toolkit, react-redux, redux, redux-thunk, reselect, immer, clsx, decimal.js-light, es-toolkit, eventemitter3, tiny-invariant, use-sync-external-store, @standard-schema/spec, @standard-schema/utils, @types/d3-*, @types/use-sync-external-store |
| ISC | d3-array, d3-color, d3-format, d3-interpolate, d3-path, d3-scale, d3-shape, d3-time, d3-time-format, d3-timer, internmap |
| BSD-3-Clause | d3-ease (salin hak cipta dan disclaimer wajib ikut paket) |
| MIT AND ISC AND BSD-3-Clause | victory-vendor 37.4.1 |
| OFL-1.1 (font, bukan kode) | @fontsource/ibm-plex-sans, -serif, -mono 5.3.0; teks di `licenses/` |

Dependensi Python (`uv.lock`) tidak dibundel ke situs statis dan tidak termasuk tabel ini.
