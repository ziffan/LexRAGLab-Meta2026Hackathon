# DATA-CONTRACTS — bentuk setiap data

Tujuan: menetapkan nama field, tipe, dan pemilik isi setiap data, serta JSON Schema keluaran Spark A, B, C, D yang patuh `strict: true`.
Sumber keputusan: H-005, H-006, H-009, H-011, H-012, H-014, H-015, H-016, H-027, H-031, H-035, H-037, H-042, H-045, H-046, H-047, H-048, H-049, H-053, H-054, H-059, H-060, H-061.

Semua contoh memakai placeholder (`"<query>"`, offset `0`), bukan butir nyata.

## 1. Konvensi

| Hal | Aturan |
|---|---|
| Offset | Indeks code point Unicode pada **teks bersih** (anotasi sudah dipisahkan, H-046), setengah terbuka `[start, end)`. Teks bersih adalah fungsi deterministik dari hash berkas dan `loader_rules_version`; setiap objek yang menyimpan offset menyimpan juga `clean_sha256`, dan offset dengan `clean_sha256` lain ditolak. Tidak ada normalisasi selain aturan pemuat H-046 |
| Hash | SHA-256 heksadesimal huruf kecil atas isi kanonik |
| Waktu | UTC, ISO 8601 dengan `Z` |
| Uang | Integer micro-USD (`cost_usd_micros`). Dilarang float |
| Token | `tokens_local` = tokenizer lokal H-014. `usage_*` = angka dari `usage` Spark. Keduanya tidak dicampur |
| Enum | Nilai data bahasa Indonesia seperti di keputusan; label UI Inggris di `docs/UI-SPEC.md` §6 |
| Penyimpanan | JSON per objek atau JSONL per koleksi di jalur `docs/ARCHITECTURE.md` §6 |
| Versi | Setiap koleksi yang diisi operator punya `version` dan tidak ditimpa; versi baru ditambahkan |

Pemilik isi: **Operator** (hanya manusia menulis), **Spark** (keluaran model, tervalidasi), **Sistem** (dihitung deterministik).

## 2. CorpusDoc

| Field | Tipe | Isi | Pemilik |
|---|---|---|---|
| `doc_id` | string | slug stabil, mis. `"<doc_id>"` | Sistem |
| `family` | enum `uupt` / `akta` | keluarga dokumen (H-031) | Sistem |
| `title` | string | nama peraturan atau akta | Sumber |
| `path` | string | jalur relatif di `data/` | Sistem |
| `sha256` | string | hash berkas mentah | Sistem |
| `clean_sha256` | string | hash UTF-8 teks bersih (H-046) | Sistem |
| `loader_rules_version` | string | versi aturan pemuat yang menghasilkan teks bersih (H-046) | Sistem |
| `char_count` | int | jumlah code point teks bersih | Sistem |
| `tokens_local` | int | token tokenizer lokal | Sistem (M0.2) |
| `tokens_endpoint` | int \| null | token dari `/v1/responses/input_tokens` dikurangi baseline | Sistem (M0.2) |
| `calibration_ratio` | number \| null | `tokens_endpoint / tokens_local` | Sistem (M0.2) |
| `sections` | array of `{section, start, end}` | rentang tiap bagian di teks bersih (H-046); untuk akta satu section `batang_tubuh` (H-076) | Sistem |
| `annotations` | array | anotasi yang dipisahkan pemuat (label, footnote, frontmatter) dengan offset tambat di teks bersih; kosong untuk akta | Sistem |

`sections` mencatat rentang setiap bagian di teks bersih. Status per ketentuan tidak disimpan di `CorpusDoc`; ia ada di `StatusTable` (§5) dengan kunci alamat.

### Aturan pemuat korpus UU PT (H-046)

Berlaku untuk berkas konsolidasi UU PT dengan SHA-256 `a6b38ee519dddeafc130b3ec18ad80805ed51602dbdd98786b7ab9adbd89ae81` (215.465 byte, LF, tanpa BOM, H-045). Pemuat menyesuaikan diri dengan berkas, bukan sebaliknya, dan hanya menerima hash yang tercatat di `config/corpus`. Perubahan apa pun pada berkas berarti pembekuan ulang: hash baru dicatat operator, keputusan direvisi, `loader_rules_version` naik bila aturan berubah, dan span gold yang sudah ditulis dihitung ulang. Akta sintetis tidak memakai aturan anotasi ini; pemuat akta hanya memeriksa UTF-8, `\r`, BOM, dan hash.

**Format berkas** (beku, apa adanya): Markdown dengan frontmatter YAML; Penjelasan inline sebagai `#### Penjelasan Pasal N` langsung setelah `### Pasal N` bernomor sama; anotasi berupa dua label tebal (di bawah Pasal 86 dan Pasal 142) dan dua footnote `[^1]`–`[^2]`; teks lama ketentuan yang diubah tidak disimpan. Heading yang sah hanya `## BAB …` (14, BAB I–XIV), `### Bagian …`, `#### Paragraf …`, `### Pasal N` (171, termasuk 153A–153J setelah Pasal 153 di bawah heading BAB XI), `#### Penjelasan Pasal N` (171), `## PENJELASAN UMUM`, dan `## PENGESAHAN DAN PENGUNDANGAN`.

**Pemisahan anotasi.** Unsur di bawah dibuang dari teks bersih dan disimpan sebagai anotasi atau metadata. Unsur itu tidak dikirim ke chunker, BM25, embedder, Spark, atau anggaran token.

| Unsur | Cara mengenali (satu pola, ketat) | Disimpan sebagai |
|---|---|---|
| Frontmatter | baris pertama `---` sampai `---` kedua | metadata dokumen; bahan baris status Perppu |
| Disclaimer editorial | baris non-kosong pertama setelah frontmatter, bunyi persis | metadata (disclosure) |
| Label tebal | baris yang seluruhnya `**…**`, bunyinya salah satu dari dua label yang dikenal, dan merupakan baris non-kosong pertama setelah `### Pasal N` | anotasi `{alamat Pasal, sumber, offset awal Pasal di teks bersih}` |
| Penanda `[^n]` di isi | `[^` + angka + `]` di dalam baris isi | anotasi `{n, offset di teks bersih tempat penanda dibuang}` |
| Pemisah `---` terakhir dan definisi footnote | `---` terakhir dan baris `[^n]: …` sesudahnya | teks definisi, ditautkan ke referensinya |
| `**` di judul naskah | pembungkus `**` dibuang, teks judul tetap | — |

Detektor penanda dijalankan atas teks bersih, bukan berkas mentah: kunci `catatan` di frontmatter memuat teks literal `[^n]` yang bukan referensi.

