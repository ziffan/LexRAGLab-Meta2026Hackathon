# PRD — LexRAGLab: penemu setting chunking dan retrieval per keluarga dokumen

Tujuan: menetapkan masalah, pengguna, lingkup, dan ukuran sukses aplikasi sebelum spec teknis dan kode.
Sumber keputusan: H-001, H-002, H-004, H-005, H-006, H-007, H-011, H-012, H-013, H-017, H-018, H-028, H-029, H-031, H-032, H-039, H-043, H-045, H-047, H-051, H-053, H-054, H-060, H-098, H-100, H-102.

## 1. Masalah

Tim RAG hukum memilih ukuran potongan (chunk) dengan menebak. Pada peraturan Indonesia, tebakan itu bisa membelah satu ayat di tengah. LLM lalu menerima setengah aturan dan mengutipnya seolah utuh.

Pemicu: kerja agentic di bidang hukum (legal opinion, legal due diligence, penyusunan kontrak) harus merujuk korpus aturan (undang-undang dan peraturan pelaksananya), dan korpus itu tidak muat dalam satu context window agen. Satu undang-undang saja bisa melewati jendela 200 ribu token, dan bahan utuh satu pekerjaan melampaui jendela 1 juta token, sementara dari naskah peraturan yang benar-benar dipakai hanya sekitar 10%. Motivasi ini berasal dari pengalaman kerja operator, bukan dari tren "RAG"; tujuan aplikasi tidak berubah (H-002, H-004, H-005). Aplikasi ini bertujuan (aims to) menemukan setting yang menjaga konteks yang dibutuhkan agen tetap kecil; itu hipotesis yang diuji lewat evaluasi, bukan klaim penghematan yang sudah terbukti.

