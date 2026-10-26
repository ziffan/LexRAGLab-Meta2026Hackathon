# VIDEO — rencana video demo

Tujuan: storyboard, aturan isi, daftar run wajib per adegan, jadwal produksi, dan gate unggah untuk video demo.
Sumber keputusan: H-006, H-011, H-017, H-018, H-021, H-028, H-029, H-031, H-039, H-041, H-043, H-045, H-047, H-050, H-053, H-054.

Kalau Official Rules menetapkan durasi atau format lain, rules yang menang, dan dokumen ini disesuaikan. Komponen layar per adegan: `docs/UI-SPEC.md` §7.

## Syarat video (panduan peserta 26 Okt)

| Hal | Asumsi | Dasar |
|---|---|---|
| Durasi | Tiga menit, target 2:50 | Panduan peserta 26 Okt: "three minute demo video" |
| Platform | YouTube unlisted, cadangan Loom; tautan harus bisa diakses | Panduan: "your video link is accessible"; platform tidak ditentukan |
| Bahasa | Narasi Inggris, UI Inggris, teks hukum Indonesia dengan gloss | H-018 |
| Ringkasan tertulis | 100–200 kata, bahasa Inggris | Asumsi; field form belum terlihat |
| Repo | Publik, Apache-2.0 | Panduan: "Repositories must be public"; H-029 |
| Isi | Hanya fitur yang dibangun selama acara; yang dibuat selama acara harus bisa diidentifikasi ("Judges must be able to clearly identify what was created during the Hackathon") | Panduan, aturan "Demo requirements"; gagal menandai = diskualifikasi |

4 November disisihkan untuk video, dan kode dibekukan 3 November malam.

## Pesan yang harus sampai

Satu kalimat: **"Muse Spark reads a new family of legal documents and finds the chunking and retrieval setting that feeds an LLM the right clauses, measured, not guessed."**

Penonton harus pulang dengan tiga hal:
1. Setting chunking itu bisa diukur, dan hasilnya terlihat sebagai frontier pada anggaran token yang sama.
2. Spark mengerjakan bagian yang tadinya butuh manusia: A, B, C, D.
3. Polanya berpindah ke keluarga dokumen lain.

## Storyboard

Durasi per adegan adalah target. Angka di narasi ditulis `{…}` dan diisi dari layar saat rekaman. Tidak ada angka yang ditulis sebelum run-nya ada.

| # | Waktu | Layar | Beat narasi (Inggris, ringkas) | Peran | Data yang harus siap |
|---|---|---|---|---|---|
| 0 | 0:00–0:20 | Pasal UU PT (misalnya tentang pemberhentian direksi) terbelah di tengah ayat oleh chunker ukuran tetap, span gold disorot merah | Legal RAG teams pick a chunk size by guess. In Indonesian regulation, a guess cuts an ayat in half, and the LLM cites half a rule | — | Satu butir kontrol operator yang terbelah oleh ukuran tetap |
| 1 | 0:20–0:55 | Panel potongan berpindah ke profil struktur, lalu frontier UU PT dengan dua titik disorot | Same token budget, `{n}` tokens. Structure-aware profile fully covers the gold for `{x of y}` held-out items, fixed-size for `{…}`. Each dot is a setting; the frontier is what's worth using | Grid (tanpa LLM) | Frontier UU PT, angka held-out, hitungan mentah |
| 2 | 0:55–1:25 | Deret frontier header B on vs off, filter butir parafrase, catatan run dengan token cached | Muse Spark writes a context header for every chunk, with the whole regulation cached. On paraphrased questions, the frontier moves by `{…}`. Cached tokens: `{…}`, cost `{$…}` | B, D | Frontier dua deret, filter asal/mode, catatan run B |
| 3 | 1:25–2:00 | Akta sintetis mentah → skema hasil induksi Spark → koreksi operator (diff v1/v2) → potongan akta | Notarial deeds have no parser. Spark reads a few and proposes the structure: head, body, closing, Pasal. I fix `{n}` lines, and the chunker follows the schema | A | Skema akta v1 dan v2, panel potongan akta |
| 4 | 2:00–2:35 | Panel bukti: jawaban dari profil terbaik vs pembanding, kutipan dengan tanda lulus/gagal; bila stretch Glimmer jadi, pemilih model berpindah ke Glimmer lokal untuk butir yang sama (H-053) | Does a better setting give a better answer? Same model, same budget. Best profile: citation passes. Baseline: `{fails / abstains}`. Checked by a deterministic verifier, not another LLM | C | Satu butir adegan yang dicek manual, ringkasan 2×2 per profil |
| 5 | 2:35–2:50 | Tombol ekspor profil, JSON profil, layar akhir dengan disclaimer | Output: a versioned profile you drop into your own RAG. Next family: internal policies. Research demo, not legal advice | Ekspor | Profil UU PT dan akta, jumlah butir dan asal |

Di adegan 1 atau 5 ditampilkan satu baris kecil: `{n} items: {a} operator-written, {b} Spark-proposed and operator-approved`. Penonton perlu tahu dari mana butir berasal (H-006).

### Kalau garis potong terpakai (H-017)

| Yang dipotong | Akibat ke video |
|---|---|
| Uji 3 berlaku | Adegan 4 hanya menampilkan uji ada dan setia. Status berlaku disebut sebagai pekerjaan berikutnya |
| Frontier akta (M4.2) | Adegan 3 berhenti di potongan akta. Kalimat soal angka akta dihapus |
| Header B hanya untuk setting di frontier | Adegan 2 tetap; narasi menyebut "on the frontier settings" |
| Akta 5 dokumen, lantai 5 butir (potong 2) | Tidak berdampak ke adegan |
| Grid sempit (potong 3) | Tidak berdampak ke adegan; frontier memuat lebih sedikit titik |