**Normalisasi.** Setelah pembuangan, deretan dua baris kosong atau lebih diciutkan menjadi satu baris kosong; awal dan akhir teks dipangkas; teks diakhiri satu LF. Tidak ada normalisasi lain (kutip, dash, spasi, huruf besar). Heading Markdown (`## BAB …`, `### Pasal N`, `#### Penjelasan Pasal N`) tetap di teks bersih apa adanya, sehingga semua chunker dan peran A melihat struktur yang sama. Pemuat menyimpan peta offset teks bersih ke nomor baris berkas untuk tampilan dan audit.

**Kalimat penutup rincian.** Baris batang tubuh yang diawali huruf kecil sah hanya bila baris non-kosong sebelumnya adalah butir rincian (`a.` atau `1.`) yang diakhiri `;`, `; atau`, atau `; dan`. Baris itu adalah kalimat penutup ayat, bukan bagian butir terakhir (contoh Pasal 102 ayat (1)). Aturan berbasis pola, bukan pengecualian per baris. Pencocokan "Cukup jelas" di Penjelasan tidak bergantung pada titik (Penjelasan Pasal 153E ayat (2) tanpa titik).

**Bagian (`section`).**

| `section` | Rentang | Isi |
|---|---|---|
| `pembukaan` | judul naskah sampai "Menetapkan" | judul, Menimbang, Mengingat |
| `penjelasan_umum` | `## PENJELASAN UMUM` sampai heading BAB pertama | Penjelasan Umum |
| `batang_tubuh` | `### Pasal N` sampai sebelum `#### Penjelasan Pasal N`, ditambah heading BAB, Bagian, dan Paragraf | ketentuan |
| `penjelasan_pasal` | `#### Penjelasan Pasal N` sampai heading berikutnya yang bukan bagian Penjelasan | Penjelasan per Pasal |
| `pengesahan` | `## PENGESAHAN DAN PENGUNDANGAN` sampai akhir teks bersih | tanda tangan, LN/TLN |

Kelima bagian tetap di teks bersih. Cakupan retrieval default (`batang_tubuh`, `penjelasan_pasal`, `penjelasan_umum`) adalah filter di `config/retrieval`, bukan pembuangan teks, sehingga mengubah cakupan tidak menggeser offset.

**Alamat kanonik.** Setiap potongan, span, dan baris status membawa `section` dan nomor Pasal. Alamat menyertakan bagian: `UU 40/2007 › Pasal 86 › ayat (9)` untuk batang tubuh dan `UU 40/2007 › Penjelasan › Pasal 86 › Ayat (9)` untuk Penjelasan. Kunci unik = (`section`, Pasal, ayat, huruf). Alamat tingkat huruf berformat `<alamat ayat> › huruf a` (huruf kecil, tanpa kurung), mis. `UU 40/2007 › Pasal 142 › ayat (2) › huruf a` (H-067, V14). BAB, Bagian, dan Paragraf diturunkan dari heading fisik terdekat (153A–153J: BAB XI); nomor Bagian dan Paragraf berulang antar BAB, jadi bukan kunci. Urutan Pasal mengikuti urutan kemunculan, bukan urutan numerik. Verifier uji 1 menolak kutipan yang nomornya benar tetapi bagiannya salah.

**Usulan baris status.** Pemuat hanya **mengusulkan** baris `StatusTable` (§5) dari anotasi. Isi tabel milik operator dan berlaku setelah operator menyetujui versinya (H-009).

| Sumber anotasi | Ketentuan yang diusulkan | Rujukan |
|---|---|---|
| Entri Perppu di frontmatter | Pasal 1, 7, 32, 153 (perubahan) dan 153A–153J (penyisipan), batang tubuh | `amended_by`: Perppu 2/2022 jo. UU 6/2023 |
| Label di bawah Pasal 86 + `[^1]` + entri MK di frontmatter | Pasal 86 ayat (9) saja, batang tubuh | `interpreted_by`: 84/PUU-XI/2013 |
| Label di bawah Pasal 142 + `[^2]` + entri UU 24/2011 di frontmatter | Pasal 142 ayat (2) huruf a, batang tubuh | UU 24/2011 Pasal 67, di `note` dan `source` |
| Tanpa anotasi | ketentuan lain | `default_rule` dari `config/corpus` |

String sumber Perppu di frontmatter diurai dengan pola sempit khusus string itu; bila pola gagal atau menghasilkan Pasal yang tidak ada di berkas, pemuat menolak. Konsistensi silang yang diperiksa: setiap label punya entri frontmatter yang cocok, setiap referensi footnote punya definisi dan entri frontmatter "(lihat footnote)", dan setiap Pasal yang disebut frontmatter ada di berkas. Ketidakcocokan ditolak dengan pesan yang menyebut baris.

**Uji penolakan pemuat (R1–R13).** Karena hash dipatok, sebagian besar uji struktur tidak pernah gagal pada berkas asli. Uji dijalankan atas salinan termutasi yang dibuat saat test (bukan salinan korpus yang di-commit), sebagai pertahanan berlapis bila korpus dibekukan ulang.

| # | Masukan uji | Hasil yang diharapkan |
|---|---|---|
| R1 | Berkas hilang, kosong, atau bukan UTF-8 valid | tolak, sebut jalur dan sebab |
| R2 | Satu byte diubah (hash asing) | tolak, sebut hash diterima dan hash yang diharapkan |
| R3 | Salinan CRLF | tolak karena `\r`, sebut baris pertama; diuji juga lewat checkout autocrlf (G-16) |
| R4 | Salinan ber-BOM | tolak |
| R5 | Penanda tersisa di teks bersih (`[^`, baris `[^n]:`, `**`, `---`, kunci frontmatter) | tolak, sebut offset dan baris asal |
| R6 | Referensi footnote tanpa definisi, definisi tanpa referensi, atau jumlah ≠ 2 | tolak |
| R7 | Label tebal tak dikenal, atau label bukan baris non-kosong pertama di bawah `### Pasal` | tolak |
| R8 | Urutan `(n)` rusak dalam satu Pasal (lompat, ulang, tidak mulai 1) | tolak, sebut Pasal dan baris |
| R9 | Baris batang tubuh diawali huruf kecil yang tidak memenuhi aturan kalimat penutup rincian | tolak |
| R10 | Jumlah `### Pasal` atau `#### Penjelasan Pasal` ≠ 171, nomor ganda, atau urutan Penjelasan tidak sama dengan urutan Pasal | tolak |
| R11 | Heading di luar pola yang sah ("Format berkas" di atas) | tolak |
| R12 | Frontmatter: kunci tidak sama dengan daftar kunci berkas beku, string sumber tidak terurai, Pasal yang disebut tidak ada, atau `catatan_koreksi`/`perubahan_pasca_pakai` tidak kosong | tolak sampai aturan untuk isi itu dispesifikasikan |
| R13 | Dua kali muat berkas yang sama | `clean_sha256` identik (determinisme) |