Ukuran masalah. Semua angka di bawah adalah pengukuran operator atas pekerjaan sebelumnya (operator's measurements of prior engagements, tidak disertakan dalam repo ini). Bukan keluaran aplikasi dan tidak diukur di aplikasi ini.

Angka korpus (penekanan utama):

| Fakta | Angka | Rujukan |
|---|---|---|
| Satu undang-undang | sekitar 320 ribu token pada satu perkara legal opinion; sendirian melewati jendela 200 ribu | pengukuran operator atas pekerjaan sebelumnya (tidak disertakan) |
| Porsi naskah peraturan yang benar-benar dipakai | sekitar 10% | idem |
| Bahan satu pekerjaan legal opinion (satu transaksi), bahan utuh, komposisi tidak dirinci | sekitar 1,2 juta token (1,2× jendela 1 juta) | idem |
| Bahan satu pekerjaan legal due diligence (berkas utuh), bahan utuh, komposisi tidak dirinci | sekitar 5,8 juta token (5,8× jendela 1 juta) | idem |
| Bahan penyusunan kontrak, bahan utuh, komposisi tidak dirinci | draf kontrak sekitar 2,2 juta token; sekitar 2,8 juta bila pustaka klausul ikut dihitung | idem |
| Bahan satu perkara dibanding jendela 1 juta token | 1,2× sampai 5,8× | idem |
| Ukuran korpus aturan per jenis pekerjaan (LO, LDD, kontrak) | tidak tersedia | idem |
| Halusinasi alat riset hukum komersial | sekitar 17–33% | catatan riset pra-acara (tidak disertakan); Magesh dkk., "Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools", arXiv:2405.20362, 2024 |
| Benchmark RAG hukum Indonesia publik dan standar | tidak ada | idem |

Laju pemakaian agen (pendukung, sekunder), agregat. Dihitung dari transkrip agen lokal operator dengan tarif list API (bukan tagihan); pengukuran operator atas pekerjaan sebelumnya, tidak disertakan dalam repo ini:

- Legal due diligence (dua engagement): sekitar 15 miliar token input ter-cache dibaca ulang dalam sekitar 120 sesi agen, sekitar US$8 ribu.
- Legal opinion: sekitar 800 juta token input ter-cache dibaca ulang dalam sekitar 40 sesi agen, sekitar US$500.
- Penyusunan kontrak: tidak tercatat; estimasi operator serupa legal opinion (estimasi, bukan ukuran).

Angka laju ini menggambarkan skala pemakaian agen pada pekerjaan sebelumnya, bukan hasil aplikasi ini dan bukan bukti bahwa aplikasi menurunkannya.

Akibatnya: memuat semuanya ke konteks tidak cukup, retrieval wajib ada, dan setting retrieval harus cocok dengan pola dokumen. Saat ini tidak ada cara terukur untuk memilih setting itu pada teks hukum Indonesia.

## 2. Jawaban produk

Untuk satu keluarga dokumen yang polanya homogen, aplikasi menemukan setting chunking dan retrieval yang memberi LLM konteks relevan dan tidak berisik. Keluarannya **profil setting berversi** yang bisa diekspor ke RAG lain. Lingkup berhenti di penemuan setting, bukan RAG produk (H-004).

"Optimal" didefinisikan di H-005: span recall dan precision token pada anggaran token tetap, ditampilkan sebagai Pareto frontier, dipilih di set tune dan dilaporkan di held-out.

Muse Spark 1.3 (`muse-spark-1.3-contributor`, H-028) mengerjakan bagian yang tadinya butuh manusia:

| Peran | Status | Kerja Spark |
|---|---|---|
| A. Induksi struktur | Inti | Membaca sampel keluarga dokumen, mengeluarkan skema hierarki yang menggerakkan chunker |
| B. Contextual chunking | Inti | Menulis header konteks per potongan, dokumen sumber di-cache |
| C. Evaluasi ujung ke ujung | Lantai bukti | Menjawab dari top-K profil terbaik vs pembanding; kutipan diperiksa verifier deterministik |
| D. Calon butir | Pendukung | Mengusulkan (query, span gold) literal dan parafrase, dan mode `unanswerable` untuk butir `tolak` (H-092, H-095); operator memeriksa semua |

Grid search retrieval tidak memakai LLM.

## 3. Persona

| Persona | Profil | Kebiasaan sekarang | Frustrasi | Job-to-be-done |
|---|---|---|---|---|
| P1 Legal engineer / tim RAG hukum | Engineer atau praktisi hukum yang membangun RAG atas peraturan, akta, atau aturan internal. Paham Python dan RAG dasar | Ukuran chunk dari tutorial (mis. ukuran tetap dengan overlap), retrieval satu mode, dinilai dengan mencoba beberapa query | Tidak tahu apakah potongan membelah pasal; tidak ada angka yang bisa dibela; ganti keluarga dokumen berarti mulai menebak lagi | "Beri aku setting yang terukur untuk keluarga dokumenku, dalam bentuk yang bisa langsung kupakai" |
| P2 Operator (pemilik data evaluasi) | Ahli domain hukum yang menulis butir kontrol, memeriksa usulan D, mengoreksi skema A | Menulis kunci jawaban manual | Waktu periksa terbatas; butir buatan model bisa melingkar | "Periksa usulan dengan cepat dan pastikan hanya butir sah yang dipakai" |
| P3 Penonton demo | Penonton global, menonton video ≤ 3 menit (Participant Guide, H-043) dan mungkin membuka repo | Menonton video demo | Teks hukum berbahasa Indonesia; klaim tanpa bukti | "Dalam tiga menit, lihat bahwa setting bisa diukur dan Spark mengerjakan bagian yang sulit" |

P1 adalah pengguna sasaran. P2 adalah operator proyek ini sendiri. P3 adalah audiens demo, bukan pengguna.

## 4. User story

Prioritas: **Must** = lantai garis potong H-017; **Stretch** = boleh dipotong (H-017). Slice rujukan ada di `docs/MILESTONES.md`.

| ID | Story | Prioritas | Kriteria terima (ringkas) | Slice |
|---|---|---|---|---|
| US-01 | Sebagai P1, aku ingin melihat batas potongan dan span gold di atas teks sumber, supaya aku tahu apakah setting membelah pasal | Must | Given satu butir dan satu setting, When panel dibuka, Then batas potongan dan span gold tampil, dan offset cocok tanpa selisih karakter | M1.1 |
| US-02 | Sebagai P1, aku ingin span recall, precision token, dan MRR per butir pada anggaran token tetap | Must | Given setting dan anggaran, Then tabel per butir tampil dengan tokenizer lokal yang tercatat | M1.2, M1.3 |
| US-03 | Sebagai P1, aku ingin Pareto frontier recall vs token di set tune dan angka held-out, supaya pilihanku tidak overfit | Must | Titik terdominasi tidak masuk frontier; angka laporan dari held-out; klik titik mengubah panel lain | M1.4 |
| US-04 | Sebagai P1, aku ingin Recall@K, entity preservation, dan boundary coherence | Must | Ketiganya tampil untuk setting terpilih, struktur vs ukuran tetap | M1.5 |
| US-05 | Sebagai P2, aku ingin Spark mengusulkan butir literal dan parafrase, lalu aku setujui, ubah, atau tolak | Must | Status hanya `usulan → disetujui / diubah / ditolak`; hanya yang disetujui masuk evaluasi; asal tercatat | M2.1 |
| US-06 | Sebagai P1/P3, aku ingin melihat jawaban Spark dari profil terbaik vs pembanding dengan kutipan yang diperiksa program | Must | Dua kolom, anggaran dan instruksi sama; tolak dan bukti-tidak-cukup adalah keluaran sah; uji ada dan setia lulus/gagal | M2.2, M2.3 |
| US-07 | Sebagai P1, aku ingin tahu apakah pasal yang dikutip berlaku pada tanggal acuan | Stretch | Tiga nilai, `berlaku_bersyarat` tampil apa adanya | M2.4 |
| US-08 | Sebagai P1, aku ingin header konteks B sebagai sumbu setting, dengan biaya dan token cached terlihat | Must | Frontier punya deret header on/off; token header masuk anggaran | M3.1, M3.2 |
| US-09 | Sebagai P2, aku ingin skema struktur hasil induksi Spark dan bisa mengoreksinya tanpa menimpa usulan asli | Must | Skema v1 (Spark) dan v2 (koreksi) tersimpan terpisah; chunker skema masuk grid | M3.3, M3.4 |
| US-10 | Sebagai P1, aku ingin pola yang sama bekerja pada akta tanpa parser | Must (skema + potongan); frontier akta boleh dipotong | Skema akta dan potongan akta tampil; frontier akta kalau tidak dipotong, sebagai uji transfer tanpa split tune/held-out (H-054) | M4.1, M4.2 |
| US-11 | Sebagai P1, aku ingin mengekspor profil berversi dan memuatnya ulang dengan hasil identik | Must | Muat ulang → hash potongan sama; hash korpus beda → ditolak | M4.3 |
| US-12 | Sebagai P3, aku ingin demo berjalan tanpa API dan tanpa macet, dan bisa dibuka sebagai situs | Must | Mode putar ulang memutar semua adegan dari `runs/` dan `data/` (H-050); ekspor statisnya terpasang di GitHub Pages tanpa backend (H-051) | M5.1 |
| US-13 | Sebagai P1, aku ingin melihat apakah profil yang sama tetap berguna untuk model open-weight yang berjalan di mesinku sendiri | Stretch | Di U3, jawaban C dari Glimmer lokal atau Spark Open (Baseten) untuk profil terbaik dan baseline, berlabel model, kuantisasi, effort, tidak dicampur dengan Contributor (H-047, H-053, H-060) | M2.5 |

## 5. Alur utama

1. Operator memuat korpus keluarga dokumen (UU PT, lalu akta). Sistem mencatat hash dan token.
2. Operator menulis butir kontrol. Spark mengusulkan butir tambahan (D). Operator memeriksa di layar Review.
3. Split tune/held-out ditetapkan sekali dengan seed tercatat (H-015).
4. Spark menginduksi skema (A). Operator mengoreksi; v2 menggerakkan chunker skema.
5. Spark menulis header potongan (B) sesuai granularitas H-038.
6. Runner grid menjalankan semua setting tanpa LLM dan menghitung metrik di tune dan held-out.
7. Pengguna memilih titik di frontier. Panel potongan, tabel per butir, dan panel bukti ikut berubah.
8. Spark menjawab satu butir dari profil terbaik dan pembanding (C). Verifier memberi tanda lulus/gagal.
9. Pengguna mengekspor profil berversi.
   - Cabang: kalau API tidak tersedia, langkah 7–9 berjalan dari run tersimpan (mode putar ulang).
   - Cabang: kalau garis potong H-017 terpakai, frontier akta dan uji 3 tidak tampil, dan layar memberi label "not run".

## 6. Lingkup dan non-lingkup

**Lingkup**
- Keluarga UU PT penuh: konsolidasi tidak resmi UU 40/2007 yang disiapkan operator sampai 30 Desember 2022, dengan anotasi perubahan (H-031, H-045), grid, peran A, B, C, D.
- Keluarga akta: transfer, hanya akta sintetis (H-007, H-039: lima akta pendirian PT ditulis agen dan direview operator, minimal 5 butir); blanko PPAT tidak dipakai (H-056).
- Aturan internal: hanya disebut di pitch dan video, tanpa dokumen.
- Satu halaman tiga panel plus layar Review, label bahasa Inggris (H-018).
- Ekspor profil berversi, mode putar ulang, dan replay statis di GitHub Pages (H-051).
- Stretch (selesai): pembanding Glimmer lokal dan Spark Open di Baseten pada peran C (H-047, H-053, H-060), diperluas ke A dan B (H-100), plus sapuan effort (H-102); hasil utama tetap Contributor.

**Non-lingkup**
- RAG produk, chatbot sitasi, aplikasi mobile.
- Auth, database, vector database, LangChain, parser PDF, reranker (H-013, `docs/MILESTONES.md`).
- Model selain `muse-spark-1.3-contributor` (H-028), kecuali pembanding terpisah Glimmer lokal dan Spark Open di Baseten untuk peran C, A, dan B (H-047, H-060, H-100; hasil utama tetap Contributor). SAM, Muse Image, dan Wonder tidak dipakai. Muse Code tetap Standard.
- Spark sebagai agen pencari setting, tool calling, Self-Route, dua atau tiga lengan (H-004).
- Akta asli, dokumen internal, data klien (H-007).
- Kode prototipe pra-acara (tidak disertakan, H-003).

## 7. Kriteria sukses

Proyek berhasil kalau, pada saat submit:

| # | Kriteria | Cara cek |
|---|---|---|
| S1 | Frontier UU PT di held-out tampil untuk minimal tiga mode retrieval dan dua chunker | Layar + catatan run |
| S2 | Butir UU PT 15–20 disetujui, minimal enam butir kontrol operator, minimal tiga kontrol di held-out | `data/butir/` + laporan split (H-011, H-015). Catatan: `uupt.v16` = 20 butir bergold + 3 `tolak` (`docs/EVAL-SPEC.md` §5 catatan H-099); kriteria tidak diubah |
| S3 | Keempat peran Spark punya keluaran tersimpan dan tampil di layar | Mode putar ulang |
| S4 | Skema A akta tersimpan v1/v2 dan menggerakkan chunker | Panel skema |
| S5 | Verifier uji 1 dan 2 berjalan dan ringkasan 2×2 tampil dalam hitungan mentah | Panel bukti |
| S6 | Profil UU PT dan akta diekspor dan lolos round-trip | Test M4.3 |
| S7 | Setiap angka di video sama dengan layar dan README | Gate `docs/VIDEO.md` |
| S8 | Tidak ada secret, akta asli, atau dokumen internal di repo | Gate `docs/SECURITY-COMPLIANCE.md` |

Angka hasil (recall, token, biaya) tidak ditargetkan di dokumen ini. Angka hanya muncul setelah run ada.

## 8. Asumsi dan risiko produk

- Official Rules dibaca dari Participant Guide (H-043): repo publik, video tiga menit, karya baru saja. Repo publik sudah diputus operator (H-029), tanpa bentrok.
- Butir sedikit, jadi hasil dilaporkan per butir tanpa klaim signifikansi (H-005).
- Butir usulan Spark bisa melingkar; dilawan dengan mode parafrase dan laporan per asal (H-006).
- Risiko lengkap: `docs/ARCHITECTURE.md` bagian failure mode.