Adegan 1, 2, dan 4 tidak boleh hilang, karena memuat inti metode dan peran Spark.

## Aturan isi

- Angka di video harus sama dengan angka di layar dan README. Pakai hitungan mentah ("7 of 12"), bukan persen, dan tanpa klaim signifikansi.
- Butir yang dipakai di adegan sudah dicocokkan manual ke teks (H-011).
- Model disebut sebagai `muse-spark-1.3` (varian Contributor). Satu kalimat disclosure (H-028): Contributor dipakai karena korpus publik atau sintetis; dokumen rahasia memakai Standard dengan mengganti model ID. Tidak ada klaim soal Wonder atau model lain. Glimmer hanya disebut bila pembanding H-047 tampil (lihat butir di bawah).
- Tidak ada UI prototipe pra-acara, dan tidak ada kode prototipe itu di layar. App hackathon ini tentu tampil (H-021).
- Disclosure korpus (H-031, H-045, H-039): teks UU PT adalah konsolidasi tidak resmi yang disiapkan operator dari teks peraturan dan putusan MK (sampai 30 Desember 2022), dan akta adalah sintetis yang ditulis agen AI lalu direview operator. Satu baris di layar akhir video dan di README, tidak perlu narasi.
- Bila pembanding Glimmer tampil (H-047, H-053): disebut "Muse Glimmer, open-weight, running locally on the operator's machine", bukan bobot yang sama dengan Spark, dengan label model, kuantisasi, dan effort di U3. Jawabannya tidak dicampur dengan jawaban Contributor tanpa label. Tanpa klaim mutu bahasa Indonesia umum. Klaim bonus open-weight hanya setelah cara verifikasi "own hardware" dikonfirmasi penyelenggara.
- Untuk akta tidak ada kata "held-out": butir akta adalah uji transfer tanpa split (H-054).
- Tidak ada akta asli, dokumen internal, data klien, atau `.env` atau API key di layar. Terminal yang direkam hanya terminal putar ulang.
- Disclaimer tampil di adegan 5: "Research demo. Not legal advice."

## Run tersimpan wajib per adegan (mode putar ulang)

Rekaman memakai mode putar ulang (M5.1). Adegan hanya bisa direkam bila run di bawah ada di `runs/`. Diperiksa saat rekaman kasar 2 Nov.

| Adegan | Run wajib | Endpoint (`docs/API.md`) |
|---|---|---|
| 0 | Potongan setting ukuran tetap untuk butir adegan; retrieval butir itu | R4, R5 |
| 1 | Grid UU PT held-out pada anggaran default; potongan profil struktur; ringkasan butir | R3 (`grid`, `items_summary`), R4 |
| 2 | Grid dengan deret header B; run B dengan cached tokens; usulan D yang disetujui (mode parafrase) | R3 (`grid`, `runs_summary`, `proposals`), R6 |
| 3 | Skema akta v1 dan v2; potongan akta menurut skema | R3 (`schemas`, `schema_diff`), R4 |
| 4 | Jawaban C untuk butir `scene_checked`, dua slot; hasil verifier; ringkasan 2×2; bila stretch Glimmer dipakai, run Glimmer untuk butir yang sama | R3 (`answers`, `answers_summary`) |
| 5 | Profil UU PT dan akta; ringkasan butir | W7, R3 (`items_summary`) |

## Produksi

| Tanggal | Langkah | Jam (operator) |
|---|---|---|
| 31 Okt | Kunci storyboard setelah hasil C pertama ada. Pilih butir adegan dan cek manual ke teks | 1 |
| 2 Nov malam | Rekaman kasar dari mode putar ulang setelah M4. Tujuannya menemukan panel yang kurang, bukan hasil final | 1 |
| 3 Nov | Perbaikan layar dari rekaman kasar (M5.1). Kode dibekukan 20:00 WIB | (masuk M5.1) |
| 4 Nov pagi | Rekam layar per adegan, terpisah | 1,5 |
| 4 Nov siang | Rekam narasi, edit, takarir Inggris dibakar ke video | 2,5 |
| 4 Nov sore | Unggah unlisted, tonton ulang penuh di perangkat lain, isi form, ringkasan 100–200 kata | 1 |
| 4 Nov malam | Submit. Batas resmi 5 Nov 09:00 WIB adalah cadangan, bukan target | — |

Total sekitar 7 jam.

Teknis rekaman:
- Rekam 1920×1080 dengan zoom browser 125–150% supaya teks hukum terbaca.
- Mode putar ulang tanpa API (M5.1), kecuali satu panggilan pendek di adegan 4 (W6) kalau ingin menunjukkan panggilan langsung.
- Narasi direkam terpisah dari layar supaya bisa diulang tanpa mengulang demo.
- Takarir dibakar ke video, karena penonton mungkin menonton tanpa suara.
- Sorotan dan zoom dibuat di editor, bukan dengan menggerakkan kursor saat rekam.

## Gate sebelum unggah

- [ ] Durasi ≤ 3:00 (Participant Guide, H-043).
- [ ] Setiap angka cocok dengan layar dan README.
- [ ] Jumlah butir dan asalnya disebut.
- [ ] Keempat peran Spark terlihat, dan nama model tampil.
- [ ] Disclaimer tampil.
- [ ] Disclosure tampil di layar akhir video dan di README: Contributor (H-028), konsolidasi UU PT tidak resmi (H-031), akta ditulis agen AI dengan identitas fiktif (H-039, H-041), Glimmer sebagai open-weight lokal dengan atribusi kartu model bila tampil (H-047).
- [ ] Tidak ada secret, akta asli, dokumen internal, atau UI prototipe pra-acara.
- [ ] Ditonton ulang penuh sekali tanpa suara dan sekali dengan suara.