Kunci frontmatter berkas beku: `jenis`, `nomor`, `tahun`, `tentang`, `konsolidasi_dalam_satu_naskah_berdasarkan` (tiga string: Perppu 2/2022 jo. UU 6/2023, UU 24/2011, Putusan MK 84/PUU-XI/2013), `lembaran_negara`, `catatan`, `catatan_koreksi`, `perubahan_pasca_pakai`.

## 3. Chunk

| Field | Tipe | Isi | Pemilik |
|---|---|---|---|
| `chunk_id` | string | hash `(doc_id, start, end, chunker_key)` | Sistem |
| `doc_id` | string | | Sistem |
| `chunker_key` | string | hash chunker + parameter + versi skema | Sistem |
| `start`, `end` | int | offset di teks bersih | Sistem |
| `clean_sha256` | string | teks bersih yang dipakai (H-046) | Sistem |
| `section` | enum `pembukaan` / `penjelasan_umum` / `batang_tubuh` / `penjelasan_pasal` / `pengesahan` | bagian dokumen (G-20, H-046); cakupan retrieval default di config: `batang_tubuh`, `penjelasan_pasal`, `penjelasan_umum` | Sistem |
| `address` | string | label alamat kanonik dengan bagian (§2 "Alamat kanonik"): `"<peraturan> › Pasal <n> › ayat (<m>)"` untuk batang tubuh, `"<peraturan> › Penjelasan › Pasal <n> › Ayat (<m>)"` untuk Penjelasan. Potongan yang melintasi beberapa unit memakai alamat unit pertama dan terakhir, `"<alamat awal> – <alamat akhir>"` | Sistem |
| `address_levels` | array of `{level: string, label: string}` | alamat terurai, termasuk `section` | Sistem |
| `tokens_local` | int | token teks sumber potongan | Sistem |
| `warnings` | array of string | mis. "no structural marker, fallback per section" | Sistem |

`fixed_size` (H-062): jendela tetap atas teks bersih dalam cakupan retrieval secara berurutan, melintasi batas Pasal dan `section`; `section` = section posisi awal potongan, `address` = rentang unit pertama dan terakhir; filter cakupan retrieval tetap per `section`.

Chunker struktur (H-064): batas potongan ayat pertama tiap Pasal mencakup heading Pasal. Ini hanya batas potongan; unit alamat untuk Recall@K tetap konvensi `docs/scenarios/M1.2.md` A4 (batas potongan bukan unit alamat). Alamat tingkat huruf berformat `› huruf a` (§2, H-067).

Alamat diberikan dari peta alamat yang sama untuk semua chunker (prinsip keadilan, `docs/MILESTONES.md`). Peta alamat UU PT berasal dari parser struktur tulisan tangan (alamat kanonik §2); peta alamat akta berasal dari `SchemaA` versi aktif, karena akta tidak punya parser tangan.

## 4. Item (butir) dan SplitRecord

**Item**

| Field | Tipe | Isi | Pemilik |
|---|---|---|---|
| `id` | string | | Sistem |
| `family` | enum `uupt` / `akta` | | Operator |
| `query` | string | | Operator, atau Spark lalu disetujui operator |
| `doc_id` | string | dokumen gold | Operator |
| `gold_spans` | array of `{start: int, end: int}` | span gold atas teks bersih; kosong = butir wajib tolak (mode `tolak`, H-092; butir lama `parafrase` + gold kosong, mis. `kontrol-K-08`, tetap sah). Span menandai semua ayat yang dibutuhkan untuk menjawab: boleh beberapa ayat, sampai seluruh Pasal bila semuanya relevan, tidak lebih (H-048). Sistem memecahnya di batas ayat menjadi bagian-ayat sebelum metrik dihitung (`docs/EVAL-SPEC.md` §6); operator tidak memecahnya sendiri | Operator |
| `clean_sha256` | string | teks bersih tempat span ditulis (H-046) | Sistem |
| `mode` | enum `literal` / `parafrase` / `tolak` | `tolak` = butir wajib tolak (H-092; akta dan UU PT sejak H-095, H-099 V4): invarian `mode = tolak` ⟹ `gold_spans = []`; arah sebaliknya tidak dipaksa. Sah untuk `family` ∈ {`akta`, `uupt`}; pemuat butir menolak `tolak` ber-gold dan nilai di luar enum (mis. `unanswerable`, nama `ProposalRecord.body.mode`). Sumber: H-092, H-095, H-099 | Operator |
| `origin` | enum `operator` / `spark_disetujui` | asal (H-006) | Sistem dari jalur masuk |
| `review_status` | enum `disetujui` / `diubah` / null | hanya untuk `spark_disetujui`; `null` untuk `operator` | Operator |
| `proposal_id` | string \| null | rujukan `ProposalD` | Sistem |
| `reference_date` | date \| null | tanggal acuan uji 3; untuk `uupt` harus ≥ 2022-12-30 (H-046), lebih awal ditolak saat masuk | Operator |
| `scene_checked` | bool | dicocokkan manual ke teks untuk adegan video (H-011) | Operator |
| `operator_note` | string \| null | | Operator |
| `created_at` | timestamp | | Sistem |

Split tidak disimpan di `Item`; dibaca dari `SplitRecord` supaya penambahan butir tidak mengubah butir lama.

**SplitRecord** (H-015, H-049). Hanya untuk `uupt`; keluarga akta tidak punya `SplitRecord` (H-054).

| Field | Tipe | Isi | Pemilik |
|---|---|---|---|
| `family` | enum | | Sistem |
| `split_version` | int | naik saat butir baru ditambahkan | Sistem |
| `seed` | int | dari `config/grid` | Operator |
| `held_out_ratio` | number | dari `config/grid`, `0.4` (H-049) | Operator |
| `strata` | array of string | `["origin", "mode"]` | Sistem |
| `assignments` | array of `{item_id: string, split: "tune" / "held_out", added_in_version: int}` | penugasan lama tidak pernah berubah | Sistem |
| `control_in_held_out` | int | jumlah butir `operator` di held-out; harus ≥ 3 untuk UU PT | Sistem |

Contoh Item (placeholder):

