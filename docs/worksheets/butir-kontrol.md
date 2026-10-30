> BUKAN BUTIR. Agen tidak menulis butir (H-006). Lembar ini hanya peta lokasi kandidat dan template kosong untuk diisi operator.

# Lembar kerja butir kontrol UU PT (untuk operator)

> Lembar snapshot 27 Okt; data berlaku `data/butir/uupt.v16.jsonl` (23 butir sah). Isian kolom (termasuk "Video") milik operator.

Tujuan: membantu operator menulis butir kontrol (asal `operator`, H-011) atas `data/uupt/UU_40_2007_PERSEROAN_TERBATAS.md`. Lembar ini hanya memetakan lokasi dan alasan struktural. Query, span, jawaban, dan pilihan mode semuanya ditulis operator. Tidak ada tafsir hukum di sini.

Dasar: H-006, H-009, H-011, H-015, H-046, H-048, H-049; `docs/DATA-CONTRACTS.md` §2 dan §4; `docs/EVAL-SPEC.md` §4 sampai §8; G-20, G-21, G-25.

## 1. Cara pakai

- Nomor baris merujuk berkas mentah beku (SHA-256 `a6b38ee5...ae81`, 4.995 baris). Offset span bukan nomor baris: tulis span atas teks bersih keluaran pemuat (M0.2), bukan atas berkas mentah.
- Untuk satu ayat, baris yang tertulis adalah baris awal ayat; untuk rentang ayat, dari baris awal ayat pertama sampai baris awal ayat terakhir (isi ayat terakhir menyusul di bawahnya); untuk satu Pasal, dari baris judul sampai sebelum Penjelasan.
- Panjang "sekitar N karakter" dihitung kasar dari baris isi berkas mentah (tanpa judul dan baris kosong). Itu bukan ukuran token dan bukan ukuran teks bersih.
- Satu butir boleh mencakup beberapa dimensi sekaligus. Kolom "Dimensi" di §5 menunjukkan Pasal yang menguji banyak dimensi.
- Kandidat bukan rekomendasi. Operator memilih, menolak, atau mencari lokasi lain, dan memverifikasi sendiri bahwa lokasi yang dipilih cocok sebagai gold.
- Heading `### Pasal N` adalah batang tubuh; `#### Penjelasan Pasal N` di bawahnya bernomor sama (G-20). Alamat kanonik selalu menyertakan bagian: `UU 40/2007 › Pasal N › ayat (m)` atau `UU 40/2007 › Penjelasan › Pasal N`.

## 2. Stratum dan dimensi uji

Stratum H-015 = asal × mode. Butir kontrol selalu asal `operator`; operator memilih mode `literal` atau `parafrase` per butir. Lokasi tidak terikat mode: lokasi yang sama bisa dipakai di kedua mode, dan memang berguna kalau sebaran mode di antara kontrol seimbang.

| Kode | Dimensi | Rujukan | Yang diuji |
|---|---|---|---|
| A | Satu ayat | H-048 | Presisi token; potongan ukuran tetap membawa ayat tetangga |
| B | Beberapa ayat berurutan | H-048 | Gold melintasi ayat; Recall@K per bagian-ayat |
| C | Penjelasan bernomor sama dengan batang tubuh | G-20 | Chunker/retriever tidak menukar bagian; alamat menyertakan bagian |
| D | Ketentuan hasil Perppu 2/2022 (Pasal 1, 7, 32, 153, 153A sampai 153J) | H-046 | Lokasi bertanggal acuan ≥ 2022-12-30; rangkaian sisipan berkosakata mirip |
| E | Pasal 86 ayat (9) (dimaknai MK) | H-046 | Pemisahan anotasi; offset atas teks bersih |
| F | Kalimat penutup rincian | G-25, H-046 | Chunker per huruf menaruh kalimat penutup pada ayat |
| G | Pasal panjang | H-012 | Ukuran tetap kecil memutus Pasal |
| H | Pasal pendek | H-012 | Ukuran tetap besar menelan tetangga |
| I | Pasal yang merujuk Pasal lain | | Jawaban tersebar di lebih dari satu Pasal; gold tetap di satu dokumen |
| J | Wajib tolak (tanpa gold) | EVAL-SPEC §4 | Perilaku abstain; `gold_spans` kosong |