```json
{
  "id": "<item_id>",
  "family": "uupt",
  "query": "<query>",
  "doc_id": "<doc_id>",
  "gold_spans": [{"start": 0, "end": 0}],
  "clean_sha256": "<sha256>",
  "mode": "parafrase",
  "origin": "operator",
  "review_status": null,
  "proposal_id": null,
  "reference_date": null,
  "scene_checked": false,
  "operator_note": null,
  "created_at": "<timestamp>"
}
```

## 5. StatusTable (H-009)

Isi tabel **hanya** berasal dari operator: pemuat mengurai anotasi di berkas konsolidasi UU PT (H-031) menjadi baris, lalu operator menyetujui versinya. Agen **DILARANG** mengisi atau mengubah entri.

| Field | Tipe | Isi |
|---|---|---|
| `version` | int | |
| `approved_by_operator` | bool | uji 3 hanya berjalan dengan versi yang disetujui |
| `source` | string | rujukan anotasi (UU pengubah atau nomor putusan MK) dan hash berkas konsolidasi |
| `entries[]` | array | per ketentuan (pasal atau ayat), diurai dari anotasi konsolidasi (H-031). Hanya ketentuan beranotasi (H-046): Pasal 1, 7, 32, 153, 153A–153J (Perppu), Pasal 86 ayat (9) (MK), Pasal 142 ayat (2) huruf a (UU 24/2011, `berlaku` + `note`). Ketentuan lain memakai `default_rule` |
| `default_rule` | object | `{status: "berlaku", effective_from: <tanggal pengundangan dari blok PENGESAHAN>}` untuk ketentuan tanpa entri; nilainya dari `config/corpus`, disetujui operator bersama versi tabel (H-046) |
| `entries[].doc_id` | string | |
| `entries[].address` | string | alamat kanonik ketentuan, termasuk bagian (§2 "Alamat kanonik", G-20) |
| `entries[].amended_by` | array of string | UU pengubah |
| `entries[].interpreted_by` | array of string | nomor putusan MK |
| `entries[].effective_from` | date \| null | berlaku sejak (versi teks ini) |
| `entries[].status` | enum `berlaku` / `dicabut` / `berlaku_bersyarat` | `berlaku_bersyarat` untuk ketentuan yang dimaknai bersyarat oleh MK |
| `entries[].note` | string \| null | catatan operator |

## 6. SchemaA — keluaran Spark peran A

**JSON Schema untuk `text.format` (`strict: true`).** Hierarki ditulis sebagai daftar datar berurutan, bukan pohon (H-016).

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["family", "levels", "default_chunk_level", "notes"],
  "properties": {
    "family": {"type": "string"},
    "levels": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["order", "name", "marker_pattern", "examples", "parent_order", "is_chunk_unit"],
        "properties": {
          "order": {"type": "integer"},
          "name": {"type": "string"},
          "marker_pattern": {"type": "string"},
          "examples": {"type": "array", "items": {"type": "string"}},
          "parent_order": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
          "is_chunk_unit": {"type": "boolean"}
        }
      }
    },
    "default_chunk_level": {"type": "integer"},
    "notes": {"anyOf": [{"type": "string"}, {"type": "null"}]}
  }
}
```

**Penyimpanan (`SchemaRecord`)**

| Field | Tipe | Isi | Pemilik |
|---|---|---|---|
| `family` | enum | | Sistem |
| `schema_version` | int | v1 = Spark, v2+ = koreksi | Sistem |
| `source` | enum `spark` / `operator` | | Sistem |
| `parent_version` | int \| null | versi yang dikoreksi | Sistem |
| `body` | objek sesuai skema di atas | | Spark (v1), Operator (v2+) |
| `validation` | array of `{order: int, example: string, matched: bool}` | pola tiap level diuji terhadap contohnya sendiri | Sistem |
| `run_id` | string \| null | | Sistem |
| `created_at` | timestamp | informatif (H-072) | Sistem |
| `operator_note` | string \| null | catatan koreksi, maks 2000 karakter; `null` untuk `spark` | Operator |
| `sample` | array of `{doc_id, clean_sha256}` | dokumen sampel induksi; koreksi mewarisi dari induk | Sistem |
| `sample_checked` | bool | pemeriksaan "contoh ada di sampel" dijalankan; `false` bila dokumen sampel tak bisa dimuat | Sistem |
| `cache_key` | string \| null | kunci cache panggilan A; `null` untuk `operator` | Sistem |

Koreksi operator **HARUS** disimpan sebagai versi baru; versi lama tidak ditimpa. Versi dinomori urut; `source` (`spark` / `operator`) pembeda, jadi induksi Spark dengan masukan berbeda juga mendapat versi baru (H-072). Disimpan di `runs/schemas/<family>/v<n>.json`.

**Aturan semantik** (keluaran Spark dan koreksi operator, sama): struktur sesuai skema di atas; `levels` tidak kosong; `order` naik ketat; `parent_order` null atau `order` yang lebih awal; `default_chunk_level` ada dan `is_chunk_unit = true`; `marker_pattern` dikompilasi (`re.MULTILINE`), tidak cocok string kosong, tanpa kuantor bersarang, maks 500 karakter; tiap `examples` satu baris (maks 300 karakter), cocok dengan pola levelnya, dan ditemukan persis di sampel; `family` sama dengan yang diminta.

**Semantik induk** (H-084): `parent_order` menunjuk induk paling spesifik; bila penanda level itu tidak muncul di teks, induk = level berikutnya pada rantai `parent_order` (pengelompokan terdekat yang ada; untuk peraturan per Lampiran II UU 12/2011: Paragraf, else Bagian, else Bab, else Buku, else tanpa induk). Skema dan validator tidak berubah.

**Keluaran ditolak.** Keluaran Spark yang gagal aturan semantik bukan `SchemaRecord`: disimpan di `runs/schemas/<family>/rejected/<run_id>.json` sebagai `{run_id, cache_key, family, body, errors[], created_at, sample}`, tidak berversi dan tidak dipakai chunker. R3 membawanya di `schemas_rejected` untuk U5.

## 7. HeaderB — keluaran Spark peran B

**JSON Schema (`strict: true`)**

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["chunk_id", "header"],
  "properties": {
    "chunk_id": {"type": "string"},
    "header": {"type": "string"}
  }
}
```

**Penyimpanan**

| Field | Tipe | Isi | Pemilik |
|---|---|---|---|
| `chunk_id` | string | harus sama dengan potongan yang diminta | Spark, diperiksa Sistem |
| `header` | string | teks header | Spark |
| `granularity` | enum `pasal` / `ayat` / `fixed_size` | H-038; `fixed_size` = header untuk potongan `fixed_size` (H-069), satu header per `chunk_id` | Sistem dari konfigurasi |
| `prompt_version` | string | | Sistem |
| `tokens_local` | int | token header, masuk anggaran (H-004) | Sistem |
| `run_id` | string | | Sistem |

## 8. AnswerC dan VerifierResult — peran C

**JSON Schema keluaran Spark (`strict: true`)**, bentuk H-004 `{status, jawaban, kutipan[]}`:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["status", "jawaban", "kutipan"],
  "properties": {
    "status": {"type": "string", "enum": ["jawab", "tolak", "bukti_tidak_cukup"]},
    "jawaban": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    "kutipan": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["alamat", "teks"],
        "properties": {
          "alamat": {"type": "string"},
          "teks": {"type": "string"}
        }
      }
    }
  }
}
```

`alamat` adalah alamat unit yang disalin dari konteks (§3 `address`), bukan label rentang `A – B` potongan (H-067, V5-strict; verifier uji 1 menolak rentang). `jawaban` boleh `null` bila status bukan `jawab`.

**Penyimpanan `AnswerRecord`**

| Field | Tipe | Isi | Pemilik |
|---|---|---|---|
| `answer_id` | string | | Sistem |
| `item_id` | string | | Sistem |
| `setting_id` | string | | Sistem |
| `slot` | enum `best` / `baseline` | | Sistem |
| `model_profile` | string | kunci daftar model di `config/model` (Contributor atau Glimmer lokal, H-053). Jawaban Glimmer adalah run terpisah dan tidak pernah digabung dengan jawaban Contributor dalam satu tabel perbandingan tanpa label | Sistem |
| `context_chunk_ids` | array of string | potongan dalam anggaran, berurutan | Sistem |
| `budget_tokens` | int | sama untuk kedua slot | Sistem |
| `output` | objek sesuai skema di atas | | Spark |
| `flags` | array of string | informatif (H-066): penanda semantik, jawaban ditandai bukan ditolak. Nilai yang dipakai kode: `jawab_tanpa_kutipan` (`status = jawab`, `kutipan` kosong), `jawab_tanpa_jawaban` (`status = jawab`, `jawaban` kosong atau hanya spasi). Daftar kosong bila tidak ada. Penilaian kutipan tetap milik verifier | Sistem |
| `run_id` | string | | Sistem |

**VerifierResult** (per kutipan)

| Field | Tipe | Isi |
|---|---|---|
| `answer_id` | string | |
| `citation_index` | int | |
| `exists` | enum `lulus` / `gagal` | uji 1: alamat ada di peta alamat |
| `faithful` | enum `lulus` / `gagal` | uji 2: persis, lalu fuzzy dengan ambang dan `D_max` dari `config/verifier`, dan pengaman digit (`docs/EVAL-SPEC.md` §10, H-067) |
| `faithful_score` | number \| null | skor fuzzy bila tidak persis |
| `valid_on_date` | enum `berlaku` / `dicabut` / `berlaku_bersyarat` / `tidak_dijalankan` | uji 3, stretch (H-017) |
| `status_table_version` | int \| null | |
| `matched_chunk_id` | string \| null | |

**RejectionSummary** (per kombinasi, hitungan mentah). Kunci: (`setting_id`, `slot`, `model_profile`) (H-067, V11). Jawaban beda `model_profile` tidak pernah dijumlahkan (H-028, H-060).

| Field | Tipe |
|---|---|
| `setting_id` | string |
| `slot` | enum `best` / `baseline` |
| `model_profile` | string |
| `answered_supported` | int |
| `answered_unsupported` | int |
| `abstained_correct` | int |
| `abstained_should_answer` | int |
| `n_items` | int |

Definisi sel di `docs/EVAL-SPEC.md` §10.

## 9. ProposalD — keluaran Spark peran D

**JSON Schema (`strict: true`)**

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["usulan"],
  "properties": {
    "usulan": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["query", "mode", "doc_id", "teks_gold", "start", "end"],
        "properties": {
          "query": {"type": "string"},
          "mode": {"type": "string", "enum": ["literal", "parafrase"]},
          "doc_id": {"type": "string"},
          "teks_gold": {"type": "string"},
          "start": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
          "end": {"anyOf": [{"type": "integer"}, {"type": "null"}]}
        }
      }
    }
  }
}
```

Sistem mencari `teks_gold` di dokumen untuk menetapkan offset. Bila Spark memberi offset, offset itu harus cocok dengan teks. Enum `mode` skema `ProposalD` = {`literal`, `parafrase`} (tidak berubah; `schema_hash` tetap).

**Varian `unanswerable` (H-092, P1/P5)** — skema keluaran terpisah `ProposalU` (`strict: true`; `family` ∈ {`akta`, `uupt`} sejak H-095, H-099 V1; prompt per keluarga, lihat "Prompt per (keluarga, mode)" di bawah):

```json
{"type": "object", "additionalProperties": false, "required": ["usulan"],
 "properties": {"usulan": {"type": "array", "items": {"type": "object", "additionalProperties": false,
   "required": ["query", "doc_id", "alasan_kode", "alasan_teks"],
   "properties": {"query": {"type": "string"}, "doc_id": {"type": "string"},
     "alasan_kode": {"type": "string", "enum": ["data_tidak_dimuat", "di_luar_akta", "rincian_tidak_diatur"]},
     "alasan_teks": {"type": "string"}}}}}}
```

Tanpa `mode`, `teks_gold`, `start`, `end`. `ProposalRecord` varian ini: `body` = `{query, mode: "unanswerable", doc_id, alasan_kode, alasan_teks}` (`mode` diisi sistem), `resolved_span = null`, `validation = null`, field baru `absence_check` dan `duplicate_of`:

| Field | Tipe | Isi |
|---|---|---|
| `absence_check.status` | `ok` / `doubtful` | `doubtful` bila ada >= 1 alasan; tetap disimpan dan dapat di-Approve (P3) |
| `absence_check.reasons` | array, urutan tetap | `lexical_overlap`, `dense_similar`, `no_distinctive_terms`, `dense_unavailable` |
| `absence_check.max_cov` | `{num: int, den: int}` | irisan terbesar token distingtif query dengan top-K; `den` = jumlah token distingtif; `0/0` = tidak ada (tanpa float) |
| `absence_check.max_cosine` | number \| null | cosine maksimum top-K dense; null bila dense mati atau tak tersedia |
| `absence_check.top_k` | array `{source: bm25/dense, rank, unit_text}` | daftar BM25 lalu dense, tanpa dedup, maks 2K |
| `absence_check.config_hash` | string | hash `config/proposals [unanswerable]` saat dihitung (R: daftar usulan melaporkan hash sekarang di `check_config_hash`) |
| `duplicate_of` | string \| null | informatif, dihitung server saat daftar/simpan (tidak disimpan): `proposal_id` rekaman `unanswerable` terdahulu dengan `doc_id` dan query ternormalisasi sama; tidak membuang usulan |