BM25 vs dense, secara umum: mode `literal` cenderung membedakan chunker/BM25 lewat istilah khas dan nomor; mode `parafrase` cenderung membedakan dense lewat kata yang berbeda dari teks. Sinyal ini bergantung pada tulisan operator, bukan pada lokasi saja, jadi tidak ada kolom mode per lokasi di bawah.

## 3. Kandidat per dimensi

### A. Satu ayat

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Pasal 7 › ayat (4)` | 221 | Ayat pendek di Pasal delapan ayat; potongan ukuran tetap hampir pasti membawa ayat tetangga, presisi token turun |
| `UU 40/2007 › Pasal 32 › ayat (2)` | 1063 | Ayat tunggal di Pasal pendek hasil Perppu; potongan besar menelan seluruh Pasal |
| `UU 40/2007 › Pasal 86 › ayat (9)` | 2683 | Ayat ke-9 dari 9, ujung Pasal; uji batas potongan di akhir Pasal |
| `UU 40/2007 › Pasal 94 › ayat (1)` | 2903 | Ayat pertama dari 9; kalimat sangat pendek, mudah tenggelam di potongan besar |
| `UU 40/2007 › Pasal 102 › ayat (4)` | 3209 | Ayat ke-4 dari 5; bertetangga dengan ayat berkosakata sama, uji pembeda ayat |
| `UU 40/2007 › Pasal 153A › ayat (1)` | 4711 | Ayat pertama Pasal sisipan; kosakata sama dengan 153B sampai 153J |
| `UU 40/2007 › Pasal 142 › ayat (6)` | 4365 | Ayat terakhir dari 6, sesudah ayat berisi rincian berhuruf; uji batas setelah rincian |

### B. Beberapa ayat berurutan

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Pasal 86 › ayat (1) sampai (4)` | 2667–2673 | Alur bertahap lintas ayat berurutan; gold bisa melintasi ayat, uji Recall@K per bagian-ayat dan potongan yang memotong di batas ayat |
| `UU 40/2007 › Pasal 102 › ayat (1) sampai (2)` | 3197–3205 | Ayat (2) merujuk ayat (1) huruf a; ayat (1) memuat rincian berhuruf plus kalimat penutup |
| `UU 40/2007 › Pasal 142 › ayat (1) sampai (2)` | 4339–4353 | Ayat (2) merujuk ayat (1); keduanya memuat rincian berhuruf; Pasal beranotasi |
| `UU 40/2007 › Pasal 21 › ayat (1) sampai (3)` | 739–755 | Pasal sembilan ayat; rentang ayat bersebelahan di Pasal yang cukup panjang |
| `UU 40/2007 › Pasal 79 › ayat (1) sampai (3)` | 2387–2395 | Pasal sepuluh ayat dengan rujukan ke Pasal lain; rentang ayat di Pasal panjang |
| `UU 40/2007 › Pasal 153A › ayat (1) sampai (2)` | 4711–4713 | Dua ayat berurutan di Pasal sisipan; ayat (2) merujuk ayat (1) |
| `UU 40/2007 › Pasal 7 › ayat (1) sampai (2)` | 215–217 | Dua ayat pertama Pasal hasil Perppu; ayat (3) merujuk ayat (2) |

### C. Penjelasan bernomor sama dengan batang tubuh