Pemeriksaan ketiadaan jawaban lokal dan deterministik atas potongan `structure_schema` skema A **aktif keluarga dokumen** (akta H-092; UU PT H-099 V2; tanpa skema aktif -> `404 not_found` sebelum Spark) (BM25 produksi dan dense bge-m3 opsional; satu fungsi tokenisasi). Nilai di `config/proposals.toml` `[unanswerable]`. Pada `diubah`, `absence_check` dihitung ulang atas query baru; `body` tidak berubah. Sumber: H-092, H-099.

**Prompt per (keluarga, mode) (H-099 V3).** `prompts/d/versions.json`: `current` (v1, mode ber-span), `by_mode` (`unanswerable` -> v2), dan `by_family_mode` (`uupt.unanswerable` -> v3). Satu fungsi lookup (`backend/proposal/prompt.py` `prompt_for`), dipanggil sebelum klien Spark dibuat: (1) `by_family_mode[family][mode]` bila ada; (2) bila tidak ada dan `mode = unanswerable`: hanya `family = akta` jatuh ke `by_mode.unanswerable`, keluarga lain = `config_invalid`; (3) mode ber-span: `by_mode[mode]` bila ada, selain itu `current`. Versi hasil lookup untuk `unanswerable` wajib memuat `"unanswerable"` di `modes`; versi tak ada atau tanpa `modes` itu = `config_invalid` (W4 `503 model_unavailable`, CLI exit 2, nol panggilan). Kunci cache akta `unanswerable` dan kunci UU PT `literal`/`parafrase` tidak berubah; skema `ProposalU` dan enum `alasan_kode` tidak berubah (makna untuk UU PT dijelaskan di v3; `di_luar_akta` = di luar dokumen). Batas usulan per panggilan: `[unanswerable] max_per_call`; kunci opsional `max_per_call_uupt` (H-099 Q1 a1; bilangan bulat > 0, belum diisi) hanya menimpa batas `uupt`, dan karena batas ikut kunci cache D, hanya kunci `uupt` `unanswerable` yang berubah. Sumber: H-095, H-099.

**Penyimpanan `ProposalRecord`**

| Field | Tipe | Isi | Pemilik |
|---|---|---|---|
| `proposal_id` | string | | Sistem |
| `family` | enum | | Sistem |
| `body` | satu elemen `usulan` | | Spark |
| `resolved_span` | `{start: int, end: int}` \| null | hasil pencarian teks | Sistem |
| `validation` | `{offset_found: bool, text_matches: bool}` | | Sistem |
| `review_status` | enum `usulan` / `disetujui` / `diubah` / `ditolak` | transisi hanya dari `usulan` | Operator |
| `edited` | `{query: string, gold_spans: array, mode: string}` \| null | isi setelah diubah | Operator |
| `operator_note` | string \| null | | Operator |
| `reviewed_at` | timestamp \| null | | Sistem |
| `item_id` | string \| null | butir yang lahir dari usulan ini | Sistem |
| `run_id` | string | | Sistem |

Status `diubah` diperlakukan sebagai disetujui setelah diubah; `origin` tetap `spark_disetujui` dan isi asli tetap tersimpan (H-035).

## 10. Setting, ItemMetrics, GridPoint, Frontier

**Setting**

| Field | Tipe | Isi |
|---|---|---|
| `setting_id` | string | hash isi kanonik field di bawah |
| `family` | enum | |
| `chunker` | enum `structure_handwritten` / `structure_schema` / `fixed_size` | H-012 |
| `chunk_size_tokens` | int \| null | hanya `fixed_size` |
| `overlap_tokens` | int \| null | hanya `fixed_size` |
| `schema_version` | int \| null | hanya `structure_schema` |
| `retrieval_mode` | enum `dense` / `bm25` / `hybrid` | |
| `header_b` | bool | |
| `budget_tokens` | int | |

**GridItem** (butir untuk grid; `item_set_hash` atasnya ikut kunci cache): `{id, family, origin, mode, clean_sha256, gold_spans, query, doc_id}`.

| Field | Tipe | Isi |
|---|---|---|
| `doc_id` | string | keluarga multi-dokumen (akta, H-086): `doc_id` dokumen yang dirujuk butir; retrieval butir itu hanya atas dokumen tersebut. String kosong `""` untuk keluarga satu dokumen (UU PT), walau berkas butir UU PT memuat `doc_id`. Bila kosong, field ini dibuang dari baris `item_set_hash`, sehingga hash butir UU PT sama persis dengan sebelum H-086; bila terisi, ikut hash |

**ItemMetrics**

| Field | Tipe | Isi |
|---|---|---|
| `item_id`, `setting_id` | string | |
| `split` | enum `tune` / `held_out` \| null | dari `SplitRecord`; `null` untuk akta (tanpa split, H-054, H-059) |
| `gold_chars` | int | |
| `covered_gold_chars` | int | |
| `span_recall` | number \| null | `null` bila tanpa gold |
| `retrieved_tokens` | int | token lokal yang dipakai, termasuk header |
| `gold_tokens_retrieved` | int | |
| `token_precision` | number \| null | |
| `reciprocal_rank` | number \| null | |
| `recall_at_k` | number \| null | |
| `fully_covered` | bool \| null | semua span gold tertutup |
| `retrieved_chunk_ids` | array of string | |
| `gold_chars_outside_units` | int \| absen | **hanya akta** (H-090 P7): karakter gold (setelah digabung) di luar semua unit peta alamat. Absen untuk UU PT (baris metrik UU PT byte-identik dengan sebelumnya). Butir ber-gold yang seluruh gold-nya di luar unit: `parts_total = 0`, `recall_at_k = null` (tidak dihitung di rata-rata, tidak hilang diam-diam: dihitung di `unit_map.n_items_recall_null`) |

Pembilang dan penyebut disimpan sebagai integer supaya UI bisa menampilkan hitungan mentah.

**GridPoint**

| Field | Tipe | Isi |
|---|---|---|
| `setting_id` | string | |
| `split` | enum `tune` / `held_out` \| null | `null` untuk akta (H-054, H-059) |
| `budget_tokens` | int | |
| `mean_span_recall` | number \| null | `null` bila tanpa butir bergold (H-061) |
| `mean_token_precision` | number \| null | rata-rata atas nilai non-null; `null` bila semua butir null (M1.2 A7b, H-059) |
| `mrr` | number \| null | `null` bila tanpa butir bergold (H-061) |
| `mean_retrieved_tokens` | number \| null | sumbu X frontier; atas butir bergold (M1.2 A8); `null` bila tanpa butir bergold (H-061) |
| `fully_covered_count` | `{covered: int, total: int}` | "covered x of y" |
| `dominated` | bool | |