Penjelasan yang berisi uraian:

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Penjelasan › Pasal 4` | 177 | Pasal pendek (sekitar 123 karakter) dengan Penjelasan jauh lebih panjang (sekitar 717); pencarian bisa mendarat di Penjelasan |
| `UU 40/2007 › Penjelasan › Pasal 6` | 203 | Pasal pendek, Penjelasan lebih panjang (sekitar 351) |
| `UU 40/2007 › Penjelasan › Pasal 8` | 323 | Penjelasan sekitar 1.279 karakter, melebihi batang tubuh (sekitar 822) |
| `UU 40/2007 › Penjelasan › Pasal 22` | 835 | Penjelasan (sekitar 1.102) hampir tiga kali batang tubuh (sekitar 437) |
| `UU 40/2007 › Penjelasan › Pasal 34` | 1111 | Penjelasan sekitar 1.642 karakter, hampir tiga kali batang tubuh (sekitar 603); kosakata dua bagian tumpang-tindih |
| `UU 40/2007 › Penjelasan › Pasal 36` | 1187 | Penjelasan sekitar 1.567 karakter, dua kali batang tubuh (sekitar 768) |
| `UU 40/2007 › Penjelasan › Pasal 86` | 2685 | Penjelasan sekitar 1.207 karakter, bersubjudul `Ayat (n)`; nomor sama dengan Pasal beranotasi |
| `UU 40/2007 › Penjelasan › Pasal 91` | 2809 | Pasal pendek (sekitar 197), Penjelasan sekitar 534 memuat uraian istilah |
| `UU 40/2007 › Penjelasan › Pasal 94` | 2921 | Penjelasan sekitar 1.257 karakter, bersubjudul ayat |
| `UU 40/2007 › Penjelasan › Pasal 102` | 3213 | Penjelasan sekitar 1.115 karakter, bersubjudul ayat; berpasangan dengan Pasal berkalimat penutup |
| `UU 40/2007 › Penjelasan › Pasal 103` | 3243 | Penjelasan (sekitar 108) berisi uraian istilah; kosakata sama dengan batang tubuh |

Pembanding (Penjelasan "Cukup jelas." yang hampir identik antar-Pasal):

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Penjelasan › Pasal 2` | 143 | Penjelasan hanya "Cukup jelas." (12 karakter); penanda pembanding, bukan kandidat gold |
| `UU 40/2007 › Penjelasan › Pasal 11` | 459 | Penjelasan hanya "Cukup jelas." (12 karakter); penanda pembanding, bukan kandidat gold |
| `UU 40/2007 › Penjelasan › Pasal 19` | 717 | Penjelasan hanya "Cukup jelas." (12 karakter); penanda pembanding, bukan kandidat gold |
| `UU 40/2007 › Penjelasan › Pasal 24` | 881 | Penjelasan hanya "Cukup jelas." (12 karakter); penanda pembanding, bukan kandidat gold |
| `UU 40/2007 › Penjelasan › Pasal 25` | 895 | Penjelasan hanya "Cukup jelas." (12 karakter); penanda pembanding, bukan kandidat gold |
| `UU 40/2007 › Penjelasan › Pasal 27` | 933 | Penjelasan hanya "Cukup jelas." (12 karakter); penanda pembanding, bukan kandidat gold |

### D. Hasil Perppu 2/2022