**Peta unit akta (H-090, M4.1)**: untuk `family = akta`, `ChunkSet.amap` dan `units` (unit pemecah gold Recall@K, label C, V5, boundary coherence) = `schema_address_map(doc, skema A akta AKTIF)` untuk SEMUA setting grid (juga `fixed_size`; setting yang dipin ke versi skema non-aktif tetap memakai peta aktif, P11). Unit = penanda `default_chunk_level` (Pasal, Kepala Akta, Komparisi, Penutup Akta, dst.) tanpa spasi tepi; ayat/huruf = `Rincian` (alamat sah di V5, tidak memecah gold, P3). Skema aktif Spark tetap dipakai dan ditandai `schema_approved: false` (P1). Teks di luar unit (LF antar unit, teks sebelum penanda pertama) tidak berunit (P7). Akta tanpa skema aktif atau tanpa penanda di dokumen itu: peta cadangan = satu unit `<awalan> › Batang Tubuh` + peringatan di `AddressMap.notes`, bertanda `kind = "fallback"` (P8); `Batang Tubuh` tidak sah di V5 bila peta skema dipakai (P6). UU PT tidak berubah satu byte.
- Kunci: `config_hash` grid akta memuat `_unit_map = {schema: {family, schema_version, schema_hash, source} | null, unit_map_version}` (`SchemaBinding.identity()` skema aktif) walau grid tanpa setting `structure_schema`. `unit_map_version` ada di `config/akta_unitmap.toml` (dimuat lewat `FAMILY_CONFIGS["akta"]` di `backend/pipeline/grid_run.py`, ikut `cfgs` akta saja; bukan `retrieval`/`grid`). Hash dan kunci UU PT tidak berubah.
- Amplop `runs/grid/<kunci>.json` akta memuat blok `unit_map`: `{unit_map_version, schema_version, schema_hash, source, schema_approved, kind: "schema" | "fallback", fallback_doc_ids: [doc_id], recall_unit, n_items_recall_null, n_items_gold_partly_outside}` (`schema_*`/`source`/`schema_approved` null bila tak ada skema aktif) dan `recall_unit: "default_chunk_level"` di tingkat atas. `n_items_recall_null` = butir ber-gold dengan `parts_total = 0`; `n_items_gold_partly_outside` = butir dengan `parts_total > 0` dan `gold_chars_outside_units > 0` (dihitung atas setting pertama yang dijalankan; peta sama untuk semua setting). Amplop UU PT tidak memuat `unit_map` maupun `recall_unit`.
- `QualityMetrics` akta menambah `recall_unit` (P10: unit = penanda level default, TIDAK sebanding dengan unit ayat UU PT, H-048) dan `unit_map_kind` (`schema` / `fallback`, tanda "peta cadangan" untuk Recall@K/boundary, P8). Entri UU PT tidak memuatnya.
- Identitas peta saat run (S14): versi + hash skema + `unit_map_version` di blok `unit_map` amplop run; kunci grid berubah bila peta berubah, sehingga run dengan peta lama tidak dipakai ulang. Menampilkan verdict/jawaban tersimpan yang dibuat dengan peta lama sebagai "peta lama" (stale) adalah tugas replay (belum ada field identitas peta di rekaman jawaban; diteruskan ke slice replay).

**Cakupan butir Recall@K (I-65, H-090)**: `QualityMetrics.items_scope` UU PT = `[quality].recall_items` (`held_out`, H-065, tidak berubah). Keluarga tanpa split (akta): cakupan = semua butir ber-gold (`config/akta_unitmap.toml` `[recall].items = "all"`), `items_scope = "transfer"` (label dari `[recall].label`; bukan nilai split, H-054, tanpa kata held-out, H-078).

**Frontier**: `{family, split, budget_tokens, point_ids: array of string, grid_run_id}`. `split` `null` untuk akta; "transfer" hanya label laporan, bukan nilai data (H-054, H-059).

**Bentuk R3 `grid` akta (H-091, H-093; W62)**: `FamilySnapshot.grid` akta = `{all: {points, frontier}, selected: null, quality_comparison: null, skipped, grid_run_id, failed_settings, header_scope, transfer, final}`; tanpa `tune`/`held_out`. Titik `GridPoint` akta (`split = null`) membawa `label`: `"no structure recognized"` untuk `structure_handwritten` (satu potongan per akta, H-093; titik tidak dibuang) dan `null` untuk lainnya. Field `label` tidak ada di amplop `runs/grid` dan tidak ada di titik UU PT; ia ditambahkan saat R3 membangun tampilan. `transfer` = `{setting_id, chunker: "structure_schema", schema_version, retrieval_mode, header_b, budget_tokens, source_setting_id, label: "transfer test, no profile selection"}` atau `null` (lihat API.md §5); `final` = `bool`, benar bila `grid_run_id` di `config/akta_grid_final.toml` sama dengan `grid.grid_run_id` (berkas itu tidak masuk `config_hash`). `report.setting` akta = `transfer`. Bentuk UU PT tidak berubah satu byte.

**QualityMetrics** (per setting): `{setting_id, entity_preservation: number | null, boundary_coherence: number | null, recall_at_k: number | null, k: int}`. Penyebut nol (`|E| = 0`, `|Bnd| = 0`, atau agregat Recall@K tanpa butir ber-gold) → `null`, UI "n/a" (M1.5 A5 alt. N1, H-059). Definisi di `docs/EVAL-SPEC.md` §6–§7.

## 11. Profile