Semua berada di batang tubuh. Tanggal berlaku konsolidasi 30 Desember 2022; `reference_date` butir tidak boleh lebih awal (H-046).

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Pasal 1` | 99–134 | Hasil Perppu; Pasal terpanjang (sekitar 3.421 karakter), 19 butir definisi bernomor tanpa ayat bernomor |
| `UU 40/2007 › Pasal 7` | 213–248 | Hasil Perppu; delapan ayat, ayat (3) merujuk ayat (2) |
| `UU 40/2007 › Pasal 32` | 1059–1066 | Hasil Perppu; Pasal pendek tiga ayat |
| `UU 40/2007 › Pasal 153` | 4701–4704 | Hasil Perppu; satu kalimat tanpa ayat bernomor, Penjelasan "Cukup jelas." |
| `UU 40/2007 › Pasal 153A` | 4709–4716 | Sisipan Perppu; pembuka rangkaian 153A sampai 153J (di bawah BAB XI) |
| `UU 40/2007 › Pasal 153B` | 4721–4728 | Sisipan; merujuk Pasal 153A, kosakata sama dengan tetangganya |
| `UU 40/2007 › Pasal 153C` | 4743–4748 | Sisipan; Pasal pendek, dua ayat |
| `UU 40/2007 › Pasal 153D` | 4753–4758 | Sisipan; Pasal pendek, dua ayat |
| `UU 40/2007 › Pasal 153E` | 4763–4768 | Sisipan; satu dari dua Pasal sisipan (bersama 153B) dengan Penjelasan lebih dari "Cukup jelas." (sekitar 178 karakter) |
| `UU 40/2007 › Pasal 153F` | 4779–4784 | Sisipan; Pasal pendek, dua ayat |
| `UU 40/2007 › Pasal 153G` | 4789–4806 | Sisipan; sekitar 986 karakter, Pasal terpanjang di rangkaian |
| `UU 40/2007 › Pasal 153H` | 4811–4816 | Sisipan; dua ayat |
| `UU 40/2007 › Pasal 153I` | 4821–4826 | Sisipan; dua ayat |
| `UU 40/2007 › Pasal 153J` | 4831–4844 | Sisipan; penutup rangkaian, sekitar 835 karakter |

### E. Pasal 86 ayat (9)

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Pasal 86 › ayat (9)` | 2683 | Ayat bertanda footnote `[^1]` di akhir kalimat; label tebal di baris 2665 (bawah judul Pasal), definisi footnote di baris 4993. Teks bersih membuang semuanya, jadi offset span dihitung atas teks bersih (G-21) |
| `UU 40/2007 › Pasal 142` | 4335–4366 | Catatan, bukan MK: label tebal (baris 4337) dan footnote `[^2]` (baris 4355, ayat (2) huruf a) bersumber UU 24/2011; statusnya urusan operator (H-046). Dicatat supaya operator tahu ada dua lokasi beranotasi |

### F. Kalimat penutup rincian

Baris kontras ikut dicatat supaya operator dapat menilai lokasi tanpa kalimat penutup.

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Pasal 102 › ayat (1)` | 3197 | Satu-satunya kalimat penutup rincian di batang tubuh berkas ini (baris 3203, diawali huruf kecil): milik ayat (1), bukan butir b. Chunker per huruf yang menempelkannya ke butir b salah |
| `UU 40/2007 › Pasal 142 › ayat (1)` | 4339 | Kontras: rincian a sampai f tanpa kalimat penutup |
| `UU 40/2007 › Pasal 142 › ayat (2)` | 4353 | Kontras: kalimat pembuka berakhir koma, rincian a dan b, tanpa kalimat penutup |
| `UU 40/2007 › Pasal 1` | 99–134 | Kontras: 19 butir bernomor tanpa ayat bernomor; menguji chunker yang menyamakan butir dengan ayat |

### G. Pasal panjang

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Pasal 1` | 99–134 | Terpanjang, sekitar 3.421 karakter isi; menguji potongan ukuran tetap kecil yang memutus Pasal |
| `UU 40/2007 › Pasal 125` | 3873–3912 | Sekitar 2.729, delapan ayat karakter isi; menguji potongan ukuran tetap kecil yang memutus Pasal |
| `UU 40/2007 › Pasal 123` | 3743–3784 | Sekitar 2.544, lima ayat karakter isi; menguji potongan ukuran tetap kecil yang memutus Pasal |
| `UU 40/2007 › Pasal 10` | 391–412 | Sekitar 2.395, sepuluh ayat karakter isi; menguji potongan ukuran tetap kecil yang memutus Pasal |
| `UU 40/2007 › Pasal 80` | 2457–2478 | Sekitar 2.145, delapan ayat karakter isi; menguji potongan ukuran tetap kecil yang memutus Pasal |
| `UU 40/2007 › Pasal 79` | 2385–2414 | Sekitar 2.100, sepuluh ayat karakter isi; menguji potongan ukuran tetap kecil yang memutus Pasal |
| `UU 40/2007 › Pasal 29` | 949–988 | Sekitar 2.037, enam ayat karakter isi; menguji potongan ukuran tetap kecil yang memutus Pasal |
| `UU 40/2007 › Pasal 127` | 4019–4036 | Sekitar 1.943, delapan ayat karakter isi; menguji potongan ukuran tetap kecil yang memutus Pasal |
| `UU 40/2007 › Pasal 86` | 2663–2684 | Sekitar 1.903, sembilan ayat karakter isi; menguji potongan ukuran tetap kecil yang memutus Pasal |