| Field | Tipe | Isi |
|---|---|---|
| `profile_version` | string | |
| `family` | enum | |
| `setting` | `Setting` | |
| `schema` | `SchemaRecord.body` \| null | disertakan utuh bila chunker skema |
| `corpus_hash` | string | hash kanonik atas pasangan `(doc_id, sha256)` semua dokumen keluarga profil itu, urut menurut `doc_id`; dokumen keluarga lain tidak ikut (H-068, M4.3 A1) |
| `config_hash` | string | hash konfigurasi pipeline untuk setting profil itu (informatif; impor W8 tidak memeriksanya). UU PT: hash pipeline umum. Akta: hash pipeline + `corpus_akta`, `akta_unitmap`, identitas skema A aktif (W66). Tidak sama dengan `config_hash` amplop grid, yang juga memuat identitas store header B dan skema semua setting grid (W67) |
| `chunk_set_hash` | string | untuk uji round-trip. Hash kanonik atas daftar pasangan `(chunk_id, teks)` terurut menurut (`doc_id`, `start`), tanpa data encoder (H-068, M4.3 A2-X) |
| `tokenizer` | `{name: string, version: string}` | |
| `clean_sha256`, `loader_rules_version` | string | teks bersih yang dipakai (H-046) |
| `packing` | enum `stop` / `skip` / `truncate` | aturan pengemasan (`docs/EVAL-SPEC.md` §3) |
| `embedder` | `{name: string, revision: string, max_seq_length: int}` \| null | H-042, tanpa prefix |
| `held_out` | `{n_items: int, by_origin: object, mean_span_recall: number \| null, mean_token_precision: number \| null, fully_covered: {covered: int, total: int}}` \| null | `mean_span_recall` dan `mean_token_precision` masing-masing `null` bila kelompok tak punya nilai non-null untuk metrik itu (konsisten H-061; H-068, M4.3 A10). `held_out` `null` untuk akta: butir akta dilaporkan per butir sebagai uji transfer, tanpa split (H-054) |
| `created_at` | timestamp | |

Profil yang dimuat dengan `corpus_hash` berbeda **HARUS** ditolak.

## 12. RunRecord

| Field | Tipe | Isi |
|---|---|---|
| `run_id` | string | |
| `kind` | enum `spark_a` / `spark_b` / `spark_c` / `spark_d` / `grid` / `measure` | |
| `created_at` | timestamp | |
| `cache_key` | string | `docs/ARCHITECTURE.md` §8 |
| `corpus_hash`, `config_hash` | string | |
| `clean_sha256`, `loader_rules_version` | string | teks bersih yang dipakai run (H-046) |
| `prompt_version`, `prompt_hash` | string \| null | |
| `model` | string \| null | `muse-spark-1.3-contributor`, atau model ID Glimmer untuk run pembanding H-047 |
| `effort` | string \| null | dari konfigurasi; untuk Glimmer = `reasoning_effort` yang dipin (H-047) |
| `tokenizer` | `{name, version}` | |
| `embedder` | `{name, revision, max_seq_length, n_truncated}` \| null | embedder dense dan jumlah potongan yang terpotong (H-042, G-22) |
| `packing` | enum \| null | aturan pengemasan yang dipakai (`docs/EVAL-SPEC.md` §3) |
| `usage_input_tokens` | int \| null | dari `usage` |
| `usage_cached_tokens` | int \| null | `usage.input_tokens_details.cached_tokens` |
| `usage_output_tokens` | int \| null | termasuk reasoning |
| `cost_usd_micros` | int \| null | dari `usage` × harga `config/model`; `0` untuk Glimmer lokal |
| `projected_cost_usd_micros` | int \| null | proyeksi cost guard (pembulatan ke atas per panggilan); diisi pada panggilan berbayar tanpa `usage` sah (usage rusak/hilang) dan pada panggilan gagal tanpa `usage` (timeout, 5xx, galat koneksi; H-063), per upaya timeout (timeout dua upaya = 2 × proyeksi; H-071). Setiap upaya yang timeout menambah 1 × proyeksi apa pun hasil upaya terakhir: timeout lalu 5xx/koneksi/usage rusak = (timeout + 1) × proyeksi; timeout lalu 4xx/429 habis = timeout × proyeksi. Pada record `ok` (atau galat dengan `usage`) yang didahului timeout, `cost_usd_micros` tetap murni usage × harga dan field ini = proyeksi × jumlah upaya timeout. Buku belanja memakai `(cost_usd_micros ?? 0) + (projected_cost_usd_micros ?? 0)` (M0.1 O-3, H-071) |
| `latency_ms` | int | |
| `host` | string | label mesin dari config (`authoritative` / `secondary`), bukan hostname; angka resmi hanya dari mesin otoritatif (H-027) |
| `device` | string | mis. `cuda:0` atau `cpu`, perangkat embedding dan model lokal |
| `provider` | string \| null | `meta` untuk Model API; `openrouter` untuk run dev/uji lewat OpenRouter (H-057), tidak pernah dipakai untuk angka yang dilaporkan; `lmstudio_local` untuk run pembanding Glimmer (H-047); `baseten` untuk run pembanding Spark Open di Baseten (H-060), hanya peran C, tidak pernah dipakai untuk angka utama |
| `quantization` | string \| null | kuantisasi Glimmer dari `config/model` (`Q4_K_M`, H-047); `null` untuk Model API |
| `status` | enum `ok` / `error` / `cached` / `replay` | |
| `error` | `{code: string, message: string}` \| null | tanpa key, tanpa stack trace |
| `failed_settings` | array of `{setting_id: string, reason: string, chunk_id: string \| null}` | hanya `kind=grid`; setting header-on yang gagal karena header hilang/kosong/basi/granularitas tak cocok (H-069). `reason` = `header_missing` / `header_invalid` / `header_stale` / `granularity_mismatch`; `chunk_id` = potongan pertama (offset awal naik) yang bermasalah. Setting itu tanpa `GridPoint`; run lanjut. Kosong `[]` bila tidak ada |

**Keluarga multi-dokumen (akta, H-086)**: `kind=grid` untuk akta menyimpan hash korpus keluarga, bukan hash satu dokumen.
- `corpus_hash` dan `clean_sha256` sama-sama berisi `family_corpus_hash`: sha256 atas JSON kanonik daftar pasangan `[doc_id, clean_sha256]` terurut menurut `doc_id` (tidak bergantung urutan masukan). Ini hash atas teks bersih (`clean_sha256`), bukan `sha256` berkas mentah; `corpus_hash` keluarga satu dokumen dan `Profile.corpus_hash` (§11) tetap seperti semula.
- `loader_rules_version` = nilai `loader_rules_version` yang berbeda antar dokumen, terurut dan digabung dengan koma (satu nilai bersama tampil sekali).
- `cache_key` memakai `family_corpus_hash` sebagai komponen korpus dan `split_version` `null` (akta tanpa split, H-054).
- Amplop `runs/grid/<kunci>.json` untuk akta: `split: null`, `selections: {}` (tanpa pemilihan profil), `quality_comparison: []`, dan `docs: [{doc_id, clean_sha256, loader_rules_version, n_items}]` terurut menurut `doc_id`. `metrics`, `points`, `frontiers` membawa `split: null`. `n_truncated_by_chunker` dijumlah lintas dokumen. `boundary_diff` (skema A) berbentuk `{versi: {doc_id: selisih}}`; untuk UU PT `{versi: selisih}`. Amplop UU PT tidak memuat `docs`.