### H. Pasal pendek

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Pasal 51` | 1573–1576 | Terpendek, sekitar 73 karakter isi; potongan besar menelan Pasal tetangga sehingga presisi token turun |
| `UU 40/2007 › Pasal 136` | 4181–4184 | Sekitar 77 karakter isi; potongan besar menelan Pasal tetangga sehingga presisi token turun |
| `UU 40/2007 › Pasal 113` | 3531–3534 | Sekitar 112 karakter isi; potongan besar menelan Pasal tetangga sehingga presisi token turun |
| `UU 40/2007 › Pasal 134` | 4141–4144 | Sekitar 113 karakter isi; potongan besar menelan Pasal tetangga sehingga presisi token turun |
| `UU 40/2007 › Pasal 124` | 3865–3868 | Sekitar 113 karakter isi; potongan besar menelan Pasal tetangga sehingga presisi token turun |
| `UU 40/2007 › Pasal 2` | 139–142 | Sekitar 173 karakter isi; potongan besar menelan Pasal tetangga sehingga presisi token turun |
| `UU 40/2007 › Pasal 119` | 3671–3674 | Sekitar 154 karakter isi; potongan besar menelan Pasal tetangga sehingga presisi token turun |

### I. Pasal yang merujuk Pasal lain

| Alamat kanonik | Baris berkas mentah | Alasan struktural |
|---|---|---|
| `UU 40/2007 › Pasal 89` | 2755–2766 | Ayat (4) merujuk Pasal 86 ayat (5) sampai (9); potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 102` | 3195–3212 | Ayat (5) merujuk Pasal 89 dan ayat (1); potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 95` | 2961–2972 | Merujuk Pasal 93 (dan Pasal lain); potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 112` | 3503–3512 | Cermin Pasal 95 untuk Dewan Komisaris, merujuk Pasal 110; potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 97` | 3017–3040 | Ayat (1) merujuk Pasal 92 ayat (1); potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 114` | 3539–3558 | Ayat (1) merujuk Pasal 108 ayat (1); cermin Pasal 97; potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 119` | 3671–3674 | Satu kalimat merujuk Pasal 105; potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 28` | 937–940 | Satu kalimat merujuk Pasal 9, 10, dan 11; potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 29` | 949–988 | Merujuk Pasal 5, 7, dan 23; potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 127` | 4019–4036 | Merujuk Pasal 87 dan 89; potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 132` | 4115–4118 | Satu kalimat merujuk Pasal 29 dan 30; potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |
| `UU 40/2007 › Pasal 153B` | 4721–4728 | Merujuk Pasal 153A ayat (2); potongan yang memuat Pasal ini belum tentu memuat Pasal yang dirujuk |

### J. Wajib tolak (tanpa gold)

Tidak ada lokasi dan tidak ada query di sini. Jenis pertanyaan di luar cakupan yang umum dipakai:

| Jenis | Catatan struktural |
|---|---|
| Topik yang diatur peraturan lain, tidak dimuat UU PT | Operator memastikan sendiri (grep) bahwa topik itu tidak ada di berkas; kata kunci bisa muncul sebagai rujukan sepintas tanpa isi |
| Perincian teknis yang didelegasikan ke peraturan turunan | Banyak ayat berbunyi "diatur dengan/dalam Peraturan Pemerintah" (mis. baris 371, 457, 663, 987, 1065, 2243, 4143, 4183, 4715, 4727, 4747, 4783, 4815, 4825, 4893). Retrieval mudah mendarat di ayat pendelegasian; menguji apakah sistem tahu isinya tidak ada |
| Subjek yang mirip tetapi di luar naskah (mis. badan usaha lain, atau peraturan lain yang bernomor mirip) | Menguji godaan menjawab dari Pasal yang berkosakata dekat |
| Pertanyaan yang jawabannya bergantung pada fakta pihak, bukan pada teks | Tidak ada teks gold untuk ditunjuk |

Butir tanpa gold: `gold_spans` kosong, `doc_id` tetap diisi, dan dilaporkan terpisah sebagai "no gold (must abstain)" (EVAL-SPEC §4). Metrik span tidak dihitung untuk butir ini.

## 4. Catatan lokasi beranotasi

- Pasal 86: label tebal baris 2665 dan `[^1]` di ayat (9) baris 2683 (definisi footnote di baris 4993).
- Pasal 142: label tebal baris 4337 dan `[^2]` di ayat (2) huruf a baris 4355 (definisi di baris 4995). Menurut H-046 hanya Pasal 86 ayat (9) yang berstatus MK; Pasal 142 `berlaku` + `note`. Keputusan status tetap milik operator (H-009).
- Perubahan hash korpus berarti span gold dihitung ulang (DATA-CONTRACTS §2).

## 5. Tabel cek-silang: dimensi × Pasal

x = Pasal itu muncul sebagai kandidat di dimensi tersebut. Dimensi J tidak berbasis lokasi dan tidak masuk tabel. Pembanding C (Cukup jelas) tidak dihitung.

| Pasal | A | B | C | D | E | F | G | H | I | Dimensi |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  | x |  |  | x |  |  | 2 |
| 2 |  |  |  |  |  |  |  | x |  | 1 |
| 4 |  |  | x |  |  |  |  |  |  | 1 |
| 6 |  |  | x |  |  |  |  |  |  | 1 |
| 7 | x | x |  | x |  |  |  |  |  | 3 |
| 8 |  |  | x |  |  |  |  |  |  | 1 |
| 10 |  |  |  |  |  |  | x |  |  | 1 |
| 21 |  | x |  |  |  |  |  |  |  | 1 |
| 22 |  |  | x |  |  |  |  |  |  | 1 |
| 28 |  |  |  |  |  |  |  |  | x | 1 |
| 29 |  |  |  |  |  |  | x |  | x | 2 |
| 32 | x |  |  | x |  |  |  |  |  | 2 |
| 34 |  |  | x |  |  |  |  |  |  | 1 |
| 36 |  |  | x |  |  |  |  |  |  | 1 |
| 51 |  |  |  |  |  |  |  | x |  | 1 |
| 79 |  | x |  |  |  |  | x |  |  | 2 |
| 80 |  |  |  |  |  |  | x |  |  | 1 |
| 86 | x | x | x |  | x |  | x |  |  | 5 |
| 89 |  |  |  |  |  |  |  |  | x | 1 |
| 91 |  |  | x |  |  |  |  |  |  | 1 |
| 94 | x |  | x |  |  |  |  |  |  | 2 |
| 95 |  |  |  |  |  |  |  |  | x | 1 |
| 97 |  |  |  |  |  |  |  |  | x | 1 |
| 102 | x | x | x |  |  | x |  |  | x | 5 |
| 103 |  |  | x |  |  |  |  |  |  | 1 |
| 112 |  |  |  |  |  |  |  |  | x | 1 |
| 113 |  |  |  |  |  |  |  | x |  | 1 |
| 114 |  |  |  |  |  |  |  |  | x | 1 |
| 119 |  |  |  |  |  |  |  | x | x | 2 |
| 123 |  |  |  |  |  |  | x |  |  | 1 |
| 124 |  |  |  |  |  |  |  | x |  | 1 |
| 125 |  |  |  |  |  |  | x |  |  | 1 |
| 127 |  |  |  |  |  |  | x |  | x | 2 |
| 132 |  |  |  |  |  |  |  |  | x | 1 |
| 134 |  |  |  |  |  |  |  | x |  | 1 |
| 136 |  |  |  |  |  |  |  | x |  | 1 |
| 142 | x | x |  |  |  |  |  |  |  | 2 |
| 153 |  |  |  | x |  |  |  |  |  | 1 |
| 153A | x | x |  | x |  |  |  |  |  | 3 |
| 153B |  |  |  | x |  |  |  |  | x | 2 |
| 153C |  |  |  | x |  |  |  |  |  | 1 |
| 153D |  |  |  | x |  |  |  |  |  | 1 |
| 153E |  |  |  | x |  |  |  |  |  | 1 |
| 153F |  |  |  | x |  |  |  |  |  | 1 |
| 153G |  |  |  | x |  |  |  |  |  | 1 |
| 153H |  |  |  | x |  |  |  |  |  | 1 |
| 153I |  |  |  | x |  |  |  |  |  | 1 |
| 153J |  |  |  | x |  |  |  |  |  | 1 |

## 6. Template butir kosong (field `Item`, DATA-CONTRACTS §4)

Disalin dari bentuk kontrak; semua nilai placeholder. Field `id`, `clean_sha256`, `origin`, `proposal_id`, `created_at` diisi sistem dari jalur masuk. Nilai di bawah hanya mengikuti konvensi contoh kontrak.

```json
{
  "id": "<diisi sistem>",
  "family": "uupt",
  "query": "<ditulis operator>",
  "doc_id": "<doc_id>",
  "gold_spans": [{"start": 0, "end": 0}],
  "clean_sha256": "<clean_sha256 hasil pemuat>",
  "mode": "<literal | parafrase>",
  "origin": "operator",
  "review_status": null,
  "proposal_id": null,
  "reference_date": "<YYYY-MM-DD, >= 2022-12-30>",
  "scene_checked": false,
  "operator_note": null,
  "created_at": "<diisi sistem>"
}
```

Butir wajib tolak: `gold_spans` diisi `[]`.

### Pengingat aturan

- Span ditulis atas teks bersih hasil pemuat; `clean_sha256` harus cocok dengan hasil pemuat. Offset dengan `clean_sha256` lain ditolak (DATA-CONTRACTS §1).
- Offset = indeks code point Unicode, setengah terbuka `[start, end)`.
- `reference_date` untuk `uupt` minimal 2022-12-30 (H-046); lebih awal ditolak saat masuk.
- Minimal enam butir kontrol (H-011) dan, setelah split berstrata (porsi held-out 0,4, H-049), minimal tiga kontrol di held-out (H-015). Bila pembulatan kurang, split memindahkan kontrol ke held-out lebih dulu; bila kontrol kurang dari tiga, split gagal.
- Span menandai semua ayat yang dibutuhkan untuk menjawab, tidak lebih (H-048). Sistem memecahnya di batas ayat; operator tidak memecahnya sendiri.
- Butir held-out dilarang dipakai memilih setting (EVAL-SPEC §8).
- Setiap butir yang akan masuk adegan video dicocokkan manual ke teks dan `scene_checked` diisi operator (H-011).
- Butir diisi dan disetujui operator saja; agen tidak menulis, menyunting, atau menyetujui butir (H-006).
